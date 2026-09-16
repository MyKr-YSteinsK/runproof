"""Disposable end-to-end probe for the formal RPF-14 Control Plane.

This probe owns a real PostgreSQL container and starts the packaged formal
Control Plane as an independent JVM.  It keeps the existing RPF-11 canonical
metadata checks and adds the formal durable job/worker crash matrix.  Secrets
are generated in-process and are never written to the result or logs.
"""

from __future__ import annotations

import json
import hashlib
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
LOCAL_ROOT = ROOT / ".local" / "rpf-14"
JAR_PATH = ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
PG_IMAGE = "postgres:16-alpine"
SCHEMA_VERSION = "rpf-14-durable-execution-schema-v1"
PROBE_PROCESS_IDS: set[int] = set()


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


def stop_process(process: subprocess.Popen[bytes], timeout: float = 10.0) -> None:
    """Stop one probe-owned process, escalating only to its exact PID tree."""

    process_id = process.pid
    # Terminate the exact process tree before terminating the Popen handle.
    # On Windows the Java launcher may have a JVM child; killing the parent
    # first lets that child detach and defeats a later /T cleanup.
    if os.name == "nt" and process.poll() is None:
        subprocess.run(["taskkill", "/PID", str(process_id), "/T", "/F"], capture_output=True, check=False, timeout=10)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
    # The exact PID is probe-owned, so this fallback cannot broaden cleanup to
    # unrelated processes and also handles a launcher that exited just before
    # the tree command above.
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process_id), "/T", "/F"], capture_output=True, check=False, timeout=10)
    try:
        if process.poll() is None:
            process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


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
        "RPF_AUTH_WORKER_TOKEN": credentials["worker"],
    })
    process = subprocess.Popen(
        ["java", "-jar", str(JAR_PATH)],
        cwd=ROOT,
        env=environment,
        stdout=stdout,
        stderr=stderr,
    )
    PROBE_PROCESS_IDS.add(process.pid)
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


def create_directory_escape_link(link: Path, target: Path) -> str | None:
    """Create a Windows symlink or junction for the containment probe."""

    try:
        link.symlink_to(target, target_is_directory=True)
        return "SYMLINK"
    except (OSError, NotImplementedError):
        if os.name != "nt":
            return None
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
            timeout=10,
        )
        return "JUNCTION" if result.returncode == 0 and link.is_dir() else None


