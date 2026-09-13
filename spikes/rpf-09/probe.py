"""RPF-09 cross-process persistence and HTTP boundary probe.

The probe starts the disposable Java/Spring candidate as a separate process,
copies only reviewed artifacts into a temporary local artifact store, and
sends constrained manifests. It deliberately never sends a raw artifact as
canonical metadata and never calls a Provider.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SCHEMA_VERSION = "rpf-control-plane-ingest-v1"


class ProbeFailure(RuntimeError):
    pass


class TransportFailure(ProbeFailure):
    pass


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def request_json(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None) -> HttpResponse:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            raw = response.read().decode("utf-8")
            return HttpResponse(response.status, json.loads(raw) if raw else {})
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw[:200]}
        return HttpResponse(error.code, parsed)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
        raise TransportFailure(f"HTTP transport unavailable: {method} {path}") from error


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def expect(response: HttpResponse, status: int, error_code: str | None = None) -> dict[str, Any]:
    require(response.status == status, f"Expected HTTP {status}, got {response.status}: {response.body}")
    if error_code is not None:
        require(response.body.get("error") == error_code, f"Expected {error_code}, got {response.body}")
    return response.body


def write_immutable(path: Path, content: bytes) -> str:
    """Local artifact-store writer: same content is idempotent, new content is rejected."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == content:
            return "IDEMPOTENT_EXISTING"
        raise ProbeFailure(f"IMMUTABLE_ARTIFACT_OVERWRITE_REJECTED:{path.name}")
    path.write_bytes(content)
    return "CREATED"


def artifact_identity(entity_type: str, document: dict[str, Any]) -> tuple[str, str, str | None, str | None, dict[str, Any]]:
    if entity_type == "RUN":
        entity = document["run"]
        source = entity["runtime"]
        return entity["run_id"], document["outcome"]["status"], entity.get("agent", {}).get("agent_version"), entity.get("evaluation_id"), source
    if entity_type == "EVALUATION":
        entity = document["evaluation"]
        source = entity["runtime"]
        return entity["evaluation_id"], entity["evaluation_status"], entity.get("agent", {}).get("agent_version"), entity.get("evaluation_id"), source
    if entity_type == "RELEASE_DECISION":
        entity = document["release_decision"]
        source = entity["source_identity"]
        evaluation_ref = entity.get("candidate_evaluation_ref") or {}
        return entity["release_decision_id"], entity["decision_status"], entity.get("evaluated_agent_version"), evaluation_ref.get("evaluation_id"), source
    raise ProbeFailure(f"Unsupported entity type: {entity_type}")


def build_manifest(entity_type: str, content: bytes, artifact_key: str, idempotency_key: str | None = None) -> dict[str, Any]:
    document = json.loads(content.decode("utf-8"))
    entity_id, outcome, agent_version, evaluation_id, source = artifact_identity(entity_type, document)
    artifact_ref = {
        "artifact_id": entity_id,
        "artifact_key": artifact_key,
        "artifact_kind": document["artifact_kind"],
        "schema_version": document["schema_version"],
        "content_sha256": sha256(content),
        "source_sha256": source["source_sha256"],
        "runtime_version": source["runtime_version"],
    }
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "outcome": outcome,
        "agent_version": agent_version,
        "evaluation_id": evaluation_id,
        "idempotency_key": idempotency_key or f"{entity_type}:{entity_id}:{artifact_ref['content_sha256']}",
        "artifact_ref": artifact_ref,
    }


def prepare_artifact(
    source_path: Path,
    entity_type: str,
    artifact_dir: Path,
    artifact_key: str,
    idempotency_key: str | None = None,
) -> tuple[dict[str, Any], Path, bytes]:
    content = source_path.read_bytes()
    target = artifact_dir / artifact_key
    result = write_immutable(target, content)
    require(result == "CREATED", f"Expected new artifact, got {result}")
    return build_manifest(entity_type, content, artifact_key, idempotency_key), target, content


