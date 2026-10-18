"""One-shot RPF-51 preflight and bounded real config-center HTTP scenario."""
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
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.effectwitness.config_http_adapter import (
    ConfigAuthorityReader, ConfigToolHost,
)
from runtime.runproof_runtime.effectwitness.config_http_contracts import (
    FrozenContracts, canonical, digest, make_contracts, sha256_bytes, strict_json,
)
from runtime.runproof_runtime.effectwitness.config_http_witness import (
    WitnessRejected, build_witness, verify_bytes,
)

TASK_ROOT = ROOT / ".local" / "rpf-51-rev2"
UPSTREAM = TASK_ROOT / "upstream-config-center"
MANIFEST_PATH = TASK_ROOT / "upstream-source-manifest.json"
PREFLIGHT_PATH = TASK_ROOT / "preflight.json"
STARTED_PATH = TASK_ROOT / "started.json"
RUN_RESULT_PATH = TASK_ROOT / "run-result.json"
FAILURE_PATH = TASK_ROOT / "run-failure.json"
WITNESS_PATH = ROOT / "spikes" / "rpf-51" / "rev-2" / "config-http-witness.json"
UPSTREAM_COMMIT = "0258b9cef02ea74a40989d035c79256c776409c0"
UPSTREAM_MANIFEST_SHA256 = "33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343"
UPSTREAM_JAR_SHA256 = "906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70"
UPSTREAM_SOURCE_FILE_COUNT = 110
UPSTREAM_SOURCE_TOTAL_BYTES = 393800
UPSTREAM_JAR_RELATIVE = "config-center-server/target/config-center-server-1.0.0.jar"
SOURCE_COPY_ACQUISITION = "COPIED_FROM_PREVIOUSLY_VERIFIED_RPF51_REV1_SOURCE_COPY_AND_JAR"
RUNPROOF_PARENT = "6753ac17ee079bf94562bfd9879bfd3c11ff74c0"
RUNPROOF_BRANCH = "codex/rpf-51-rev2-http-effect-recovery"
RUNTIME_SOURCE_FILES = (
    "runtime/runproof_runtime/effectwitness/config_http_contracts.py",
    "runtime/runproof_runtime/effectwitness/config_http_adapter.py",
    "runtime/runproof_runtime/effectwitness/config_http_oracle.py",
    "runtime/runproof_runtime/effectwitness/config_http_witness.py",
    "spikes/rpf-51/probe.py",
)
MAX_RUN_SECONDS = 1800
MAX_HTTP_REQUESTS = 12
SCENARIO_BUDGET = {"business_scenarios": 1, "http_requests": MAX_HTTP_REQUESTS,
                   "provider_requests": 0, "tokens": 0, "cost_cny": 0}


class ProbeError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write_exclusive(path: Path, raw: bytes) -> None:
    _owned_path(path)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _write_witness_once(raw: bytes) -> None:
    resolved = WITNESS_PATH.resolve()
    if (resolved != WITNESS_PATH.absolute()
            or WITNESS_PATH.parent.resolve() != (ROOT / "spikes" / "rpf-51" / "rev-2").resolve()):
        raise ProbeError("WITNESS_PATH_NOT_ALLOWLISTED")
    fd = os.open(WITNESS_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _owned_path(path: Path) -> Path:
    root = TASK_ROOT.resolve()
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents:
        raise ProbeError("TASK_PATH_OUTSIDE_RPF51_REV2")
    current = path
    while current != ROOT and current != current.parent:
        if current.is_symlink():
            raise ProbeError("TASK_PATH_SYMLINK")
        if current == TASK_ROOT:
            break
        current = current.parent
    return resolved


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, check=False)
    if result.returncode:
        raise ProbeError("RUNPROOF_GIT_IDENTITY_UNAVAILABLE")
    return result.stdout.strip()