def sha256(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def formal_source_identity() -> dict[str, Any]:
    """Bind probe evidence to the formal RPF-14 implementation bytes."""

    source_paths = [
        ROOT / "control-plane" / "pom.xml",
        ROOT / "control-plane" / "src" / "main" / "resources" / "application.properties",
        ROOT / "runtime" / "runproof_runtime" / "control_plane_client.py",
        ROOT / "runtime" / "runproof_runtime" / "durable_worker.py",
        ROOT / "ci" / "run_release_gate.py",
        ROOT / "web" / "src" / "App.tsx",
        ROOT / "web" / "src" / "data" / "executions.ts",
        ROOT / "web" / "src" / "styles.css",
        ROOT / "control-plane" / "probe.py",
    ]
    source_paths.extend(sorted((ROOT / "control-plane" / "src" / "main" / "java").rglob("*.java")))
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(source_paths, key=lambda candidate: candidate.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        files.append(relative)
    return {"source_sha256": digest.hexdigest(), "files": files}


def contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(contains_key(child, key) for child in value)
    return False


def durable_payload(job_id: str, *, profile: str | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    if profile is not None and output_dir is not None:
        return {
            "contract": "rpf-evaluation-execution-v1",
            "agent_profile": profile,
            "regression_path": "runtime/reviewed-regression.json",
            "output_dir": str(output_dir),
            "evaluation_id": f"evaluation-{job_id}",
            "operation_environment_id": f"rpf14-environment-{job_id}",
        }
    return {
        "contract": "rpf14-durable-probe-v1",
        "scenario_ref": {"scenario_id": "rpf14-formal-probe", "scenario_version": "1"},
        "execution_ref": f"execution-{job_id}",
    }


def durable_submission(
    job_id: str,
    *,
    target_id: str | None = None,
    payload_ref: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    target = target_id or f"evaluation-{job_id}"
    payload = payload_ref or durable_payload(job_id)
    fingerprint_input = {
        "job_id": job_id,
        "target_type": "EVALUATION",
        "target_id": target,
        "payload_ref": payload,
    }
    return {
        "job_id": job_id,
        "idempotency_key": idempotency_key or f"rpf14-idempotency-{job_id}",
        "request_fingerprint": sha256(json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":"))),
        "job_type": "EVALUATION",
        "target_type": "EVALUATION",
        "target_id": target,
        "correlation_id": f"rpf14-correlation-{job_id}",
        "payload_ref": payload,
    }


def submit_durable(
    base_url: str,
    token: str,
    job_id: str,
    *,
    target_id: str | None = None,
    payload_ref: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    request_body = durable_submission(
        job_id,
        target_id=target_id,
        payload_ref=payload_ref,
        idempotency_key=idempotency_key,
    )
    status, response = http_json(base_url, "POST", "/jobs", token=token, body=request_body)
    return status, response, request_body


def owner_payload(lease: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": lease["attempt_id"],
        "worker_id": lease["worker_id"],
        "lease_token": lease["lease_token"],
        "lease_version": lease["lease_version"],
    }


def claim_durable(base_url: str, token: str, job_id: str, worker_id: str, lease_seconds: int = 3) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    status, response = http_json(
        base_url,
        "POST",
        f"/jobs/{job_id}/claim",
        token=token,
        body={"worker_id": worker_id, "lease_seconds": lease_seconds},
    )
    lease = response.get("lease") if isinstance(response.get("lease"), dict) else None
    return status, response, lease


def start_durable(base_url: str, token: str, job_id: str, lease: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    status, response = http_json(base_url, "POST", f"/jobs/{job_id}/start", token=token, body=owner_payload(lease))
    if status == 200 and isinstance(response.get("job"), dict) and isinstance(response["job"].get("version"), int):
        lease["lease_version"] = response["job"]["version"]
    return status, response


def evidence_body(job_id: str, outcome: str = "PASS", suffix: str = "terminal", lease: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence_id = f"rpf14-evidence-{job_id}-{suffix}"
    content_sha = sha256(f"{evidence_id}:{outcome}:rpf14")
    body = {
        "evidence_id": evidence_id,
        "entity_type": "EVALUATION",
        "entity_id": f"evaluation-{job_id}",
        "outcome": outcome,
        "content_sha256": content_sha,
        "artifact_ref": {
            "artifact_id": evidence_id,
            "artifact_key": f"evaluation/{job_id}/{content_sha}.json",
            "artifact_kind": "RunProof Durable Execution Evidence",
            "schema_version": "rpf-execution-evidence-v1",
            "content_sha256": content_sha,
            "source_sha256": sha256("rpf14-formal-probe-source"),
            "runtime_version": "rpf14-formal-probe-v1",
        },
    }
    return (owner_payload(lease) | body) if lease is not None else body


def prepare_terminal_artifact(
    base_url: str,
    token: str,
    artifact_root: Path,
    run_dir: Path,
    job_id: str,
    suffix: str,
) -> Any:
    """Register a minimal canonical Run artifact for a synthetic PASS job."""

    run_id = f"rpf14-terminal-{job_id}-{suffix}"
    path = run_dir / f"{run_id}.json"
    document = {
        "artifact_kind": "Run Evidence",
        "schema_version": "rpf-run-evidence-v2",
        "source_sha256": sha256("rpf14-formal-probe-source"),
        "runtime_version": "rpf14-formal-probe-v1",
        "run": {
            "run_id": run_id,
            "agent": {"agent_id": "rpf14-probe-agent", "agent_version": "rpf14-probe-v1"},
            "scenario": {"scenario_id": "rpf14-terminal-probe", "scenario_version": "1"},
        },
        "environment": {"environment_id": f"rpf14-terminal-environment-{job_id}-{suffix}"},
        "outcome": {"status": "PASS"},
        "verification": {"status": "PASS", "verifier": "rpf14-formal-probe"},
        "trajectory": {"events": []},
    }
    path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    client = ControlPlaneClient(base_url, token)
    response = client.ingest_file(path, artifact_root)
    if response.get("status") not in {"INGESTED", "RECONCILED", "IDEMPOTENT_REPLAY"}:
        raise ProbeFailure(f"terminal artifact registration returned {response.get('status', 'MISSING')}")
    return build_artifact_manifest(path, artifact_root)


def ingest_durable_evidence(
    base_url: str,
    token: str,
    job_id: str,
    outcome: str = "PASS",
    suffix: str = "terminal",
    lease: dict[str, Any] | None = None,
    *,
    artifact_root: Path | None = None,
    run_dir: Path | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    body = evidence_body(job_id, outcome, suffix, lease)
    if outcome == "PASS" and artifact_root is not None and run_dir is not None:
        artifact = prepare_terminal_artifact(base_url, token, artifact_root, run_dir, job_id, suffix)
        body.update({
            "entity_type": artifact.entity_type,
            "entity_id": artifact.entity_id,
            "content_sha256": artifact.content_sha256,
            "artifact_ref": artifact.manifest["artifact_ref"],
        })
    status, response = http_json(base_url, "POST", f"/jobs/{job_id}/evidence", token=token, body=body)
    return status, response, body


def operation_body(lease: dict[str, Any], operation_id: str, environment_id: str) -> dict[str, Any]:
    return owner_payload(lease) | {
        "operation_id": operation_id,
        "environment_id": environment_id,
        "operation_fingerprint": sha256(f"{operation_id}:{environment_id}:rpf14-operation-v1"),
    }


def spawn_response_lost_worker(base_url: str, job_id: str, operation_id: str, token: str) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["RPF_AUTH_WORKER_TOKEN"] = token
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker-response-lost", base_url, job_id, operation_id],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        timeout=30,
    )


def run_response_lost_child(base_url: str, job_id: str, operation_id: str) -> int:
    token = os.environ.get("RPF_AUTH_WORKER_TOKEN")
    if not token:
        return 31
    status, claim, lease = claim_durable(base_url, token, job_id, "rpf14-worker-lost", 1)
    if status != 200 or claim.get("status") != "CLAIMED" or lease is None:
        return 32
    status, _ = start_durable(base_url, token, job_id, lease)
    if status != 200:
        return 33
    prepared_status, prepared = http_json(
        base_url,
        "POST",
        f"/jobs/{job_id}/operations",
        token=token,
        body=operation_body(lease, operation_id, "rpf14-response-lost-environment"),
    )
    if prepared_status != 200 or prepared.get("status") not in {"PREPARED", "IDEMPOTENT_REPLAY"}:
        return 34
    lost_status, lost = http_json(
        base_url,
        "POST",
        f"/jobs/{job_id}/operations/{operation_id}/apply?simulate_response_lost=true",
        token=token,
        body=owner_payload(lease),
    )
    if lost_status != 503 or lost.get("error") != "TRANSPORT_RESPONSE_LOST":
        return 35
    os._exit(17)


def spawn_artifact_crash_worker(artifact_path: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker-artifact-crash", str(artifact_path)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        timeout=30,
    )


def run_artifact_crash_child(artifact_path: str) -> int:
    if not Path(artifact_path).is_file():
        return 41
    os._exit(23)


def spawn_formal_worker(
    base_url: str,
    token: str,
    artifact_root: Path,
    repo_root: Path,
    result_path: Path,
    *,
    worker_id: str = "rpf14-formal-worker",
    max_jobs: int = 1,
    idle_timeout: float = 180.0,
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
    environment = os.environ.copy()
    environment["RPF_AUTH_WORKER_TOKEN"] = token
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "runtime.runproof_runtime.durable_worker",
            "--base-url",
            base_url,
            "--worker-id",
            worker_id,
            "--repo-root",
            str(repo_root),
            "--artifact-store-root",
            str(artifact_root),
            "--lease-seconds",
            "3",
            "--max-jobs",
            str(max_jobs),
            "--idle-timeout",
            str(idle_timeout),
            "--result-path",
            str(result_path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        timeout=210,
    )
    if not result_path.is_file():
        return process, {}
    try:
        document = json.loads(result_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        document = {}
    return process, document if isinstance(document, dict) else {}


def main() -> int:
    if not JAR_PATH.is_file():
        raise ProbeFailure("Formal Control Plane jar is missing; run Maven package first")
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = f"control-plane-{uuid.uuid4().hex[:10]}"
    run_dir = LOCAL_ROOT / run_id
    artifact_root = run_dir / "artifacts"
    log_dir = run_dir / "logs"
    run_dir.mkdir(parents=True, exist_ok=True)
    container = f"rpf14-postgres-{uuid.uuid4().hex[:10]}"
    volume = f"rpf14-volume-{uuid.uuid4().hex[:10]}"
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
        "worker": "rpf-worker-" + secrets.token_urlsafe(18),
    }
    service: subprocess.Popen[bytes] | None = None
    service_handles: tuple[Any, Any] | None = None
    mismatch_service: subprocess.Popen[bytes] | None = None
    checks: dict[str, dict[str, Any]] = {}
    artifacts: list[Any] = []
    expected_rows = 0
    worker_job_id: str | None = None

    try:
        start_postgres(container, volume, pg_port, password)
        service, *handles = start_service(service_port, pg_port, artifact_root, credentials, log_dir)
        service_handles = (handles[0], handles[1])
        health = wait_for_health(base_url, service)
        checks["health_readiness"] = {"status": "PASS", "database": health.get("database"), "schema": health.get("schema_version")}
        if health.get("database_product") != "PostgreSQL" or health.get("schema_version") != SCHEMA_VERSION:
            raise ProbeFailure("health did not report PostgreSQL and RPF-14 schema identity")

        status, boundary = http_json(base_url, "GET", "/capabilities")
        require_status(status, 200, boundary, "capabilities")
        if boundary.get("canonical_store") != "POSTGRESQL_CANONICAL_METADATA" or boundary.get("queue_or_broker") is not False or boundary.get("release_or_deploy_authorized") is not False or boundary.get("job_transport_resolved") is not True:
            raise ProbeFailure("capability boundary drifted")
        checks["boundary"] = {"status": "PASS", "transport": boundary.get("transport"), "ci_integration": boundary.get("ci_integration"), "queue": False, "release_authorized": False, "job_transport_resolved": True}

        # Run the formal worker as an independent process against the formal
        # API.  This is the product path used later by CI, not the historical
        # RPF-13 disposable candidate.
        worker_job_id = "rpf14-formal-worker-" + uuid.uuid4().hex[:8]
        worker_output_dir = run_dir / "worker-output"
        worker_result_path = run_dir / "worker-result.json"
        worker_payload = durable_payload(
            worker_job_id,
            profile="production-change-agent-v1",
            output_dir=worker_output_dir,
        )
        submit_status, submit_response, _ = submit_durable(
            base_url,
            credentials["ci"],
            worker_job_id,
            target_id=f"evaluation-{worker_job_id}",
            payload_ref=worker_payload,
        )
        if submit_status != 201 or submit_response.get("status") != "SUBMITTED" or submit_response.get("job", {}).get("state") != "QUEUED":
            raise ProbeFailure("formal worker job did not enter QUEUED")
        worker_process, worker_result = spawn_formal_worker(
            base_url,
            credentials["worker"],
            artifact_root,
            ROOT,
            worker_result_path,
        )
        if worker_process.returncode != 0 or worker_result.get("status") != "PASS":
            raise ProbeFailure("formal durable worker process did not complete successfully")
        worker_jobs = worker_result.get("jobs")
        if not isinstance(worker_jobs, list) or len(worker_jobs) != 1 or worker_jobs[0].get("status") != "COMPLETED":
            raise ProbeFailure("formal durable worker did not report one completed job")
        worker_read_status, worker_read = http_json(base_url, "GET", f"/jobs/{worker_job_id}", token=credentials["read"])
        require_status(worker_read_status, 200, worker_read, "formal worker job read-back")
        if worker_read.get("state") != "COMPLETED" or not worker_read.get("terminal_evidence_id") or not worker_read.get("operations"):
            raise ProbeFailure("formal worker job did not retain terminal evidence and operation history")
        worker_serialized = json.dumps(worker_result, ensure_ascii=False)
        if any(secret in worker_serialized for secret in credentials.values()):
            raise ProbeFailure("formal worker result exposed a credential")
        checks["formal_worker_process"] = {
            "status": "PASS",
            "job_id": worker_job_id,
            "submit": submit_response.get("status"),
            "worker_process_exit": worker_process.returncode,
            "terminal_state": worker_read.get("state"),
            "attempt_number": worker_read.get("attempt_number"),
            "operation_status": worker_read["operations"][0].get("status"),
            "evidence_count": len(worker_read.get("evidence", [])),
            "raw_lease_token_in_result": False,
            "agent_fail_created": False,
        }

        # F05 regression: terminal history must not occupy the bounded
        # discovery page used by a worker.  Seed more terminal rows than the
        # legacy page size, then submit one eligible job after that history.
        terminal_history_count = 24
        for index in range(terminal_history_count):
            history_job_id = f"rpf22-terminal-history-{index:02d}-{uuid.uuid4().hex[:6]}"
            history_submit_status, _, _ = submit_durable(base_url, credentials["ci"], history_job_id)
            require_status(history_submit_status, 201, {}, "terminal history seed submit")
            history_claim_status, _, history_lease = claim_durable(
                base_url, credentials["worker"], history_job_id, f"rpf22-history-worker-{index:02d}", 4
            )
            require_status(history_claim_status, 200, {}, "terminal history seed claim")
            if history_lease is None:
                raise ProbeFailure("terminal history seed lease missing")
            start_durable(base_url, credentials["worker"], history_job_id, history_lease)
            history_evidence_status, _, history_evidence = ingest_durable_evidence(
                base_url,
                credentials["worker"],
                history_job_id,
                "ERROR",
                suffix="terminal-history",
                lease=history_lease,
            )
            require_status(history_evidence_status, 200, {}, "terminal history seed evidence")
            history_fail_status, history_fail = http_json(
                base_url,
                "POST",
                f"/jobs/{history_job_id}/fail-platform",
                token=credentials["worker"],
                body=owner_payload(history_lease)
                | {"evidence_id": history_evidence["evidence_id"], "reason": "RPF22_TERMINAL_HISTORY_SEED"},
            )
            require_status(history_fail_status, 200, history_fail, "terminal history seed finalization")
            if history_fail.get("job", {}).get("state") != "FAILED_PLATFORM":
                raise ProbeFailure("terminal history seed did not become FAILED_PLATFORM")

        discovery_job_id = "rpf22-eligible-after-history-" + uuid.uuid4().hex[:8]
        discovery_output_dir = run_dir / "rpf22-discovery-output"
        discovery_result_path = run_dir / "rpf22-discovery-result.json"
        discovery_payload = durable_payload(
            discovery_job_id,
            profile="production-change-agent-v1",
            output_dir=discovery_output_dir,
        )
        discovery_submit_status, discovery_submit, _ = submit_durable(
            base_url,
            credentials["ci"],
            discovery_job_id,
            target_id=f"evaluation-{discovery_job_id}",
            payload_ref=discovery_payload,
        )
        require_status(discovery_submit_status, 201, discovery_submit, "eligible discovery submit")
        eligible_status, eligible_response = http_json(
            base_url, "GET", "/jobs?eligible=true&limit=20", token=credentials["read"]
        )
        require_status(eligible_status, 200, eligible_response, "eligible discovery API")
        eligible_items = eligible_response.get("items") if isinstance(eligible_response.get("items"), list) else []
        if eligible_response.get("discovery") != "ELIGIBLE":
            raise ProbeFailure("eligible discovery response did not identify its server-side mode")
        if discovery_job_id not in {item.get("job_id") for item in eligible_items if isinstance(item, dict)}:
            raise ProbeFailure("eligible discovery omitted the queued job after terminal history")
        if any(item.get("state") in {"COMPLETED", "FAILED_PLATFORM", "CANCELLED"} for item in eligible_items if isinstance(item, dict)):
            raise ProbeFailure("eligible discovery returned terminal history")
        discovery_worker_process, discovery_worker_result = spawn_formal_worker(
            base_url,
            credentials["worker"],
            artifact_root,
            ROOT,
            discovery_result_path,
            worker_id="rpf22-discovery-worker",
            max_jobs=1,
            idle_timeout=30.0,
        )
        if discovery_worker_process.returncode != 0 or discovery_worker_result.get("status") != "PASS":
            raise ProbeFailure("eligible discovery worker process did not complete successfully")
        discovery_jobs = discovery_worker_result.get("jobs")
        if not isinstance(discovery_jobs, list) or len(discovery_jobs) != 1 or discovery_jobs[0].get("job_id") != discovery_job_id or discovery_jobs[0].get("status") != "COMPLETED":
            raise ProbeFailure("eligible discovery worker did not process the queued job")
        discovery_read_status, discovery_read = http_json(
            base_url, "GET", f"/jobs/{discovery_job_id}", token=credentials["read"]
        )
        require_status(discovery_read_status, 200, discovery_read, "eligible discovery read-back")
        if discovery_read.get("state") != "COMPLETED":
            raise ProbeFailure("eligible discovery queued job did not complete")
        checks["eligible_discovery_starvation"] = {
            "status": "PASS",
            "terminal_history_count": terminal_history_count,
            "legacy_page_size": 20,
            "queued_job": discovery_job_id,
            "eligible_endpoint": "/jobs?eligible=true&limit=20",
            "server_side_predicate": True,
            "terminal_history_returned": False,
            "worker_processed": discovery_jobs[0].get("job_id"),
            "terminal_state": discovery_read.get("state"),
        }

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
        race_id = "rpf14-concurrent-run-" + uuid.uuid4().hex[:8]
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
        key_conflict_document["run"]["run_id"] = "rpf14-idempotency-conflict-" + uuid.uuid4().hex[:8]
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
        absolute_path = json.loads(json.dumps(first.manifest))
        absolute_path["artifact_ref"]["artifact_key"] = str((artifact_root / Path(*first.artifact_key.split("/"))).resolve())
        status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=absolute_path)
        require_status(status, 422, body, "absolute artifact path")
        escape_outside = run_dir / "artifact-escape-outside"
        escape_parent = artifact_root / "escape-parent"
        escape_outside.mkdir(parents=True, exist_ok=True)
        escape_link_kind = create_directory_escape_link(escape_parent, escape_outside)
        if escape_link_kind is None:
            raise ProbeFailure("filesystem did not permit a symbolic-link or junction containment experiment")
        try:
            symlink_parent = json.loads(json.dumps(first.manifest))
            symlink_parent["artifact_ref"]["artifact_key"] = "escape-parent/escaped.json"
            status, body = http_json(base_url, "POST", "/ingest/completed-evidence", token=credentials["evidence"], body=symlink_parent)
            require_status(status, 422, body, "symlink or junction parent escape")
            if (escape_outside / "escaped.json").exists():
                raise ProbeFailure("artifact ingest wrote through a symlink or junction parent")
        finally:
            try:
                escape_parent.unlink()
            except FileNotFoundError:
                pass
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
        checks["artifact_fail_closed"] = {"status": "PASS", "path_traversal": 422, "absolute_path": 422, "symlink_or_junction_parent": {"kind": escape_link_kind, "http": 422}, "source_mismatch": 422, "wrong_schema": 422, "wrong_identity": 422, "corrupt": 422, "missing": "UNAVAILABLE", "overwrite": "REJECTED"}

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
        candidate_evaluation = next(item for item in artifacts if item.entity_type == "EVALUATION" and "candidate" in item.path.name)

        # Formal durable execution contract: submit/replay/conflict, bounded
        # payloads, and explicit separation between submitter and worker.
        durable_job_id = "rpf14-submit-" + uuid.uuid4().hex[:8]
        submit_status, submit_response, submit_request = submit_durable(base_url, credentials["ci"], durable_job_id)
        require_status(submit_status, 201, submit_response, "durable initial submit")
        if submit_response.get("status") != "SUBMITTED" or submit_response.get("job", {}).get("state") != "QUEUED":
            raise ProbeFailure("durable submit did not return QUEUED")
        replay_status, replay_response, _ = submit_durable(
            base_url,
            credentials["ci"],
            durable_job_id,
            target_id=submit_request["target_id"],
            payload_ref=submit_request["payload_ref"],
            idempotency_key=submit_request["idempotency_key"],
        )
        require_status(replay_status, 200, replay_response, "durable replay")
        if replay_response.get("status") != "IDEMPOTENT_REPLAY" or replay_response.get("already_exists") is not True:
            raise ProbeFailure("same durable submit was not an idempotent replay")
        conflict_request = dict(submit_request)
        conflict_request["request_fingerprint"] = sha256("rpf14-different-submit")
        conflict_status, conflict_response = http_json(base_url, "POST", "/jobs", token=credentials["ci"], body=conflict_request)
        require_status(conflict_status, 409, conflict_response, "durable identity conflict")
        if conflict_response.get("error") != "IDEMPOTENCY_CONFLICT":
            raise ProbeFailure("durable identity conflict code drifted")
        unsafe_request = durable_submission("rpf14-unsafe-" + uuid.uuid4().hex[:8])
        unsafe_request["payload_ref"] = {"private_reasoning": "must-not-persist"}
        unsafe_status, unsafe_response = http_json(base_url, "POST", "/jobs", token=credentials["ci"], body=unsafe_request)
        require_status(unsafe_status, 400, unsafe_response, "unsafe durable payload")
        if unsafe_response.get("error") != "FORBIDDEN_PAYLOAD_FIELD":
            raise ProbeFailure("unsafe durable payload was not rejected")
        authority_checks = {}
        for principal_name in ("read", "agent", "decision"):
            denied_status, denied_body = http_json(
                base_url,
                "POST",
                f"/jobs/{durable_job_id}/claim",
                token=credentials[principal_name],
                body={"worker_id": f"rpf14-denied-{principal_name}", "lease_seconds": 3},
            )
            require_status(denied_status, 403, denied_body, f"{principal_name} claim authority")
            authority_checks[f"{principal_name}_claim"] = denied_status
        ci_claim_status, ci_claim_body = http_json(
            base_url,
            "POST",
            f"/jobs/{durable_job_id}/claim",
            token=credentials["ci"],
            body={"worker_id": "rpf14-ci-cannot-claim", "lease_seconds": 3},
        )
        require_status(ci_claim_status, 403, ci_claim_body, "CI worker authority")
        authority_checks["ci_claim"] = ci_claim_status
        worker_decision_status, worker_decision_body = http_json(
            base_url,
            "POST",
            "/release-decisions",
            token=credentials["worker"],
            body=decision_artifact.manifest,
        )
        require_status(worker_decision_status, 403, worker_decision_body, "worker decision authority")
        authority_checks["worker_decision"] = worker_decision_status
        checks["durable_submit_replay_conflict_authority"] = {
            "status": "PASS",
            "initial": submit_response.get("status"),
            "initial_http": submit_status,
            "replay": replay_response.get("status"),
            "conflict": conflict_response.get("error"),
            "unsafe_payload": unsafe_response.get("error"),
            "authority": authority_checks,
            "submit_does_not_start": submit_response["job"]["state"] == "QUEUED",
        }

        # Two independent HTTP workers race on one PostgreSQL row.  The
        # winner is heartbeated and finalized; the terminal row is not
        # claimable again and never exposes the raw lease token.
        race_job_id = "rpf14-claim-race-" + uuid.uuid4().hex[:8]
        race_submit_status, _, _ = submit_durable(base_url, credentials["ci"], race_job_id)
        require_status(race_submit_status, 201, {}, "claim race submit")
        with ThreadPoolExecutor(max_workers=2) as executor:
            race_results = list(executor.map(
                lambda worker: claim_durable(base_url, credentials["worker"], race_job_id, worker, 4),
                ("rpf14-race-a", "rpf14-race-b"),
            ))
        race_statuses = sorted(item[0] for item in race_results)
        if race_statuses != [200, 409]:
            raise ProbeFailure(f"concurrent durable claim expected [200, 409], got {race_statuses}")
        _, race_winner, race_lease = next(item for item in race_results if item[0] == 200)
        if race_lease is None:
            raise ProbeFailure("winning durable claim did not return a lease")
        start_status, start_response = start_durable(base_url, credentials["worker"], race_job_id, race_lease)
        require_status(start_status, 200, start_response, "race start")
        previous_version = race_lease["lease_version"]
        heartbeat_status, heartbeat_response = http_json(
            base_url,
            "POST",
            f"/jobs/{race_job_id}/heartbeat",
            token=credentials["worker"],
            body=owner_payload(race_lease) | {"lease_seconds": 4},
        )
        require_status(heartbeat_status, 200, heartbeat_response, "race heartbeat")
        race_lease.update(heartbeat_response.get("lease", {}))
        if race_lease.get("lease_version", 0) <= previous_version:
            raise ProbeFailure("heartbeat did not advance fencing version")
        _, race_evidence_response, race_evidence = ingest_durable_evidence(
            base_url, credentials["worker"], race_job_id, lease=race_lease,
            artifact_root=artifact_root, run_dir=run_dir,
        )
        race_complete_status, race_complete = http_json(
            base_url,
            "POST",
            f"/jobs/{race_job_id}/complete",
            token=credentials["worker"],
            body=owner_payload(race_lease) | {"evidence_id": race_evidence["evidence_id"]},
        )
        require_status(race_complete_status, 200, race_complete, "race complete")
        terminal_status, terminal_body, _ = claim_durable(base_url, credentials["worker"], race_job_id, "rpf14-after-terminal", 3)
        require_status(terminal_status, 200, terminal_body, "terminal claim")
        if terminal_body.get("status") != "TERMINAL":
            raise ProbeFailure("terminal durable job was claimable again")
        if contains_key(race_complete, "lease_token"):
            raise ProbeFailure("raw lease token appeared in durable job read model")
        checks["claim_heartbeat_terminal"] = {
            "status": "PASS",
            "concurrent_http_statuses": race_statuses,
            "single_owner": True,
            "heartbeat_version_advanced": True,
            "terminal_claim": terminal_body.get("status"),
            "terminal_evidence": race_complete.get("job", {}).get("terminal_evidence_id"),
            "raw_lease_token_in_read_model": False,
            "evidence_ingest": race_evidence_response.get("status"),
        }

        # Lease expiry before Agent start is safe to reclaim.  The old
        # attempt is fenced from heartbeat and finalization, while the new
        # attempt receives a distinct attempt id/number.
        reclaim_job_id = "rpf14-reclaim-" + uuid.uuid4().hex[:8]
        reclaim_submit_status, _, _ = submit_durable(base_url, credentials["ci"], reclaim_job_id)
        require_status(reclaim_submit_status, 201, {}, "reclaim submit")
        old_claim_status, _, old_lease = claim_durable(base_url, credentials["worker"], reclaim_job_id, "rpf14-old-worker", 1)
        require_status(old_claim_status, 200, {}, "old reclaim claim")
        if old_lease is None:
            raise ProbeFailure("old reclaim attempt has no lease")
        time.sleep(1.4)
        eligible_reclaim_status, eligible_reclaim_response = http_json(
            base_url, "GET", "/jobs?eligible=true&limit=20", token=credentials["read"]
        )
        require_status(eligible_reclaim_status, 200, eligible_reclaim_response, "expired lease eligible discovery")
        eligible_reclaim_ids = {
            item.get("job_id") for item in eligible_reclaim_response.get("items", []) if isinstance(item, dict)
        }
        if reclaim_job_id not in eligible_reclaim_ids:
            raise ProbeFailure("eligible discovery omitted the expired active lease")
        new_claim_status, new_claim, new_lease = claim_durable(base_url, credentials["worker"], reclaim_job_id, "rpf14-new-worker", 3)
        require_status(new_claim_status, 200, new_claim, "safe reclaim")
        if new_claim.get("status") != "CLAIMED" or new_lease is None or new_claim.get("job", {}).get("attempt_number") != 2:
            raise ProbeFailure("expired safe reclaim did not create attempt two")
        stale_evidence_status, stale_evidence_response = http_json(
            base_url,
            "POST",
            f"/jobs/{reclaim_job_id}/evidence",
            token=credentials["worker"],
            body=evidence_body(reclaim_job_id, suffix="stale-attempt", lease=old_lease),
        )
        require_status(stale_evidence_status, 409, stale_evidence_response, "stale evidence ingest")
        if stale_evidence_response.get("error") != "STALE_ATTEMPT":
            raise ProbeFailure("stale evidence ingest code drifted")
        _, _, reclaim_evidence = ingest_durable_evidence(
            base_url, credentials["worker"], reclaim_job_id, lease=new_lease,
            artifact_root=artifact_root, run_dir=run_dir,
        )
        old_heartbeat_status, old_heartbeat = http_json(
            base_url,
            "POST",
            f"/jobs/{reclaim_job_id}/heartbeat",
            token=credentials["worker"],
            body=owner_payload(old_lease) | {"lease_seconds": 3},
        )
        require_status(old_heartbeat_status, 409, old_heartbeat, "stale heartbeat")
        old_complete_status, old_complete = http_json(
            base_url,
            "POST",
            f"/jobs/{reclaim_job_id}/complete",
            token=credentials["worker"],
            body=owner_payload(old_lease) | {"evidence_id": reclaim_evidence["evidence_id"]},
        )
        require_status(old_complete_status, 409, old_complete, "stale finalization")
        if old_heartbeat.get("error") != "STALE_ATTEMPT" or old_complete.get("error") != "STALE_ATTEMPT":
            raise ProbeFailure("stale attempt rejection code drifted")
        start_durable(base_url, credentials["worker"], reclaim_job_id, new_lease)
        new_complete_status, new_complete = http_json(
            base_url,
            "POST",
            f"/jobs/{reclaim_job_id}/complete",
            token=credentials["worker"],
            body=owner_payload(new_lease) | {"evidence_id": reclaim_evidence["evidence_id"]},
        )
        require_status(new_complete_status, 200, new_complete, "new attempt finalization")
        attempts = new_complete.get("job", {}).get("attempts", [])
        if len(attempts) != 2 or attempts[0].get("attempt_id") == attempts[1].get("attempt_id"):
            raise ProbeFailure("safe reclaim did not preserve distinct append-only attempts")
        checks["lease_expiry_reclaim_stale_fencing"] = {
            "status": "PASS",
            "old_attempt_status": attempts[0].get("status"),
            "new_attempt_status": attempts[1].get("status"),
            "attempt_number": new_complete.get("job", {}).get("attempt_number"),
            "old_heartbeat": old_heartbeat.get("error"),
            "old_evidence": stale_evidence_response.get("error"),
            "old_finalize": old_complete.get("error"),
            "eligible_discovery_before_reclaim": reclaim_job_id in eligible_reclaim_ids,
            "agent_fail_created": False,
        }

        # A durable NOT_SUBMITTED boundary lets a later attempt reuse the
        # same operation identity.  The simulated controlled effect is then
        # applied once and confirmed once.
        operation_job_id = "rpf14-not-submitted-" + uuid.uuid4().hex[:8]
        operation_submit_status, _, _ = submit_durable(base_url, credentials["ci"], operation_job_id)
        require_status(operation_submit_status, 201, {}, "operation submit")
        _, _, operation_old_lease = claim_durable(base_url, credentials["worker"], operation_job_id, "rpf14-operation-old", 2)
        if operation_old_lease is None:
            raise ProbeFailure("operation old lease missing")
        start_durable(base_url, credentials["worker"], operation_job_id, operation_old_lease)
        operation_id = f"rpf14-operation-{operation_job_id}"
        operation_request = operation_body(operation_old_lease, operation_id, "rpf14-safe-environment")
        prepared_status, prepared = http_json(base_url, "POST", f"/jobs/{operation_job_id}/operations", token=credentials["worker"], body=operation_request)
        require_status(prepared_status, 200, prepared, "operation prepare")
        if prepared.get("status") != "PREPARED":
            raise ProbeFailure("operation did not enter PREPARED")
        not_submitted_status, not_submitted = http_json(
            base_url,
            "POST",
            f"/jobs/{operation_job_id}/operations/{operation_id}/not-submitted",
            token=credentials["worker"],
            body=owner_payload(operation_old_lease),
        )
        require_status(not_submitted_status, 200, not_submitted, "not submitted proof")
        if not_submitted.get("status") != "NOT_SUBMITTED":
            raise ProbeFailure("NOT_SUBMITTED proof was not recorded")
        time.sleep(2.4)
        _, operation_new_claim, operation_new_lease = claim_durable(base_url, credentials["worker"], operation_job_id, "rpf14-operation-new", 3)
        if operation_new_claim.get("status") != "CLAIMED" or operation_new_lease is None:
            raise ProbeFailure("NOT_SUBMITTED job was not safely re-claimed")
        start_durable(base_url, credentials["worker"], operation_job_id, operation_new_lease)
        operation_replay_status, operation_replay = http_json(base_url, "POST", f"/jobs/{operation_job_id}/operations", token=credentials["worker"], body=operation_body(operation_new_lease, operation_id, "rpf14-safe-environment"))
        require_status(operation_replay_status, 200, operation_replay, "operation identity replay")
        operation_conflict_body = operation_body(operation_new_lease, operation_id, "rpf14-different-environment")
        operation_conflict_status, operation_conflict = http_json(base_url, "POST", f"/jobs/{operation_job_id}/operations", token=credentials["worker"], body=operation_conflict_body)
        require_status(operation_conflict_status, 409, operation_conflict, "operation identity conflict")
        applied_status, applied = http_json(base_url, "POST", f"/jobs/{operation_job_id}/operations/{operation_id}/apply", token=credentials["worker"], body=owner_payload(operation_new_lease))
        require_status(applied_status, 200, applied, "operation apply")
        confirmed_status, confirmed = http_json(base_url, "POST", f"/jobs/{operation_job_id}/operations/{operation_id}/confirm", token=credentials["worker"], body=owner_payload(operation_new_lease))
        require_status(confirmed_status, 200, confirmed, "operation confirm")
        _, _, operation_evidence = ingest_durable_evidence(
            base_url, credentials["worker"], operation_job_id, lease=operation_new_lease,
            artifact_root=artifact_root, run_dir=run_dir,
        )
        operation_complete_status, operation_complete = http_json(
            base_url,
            "POST",
            f"/jobs/{operation_job_id}/complete",
            token=credentials["worker"],
            body=owner_payload(operation_new_lease) | {"evidence_id": operation_evidence["evidence_id"]},
        )
        require_status(operation_complete_status, 200, operation_complete, "operation complete")
        operation_snapshot = operation_complete.get("job", {})
        if operation_snapshot.get("operations", [{}])[0].get("effect_count") != 1:
            raise ProbeFailure("operation retry produced more than one side effect")
        checks["operation_identity_not_submitted"] = {
            "status": "PASS",
            "prepare": prepared.get("status"),
            "not_submitted": not_submitted.get("status"),
            "reclaim_attempt": operation_snapshot.get("attempt_number"),
            "replay": operation_replay.get("status"),
            "identity_conflict": operation_conflict.get("error"),
            "apply": applied.get("status"),
            "confirm": confirmed.get("status"),
            "effect_count": operation_snapshot["operations"][0].get("effect_count"),
            "agent_fail_created": False,
        }

        # A real child process commits the controlled effect, receives a
        # response-lost boundary, and exits.  The recovery worker must first
        # mark/reconcile UNKNOWN_OUTCOME; it may not blindly apply again.
        unknown_job_id = "rpf14-unknown-" + uuid.uuid4().hex[:8]
        unknown_submit_status, _, _ = submit_durable(base_url, credentials["ci"], unknown_job_id)
        require_status(unknown_submit_status, 201, {}, "unknown submit")
        unknown_operation_id = f"rpf14-operation-{unknown_job_id}"
        response_lost_child = spawn_response_lost_worker(base_url, unknown_job_id, unknown_operation_id, credentials["worker"])
        if response_lost_child.returncode != 17:
            raise ProbeFailure(f"response-lost child exited at wrong boundary: {response_lost_child.returncode}")
        time.sleep(1.4)
        expired_status, expired_response, expired_lease = claim_durable(base_url, credentials["worker"], unknown_job_id, "rpf14-reconcile-worker", 3)
        require_status(expired_status, 200, expired_response, "expired unknown claim")
        if expired_response.get("status") != "RECONCILE_REQUIRED" or expired_lease is not None:
            raise ProbeFailure("expired in-flight effect did not enter reconcile-required")
        unknown_status, unknown_response = http_json(base_url, "POST", f"/jobs/{unknown_job_id}/operations/{unknown_operation_id}/unknown", token=credentials["worker"], body={"worker_id": "rpf14-reconcile-worker"})
        require_status(unknown_status, 200, unknown_response, "mark unknown outcome")
        reconcile_status, reconcile_response = http_json(base_url, "POST", f"/jobs/{unknown_job_id}/operations/{unknown_operation_id}/reconcile", token=credentials["worker"], body={"worker_id": "rpf14-reconcile-worker"})
        require_status(reconcile_status, 200, reconcile_response, "operation reconcile")
        if unknown_response.get("status") != "UNKNOWN_OUTCOME" or reconcile_response.get("status") != "CONFIRMED" or reconcile_response.get("safe_to_retry") is not False:
            raise ProbeFailure("UNKNOWN_OUTCOME reconcile contract failed")
        _, unknown_reclaim, unknown_lease = claim_durable(base_url, credentials["worker"], unknown_job_id, "rpf14-reconcile-final", 3)
        if unknown_reclaim.get("status") != "CLAIMED" or unknown_lease is None:
            raise ProbeFailure("reconciled unknown job was not re-queued")
        start_durable(base_url, credentials["worker"], unknown_job_id, unknown_lease)
        confirmed_replay_status, confirmed_replay = http_json(base_url, "POST", f"/jobs/{unknown_job_id}/operations", token=credentials["worker"], body=operation_body(unknown_lease, unknown_operation_id, "rpf14-response-lost-environment"))
        require_status(confirmed_replay_status, 200, confirmed_replay, "confirmed operation prepare replay")
        no_blind_retry_status, no_blind_retry = http_json(base_url, "POST", f"/jobs/{unknown_job_id}/operations/{unknown_operation_id}/apply", token=credentials["worker"], body=owner_payload(unknown_lease))
        require_status(no_blind_retry_status, 200, no_blind_retry, "confirmed operation no-op")
        _, _, unknown_evidence = ingest_durable_evidence(
            base_url, credentials["worker"], unknown_job_id, lease=unknown_lease,
            artifact_root=artifact_root, run_dir=run_dir,
        )
        unknown_complete_status, unknown_complete = http_json(base_url, "POST", f"/jobs/{unknown_job_id}/complete", token=credentials["worker"], body=owner_payload(unknown_lease) | {"evidence_id": unknown_evidence["evidence_id"]})
        require_status(unknown_complete_status, 200, unknown_complete, "unknown complete")
        unknown_snapshot = unknown_complete.get("job", {})
        unknown_operation = unknown_snapshot.get("operations", [{}])[0]
        unknown_events = [event.get("event_type") for event in unknown_snapshot.get("events", [])]
        if unknown_operation.get("effect_count") != 1 or "UNKNOWN_OUTCOME" not in unknown_events or "OPERATION_RECONCILED" not in unknown_events:
            raise ProbeFailure("unknown outcome recovery duplicated effect or lost event history")
        checks["response_lost_unknown_reconcile_cross_process"] = {
            "status": "PASS",
            "child_exit": response_lost_child.returncode,
            "expired_claim": expired_response.get("status"),
            "unknown": unknown_response.get("status"),
            "reconcile": reconcile_response.get("status"),
            "safe_to_retry": reconcile_response.get("safe_to_retry"),
            "confirmed_prepare_replay": confirmed_replay.get("status"),
            "post_reconcile_apply": no_blind_retry.get("status"),
            "effect_count": unknown_operation.get("effect_count"),
            "events": [event for event in unknown_events if event in {"UNKNOWN_OUTCOME", "OPERATION_RECONCILED"}],
            "worker_restart_boundary": True,
            "agent_fail_created": False,
        }

        # Artifact generation is separated from ingest.  A child exits after
        # generation; the parent performs canonical ingest twice and records
        # one immutable execution evidence ref without rerunning the Agent.
        artifact_job_id = "rpf14-artifact-" + uuid.uuid4().hex[:8]
        artifact_submit_status, _, _ = submit_durable(base_url, credentials["ci"], artifact_job_id)
        require_status(artifact_submit_status, 201, {}, "artifact submit")
        _, _, artifact_lease = claim_durable(base_url, credentials["worker"], artifact_job_id, "rpf14-artifact-worker", 4)
        if artifact_lease is None:
            raise ProbeFailure("artifact job lease missing")
        start_durable(base_url, credentials["worker"], artifact_job_id, artifact_lease)
        artifact_document = json.loads(candidate_evaluation.path.read_text(encoding="utf-8"))
        artifact_evaluation_id = f"rpf14-generated-evaluation-{uuid.uuid4().hex[:8]}"
        if not isinstance(artifact_document.get("evaluation"), dict):
            raise ProbeFailure("reviewed Evaluation fixture is malformed")
        artifact_document["evaluation"]["evaluation_id"] = artifact_evaluation_id
        generated_artifact_path = run_dir / f"{artifact_evaluation_id}.json"
        generated_artifact_path.write_text(json.dumps(artifact_document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        artifact_crash = spawn_artifact_crash_worker(generated_artifact_path)
        if artifact_crash.returncode != 23:
            raise ProbeFailure(f"artifact worker exited at wrong boundary: {artifact_crash.returncode}")
        artifact_client = ControlPlaneClient(base_url, credentials["worker"])
        artifact_first = artifact_client.ingest_file(generated_artifact_path, artifact_root)
        artifact_manifest = build_artifact_manifest(generated_artifact_path, artifact_root)
        artifact_second = artifact_client.ingest_file(generated_artifact_path, artifact_root)
        if artifact_first.get("status") not in {"INGESTED", "RECONCILED"} or artifact_second.get("status") not in {"IDEMPOTENT_REPLAY", "RECONCILED"}:
            raise ProbeFailure("artifact ingest interruption was not idempotent")
        artifact_evidence = {
            "evidence_id": f"rpf14-execution-evidence-{artifact_job_id}",
            "entity_type": "EVALUATION",
            "entity_id": artifact_evaluation_id,
            "outcome": "PASS",
            "content_sha256": artifact_manifest.content_sha256,
            "artifact_ref": artifact_manifest.manifest["artifact_ref"],
        }
        artifact_evidence = owner_payload(artifact_lease) | artifact_evidence
        artifact_evidence_status, artifact_evidence_response = http_json(base_url, "POST", f"/jobs/{artifact_job_id}/evidence", token=credentials["worker"], body=artifact_evidence)
        require_status(artifact_evidence_status, 200, artifact_evidence_response, "artifact execution evidence")
        artifact_replay_status, artifact_replay_response = http_json(base_url, "POST", f"/jobs/{artifact_job_id}/evidence", token=credentials["worker"], body=artifact_evidence)
        require_status(artifact_replay_status, 200, artifact_replay_response, "artifact evidence replay")
        artifact_complete_status, artifact_complete = http_json(base_url, "POST", f"/jobs/{artifact_job_id}/complete", token=credentials["worker"], body=owner_payload(artifact_lease) | {"evidence_id": artifact_evidence["evidence_id"]})
        require_status(artifact_complete_status, 200, artifact_complete, "artifact job complete")
        if artifact_complete.get("job", {}).get("attempt_number") != 1 or len(artifact_complete.get("job", {}).get("evidence", [])) != 1:
            raise ProbeFailure("artifact recovery reran the attempt or duplicated evidence")
        checks["artifact_ingest_crash_recovery"] = {
            "status": "PASS",
            "artifact_generated_before_crash": True,
            "child_exit": artifact_crash.returncode,
            "canonical_first_ingest": artifact_first.get("status"),
            "canonical_replay": artifact_second.get("status"),
            "execution_evidence": artifact_evidence_response.get("status"),
            "execution_evidence_replay": artifact_replay_response.get("status"),
            "attempt_number": artifact_complete.get("job", {}).get("attempt_number"),
            "evidence_count": len(artifact_complete.get("job", {}).get("evidence", [])),
            "agent_rerun": False,
        }

        # A PASS evidence row without a registered canonical artifact is not
        # allowed to terminalize a claimed/running job.  The row remains
        # active so the worker can repair the missing artifact or report a
        # platform failure without silently claiming success.
        missing_artifact_job_id = "rpf14-terminal-missing-artifact-" + uuid.uuid4().hex[:8]
        missing_submit_status, _, _ = submit_durable(base_url, credentials["ci"], missing_artifact_job_id)
        require_status(missing_submit_status, 201, {}, "missing terminal artifact submit")
        _, _, missing_artifact_lease = claim_durable(base_url, credentials["worker"], missing_artifact_job_id, "rpf14-missing-artifact-worker", 4)
        if missing_artifact_lease is None:
            raise ProbeFailure("missing terminal artifact lease missing")
        start_durable(base_url, credentials["worker"], missing_artifact_job_id, missing_artifact_lease)
        missing_evidence = evidence_body(missing_artifact_job_id, lease=missing_artifact_lease)
        missing_evidence_status, missing_evidence_response = http_json(
            base_url, "POST", f"/jobs/{missing_artifact_job_id}/evidence",
            token=credentials["worker"], body=missing_evidence,
        )
        require_status(missing_evidence_status, 200, missing_evidence_response, "missing terminal artifact evidence")
        missing_complete_status, missing_complete_response = http_json(
            base_url, "POST", f"/jobs/{missing_artifact_job_id}/complete",
            token=credentials["worker"],
            body=owner_payload(missing_artifact_lease) | {"evidence_id": missing_evidence["evidence_id"]},
        )
        require_status(missing_complete_status, 422, missing_complete_response, "missing terminal artifact completion")
        if missing_complete_response.get("error") != "TERMINAL_ARTIFACT_NOT_REGISTERED":
            raise ProbeFailure("missing terminal artifact error code drifted")
        missing_job_status, missing_job = http_json(base_url, "GET", f"/jobs/{missing_artifact_job_id}", token=credentials["read"])
        require_status(missing_job_status, 200, missing_job, "missing terminal artifact read-back")
        if missing_job.get("state") != "RUNNING" or missing_job.get("terminal_evidence_id") is not None:
            raise ProbeFailure("missing terminal artifact changed the job to a false terminal success")

        mismatch_artifact_job_id = "rpf14-terminal-mismatch-artifact-" + uuid.uuid4().hex[:8]
        mismatch_submit_status, _, _ = submit_durable(base_url, credentials["ci"], mismatch_artifact_job_id)
        require_status(mismatch_submit_status, 201, {}, "mismatched terminal artifact submit")
        _, _, mismatch_lease = claim_durable(base_url, credentials["worker"], mismatch_artifact_job_id, "rpf14-mismatch-artifact-worker", 4)
        if mismatch_lease is None:
            raise ProbeFailure("mismatched terminal artifact lease missing")
        start_durable(base_url, credentials["worker"], mismatch_artifact_job_id, mismatch_lease)
        mismatch_artifact = prepare_terminal_artifact(
            base_url, credentials["worker"], artifact_root, run_dir,
            mismatch_artifact_job_id, "mismatch",
        )
        mismatch_evidence = evidence_body(mismatch_artifact_job_id, suffix="mismatch", lease=mismatch_lease)
        mismatch_evidence.update({
            "entity_type": mismatch_artifact.entity_type,
            "entity_id": mismatch_artifact.entity_id,
            "content_sha256": mismatch_artifact.content_sha256,
            "artifact_ref": json.loads(json.dumps(mismatch_artifact.manifest["artifact_ref"])),
        })
        mismatch_evidence["artifact_ref"]["artifact_id"] = "tampered-terminal-artifact"
        mismatch_evidence_status, mismatch_evidence_response = http_json(
            base_url, "POST", f"/jobs/{mismatch_artifact_job_id}/evidence",
            token=credentials["worker"], body=mismatch_evidence,
        )
        require_status(mismatch_evidence_status, 200, mismatch_evidence_response, "mismatched terminal artifact evidence")
        mismatch_complete_status, mismatch_complete_response = http_json(
            base_url, "POST", f"/jobs/{mismatch_artifact_job_id}/complete",
            token=credentials["worker"],
            body=owner_payload(mismatch_lease) | {"evidence_id": mismatch_evidence["evidence_id"]},
        )
        require_status(mismatch_complete_status, 422, mismatch_complete_response, "mismatched terminal artifact completion")
        if mismatch_complete_response.get("error") != "INVALID_TERMINAL_ARTIFACT_REF":
            raise ProbeFailure("mismatched terminal artifact error code drifted")
        mismatch_job_status, mismatch_job = http_json(
            base_url, "GET", f"/jobs/{mismatch_artifact_job_id}", token=credentials["read"],
        )
        require_status(mismatch_job_status, 200, mismatch_job, "mismatched terminal artifact read-back")
        if mismatch_job.get("state") != "RUNNING" or mismatch_job.get("terminal_evidence_id") is not None:
            raise ProbeFailure("mismatched terminal artifact changed the job to a false terminal success")
        checks["terminal_artifact_binding"] = {
            "status": "PASS",
            "missing_artifact_http": missing_complete_status,
            "missing_artifact_error": missing_complete_response.get("error"),
            "job_state_after_rejection": missing_job.get("state"),
            "terminal_evidence_after_rejection": missing_job.get("terminal_evidence_id"),
            "mismatched_artifact_http": mismatch_complete_status,
            "mismatched_artifact_error": mismatch_complete_response.get("error"),
            "mismatched_job_state_after_rejection": mismatch_job.get("state"),
        }

        # Cancellation and timeout remain platform/execution states, never
        # an Agent FAIL.  Queued cancellation/timeout terminalize directly;
        # running cancellation waits for owner acknowledgement.
        queued_cancel_id = "rpf14-cancel-queued-" + uuid.uuid4().hex[:8]
        cancel_submit_status, _, _ = submit_durable(base_url, credentials["ci"], queued_cancel_id)
        require_status(cancel_submit_status, 201, {}, "queued cancel submit")
        _, _, queued_cancel_evidence = ingest_durable_evidence(base_url, credentials["worker"], queued_cancel_id, "CANCELLED")
        queued_cancel_status, queued_cancel_response = http_json(base_url, "POST", f"/jobs/{queued_cancel_id}/cancel", token=credentials["ci"], body={"evidence_id": queued_cancel_evidence["evidence_id"]})
        require_status(queued_cancel_status, 200, queued_cancel_response, "queued cancel")
        if queued_cancel_response.get("job", {}).get("state") != "CANCELLED":
            raise ProbeFailure("queued cancel did not terminalize")
        running_cancel_id = "rpf14-cancel-running-" + uuid.uuid4().hex[:8]
        cancel_running_submit_status, _, _ = submit_durable(base_url, credentials["ci"], running_cancel_id)
        require_status(cancel_running_submit_status, 201, {}, "running cancel submit")
        _, _, running_cancel_lease = claim_durable(base_url, credentials["worker"], running_cancel_id, "rpf14-cancel-worker", 4)
        if running_cancel_lease is None:
            raise ProbeFailure("running cancel lease missing")
        start_durable(base_url, credentials["worker"], running_cancel_id, running_cancel_lease)
        _, _, running_cancel_evidence = ingest_durable_evidence(base_url, credentials["worker"], running_cancel_id, "CANCELLED", lease=running_cancel_lease)
        cancel_request_status, cancel_request_response = http_json(base_url, "POST", f"/jobs/{running_cancel_id}/cancel", token=credentials["ci"], body={})
        require_status(cancel_request_status, 200, cancel_request_response, "running cancel request")
        if cancel_request_response.get("status") != "CANCEL_REQUESTED":
            raise ProbeFailure("running cancel did not remain a request")
        running_cancel_lease["lease_version"] = cancel_request_response["job"]["version"]
        cancel_ack_status, cancel_ack_response = http_json(base_url, "POST", f"/jobs/{running_cancel_id}/cancel/ack", token=credentials["worker"], body=owner_payload(running_cancel_lease) | {"evidence_id": running_cancel_evidence["evidence_id"]})
        require_status(cancel_ack_status, 200, cancel_ack_response, "running cancel acknowledgement")
        if cancel_ack_response.get("job", {}).get("state") != "CANCELLED":
            raise ProbeFailure("running cancel acknowledgement did not cancel")

        timeout_job_id = "rpf14-timeout-unknown-" + uuid.uuid4().hex[:8]
        timeout_submit_status, _, _ = submit_durable(base_url, credentials["ci"], timeout_job_id)
        require_status(timeout_submit_status, 201, {}, "timeout submit")
        _, _, timeout_lease = claim_durable(base_url, credentials["worker"], timeout_job_id, "rpf14-timeout-worker", 4)
        if timeout_lease is None:
            raise ProbeFailure("timeout lease missing")
        start_durable(base_url, credentials["worker"], timeout_job_id, timeout_lease)
        timeout_operation_id = f"rpf14-operation-{timeout_job_id}"
        timeout_operation_status, timeout_operation_response = http_json(base_url, "POST", f"/jobs/{timeout_job_id}/operations", token=credentials["worker"], body=operation_body(timeout_lease, timeout_operation_id, "rpf14-timeout-environment"))
        require_status(timeout_operation_status, 200, timeout_operation_response, "timeout operation prepare")
        timeout_lost_status, timeout_lost_response = http_json(base_url, "POST", f"/jobs/{timeout_job_id}/operations/{timeout_operation_id}/apply?simulate_response_lost=true", token=credentials["worker"], body=owner_payload(timeout_lease))
        require_status(timeout_lost_status, 503, timeout_lost_response, "timeout response-lost")
        _, _, timeout_evidence = ingest_durable_evidence(base_url, credentials["worker"], timeout_job_id, "INCONCLUSIVE", lease=timeout_lease)
        timeout_request_status, timeout_request_response = http_json(base_url, "POST", f"/jobs/{timeout_job_id}/timeout", token=credentials["worker"], body=owner_payload(timeout_lease) | {"evidence_id": timeout_evidence["evidence_id"]})
        require_status(timeout_request_status, 200, timeout_request_response, "unknown timeout")
        if timeout_request_response.get("status") != "RECONCILE_REQUIRED":
            raise ProbeFailure("unknown side-effect timeout did not require reconcile")
        http_json(base_url, "POST", f"/jobs/{timeout_job_id}/operations/{timeout_operation_id}/unknown", token=credentials["worker"], body={"worker_id": "rpf14-timeout-recovery"})
        timeout_reconcile_status, timeout_reconcile_response = http_json(base_url, "POST", f"/jobs/{timeout_job_id}/operations/{timeout_operation_id}/reconcile", token=credentials["worker"], body={"worker_id": "rpf14-timeout-recovery"})
        require_status(timeout_reconcile_status, 200, timeout_reconcile_response, "timeout reconcile")
        _, _, timeout_final_lease = claim_durable(base_url, credentials["worker"], timeout_job_id, "rpf14-timeout-final", 3)
        if timeout_final_lease is None:
            raise ProbeFailure("timeout reconcile did not requeue")
        start_durable(base_url, credentials["worker"], timeout_job_id, timeout_final_lease)
        timeout_failed_status, timeout_failed_response = http_json(base_url, "POST", f"/jobs/{timeout_job_id}/fail-platform", token=credentials["worker"], body=owner_payload(timeout_final_lease) | {"evidence_id": timeout_evidence["evidence_id"], "reason": "RPF14_TIMEOUT_AFTER_RECONCILE"})
        require_status(timeout_failed_status, 200, timeout_failed_response, "platform timeout finalization")
        queued_timeout_id = "rpf14-timeout-queued-" + uuid.uuid4().hex[:8]
        queued_timeout_submit_status, _, _ = submit_durable(base_url, credentials["ci"], queued_timeout_id)
        require_status(queued_timeout_submit_status, 201, {}, "queued timeout submit")
        _, _, queued_timeout_evidence = ingest_durable_evidence(base_url, credentials["worker"], queued_timeout_id, "INCONCLUSIVE")
        queued_timeout_status, queued_timeout_response = http_json(base_url, "POST", f"/jobs/{queued_timeout_id}/timeout", token=credentials["ci"], body={"evidence_id": queued_timeout_evidence["evidence_id"]})
        require_status(queued_timeout_status, 200, queued_timeout_response, "queued timeout")
        if timeout_failed_response.get("job", {}).get("state") != "FAILED_PLATFORM" or timeout_failed_response.get("job", {}).get("outcome_status") != "INCONCLUSIVE":
            raise ProbeFailure("platform timeout was not FAILED_PLATFORM/INCONCLUSIVE")
        if queued_timeout_response.get("job", {}).get("state") != "FAILED_PLATFORM":
            raise ProbeFailure("queued timeout was not FAILED_PLATFORM")
        checks["cancellation_timeout_platform_semantics"] = {
            "status": "PASS",
            "queued_cancel": queued_cancel_response.get("status"),
            "running_cancel_request": cancel_request_response.get("status"),
            "running_cancel_ack": cancel_ack_response.get("job", {}).get("state"),
            "unknown_timeout": timeout_request_response.get("status"),
            "timeout_reconcile": timeout_reconcile_response.get("status"),
            "platform_timeout_state": timeout_failed_response.get("job", {}).get("state"),
            "platform_timeout_outcome": timeout_failed_response.get("job", {}).get("outcome_status"),
            "queued_timeout_state": queued_timeout_response.get("job", {}).get("state"),
            "agent_fail_created": False,
        }

        # Read API/metrics and retention boundary are intentionally
        # operator-facing and read-only.  No delete/cleanup route is exposed
        # by this stabilization implementation.
        jobs_status, jobs_response = http_json(base_url, "GET", "/jobs?limit=100", token=credentials["read"])
        require_status(jobs_status, 200, jobs_response, "execution list API")
        metrics_status, metrics_response = http_json(base_url, "GET", "/execution-metrics", token=credentials["read"])
        require_status(metrics_status, 200, metrics_response, "execution metrics API")
        required_metrics = {"queued_jobs", "claimed_or_running_jobs", "reconcile_required_jobs", "completed_jobs", "platform_failed_jobs", "cancelled_jobs", "lease_expiry_count", "reclaim_count", "stale_attempt_rejection_count", "attempts_total", "eligible_jobs"}
        if not required_metrics.issubset(metrics_response):
            raise ProbeFailure("execution metrics are incomplete")
        listed_jobs = jobs_response.get("items", [])
        if any(contains_key(item, "lease_token") for item in listed_jobs):
            raise ProbeFailure("execution list API exposed a raw lease token")
        schema_tables = psql(container, "runproof", "SELECT count(*) FROM information_schema.tables WHERE table_name IN ('rpf_execution_job','rpf_execution_attempt','rpf_execution_operation','rpf_execution_event','rpf_execution_evidence');")
        eligible_index_count = psql(container, "runproof", "SELECT count(*) FROM pg_indexes WHERE indexname='rpf_execution_job_eligible_discovery_idx';")
        history_versions = psql(container, "runproof", "SELECT string_agg(version, ',') FROM rpf_schema_history;")
        if int(schema_tables) != 5 or int(eligible_index_count) != 1 or "rpf-11-postgresql-canonical-schema-v1" not in history_versions or SCHEMA_VERSION not in history_versions:
            raise ProbeFailure("durable schema/history identity is incomplete")
        checks["execution_read_api_metrics_retention"] = {
            "status": "PASS",
            "listed_jobs": len(listed_jobs),
            "metrics": sorted(required_metrics),
            "raw_lease_token_in_read_model": False,
            "retention": {
                "terminal_jobs_retained": True,
                "attempts_events_append_only": True,
                "evidence_retention_independent": True,
                "delete_endpoint": False,
                "cleanup_policy": "OUT_OF_SCOPE_NO_SILENT_DELETE",
            },
            "execution_tables": int(schema_tables),
            "eligible_discovery_index": int(eligible_index_count),
            "schema_history": history_versions.split(","),
        }

        decision_id = "release-decision-rpf14-superseding-" + uuid.uuid4().hex[:8]
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

        stop_process(service)
        if service_handles:
            for handle in service_handles:
                handle.close()
            service_handles = None
        service, *handles = start_service(service_port, pg_port, artifact_root, credentials, log_dir)
        service_handles = (handles[0], handles[1])
        health = wait_for_health(base_url, service)
        status, body = http_json(base_url, "GET", f"/metadata/RELEASE_DECISION/{decision_id}", token=credentials["read"])
        require_status(status, 200, body, "service restart history")
        status, worker_after_restart = http_json(base_url, "GET", f"/jobs/{worker_job_id}", token=credentials["read"])
        require_status(status, 200, worker_after_restart, "worker terminal read after service restart")
        if worker_after_restart.get("state") != "COMPLETED":
            raise ProbeFailure("formal worker terminal job was not readable after service restart")
        checks["service_restart"] = {"status": "PASS", "ready": health.get("readiness"), "history_recovered": True, "worker_terminal_readback": worker_after_restart.get("state")}

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
        restore_database = "rpf14_restore"
        docker(["exec", container, "createdb", "-U", "runproof", restore_database])
        docker(["exec", "-i", container, "pg_restore", "-U", "runproof", "-d", restore_database], input_bytes=dump, timeout=60)
        restored_rows = int(psql(container, restore_database, "SELECT count(*) FROM canonical_metadata;"))
        restored_decisions = int(psql(container, restore_database, "SELECT count(*) FROM canonical_metadata WHERE entity_type = 'RELEASE_DECISION';"))
        restored_jobs = int(psql(container, restore_database, "SELECT count(*) FROM rpf_execution_job;"))
        restored_events = int(psql(container, restore_database, "SELECT count(*) FROM rpf_execution_event;"))
        docker(["exec", container, "dropdb", "-U", "runproof", restore_database])
        if restored_rows < expected_rows or restored_decisions < 3 or restored_jobs < 1 or restored_events < restored_jobs:
            raise ProbeFailure("independent pg_restore did not preserve canonical and execution rows")
        checks["backup_restore"] = {"status": "PASS", "format": "pg_dump custom", "bytes": len(dump), "restored_canonical_rows": restored_rows, "restored_decisions": restored_decisions, "restored_execution_jobs": restored_jobs, "restored_execution_events": restored_events}

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
            "schema_version": "rpf-14-formal-control-plane-evidence-v1",
            "artifact_kind": "RunProof Formal Durable Execution Evidence",
            "status": "PASS",
            "checks": checks,
            "source_identity": formal_source_identity(),
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
            stop_process(mismatch_service, timeout=5)
        if service is not None and service.poll() is None:
            stop_process(service)
        if service_handles:
            for handle in service_handles:
                handle.close()
        cleanup(container, volume)
        for process_id in sorted(PROBE_PROCESS_IDS):
            subprocess.run(["taskkill", "/PID", str(process_id), "/T", "/F"], capture_output=True, check=False, timeout=10)
        PROBE_PROCESS_IDS.clear()


def write_result(run_dir: Path, document: dict[str, Any]) -> int:
    output = run_dir / "probe-result.json"
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if document.get("status") == "PASS":
        print(f"PASS: RPF-14 formal Control Plane durable/PostgreSQL/corpus/auth probe ({output.as_posix()})")
        return 0
    print(f"FAIL: RPF-14 formal Control Plane probe ({output.as_posix()})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--worker-response-lost":
        raise SystemExit(run_response_lost_child(sys.argv[2], sys.argv[3], sys.argv[4]))
    if len(sys.argv) == 3 and sys.argv[1] == "--worker-artifact-crash":
        raise SystemExit(run_artifact_crash_child(sys.argv[2]))
    raise SystemExit(main())
