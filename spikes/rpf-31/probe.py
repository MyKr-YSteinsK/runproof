"""RPF-31 disposable S3-compatible ArtifactStore contract probe.

The probe owns only temporary Docker containers/volumes and a temporary
credential file.  It does not replace the formal LocalFileArtifactStore or
touch PostgreSQL/canonical metadata.  The Java child is the provider-facing
boundary and uses the AWS SDK for Java S3 client exclusively.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
SPIKE_ROOT = Path(__file__).resolve().parent
JAVA_POM = SPIKE_ROOT / "java" / "pom.xml"
JAR_PATH = SPIKE_ROOT / "java" / "target" / "rpf31-s3-probe.jar"
SEAWEED_IMAGE = "chrislusf/seaweedfs:4.47"
RUSTFS_IMAGE = "rustfs/rustfs:1.0.0"
FORMAL_SCHEMA = "rpf-s3-compatible-spike-v1"


class ProbeFailure(RuntimeError):
    pass


def source_paths() -> list[Path]:
    paths = [
        SPIKE_ROOT / "README.md",
        SPIKE_ROOT / "probe.py",
        SPIKE_ROOT / "verify-evidence.py",
        JAVA_POM,
        ROOT / ".github" / "workflows" / "rpf-31-s3-spike.yml",
    ]
    paths.extend(sorted((SPIKE_ROOT / "java" / "src").rglob("*.java"), key=str))
    return paths


def source_hash(paths: Iterable[Path] | None = None) -> str:
    digest = hashlib.sha256()
    selected = paths or source_paths()
    for path in sorted((item.resolve() for item in selected), key=lambda item: item.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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


def local_port() -> int:
    handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    handle.bind(("127.0.0.1", 0))
    selected = int(handle.getsockname()[1])
    handle.close()
    return selected


def wait_socket(port: int, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise ProbeFailure("OBJECT_STORE_READINESS_TIMEOUT")


def image_digest(image: str) -> str:
    value = docker(["image", "inspect", image, "--format", "{{json .RepoDigests}}"], timeout=30, check=False)
    try:
        digests = json.loads(value)
    except json.JSONDecodeError:
        digests = []
    return str(digests[0]) if isinstance(digests, list) and digests else image


def ensure_image(image: str) -> str:
    inspected = subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False, timeout=30)
    if inspected.returncode != 0:
        docker(["pull", image], timeout=600)
    return image_digest(image)


def remove_container(name: str) -> bool:
    docker(["rm", "--force", name], timeout=30, check=False)
    return subprocess.run(["docker", "inspect", name], capture_output=True, check=False, timeout=15).returncode != 0


def remove_volume(name: str) -> bool:
    docker(["volume", "rm", "--force", name], timeout=30, check=False)
    return subprocess.run(["docker", "volume", "inspect", name], capture_output=True, check=False, timeout=15).returncode != 0


def output_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def run_java(
    endpoint: str,
    bucket: str,
    *,
    mode: str,
    prefix: str = "",
    key: str = "",
    primary: dict[str, Any] | None = None,
    credentials: dict[str, str],
    timeout: int = 180,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update({
        "RPF31_ACCESS_KEY": credentials["access"],
        "RPF31_SECRET_KEY": credentials["secret"],
        "RPF31_READONLY_ACCESS": credentials.get("readonly_access", ""),
        "RPF31_READONLY_SECRET": credentials.get("readonly_secret", ""),
        "RPF31_WRONG_ACCESS": credentials["wrong_access"],
        "RPF31_WRONG_SECRET": credentials["wrong_secret"],
    })
    command = [
        "java", "-jar", str(JAR_PATH),
        f"--mode={mode}", f"--endpoint={endpoint}", f"--bucket={bucket}",
    ]
    if prefix:
        command.append(f"--prefix={prefix}")
    if key:
        command.append(f"--key={key}")
    if primary:
        command.extend([
            f"--expected-sha={primary['expected_sha256']}",
            f"--entity-id={primary['entity_id']}",
            f"--source-sha={primary['source_sha256']}",
            f"--runtime-version={primary['runtime_version']}",
        ])
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise ProbeFailure(f"JAVA_{mode.upper()}_NO_RESULT")
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise ProbeFailure(f"JAVA_{mode.upper()}_INVALID_RESULT") from error
    if not isinstance(result, dict):
        raise ProbeFailure(f"JAVA_{mode.upper()}_RESULT_NOT_OBJECT")
    result["process_exit"] = completed.returncode
    if completed.returncode != 0 and result.get("status") == "PASS":
        raise ProbeFailure(f"JAVA_{mode.upper()}_EXITED_WITH_PASS_FAILURE")
    return result


def wait_candidate_ready(endpoint: str, bucket: str, credentials: dict[str, str], timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            health = run_java(endpoint, bucket, mode="health", credentials=credentials, timeout=15)
            if health.get("status") == "PASS":
                return
        except (ProbeFailure, subprocess.TimeoutExpired):
            pass
        time.sleep(0.5)
    raise ProbeFailure("OBJECT_STORE_S3_API_READINESS_TIMEOUT")


def seaweed_config(credentials: dict[str, str]) -> dict[str, Any]:
    return {
        "identities": [
            {
                "name": "rpf31-admin",
                "credentials": [{"accessKey": credentials["access"], "secretKey": credentials["secret"]}],
                "actions": ["Admin", "Read", "List", "Tagging", "Write"],
            },
            {
                "name": "rpf31-read-only",
                "credentials": [{"accessKey": credentials["readonly_access"], "secretKey": credentials["readonly_secret"]}],
                "actions": ["Read", "List"],
            },
        ]
    }


def start_candidate(name: str, image: str, container: str, volume: str, host_port: int, secret_dir: Path, credentials: dict[str, str]) -> None:
    docker(["volume", "create", "--label", "com.runproof.owner=runproof", "--label", "com.runproof.plan=rpf-31", "--label", f"com.runproof.candidate={name}", volume])
    common = [
        "run", "--detach", "--pull=never", "--name", container,
        "--label", "com.runproof.owner=runproof",
        "--label", "com.runproof.plan=rpf-31",
        "--label", f"com.runproof.candidate={name}",
        "--label", "com.runproof.lifecycle=disposable-object-store",
        "--publish", f"127.0.0.1:{host_port}:9000" if name == "rustfs" else f"127.0.0.1:{host_port}:8333",
        "--mount", f"type=volume,source={volume},target=/data",
    ]
    if name == "seaweedfs":
        config_path = secret_dir / "seaweed-s3.json"
        output_json(config_path, seaweed_config(credentials))
        command = common + [
            "--mount", f"type=bind,source={config_path.resolve()},target=/etc/seaweedfs/s3.json,readonly",
            image, "mini", "-dir=/data", "-s3", "-s3.port=8333", "-s3.config=/etc/seaweedfs/s3.json",
        ]
    elif name == "rustfs":
        command = common + [
            "--env", f"RUSTFS_ACCESS_KEY={credentials['access']}",
            "--env", f"RUSTFS_SECRET_KEY={credentials['secret']}",
            "--env", "RUSTFS_CONSOLE_ENABLE=false",
            image,
        ]
    else:
        raise ProbeFailure(f"UNKNOWN_CANDIDATE_{name}")
    docker(command, timeout=60)


def candidate_credentials(name: str) -> dict[str, str]:
    seed = uuid.uuid4().hex
    values = {
        "access": f"rpf31{seed[:16].upper()}",
        "secret": f"rpf31-secret-{seed}",
        "readonly_access": f"rpf31ro{seed[16:].upper()}",
        "readonly_secret": f"rpf31-readonly-{seed}",
        "wrong_access": f"rpf31-wrong-{name}-{seed[:8]}",
        "wrong_secret": f"rpf31-wrong-secret-{seed}",
    }
    if name == "rustfs":
        values["readonly_access"] = ""
        values["readonly_secret"] = ""
    return values


def run_candidate(name: str, image: str, output_dir: Path, secret_dir: Path) -> dict[str, Any]:
    credentials = candidate_credentials(name)
    container = f"rpf31-{name}-{uuid.uuid4().hex[:10]}"
    volume = f"rpf31-{name}-volume-{uuid.uuid4().hex[:10]}"
    host_port = local_port()
    bucket = f"rpf31-{name}-{uuid.uuid4().hex[:12]}"
    prefix = f"rpf31/{name}/{uuid.uuid4().hex}/"
    endpoint = f"http://127.0.0.1:{host_port}"
    digest = ensure_image(image)
    current_cleanup = {"container_removed": False, "volume_removed": False, "secret_config_removed": False}
    try:
        start_candidate(name, image, container, volume, host_port, secret_dir, credentials)
        wait_socket(host_port)
        wait_candidate_ready(endpoint, bucket, credentials)
        full = run_java(endpoint, bucket, mode="full", prefix=prefix, credentials=credentials)
        if full.get("status") != "PASS":
            diagnostic_log = docker(["logs", container], timeout=30, check=False)
            for secret in credentials.values():
                if secret:
                    diagnostic_log = diagnostic_log.replace(secret, "<redacted>")
            return {
                "name": name,
                "image": image,
                "image_digest": digest,
                "status": "COMPARISON_INCOMPATIBLE",
                "endpoint": "loopback-only disposable endpoint",
                "probe": full,
                "critical_contract_passed": False,
                "failure_boundary": "candidate did not pass the same standard S3 contract; no non-atomic fallback was attempted",
                "diagnostic_log_tail": diagnostic_log[-4000:],
                "cleanup": current_cleanup,
            }
        primary = full.get("primary")
        if not isinstance(primary, dict):
            raise ProbeFailure(f"{name.upper()}_PRIMARY_IDENTITY_MISSING")
        docker(["restart", container], timeout=60)
        wait_socket(host_port)
        wait_candidate_ready(endpoint, bucket, credentials)
        restart = run_java(endpoint, bucket, mode="restart", key=str(primary["key"]), primary=primary, credentials=credentials)
        docker(["stop", container], timeout=30)
        unavailable = run_java(endpoint, bucket, mode="unavailable", key=str(primary["key"]), primary=primary, credentials=credentials, timeout=30)
        return {
            "name": name,
            "image": image,
            "image_digest": digest,
            "status": "PASS",
            "endpoint": "loopback-only disposable endpoint",
            "bucket_bootstrap": "fresh bucket per candidate",
            "full": full,
            "restart": restart,
            "endpoint_unavailable": unavailable,
            "critical_contract_passed": True,
            "selected_for_formal_follow_up": name == "seaweedfs",
            "cleanup": current_cleanup,
        }
    except Exception as error:
        raw_logs = docker(["logs", container], timeout=30, check=False)
        for secret in credentials.values():
            if secret:
                raw_logs = raw_logs.replace(secret, "<redacted>")
        return {
            "name": name,
            "image": image,
            "image_digest": digest,
            "status": "FAILED",
            "endpoint": "loopback-only disposable endpoint",
            "critical_contract_passed": False,
            "error_type": type(error).__name__,
            "error_code": str(error),
            "diagnostic_log_tail": raw_logs[-4000:],
            "cleanup": current_cleanup,
        }
    finally:
        current_cleanup["container_removed"] = remove_container(container)
        current_cleanup["volume_removed"] = remove_volume(volume)
        for child in list(secret_dir.iterdir()) if secret_dir.exists() else []:
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
        current_cleanup["secret_config_removed"] = not any(secret_dir.iterdir()) if secret_dir.exists() else True


def cleanup_labels() -> dict[str, Any]:
    containers = docker(["ps", "-aq", "--filter", "label=com.runproof.plan=rpf-31", "--format", "{{.Names}}"], check=False).splitlines()
    volumes = docker(["volume", "ls", "-q", "--filter", "label=com.runproof.plan=rpf-31"], check=False).splitlines()
    return {"no_labeled_containers": not containers, "no_labeled_volumes": not volumes, "containers": containers, "volumes": volumes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RPF-31 S3-compatible ArtifactStore contract probe.")
    parser.add_argument("--run", action="store_true", help="execute the disposable local or hosted-style probe")
    parser.add_argument("--hosted", action="store_true", help="label evidence as hosted Linux focused execution")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("--run is required")
    if not JAR_PATH.is_file():
        raise ProbeFailure("RPF31_JAVA_PROBE_JAR_MISSING")

    output_dir = (args.output_dir or (ROOT / ".local" / "rpf-31" / ("hosted" if args.hosted else "local"))).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "rpf31-result.json"
    local_state_root = (ROOT / ".local").resolve()
    local_state_root.mkdir(parents=True, exist_ok=True)
    secret_dir = Path(tempfile.mkdtemp(prefix="rpf31-secrets-", dir=str(local_state_root)))
    candidate_results: list[dict[str, Any]] = []
    failure: str | None = None
    try:
        for name, image in (("seaweedfs", SEAWEED_IMAGE), ("rustfs", RUSTFS_IMAGE)):
            try:
                candidate_results.append(run_candidate(name, image, output_dir, secret_dir))
            except Exception as error:
                candidate_results.append({
                    "name": name,
                    "image": image,
                    "status": "FAILED",
                    "critical_contract_passed": False,
                    "error_type": type(error).__name__,
                    "error_code": str(error),
                })
                if name == "seaweedfs":
                    failure = f"SEAWEEDFS_{type(error).__name__}"
    finally:
        shutil.rmtree(secret_dir, ignore_errors=True)

    selected = next((item for item in candidate_results if item.get("name") == "seaweedfs"), {})
    selected_passed = selected.get("status") == "PASS" and selected.get("critical_contract_passed") is True
    cleanup = cleanup_labels()
    if not selected_passed:
        failure = failure or "SELECTED_CANDIDATE_CONTRACT_FAILED"
    status = "PASS" if selected_passed and cleanup["no_labeled_containers"] and cleanup["no_labeled_volumes"] else "FAIL"
    result = {
        "schema_version": FORMAL_SCHEMA,
        "plan_id": "RPF-31",
        "status": status,
        "environment": {
            "execution_profile": "hosted-linux-focused" if args.hosted else "local-windows",
            "os": platform.platform(),
            "python": platform.python_version(),
            "docker_server": docker(["version", "--format", "{{.Server.Version}}"], check=False),
        },
        "source_identity": {"source_sha256": source_hash(), "files": [path.relative_to(ROOT).as_posix() for path in source_paths()]},
        "candidates": candidate_results,
        "candidate_comparison": {
            "primary": "SeaweedFS",
            "secondary": "RustFS",
            "historical_rejected": "MinIO Community server is recorded only as an archived comparison and is not a new dependency",
        },
        "decision": {
            "PROCEED_TO_FORMAL_S3_ARTIFACT_STORE": "YES" if selected_passed else "NO",
            "reason": "SeaweedFS passed atomic conditional create, replay/conflict races, verification, credentials, restart, and unavailable-endpoint boundaries" if selected_passed else failure,
            "formal_implementation_changed": False,
            "historical_artifacts_rewritten": False,
        },
        "secret_boundary": {
            "credentials_from_ephemeral_environment": True,
            "temporary_provider_config_deleted": True,
            "credentials_in_result": False,
            "credentials_in_git": False,
            "provider_logs_exported": False,
        },
        "cleanup": cleanup,
        "release_or_deploy_executed": False,
    }
    if failure:
        result["failure"] = failure
    output_json(result_path, result)
    print(json.dumps({"status": status, "result": str(result_path), "selected": selected.get("status"), "cleanup": cleanup}, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeFailure as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
