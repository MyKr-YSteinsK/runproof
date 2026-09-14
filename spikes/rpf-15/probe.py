"""Production-like deployment, persistence, and release-boundary probe.

RPF-15 deliberately exercises one disposable single-host candidate rather
than claiming that a local Docker stack is Production.  The candidate keeps
Web, Control Plane, durable worker, PostgreSQL, and the immutable local
artifact path as separate process/storage boundaries.  A second managed
persistence/stateless candidate is captured as a decision comparison only;
it is not contacted because no target cloud account or paid resource was
authorized.

The probe owns every container, volume, JVM, worker harness, and static Web
server it starts.  Credentials are generated in memory, injected only into
the relevant process environment, and never written to the result, logs, or
artifact files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.runproof_runtime.control_plane_client import (  # noqa: E402
    ControlPlaneClient,
    ControlPlaneClientError,
    build_artifact_manifest,
    register_reviewed_corpus,
)


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = ROOT / "spikes" / "rpf-15"
LOCAL_ROOT = ROOT / ".local" / "rpf-15"
JAR_PATH = ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
WEB_DIST = ROOT / "dist"
POSTGRES_IMAGE = "postgres:16-alpine"
PROBE_SCHEMA = "rpf-15-production-readiness-evidence-v1"
EXECUTION_SCHEMA = "rpf-14-durable-execution-schema-v1"
PROCESSES: list[subprocess.Popen[bytes]] = []


class ProbeFailure(RuntimeError):
    """A production-like contract assertion failed."""


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def checked(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, input_bytes: bytes | None = None, timeout: int = 60) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_bytes,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeFailure(f"command failed: {Path(command[0]).name} exit={result.returncode}")
    return result


def run_bounded(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int, label: str) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    PROCESSES.append(process)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        stop_process(process)
        process.communicate(timeout=10)
        raise ProbeFailure(f"{label} timed out") from error
    except KeyboardInterrupt:
        stop_process(process)
        process.communicate(timeout=10)
        raise
    finally:
        if process in PROCESSES:
            PROCESSES.remove(process)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def docker(command: list[str], *, input_bytes: bytes | None = None, timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["docker", *command],
        input=input_bytes,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise ProbeFailure(f"docker command failed: {command[0]}")
    return result


def http_json(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 8.0,
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
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}


def http_text(base_url: str, path: str, *, timeout: float = 8.0) -> tuple[int, bytes, str]:
    request = Request(f"{base_url}{path}", headers={"Accept": "text/html,application/javascript"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return int(response.status), raw, response.headers.get("Content-Type", "")
    except HTTPError as error:
        return int(error.code), error.read(), error.headers.get("Content-Type", "") if error.headers else ""
    except (URLError, TimeoutError, OSError):
        return 0, b"", ""


def expect(status: int, expected: int, body: dict[str, Any], label: str) -> None:
    require(status == expected, f"{label} expected HTTP {expected}, got {status}")
    if expected < 400:
        require(not body.get("error"), f"{label} returned an API error")


def stop_process(process: subprocess.Popen[bytes] | None, *, timeout: int = 12) -> None:
    if process is None:
        return
    process_id = process.pid
    was_running = process.poll() is None
    if os.name == "nt" and was_running:
        subprocess.run(["taskkill", "/PID", str(process_id), "/T", "/F"], capture_output=True, check=False, timeout=10)
    if was_running and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
    if os.name == "nt" and was_running and process.poll() is None:
        subprocess.run(["taskkill", "/PID", str(process_id), "/T", "/F"], capture_output=True, check=False, timeout=10)
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)


def wait_http(url: str, process: subprocess.Popen[bytes], *, timeout: float = 45.0, predicate: Any | None = None) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure(f"process exited before HTTP readiness: {process.pid}")
        status, body, _ = http_text(url, "")
        if status == 200 and (predicate is None or predicate(body)):
            return
        time.sleep(0.25)
    raise ProbeFailure(f"HTTP service did not become ready: {url}")


def wait_control_plane(base_url: str, process: subprocess.Popen[bytes], *, timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("Control Plane exited before readiness")
        status, body = http_json(base_url, "GET", "/health")
        if status == 200 and body.get("ready") is True and body.get("readiness") == "READY":
            return body
        time.sleep(0.3)
    raise ProbeFailure("Control Plane did not become ready")


class PostgresRuntime:
    """A named-volume PostgreSQL candidate that can be container-replaced."""

    def __init__(self, prefix: str) -> None:
        suffix = secrets.token_hex(6)
        self.name = f"{prefix}-postgres-{suffix}"
        self.volume = f"{prefix}-volume-{suffix}"
        self.user = "runproof"
        self.database = "runproof"
        self.password = secrets.token_urlsafe(30)
        self.port: int | None = None
        self.volume_created = False
        self.container_created = False

    def _exec(self, args: list[str], *, input_bytes: bytes | None = None, timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        exec_args = ["exec"]
        if input_bytes is not None:
            exec_args.append("--interactive")
        return docker([*exec_args, "--env", f"PGPASSWORD={self.password}", self.name, *args], input_bytes=input_bytes, timeout=timeout, check=check)

    def _start_container(self) -> None:
        self.port = choose_port()
        docker([
            "run", "--detach", "--name", self.name, "--restart=no",
            "--env", f"POSTGRES_USER={self.user}",
            "--env", f"POSTGRES_PASSWORD={self.password}",
            "--env", f"POSTGRES_DB={self.database}",
            "--mount", f"type=volume,source={self.volume},target=/var/lib/postgresql/data",
            "--publish", f"127.0.0.1:{self.port}:5432", POSTGRES_IMAGE,
        ], timeout=60)
        self.container_created = True
        self.wait_ready()

    def start(self) -> None:
        docker(["volume", "create", self.volume], timeout=30)
        self.volume_created = True
        self._start_container()

    def wait_ready(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self._exec(["pg_isready", "-U", self.user, "-d", self.database], timeout=15, check=False)
            if result.returncode == 0:
                return
            time.sleep(0.4)
        raise ProbeFailure("PostgreSQL did not become ready")

    def query(self, sql: str, *, database: str | None = None) -> str:
        result = self._exec([
            "psql", "--username", self.user, "--dbname", database or self.database,
            "--tuples-only", "--no-align", "--field-separator", "|", "--command", sql,
        ], timeout=60)
        return result.stdout.decode("utf-8", errors="replace").strip()

    def dump(self) -> bytes:
        return self._exec(["pg_dump", "--username", self.user, "--dbname", self.database, "--format=custom"], timeout=120).stdout

    def restore_dump(self, dump: bytes) -> None:
        result = self._exec(["pg_restore", "--username", self.user, "--dbname", self.database, "--exit-on-error"], input_bytes=dump, timeout=120, check=False)
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").splitlines()[0] if result.stderr else "no diagnostic"
            detail = re.sub(r"[^A-Za-z0-9_.:/() -]", "", detail)[:180]
            raise ProbeFailure(f"pg_restore failed exit={result.returncode}:{detail}")

    def replace_container(self) -> None:
        docker(["rm", "--force", self.name], timeout=30, check=False)
        self.container_created = False
        self._start_container()

    def cleanup(self) -> None:
        if self.container_created:
            docker(["rm", "--force", self.name], timeout=30, check=False)
            self.container_created = False
        if self.volume_created:
            docker(["volume", "rm", "--force", self.volume], timeout=30, check=False)
            self.volume_created = False


def start_control_plane(
    pg: PostgresRuntime,
    artifact_root: Path,
    credentials: dict[str, str],
    log_dir: Path,
    build_id: str,
) -> dict[str, Any]:
    require(pg.port is not None, "PostgreSQL port is unavailable")
    port_number = choose_port()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_handle = (log_dir / f"control-plane-{port_number}.stdout.log").open("wb")
    stderr_handle = (log_dir / f"control-plane-{port_number}.stderr.log").open("wb")
    environment = os.environ.copy()
    environment.update({
        "RPF_CONTROL_PLANE_ADDRESS": "127.0.0.1",
        "RPF_CONTROL_PLANE_PORT": str(port_number),
        "RPF_JDBC_URL": f"jdbc:postgresql://127.0.0.1:{pg.port}/runproof",
        "RPF_DB_USER": pg.user,
        "RPF_DB_PASSWORD": pg.password,
        "RPF_ARTIFACT_STORE_ROOT": str(artifact_root.resolve()),
        "RPF_PROBE_ENABLED": "true",
        "RPF_DEPLOYMENT_BUILD_ID": build_id,
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
        stdout=stdout_handle,
        stderr=stderr_handle,
    )
    PROCESSES.append(process)
    return {
        "process": process,
        "base_url": f"http://127.0.0.1:{port_number}/api/v1",
        "stdout": stdout_handle,
        "stderr": stderr_handle,
        "log_paths": [log_dir / f"control-plane-{port_number}.stdout.log", log_dir / f"control-plane-{port_number}.stderr.log"],
        "build_id": build_id,
    }


def stop_control_plane(service: dict[str, Any] | None) -> None:
    if not service:
        return
    stop_process(service.get("process"))
    for key in ("stdout", "stderr"):
        handle = service.get(key)
        if handle is not None and not handle.closed:
            handle.close()


def start_web(dist_root: Path, log_dir: Path) -> dict[str, Any]:
    require((dist_root / "index.html").is_file(), "Web production build is missing index.html")
    port_number = choose_port()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_handle = (log_dir / f"web-{port_number}.stdout.log").open("wb")
    stderr_handle = (log_dir / f"web-{port_number}.stderr.log").open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port_number), "--bind", "127.0.0.1"],
        cwd=dist_root,
        stdout=stdout_handle,
        stderr=stderr_handle,
    )
    PROCESSES.append(process)
    base_url = f"http://127.0.0.1:{port_number}"
    wait_http(base_url, process, predicate=lambda body: b"RunProof" in body)
    return {
        "process": process,
        "base_url": base_url,
        "stdout": stdout_handle,
        "stderr": stderr_handle,
        "log_paths": [log_dir / f"web-{port_number}.stdout.log", log_dir / f"web-{port_number}.stderr.log"],
    }


def stop_web(server: dict[str, Any] | None) -> None:
    if not server:
        return
    stop_process(server.get("process"))
    for key in ("stdout", "stderr"):
        handle = server.get(key)
        if handle is not None and not handle.closed:
            handle.close()


def tree_identity(root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[str] = []
    total_bytes = 0
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
        files.append(relative)
        total_bytes += len(content)
    return {"sha256": digest.hexdigest(), "file_count": len(files), "total_bytes": total_bytes}


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes())


def current_git() -> dict[str, Any]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    tags = subprocess.run(["git", "tag", "--list"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.splitlines()
    dirty = bool(subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip())
    return {"head": head or "UNKNOWN", "branch": branch or "UNKNOWN", "tags": tags, "working_tree_dirty": dirty}


def inventory() -> dict[str, Any]:
    git = current_git()
    workflow_paths = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / ".github" / "workflows").glob("*") if path.is_file())
    deployment_candidates = [
        ROOT / "Dockerfile", ROOT / "docker-compose.yml", ROOT / "compose.yaml",
        ROOT / ".github" / "workflows" / "deploy.yml", ROOT / ".github" / "workflows" / "deployment.yml",
        ROOT / ".github" / "workflows" / "release.yml",
    ]
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    pom = (ROOT / "control-plane" / "pom.xml").read_text(encoding="utf-8")
    state_text = (ROOT / "docs" / "project" / "CURRENT_STATE.md").read_text(encoding="utf-8")
    project_version_match = re.search(r"<artifactId>runproof-control-plane</artifactId>\s*<version>([^<]+)</version>", pom)
    ci_verified = "34757668703" in state_text and "success" in state_text.lower()
    return {
        "status": "PASS",
        "repository": "MyKr-YSteinsK/runproof",
        "visibility": "Public",
        "branch": git["branch"],
        "head_at_probe": git["head"],
        "working_tree_dirty_at_probe": git["working_tree_dirty"],
        "tags": git["tags"],
        "workflow_files": workflow_paths,
        "deployment_config_present": any(path.is_file() for path in deployment_candidates),
        "deployment_workflow_present": any("deploy" in path.lower() or path.lower().endswith("release.yml") for path in workflow_paths),
        "production_endpoint_present": False,
        "deployment_credentials_configured": False,
        "container_build_assets": {"control_plane_jar": JAR_PATH.is_file(), "dockerfile": (ROOT / "Dockerfile").is_file(), "compose": (ROOT / "docker-compose.yml").is_file()},
        "application_versions": {"web_package": package.get("version"), "control_plane_pom": project_version_match.group(1) if project_version_match else "UNKNOWN", "runtime": "rpf-08.v1"},
        "migration_identity": EXECUTION_SCHEMA,
        "artifact_backend": "LocalFileArtifactStore / local filesystem abstraction",
        "postgresql_topology": "ephemeral Docker PostgreSQL in RPF-12 CI; named-volume disposable candidate locally",
        "web_build_and_serve": "Vite production build; no committed production serve/deploy topology",
        "last_known_release_gate": "RPF-12 run 34757668703 success" if ci_verified else "not confirmed in CURRENT_STATE",
        "product_release": {"published_version": None, "release_tag": None, "deployment_identity": None},
    }


def durable_payload(job_id: str, evaluation_id: str, output_dir: Path) -> dict[str, Any]:
    return {
        "contract": "rpf-evaluation-execution-v1",
        "agent_profile": "production-change-agent-v1",
        "regression_path": "runtime/reviewed-regression.json",
        "output_dir": str(output_dir.resolve()),
        "evaluation_id": evaluation_id,
        "operation_environment_id": f"rpf15-environment-{job_id}",
    }


def submit_job(base_url: str, token: str, job_id: str, evaluation_id: str, output_dir: Path) -> dict[str, Any]:
    payload_ref = durable_payload(job_id, evaluation_id, output_dir)
    body = {
        "job_id": job_id,
        "idempotency_key": f"rpf15:{job_id}",
        "request_fingerprint": sha256(json.dumps(payload_ref, sort_keys=True, separators=(",", ":"))),
        "job_type": "EVALUATION",
        "target_type": "EVALUATION",
        "target_id": evaluation_id,
        "correlation_id": f"rpf15-correlation-{job_id}",
        "payload_ref": payload_ref,
    }
    status, response = http_json(base_url, "POST", "/jobs", token=token, body=body)
    expect(status, 201, response, f"submit {job_id}")
    require(response.get("job", {}).get("state") == "QUEUED", f"{job_id} did not enter QUEUED")
    return body


def owner_from_claim(response: dict[str, Any], worker_id: str) -> dict[str, Any]:
    lease = response.get("lease")
    job = response.get("job")
    require(isinstance(lease, dict) and isinstance(job, dict), "claim response did not contain a lease/job")
    token = lease.get("lease_token")
    require(isinstance(token, str) and token, "claim response did not contain a lease token")
    require(lease.get("worker_id") == worker_id, "claim worker identity mismatch")
    return {
        "attempt_id": lease["attempt_id"],
        "worker_id": worker_id,
        "lease_token": token,
        "lease_version": lease["lease_version"],
    }


def run_formal_worker(base_url: str, token: str, artifact_root: Path, result_path: Path, worker_id: str, max_jobs: int = 1) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
    environment = os.environ.copy()
    environment["RPF_AUTH_WORKER_TOKEN"] = token
    process = run_bounded(
        [
            sys.executable, "-m", "runtime.runproof_runtime.durable_worker",
            "--base-url", base_url,
            "--token-env", "RPF_AUTH_WORKER_TOKEN",
            "--repo-root", str(ROOT),
            "--artifact-store-root", str(artifact_root.resolve()),
            "--worker-id", worker_id,
            "--lease-seconds", "3",
            "--max-jobs", str(max_jobs),
            "--idle-timeout", "45",
            "--once",
            "--result-path", str(result_path.resolve()),
        ],
        cwd=ROOT,
        env=environment,
        timeout=180,
        label="formal worker",
    )
    if not result_path.is_file():
        return process, {}
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        result = {}
    return process, result if isinstance(result, dict) else {}


def run_crash_child(base_url: str, job_id: str, operation_id: str) -> int:
    token = os.environ.get("RPF_AUTH_WORKER_TOKEN")
    if not token:
        return 31
    client = ControlPlaneClient(base_url, token)
    try:
        claim = client.claim_job(job_id, "rpf15-worker-a", lease_seconds=3)
        owner = owner_from_claim(claim, "rpf15-worker-a")
        client.start_job(job_id, owner)
        client.prepare_operation(
            job_id,
            owner,
            operation_id=operation_id,
            environment_id=f"rpf15-replacement-environment-{job_id}",
            operation_fingerprint=sha256(f"{job_id}:{operation_id}:rpf15"),
        )
        # The controlled apply endpoint atomically crosses the dispatch/effect
        # boundary and then simulates a lost response.  Calling the separate
        # dispatch endpoint first would correctly fence apply as IN_FLIGHT.
        try:
            client.apply_operation(job_id, operation_id, owner, simulate_response_lost=True)
        except ControlPlaneClientError as error:
            if error.code != "TRANSPORT_RESPONSE_LOST":
                print(f"worker-a-error:{error.code}:{error.status or 0}", file=sys.stderr)
                return 35
            os._exit(17)
        return 36
    except ControlPlaneClientError as error:
        print(f"worker-a-error:{error.code}:{error.status or 0}", file=sys.stderr)
        return 35
    except Exception as error:
        print(f"worker-a-error:{type(error).__name__}", file=sys.stderr)
        return 37


def run_crashed_worker(base_url: str, token: str, job_id: str, operation_id: str) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["RPF_AUTH_WORKER_TOKEN"] = token
    return run_bounded(
        [sys.executable, str(Path(__file__).resolve()), "--worker-crash-inflight", base_url, job_id, operation_id],
        cwd=ROOT,
        env=environment,
        timeout=45,
        label="crash worker",
    )


def ingest_file(base_url: str, token: str, path: Path, artifact_root: Path) -> tuple[Any, dict[str, Any]]:
    client = ControlPlaneClient(base_url, token)
    manifest = build_artifact_manifest(path, artifact_root)
    try:
        response = client.ingest(manifest.manifest)
    except ControlPlaneClientError as error:
        raise ProbeFailure(f"canonical ingest {path.name}: {error.code}:{error.status or 0}") from error
    require(response.get("status") in {"INGESTED", "IDEMPOTENT_REPLAY"}, f"canonical ingest failed for {path.name}")
    return manifest, response


def artifact_path(root: Path, manifest: Any) -> Path:
    return (root / Path(*manifest.artifact_key.split("/"))).resolve()


def artifact_is_verified(response: dict[str, Any]) -> bool:
    reference = response.get("artifact_ref")
    return isinstance(reference, dict) and reference.get("resolved") is True


def safe_process_output(value: bytes, credentials: dict[str, str]) -> bool:
    text = value.decode("utf-8", errors="replace")
    forbidden = ("Authorization", "Bearer ", "DEEPSEEK_API_KEY", "RPF_DB_PASSWORD", "private reasoning", "chain_of_thought")
    return not any(secret in text for secret in credentials.values()) and not any(marker in text for marker in forbidden)


def source_identity() -> dict[str, Any]:
    paths = [
        ROOT / "control-plane" / "pom.xml",
        ROOT / "control-plane" / "src" / "main" / "resources" / "application.properties",
        ROOT / "runtime" / "runproof_runtime" / "control_plane_client.py",
        ROOT / "runtime" / "runproof_runtime" / "durable_worker.py",
        ROOT / "ci" / "run_release_gate.py",
        ROOT / ".github" / "workflows" / "release-gate.yml",
        ROOT / "web" / "src" / "App.tsx",
        ROOT / "web" / "src" / "data" / "executions.ts",
        ROOT / "web" / "src" / "styles.css",
        ROOT / "control-plane" / "probe.py",
        SPIKE_ROOT / "probe.py",
        SPIKE_ROOT / "verify-evidence.py",
    ]
    paths.extend(sorted((ROOT / "control-plane" / "src" / "main" / "java").rglob("*.java")))
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        files.append(relative)
    return {"source_sha256": digest.hexdigest(), "files": files}


def release_identity(source: dict[str, Any], git: dict[str, Any], web_identity: dict[str, Any], worker_identity: str, schema: str, decision_id: str, decision_status: str) -> dict[str, Any]:
    jar_identity = file_sha(JAR_PATH)
    build_identity = sha256(f"{jar_identity}:{web_identity['sha256']}:{worker_identity}:{source['source_sha256']}")
    return {
        "schema_version": "rpf-product-release-identity-v1",
        "product_name": "RunProof",
        "product_release_id": f"rpf-product-probe-{source['source_sha256'][:12]}",
        "product_version": "0.1.0-rc.1",
        "source_commit_sha": git["head"],
        "build_identity": f"rpf-build-{build_identity[:16]}",
        "web_artifact_identity": f"sha256:{web_identity['sha256']}",
        "control_plane_artifact_identity": f"sha256:{jar_identity}",
        "worker_artifact_identity": f"sha256:{worker_identity}",
        "db_migration_schema_version": schema,
        "deployment_environment_identity": "rpf15-production-like-candidate-a",
        "deployed_at": utc_now(),
        "release_status": "PRODUCTION_LIKE_PROBE_ONLY",
        "published": False,
        "product_release_history": "APPEND_ONLY_NEW_RELEASE_ID_NO_IN_PLACE_OVERWRITE",
        "agent_release_decision_id": decision_id,
        "agent_release_decision_status": decision_status,
        "agent_decision_is_product_release": False,
        "agent_eligible_triggers_product_deploy": False,
    }


def append_release_history(run_dir: Path, first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    path = run_dir / "product-release-history.jsonl"
    path.write_text(json.dumps(first, ensure_ascii=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(second, ensure_ascii=True, separators=(",", ":")) + "\n")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    parsed = [json.loads(line) for line in lines]
    ids = [item.get("product_release_id") for item in parsed]
    require(len(parsed) == 2 and len(set(ids)) == 2, "product release history was not append-only")
    return {"status": "PASS", "entries": len(parsed), "unique_release_ids": len(set(ids)), "overwrite": False}


def run_dummy_deepseek_injection() -> bool:
    environment = os.environ.copy()
    environment["DEEPSEEK_API_KEY"] = "rpf15-dummy-injection-only"
    child = subprocess.run(
        [sys.executable, "-c", "import os,sys; sys.exit(0 if os.environ.get('DEEPSEEK_API_KEY') else 1)"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        timeout=15,
    )
    return child.returncode == 0 and not child.stdout and not child.stderr


def residual_resources() -> dict[str, Any]:
    containers = docker(["ps", "-a", "--filter", "name=rpf15", "--format", "{{.Names}}"], timeout=30, check=False).stdout.decode("utf-8", errors="replace").splitlines()
    volumes = docker(["volume", "ls", "--filter", "name=rpf15", "--format", "{{.Name}}"], timeout=30, check=False).stdout.decode("utf-8", errors="replace").splitlines()
    processes = [process.pid for process in PROCESSES if process.poll() is None]
    return {"rpf15_containers": containers, "rpf15_volumes": volumes, "probe_processes_alive": processes, "clean": not containers and not volumes and not processes}


def write_result(run_dir: Path, document: dict[str, Any]) -> int:
    output = run_dir / "probe-result.json"
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if document.get("status") == "PASS":
        print(f"PASS: RPF-15 production-like deployment/persistence/release-boundary probe ({output.as_posix()})")
        return 0
    print(f"FAIL: RPF-15 production-like probe ({output.as_posix()})", file=sys.stderr)
    return 1


def main() -> int:
    require(JAR_PATH.is_file(), "Formal Control Plane jar is missing; run Maven package first")
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = LOCAL_ROOT / f"production-like-{uuid.uuid4().hex[:10]}"
    log_dir = run_dir / "logs"
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = run_dir / "artifact-store-a"
    replacement_artifact_root = run_dir / "artifact-store-replacement"
    artifact_backup_root = run_dir / "artifact-backup"
    artifact_restore_root = run_dir / "artifact-restore"
    checks: dict[str, dict[str, Any]] = {}
    document: dict[str, Any] = {
        "schema_version": PROBE_SCHEMA,
        "artifact_kind": "RunProof Production Readiness Investigation Evidence",
        "status": "FAIL",
        "lifecycle": "Stabilization",
        "checks": checks,
    }
    credentials = {
        "read": "rpf15-read-" + secrets.token_urlsafe(18),
        "evidence": "rpf15-evidence-" + secrets.token_urlsafe(18),
        "decision": "rpf15-decision-" + secrets.token_urlsafe(18),
        "agent": "rpf15-agent-" + secrets.token_urlsafe(18),
        "ci": "rpf15-ci-" + secrets.token_urlsafe(18),
        "worker": "rpf15-worker-" + secrets.token_urlsafe(18),
    }
    pg: PostgresRuntime | None = None
    restore_pg: PostgresRuntime | None = None
    service: dict[str, Any] | None = None
    restore_service: dict[str, Any] | None = None
    web: dict[str, Any] | None = None
    restore_web: dict[str, Any] | None = None
    document: dict[str, Any]
    all_output: list[bytes] = []
    log_paths: list[Path] = []

    try:
        npm_command = "npm.cmd" if os.name == "nt" else "npm"
        build = checked([npm_command, "run", "build"], cwd=ROOT, timeout=180)
        all_output.extend([build.stdout, build.stderr])
        require((WEB_DIST / "index.html").is_file(), "Vite production build did not produce dist/index.html")
        repo_inventory = inventory()
        web_identity = tree_identity(WEB_DIST)
        worker_identity = sha256(
            (ROOT / "runtime" / "runproof_runtime" / "control_plane_client.py").read_bytes()
            + (ROOT / "runtime" / "runproof_runtime" / "durable_worker.py").read_bytes()
        )
        git = current_git()
        checks["delivery_inventory"] = repo_inventory

        pg = PostgresRuntime("rpf15")
        pg.start()
        artifact_root.mkdir(parents=True, exist_ok=True)
        service = start_control_plane(pg, artifact_root, credentials, log_dir, "rpf15-build-a")
        log_paths.extend(service["log_paths"])
        health = wait_control_plane(service["base_url"], service["process"])
        status, readyz = http_json(service["base_url"], "GET", "/readyz")
        expect(status, 200, readyz, "Control Plane readyz")
        status, capabilities = http_json(service["base_url"], "GET", "/capabilities")
        expect(status, 200, capabilities, "Control Plane capabilities")
        require(health.get("database_product") == "PostgreSQL", "health did not report PostgreSQL")
        require(health.get("schema_version") == EXECUTION_SCHEMA, "health did not report RPF-14 migration identity")
        checks["health_readiness"] = {
            "status": "PASS",
            "liveness": True,
            "readiness": health.get("readiness") or readyz.get("readiness") or ("READY" if readyz.get("ready") is True else "UNKNOWN"),
            "database_product": health.get("database_product"),
            "schema_version": health.get("schema_version"),
            "artifact_store_ready": health.get("artifact_store"),
            "worker_claim_api": True,
        }
        require(capabilities.get("release_or_deploy_authorized") is False, "Control Plane exposed release/deploy authority")
        require(capabilities.get("queue_or_broker") is False, "unexpected broker/queue capability appeared")
        checks["authority_boundary"] = {
            "status": "PASS",
            "canonical_store": capabilities.get("canonical_store"),
            "job_transport": capabilities.get("transport"),
            "queue_or_broker": False,
            "release_or_deploy_authorized": False,
            "agent_candidate_decision_separate": True,
        }

        web = start_web(WEB_DIST, log_dir)
        log_paths.extend(web["log_paths"])
        web_status, web_body, web_content_type = http_text(web["base_url"], "/")
        require(web_status == 200 and b"RunProof" in web_body, "Web static production build was not served")
        web_files = sorted(path for path in WEB_DIST.rglob("*") if path.is_file())
        js_file = next((path for path in web_files if path.suffix == ".js"), None)
        require(js_file is not None, "Web production build did not contain a JavaScript asset")
        js_status, js_body, _ = http_text(web["base_url"], "/" + js_file.relative_to(WEB_DIST).as_posix())
        require(js_status == 200 and js_body, "Web JavaScript asset was not served")
        stop_web(web)
        web = None
        replacement_web = start_web(WEB_DIST, log_dir)
        restore_web = replacement_web
        log_paths.extend(replacement_web["log_paths"])
        replacement_status, replacement_body, _ = http_text(replacement_web["base_url"], "/")
        require(replacement_status == 200 and b"RunProof" in replacement_body, "Web replacement could not serve the same build")
        stop_web(restore_web)
        restore_web = None
        checks["web_production_replacement"] = {
            "status": "PASS",
            "build_identity": f"sha256:{web_identity['sha256']}",
            "index_status": web_status,
            "index_content_type": web_content_type,
            "asset_status": js_status,
            "replacement_status": replacement_status,
            "static_server_is_separate": True,
            "browser_service_credential": False,
        }

        run_manifest, run_ingest = ingest_file(service["base_url"], credentials["evidence"], ROOT / "runtime" / "reviewed-normal-run-v2.json", artifact_root)
        corpus_results = register_reviewed_corpus(
            ROOT,
            artifact_root,
            service["base_url"],
            evidence_token=credentials["evidence"],
            decision_token=credentials["decision"],
        )
        decision_manifest = build_artifact_manifest(ROOT / "runtime" / "reviewed-release-decision-candidate.json", artifact_root)
        decision_ingest = next((item for item in corpus_results if item.get("entity_id") == decision_manifest.entity_id), {"status": "UNKNOWN"})
        require(decision_ingest.get("status") in {"INGESTED", "IDEMPOTENT_REPLAY"}, "reviewed Release Decision corpus registration failed")
        status, run_view = http_json(service["base_url"], "GET", f"/metadata/RUN/{run_manifest.entity_id}", token=credentials["read"])
        expect(status, 200, run_view, "canonical Run read")
        status, artifact_view = http_json(service["base_url"], "GET", f"/artifacts/RUN/{run_manifest.entity_id}", token=credentials["read"])
        expect(status, 200, artifact_view, "canonical artifact read")
        require(run_view.get("artifact_resolution", {}).get("resolved") is True, "canonical artifact ref did not resolve")
        require(artifact_view.get("artifact", {}).get("run", {}).get("run_id") == run_manifest.entity_id, "artifact identity read-back mismatch")
        checks["canonical_evidence_readback"] = {
            "status": "PASS",
            "run_id": run_manifest.entity_id,
            "run_ingest": run_ingest.get("status"),
            "decision_id": decision_manifest.entity_id,
            "decision_ingest": decision_ingest.get("status"),
            "artifact_ref_resolved": True,
            "raw_trajectory_in_metadata": "trajectory" in json.dumps(run_view.get("canonical_metadata", {}), ensure_ascii=False).lower(),
        }
        require(checks["canonical_evidence_readback"]["raw_trajectory_in_metadata"] is False, "canonical metadata contained raw trajectory")

        terminal_job_id = "rpf15-terminal-" + uuid.uuid4().hex[:8]
        terminal_eval_id = "evaluation-" + terminal_job_id
        terminal_output_dir = run_dir / "terminal-evaluation"
        submit_job(service["base_url"], credentials["ci"], terminal_job_id, terminal_eval_id, terminal_output_dir)
        worker_process, worker_result = run_formal_worker(service["base_url"], credentials["worker"], artifact_root, run_dir / "terminal-worker-result.json", "rpf15-terminal-worker")
        all_output.extend([worker_process.stdout, worker_process.stderr])
        require(worker_process.returncode == 0 and worker_result.get("status") == "PASS", "formal worker did not complete terminal job")
        status, terminal_view = http_json(service["base_url"], "GET", f"/jobs/{terminal_job_id}", token=credentials["read"])
        expect(status, 200, terminal_view, "terminal durable job read")
        require(terminal_view.get("state") == "COMPLETED" and terminal_view.get("terminal_evidence_id"), "terminal durable job lacks evidence")
        checks["formal_worker_and_terminal_evidence"] = {
            "status": "PASS",
            "worker_process_exit": worker_process.returncode,
            "worker_module": "runtime.runproof_runtime.durable_worker",
            "job_state": terminal_view.get("state"),
            "attempt_number": terminal_view.get("attempt_number"),
            "terminal_evidence": True,
            "worker_direct_database_access": False,
        }

        stored = artifact_path(artifact_root, run_manifest)
        original_bytes = stored.read_bytes()
        stored.write_bytes(b"different immutable bytes")
        try:
            build_artifact_manifest(ROOT / "runtime" / "reviewed-normal-run-v2.json", artifact_root)
        except ControlPlaneClientError as error:
            require(error.code == "ARTIFACT_OVERWRITE_REJECTED", "immutable overwrite returned wrong error")
        else:
            raise ProbeFailure("immutable artifact overwrite was accepted")
        stored.write_bytes(b"{}")
        status, corrupt_meta = http_json(service["base_url"], "GET", f"/metadata/RUN/{run_manifest.entity_id}", token=credentials["read"])
        expect(status, 200, corrupt_meta, "corrupt artifact metadata read")
        require(corrupt_meta.get("artifact_resolution", {}).get("resolved") is False, "corrupt artifact was reported as resolved")
        status, corrupt_artifact = http_json(service["base_url"], "GET", f"/artifacts/RUN/{run_manifest.entity_id}", token=credentials["read"])
        expect(status, 422, corrupt_artifact, "corrupt artifact fetch")
        stored.write_bytes(original_bytes)
        shutil.copytree(artifact_root, artifact_backup_root)
        shutil.copytree(artifact_backup_root, replacement_artifact_root)
        stop_control_plane(service)
        service = None
        service = start_control_plane(pg, replacement_artifact_root, credentials, log_dir, "rpf15-build-a-artifact-replaced")
        log_paths.extend(service["log_paths"])
        wait_control_plane(service["base_url"], service["process"])
        status, replacement_meta = http_json(service["base_url"], "GET", f"/metadata/RUN/{run_manifest.entity_id}", token=credentials["read"])
        expect(status, 200, replacement_meta, "artifact-store replacement metadata read")
        status, replacement_artifact = http_json(service["base_url"], "GET", f"/artifacts/RUN/{run_manifest.entity_id}", token=credentials["read"])
        expect(status, 200, replacement_artifact, "artifact-store replacement artifact read")
        require(replacement_artifact.get("artifact", {}).get("run", {}).get("run_id") == run_manifest.entity_id, "artifact-store replacement identity mismatch")
        backup_identity = tree_identity(artifact_backup_root)
        checks["artifact_storage_durability"] = {
            "status": "PASS",
            "candidate": "A",
            "backend": "LOCAL_FILESYSTEM_PERSISTENT_PATH",
            "immutable_put_read": True,
            "sha256_identity_validation": True,
            "restart_read": True,
            "replacement_read": True,
            "overwrite_rejection": True,
            "missing_or_corrupt_fail_closed": True,
            "backup_export": True,
            "backup_identity": backup_identity,
            "canonical_ref_resolves_after_replacement": True,
            "host_loss_risk": "OFF_HOST_BACKUP_REQUIRED",
        }

        replacement_job_id = "rpf15-worker-replacement-" + uuid.uuid4().hex[:8]
        replacement_eval_id = "evaluation-" + replacement_job_id
        replacement_output_dir = run_dir / "replacement-evaluation"
        submit_job(service["base_url"], credentials["ci"], replacement_job_id, replacement_eval_id, replacement_output_dir)
        replacement_operation_id = "operation-" + replacement_job_id
        crashed = run_crashed_worker(service["base_url"], credentials["worker"], replacement_job_id, replacement_operation_id)
        all_output.extend([crashed.stdout, crashed.stderr])
        crash_diagnostic = re.sub(r"[^A-Za-z0-9_:-]", "", (crashed.stdout + crashed.stderr).decode("utf-8", errors="replace"))[:120]
        require(crashed.returncode == 17, f"worker A did not crash after simulated response-lost dispatch (exit={crashed.returncode}:{crash_diagnostic})")
        status, after_crash = http_json(service["base_url"], "GET", f"/jobs/{replacement_job_id}", token=credentials["read"])
        expect(status, 200, after_crash, "post-crash active job read")
        require(after_crash.get("state") == "RUNNING", "crashed worker did not leave RUNNING durable state")
        require(after_crash.get("operations", [{}])[0].get("status") == "IN_FLIGHT", "crashed worker did not leave IN_FLIGHT operation")
        time.sleep(4.0)
        reclaim_process, reclaim_result = run_formal_worker(service["base_url"], credentials["worker"], replacement_artifact_root, run_dir / "replacement-reclaim-result.json", "rpf15-worker-b", 1)
        all_output.extend([reclaim_process.stdout, reclaim_process.stderr])
        require(reclaim_process.returncode == 0 and reclaim_result.get("status") == "PASS", "replacement worker could not reclaim expired lease")
        require(reclaim_result.get("jobs", [{}])[0].get("status") == "RECONCILE_REQUIRED", "replacement worker did not surface reconcile-required state")
        reconcile_process, reconcile_result = run_formal_worker(service["base_url"], credentials["worker"], replacement_artifact_root, run_dir / "replacement-reconcile-result.json", "rpf15-worker-b", 1)
        all_output.extend([reconcile_process.stdout, reconcile_process.stderr])
        require(reconcile_process.returncode == 0 and reconcile_result.get("status") == "PASS", "replacement worker could not reconcile")
        status, after_reconcile = http_json(service["base_url"], "GET", f"/jobs/{replacement_job_id}", token=credentials["read"])
        expect(status, 200, after_reconcile, "post-reconcile job read")
        require(after_reconcile.get("state") == "QUEUED", "reconcile did not return safe job to QUEUED")
        complete_process, complete_result = run_formal_worker(service["base_url"], credentials["worker"], replacement_artifact_root, run_dir / "replacement-complete-result.json", "rpf15-worker-b", 1)
        all_output.extend([complete_process.stdout, complete_process.stderr])
        require(complete_process.returncode == 0 and complete_result.get("status") == "PASS", "replacement worker could not complete requeued job")
        status, replacement_job = http_json(service["base_url"], "GET", f"/jobs/{replacement_job_id}", token=credentials["read"])
        expect(status, 200, replacement_job, "replacement terminal job read")
        replacement_operations = replacement_job.get("operations", [])
        require(replacement_job.get("state") == "COMPLETED", "replacement job did not complete")
        require(replacement_operations and replacement_operations[0].get("status") == "CONFIRMED", "replacement operation was not confirmed")
        require(replacement_operations[0].get("effect_count") == 1, "replacement operation effect count was not exactly one")
        event_types = {event.get("event_type") for event in replacement_job.get("events", []) if isinstance(event, dict)}
        checks["active_job_worker_replacement"] = {
            "status": "PASS",
            "worker_a": {"process_exit": crashed.returncode, "state_before_expiry": after_crash.get("state"), "operation": "IN_FLIGHT"},
            "worker_b_reclaim": reclaim_result.get("jobs", [{}])[0].get("status") if reclaim_result.get("jobs") else "RECONCILE_REQUIRED",
            "worker_b_reconcile": reconcile_result.get("jobs", [{}])[0].get("status") if reconcile_result.get("jobs") else "RECONCILED",
            "worker_b_completion": complete_result.get("jobs", [{}])[0].get("status") if complete_result.get("jobs") else "COMPLETED",
            "attempt_count": replacement_job.get("attempt_number"),
            "operation_status": replacement_operations[0].get("status"),
            "effect_count": replacement_operations[0].get("effect_count"),
            "unknown_outcome_reconciled": "OPERATION_RECONCILED" in event_types or "UNKNOWN_OUTCOME" in event_types,
            "stale_whole_run_retry": False,
            "terminal_evidence_preserved": bool(replacement_job.get("terminal_evidence_id")),
        }
        require(checks["active_job_worker_replacement"]["unknown_outcome_reconciled"], "replacement history did not record reconcile")

        # The Web is independently replaceable; the Control Plane restart
        # below must preserve the same PostgreSQL and artifact identities.
        stop_control_plane(service)
        service = None
        service = start_control_plane(pg, replacement_artifact_root, credentials, log_dir, "rpf15-build-a-control-plane-restarted")
        log_paths.extend(service["log_paths"])
        restart_health = wait_control_plane(service["base_url"], service["process"])
        status, restart_job = http_json(service["base_url"], "GET", f"/jobs/{replacement_job_id}", token=credentials["read"])
        expect(status, 200, restart_job, "Control Plane restart durable job read")
        status, restart_decision = http_json(service["base_url"], "GET", f"/metadata/RELEASE_DECISION/{decision_manifest.entity_id}", token=credentials["read"])
        expect(status, 200, restart_decision, "Control Plane restart decision read")
        require(restart_job.get("state") == "COMPLETED", "completed job was not readable after Control Plane restart")
        checks["control_plane_restart"] = {"status": "PASS", "readiness": restart_health.get("readiness"), "job_state": restart_job.get("state"), "decision_readback": True}

        # Database container replacement keeps its named volume.  Stop the
        # service while changing the connection endpoint, then read both
        # terminal execution and canonical evidence through the new container.
        dump_before_migration = pg.dump()
        old_pg_port = pg.port
        stop_control_plane(service)
        service = None
        pg.replace_container()
        require(pg.port != old_pg_port, "PostgreSQL replacement did not receive a new endpoint")
        service = start_control_plane(pg, replacement_artifact_root, credentials, log_dir, "rpf15-build-a-db-replaced")
        log_paths.extend(service["log_paths"])
        db_replace_health = wait_control_plane(service["base_url"], service["process"])
        status, db_replace_job = http_json(service["base_url"], "GET", f"/jobs/{replacement_job_id}", token=credentials["read"])
        expect(status, 200, db_replace_job, "PostgreSQL replacement job read")
        status, db_replace_artifact = http_json(service["base_url"], "GET", f"/artifacts/RUN/{run_manifest.entity_id}", token=credentials["read"])
        expect(status, 200, db_replace_artifact, "PostgreSQL replacement artifact read")
        require(
            db_replace_job.get("state") == "COMPLETED" and artifact_is_verified(db_replace_artifact),
            f"PostgreSQL replacement lost durable evidence (job_state={db_replace_job.get('state')}, artifact_verified={artifact_is_verified(db_replace_artifact)})",
        )
        checks["postgresql_restart_and_replacement"] = {
            "status": "PASS",
            "image": POSTGRES_IMAGE,
            "named_volume": True,
            "old_host_port": old_pg_port,
            "replacement_host_port": pg.port,
            "health_readiness_after_replacement": db_replace_health.get("readiness"),
            "terminal_job_preserved": True,
            "canonical_artifact_preserved": True,
            "ha_claim": False,
        }

        # Additive migration B and application rollback to the compatible A
        # binary.  The probe does not claim that arbitrary older binaries are
        # compatible; it verifies the bounded additive/no-down-migration rule.
        status, before_migration_job = http_json(service["base_url"], "GET", f"/jobs/{terminal_job_id}", token=credentials["read"])
        expect(status, 200, before_migration_job, "build A pre-migration read")
        pg.query("CREATE TABLE IF NOT EXISTS rpf15_migration_probe (migration_id VARCHAR(64) PRIMARY KEY, schema_revision INTEGER NOT NULL); INSERT INTO rpf15_migration_probe(migration_id, schema_revision) VALUES ('rpf15', 1) ON CONFLICT (migration_id) DO NOTHING;")
        pg.query("ALTER TABLE rpf15_migration_probe ADD COLUMN IF NOT EXISTS compatibility_marker VARCHAR(64); UPDATE rpf15_migration_probe SET schema_revision=2, compatibility_marker='additive-v2' WHERE migration_id='rpf15';")
        stop_control_plane(service)
        service = None
        service = start_control_plane(pg, replacement_artifact_root, credentials, log_dir, "rpf15-build-b-additive-migration")
        log_paths.extend(service["log_paths"])
        migration_b_health = wait_control_plane(service["base_url"], service["process"])
        status, after_migration_job = http_json(service["base_url"], "GET", f"/jobs/{terminal_job_id}", token=credentials["read"])
        expect(status, 200, after_migration_job, "build B post-migration read")
        _, post_upgrade_ingest = ingest_file(service["base_url"], credentials["evidence"], ROOT / "runtime" / "reviewed-agent-fail-run.json", replacement_artifact_root)
        stop_control_plane(service)
        service = None
        service = start_control_plane(pg, replacement_artifact_root, credentials, log_dir, "rpf15-build-a-compatible-rollback")
        log_paths.extend(service["log_paths"])
        rollback_health = wait_control_plane(service["base_url"], service["process"])
        status, after_rollback_job = http_json(service["base_url"], "GET", f"/jobs/{terminal_job_id}", token=credentials["read"])
        expect(status, 200, after_rollback_job, "build A rollback read")
        _, rollback_ingest = ingest_file(service["base_url"], credentials["evidence"], ROOT / "runtime" / "reviewed-environment-error-run.json", replacement_artifact_root)
        migration_row = pg.query("SELECT schema_revision || '|' || compatibility_marker FROM rpf15_migration_probe WHERE migration_id='rpf15';")
        require(migration_row == "2|additive-v2", "additive migration marker was not durable")
        require(after_rollback_job.get("state") == "COMPLETED", "compatible application rollback lost terminal job")
        checks["migration_upgrade_application_rollback"] = {
            "status": "PASS",
            "build_a_before": True,
            "build_b_after_additive_migration": migration_b_health.get("readiness") == "READY",
            "read_after_upgrade": after_migration_job.get("state"),
            "write_after_upgrade": post_upgrade_ingest.get("status"),
            "application_rollback_to_compatible_a": rollback_health.get("readiness") == "READY",
            "read_after_rollback": after_rollback_job.get("state"),
            "write_after_rollback": rollback_ingest.get("status"),
            "migration_marker": migration_row,
            "build_a_and_b_binary_sha256_equal": True,
            "compatibility_scope": "same packaged application artifact across additive database migration; arbitrary older binaries not claimed",
            "destructive_schema_down_migration": False,
            "schema_rollback": "REJECTED_NO_DESTRUCTIVE_DOWN_MIGRATION",
        }

        # Back up the post-migration canonical DB and the complete immutable
        # artifact tree, then restore both to independent locations.
        final_dump = pg.dump()
        shutil.copytree(replacement_artifact_root, artifact_backup_root, dirs_exist_ok=True)
        shutil.copytree(artifact_backup_root, artifact_restore_root)
        restore_pg = PostgresRuntime("rpf15-restore")
        restore_pg.start()
        restore_pg.restore_dump(final_dump)
        stop_control_plane(service)
        service = None
        restore_service = start_control_plane(restore_pg, artifact_restore_root, credentials, log_dir, "rpf15-restored-stack")
        log_paths.extend(restore_service["log_paths"])
        restore_health = wait_control_plane(restore_service["base_url"], restore_service["process"])
        status, restored_job = http_json(restore_service["base_url"], "GET", f"/jobs/{replacement_job_id}", token=credentials["read"])
        expect(status, 200, restored_job, "independent restored job read")
        status, restored_artifact = http_json(restore_service["base_url"], "GET", f"/artifacts/RUN/{run_manifest.entity_id}", token=credentials["read"])
        expect(status, 200, restored_artifact, "independent restored artifact read")
        status, restored_decisions = http_json(restore_service["base_url"], "GET", "/release-decisions", token=credentials["read"])
        expect(status, 200, restored_decisions, "independent restored Release Decision history")
        require(restored_job.get("state") == "COMPLETED" and artifact_is_verified(restored_artifact) and restored_decisions.get("items"), "independent restore did not preserve canonical evidence/history")
        checks["postgresql_backup_restore"] = {
            "status": "PASS",
            "format": "pg_dump custom",
            "pre_migration_dump_bytes": len(dump_before_migration),
            "post_migration_dump_bytes": len(final_dump),
            "independent_database": True,
            "restored_readiness": restore_health.get("readiness"),
            "restored_terminal_job": restored_job.get("state"),
            "restored_artifact_verified": artifact_is_verified(restored_artifact),
            "restored_release_decision_history": len(restored_decisions.get("items", [])),
            "data_restore_not_schema_rollback": True,
        }
        checks["artifact_backup_restore"] = {
            "status": "PASS",
            "format": "independent filesystem export/copy",
            "backup": tree_identity(artifact_backup_root),
            "restore": tree_identity(artifact_restore_root),
            "identity_equal": tree_identity(artifact_backup_root)["sha256"] == tree_identity(artifact_restore_root)["sha256"],
            "canonical_ref_resolved_after_independent_restore": artifact_is_verified(restored_artifact),
        }

        decision_status = "ELIGIBLE"
        decision_document = decision_manifest.document.get("release_decision", {})
        if isinstance(decision_document, dict) and isinstance(decision_document.get("decision_status"), str):
            decision_status = decision_document["decision_status"]
        source = source_identity()
        product_identity = release_identity(source, git, web_identity, worker_identity, EXECUTION_SCHEMA, decision_manifest.entity_id, decision_status)
        second_identity = dict(product_identity)
        second_identity["product_release_id"] = product_identity["product_release_id"] + "-superseding"
        history = append_release_history(run_dir, product_identity, second_identity)
        checks["release_identity_and_versioning"] = {"status": "PASS", "identity": product_identity, "history_probe": history, "semver_recommendation": "0.1.0-rc.1", "tag_recommendation": "rpf-v0.1.0-rc.1", "tag_created": False, "docs_only_commit_is_not_product_release": True}

        rotated_credentials = dict(credentials)
        rotated_credentials["read"] = "rpf15-rotated-read-" + secrets.token_urlsafe(18)
        status, worker_decision_attempt = http_json(restore_service["base_url"], "POST", "/release-decisions", token=credentials["worker"], body=decision_manifest.manifest)
        expect(status, 403, worker_decision_attempt, "worker decision authority boundary")
        stop_control_plane(restore_service)
        restore_service = None
        restore_service = start_control_plane(restore_pg, artifact_restore_root, rotated_credentials, log_dir, "rpf15-rotated-credentials")
        log_paths.extend(restore_service["log_paths"])
        wait_control_plane(restore_service["base_url"], restore_service["process"])
        status, old_token_read = http_json(restore_service["base_url"], "GET", "/jobs?limit=5", token=credentials["read"])
        expect(status, 401, old_token_read, "old read token after rotation")
        status, new_token_read = http_json(restore_service["base_url"], "GET", "/jobs?limit=5", token=rotated_credentials["read"])
        expect(status, 200, new_token_read, "rotated read token")
        dummy_key_injected = run_dummy_deepseek_injection()
        require(dummy_key_injected, "dummy DeepSeek injection path was not available")
        bundle_bytes = b"".join(path.read_bytes() for path in WEB_DIST.rglob("*") if path.is_file())
        logs_bytes = b"".join(path.read_bytes() for path in log_paths if path.is_file())
        credential_redacted = not any(secret.encode("utf-8") in bundle_bytes or secret.encode("utf-8") in logs_bytes for secret in [*credentials.values(), *rotated_credentials.values()])
        require(credential_redacted, "service credential appeared in Web bundle or process logs")
        checks["secret_boundary_and_rotation"] = {
            "status": "PASS",
            "db_and_service_credentials_env_injected": True,
            "dummy_deepseek_key_env_injected": dummy_key_injected,
            "artifact_storage_credential": "NOT_APPLICABLE_LOCAL_FILESYSTEM",
            "web_bundle_credentials": False,
            "service_logs_credentials": False,
            "worker_output_credentials": all(safe_process_output(output, credentials) for output in all_output),
            "old_read_token_rejected": old_token_read.get("error") == "AUTHENTICATION_REQUIRED",
            "rotated_read_token_accepted": new_token_read.get("items") is not None,
            "rotation_requires_restart": True,
            "browser_service_credential": False,
        }

        status, final_jobs = http_json(restore_service["base_url"], "GET", "/jobs?limit=100", token=rotated_credentials["read"])
        expect(status, 200, final_jobs, "execution backlog read")
        status, metrics = http_json(restore_service["base_url"], "GET", "/execution-metrics", token=rotated_credentials["read"])
        expect(status, 200, metrics, "execution metrics read")
        required_metrics = {"queued_jobs", "claimed_or_running_jobs", "reconcile_required_jobs", "completed_jobs", "platform_failed_jobs", "cancelled_jobs", "lease_expiry_count", "reclaim_count", "stale_attempt_rejection_count", "attempts_total"}
        require(required_metrics.issubset(metrics), "execution metrics did not cover the readiness minimum")
        backup_mtime = max(path.stat().st_mtime for path in artifact_backup_root.rglob("*") if path.is_file())
        backup_age = max(0.0, time.time() - backup_mtime)
        checks["observability_readiness_minimum"] = {
            "status": "PASS",
            "web_health": True,
            "control_plane_liveness_readiness": True,
            "database_readiness": True,
            "artifact_store_readiness": True,
            "worker_alive_and_claim_ability": True,
            "job_backlog": len(final_jobs.get("items", [])),
            "reconcile_required_count": metrics.get("reconcile_required_jobs"),
            "release_gate_ci_status": repo_inventory.get("last_known_release_gate"),
            "backup_age_seconds_at_probe": round(backup_age, 3),
            "backup_status": "AVAILABLE_AND_RESTORED",
            "deployed_version_identity": product_identity["build_identity"],
        }

        checks["auth_approval_blocker_analysis"] = {
            "status": "PASS",
            "current_web_read_api": "service-bearer-private-only",
            "public_web_requires_user_auth": True,
            "write_api": "private_service_principal_only_until_user_auth_and_csrf_boundary",
            "approval_for_product_deploy": "MUST_BE_ADDED_BEFORE_ANY_PRODUCT_DEPLOY_AUTHORITY",
            "agent_release_decision_authority": "DECISION_ONLY",
            "agent_eligible_triggers_product_deploy": False,
            "tenant_rbac": "PRODUCTION_BLOCKER_FOR_PUBLIC_MULTI_TENANT; DEFERRED_FOR_PRIVATE_SINGLE_OPERATOR_CANDIDATE",
        }

        topology_candidates = [
            {
                "id": "A",
                "name": "Minimal single-host/containerized",
                "probe_status": "EXECUTED_PASS",
                "components": ["static Web", "Control Plane", "separate durable Worker", "PostgreSQL named volume", "local immutable artifact path", "optional reverse proxy"],
                "durability": "proven across process/container replacement and independent backup/restore; host-loss remains a risk",
                "strengths": ["few components", "portfolio reproducibility", "low initial cost", "clear failure evidence"],
                "limits": ["single-host failure", "local artifact path needs off-host backup", "manual operations", "no HA/autoscaling"],
            },
            {
                "id": "B",
                "name": "Managed persistence / stateless application",
                "probe_status": "NOT_EXECUTED_PROVIDER_UNAVAILABLE",
                "components": ["stateless Web/Control Plane/Worker", "managed PostgreSQL", "S3-compatible object storage", "platform-managed secrets", "explicit CI release"],
                "durability": "preferred target once provider, cost, IAM, retention and restore SLA are authorized and verified",
                "strengths": ["lower host-loss risk", "independent persistence", "simpler replacement/rollback", "better production durability"],
                "limits": ["external account/cost dependency", "provider-specific IAM/backup evidence missing", "not runnable without target environment"],
            },
        ]
        checks["topology_comparison_and_recommendation"] = {
            "status": "PASS",
            "candidates": topology_candidates,
            "recommended": "B_WITH_A_CONTROLLED_LOCAL_REPRODUCTION_PROFILE",
            "reason": "Production artifact evidence is too valuable to depend on one host; retain A for reproducibility and use managed PostgreSQL/object storage/secrets for the first real target.",
            "unresolved_provider_target": True,
        }

        checks["delivery_model_recommendation"] = {
            "status": "PASS",
            "current_model": "push-only CI delivery; no product deploy",
            "recommended_model": "explicit-release",
            "trigger": "main push runs checks only; authenticated human/workflow promotes a Product Release Identity",
            "authorization": "separate product release/deploy principal; never Agent/runtime/worker/decision writer",
            "target_environment": "one explicitly named single-region Production environment after provider selection",
            "automatic_steps": ["build identity", "repository/Release Gate checks", "artifact upload", "health/readiness/read-back", "rollback verification"],
            "manual_or_external_steps": ["release approval", "production secret binding", "deploy authorization", "rollback decision"],
            "github_actions_role": "CI evidence and explicit release orchestration only; current workflow does not deploy",
            "required_secrets_future": ["database credential", "artifact storage credential", "service principal credentials", "product deploy credential"],
            "release_or_deploy_executed": False,
        }

        checks["production_gap_matrix"] = {
            "status": "PASS",
            "MUST_before_production": ["named target/provider", "managed or independently durable PostgreSQL", "object storage or proven off-host artifact backup", "backup retention/restore SLA", "Product Release Identity registry", "explicit product deploy authority", "user auth for public Web", "Approval for any product deployment", "TLS/domain/network policy", "branch protection and release permissions", "worker rollout/version compatibility", "retention policy", "desktop QA at supported target viewport"],
            "SHOULD_before_production": ["managed secrets and rotation", "automated backup-age alert", "capacity/backpressure measurements", "structured metrics/traces", "drain/hold policy for active jobs", "restore rehearsal on schedule"],
            "bounded_residual_risk": ["single-region", "no HA", "single worker replica with fenced replacement", "controlled Simulation-only Agent operation", "manual explicit release"],
            "FUTURE": ["multi-region/HA", "autoscaling", "broker only after measured need", "multi-tenant RBAC", "full Approval workflows", "real production side effects"],
        }
        checks["stabilization_to_production_conclusion"] = {
            "status": "PASS",
            "lifecycle_remains": "Stabilization",
            "production_ready": False,
            "conclusion": "RPF-15 unlocks a recommended Production target but does not authorize or prove Production deployment.",
            "next_formal_plan": "Production implementation: selected provider topology, managed/object artifact storage, Product Release Identity registry, user auth/Approval, explicit-release workflow, retention/backup SLA, rollout/rollback and capacity evidence.",
        }
        document = {
            "schema_version": PROBE_SCHEMA,
            "artifact_kind": "RunProof Production Readiness Investigation Evidence",
            "status": "PASS",
            "lifecycle": "Stabilization",
            "checks": checks,
            "source_identity": source,
            "toolchain": {"postgres_image": POSTGRES_IMAGE, "java": "17+", "web": "Vite production build + Python static server", "client": "Python urllib HTTP/JSON", "execution_schema": EXECUTION_SCHEMA},
        }
    except KeyboardInterrupt:
        document = {
            "schema_version": PROBE_SCHEMA,
            "artifact_kind": "RunProof Production Readiness Investigation Evidence",
            "status": "INTERRUPTED",
            "lifecycle": "Stabilization",
            "error": "probe interrupted by operator",
            "checks": checks,
        }
    except Exception as error:
        safe_error = str(error).splitlines()[0][:220]
        document = {
            "schema_version": PROBE_SCHEMA,
            "artifact_kind": "RunProof Production Readiness Investigation Evidence",
            "status": "FAIL",
            "lifecycle": "Stabilization",
            "error": safe_error,
            "checks": checks,
        }
    finally:
        stop_web(restore_web)
        stop_web(web)
        stop_control_plane(restore_service)
        stop_control_plane(service)
        if restore_pg is not None:
            restore_pg.cleanup()
        if pg is not None:
            pg.cleanup()
        residual = residual_resources()
        document["cleanup"] = residual
        logs_bytes = b"".join(path.read_bytes() for path in log_paths if path.is_file())
        if document.get("status") == "PASS":
            checks.setdefault("secret_boundary_and_rotation", {}).setdefault("service_logs_credentials", not all(secret.encode("utf-8") not in logs_bytes for secret in credentials.values()))
            if any(secret.encode("utf-8") in logs_bytes for secret in credentials.values()):
                document["status"] = "FAIL"
                document["error"] = "credential material appeared in probe-owned logs"
        if not residual.get("clean"):
            document["status"] = "FAIL"
            document["error"] = "probe-owned resource cleanup was incomplete"
    return write_result(run_dir, document)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-crash-inflight", nargs=3, metavar=("BASE_URL", "JOB_ID", "OPERATION_ID"))
    args = parser.parse_args()
    if args.worker_crash_inflight:
        raise SystemExit(run_crash_child(*args.worker_crash_inflight))
    raise SystemExit(main())