class RunningService:
    def __init__(self, jar: Path, data_dir: Path, artifact_dir: Path, log_path: Path) -> None:
        self.port = choose_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.log_file = log_path.open("w", encoding="utf-8", newline="\n")
        self.process = subprocess.Popen(
            [
                "java",
                "-jar",
                str(jar.resolve()),
                "--server.address=127.0.0.1",
                f"--server.port={self.port}",
                f"--rpf.data-dir={data_dir.resolve().as_posix()}",
                f"--rpf.artifact-dir={artifact_dir.resolve().as_posix()}",
            ],
            cwd=ROOT,
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
        )
        self.wait_until_ready()

    def wait_until_ready(self) -> None:
        deadline = time.monotonic() + 30
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                tail = self.log_path_tail()
                raise ProbeFailure(f"Java Control Plane exited during startup: {tail}")
            try:
                response = request_json(self.base_url, "GET", "/api/v1/health")
                if response.status == 200 and response.body.get("readiness") == "READY":
                    return
                last_error = ProbeFailure(f"health={response.status}:{response.body}")
            except TransportFailure as error:
                last_error = error
            time.sleep(0.2)
        raise ProbeFailure(f"Control Plane did not become ready: {last_error}; {self.log_path_tail()}")

    def log_path_tail(self) -> str:
        try:
            self.log_file.flush()
            return "\n".join(self.log_file.name and Path(self.log_file.name).read_text(encoding="utf-8", errors="replace").splitlines()[-20:] or [])
        except OSError:
            return "<log unavailable>"

    def stop(self) -> None:
        if self.process.poll() is None:
            try:
                request_json(self.base_url, "POST", "/api/v1/probe/shutdown")
            except TransportFailure:
                pass
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if sys.platform.startswith("win"):
                    # The PID is the process created by this probe; taskkill
                    # is only a fallback after graceful shutdown timed out.
                    subprocess.run(
                        ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    self.process.kill()
                self.process.wait(timeout=5)
        elif sys.platform.startswith("win"):
            # A Windows launcher can report exit before its JVM child closes;
            # the tree fallback is still scoped to this exact PID.
            subprocess.run(
                ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        self.log_file.close()


def toolchain_snapshot() -> dict[str, Any]:
    return {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "java_on_path": shutil.which("java") is not None,
        "maven_on_path": shutil.which("mvn") is not None,
        "docker_cli_on_path": shutil.which("docker") is not None,
        "psql_on_path": shutil.which("psql") is not None,
        "node_on_path": shutil.which("node") is not None,
        "npm_on_path": shutil.which("npm") is not None,
    }


def run_probe(jar: Path) -> Path:
    output_root = ROOT / ".local" / "rpf-09"
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="probe-", dir=output_root))
    data_dir = run_dir / "database"
    artifact_dir = run_dir / "artifacts"
    data_dir.mkdir()
    artifact_dir.mkdir()
    results: dict[str, Any] = {
        "schema_version": "rpf-09-probe-result-v1",
        "started_at": utc_now(),
        "persistence_candidate": {
            "database": "H2 file mode",
            "framework": "Spring Boot 3.4.5",
            "canonical_metadata_schema": "rpf-09-metadata-schema-v1",
        },
        "toolchain": toolchain_snapshot(),
        "checks": {},
        "errors": [],
    }

    source_files = {
        "run": ROOT / "runtime" / "reviewed-normal-run-v2.json",
        "evaluation": ROOT / "runtime" / "reviewed-evaluation-candidate.json",
        "candidate_decision": ROOT / "runtime" / "reviewed-release-decision-candidate.json",
        "baseline_decision": ROOT / "runtime" / "reviewed-release-decision-baseline.json",
    }
    for path in source_files.values():
        require(path.is_file(), f"Missing reviewed source artifact: {path}")

    run_manifest, run_path, run_content = prepare_artifact(source_files["run"], "RUN", artifact_dir, "run-candidate.json")
    evaluation_manifest, evaluation_path, evaluation_content = prepare_artifact(source_files["evaluation"], "EVALUATION", artifact_dir, "evaluation-candidate.json")
    candidate_manifest, candidate_path, candidate_content = prepare_artifact(source_files["candidate_decision"], "RELEASE_DECISION", artifact_dir, "release-decision-candidate.json")
    baseline_manifest, baseline_path, baseline_content = prepare_artifact(source_files["baseline_decision"], "RELEASE_DECISION", artifact_dir, "release-decision-baseline.json")

    immutable_same = write_immutable(candidate_path, candidate_content)
    overwrite_rejected = False
    try:
        write_immutable(candidate_path, b"different immutable content")
    except ProbeFailure as error:
        overwrite_rejected = "IMMUTABLE_ARTIFACT_OVERWRITE_REJECTED" in str(error)
    require(immutable_same == "IDEMPOTENT_EXISTING" and overwrite_rejected, "Immutable artifact writer contract failed")
    results["checks"]["artifact_immutable_writer"] = "PASS"

    service: RunningService | None = None
    try:
        service = RunningService(jar, data_dir, artifact_dir, run_dir / "control-plane-1.log")
        base_url = service.base_url
        health = expect(request_json(base_url, "GET", "/api/v1/health"), 200)
        require(health["schema_version"] == "rpf-09-metadata-schema-v1", f"Unexpected schema health: {health}")
        results["checks"]["health_readiness"] = health
        boundary = expect(request_json(base_url, "GET", "/api/v1/probe/boundary"), 200)
        require(boundary["transport"] == "SYNCHRONOUS_HTTP_JSON" and not boundary["job_transport_resolved"], f"Boundary drifted: {boundary}")
        results["checks"]["transport_boundary"] = boundary

        ingested_run = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", run_manifest), 201)
        ingested_evaluation = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", evaluation_manifest), 201)
        ingested_candidate = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", candidate_manifest), 201)
        require(ingested_run["status"] == "INGESTED" and ingested_evaluation["status"] == "INGESTED" and ingested_candidate["status"] == "INGESTED", "Initial ingestion did not commit")
        results["checks"]["cross_runtime_ingest"] = {
            "status": "PASS",
            "entities": ["RUN", "EVALUATION", "RELEASE_DECISION"],
            "raw_artifact_in_metadata": False,
        }

        run_id = run_manifest["entity_id"]
        evaluation_id = evaluation_manifest["entity_id"]
        candidate_id = candidate_manifest["entity_id"]
        for path, entity_id in ((f"/api/v1/runs/{run_id}", run_id), (f"/api/v1/evaluations/{evaluation_id}", evaluation_id), (f"/api/v1/release-decisions/{candidate_id}", candidate_id)):
            view = expect(request_json(base_url, "GET", path), 200)
            canonical = view["canonical_metadata"]
            resolved = view["artifact_resolution"]
            require(canonical["entity_id"] == entity_id and resolved["resolved"] is True, f"Stable ref did not resolve: {view}")
            require("raw_artifact" not in view and "payload" not in canonical, f"Raw artifact leaked into metadata view: {view}")
        release_list = expect(request_json(base_url, "GET", "/api/v1/release-decisions"), 200)
        require(len(release_list["items"]) == 1, f"Unexpected release decision list: {release_list}")
        results["checks"]["metadata_query_and_stable_ref"] = "PASS"

        duplicate = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", candidate_manifest), 200)
        require(duplicate["status"] == "IDEMPOTENT_REPLAY" and duplicate["already_exists"] is True, f"Duplicate was not idempotent: {duplicate}")
        results["checks"]["duplicate_ingest"] = duplicate["status"]

        conflict_content = candidate_content + b"\n"
        conflict_key = "release-decision-candidate-conflict.json"
        write_immutable(artifact_dir / conflict_key, conflict_content)
        conflict_manifest = build_manifest("RELEASE_DECISION", conflict_content, conflict_key, "conflict-idempotency-key")
        conflict = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", conflict_manifest), 409, "IDENTITY_CONTENT_CONFLICT")
        results["checks"]["identity_conflict"] = conflict["error"]

        missing_manifest = json.loads(json.dumps(candidate_manifest))
        missing_manifest["artifact_ref"]["artifact_key"] = "missing-at-ingest.json"
        missing = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", missing_manifest), 422, "INVALID_EVIDENCE_ARTIFACT_MISSING")
        results["checks"]["missing_artifact_at_ingest"] = missing["error"]

        unknown_document = json.loads(candidate_content.decode("utf-8"))
        unknown_document["schema_version"] = "rpf-unknown-schema-v99"
        unknown_content = json.dumps(unknown_document, ensure_ascii=False, indent=2).encode("utf-8")
        unknown_key = "release-decision-unknown-schema.json"
        write_immutable(artifact_dir / unknown_key, unknown_content)
        unknown_manifest = build_manifest("RELEASE_DECISION", unknown_content, unknown_key, "unknown-schema-key")
        unknown = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", unknown_manifest), 422, "INVALID_EVIDENCE_UNKNOWN_SCHEMA")
        results["checks"]["unknown_schema"] = unknown["error"]

        rollback = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence?fail_after_write=true", baseline_manifest), 500, "PROBE_TRANSACTION_ROLLED_BACK")
        baseline_id = baseline_manifest["entity_id"]
        after_rollback = expect(request_json(base_url, "GET", f"/api/v1/release-decisions/{baseline_id}"), 404, "CANONICAL_METADATA_NOT_FOUND")
        require(rollback["retriable"] is False and after_rollback["error"] == "CANONICAL_METADATA_NOT_FOUND", "Transaction rollback was not fail-closed")
        normal_baseline = expect(request_json(base_url, "POST", "/api/v1/ingest/completed-evidence", baseline_manifest), 201)
        require(normal_baseline["status"] == "INGESTED", "Baseline could not be committed after rollback")
        results["checks"]["transaction_rollback"] = {"write_response": rollback["error"], "post_rollback_lookup": after_rollback["error"], "recovery_ingest": normal_baseline["status"]}

        original_candidate = candidate_path.read_bytes()
        candidate_path.write_bytes(b'{"corrupt":')
        corrupt = expect(request_json(base_url, "GET", f"/api/v1/release-decisions/{candidate_id}"), 422, "INVALID_EVIDENCE_ARTIFACT_HASH_MISMATCH")
        candidate_path.write_bytes(original_candidate)
        candidate_path.unlink()
        missing_after_commit = expect(request_json(base_url, "GET", f"/api/v1/release-decisions/{candidate_id}"), 422, "INVALID_EVIDENCE_ARTIFACT_MISSING")
        candidate_path.write_bytes(original_candidate)
        restored = expect(request_json(base_url, "GET", f"/api/v1/release-decisions/{candidate_id}"), 200)
        require(restored["artifact_resolution"]["resolved"] is True, "Artifact ref did not recover after fault injection")
        results["checks"]["fail_closed_artifact_faults"] = {
            "corrupt": corrupt["error"],
            "missing_after_commit": missing_after_commit["error"],
            "restored": "PASS",
        }

        service.stop()
        service = None
        try:
            request_json(base_url, "GET", "/api/v1/health")
        except TransportFailure:
            results["checks"]["transport_unavailable_after_stop"] = {"status": "PASS", "classified_as": "RETRIABLE_TRANSPORT_FAILURE"}
        else:
            raise ProbeFailure("Stopped Control Plane still answered HTTP")

        service = RunningService(jar, data_dir, artifact_dir, run_dir / "control-plane-2.log")
        restarted_health = expect(request_json(service.base_url, "GET", "/api/v1/health"), 200)
        require(restarted_health["readiness"] == "READY", f"Restarted service was not ready: {restarted_health}")
        for path in (f"/api/v1/runs/{run_id}", f"/api/v1/evaluations/{evaluation_id}", f"/api/v1/release-decisions/{candidate_id}", f"/api/v1/release-decisions/{baseline_id}"):
            restarted_view = expect(request_json(service.base_url, "GET", path), 200)
            require(restarted_view["artifact_resolution"]["resolved"] is True, f"Restart lost or invalidated stable ref: {path}")
        restarted_list = expect(request_json(service.base_url, "GET", "/api/v1/release-decisions"), 200)
        require(len(restarted_list["items"]) == 2, f"Release Decision history did not survive restart: {restarted_list}")
        results["checks"]["service_restart_persistence"] = {
            "metadata": "PASS",
            "artifact_refs": "PASS",
            "release_decision_history": "PASS",
            "release_decision_count": len(restarted_list["items"]),
        }
        results["checks"]["error_classification"] = {
            "request_validation": ["UNKNOWN_MANIFEST_SCHEMA"],
            "invalid_evidence": ["INVALID_EVIDENCE_ARTIFACT_MISSING", "INVALID_EVIDENCE_ARTIFACT_HASH_MISMATCH", "INVALID_EVIDENCE_UNKNOWN_SCHEMA"],
            "identity_conflict": ["IDENTITY_CONTENT_CONFLICT"],
            "platform_storage": ["PLATFORM_STORAGE_UNAVAILABLE (handler defined; not induced against embedded DB)"],
            "retriable_transport": ["RETRIABLE_TRANSPORT_FAILURE after process stop"],
            "agent_fail_attribution": False,
        }
    finally:
        if service is not None:
            service.stop()

    results["finished_at"] = utc_now()
    results["run_directory"] = str(run_dir.relative_to(ROOT))
    result_path = run_dir / "probe-result.json"
    result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-09 cross-process Control Plane probe.")
    parser.add_argument(
        "--jar",
        type=Path,
        default=ROOT / "spikes" / "rpf-09" / "control-plane" / "target" / "rpf-09-control-plane-probe-0.1.0-SNAPSHOT.jar",
        help="Path to the packaged Spring Boot probe jar.",
    )
    args = parser.parse_args()
    if not args.jar.is_file():
        print(f"Missing jar: {args.jar}. Run mvn -q test package in spikes/rpf-09/control-plane first.", file=sys.stderr)
        return 2
    try:
        result = run_probe(args.jar)
    except Exception as error:
        print(f"RPF-09 probe failed: {error}", file=sys.stderr)
        return 1
    print(f"PASS: RPF-09 cross-process probe; result={result.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
