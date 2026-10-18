"""One-shot RPF-51 preflight and bounded real config-center HTTP scenario."""
from __future__ import annotations

import argparse
import hashlib
import http.client
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
from runtime.runproof_runtime.effectwitness.config_http_oracle import evaluate_config_effect

TASK_ROOT = ROOT / ".local" / "rpf-51-rev3"
SOURCE_SEED_ROOT = ROOT / ".local" / "rpf-51-rev2" / "upstream-config-center"
SOURCE_SEED_MANIFEST = ROOT / ".local" / "rpf-51-rev2" / "upstream-source-manifest.json"
UPSTREAM = TASK_ROOT / "upstream-config-center"
MANIFEST_PATH = TASK_ROOT / "upstream-source-manifest.json"
DIAGNOSTIC_ROOT = TASK_ROOT / "diagnostic"
DIAGNOSTIC_INTENT_PATH = DIAGNOSTIC_ROOT / "intent.json"
DIAGNOSTIC_STARTED_PATH = DIAGNOSTIC_ROOT / "started.json"
DIAGNOSTIC_RESULT_PATH = DIAGNOSTIC_ROOT / "result.json"
DIAGNOSTIC_FAILURE_PATH = DIAGNOSTIC_ROOT / "failure.json"
DIAGNOSTIC_LOG_PATH = DIAGNOSTIC_ROOT / "config-center-server.log"
DIAGNOSTIC_READINESS_LOG = DIAGNOSTIC_ROOT / "readiness-observations.jsonl"
SCENARIO_ROOT = TASK_ROOT / "scenario"
PREFLIGHT_PATH = SCENARIO_ROOT / "preflight.json"
STARTED_PATH = SCENARIO_ROOT / "started.json"
RUN_RESULT_PATH = SCENARIO_ROOT / "run-result.json"
FAILURE_PATH = SCENARIO_ROOT / "run-failure.json"
SCENARIO_LOG_PATH = SCENARIO_ROOT / "config-center-server.log"
SCENARIO_READINESS_LOG = SCENARIO_ROOT / "readiness-observations.jsonl"
WITNESS_PATH = ROOT / "spikes" / "rpf-51" / "rev-3" / "config-http-witness.json"
READINESS_DIAGNOSTIC_PATH = ROOT / "spikes" / "rpf-51" / "rev-3" / "readiness-diagnostic.json"
REV3_ROOT = ROOT / "spikes" / "rpf-51" / "rev-3"
UPSTREAM_COMMIT = "0258b9cef02ea74a40989d035c79256c776409c0"
UPSTREAM_MANIFEST_SHA256 = "33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343"
UPSTREAM_JAR_SHA256 = "906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70"
UPSTREAM_SOURCE_FILE_COUNT = 110
UPSTREAM_SOURCE_TOTAL_BYTES = 393800
UPSTREAM_JAR_RELATIVE = "config-center-server/target/config-center-server-1.0.0.jar"
SOURCE_COPY_ACQUISITION = "COPIED_FROM_PREVIOUSLY_VERIFIED_RPF51_REV2_SOURCE_COPY_AND_JAR"
RUNPROOF_PARENT = "68ac08de12048856fe38aa7e8548ad5bb3516a9b"
RUNPROOF_BRANCH = "codex/rpf-51-rev3-readiness-http-effect"
RUNPROOF_ORIGIN_URL = "https://github.com/MyKr-YSteinsK/runproof.git"
RUNTIME_SOURCE_FILES = (
    "runtime/runproof_runtime/effectwitness/config_http_contracts.py",
    "runtime/runproof_runtime/effectwitness/config_http_adapter.py",
    "runtime/runproof_runtime/effectwitness/config_http_oracle.py",
    "runtime/runproof_runtime/effectwitness/config_http_witness.py",
    "spikes/rpf-51/probe.py",
)
MAX_RUN_SECONDS = 900
MAX_HTTP_REQUESTS = 12
MAX_STARTUP_SECONDS = 180
MAX_DIAGNOSTIC_SECONDS = 360
MAX_DIAGNOSTIC_HEALTH_GETS = 5
MAX_TOTAL_JAVA_SECONDS = 1500
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
            or WITNESS_PATH.parent.resolve() != REV3_ROOT.resolve()):
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
        raise ProbeError("TASK_PATH_OUTSIDE_RPF51_REV3")
    current = path
    while current != ROOT and current != current.parent:
        if current.is_symlink():
            raise ProbeError("TASK_PATH_SYMLINK")
        if current == TASK_ROOT:
            break
        current = current.parent
    return resolved


