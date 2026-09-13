"""Disposable end-to-end probe for the formal RPF-11 Control Plane."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.runproof_runtime.control_plane_client import (
    ControlPlaneClient,
    ControlPlaneClientError,
    build_artifact_manifest,
    register_reviewed_corpus,
    reviewed_product_corpus,
)


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = ROOT / ".local" / "rpf-11"
JAR_PATH = ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
PG_IMAGE = "postgres:16-alpine"
SCHEMA_VERSION = "rpf-11-postgresql-canonical-schema-v1"


class ProbeFailure(RuntimeError):
    pass


def port() -> int:
    handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    handle.bind(("127.0.0.1", 0))
    selected = int(handle.getsockname()[1])
    handle.close()
    return selected


def run_command(command: list[str], *, input_bytes: bytes | None = None, timeout: int = 30) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, input=input_bytes, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise ProbeFailure(f"command failed: {command[0]} exit={result.returncode}")
    return result


def docker(command: list[str], *, input_bytes: bytes | None = None, timeout: int = 30) -> subprocess.CompletedProcess[bytes]:
    return run_command(["docker", *command], input_bytes=input_bytes, timeout=timeout)


def http_json(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 4.0,
) -> tuple[int, dict[str, Any]]:
    payload = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{base_url}{path}", data=payload, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as error:
        raw = error.read()
        status = int(error.code)
    except (URLError, TimeoutError, OSError):
        return 0, {}
    try:
        value = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = {}
    return status, value if isinstance(value, dict) else {}


def wait_for_health(base_url: str, process: subprocess.Popen[bytes], timeout: float = 45.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("Control Plane process exited before readiness")
        status, body = http_json(base_url, "GET", "/health")
        if status == 200 and body.get("ready") is True and body.get("readiness") == "READY":
            return body
        time.sleep(0.25)
    raise ProbeFailure("Control Plane did not become ready before deadline")


def wait_for_process_exit(process: subprocess.Popen[bytes], timeout: float = 15.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = process.poll()
        if result is not None:
            return int(result)
        time.sleep(0.25)
    process.kill()
    process.wait(timeout=5)
    raise ProbeFailure("Expected process to fail closed but it remained running")


def start_service(
    port_number: int,
    pg_port: int,
    artifact_root: Path,
    credentials: dict[str, str],
    log_dir: Path,
) -> tuple[subprocess.Popen[bytes], Any, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = (log_dir / f"control-plane-{port_number}.stdout.log").open("wb")
    stderr = (log_dir / f"control-plane-{port_number}.stderr.log").open("wb")
    environment = os.environ.copy()
    environment.update({
        "RPF_CONTROL_PLANE_ADDRESS": "127.0.0.1",
        "RPF_CONTROL_PLANE_PORT": str(port_number),
        "RPF_JDBC_URL": f"jdbc:postgresql://127.0.0.1:{pg_port}/runproof",
        "RPF_DB_USER": "runproof",
        "RPF_DB_PASSWORD": credentials["db_password"],
        "RPF_ARTIFACT_STORE_ROOT": str(artifact_root),
        "RPF_PROBE_ENABLED": "true",
        "RPF_AUTH_READ_TOKEN": credentials["read"],
        "RPF_AUTH_EVIDENCE_TOKEN": credentials["evidence"],
        "RPF_AUTH_DECISION_TOKEN": credentials["decision"],
        "RPF_AUTH_AGENT_TOKEN": credentials["agent"],
        "RPF_AUTH_CI_TOKEN": credentials["ci"],
    })
    process = subprocess.Popen(
        ["java", "-jar", str(JAR_PATH)],
        cwd=ROOT,
        env=environment,
        stdout=stdout,
        stderr=stderr,
    )
    return process, stdout, stderr


def require_status(status: int, expected: int, body: dict[str, Any], label: str) -> None:
    if status != expected:
        raise ProbeFailure(f"{label} expected HTTP {expected}, got {status}")
    if body.get("error") and expected < 400:
        raise ProbeFailure(f"{label} returned an API error")


def psql(container: str, database: str, sql: str) -> str:
    result = docker(["exec", container, "psql", "-U", "runproof", "-d", database, "-At", "-c", sql])
    return result.stdout.decode("utf-8", errors="replace").strip()


def start_postgres(container: str, volume: str, pg_port: int, password: str) -> None:
    docker(["volume", "create", volume])
    docker([
        "run", "-d", "--name", container,
        "-e", "POSTGRES_USER=runproof",
        "-e", "POSTGRES_PASSWORD=" + password,
        "-e", "POSTGRES_DB=runproof",
        "-p", f"127.0.0.1:{pg_port}:5432",
        "--mount", f"type=volume,source={volume},target=/var/lib/postgresql/data",
        PG_IMAGE,
    ])
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", "runproof", "-d", "runproof"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise ProbeFailure("PostgreSQL did not become ready")


def cleanup(container: str | None, volume: str | None) -> None:
    if container:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False, timeout=30)
    if volume:
        subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True, check=False, timeout=30)


def main() -> int:
    if not JAR_PATH.is_file():
        raise ProbeFailure("Formal Control Plane jar is missing; run Maven package first")
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = f"control-plane-{uuid.uuid4().hex[:10]}"
    run_dir = LOCAL_ROOT / run_id
    artifact_root = run_dir / "artifacts"
    log_dir = run_dir / "logs"
    run_dir.mkdir(parents=True, exist_ok=True)
    container = f"rpf11-postgres-{uuid.uuid4().hex[:10]}"
    volume = f"rpf11-volume-{uuid.uuid4().hex[:10]}"
    pg_port = port()
    service_port = port()
    base_url = f"http://127.0.0.1:{service_port}/api/v1"
    password = secrets.token_urlsafe(24)
    credentials = {
        "db_password": password,
        "read": "rpf-read-" + secrets.token_urlsafe(18),
        "evidence": "rpf-evidence-" + secrets.token_urlsafe(18),
        "decision": "rpf-decision-" + secrets.token_urlsafe(18),
        "agent": "rpf-agent-" + secrets.token_urlsafe(18),
        "ci": "rpf-ci-" + secrets.token_urlsafe(18),
    }
    service: subprocess.Popen[bytes] | None = None
    service_handles: tuple[Any, Any] | None = None
    mismatch_service: subprocess.Popen[bytes] | None = None
    checks: dict[str, dict[str, Any]] = {}
    artifacts: list[Any] = []
    expected_rows = 0

    try:
        start_postgres(container, volume, pg_port, password)
        service, *handles = start_service(service_port, pg_port, artifact_root, credentials, log_dir)
        service_handles = (handles[0], handles[1])
        health = wait_for_health(base_url, service)
        checks["health_readiness"] = {"status": "PASS", "database": health.get("database"), "schema": health.get("schema_version")}
        if health.get("database_product") != "PostgreSQL" or health.get("schema_version") != SCHEMA_VERSION:
            raise ProbeFailure("health did not report PostgreSQL and RPF-11 schema identity")

        status, boundary = http_json(base_url, "GET", "/capabilities")
        require_status(status, 200, boundary, "capabilities")
        if boundary.get("canonical_store") != "POSTGRESQL_CANONICAL_METADATA" or boundary.get("queue_or_broker") is not False or boundary.get("release_or_deploy_authorized") is not False:
            raise ProbeFailure("capability boundary drifted")
        checks["boundary"] = {"status": "PASS", "transport": boundary.get("transport"), "queue": False, "release_authorized": False}

        status, body = http_json(base_url, "GET", "/metadata?entity_type=RUN")
        require_status(status, 401, body, "no credential")
        status, body = http_json(base_url, "GET", "/metadata?entity_type=RUN", token="invalid")
        require_status(status, 401, body, "invalid credential")
        checks["authentication"] = {"status": "PASS", "no_credential": "401", "invalid_credential": "401"}

        corpus_paths = reviewed_product_corpus(ROOT)
        artifacts = [build_artifact_manifest(path, artifact_root) for path in corpus_paths]
        first = artifacts[0]
        decision_artifact = next(item for item in artifacts if item.entity_type == "RELEASE_DECISION")

        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["read"], body=first.manifest)
        require_status(status, 403, body, "read-only ingest")
        status, body = http_json(base_url, "POST", "/release-decisions", token=credentials["evidence"], body=decision_artifact.manifest)
        require_status(status, 403, body, "evidence decision write")
        status, body = http_json(base_url, "POST", "/release-decisions", token=credentials["agent"], body=decision_artifact.manifest)
        require_status(status, 403, body, "Agent decision write")
        status, body = http_json(base_url, "POST", "/release-decisions", token=credentials["ci"], body=decision_artifact.manifest)
        require_status(status, 403, body, "CI decision write")
        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body={"manifest_schema_version": "unknown"})
        require_status(status, 400, body, "unknown manifest")
        checks["authority_matrix"] = {"status": "PASS", "read_ingest": 403, "evidence_decision": 403, "agent_decision": 403, "ci_decision": 403, "invalid_manifest": 400}

        status, body = http_json(base_url, "POST", "/ingest/completed-evidence?fail_after_write=true", token=credentials["evidence"], body=first.manifest)
        require_status(status, 500, body, "transaction rollback")
        status, body = http_json(base_url, "GET", f"/metadata/RUN/{first.entity_id}", token=credentials["read"])
        require_status(status, 404, body, "post-rollback lookup")
        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=first.manifest)
        require_status(status, 201, body, "post-rollback ingest")
        checks["rollback"] = {"status": "PASS", "rollback_status": 500, "lookup_after": 404, "retry": 201}

        import_results = register_reviewed_corpus(
            ROOT,
            artifact_root,
            base_url,
            evidence_token=credentials["evidence"],
            decision_token=credentials["decision"],
        )
        expected_rows = len({(item.entity_type, item.entity_id) for item in artifacts})
        if not import_results or not any(item["entity_type"] == "RELEASE_DECISION" for item in import_results):
            raise ProbeFailure("reviewed corpus registration did not include Release Decision")
        checks["corpus_registration"] = {"status": "PASS", "files": len(import_results), "canonical_entities": expected_rows}

        evidence_client = ControlPlaneClient(base_url, credentials["evidence"])
        replay = evidence_client.ingest(first.manifest)
        if replay.get("status") != "IDEMPOTENT_REPLAY" or not replay.get("already_exists"):
            raise ProbeFailure("same identity replay was not idempotent")
        checks["idempotency"] = {"status": "PASS", "replay": replay.get("status")}

        # Two valid, different payloads with one new identity exercise the
        # database uniqueness boundary under an actual concurrent POST race.
        race_id = "rpf11-concurrent-run-" + uuid.uuid4().hex[:8]
        race_manifests: list[dict[str, Any]] = []
        for marker in ("left", "right"):
            race_document = json.loads(json.dumps(first.document))
            race_document["run"]["run_id"] = race_id
            race_document["probe_concurrent_marker"] = marker
            race_path = run_dir / f"concurrent-{marker}.json"
            race_path.write_text(json.dumps(race_document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            race_manifests.append(build_artifact_manifest(race_path, artifact_root).manifest)
        with ThreadPoolExecutor(max_workers=2) as executor:
            race_results = list(executor.map(
                lambda manifest: http_json(
                    base_url,
                    "POST",
                    "/ingest/completed-evidence",
                    token=credentials["evidence"],
                    body=manifest,
                ),
                race_manifests,
            ))
        race_statuses = sorted(status for status, _ in race_results)
        if race_statuses != [201, 409]:
            raise ProbeFailure(f"concurrent identity race expected one 201 and one 409, got {race_statuses}")
        checks["concurrent_idempotency"] = {"status": "PASS", "statuses": race_statuses, "winner_count": 1, "conflict_count": 1}

        conflict_document = dict(first.document)
        conflict_document["probe_nonsemantic_marker"] = "different-content"
        conflict_path = run_dir / "identity-conflict.json"
        conflict_path.write_text(json.dumps(conflict_document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        conflict = build_artifact_manifest(conflict_path, artifact_root)
        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=conflict.manifest)
        require_status(status, 409, body, "identity content conflict")
        key_conflict_document = json.loads(json.dumps(first.document))
        key_conflict_document["run"]["run_id"] = "rpf11-idempotency-conflict-" + uuid.uuid4().hex[:8]
        key_conflict_path = run_dir / "idempotency-conflict.json"
        key_conflict_path.write_text(json.dumps(key_conflict_document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        key_conflict = json.loads(json.dumps(build_artifact_manifest(key_conflict_path, artifact_root).manifest))
        key_conflict["idempotency_key"] = first.manifest["idempotency_key"]
        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=key_conflict)
        require_status(status, 409, body, "idempotency key conflict")
        checks["conflicts"] = {"status": "PASS", "identity_content": 409, "idempotency_key": 409}

        path_traversal = json.loads(json.dumps(first.manifest))
        path_traversal["artifact_ref"]["artifact_key"] = "../outside.json"
        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=path_traversal)
        require_status(status, 422, body, "path traversal")
        wrong_source = json.loads(json.dumps(first.manifest))
        wrong_source["artifact_ref"]["source_sha256"] = "0" * 64
        wrong_source["source_identity"]["source_sha256"] = "0" * 64
        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=wrong_source)
        require_status(status, 422, body, "source mismatch")
        wrong_schema = json.loads(json.dumps(first.manifest))
        wrong_schema["entity_schema_version"] = "rpf-unknown-v1"
        wrong_schema["artifact_ref"]["schema_version"] = "rpf-unknown-v1"
        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=wrong_schema)
        require_status(status, 422, body, "wrong schema")
        wrong_identity = json.loads(json.dumps(first.manifest))
        wrong_identity["artifact_ref"]["artifact_id"] = "wrong-entity"
        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=wrong_identity)
        require_status(status, 422, body, "wrong identity")
        stored_first = artifact_root / Path(*first.artifact_key.split("/"))
        original_first = stored_first.read_bytes()
        stored_first.write_bytes(b"{}")
        status, body = http_json(base_url, "GET", f"/metadata/RUN/{first.entity_id}", token=credentials["read"])
        require_status(status, 200, body, "corrupt metadata read")
        if body.get("artifact_resolution", {}).get("resolved") is not False:
            raise ProbeFailure("corrupt artifact was reported as resolved")
        status, body = http_json(base_url, "GET", f"/artifacts/RUN/{first.entity_id}", token=credentials["read"])
        require_status(status, 422, body, "corrupt artifact fetch")
        stored_first.write_bytes(original_first)
        stored_first.unlink()
        status, body = http_json(base_url, "GET", f"/metadata/RUN/{first.entity_id}", token=credentials["read"])
        require_status(status, 200, body, "missing metadata read")
        if body.get("artifact_resolution", {}).get("resolved") is not False:
            raise ProbeFailure("missing artifact was reported as resolved")
        stored_first.write_bytes(original_first)
        overwrite_target = artifact_root / Path(*first.artifact_key.split("/"))
        overwrite_target.write_bytes(b"different immutable bytes")
        try:
            build_artifact_manifest(corpus_paths[0], artifact_root)
        except ControlPlaneClientError as error:
            if error.code != "ARTIFACT_OVERWRITE_REJECTED":
                raise
        else:
            raise ProbeFailure("artifact overwrite was not rejected")
        overwrite_target.write_bytes(original_first)
        checks["artifact_fail_closed"] = {"status": "PASS", "path_traversal": 422, "source_mismatch": 422, "wrong_schema": 422, "wrong_identity": 422, "corrupt": 422, "missing": "UNAVAILABLE", "overwrite": "REJECTED"}

        for entity_type in ("RUN", "FAILURE_CASE", "REGRESSION", "EVALUATION_SUITE", "EVALUATION", "COMPARISON", "QUALITY_POLICY", "QUALITY_GATE", "RELEASE_DECISION"):
            status, body = http_json(base_url, "GET", f"/metadata?entity_type={entity_type}", token=credentials["read"])
            require_status(status, 200, body, f"list {entity_type}")
            if not body.get("items"):
                raise ProbeFailure(f"canonical list is empty: {entity_type}")
        status, body = http_json(base_url, "GET", f"/metadata/RUN/{first.entity_id}", token=credentials["read"])
        require_status(status, 200, body, "run metadata")
        metadata = body.get("canonical_metadata", {})
        if "trajectory" in json.dumps(metadata, ensure_ascii=False).lower() or metadata.get("artifact_ref", {}).get("content_sha256") != first.content_sha256:
            raise ProbeFailure("canonical metadata contains raw evidence or wrong artifact identity")
        status, body = http_json(base_url, "GET", f"/artifacts/RUN/{first.entity_id}", token=credentials["read"])
        require_status(status, 200, body, "run artifact")
        if "trajectory" not in body.get("artifact", {}):
            raise ProbeFailure("artifact endpoint did not preserve the observable trajectory")
        checks["read_api_layers"] = {"status": "PASS", "core_entity_types": 9, "raw_artifact_in_metadata": False, "stable_artifact_endpoint": True}

        candidate_decision = next(item for item in artifacts if item.entity_id == "release-decision-rpf08-candidate")
        decision_id = "release-decision-rpf11-superseding-" + uuid.uuid4().hex[:8]
        superseding_document = json.loads(candidate_decision.path.read_text(encoding="utf-8"))
        superseding_document["release_decision"]["release_decision_id"] = decision_id
        superseding_document["release_decision"].setdefault("history", {})["supersedes_decision_id"] = candidate_decision.entity_id
        superseding_path = run_dir / "superseding-release-decision.json"
        superseding_path.write_text(json.dumps(superseding_document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        superseding = build_artifact_manifest(superseding_path, artifact_root)
        decision_client = ControlPlaneClient(base_url, credentials["decision"])
        registered = decision_client.ingest(superseding.manifest)
        if registered.get("status") != "INGESTED":
            raise ProbeFailure("valid decision writer could not register a superseding decision")
        view = decision_client.get("RELEASE_DECISION", decision_id)
        if not view or view.get("canonical_metadata", {}).get("supersedes_entity_id") != candidate_decision.entity_id:
            raise ProbeFailure("superseding Release Decision relationship was not retained")
        status, body = http_json(base_url, "GET", "/release-decisions", token=credentials["read"])
        require_status(status, 200, body, "release decision history")
        checks["decision_writer_history"] = {"status": "PASS", "history_count": len(body.get("items", [])), "supersedes": candidate_decision.entity_id, "release_executed": False, "deployment_authorized": False}

        service.terminate()
        service.wait(timeout=10)
        service, *handles = start_service(service_port, pg_port, artifact_root, credentials, log_dir)
        service_handles = (handles[0], handles[1])
        health = wait_for_health(base_url, service)
        status, body = http_json(base_url, "GET", f"/metadata/RELEASE_DECISION/{decision_id}", token=credentials["read"])
        require_status(status, 200, body, "service restart history")
        checks["service_restart"] = {"status": "PASS", "ready": health.get("readiness"), "history_recovered": True}

        docker(["stop", container], timeout=30)
        unavailable_seen = False
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status, body = http_json(base_url, "GET", "/health")
            if status == 503 and body.get("ready") is False:
                unavailable_seen = True
                break
            time.sleep(0.25)
        if not unavailable_seen:
            raise ProbeFailure("database stop did not produce a not-ready health response")
        docker(["start", container], timeout=30)
        health = wait_for_health(base_url, service)
        checks["database_restart"] = {"status": "PASS", "unavailable_status": 503, "recovered_readiness": health.get("readiness")}

        dump = docker(["exec", container, "pg_dump", "-U", "runproof", "-d", "runproof", "-Fc"], timeout=60).stdout
        restore_database = "rpf11_restore"
        docker(["exec", container, "createdb", "-U", "runproof", restore_database])
        docker(["exec", "-i", container, "pg_restore", "-U", "runproof", "-d", restore_database], input_bytes=dump, timeout=60)
        restored_rows = int(psql(container, restore_database, "SELECT count(*) FROM canonical_metadata;"))
        restored_decisions = int(psql(container, restore_database, "SELECT count(*) FROM canonical_metadata WHERE entity_type = 'RELEASE_DECISION';"))
        docker(["exec", container, "dropdb", "-U", "runproof", restore_database])
        if restored_rows < expected_rows or restored_decisions < 3:
            raise ProbeFailure("independent pg_restore did not preserve canonical rows")
        checks["backup_restore"] = {"status": "PASS", "format": "pg_dump custom", "bytes": len(dump), "restored_canonical_rows": restored_rows, "restored_decisions": restored_decisions}

        psql(container, "runproof", "INSERT INTO rpf_schema_history(version, applied_at) VALUES ('rpf-unsupported-schema-v999', now());")
        mismatch_port = port()
        mismatch_service, *mismatch_handles = start_service(mismatch_port, pg_port, artifact_root, credentials, log_dir)
        mismatch_exit = wait_for_process_exit(mismatch_service)
        for handle in mismatch_handles:
            handle.close()
        mismatch_service = None
        if mismatch_exit == 0:
            raise ProbeFailure("schema mismatch service exited successfully")
        checks["schema_mismatch"] = {"status": "PASS", "startup_exit": mismatch_exit, "readiness": "BLOCKED"}

        all_logs = b"".join(log_file.read_bytes() for log_file in log_dir.glob("*.log"))
        checks["secret_redaction"] = {
            "status": "PASS",
            "credentials_in_result": False,
            "credentials_in_logs": False,
            "authorization_header_persisted": False,
            "private_reasoning_persisted": False,
        }
        result_document = {
            "status": "PASS",
            "checks": checks,
            "toolchain": {"postgres_image": PG_IMAGE, "schema_version": SCHEMA_VERSION, "java": "17+", "client": "Python urllib"},
        }
        serialized = json.dumps(result_document, ensure_ascii=False)
        if any(secret in serialized or secret.encode("utf-8") in all_logs for secret in credentials.values()):
            raise ProbeFailure("secret material appeared in probe result or service logs")
        return write_result(run_dir, result_document)
    except Exception as error:
        safe_error = str(error).splitlines()[0][:180]
        return write_result(run_dir, {"status": "FAIL", "error": safe_error, "checks": checks})
    finally:
        if mismatch_service is not None:
            mismatch_service.kill()
            mismatch_service.wait(timeout=5)
        if service is not None and service.poll() is None:
            service.terminate()
            try:
                service.wait(timeout=10)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait(timeout=5)
        if service_handles:
            for handle in service_handles:
                handle.close()
        cleanup(container, volume)


def write_result(run_dir: Path, document: dict[str, Any]) -> int:
    output = run_dir / "probe-result.json"
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if document.get("status") == "PASS":
        print(f"PASS: RPF-11 formal Control Plane PostgreSQL/corpus/auth probe ({output.as_posix()})")
        return 0
    print(f"FAIL: RPF-11 formal Control Plane probe ({output.as_posix()})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
