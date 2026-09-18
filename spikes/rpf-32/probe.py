"""Focused formal RPF-32 S3ArtifactStore integration probe.

The probe owns only disposable SeaweedFS/PostgreSQL resources, a packaged
formal Control Plane JVM and ignored local staging/output.  It never uses
production credentials, changes reviewed corpus bytes or invokes a release
operation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT = ROOT / ".local" / "rpf-32"
JAR_PATH = ROOT / "control-plane" / "target" / "runproof-control-plane-0.1.0-SNAPSHOT.jar"
BOOTSTRAP_POM = SPIKE_ROOT / "java" / "pom.xml"
BOOTSTRAP_JAR = SPIKE_ROOT / "java" / "target" / "rpf32-s3-bootstrap.jar"
PG_IMAGE = "postgres:16-alpine"
SEAWEED_IMAGE = "chrislusf/seaweedfs:4.47"
PROBE_SCHEMA = "rpf-s3-artifact-store-formal-probe-v1"


def load_control_plane_probe() -> Any:
    spec = importlib.util.spec_from_file_location("rpf_control_plane_probe", ROOT / "control-plane" / "probe.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("CONTROL_PLANE_PROBE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CP = load_control_plane_probe()


class ProbeFailure(RuntimeError):
    pass


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def local_port() -> int:
    handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    handle.bind(("127.0.0.1", 0))
    selected = int(handle.getsockname()[1])
    handle.close()
    return selected


def docker(args: list[str], *, timeout: int = 60, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise ProbeFailure(f"DOCKER_{args[0].upper()}_FAILED")
    return result.stdout.strip()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def credentials(prefix: str) -> dict[str, str]:
    seed = secrets.token_hex(12)
    return {
        "read": f"{prefix}-read-{seed}",
        "evidence": f"{prefix}-evidence-{seed}",
        "decision": f"{prefix}-decision-{seed}",
        "agent": f"{prefix}-agent-{seed}",
        "ci": f"{prefix}-ci-{seed}",
        "worker": f"{prefix}-worker-{seed}",
        "db_password": f"{prefix}-db-{seed}",
    }


def s3_credentials() -> dict[str, str]:
    seed = uuid.uuid4().hex
    return {
        "access": f"rpf32{seed[:16].upper()}",
        "secret": f"rpf32-secret-{seed}",
        "readonly_access": f"rpf32ro{seed[16:].upper()}",
        "readonly_secret": f"rpf32-readonly-{seed}",
        "wrong_access": f"rpf32-wrong-{seed[:8]}",
        "wrong_secret": f"rpf32-wrong-secret-{seed}",
    }


def wait_socket(port: int, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise ProbeFailure("OBJECT_STORE_READINESS_TIMEOUT")


def ensure_image(image: str) -> str:
    inspected = subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False, timeout=30)
    if inspected.returncode != 0:
        docker(["pull", image], timeout=600)
    digest = docker(["image", "inspect", image, "--format", "{{json .RepoDigests}}"], timeout=30, check=False)
    try:
        values = json.loads(digest)
    except json.JSONDecodeError:
        values = []
    return str(values[0]) if isinstance(values, list) and values else image


def remove_exact(name: str, kind: str) -> bool:
    if kind == "container":
        docker(["rm", "--force", name], timeout=30, check=False)
        return subprocess.run(["docker", "inspect", name], capture_output=True, check=False, timeout=15).returncode != 0
    docker(["volume", "rm", "--force", name], timeout=30, check=False)
    return subprocess.run(["docker", "volume", "inspect", name], capture_output=True, check=False, timeout=15).returncode != 0


def seaweed_config(s3: dict[str, str]) -> dict[str, Any]:
    return {
        "identities": [
            {
                "name": "rpf32-admin",
                "credentials": [{"accessKey": s3["access"], "secretKey": s3["secret"]}],
                "actions": ["Admin", "Read", "List", "Tagging", "Write"],
            },
            {
                "name": "rpf32-read-only",
                "credentials": [{"accessKey": s3["readonly_access"], "secretKey": s3["readonly_secret"]}],
                "actions": ["Read", "List"],
            },
        ]
    }


def start_object_store(
    container: str,
    volume: str,
    port: int,
    config_path: Path,
    s3: dict[str, str],
) -> None:
    docker(["volume", "create", "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-32", volume])
    write_json(config_path, seaweed_config(s3))
    docker([
        "run", "--detach", "--pull=never", "--name", container,
        "--label", "com.runproof.owner=runproof",
        "--label", "com.runproof.plan=rpf-32",
        "--label", "com.runproof.lifecycle=disposable-object-store",
        "--publish", f"127.0.0.1:{port}:8333",
        "--mount", f"type=volume,source={volume},target=/data",
        "--mount", f"type=bind,source={config_path.resolve()},target=/etc/seaweedfs/s3.json,readonly",
        SEAWEED_IMAGE, "mini", "-dir=/data", "-s3", "-s3.port=8333", "-s3.config=/etc/seaweedfs/s3.json",
    ])


def start_postgres(container: str, volume: str, port: int, service: dict[str, str]) -> None:
    docker(["volume", "create", "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-32", volume])
    docker([
        "run", "--detach", "--pull=never", "--name", container,
        "--label", "com.runproof.owner=runproof",
        "--label", "com.runproof.plan=rpf-32",
        "--label", "com.runproof.lifecycle=disposable-postgresql",
        "--env", "POSTGRES_USER=runproof",
        "--env", f"POSTGRES_PASSWORD={service['db_password']}",
        "--env", "POSTGRES_DB=runproof",
        "--publish", f"127.0.0.1:{port}:5432",
        "--mount", f"type=volume,source={volume},target=/var/lib/postgresql/data",
        PG_IMAGE,
    ])
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        ready = subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", "runproof", "-d", "runproof"],
            capture_output=True,
            check=False,
            timeout=15,
        )
        if ready.returncode == 0:
            return
        time.sleep(0.5)
    raise ProbeFailure("POSTGRES_READINESS_TIMEOUT")


def base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/api/v1"


def service_environment(
    port: int,
    pg_port: int,
    service: dict[str, str],
    s3: dict[str, str],
    *,
    s3_access: str,
    s3_secret: str,
    bucket: str,
    prefix: str,
    backend: str = "s3",
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({
        "RPF_CONTROL_PLANE_ADDRESS": "127.0.0.1",
        "RPF_CONTROL_PLANE_PORT": str(port),
        "RPF_JDBC_URL": f"jdbc:postgresql://127.0.0.1:{pg_port}/runproof",
        "RPF_DB_USER": "runproof",
        "RPF_DB_PASSWORD": service["db_password"],
        "RPF_ARTIFACT_STORE_BACKEND": backend,
        "RPF_ARTIFACT_STORE_S3_ENDPOINT": s3["endpoint"],
        "RPF_ARTIFACT_STORE_S3_REGION": "us-east-1",
        "RPF_ARTIFACT_STORE_S3_BUCKET": bucket,
        "RPF_ARTIFACT_STORE_S3_PREFIX": prefix,
        "RPF_ARTIFACT_STORE_S3_ACCESS_KEY": s3_access,
        "RPF_ARTIFACT_STORE_S3_SECRET_KEY": s3_secret,
        "RPF_ARTIFACT_STORE_S3_PATH_STYLE_ACCESS": "true",
        "RPF_ARTIFACT_STORE_S3_CONNECT_TIMEOUT_MS": "2000",
        "RPF_ARTIFACT_STORE_S3_API_TIMEOUT_MS": "5000",
        "RPF_ARTIFACT_STORE_S3_ATTEMPT_TIMEOUT_MS": "5000",
        "RPF_PROBE_ENABLED": "true",
        "RPF_AUTH_READ_TOKEN": service["read"],
        "RPF_AUTH_EVIDENCE_TOKEN": service["evidence"],
        "RPF_AUTH_DECISION_TOKEN": service["decision"],
        "RPF_AUTH_AGENT_TOKEN": service["agent"],
        "RPF_AUTH_CI_TOKEN": service["ci"],
        "RPF_AUTH_WORKER_TOKEN": service["worker"],
    })
    return environment


def start_service(
    port: int,
    pg_port: int,
    service: dict[str, str],
    s3: dict[str, str],
    *,
    s3_access: str,
    s3_secret: str,
    bucket: str,
    prefix: str,
    log_dir: Path,
    backend: str = "s3",
) -> subprocess.Popen[bytes]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = (log_dir / f"control-plane-{port}.stdout.log").open("wb")
    stderr = (log_dir / f"control-plane-{port}.stderr.log").open("wb")
    environment = service_environment(
        port, pg_port, service, s3, s3_access=s3_access, s3_secret=s3_secret,
        bucket=bucket, prefix=prefix, backend=backend,
    )
    return subprocess.Popen(
        ["java", "-jar", str(JAR_PATH)],
        cwd=ROOT,
        env=environment,
        stdout=stdout,
        stderr=stderr,
    )


def wait_service_ready(process: subprocess.Popen[bytes], url: str, timeout: float = 45.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("CONTROL_PLANE_EXITED_BEFORE_READY")
        status, body = CP.http_json(url, "GET", "/health")
        if status == 200 and body.get("ready") is True and body.get("artifact_store") == "AVAILABLE":
            return body
        time.sleep(0.25)
    raise ProbeFailure("CONTROL_PLANE_S3_READINESS_TIMEOUT")


def wait_storage_unavailable(process: subprocess.Popen[bytes], url: str, timeout: float = 15.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeFailure("CONTROL_PLANE_EXITED_DURING_STORAGE_FAILURE")
        status, body = CP.http_json(url, "GET", "/health")
        if status == 503 and body.get("artifact_store") == "UNAVAILABLE":
            return body
        time.sleep(0.25)
    raise ProbeFailure("CONTROL_PLANE_DID_NOT_FAIL_CLOSED_FOR_STORAGE")


def bootstrap_bucket(endpoint: str, bucket: str, s3: dict[str, str]) -> dict[str, Any]:
    """Pre-create only the disposable bucket; formal bytes use S3ArtifactStore."""

    if not BOOTSTRAP_JAR.is_file():
        built = subprocess.run(
            ["mvn", "-q", "package", "-f", str(BOOTSTRAP_POM)],
            cwd=ROOT,
            capture_output=True,
            timeout=180,
            check=False,
        )
        if built.returncode != 0 or not BOOTSTRAP_JAR.is_file():
            raise ProbeFailure("RPF32_BUCKET_BOOTSTRAP_BUILD_FAILED")
    environment = os.environ.copy()
    environment.update({
        "RPF32_ACCESS_KEY": s3["access"],
        "RPF32_SECRET_KEY": s3["secret"],
    })
    command = [
        "java", "-jar", str(BOOTSTRAP_JAR),
        f"--endpoint={endpoint}", f"--bucket={bucket}",
    ]
    last_result = None
    for attempt in range(12):
        last_result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        lines = [line.strip() for line in last_result.stdout.splitlines() if line.strip()]
        if last_result.returncode == 0 and lines:
            try:
                document = json.loads(lines[-1])
            except json.JSONDecodeError:
                document = None
            if isinstance(document, dict) and document.get("status") == "PASS":
                return {"status": "PASS", "provider": "SeaweedFS-4.47", "mode": "bucket bootstrap only"}
        time.sleep(0.5 if attempt < 4 else 1.0)
    if last_result is not None and last_result.returncode != 0:
        raise ProbeFailure("RPF32_BUCKET_BOOTSTRAP_FAILED")
    raise ProbeFailure("RPF32_BUCKET_BOOTSTRAP_INVALID_RESULT")


def raw_manifest(path: Path, artifact_root: Path) -> tuple[dict[str, Any], Any]:
    artifact = CP.build_artifact_manifest(path, artifact_root)
    return dict(artifact.manifest), artifact


def post_manifest(url: str, token: str, manifest: dict[str, Any], *, fail_after_write: bool = False) -> tuple[int, dict[str, Any]]:
    suffix = "?fail_after_write=true" if fail_after_write else ""
    return CP.http_json(url, "POST", f"/ingest/completed-evidence{suffix}", token=token, body=manifest)


def spawn_worker(
    url: str,
    service: dict[str, str],
    s3: dict[str, str],
    *,
    bucket: str,
    prefix: str,
    artifact_root: Path,
    output_dir: Path,
    result_path: Path,
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
    environment = service_environment(
        int(url.rsplit(":", 1)[1].split("/", 1)[0]),
        int(os.environ["RPF32_PG_PORT"]),
        service,
        s3,
        s3_access=s3["access"],
        s3_secret=s3["secret"],
        bucket=bucket,
        prefix=prefix,
    )
    environment["RPF_AUTH_WORKER_TOKEN"] = service["worker"]
    environment["RPF_ARTIFACT_STORE_BACKEND"] = "s3"
    process = subprocess.run(
        [
            sys.executable, "-m", "runtime.runproof_runtime.durable_worker",
            "--base-url", url,
            "--artifact-store-backend", "s3",
            "--worker-id", "rpf32-s3-worker",
            "--repo-root", str(ROOT),
            "--artifact-store-root", str(artifact_root),
            "--allowed-root", str(output_dir),
            "--lease-seconds", "3",
            "--max-jobs", "1",
            "--idle-timeout", "180",
            "--result-path", str(result_path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=210,
        check=False,
    )
    result_path.with_name("worker-stdout.log").write_text(process.stdout or "", encoding="utf-8", newline="\n")
    result_path.with_name("worker-stderr.log").write_text(process.stderr or "", encoding="utf-8", newline="\n")
    if not result_path.is_file():
        return process, {}
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        result = {}
    return process, result if isinstance(result, dict) else {}


def source_identity() -> dict[str, Any]:
    paths = [
        ROOT / "control-plane" / "pom.xml",
        ROOT / "control-plane" / "src" / "main" / "resources" / "application.properties",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "ArtifactStore.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "ArtifactStoreSupport.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "LocalFileArtifactStore.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "S3ArtifactStore.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "ControlPlaneController.java",
        ROOT / "control-plane" / "src" / "main" / "java" / "com" / "runproof" / "controlplane" / "CanonicalMetadataService.java",
        ROOT / "runtime" / "runproof_runtime" / "control_plane_client.py",
        ROOT / "runtime" / "runproof_runtime" / "durable_worker.py",
        SPIKE_ROOT / "probe.py",
        SPIKE_ROOT / "verify-evidence.py",
        BOOTSTRAP_POM,
        *sorted((SPIKE_ROOT / "java" / "src").rglob("*.java"), key=str),
    ]
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(paths, key=lambda candidate: candidate.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        files.append(relative)
    return {"source_sha256": digest.hexdigest(), "files": files}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the formal RPF-32 S3ArtifactStore integration probe.")
    parser.add_argument("--run", action="store_true", help="execute disposable SeaweedFS/PostgreSQL/Control Plane checks")
    parser.add_argument("--hosted", action="store_true", help="label evidence as hosted-style execution")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("--run is required")
    if not JAR_PATH.is_file():
        raise ProbeFailure("RPF32_CONTROL_PLANE_JAR_MISSING")

    output_dir = (args.output_dir or LOCAL_ROOT / ("hosted" if args.hosted else "local")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / f"run-{uuid.uuid4().hex[:10]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "rpf32-result.json"
    service = credentials("rpf32")
    readonly_service = credentials("rpf32-readonly")
    readonly_service["db_password"] = service["db_password"]
    invalid_service = credentials("rpf32-invalid")
    invalid_service["db_password"] = service["db_password"]
    s3 = s3_credentials()
    pg_container = f"rpf32-postgres-{uuid.uuid4().hex[:10]}"
    pg_volume = f"rpf32-postgres-volume-{uuid.uuid4().hex[:10]}"
    object_container = f"rpf32-seaweed-{uuid.uuid4().hex[:10]}"
    object_volume = f"rpf32-seaweed-volume-{uuid.uuid4().hex[:10]}"
    pg_port = local_port()
    object_port = local_port()
    service_port = local_port()
    readonly_port = local_port()
    invalid_port = local_port()
    object_config = run_dir / "seaweed-s3.json"
    log_dir = run_dir / "logs"
    artifact_root = run_dir / "worker-artifacts"
    worker_output = run_dir / "worker-output"
    endpoint = f"http://127.0.0.1:{object_port}"
    bucket = f"rpf32-{uuid.uuid4().hex[:12]}"
    prefix = f"rpf32/formal/{uuid.uuid4().hex}/"
    service_process: subprocess.Popen[bytes] | None = None
    readonly_process: subprocess.Popen[bytes] | None = None
    invalid_process: subprocess.Popen[bytes] | None = None
    cleanup = {
        "control_plane_stopped": False,
        "readonly_stopped": False,
        "invalid_backend_stopped": False,
        "seaweed_container_removed": False,
        "seaweed_volume_removed": False,
        "postgres_container_removed": False,
        "postgres_volume_removed": False,
        "config_removed": False,
    }
    checks: dict[str, Any] = {}
    try:
        ensure_image(PG_IMAGE)
        ensure_image(SEAWEED_IMAGE)
        start_object_store(object_container, object_volume, object_port, object_config, s3)
        wait_socket(object_port)
        s3["endpoint"] = endpoint
        checks["bucket_bootstrap"] = bootstrap_bucket(endpoint, bucket, s3)
        start_postgres(pg_container, pg_volume, pg_port, service)
        os.environ["RPF32_PG_PORT"] = str(pg_port)

        url = base_url(service_port)
        service_process = start_service(
            service_port, pg_port, service, s3,
            s3_access=s3["access"], s3_secret=s3["secret"],
            bucket=bucket, prefix=prefix, log_dir=log_dir,
        )
        checks["s3_health"] = wait_service_ready(service_process, url)

        evidence_client = CP.ControlPlaneClient(url, service["evidence"], artifact_store_backend="s3")
        read_client = CP.ControlPlaneClient(url, service["read"], artifact_store_backend="s3")
        source = ROOT / "runtime" / "reviewed-normal-run-v2.json"
        manifest, artifact = raw_manifest(source, artifact_root)
        ingested = evidence_client.ingest_file(source, artifact_root)
        entity_id = artifact.entity_id
        read_back = read_client.get("RUN", entity_id)
        if not isinstance(read_back, dict) or read_back.get("canonical_metadata", {}).get("artifact_ref", {}).get("content_sha256") != artifact.content_sha256:
            raise ProbeFailure("S3_CANONICAL_READBACK_MISMATCH")
        artifact_read_status, artifact_read = CP.http_json(url, "GET", f"/artifacts/RUN/{entity_id}", token=service["read"])
        CP.require_status(artifact_read_status, 200, artifact_read, "S3 verified artifact read")
        checks["canonical_ingest"] = {
            "status": ingested.get("status"),
            "entity_id": entity_id,
            "content_sha256": artifact.content_sha256,
            "artifact_resolution": artifact_read.get("artifact_ref", {}).get("availability"),
        }

        replay = evidence_client.ingest_file(source, artifact_root)
        if replay.get("status") not in {"IDEMPOTENT_REPLAY", "RECONCILED"}:
            raise ProbeFailure("S3_METADATA_REPLAY_NOT_IDEMPOTENT")
        checks["metadata_replay"] = {"status": replay.get("status"), "already_exists": replay.get("already_exists")}

        different_path = run_dir / "different-same-identity.json"
        different_document = json.loads(source.read_text(encoding="utf-8"))
        different_document["rpf32_probe_marker"] = "same-identity-different-bytes"
        different_path.write_text(json.dumps(different_document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        different_manifest, different_artifact = raw_manifest(different_path, artifact_root)
        evidence_client.put_artifact_bytes(different_artifact.artifact_key, different_artifact.content)
        different_status, different_response = post_manifest(url, service["evidence"], different_manifest)
        if different_status != 409 and different_response.get("error") != "IDENTITY_CONTENT_CONFLICT":
            raise ProbeFailure("S3_DIFFERENT_BYTES_DID_NOT_CONFLICT")
        checks["metadata_conflict"] = {"status": different_status, "error": different_response.get("error")}

        orphan_path = run_dir / "orphan-before-rollback.json"
        orphan_document = json.loads(source.read_text(encoding="utf-8"))
        orphan_id = f"rpf32-orphan-{uuid.uuid4().hex[:8]}"
        orphan_document["run"]["run_id"] = orphan_id
        orphan_document["rpf32_probe_marker"] = "orphan-before-metadata-rollback"
        orphan_path.write_text(json.dumps(orphan_document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        orphan_manifest, orphan_artifact = raw_manifest(orphan_path, artifact_root)
        evidence_client.put_artifact_bytes(orphan_artifact.artifact_key, orphan_artifact.content)
        rollback_status, rollback_response = post_manifest(url, service["evidence"], orphan_manifest, fail_after_write=True)
        if rollback_status != 500 or rollback_response.get("error") != "PROBE_TRANSACTION_ROLLED_BACK":
            raise ProbeFailure("S3_METADATA_ROLLBACK_BOUNDARY_MISSING")
        if read_client.get("RUN", orphan_artifact.entity_id) is not None:
            raise ProbeFailure("S3_ROLLBACK_LEFT_CANONICAL_METADATA")
        repaired = evidence_client.ingest_file(orphan_path, artifact_root)
        if repaired.get("status") not in {"INGESTED", "RECONCILED"}:
            raise ProbeFailure("S3_ORPHAN_REPLAY_NOT_REPAIRED")
        checks["orphan_and_replay"] = {
            "rollback_status": rollback_status,
            "orphan_object_present_before_replay": True,
            "replay_status": repaired.get("status"),
        }

        race_key = f"run/rpf32-race/{uuid.uuid4().hex}.json"
        same_results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(evidence_client.put_artifact_bytes, race_key, b"rpf32-same") for _ in range(2)]
            for future in futures:
                same_results.append(future.result())
        if sorted(bool(item.get("alreadyExists")) for item in same_results) != [False, True]:
            raise ProbeFailure("S3_SAME_BYTES_RACE_NOT_ATOMIC")
        different_key = f"run/rpf32-different/{uuid.uuid4().hex}.json"
        with ThreadPoolExecutor(max_workers=2) as executor:
            different_futures = [
                executor.submit(evidence_client.put_artifact_bytes, different_key, value)
                for value in (b"rpf32-a", b"rpf32-b")
            ]
            different_results: list[str] = []
            for future in different_futures:
                try:
                    different_results.append("success:" + str(future.result().get("alreadyExists")))
                except CP.ControlPlaneClientError as error:
                    different_results.append("error:" + error.code)
        if len([item for item in different_results if item.startswith("success:")]) != 1 or "error:ARTIFACT_OVERWRITE_REJECTED" not in different_results:
            raise ProbeFailure("S3_DIFFERENT_BYTES_RACE_NOT_CONFLICT")
        checks["conditional_races"] = {"same_bytes": same_results, "different_bytes": different_results}

        missing_path = run_dir / "missing-object.json"
        missing_document = json.loads(source.read_text(encoding="utf-8"))
        missing_document["run"]["run_id"] = f"rpf32-missing-{uuid.uuid4().hex[:8]}"
        missing_document["rpf32_probe_marker"] = "missing-object"
        missing_path.write_text(json.dumps(missing_document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        missing_manifest, missing_artifact = raw_manifest(missing_path, artifact_root)
        missing_status, missing_response = post_manifest(url, service["evidence"], missing_manifest)
        if missing_status != 422 or missing_response.get("error") != "INVALID_EVIDENCE_ARTIFACT_MISSING":
            raise ProbeFailure("S3_MISSING_OBJECT_NOT_FAIL_CLOSED")
        checks["missing_object"] = {"status": missing_status, "error": missing_response.get("error")}

        traversal_error = None
        try:
            evidence_client.put_artifact_bytes("../outside.json", b"unsafe")
        except CP.ControlPlaneClientError as error:
            traversal_error = error.code
        if traversal_error != "INVALID_EVIDENCE_ARTIFACT_PATH":
            raise ProbeFailure("S3_KEY_CONTAINMENT_NOT_ENFORCED")
        checks["key_containment"] = {"error": traversal_error}

        corrupt_key = f"run/rpf32-corrupt/{uuid.uuid4().hex}.json"
        corrupt_content = b"not-json"
        corrupt_id = f"rpf32-corrupt-{uuid.uuid4().hex[:8]}"
        corrupt_sha = digest_bytes(corrupt_content)
        evidence_client.put_artifact_bytes(corrupt_key, corrupt_content)
        corrupt_manifest = {
            "manifest_schema_version": "rpf-canonical-ingest-v1",
            "entity_type": "RUN",
            "entity_id": corrupt_id,
            "entity_schema_version": "rpf-run-evidence-v2",
            "outcome": "PASS",
            "idempotency_key": f"RPF32:{corrupt_id}:{corrupt_sha}",
            "source_identity": {"source_sha256": "a" * 64, "runtime_version": "rpf32-test-v1"},
            "key_refs": [],
            "summary": {"entity_id": corrupt_id, "status": "PASS"},
            "artifact_ref": {
                "artifact_id": corrupt_id,
                "artifact_key": corrupt_key,
                "artifact_kind": "Run Evidence",
                "schema_version": "rpf-run-evidence-v2",
                "content_sha256": corrupt_sha,
                "source_sha256": "a" * 64,
                "runtime_version": "rpf32-test-v1",
            },
        }
        corrupt_status, corrupt_response = post_manifest(url, service["evidence"], corrupt_manifest)
        if corrupt_status != 422 or corrupt_response.get("error") != "INVALID_EVIDENCE_ARTIFACT_JSON":
            raise ProbeFailure("S3_CORRUPT_OBJECT_NOT_FAIL_CLOSED")
        checks["corrupt_object"] = {"status": corrupt_status, "error": corrupt_response.get("error")}

        readonly_url = base_url(readonly_port)
        readonly_process = start_service(
            readonly_port, pg_port, readonly_service, s3,
            s3_access=s3["readonly_access"], s3_secret=s3["readonly_secret"],
            bucket=bucket, prefix=prefix, log_dir=log_dir,
        )
        wait_service_ready(readonly_process, readonly_url)
        readonly_client = CP.ControlPlaneClient(readonly_url, readonly_service["evidence"], artifact_store_backend="s3")
        readonly_read_status, readonly_read = CP.http_json(readonly_url, "GET", f"/artifacts/RUN/{entity_id}", token=readonly_service["read"])
        CP.require_status(readonly_read_status, 200, readonly_read, "read-only S3 verified read")
        readonly_error = None
        readonly_put_response: dict[str, Any] | None = None
        try:
            readonly_put_response = readonly_client.put_artifact_bytes(f"run/rpf32-readonly/{uuid.uuid4().hex}.json", b"read-only")
        except CP.ControlPlaneClientError as error:
            readonly_error = error.code
        if readonly_error != "ARTIFACT_STORE_ACCESS_DENIED":
            raise ProbeFailure("S3_READ_ONLY_PRINCIPAL_COULD_WRITE:" + json.dumps({
                "error": readonly_error,
                "response": readonly_put_response,
            }, ensure_ascii=False, separators=(",", ":")))
        checks["read_only_principal"] = {"read_status": readonly_read_status, "put_error": readonly_error}

        invalid_process = start_service(
            invalid_port, pg_port, invalid_service, s3,
            s3_access=s3["wrong_access"], s3_secret=s3["wrong_secret"],
            bucket=bucket, prefix=prefix, log_dir=log_dir,
        )
        invalid_health = wait_storage_unavailable(invalid_process, base_url(invalid_port))
        checks["invalid_access"] = {"artifact_store": invalid_health.get("artifact_store"), "ready": invalid_health.get("ready")}
        CP.stop_process(invalid_process)
        invalid_process = None
        cleanup["invalid_backend_stopped"] = True

        invalid_backend_process = start_service(
            invalid_port, pg_port, invalid_service, s3,
            s3_access=s3["access"], s3_secret=s3["secret"],
            bucket=bucket, prefix=prefix, log_dir=log_dir, backend="invalid",
        )
        invalid_exit = CP.wait_for_process_exit(invalid_backend_process, timeout=20)
        checks["invalid_backend"] = {"exit_code": invalid_exit, "fallback": False}
        invalid_process = None
        cleanup["invalid_backend_stopped"] = True

        docker(["stop", object_container], timeout=30)
        unavailable_health = wait_storage_unavailable(service_process, url)
        unavailable_status, unavailable_response = CP.http_json(url, "GET", f"/artifacts/RUN/{entity_id}", token=service["read"])
        if unavailable_status != 503 or unavailable_response.get("error") not in {"ARTIFACT_STORE_UNAVAILABLE", "ARTIFACT_STORE_UNKNOWN_OUTCOME"}:
            raise ProbeFailure("S3_ENDPOINT_UNAVAILABLE_NOT_CLASSIFIED")
        docker(["start", object_container], timeout=30)
        wait_socket(object_port)
        wait_service_ready(service_process, url)
        recovered_status, recovered = CP.http_json(url, "GET", f"/artifacts/RUN/{entity_id}", token=service["read"])
        CP.require_status(recovered_status, 200, recovered, "S3 restart read-back")
        checks["object_store_restart"] = {
            "unavailable_health": unavailable_health.get("artifact_store"),
            "unavailable_read_status": unavailable_status,
            "recovered_read_status": recovered_status,
        }

        docker(["restart", pg_container], timeout=60)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            ready = subprocess.run(
                ["docker", "exec", pg_container, "pg_isready", "-U", "runproof", "-d", "runproof"],
                capture_output=True, check=False, timeout=15,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise ProbeFailure("POSTGRES_RESTART_READINESS_TIMEOUT")
        wait_service_ready(service_process, url)
        postgres_recovered = read_client.get("RUN", entity_id)
        if not isinstance(postgres_recovered, dict):
            raise ProbeFailure("POSTGRES_RESTART_CANONICAL_READBACK_MISSING")
        checks["postgres_restart"] = {"canonical_readback": True}

        job_id = f"rpf32-s3-worker-{uuid.uuid4().hex[:8]}"
        payload = CP.durable_payload(job_id, profile="production-change-agent-v1", output_dir=worker_output)
        submit_status, submit_response, _ = CP.submit_durable(
            url, service["ci"], job_id,
            target_id=f"evaluation-{job_id}",
            payload_ref=payload,
        )
        if submit_status not in {201, 200} or submit_response.get("status") not in {"SUBMITTED", "IDEMPOTENT_REPLAY"}:
            raise ProbeFailure("S3_DURABLE_JOB_SUBMIT_FAILED:" + json.dumps({
                "status": submit_status,
                "error": submit_response.get("error"),
            }, ensure_ascii=False, separators=(",", ":")))
        worker_process, worker_result = spawn_worker(
            url, service, s3, bucket=bucket, prefix=prefix,
            artifact_root=artifact_root, output_dir=worker_output,
            result_path=run_dir / "worker-result.json",
        )
        worker_job_status, worker_job = CP.http_json(url, "GET", f"/jobs/{job_id}", token=service["read"])
        if worker_process.returncode != 0 or worker_result.get("status") != "PASS" or worker_job_status != 200 or worker_job.get("state") != "COMPLETED":
            raise ProbeFailure("S3_DURABLE_WORKER_NOT_COMPLETED:" + json.dumps({
                "process_returncode": worker_process.returncode,
                "worker_result": worker_result,
                "job_status": worker_job_status,
                "job_state": worker_job.get("state"),
            }, ensure_ascii=False, separators=(",", ":")))
        checks["durable_worker"] = {
            "process_exit": worker_process.returncode,
            "worker_status": worker_result.get("status"),
            "job_state": worker_job.get("state"),
            "evidence_count": len(worker_job.get("evidence", [])) if isinstance(worker_job.get("evidence"), list) else 0,
        }

        agent_upload_status = None
        agent_upload_error = None
        try:
            CP.ControlPlaneClient(url, service["agent"], artifact_store_backend="s3").put_artifact_bytes(
                "run/rpf32-authority.json", b"agent-write-must-be-denied"
            )
            agent_upload_status = 200
        except CP.ControlPlaneClientError as error:
            agent_upload_status = error.status
            agent_upload_error = error.code
        checks["authority"] = {
            "agent_upload_status": agent_upload_status,
            "agent_upload_error": agent_upload_error,
            "release_or_deploy": False,
            "canonical_metadata_store": "PostgreSQL",
            "artifact_bytes_store": "S3-compatible-SeaweedFS-4.47",
        }
        if checks["authority"]["agent_upload_status"] != 403:
            raise ProbeFailure("AGENT_ARTIFACT_WRITE_AUTHORITY_WIDENED")

        result = {
            "schema_version": PROBE_SCHEMA,
            "status": "PASS",
            "execution_mode": "hosted-style" if args.hosted else "local-disposable",
            "provider": {
                "name": "SeaweedFS",
                "version": "4.47",
                "image": SEAWEED_IMAGE,
                "endpoint": "loopback-only disposable endpoint",
                "bucket": "fresh disposable bucket",
                "prefix": "fresh disposable prefix",
            },
            "checks": checks,
            "source_identity": source_identity(),
            "history_boundary": {
                "historical_reviewed_bytes_changed": False,
                "historical_local_backend_migrated": False,
                "release_or_deploy_executed": False,
            },
            "cleanup": cleanup,
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return 0
    except Exception as error:
        result = {
            "schema_version": PROBE_SCHEMA,
            "status": "FAIL",
            "execution_mode": "hosted-style" if args.hosted else "local-disposable",
            "error_code": str(error)[:200],
            "source_identity": source_identity(),
            "cleanup": cleanup,
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return 1
    finally:
        if invalid_process is not None:
            CP.stop_process(invalid_process)
            cleanup["invalid_backend_stopped"] = True
        if readonly_process is not None:
            CP.stop_process(readonly_process)
            cleanup["readonly_stopped"] = True
        if service_process is not None:
            CP.stop_process(service_process)
            cleanup["control_plane_stopped"] = True
        cleanup["seaweed_container_removed"] = remove_exact(object_container, "container")
        cleanup["seaweed_volume_removed"] = remove_exact(object_volume, "volume")
        cleanup["postgres_container_removed"] = remove_exact(pg_container, "container")
        cleanup["postgres_volume_removed"] = remove_exact(pg_volume, "volume")
        object_config.unlink(missing_ok=True)
        cleanup["config_removed"] = not object_config.exists()
        if result_path.is_file():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                result["cleanup"] = cleanup
                result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