def _has_symlink_in_repo_path(path: Path) -> bool:
    current = path.absolute()
    while current != ROOT and ROOT in current.parents:
        if current.is_symlink():
            return True
        current = current.parent
    return False


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
    launcher = shutil.which("java")
    if not launcher:
        raise ProbeError("JAVA_UNAVAILABLE")
    try:
        result = subprocess.run([launcher, "-XshowSettings:properties", "-version"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=10, check=False, text=True)
    except (OSError, subprocess.TimeoutExpired):
        raise ProbeError("JAVA_VERSION_PROBE_FAILED") from None
    if result.returncode != 0:
        raise ProbeError("JAVA_VERSION_PROBE_FAILED")
    home_match = re.search(r"^\s*java\.home\s*=\s*(.*?)\s*$", result.stdout, re.MULTILINE)
    if not home_match:
        raise ProbeError("JAVA_HOME_UNAVAILABLE")
    java_home = Path(home_match.group(1))
    java_name = "java.exe" if os.name == "nt" else "java"
    java = java_home / "bin" / java_name
    if not java.is_file():
        raise ProbeError("JAVA_HOME_EXECUTABLE_UNAVAILABLE")
    try:
        direct_result = subprocess.run([str(java), "-version"], stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, timeout=10, check=False, text=True)
    except (OSError, subprocess.TimeoutExpired):
        raise ProbeError("JAVA_VERSION_PROBE_FAILED") from None
    if direct_result.returncode != 0:
        raise ProbeError("JAVA_VERSION_PROBE_FAILED")
    match = re.search(r'version "(17(?:\.\d+){1,2}(?:\+[-A-Za-z0-9._]+)?)"', direct_result.stdout)
    if not match:
        raise ProbeError("JAVA_17_REQUIRED")
    return str(java), match.group(1)


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


def _check_repo_identity() -> None:
    if Path(_git("rev-parse", "--show-toplevel")).resolve() != ROOT.resolve():
        raise ProbeError("RUNPROOF_ROOT_MISMATCH")
    if _git("rev-parse", "HEAD") != RUNPROOF_PARENT:
        raise ProbeError("RUNPROOF_PARENT_MISMATCH")
    if _git("branch", "--show-current") != RUNPROOF_BRANCH:
        raise ProbeError("RUNPROOF_BRANCH_MISMATCH")
    if (_git("remote", "get-url", "origin") != RUNPROOF_ORIGIN_URL
            or _git("remote", "get-url", "--push", "origin") != RUNPROOF_ORIGIN_URL):
        raise ProbeError("RUNPROOF_ORIGIN_MISMATCH")


def _copy_verified_source() -> tuple[dict, str]:
    if TASK_ROOT.exists() or TASK_ROOT.is_symlink():
        raise ProbeError("REV3_TASK_ROOT_ALREADY_EXISTS")
    if _has_symlink_in_repo_path(TASK_ROOT.parent):
        raise ProbeError("REV3_TASK_PARENT_IS_LINK")
    if (not SOURCE_SEED_ROOT.is_dir() or _has_symlink_in_repo_path(SOURCE_SEED_ROOT)
            or not SOURCE_SEED_MANIFEST.is_file()
            or _has_symlink_in_repo_path(SOURCE_SEED_MANIFEST)):
        raise ProbeError("REV2_VERIFIED_SOURCE_COPY_UNAVAILABLE")
    raw_manifest = SOURCE_SEED_MANIFEST.read_bytes()
    manifest_sha256 = sha256_bytes(raw_manifest)
    if manifest_sha256 != UPSTREAM_MANIFEST_SHA256:
        raise ProbeError("SOURCE_MANIFEST_SHA256_MISMATCH")
    try:
        manifest = json.loads(raw_manifest.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        raise ProbeError("SOURCE_MANIFEST_INVALID") from None
    if (type(manifest) is not dict
            or set(manifest) != {"source_commit", "file_count", "total_bytes", "files"}
            or manifest["source_commit"] != UPSTREAM_COMMIT
            or type(manifest["files"]) is not list
            or manifest["file_count"] != UPSTREAM_SOURCE_FILE_COUNT
            or len(manifest["files"]) != UPSTREAM_SOURCE_FILE_COUNT
            or manifest["total_bytes"] != UPSTREAM_SOURCE_TOTAL_BYTES):
        raise ProbeError("SOURCE_MANIFEST_IDENTITY")
    TASK_ROOT.mkdir()
    UPSTREAM.mkdir()
    seen: set[str] = set()
    copied_bytes = 0
    for item in manifest["files"]:
        if type(item) is not dict or set(item) != {"path", "bytes", "sha256"}:
            raise ProbeError("SOURCE_MANIFEST_ENTRY")
        relative = PurePosixPath(item["path"].replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts or item["path"] in seen:
            raise ProbeError("SOURCE_MANIFEST_PATH")
        seen.add(item["path"])
        source = SOURCE_SEED_ROOT.joinpath(*relative.parts)
        destination = UPSTREAM.joinpath(*relative.parts)
        if _has_symlink_in_repo_path(source) or not source.is_file():
            raise ProbeError("SOURCE_FILE_MISSING_OR_LINK")
        file_raw = source.read_bytes()
        if len(file_raw) != item["bytes"] or sha256_bytes(file_raw) != item["sha256"]:
            raise ProbeError("SOURCE_FILE_DIGEST_MISMATCH")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(file_raw)
        copied_bytes += len(file_raw)
    jar_relative = PurePosixPath(UPSTREAM_JAR_RELATIVE)
    source_jar = SOURCE_SEED_ROOT.joinpath(*jar_relative.parts)
    destination_jar = UPSTREAM.joinpath(*jar_relative.parts)
    if _has_symlink_in_repo_path(source_jar) or not source_jar.is_file():
        raise ProbeError("CONFIG_CENTER_JAR_UNAVAILABLE")
    jar_raw = source_jar.read_bytes()
    if sha256_bytes(jar_raw) != UPSTREAM_JAR_SHA256 or len(jar_raw) != 66981576:
        raise ProbeError("CONFIG_CENTER_JAR_SHA256_MISMATCH")
    destination_jar.parent.mkdir(parents=True, exist_ok=True)
    destination_jar.write_bytes(jar_raw)
    MANIFEST_PATH.write_bytes(raw_manifest)
    verified_manifest, verified_sha = _source_manifest()
    if copied_bytes != UPSTREAM_SOURCE_TOTAL_BYTES or verified_sha != manifest_sha256:
        raise ProbeError("SOURCE_COPY_VERIFICATION_FAILED")
    return verified_manifest, verified_sha


def prepare_diagnostic() -> dict:
    _check_repo_identity()
    if (READINESS_DIAGNOSTIC_PATH.exists() or DIAGNOSTIC_INTENT_PATH.exists()
            or DIAGNOSTIC_STARTED_PATH.exists() or DIAGNOSTIC_RESULT_PATH.exists()
            or DIAGNOSTIC_FAILURE_PATH.exists() or WITNESS_PATH.exists()):
        raise ProbeError("REV3_DIAGNOSTIC_ONE_SHOT_ARTIFACT_ALREADY_EXISTS")
    java, java_version = _java_info()
    runtime_digest = _runtime_source_digest()
    port = _free_port()
    if not _port_closed(port):
        raise ProbeError("DIAGNOSTIC_PORT_OCCUPIED_BEFORE_FREEZE")
    manifest, manifest_sha256 = _copy_verified_source()
    DIAGNOSTIC_ROOT.mkdir()
    nonce = uuid.uuid4().hex
    intent = {
        "schema_version": "rpf51-rev3-diagnostic-intent-v1",
        "diagnostic_id": "rpf51-diag-" + nonce,
        "runproof_parent_commit": RUNPROOF_PARENT,
        "runproof_branch": RUNPROOF_BRANCH,
        "runtime_source_sha256": runtime_digest,
        "config_center_source_commit": UPSTREAM_COMMIT,
        "config_center_source_manifest_sha256": manifest_sha256,
        "config_center_source_file_count": manifest["file_count"],
        "config_center_source_bytes": manifest["total_bytes"],
        "config_center_jar_sha256": UPSTREAM_JAR_SHA256,
        "config_center_jar_bytes": 66981576,
        "java_version": java_version,
        "spring_profile": "local",
        "persistence": "in-memory-h2",
        "bind_address": "127.0.0.1",
        "port": port,
        "health_method": "GET",
        "health_path": "/actuator/health",
        "max_health_gets": MAX_DIAGNOSTIC_HEALTH_GETS,
        "business_http_requests": 0,
        "provider_requests": 0,
        "tokens": 0,
        "cost_cny": 0,
        "prepared_at_utc": _utc_now(),
    }
    _write_exclusive(DIAGNOSTIC_INTENT_PATH, canonical(intent))
    print(json.dumps({"status": "DIAGNOSTIC_INTENT_FROZEN",
                      "diagnostic_id": intent["diagnostic_id"], "port": port,
                      "config_center_source_commit": UPSTREAM_COMMIT,
                      "source_manifest_sha256": manifest_sha256,
                      "jar_sha256": UPSTREAM_JAR_SHA256,
                      "runtime_source_sha256": runtime_digest}, sort_keys=True))
    return intent


def _read_diagnostic_result() -> dict:
    try:
        result = strict_json(DIAGNOSTIC_RESULT_PATH.read_bytes())
    except (OSError, ValueError):
        raise ProbeError("DIAGNOSTIC_RESULT_UNAVAILABLE") from None
    if (type(result) is not dict or result.get("schema_version") != "rpf51-rev3-diagnostic-result-v1"
            or result.get("status") != "PASS" or result.get("ready") is not True
            or result.get("business_http_request_count") != 0
            or result.get("process_exit_code") is None or result.get("process_stopped") is not True
            or result.get("process_id", 0) <= 0 or result.get("port_closed") is not True
            or result.get("external_connections") != []
            or not 1 <= result.get("health_get_count", 0) <= MAX_DIAGNOSTIC_HEALTH_GETS
            or result.get("runtime_source_sha256") != _runtime_source_digest()
            or result.get("runproof_parent_commit") != RUNPROOF_PARENT
            or result.get("config_center_source_manifest_sha256") != UPSTREAM_MANIFEST_SHA256
            or result.get("config_center_jar_sha256") != UPSTREAM_JAR_SHA256
            or result.get("java_version") is None
            or not DIAGNOSTIC_STARTED_PATH.is_file()):
        raise ProbeError("DIAGNOSTIC_NOT_PASS")
    try:
        tracked = strict_json(READINESS_DIAGNOSTIC_PATH.read_bytes())
    except (OSError, ValueError):
        raise ProbeError("READINESS_DIAGNOSTIC_UNAVAILABLE") from None
    if (type(tracked) is not dict
            or tracked.get("schema_version") != "rpf51-rev3-readiness-diagnostic-v1"
            or tracked.get("status") != "PASS"
            or tracked.get("diagnostic_result_sha256") != sha256_bytes(DIAGNOSTIC_RESULT_PATH.read_bytes())):
        raise ProbeError("READINESS_DIAGNOSTIC_MISMATCH")
    return result


def prepare_scenario() -> dict:
    _check_repo_identity()
    diagnostic = _read_diagnostic_result()
    if (PREFLIGHT_PATH.exists() or STARTED_PATH.exists() or RUN_RESULT_PATH.exists()
            or FAILURE_PATH.exists() or WITNESS_PATH.exists()):
        raise ProbeError("REV3_SCENARIO_ONE_SHOT_ARTIFACT_ALREADY_EXISTS")
    manifest, manifest_sha256 = _source_manifest()
    jar = UPSTREAM.joinpath(*PurePosixPath(UPSTREAM_JAR_RELATIVE).parts)
    if not jar.is_file():
        raise ProbeError("CONFIG_CENTER_JAR_UNAVAILABLE")
    java, java_version = _java_info()
    if java_version != diagnostic["java_version"]:
        raise ProbeError("JAVA_VERSION_CHANGED_AFTER_DIAGNOSTIC")
    runtime_digest = _runtime_source_digest()
    diagnostic_port = diagnostic["port"]
    port = _free_port()
    attempts = 0
    while port == diagnostic_port and attempts < 20:
        port = _free_port()
        attempts += 1
    if port == diagnostic_port or not _port_closed(port):
        raise ProbeError("SCENARIO_PORT_NOT_FRESH")
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
    SCENARIO_ROOT.mkdir()
    document = {"schema_version": "rpf51-rev3-scenario-preflight-v1",
                "diagnostic_result_sha256": sha256_bytes(DIAGNOSTIC_RESULT_PATH.read_bytes()),
                "diagnostic_elapsed_seconds": diagnostic["elapsed_seconds"],
                "max_diagnostic_seconds": MAX_DIAGNOSTIC_SECONDS,
                "max_scenario_seconds": MAX_RUN_SECONDS,
                "max_total_java_seconds": MAX_TOTAL_JAVA_SECONDS,
                "contracts": contracts.document(),
                "source_copy": {"commit": UPSTREAM_COMMIT, "file_count": manifest["file_count"],
                                "total_bytes": manifest["total_bytes"],
                                "manifest_sha256": manifest_sha256,
                                "jar_bytes": 66981576, "jar_sha256": UPSTREAM_JAR_SHA256,
                                "prior_runproof_revision": "rev-2",
                                "acquisition": SOURCE_COPY_ACQUISITION},
                "java_executable": "java", "maven_version": "NOT_RUN_REUSED_REV2_JAR",
                "scenario_budget": SCENARIO_BUDGET}
    _write_exclusive(PREFLIGHT_PATH, canonical(document))
    print(json.dumps({"status": "SCENARIO_PREFLIGHT_FROZEN", "run_id": run_id, "port": port,
                      "external_source_commit": UPSTREAM_COMMIT,
                      "contract_sha256": contracts.hashes}, sort_keys=True))
    return document


def _read_preflight() -> tuple[dict, FrozenContracts]:
    try:
        document = strict_json(PREFLIGHT_PATH.read_bytes())
    except (OSError, ValueError):
        raise ProbeError("PREFLIGHT_UNAVAILABLE") from None
    if type(document) is not dict or set(document) != {
            "schema_version", "diagnostic_result_sha256", "diagnostic_elapsed_seconds",
            "max_diagnostic_seconds", "max_scenario_seconds", "max_total_java_seconds",
            "contracts", "source_copy", "java_executable", "maven_version", "scenario_budget"}:
        raise ProbeError("PREFLIGHT_SHAPE")
    if document["schema_version"] != "rpf51-rev3-scenario-preflight-v1":
        raise ProbeError("PREFLIGHT_VERSION")
    diagnostic = _read_diagnostic_result()
    if document["diagnostic_result_sha256"] != sha256_bytes(DIAGNOSTIC_RESULT_PATH.read_bytes()):
        raise ProbeError("DIAGNOSTIC_RESULT_CHANGED_AFTER_FREEZE")
    if (document["diagnostic_elapsed_seconds"] != diagnostic["elapsed_seconds"]
            or document["max_diagnostic_seconds"] != MAX_DIAGNOSTIC_SECONDS
            or document["max_scenario_seconds"] != MAX_RUN_SECONDS
            or document["max_total_java_seconds"] != MAX_TOTAL_JAVA_SECONDS):
        raise ProbeError("JAVA_RUNTIME_BUDGET_CHANGED_AFTER_FREEZE")
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
                               "prior_runproof_revision": "rev-2",
                               "acquisition": SOURCE_COPY_ACQUISITION}
            or document["java_executable"] != "java"
            or document["maven_version"] != "NOT_RUN_REUSED_REV2_JAR"
            or document["scenario_budget"] != SCENARIO_BUDGET):
        raise ProbeError("PREFLIGHT_SOURCE_PROVENANCE")
    try:
        contracts = FrozenContracts.from_document(document["contracts"])
    except Exception:
        raise ProbeError("PREFLIGHT_CONTRACTS") from None
    if diagnostic["port"] == contracts.experiment["port"]:
        raise ProbeError("DIAGNOSTIC_SCENARIO_PORT_REUSED")
    if (contracts.experiment["runproof_parent_commit"] != RUNPROOF_PARENT
            or contracts.experiment["config_center_source_commit"] != UPSTREAM_COMMIT):
        raise ProbeError("PREFLIGHT_REV3_SOURCE_IDENTITY")
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


def parse_netstat_output(output: str) -> tuple[list[dict], int]:
    """Parse complete Windows TCP rows; malformed rows never prove ownership."""
    rows: list[dict] = []
    malformed = 0
    for line in output.splitlines():
        parts = line.split()
        if not parts or parts[0].upper() != "TCP":
            continue
        if len(parts) < 5 or not parts[-1].isdigit():
            malformed += 1
            continue
        rows.append({"protocol": "TCP", "local": parts[1], "remote": parts[2],
                     "state": parts[-2].upper(), "pid": int(parts[-1])})
    return rows, malformed


def _netstat_rows() -> tuple[list[dict], int]:
    try:
        result = subprocess.run(["netstat.exe", "-ano", "-p", "tcp"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=10, check=False, text=True)
    except (OSError, subprocess.TimeoutExpired):
        raise ProbeError("PROCESS_SOCKET_AUDIT_UNAVAILABLE") from None
    if result.returncode != 0:
        raise ProbeError("PROCESS_SOCKET_AUDIT_UNAVAILABLE")
    return parse_netstat_output(result.stdout)


def _endpoint_port(endpoint: str) -> int | None:
    suffix = endpoint.rsplit(":", 1)[-1]
    return int(suffix) if suffix.isdigit() else None


def _listener_status(rows: list[dict], malformed: int, pid: int, port: int) -> tuple[bool, str]:
    listeners = [row for row in rows if row["state"] == "LISTENING"
                 and _endpoint_port(row["local"]) == port]
    if len(listeners) > 1:
        return False, "MULTIPLE_PORT_LISTENERS"
    if not listeners:
        return False, "NETSTAT_OUTPUT_INCOMPLETE" if malformed else "OWNED_LISTENER_NOT_VISIBLE"
    row = listeners[0]
    if row["local"] != f"127.0.0.1:{port}":
        return False, "LISTENER_NOT_EXACT_LOOPBACK"
    if row["pid"] != pid:
        return False, "LISTENER_PID_MISMATCH"
    if malformed:
        return False, "NETSTAT_OUTPUT_INCOMPLETE"
    return True, "OWNED_LOOPBACK_LISTENER"


def _listener_owned(pid: int, port: int) -> bool:
    rows, malformed = _netstat_rows()
    return _listener_status(rows, malformed, pid, port)[0]


def _external_connections(pid: int, allowed_port: int) -> list[str]:
    import ipaddress
    external = []
    rows, malformed = _netstat_rows()
    for row in rows:
        if row["pid"] != pid:
            continue
        if row["state"] == "LISTENING":
            if row["local"] != f"127.0.0.1:{allowed_port}":
                external.append("NON_LOOPBACK_OR_UNEXPECTED_LISTENER")
            continue
        remote = row["remote"]
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
    if malformed:
        external.append("NETSTAT_OUTPUT_INCOMPLETE")
    return sorted(set(external))


def _port_closed(port: int) -> bool:
    rows, malformed = _netstat_rows()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return False
    except OSError:
        return malformed == 0 and not any(
            row["state"] == "LISTENING" and _endpoint_port(row["local"]) == port
            for row in rows)


def _tcp_connect(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.35):
            return True
    except OSError:
        return False


def _health_get(port: int) -> tuple[int | None, bool, str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", "/actuator/health", headers={"Accept": "application/json"})
        response = connection.getresponse()
        raw = response.read(4097)
        if len(raw) > 4096:
            return response.status, False, "HEALTH_BODY_TOO_LARGE"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            return response.status, False, "HEALTH_BODY_INVALID"
        if response.status != 200:
            return response.status, False, "HEALTH_HTTP_STATUS_NOT_200"
        if type(body) is not dict or body.get("status") != "UP":
            return response.status, False, "HEALTH_STATUS_NOT_UP"
        return response.status, True, "HEALTH_UP"
    except (OSError, http.client.HTTPException, TimeoutError):
        return None, False, "HEALTH_TRANSPORT_ERROR"
    finally:
        connection.close()


def _readiness(process: subprocess.Popen, port: int, *, log_path: Path,
               timeout_seconds: int = MAX_STARTUP_SECONDS,
               max_health_gets: int = MAX_DIAGNOSTIC_HEALTH_GETS) -> dict:
    if timeout_seconds < 1 or timeout_seconds > MAX_STARTUP_SECONDS:
        raise ProbeError("READINESS_TIMEOUT_OUT_OF_BOUNDS")
    started = time.monotonic()
    deadline = started + timeout_seconds
    health_gets = 0
    polls = 0
    category_counts: dict[str, int] = {}
    first_samples: list[dict] = []
    last_samples: list[dict] = []
    last_failure = "READINESS_PENDING"
    ready = False
    with log_path.open("xb") as poll_log:
        while time.monotonic() < deadline:
            polls += 1
            process_running = process.poll() is None
            tcp_ok = _tcp_connect(port) if process_running else False
            rows, malformed = _netstat_rows()
            owned, ownership_category = _listener_status(rows, malformed, process.pid, port)
            http_status = None
            http_health = None
            category = "PROCESS_EXITED" if not process_running else "TCP_CONNECT_FAILED"
            if process_running and tcp_ok:
                category = ownership_category if not owned else "HEALTH_GET_NOT_ATTEMPTED"
            if process_running and tcp_ok and owned:
                if health_gets >= max_health_gets:
                    category = "HEALTH_GET_BUDGET_EXHAUSTED"
                else:
                    health_gets += 1
                    http_status, http_health, category = _health_get(port)
                    rows_after, malformed_after = _netstat_rows()
                    owned_after, _ = _listener_status(rows_after, malformed_after,
                                                       process.pid, port)
                    identity_stable = process.poll() is None and owned_after
                    if http_health and not identity_stable:
                        http_health = False
                        category = "OWNED_SERVICE_IDENTITY_CHANGED"
                    elif http_health:
                        ready = True
                        category = "READY_OWNED_PID_AND_HEALTH_UP"
                    elif not owned_after:
                        category = "OWNED_LISTENER_CHANGED_AFTER_HEALTH"
            sample = {
                "poll": polls,
                "process_running": process_running,
                "tcp_connect": tcp_ok,
                "owned_listener": owned,
                "http_health": http_health,
                "http_status": http_status,
                "pid_match": bool(owned and process.pid > 0),
                "monotonic_elapsed": round(time.monotonic() - started, 4),
                "last_failure_category": category,
            }
            poll_log.write(canonical(sample) + b"\n")
            poll_log.flush()
            category_counts[category] = category_counts.get(category, 0) + 1
            if len(first_samples) < 3:
                first_samples.append(sample)
            last_samples.append(sample)
            if len(last_samples) > 5:
                last_samples.pop(0)
            last_failure = category
            if (ready or not process_running
                    or category in ("HEALTH_GET_BUDGET_EXHAUSTED",
                                    "OWNED_SERVICE_IDENTITY_CHANGED")):
                break
            remaining = deadline - time.monotonic()
            if remaining > 0:
                delay = min(1.0, 0.2 * (1.5 ** min(polls - 1, 4)))
                time.sleep(min(remaining, delay))
    return {"ready": ready, "failure_category": None if ready else last_failure,
            "poll_count": polls, "health_get_count": health_gets,
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "category_counts": category_counts, "first_samples": first_samples,
            "last_samples": last_samples}


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


def _task_environment(api_key: str, scope_root: Path, temp_dir: Path) -> dict[str, str]:
    task_env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "PATH")
                if name in os.environ}
    task_env.update({"CONFIG_CENTER_API_KEY": api_key, "SERVER_ADDRESS": "127.0.0.1",
                     "TEMP": str(temp_dir), "TMP": str(temp_dir), "TMPDIR": str(temp_dir),
                     "HOME": str(scope_root), "USERPROFILE": str(scope_root)})
    return task_env


def _stop_owned_process(process: subprocess.Popen) -> bool:
    """Stop only the Popen handle created by this invocation and confirm its exit."""
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
    return process.poll() is not None


def _write_tracked_once(path: Path, raw: bytes) -> None:
    if path.parent.resolve() != REV3_ROOT.resolve() or path.resolve() != path.absolute():
        raise ProbeError("REV3_TRACKED_PATH_NOT_ALLOWLISTED")
    if path.exists():
        raise ProbeError("REV3_TRACKED_EVIDENCE_ALREADY_EXISTS")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _read_diagnostic_intent() -> dict:
    try:
        intent = strict_json(DIAGNOSTIC_INTENT_PATH.read_bytes())
    except (OSError, ValueError):
        raise ProbeError("DIAGNOSTIC_INTENT_UNAVAILABLE") from None
    expected_fields = {
        "schema_version", "diagnostic_id", "runproof_parent_commit", "runproof_branch",
        "runtime_source_sha256", "config_center_source_commit",
        "config_center_source_manifest_sha256", "config_center_source_file_count",
        "config_center_source_bytes", "config_center_jar_sha256", "config_center_jar_bytes",
        "java_version", "spring_profile", "persistence", "bind_address", "port",
        "health_method", "health_path", "max_health_gets", "business_http_requests",
        "provider_requests", "tokens", "cost_cny", "prepared_at_utc",
    }
    if type(intent) is not dict or set(intent) != expected_fields:
        raise ProbeError("DIAGNOSTIC_INTENT_SHAPE")
    if (intent["schema_version"] != "rpf51-rev3-diagnostic-intent-v1"
            or intent["runproof_parent_commit"] != RUNPROOF_PARENT
            or intent["runproof_branch"] != RUNPROOF_BRANCH
            or intent["runtime_source_sha256"] != _runtime_source_digest()
            or intent["config_center_source_commit"] != UPSTREAM_COMMIT
            or intent["config_center_source_manifest_sha256"] != UPSTREAM_MANIFEST_SHA256
            or intent["config_center_source_file_count"] != UPSTREAM_SOURCE_FILE_COUNT
            or intent["config_center_source_bytes"] != UPSTREAM_SOURCE_TOTAL_BYTES
            or intent["config_center_jar_sha256"] != UPSTREAM_JAR_SHA256
            or intent["config_center_jar_bytes"] != 66981576
            or intent["spring_profile"] != "local" or intent["persistence"] != "in-memory-h2"
            or intent["bind_address"] != "127.0.0.1"
            or intent["health_method"] != "GET" or intent["health_path"] != "/actuator/health"
            or intent["max_health_gets"] != MAX_DIAGNOSTIC_HEALTH_GETS
            or intent["business_http_requests"] != 0
            or intent["provider_requests"] != 0 or intent["tokens"] != 0
            or intent["cost_cny"] != 0):
        raise ProbeError("DIAGNOSTIC_INTENT_IDENTITY")
    if type(intent["port"]) is not int or not 1 <= intent["port"] <= 65535:
        raise ProbeError("DIAGNOSTIC_INTENT_PORT")
    return intent


def run_diagnostic_once() -> dict:
    _check_repo_identity()
    if (DIAGNOSTIC_STARTED_PATH.exists() or DIAGNOSTIC_RESULT_PATH.exists()
            or DIAGNOSTIC_FAILURE_PATH.exists() or READINESS_DIAGNOSTIC_PATH.exists()):
        raise ProbeError("REV3_DIAGNOSTIC_ONE_SHOT_ALREADY_CONSUMED")
    intent = _read_diagnostic_intent()
    manifest, manifest_sha = _source_manifest()
    if manifest_sha != intent["config_center_source_manifest_sha256"]:
        raise ProbeError("DIAGNOSTIC_SOURCE_CHANGED")
    jar = UPSTREAM.joinpath(*PurePosixPath(UPSTREAM_JAR_RELATIVE).parts)
    java, java_version = _java_info()
    if java_version != intent["java_version"]:
        raise ProbeError("JAVA_VERSION_CHANGED_AFTER_DIAGNOSTIC_FREEZE")
    if not _port_closed(intent["port"]):
        raise ProbeError("DIAGNOSTIC_PORT_OCCUPIED_BEFORE_START")
    started_marker = {"schema_version": "rpf51-rev3-diagnostic-started-v1",
                      "diagnostic_id": intent["diagnostic_id"],
                      "started_at_utc": _utc_now(),
                      "intent_sha256": sha256_bytes(DIAGNOSTIC_INTENT_PATH.read_bytes())}
    _write_exclusive(DIAGNOSTIC_STARTED_PATH, canonical(started_marker))

    port = intent["port"]
    app = "rpf51-diag-app-" + uuid.uuid4().hex[:12]
    env_name = "rpf51-diag-env-" + uuid.uuid4().hex[:12]
    api_key = secrets.token_urlsafe(32)
    temp_dir = DIAGNOSTIC_ROOT / "tmp"
    for directory in (temp_dir, DIAGNOSTIC_ROOT / "runtime"):
        _owned_path(directory)
        directory.mkdir(parents=True, exist_ok=True)
    args = _build_java_args(java, temp_dir, jar, port, app, env_name)
    process_command = _redacted_process_command(port)
    readiness = {"ready": False, "failure_category": "PROCESS_NOT_STARTED",
                 "poll_count": 0, "health_get_count": 0, "elapsed_seconds": 0,
                 "category_counts": {}, "first_samples": [], "last_samples": []}
    process = None
    process_started_at = _utc_now()
    monotonic_started = time.monotonic()
    failure = None
    external_connections: list[str] = []
    process_stopped = False
    with DIAGNOSTIC_LOG_PATH.open("xb") as server_log:
        try:
            process = subprocess.Popen(
                args, cwd=UPSTREAM, env=_task_environment(api_key, DIAGNOSTIC_ROOT, temp_dir),
                stdin=subprocess.DEVNULL, stdout=server_log, stderr=subprocess.STDOUT,
                shell=False, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            readiness = _readiness(process, port, log_path=DIAGNOSTIC_READINESS_LOG,
                                    timeout_seconds=MAX_STARTUP_SECONDS,
                                    max_health_gets=MAX_DIAGNOSTIC_HEALTH_GETS)
            if not readiness["ready"]:
                failure = readiness["failure_category"] or "DIAGNOSTIC_READINESS_FAILED"
            if process.poll() is None:
                external_connections = _external_connections(process.pid, port)
                if external_connections:
                    failure = failure or "UNEXPECTED_EXTERNAL_CONNECTION"
        except ProbeError as exc:
            failure = failure or exc.code
        except (OSError, subprocess.SubprocessError, ValueError):
            failure = failure or "DIAGNOSTIC_RUNTIME_ERROR"
        except Exception:
            failure = failure or "DIAGNOSTIC_UNEXPECTED_ERROR"
        finally:
            if process is not None:
                if process.poll() is None:
                    try:
                        external_connections = _external_connections(process.pid, port)
                    except ProbeError:
                        external_connections = ["PROCESS_SOCKET_AUDIT_UNAVAILABLE"]
                    if external_connections:
                        failure = failure or "UNEXPECTED_EXTERNAL_CONNECTION"
                process_stopped = _stop_owned_process(process)
            server_log.flush()
            os.fsync(server_log.fileno())
    elapsed = round(time.monotonic() - monotonic_started, 6)
    try:
        port_closed = _port_closed(port)
    except ProbeError:
        port_closed = False
        failure = failure or "DIAGNOSTIC_PORT_CLOSE_AUDIT_UNAVAILABLE"
    if process is None:
        process_stopped = True
    if not process_stopped or not port_closed:
        failure = failure or "DIAGNOSTIC_SHUTDOWN_UNVERIFIED"
    if elapsed > MAX_DIAGNOSTIC_SECONDS:
        failure = failure or "DIAGNOSTIC_RUNTIME_BUDGET_EXCEEDED"
    try:
        log_raw = DIAGNOSTIC_LOG_PATH.read_bytes()
        key_found = api_key.encode("ascii") in log_raw
    except OSError:
        key_found = True
        failure = failure or "DIAGNOSTIC_LOG_UNAVAILABLE"
    if key_found:
        failure = failure or "API_KEY_FOUND_IN_DIAGNOSTIC_LOG"
    process_exit_code = process.returncode if process is not None else None
    status = "PASS" if failure is None and readiness["ready"] else "FAILED"
    result = {
        "schema_version": "rpf51-rev3-diagnostic-result-v1",
        "diagnostic_id": intent["diagnostic_id"], "status": status,
        "failure_category": failure, "ready": readiness["ready"],
        "runproof_parent_commit": RUNPROOF_PARENT,
        "runtime_source_sha256": intent["runtime_source_sha256"],
        "config_center_source_commit": UPSTREAM_COMMIT,
        "config_center_source_manifest_sha256": manifest_sha,
        "config_center_source_file_count": manifest["file_count"],
        "config_center_source_bytes": manifest["total_bytes"],
        "config_center_jar_sha256": UPSTREAM_JAR_SHA256,
        "config_center_jar_bytes": 66981576, "java_version": java_version,
        "process_id": process.pid if process is not None else None,
        "process_command": process_command, "process_started_at_utc": process_started_at,
        "process_stopped_at_utc": _utc_now(), "process_exit_code": process_exit_code,
        "spring_profile": "local", "persistence": "in-memory-h2",
        "bind_address": "127.0.0.1", "port": port,
        "readiness": readiness, "health_get_count": readiness["health_get_count"],
        "business_http_request_count": 0, "provider_requests": 0, "tokens": 0,
        "cost_cny": 0, "elapsed_seconds": elapsed,
        "process_stopped": process_stopped, "port_closed": port_closed,
        "external_connections": external_connections,
        "api_key_found_in_log": key_found,
    }
    result_raw = canonical(result)
    _write_exclusive(DIAGNOSTIC_RESULT_PATH, result_raw)
    if status != "PASS" and not DIAGNOSTIC_FAILURE_PATH.exists():
        _write_exclusive(DIAGNOSTIC_FAILURE_PATH, canonical({
            "schema_version": "rpf51-rev3-diagnostic-failure-v1",
            "failure_category": failure, "diagnostic_id": intent["diagnostic_id"],
            "process_id": result["process_id"], "process_stopped": process_stopped,
            "port_closed": port_closed, "health_get_count": readiness["health_get_count"],
            "business_http_request_count": 0,
        }))
    tracked = {
        "schema_version": "rpf51-rev3-readiness-diagnostic-v1",
        "status": status, "failure_category": failure,
        "diagnostic_id": intent["diagnostic_id"],
        "runproof_parent_commit": RUNPROOF_PARENT,
        "runtime_source_sha256": intent["runtime_source_sha256"],
        "config_center_source_commit": UPSTREAM_COMMIT,
        "config_center_source_manifest_sha256": manifest_sha,
        "config_center_jar_sha256": UPSTREAM_JAR_SHA256,
        "java_version": java_version, "process_id": result["process_id"],
        "process_command": process_command, "port": port,
        "spring_profile": "local", "persistence": "in-memory-h2",
        "health_path": "/actuator/health", "health_get_count": readiness["health_get_count"],
        "readiness": readiness, "business_http_request_count": 0,
        "provider_requests": 0, "tokens": 0, "cost_cny": 0,
        "elapsed_seconds": elapsed, "process_exit_code": process_exit_code,
        "process_stopped": process_stopped, "port_closed": port_closed,
        "external_connections": external_connections,
        "api_key_found_in_log": key_found,
        "diagnostic_result_sha256": sha256_bytes(result_raw),
        "limitations": ["HEALTH_GET_ONLY", "NO_BUSINESS_EFFECT", "NO_PROVIDER",
                        "SAME_HOST_PROCESS_AND_LOOPBACK_OBSERVATION"],
    }
    tracked_raw = canonical(tracked)
    if len(tracked_raw) > 16 * 1024:
        raise ProbeError("READINESS_DIAGNOSTIC_SIZE_LIMIT")
    _write_tracked_once(READINESS_DIAGNOSTIC_PATH, tracked_raw)
    print(json.dumps({"status": status, "diagnostic_id": intent["diagnostic_id"],
                      "process_id": result["process_id"], "port": port,
                      "health_get_count": readiness["health_get_count"],
                      "process_stopped": process_stopped, "port_closed": port_closed,
                      "failure_category": failure}, sort_keys=True))
    return result


def run_once() -> dict:
    _check_repo_identity()
    if STARTED_PATH.exists() or RUN_RESULT_PATH.exists() or FAILURE_PATH.exists() or WITNESS_PATH.exists():
        raise ProbeError("RPF51_REV3_SCENARIO_ONE_SHOT_ALREADY_CONSUMED")
    preflight, contracts = _read_preflight()
    if WITNESS_PATH.exists():
        raise ProbeError("REV3_WITNESS_OUTPUT_ALREADY_EXISTS")
    if not _port_closed(contracts.experiment["port"]):
        raise ProbeError("FROZEN_PORT_OCCUPIED_BEFORE_START")
    _owned_path(STARTED_PATH)
    started_record = {"schema_version": "rpf51-rev3-scenario-started-v1",
                      "run_id": contracts.experiment["run_id"], "started_at_utc": _utc_now(),
                      "preflight_sha256": sha256_bytes(PREFLIGHT_PATH.read_bytes())}
    _write_exclusive(STARTED_PATH, canonical(started_record))

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
    temp_dir = SCENARIO_ROOT / "tmp"
    for directory in (temp_dir, SCENARIO_ROOT / "runtime"):
        _owned_path(directory)
        directory.mkdir(parents=True, exist_ok=True)
    log_path = SCENARIO_LOG_PATH
    _owned_path(log_path)
    if log_path.exists():
        raise ProbeError("SERVER_LOG_ALREADY_EXISTS")

    args = _build_java_args(java, temp_dir, jar, port, app, env_name)
    process_command = _redacted_process_command(port)
    task_env = _task_environment(api_key, SCENARIO_ROOT, temp_dir)

    process = None
    started_at = _utc_now()
    monotonic_start = time.monotonic()
    observations: list[dict] = []
    steps = 0
    external_connections: list[str] = []
    run_record = None
    readiness = {"ready": False, "failure_category": "PROCESS_NOT_STARTED",
                 "poll_count": 0, "health_get_count": 0, "elapsed_seconds": 0,
                 "category_counts": {}, "first_samples": [], "last_samples": []}
    failure_code = None
    process_stopped = False
    with log_path.open("xb") as server_log:
        try:
            process = subprocess.Popen(args, cwd=UPSTREAM, env=task_env, stdin=subprocess.DEVNULL,
                                       stdout=server_log, stderr=subprocess.STDOUT,
                                       shell=False, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            steps += 1
            readiness = _readiness(process, port, log_path=SCENARIO_READINESS_LOG,
                                   timeout_seconds=MAX_STARTUP_SECONDS,
                                   max_health_gets=MAX_DIAGNOSTIC_HEALTH_GETS)
            if not readiness["ready"]:
                raise ProbeError(readiness["failure_category"] or "SCENARIO_READINESS_FAILED")
            steps += 1
            external_connections = _external_connections(process.pid, port)
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
            external_connections = _external_connections(process.pid, port)
            if external_connections:
                raise ProbeError("UNEXPECTED_EXTERNAL_CONNECTION")
            if time.monotonic() - monotonic_start > MAX_RUN_SECONDS:
                raise ProbeError("SCENARIO_RUNTIME_BUDGET_EXCEEDED")
        except ProbeError as exc:
            failure_code = exc.code
        except (OSError, subprocess.SubprocessError, ValueError, AdapterRejected):
            failure_code = "SCENARIO_RUNTIME_ERROR"
        except Exception:
            failure_code = "SCENARIO_UNEXPECTED_ERROR"
        finally:
            if process is not None:
                if process.poll() is None:
                    try:
                        external_connections = _external_connections(process.pid, port)
                    except ProbeError:
                        external_connections = ["PROCESS_SOCKET_AUDIT_UNAVAILABLE"]
                    if external_connections:
                        failure_code = failure_code or "UNEXPECTED_EXTERNAL_CONNECTION"
                process_stopped = _stop_owned_process(process)
            server_log.flush()
            os.fsync(server_log.fileno())
    steps += 1
    elapsed = time.monotonic() - monotonic_start
    diagnostic_elapsed = _read_diagnostic_result()["elapsed_seconds"]
    total_java_elapsed = diagnostic_elapsed + elapsed
    try:
        port_closed = _port_closed(port)
    except ProbeError:
        port_closed = False
        failure_code = failure_code or "SCENARIO_PORT_CLOSE_AUDIT_UNAVAILABLE"
    if process is None:
        process_stopped = True
    if not process_stopped or not port_closed:
        failure_code = failure_code or "OWNED_SERVICE_SHUTDOWN_UNVERIFIED"
    if elapsed > MAX_RUN_SECONDS:
        failure_code = failure_code or "SCENARIO_RUNTIME_BUDGET_EXCEEDED"
    if total_java_elapsed > MAX_TOTAL_JAVA_SECONDS:
        failure_code = failure_code or "TOTAL_JAVA_RUNTIME_BUDGET_EXCEEDED"
    if process is not None:
        if process.poll() is None:
            failure_code = failure_code or "OWNED_SERVICE_STILL_RUNNING"
        if process.poll() is None:
            external_connections = _external_connections(process.pid, port)
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
        if external_connections:
            failure_code = failure_code or "UNEXPECTED_EXTERNAL_CONNECTION"
    try:
        log_raw = log_path.read_bytes()
        key_found = api_key.encode("ascii") in log_raw or invalid_key.encode("ascii") in log_raw
    except OSError:
        key_found = True
        failure_code = failure_code or "SERVER_LOG_UNAVAILABLE"
    if key_found:
        failure_code = failure_code or "API_KEY_FOUND_IN_SERVICE_LOG"
    observations_raw = canonical(observations)
    if api_key.encode("ascii") in observations_raw or invalid_key.encode("ascii") in observations_raw:
        failure_code = failure_code or "API_KEY_FOUND_IN_OBSERVATIONS"
        observations_raw = b"[]"
    observations_path = SCENARIO_ROOT / "http-observations.json"
    if not observations_path.exists():
        _write_exclusive(observations_path, observations_raw)
    effect_result = evaluate_config_effect(contracts.effect, observations)
    witness = None
    raw = b""
    if (process is not None and readiness["ready"] and not failure_code
            and len(observations) <= MAX_HTTP_REQUESTS
            and effect_result["contract_outcome"] == "CONTRACT_SATISFIED_IN_RUN"
            and not effect_result["violated_rules"] and not effect_result["evidence_gaps"]):
        try:
            witness = build_witness(contracts, run_record, observations)
            raw = canonical(witness)
            if api_key.encode("ascii") in raw or invalid_key.encode("ascii") in raw:
                failure_code = "API_KEY_FOUND_IN_WITNESS"
                witness = None
                raw = b""
            else:
                verify_bytes(raw)
                _write_witness_once(raw)
        except (WitnessRejected, ProbeError, ValueError, OSError):
            failure_code = failure_code or "WITNESS_SELF_VERIFICATION_FAILED"
            witness = None
            raw = b""
    else:
        failure_code = failure_code or "ORACLE_CONTRACT_NOT_SATISFIED"
        witness = None
        raw = b""
    if failure_code or witness is None:
        result = {"schema_version": "rpf51-rev3-scenario-result-v1",
                  "status": "PARTIAL", "failure_category": failure_code,
                  "run_id": contracts.experiment["run_id"],
                  "contract_outcome": effect_result["contract_outcome"],
                  "http_request_count": len(observations), "health_get_count": readiness["health_get_count"],
                  "step_count": steps, "elapsed_seconds": round(elapsed, 6),
                  "provider_requests": 0, "tokens": 0, "cost_cny": 0,
                  "diagnostic_elapsed_seconds": diagnostic_elapsed,
                  "total_java_elapsed_seconds": round(total_java_elapsed, 6),
                  "process_id": process.pid if process is not None else None,
                  "process_exit_code": process.returncode if process is not None else None,
                  "process_stopped": process_stopped, "port_closed": port_closed,
                  "external_connections": external_connections,
                  "readiness": readiness, "http_observations_path": str(observations_path),
                  "witness_written": False,
                  "violated_rules": effect_result["violated_rules"],
                  "evidence_gaps": effect_result["evidence_gaps"]}
        if not RUN_RESULT_PATH.exists():
            _write_exclusive(RUN_RESULT_PATH, canonical(result))
        if not FAILURE_PATH.exists():
            _write_exclusive(FAILURE_PATH, canonical({"schema_version": "rpf51-rev3-scenario-failure-v1",
                                                      "failure_category": failure_code,
                                                      "process_id": result["process_id"],
                                                      "process_stopped": process_stopped,
                                                      "port_closed": port_closed,
                                                      "http_request_count": len(observations),
                                                      "health_get_count": readiness["health_get_count"],
                                                      "witness_written": False}))
        print(json.dumps({"status": "PARTIAL", **result}, sort_keys=True))
        raise ProbeError(failure_code or "ORACLE_CONTRACT_NOT_SATISFIED")
    anchor = sha256_bytes(raw)
    result = {"schema_version": "rpf51-rev3-scenario-result-v1", "status": "PASS",
              "run_id": contracts.experiment["run_id"],
              "source_level": witness["source_identity"]["source_level"],
              "contract_outcome": witness["effect_result"]["contract_outcome"],
              "witness_sha256": anchor, "witness_bytes": len(raw),
              "http_request_count": len(observations), "health_get_count": readiness["health_get_count"],
              "step_count": steps, "elapsed_seconds": round(elapsed, 6),
              "provider_requests": 0, "tokens": 0, "cost_cny": 0,
              "diagnostic_elapsed_seconds": diagnostic_elapsed,
              "total_java_elapsed_seconds": round(total_java_elapsed, 6),
              "process_id": process.pid, "process_exit_code": process.returncode,
              "process_stopped": process_stopped, "port_closed": port_closed,
              "external_connections": external_connections,
              "violated_rules": witness["effect_result"]["violated_rules"],
              "evidence_gaps": witness["effect_result"]["evidence_gaps"]}
    _write_exclusive(RUN_RESULT_PATH, canonical(result))
    print(json.dumps({"status": "RUN_RECORDED", **result}, sort_keys=True))
    return result


def _record_failure(code: str) -> None:
    if STARTED_PATH.exists() and not FAILURE_PATH.exists():
        _write_exclusive(FAILURE_PATH, canonical({
            "schema_version": "rpf51-rev3-scenario-failure-v1",
            "failure_category": code, "started_marker_present": True,
            "witness_written": WITNESS_PATH.exists(),
        }))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded one-shot RPF-51 config-center proof",
                                     allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-diagnostic", action="store_true",
                       help="copy verified source and freeze the single read-only diagnostic")
    modes.add_argument("--diagnose", action="store_true",
                       help="run one read-only health diagnostic and verify shutdown")
    modes.add_argument("--prepare-scenario", action="store_true",
                       help="freeze one business scenario after diagnostic PASS")
    modes.add_argument("--run-scenario", action="store_true",
                       help="consume the single business scenario and produce real evidence")
    args = parser.parse_args(argv)
    try:
        if args.prepare_diagnostic:
            prepare_diagnostic()
        elif args.diagnose:
            result = run_diagnostic_once()
            return 0 if result["status"] == "PASS" else 3
        elif args.prepare_scenario:
            prepare_scenario()
        else:
            try:
                run_once()
            except ProbeError as exc:
                _record_failure(exc.code)
                print(f"RPF51_STOP {exc.code}", file=sys.stderr)
                return 3
        return 0
    except ProbeError as exc:
        if args.diagnose and DIAGNOSTIC_STARTED_PATH.exists() and not DIAGNOSTIC_FAILURE_PATH.exists():
            _write_exclusive(DIAGNOSTIC_FAILURE_PATH, canonical({
                "schema_version": "rpf51-rev3-diagnostic-failure-v1",
                "failure_category": exc.code, "diagnostic_id": None,
                "result_written": DIAGNOSTIC_RESULT_PATH.exists(),
            }))
        if args.run_scenario:
            _record_failure(exc.code)
        print(f"RPF51_STOP {exc.code}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