def _source_manifest() -> tuple[dict, str]:
    raw = MANIFEST_PATH.read_bytes()
    manifest_sha256 = sha256_bytes(raw)
    if manifest_sha256 != UPSTREAM_MANIFEST_SHA256:
        raise ProbeError("SOURCE_MANIFEST_SHA256_MISMATCH")
    try:
        manifest = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        raise ProbeError("SOURCE_MANIFEST_INVALID") from None
    if (type(manifest) is not dict
            or set(manifest) != {"source_commit", "file_count", "total_bytes", "files"}
            or manifest["source_commit"] != UPSTREAM_COMMIT
            or type(manifest["files"]) is not list
            or manifest["file_count"] != len(manifest["files"])
            or len(manifest["files"]) != UPSTREAM_SOURCE_FILE_COUNT
            or manifest["total_bytes"] != UPSTREAM_SOURCE_TOTAL_BYTES):
        raise ProbeError("SOURCE_MANIFEST_IDENTITY")
    total = 0
    seen = set()
    for item in manifest["files"]:
        if type(item) is not dict or set(item) != {"path", "bytes", "sha256"}:
            raise ProbeError("SOURCE_MANIFEST_ENTRY")
        relative = PurePosixPath(item["path"].replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts or item["path"] in seen:
            raise ProbeError("SOURCE_MANIFEST_PATH")
        seen.add(item["path"])
        target = UPSTREAM.joinpath(*relative.parts)
        if target.is_symlink() or not target.is_file():
            raise ProbeError("SOURCE_FILE_MISSING_OR_LINK")
        file_raw = target.read_bytes()
        if len(file_raw) != item["bytes"] or sha256_bytes(file_raw) != item["sha256"]:
            raise ProbeError("SOURCE_FILE_DIGEST_MISMATCH")
        total += len(file_raw)
    if total != manifest["total_bytes"]:
        raise ProbeError("SOURCE_TREE_BYTE_COUNT")
    actual_files = list(UPSTREAM.rglob("*"))
    if any(path.is_symlink() for path in actual_files):
        raise ProbeError("SOURCE_TREE_SYMLINK")
    actual_relative_files = {
        path.relative_to(UPSTREAM).as_posix() for path in actual_files if path.is_file()
    }
    expected_relative_files = {
        PurePosixPath(item["path"].replace("\\", "/")).as_posix() for item in manifest["files"]
    }
    expected_copy_files = expected_relative_files | {UPSTREAM_JAR_RELATIVE}
    if actual_relative_files != expected_copy_files:
        raise ProbeError("SOURCE_TREE_UNEXPECTED_FILE")
    jar = UPSTREAM.joinpath(*PurePosixPath(UPSTREAM_JAR_RELATIVE).parts)
    if sha256_bytes(jar.read_bytes()) != UPSTREAM_JAR_SHA256:
        raise ProbeError("CONFIG_CENTER_JAR_SHA256_MISMATCH")
    return manifest, manifest_sha256


def _runtime_source_digest() -> str:
    files = {}
    for relative in RUNTIME_SOURCE_FILES:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise ProbeError("RUNTIME_SOURCE_FILE_UNAVAILABLE")
        files[relative] = sha256_bytes(path.read_bytes())
    return digest(files)


def _java_info() -> tuple[str, str]:
    java = shutil.which("java")
    if not java:
        raise ProbeError("JAVA_UNAVAILABLE")
    try:
        result = subprocess.run([java, "-version"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=10, check=False, text=True)
    except (OSError, subprocess.TimeoutExpired):
        raise ProbeError("JAVA_VERSION_PROBE_FAILED") from None
    if result.returncode != 0:
        raise ProbeError("JAVA_VERSION_PROBE_FAILED")
    match = re.search(r'version "(17(?:\.\d+){1,2}(?:\+[-A-Za-z0-9._]+)?)"', result.stdout)
    if not match:
        raise ProbeError("JAVA_17_REQUIRED")
    return java, match.group(1)


def _free_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except OSError:
        raise ProbeError("LOOPBACK_PORT_UNAVAILABLE") from None


def _build_java_args(java: str, temp_dir: Path, jar: Path, port: int,
                     app: str, env_name: str) -> list[str]:
    """Build Java argv with only the environment placeholder for the API key."""
    return [java, f"-Djava.io.tmpdir={temp_dir}", "-jar", str(jar),
            "--spring.profiles.active=local", "--server.address=127.0.0.1",
            f"--server.port={port}", "--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}",
            f"--security.api-keys[0].app={app}", f"--security.api-keys[0].env={env_name}"]


def _redacted_process_command(port: int) -> list[str]:
    return ["java", "-Djava.io.tmpdir=<task-owned-tmp>", "-jar",
            "<task-owned>/config-center-server-1.0.0.jar",
            "--spring.profiles.active=local", "--server.address=127.0.0.1",
            f"--server.port={port}", "--security.api-keys[0].key=<environment-placeholder>",
            "--security.api-keys[0].app=<synthetic>",
            "--security.api-keys[0].env=<synthetic>"]


def prepare() -> dict:
    if Path(_git("rev-parse", "--show-toplevel")).resolve() != ROOT.resolve():
        raise ProbeError("RUNPROOF_ROOT_MISMATCH")
    if _git("rev-parse", "HEAD") != RUNPROOF_PARENT:
        raise ProbeError("RUNPROOF_PARENT_MISMATCH")
    if _git("branch", "--show-current") != RUNPROOF_BRANCH:
        raise ProbeError("RUNPROOF_BRANCH_MISMATCH")
    for path in (PREFLIGHT_PATH, STARTED_PATH, RUN_RESULT_PATH, FAILURE_PATH, WITNESS_PATH):
        if path.exists():
            raise ProbeError("RPF51_REV2_ONE_SHOT_ARTIFACT_ALREADY_EXISTS")
    if not TASK_ROOT.is_dir() or not UPSTREAM.is_dir() or not MANIFEST_PATH.is_file():
        raise ProbeError("TASK_OWNED_SOURCE_COPY_UNAVAILABLE")
    manifest, manifest_sha256 = _source_manifest()
    jar = UPSTREAM.joinpath(*PurePosixPath(UPSTREAM_JAR_RELATIVE).parts)
    if not jar.is_file():
        raise ProbeError("CONFIG_CENTER_JAR_UNAVAILABLE")
    java, java_version = _java_info()
    runtime_digest = _runtime_source_digest()
    port = _free_port()
    nonce = uuid.uuid4().hex
    run_id = "rpf51-" + nonce
    effect_app = "rpf51-app-" + uuid.uuid4().hex[:12]
    effect_env = "rpf51-env-" + uuid.uuid4().hex[:12]
    effect_key = "rpf51.value." + uuid.uuid4().hex
    contracts = make_contracts(
        run_id=run_id, environment_id="env-" + run_id, execution_id="exec-" + nonce,
        app=effect_app, env=effect_env, key=effect_key, port=port,
        runproof_parent_commit=RUNPROOF_PARENT, runtime_source_sha256=runtime_digest,
        config_center_source_commit=UPSTREAM_COMMIT,
        config_center_manifest_sha256=manifest_sha256,
        config_center_jar_sha256=sha256_bytes(jar.read_bytes()), java_version=java_version,
        prepared_at_utc=_utc_now())
    contracts.validate()
    document = {"schema_version": "rpf51-rev2-preflight-v1", "contracts": contracts.document(),
                "source_copy": {"commit": UPSTREAM_COMMIT, "file_count": manifest["file_count"],
                                "total_bytes": manifest["total_bytes"],
                                "manifest_sha256": manifest_sha256,
                                "jar_bytes": 66981576, "jar_sha256": UPSTREAM_JAR_SHA256,
                                "prior_runproof_revision": "rev-1",
                                "acquisition": SOURCE_COPY_ACQUISITION},
                "java_executable": "java", "maven_version": "NOT_RUN_REUSED_REV1_JAR",
                "scenario_budget": SCENARIO_BUDGET}
    _write_exclusive(PREFLIGHT_PATH, canonical(document))
    print(json.dumps({"status": "PREFLIGHT_FROZEN", "run_id": run_id, "port": port,
                      "external_source_commit": UPSTREAM_COMMIT,
                      "contract_sha256": contracts.hashes}, sort_keys=True))
    return document


def _read_preflight() -> tuple[dict, FrozenContracts]:
    try:
        document = strict_json(PREFLIGHT_PATH.read_bytes())
    except (OSError, ValueError):
        raise ProbeError("PREFLIGHT_UNAVAILABLE") from None
    if type(document) is not dict or set(document) != {
            "schema_version", "contracts", "source_copy", "java_executable", "maven_version", "scenario_budget"}:
        raise ProbeError("PREFLIGHT_SHAPE")
    if document["schema_version"] != "rpf51-rev2-preflight-v1":
        raise ProbeError("PREFLIGHT_VERSION")
    source_copy = document["source_copy"]
    if (type(source_copy) is not dict
            or set(source_copy) != {"commit", "file_count", "total_bytes", "manifest_sha256",
                                    "jar_bytes", "jar_sha256", "prior_runproof_revision", "acquisition"}
            or source_copy != {"commit": UPSTREAM_COMMIT,
                               "file_count": UPSTREAM_SOURCE_FILE_COUNT,
                               "total_bytes": UPSTREAM_SOURCE_TOTAL_BYTES,
                               "manifest_sha256": UPSTREAM_MANIFEST_SHA256,
                               "jar_bytes": 66981576,
                               "jar_sha256": UPSTREAM_JAR_SHA256,
                               "prior_runproof_revision": "rev-1",
                               "acquisition": SOURCE_COPY_ACQUISITION}
            or document["java_executable"] != "java"
            or document["maven_version"] != "NOT_RUN_REUSED_REV1_JAR"
            or document["scenario_budget"] != SCENARIO_BUDGET):
        raise ProbeError("PREFLIGHT_SOURCE_PROVENANCE")
    try:
        contracts = FrozenContracts.from_document(document["contracts"])
    except Exception:
        raise ProbeError("PREFLIGHT_CONTRACTS") from None
    if (contracts.experiment["runproof_parent_commit"] != RUNPROOF_PARENT
            or contracts.experiment["config_center_source_commit"] != UPSTREAM_COMMIT):
        raise ProbeError("PREFLIGHT_REV2_SOURCE_IDENTITY")
    if (_git("rev-parse", "HEAD") != RUNPROOF_PARENT
            or _git("branch", "--show-current") != RUNPROOF_BRANCH
            or _runtime_source_digest() != contracts.experiment["runtime_source_sha256"]):
        raise ProbeError("FROZEN_RUNTIME_SOURCE_CHANGED")
    manifest, manifest_sha = _source_manifest()
    if (manifest_sha != contracts.experiment["config_center_manifest_sha256"]
            or manifest["source_commit"] != contracts.experiment["config_center_source_commit"]):
        raise ProbeError("FROZEN_EXTERNAL_SOURCE_CHANGED")
    jar = UPSTREAM.joinpath(*PurePosixPath(UPSTREAM_JAR_RELATIVE).parts)
    if not jar.is_file() or sha256_bytes(jar.read_bytes()) != contracts.experiment["config_center_jar_sha256"]:
        raise ProbeError("FROZEN_JAR_CHANGED")
    return document, contracts


def _netstat_rows() -> list[list[str]]:
    try:
        result = subprocess.run(["netstat.exe", "-ano", "-p", "tcp"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=10, check=False, text=True)
    except (OSError, subprocess.TimeoutExpired):
        raise ProbeError("PROCESS_SOCKET_AUDIT_UNAVAILABLE") from None
    if result.returncode != 0:
        raise ProbeError("PROCESS_SOCKET_AUDIT_UNAVAILABLE")
    return [line.split() for line in result.stdout.splitlines()
            if line.lstrip().startswith("TCP ") and len(line.split()) >= 5]


def _listener_owned(pid: int, port: int) -> bool:
    rows = _netstat_rows()
    target = str(port)
    matches = [row for row in rows if row[1].endswith(":" + target)
               and row[3].upper() == "LISTENING"]
    return (len(matches) == 1 and matches[0][1] == f"127.0.0.1:{port}"
            and matches[0][4] == str(pid))


def _external_connections(pid: int) -> list[str]:
    import ipaddress
    external = []
    for row in _netstat_rows():
        if row[4] != str(pid) or row[3].upper() == "LISTENING":
            continue
        remote = row[2]
        if remote in ("0.0.0.0:0", "[::]:0", "*:*"):
            continue
        host = remote.rsplit(":", 1)[0].strip("[]")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            external.append("NON_IP_REMOTE_CONNECTION")
            continue
        if not address.is_loopback:
            external.append("NON_LOOPBACK_CONNECTION")
    return sorted(set(external))


def _port_closed(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return False
    except OSError:
        return not any(row[1].endswith(":" + str(port)) and row[3].upper() == "LISTENING"
                       for row in _netstat_rows())


def _api_body(observation: dict, status: int, code: int):
    body = observation.get("response")
    return (observation.get("status") == status and observation.get("transport_error") is None
            and type(body) is dict and set(body) == {"code", "message", "data", "traceId"}
            and type(body["code"]) is int and body["code"] == code)


def _empty_initial(observations: list[dict]) -> bool:
    if len(observations) < 2:
        return False
    current, history = observations[0], observations[1]
    return (_api_body(current, 404, 4041) and current["response"]["data"] is None
            and _api_body(history, 200, 0) and history["response"]["data"] == [])


def _write_obs_result(observations: list[dict], kind: str) -> dict | None:
    return next((item for item in observations if item["kind"] == kind), None)


def run_once() -> dict:
    if STARTED_PATH.exists() or RUN_RESULT_PATH.exists() or FAILURE_PATH.exists() or WITNESS_PATH.exists():
        raise ProbeError("RPF51_REV2_ONE_SHOT_ALREADY_CONSUMED")
    preflight, contracts = _read_preflight()
    _owned_path(STARTED_PATH)
    started_record = {"schema_version": "rpf51-rev2-started-v1",
                      "run_id": contracts.experiment["run_id"], "started_at_utc": _utc_now(),
                      "preflight_sha256": sha256_bytes(PREFLIGHT_PATH.read_bytes())}
    _write_exclusive(STARTED_PATH, canonical(started_record))

    if WITNESS_PATH.exists():
        raise ProbeError("WITNESS_OUTPUT_ALREADY_EXISTS")
    if not _port_closed(contracts.experiment["port"]):
        raise ProbeError("FROZEN_PORT_OCCUPIED_BEFORE_START")

    app = contracts.effect["app"]
    env_name = contracts.effect["env"]
    port = contracts.experiment["port"]
    jar = UPSTREAM.joinpath(*PurePosixPath(UPSTREAM_JAR_RELATIVE).parts)
    java, actual_java_version = _java_info()
    if actual_java_version != contracts.experiment["java_version"]:
        raise ProbeError("JAVA_VERSION_CHANGED_AFTER_FREEZE")
    api_key = secrets.token_urlsafe(32)
    invalid_key = secrets.token_urlsafe(32)
    while invalid_key == api_key:
        invalid_key = secrets.token_urlsafe(32)
    log_dir = TASK_ROOT / "logs"
    temp_dir = TASK_ROOT / "tmp"
    for directory in (log_dir, temp_dir, TASK_ROOT / "runtime"):
        _owned_path(directory)
        directory.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "config-center-server.log"
    _owned_path(log_path)
    if log_path.exists():
        raise ProbeError("SERVER_LOG_ALREADY_EXISTS")

    args = _build_java_args(java, temp_dir, jar, port, app, env_name)
    process_command = _redacted_process_command(port)
    task_env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "PATH") if name in os.environ}
    task_env.update({"CONFIG_CENTER_API_KEY": api_key, "SERVER_ADDRESS": "127.0.0.1",
                     "TEMP": str(temp_dir), "TMP": str(temp_dir), "TMPDIR": str(temp_dir),
                     "HOME": str(TASK_ROOT), "USERPROFILE": str(TASK_ROOT)})

    process = None
    started_at = _utc_now()
    monotonic_start = time.monotonic()
    observations: list[dict] = []
    steps = 0
    external_connections: list[str] = []
    run_record = None
    with log_path.open("xb") as server_log:
        try:
            process = subprocess.Popen(args, cwd=UPSTREAM, env=task_env, stdin=subprocess.DEVNULL,
                                       stdout=server_log, stderr=subprocess.STDOUT,
                                       shell=False, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            steps += 1
            deadline = time.monotonic() + 90
            ready = False
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise ProbeError("OWNED_SERVICE_EXITED_BEFORE_READY")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                        if _listener_owned(process.pid, port):
                            ready = True
                            break
                except OSError:
                    time.sleep(0.2)
            if not ready:
                raise ProbeError("OWNED_LOOPBACK_SERVICE_NOT_READY")
            steps += 1
            external_connections = _external_connections(process.pid)
            if external_connections:
                raise ProbeError("UNEXPECTED_EXTERNAL_CONNECTION")

            host = ConfigToolHost(contracts, api_key, observations)
            reader = ConfigAuthorityReader(contracts, observations)

            # Step 1: prove this random namespace is empty before any write.
            reader.get_one(kind="initial_current")
            steps += 1
            reader.get_history(kind="initial_history")
            steps += 1
            if _empty_initial(observations):
                host.upsert(kind="unauthorized_write", value=contracts.effect["unauthorized_value"],
                            credential_override=invalid_key)
                steps += 1
                reader.get_one(kind="after_unauthorized_current")
                steps += 1
                reader.get_history(kind="after_unauthorized_history")
                steps += 1
                unauthorized = _write_obs_result(observations, "unauthorized_write")
                after_unauth_current = _write_obs_result(observations, "after_unauthorized_current")
                after_unauth_history = _write_obs_result(observations, "after_unauthorized_history")
                unauthorized_ok = (_api_body(unauthorized, 403, 4031)
                                   and _api_body(after_unauth_current, 404, 4041)
                                   and after_unauth_current["response"]["data"] is None
                                   and _api_body(after_unauth_history, 200, 0)
                                   and after_unauth_history["response"]["data"] == [])
                if unauthorized_ok:
                    host.upsert(kind="create_v1", value=contracts.effect["initial_value"])
                    steps += 1
                    created = _write_obs_result(observations, "create_v1")
                    created_data = created.get("response", {}).get("data") if created else None
                    if (_api_body(created, 200, 0) and type(created_data) is dict
                            and created_data.get("value") == contracts.effect["initial_value"]
                            and created_data.get("version") == 1):
                        host.upsert(kind="update_v2", value=contracts.effect["required_value"],
                                    expected_version=contracts.effect["initial_version"])
                        steps += 1
                        updated = _write_obs_result(observations, "update_v2")
                        updated_data = updated.get("response", {}).get("data") if updated else None
                        if (_api_body(updated, 200, 0) and type(updated_data) is dict
                                and updated_data.get("value") == contracts.effect["required_value"]
                                and updated_data.get("version") == 2):
                            host.upsert(kind="stale_update", value=contracts.effect["stale_value"],
                                        expected_version=contracts.effect["stale_expected_version"])
                            steps += 1
            # Final readback is the effect authority and also reconciles an uncertain POST without retry.
            if len(observations) <= MAX_HTTP_REQUESTS - 3 and any(
                    item["kind"] in ("create_v1", "update_v2", "stale_update") for item in observations):
                reader.get_one(kind="final_current")
                steps += 1
                reader.get_history(kind="final_history")
                steps += 1
                reader.list_configs()
                steps += 1
            external_connections = _external_connections(process.pid)
            if external_connections:
                raise ProbeError("UNEXPECTED_EXTERNAL_CONNECTION")
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            server_log.flush()
            os.fsync(server_log.fileno())
    steps += 1
    elapsed = time.monotonic() - monotonic_start
    if process is not None:
        port_closed = _port_closed(port)
        external_connections = _external_connections(process.pid) if process.poll() is None else []
        run_record = {
            "process_id": process.pid, "process_command": process_command,
            "process_started_at_utc": started_at, "process_stopped_at_utc": _utc_now(),
            "java_version": actual_java_version, "spring_profile": "local",
            "bind_address": "127.0.0.1", "port": port, "persistence": "in-memory-h2",
            "working_copy": "task-owned-copy",
            "config_center_source_commit": contracts.experiment["config_center_source_commit"],
            "config_center_jar_sha256": contracts.experiment["config_center_jar_sha256"],
            "readiness": "TCP_LOOPBACK_LISTENER_OWNED_PID", "shutdown": "OWNED_PID_EXITED",
            "process_exit_code": process.returncode if process.returncode is not None else -1,
            "port_closed": port_closed, "external_connections": external_connections,
            "http_request_count": len(observations), "step_count": steps,
            "elapsed_seconds": round(elapsed, 6), "provider_requests": 0, "tokens": 0,
            "cost_cny": 0, "target_agent_executed": False,
        }
        if not port_closed or process.poll() is None:
            raise ProbeError("OWNED_SERVICE_SHUTDOWN_UNVERIFIED")
        if external_connections:
            raise ProbeError("UNEXPECTED_EXTERNAL_CONNECTION")
        log_bytes = log_path.read_bytes()
        if api_key.encode("ascii") in log_bytes or invalid_key.encode("ascii") in log_bytes:
            raise ProbeError("API_KEY_FOUND_IN_SERVICE_LOG")
        witness = build_witness(contracts, run_record, observations)
        raw = canonical(witness)
        if api_key.encode("ascii") in raw or invalid_key.encode("ascii") in raw:
            raise ProbeError("API_KEY_FOUND_IN_WITNESS")
        verify_bytes(raw)
        _write_witness_once(raw)
        anchor = sha256_bytes(raw)
        result = {"schema_version": "rpf51-rev2-run-result-v1", "run_id": contracts.experiment["run_id"],
                  "source_level": witness["source_identity"]["source_level"],
                  "contract_outcome": witness["effect_result"]["contract_outcome"],
                  "witness_sha256": anchor, "http_request_count": len(observations),
                  "step_count": steps, "elapsed_seconds": run_record["elapsed_seconds"],
                  "provider_requests": 0, "tokens": 0, "cost_cny": 0,
                  "process_id": process.pid, "process_exit_code": process.returncode,
                  "port_closed": port_closed, "violated_rules": witness["effect_result"]["violated_rules"],
                  "evidence_gaps": witness["effect_result"]["evidence_gaps"]}
        _write_exclusive(RUN_RESULT_PATH, canonical(result))
        print(json.dumps({"status": "RUN_RECORDED", **result}, sort_keys=True))
        return result
    raise ProbeError("SERVICE_PROCESS_NOT_STARTED")


def _record_failure(code: str) -> None:
    if not FAILURE_PATH.exists():
        try:
            _write_exclusive(FAILURE_PATH, canonical({"schema_version": "rpf51-rev2-run-failure-v1",
                                                      "error_code": code,
                                                      "started_marker_present": STARTED_PATH.exists(),
                                                      "witness_written": WITNESS_PATH.exists()}))
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded one-shot RPF-51 config-center proof")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true",
                       help="freeze contracts after the isolated service jar is built")
    modes.add_argument("--run", action="store_true",
                       help="consume the one-shot marker and run one bounded HTTP scenario")
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            prepare()
        else:
            try:
                run_once()
            except ProbeError as exc:
                _record_failure(exc.code)
                print(f"RPF51_STOP {exc.code}", file=sys.stderr)
                return 3
        return 0
    except ProbeError as exc:
        print(f"RPF51_STOP {exc.code}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
