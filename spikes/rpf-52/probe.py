"""One-shot RPF-52 preflight and bounded Pydantic AI/config-center scenario."""
from __future__ import annotations

import argparse
import base64
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
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.effectwitness.config_target_bridge import (
    BoundedConfigHttp, ConfigTargetAuthorityReader, ConfigTargetFixtureHost,
    ConfigTargetToolHost, TargetBridgeRejected,
)
from runtime.runproof_runtime.effectwitness.config_target_contracts import (
    CONTRACT_SCHEMA, GIT_BRANCH, HTTP_ORDER, MANIFEST_SHA, PARENT_SHA,
    PLAN_REVISION, SOURCE_COMMIT, SOURCE_LEVEL, JAR_SHA, canonical, digest,
    evaluate_config_target_effect, make_contracts, parse_sdk_child_report,
    strict_json, validate_contracts,
)
from runtime.runproof_runtime.effectwitness.config_target_verify import (
    EvidenceRejected, verify_bytes,
)

TASK_ROOT = ROOT / ".local" / "rpf-52-rev3"
SCENARIO_ROOT = TASK_ROOT / "scenario"
PREFLIGHT_PATH = SCENARIO_ROOT / "preflight.json"
STARTED_PATH = SCENARIO_ROOT / "scenario-started.json"
RESULT_PATH = SCENARIO_ROOT / "scenario-result.json"
SDK_DIAGNOSTIC_PATH = ROOT / "spikes" / "rpf-52" / "rev-3" / "sdk-diagnostic.json"
EVIDENCE_PATH = ROOT / "spikes" / "rpf-52" / "rev-3" / "config-target-fixture-evidence.json"
OLD_TASK_ROOT = ROOT / ".local" / "rpf-51-rev4"
SOURCE_ROOT = OLD_TASK_ROOT / "upstream-config-center"
MANIFEST_PATH = OLD_TASK_ROOT / "upstream-source-manifest.json"
JAR_PATH = SOURCE_ROOT / "config-center-server" / "target" / "config-center-server-1.0.0.jar"
TASK_JAR_PATH = SCENARIO_ROOT / "config-center-server-1.0.0.jar"
SDK_BOOTSTRAP_PYTHON = Path(
    r"C:\Users\Yukis\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe")
SDK_PYTHON = SDK_BOOTSTRAP_PYTHON
SDK_SITE_PACKAGES = ROOT / ".local" / "rpf-48" / "venv" / "Lib" / "site-packages"
SDK_DISTRIBUTION_REF = ".local/rpf-48/venv/Lib/site-packages"
SDK_CHILD = ROOT / "runtime" / "runproof_runtime" / "effectwitness" / "config_target_external.py"
JAVA = Path(r"C:\Program Files\Java\jdk-17\bin\java.exe")
BRANCH = GIT_BRANCH
ORIGIN = "https://github.com/MyKr-YSteinsK/runproof.git"
MAIN_SHA = "bda0cd49e50e3181f604324e94877a24b9885334"
_RUNTIME_FILES = (
    "runtime/runproof_runtime/effectwitness/config_target_contracts.py",
    "runtime/runproof_runtime/effectwitness/config_target_bridge.py",
    "runtime/runproof_runtime/effectwitness/config_target_external.py",
    "runtime/runproof_runtime/effectwitness/config_target_verify.py",
    "runtime/tests/test_effectwitness_config_target.py",
    "spikes/rpf-52/probe.py",
    "spikes/rpf-52/rev-3/diagnose.py",
)
_ALLOWED_TRACKED_CHANGES = set(_RUNTIME_FILES)
_ALLOWED_UNTRACKED_DIRECTORIES = {"docs/reviews/", "spikes/rpf-52/rev-3/"}
_PACKAGE_SCRIPT = r'''
import base64, hashlib, importlib.metadata as md, inspect, json, pathlib, sys
sys.path.insert(0,sys.argv[1])
from openai import AsyncOpenAI
from pydantic_ai import Agent
def package(name):
    dist=md.distribution(name)
    files=list(dist.files or ())
    checked=0
    bad=0
    for f in files:
        if f.hash is None:
            continue
        p=pathlib.Path(dist.locate_file(f))
        if not p.is_file():
            bad+=1
            continue
        actual=hashlib.new(f.hash.mode,p.read_bytes()).digest()
        if base64.urlsafe_b64encode(actual).decode().rstrip("=") != f.hash.value:
            bad+=1
        checked+=1
    site=pathlib.Path(dist.locate_file("")).resolve()
    return {"version":dist.version,
            "metadata_sha256":hashlib.sha256(dist.read_text("METADATA").encode()).hexdigest(),
            "record_sha256":hashlib.sha256(dist.read_text("RECORD").encode()).hexdigest(),
            "record_files":len(files),"record_hashes_checked":checked,
            "record_mismatches":bad}
sdk=pathlib.Path(inspect.getfile(Agent)).resolve()
client=pathlib.Path(inspect.getfile(AsyncOpenAI)).resolve()
site=pathlib.Path(md.distribution("pydantic-ai-slim").locate_file("")).resolve()
openai_site=pathlib.Path(md.distribution("openai").locate_file("")).resolve()
print(json.dumps({"python_version":sys.version.split()[0],
 "python_executable":sys.executable,
 "sdk_source_sha256":hashlib.sha256(sdk.read_bytes()).hexdigest(),
 "sdk_source_relative":sdk.relative_to(site).as_posix(),
 "openai_source_sha256":hashlib.sha256(client.read_bytes()).hexdigest(),
 "openai_source_relative":client.relative_to(openai_site).as_posix(),
 "sdk_distributions":{"pydantic-ai-slim":package("pydantic-ai-slim"),
                      "openai":package("openai")}},
 sort_keys=True,separators=(",",":")))
'''


class ProbeError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=30, check=False, text=True)
    if result.returncode:
        raise ProbeError("GIT_" + args[0].upper().replace("-", "_"))
    return result.stdout.strip()


def _check_repo_identity(*, require_remote_free: bool) -> dict:
    if Path(_git("rev-parse", "--show-toplevel")).resolve() != ROOT.resolve():
        raise ProbeError("RUNPROOF_ROOT_MISMATCH")
    if _git("rev-parse", "HEAD") != PARENT_SHA or _git("branch", "--show-current") != BRANCH:
        raise ProbeError("RUNPROOF_BASE_OR_BRANCH_MISMATCH")
    if (_git("remote", "get-url", "origin") != ORIGIN
            or _git("remote", "get-url", "--push", "origin") != ORIGIN):
        raise ProbeError("RUNPROOF_ORIGIN_MISMATCH")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT, check=False).returncode:
        raise ProbeError("INDEX_NOT_CLEAN")
    status = subprocess.run(["git", "status", "--porcelain=v1"], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=30, check=False, text=True)
    if status.returncode:
        raise ProbeError("WORKTREE_STATUS_UNAVAILABLE")
    for line in status.stdout.splitlines():
        if len(line) < 4:
            raise ProbeError("WORKTREE_STATUS_INVALID")
        code, path = line[:2], line[3:].replace("\\", "/")
        if code == "??" and path in _ALLOWED_UNTRACKED_DIRECTORIES:
            continue
        if code == "??" or path not in _ALLOWED_TRACKED_CHANGES:
            raise ProbeError("WORKTREE_OUTSIDE_ALLOWLIST")
    refs = {}
    raw = subprocess.run(["git", "ls-remote", "origin", "refs/heads/main",
                          "refs/heads/" + BRANCH], cwd=ROOT, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, timeout=30, check=False, text=True)
    if raw.returncode:
        raise ProbeError("REMOTE_READ_UNAVAILABLE")
    for line in raw.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            refs[parts[1]] = parts[0]
    if refs.get("refs/heads/main") != MAIN_SHA:
        raise ProbeError("REMOTE_MAIN_CHANGED")
    remote_branch = refs.get("refs/heads/" + BRANCH)
    if require_remote_free and remote_branch is not None:
        raise ProbeError("REMOTE_BRANCH_ALREADY_EXISTS")
    return {"repo": "MyKr-YSteinsK/runproof", "branch": BRANCH,
            "base_sha": PARENT_SHA, "remote": ORIGIN, "main_sha": MAIN_SHA,
            "remote_branch_sha": remote_branch}


def _has_symlink(path: Path, stop: Path) -> bool:
    current = path
    while current != stop and current != current.parent:
        if current.is_symlink():
            return True
        current = current.parent
    return False


def _verify_source_bundle() -> dict:
    if (not MANIFEST_PATH.is_file() or _has_symlink(MANIFEST_PATH, ROOT)
            or not SOURCE_ROOT.is_dir() or _has_symlink(SOURCE_ROOT, ROOT)
            or not JAR_PATH.is_file() or _has_symlink(JAR_PATH, ROOT)):
        raise ProbeError("REV4_SOURCE_OR_JAR_UNAVAILABLE")
    raw = MANIFEST_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ProbeError("SOURCE_MANIFEST_SHA_MISMATCH")
    try:
        manifest = strict_json(raw)
    except Exception:
        raise ProbeError("SOURCE_MANIFEST_INVALID") from None
    if (type(manifest) is not dict
            or set(manifest) != {"source_commit", "file_count", "total_bytes", "files"}
            or manifest["source_commit"] != SOURCE_COMMIT
            or manifest["file_count"] != 110 or len(manifest["files"]) != 110
            or manifest["total_bytes"] != 393800):
        raise ProbeError("SOURCE_MANIFEST_CONTRACT")
    count = total = 0
    for item in manifest["files"]:
        if type(item) is not dict or set(item) != {"path", "bytes", "sha256"}:
            raise ProbeError("SOURCE_MANIFEST_ENTRY")
        relative = PurePosixPath(item["path"].replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ProbeError("SOURCE_PATH_ESCAPE")
        candidate = SOURCE_ROOT.joinpath(*relative.parts)
        if (not candidate.is_file() or _has_symlink(candidate, SOURCE_ROOT)
                or not candidate.resolve().is_relative_to(SOURCE_ROOT.resolve())):
            raise ProbeError("SOURCE_FILE_MISSING_OR_LINK")
        raw_file = candidate.read_bytes()
        if len(raw_file) != item["bytes"] or hashlib.sha256(raw_file).hexdigest() != item["sha256"]:
            raise ProbeError("SOURCE_FILE_SHA_MISMATCH")
        total += len(raw_file)
        count += 1
    jar_raw = JAR_PATH.read_bytes()
    if (len(jar_raw) != 66981576 or hashlib.sha256(jar_raw).hexdigest() != JAR_SHA):
        raise ProbeError("JAR_SHA_MISMATCH")
    return {"source_commit": SOURCE_COMMIT, "manifest_sha256": MANIFEST_SHA,
            "source_file_count": count, "source_bytes": total,
            "jar_bytes": len(jar_raw), "jar_sha256": JAR_SHA,
            "source_root": ".local/rpf-51-rev4/upstream-config-center",
            "source_jar_path": ".local/rpf-51-rev4/upstream-config-center/config-center-server/target/config-center-server-1.0.0.jar",
            "runtime_jar_path": ".local/rpf-52-rev3/scenario/config-center-server-1.0.0.jar"}


def _copy_task_jar() -> dict:
    if SCENARIO_ROOT.is_symlink() or not SCENARIO_ROOT.is_dir():
        raise ProbeError("TASK_JAR_DESTINATION_UNAVAILABLE")
    if TASK_JAR_PATH.exists() or TASK_JAR_PATH.is_symlink():
        return _verify_task_jar()
    try:
        with JAR_PATH.open("rb") as source, TASK_JAR_PATH.open("xb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
    except OSError:
        raise ProbeError("TASK_JAR_COPY_FAILED") from None
    return _verify_task_jar()


def _verify_task_jar() -> dict:
    if (not TASK_JAR_PATH.is_file() or _has_symlink(TASK_JAR_PATH, SCENARIO_ROOT)):
        raise ProbeError("TASK_JAR_UNAVAILABLE_OR_LINK")
    raw = TASK_JAR_PATH.read_bytes()
    if len(raw) != 66981576 or hashlib.sha256(raw).hexdigest() != JAR_SHA:
        raise ProbeError("TASK_JAR_IDENTITY_MISMATCH")
    return {"path": ".local/rpf-52-rev3/scenario/config-center-server-1.0.0.jar",
            "bytes": len(raw), "sha256": JAR_SHA}


def _sdk_identity() -> dict:
    if (not SDK_PYTHON.is_file() or _has_symlink(SDK_PYTHON, ROOT)
            or not SDK_SITE_PACKAGES.is_dir() or _has_symlink(SDK_SITE_PACKAGES, ROOT)):
        raise ProbeError("PINNED_SDK_PYTHON_UNAVAILABLE")
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in {"OPENAI_API_KEY", "DEEPSEEK_API_KEY", "HTTP_PROXY",
                                "HTTPS_PROXY", "ALL_PROXY", "HTTP_PROXY", "NO_PROXY"}
           and "API_KEY" not in k.upper() and "TOKEN" not in k.upper()}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "OTEL_SDK_DISABLED": "true",
                "LOGFIRE_SEND_TO_LOGFIRE": "false"})
    result = subprocess.run([str(SDK_PYTHON), "-B", "-I", "-c", _PACKAGE_SCRIPT,
                             str(SDK_SITE_PACKAGES.resolve())],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=90, check=False)
    if result.returncode:
        raise ProbeError("PINNED_SDK_INSPECTION_FAILED")
    try:
        data = strict_json(result.stdout)
    except Exception:
        raise ProbeError("PINNED_SDK_IDENTITY_INVALID") from None
    if data.get("python_version") != "3.12.13":
        raise ProbeError("PINNED_PYTHON_VERSION_MISMATCH")
    try:
        actual_python = Path(data["python_executable"]).resolve(strict=True)
        expected_python = SDK_BOOTSTRAP_PYTHON.resolve(strict=True)
    except (OSError, RuntimeError, KeyError):
        raise ProbeError("SDK_PYTHON_IDENTITY_UNAVAILABLE") from None
    if actual_python != expected_python:
        raise ProbeError("SDK_PYTHON_IDENTITY_MISMATCH")
    data["python_executable"] = "pinned-cpython-3.12.13"
    if (data["sdk_distributions"]["pydantic-ai-slim"]["version"] != "2.57.0"
            or data["sdk_distributions"]["openai"]["version"] != "3.35.1"
            or data["sdk_distributions"]["pydantic-ai-slim"]["record_mismatches"] != 0
            or data["sdk_distributions"]["openai"]["record_mismatches"] != 0):
        raise ProbeError("PINNED_SDK_DISTRIBUTION_MISMATCH")
    data["distribution_origin"] = "rpf48-pinned-site-packages-read-only"
    data["readonly_distribution_ref_sha256"] = hashlib.sha256(
        SDK_DISTRIBUTION_REF.encode("utf-8")).hexdigest()
    return data


def _verify_task_sdk_runtime() -> None:
    if (not SDK_BOOTSTRAP_PYTHON.is_file()
            or _has_symlink(SDK_BOOTSTRAP_PYTHON, Path("C:\\"))
            or not SDK_SITE_PACKAGES.is_dir()):
        raise ProbeError("PINNED_SDK_SOURCE_ENV_UNAVAILABLE")
    identity = subprocess.run([str(SDK_BOOTSTRAP_PYTHON), "-B", "-I", "-c",
                               "import sys; print(sys.version.split()[0])"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=20, check=False, text=True)
    if identity.returncode or identity.stdout.strip() != "3.12.13":
        raise ProbeError("SDK_BOOTSTRAP_PYTHON_MISMATCH")


def _java_identity() -> dict:
    if not JAVA.is_file() or _has_symlink(JAVA, JAVA.parents[2]):
        raise ProbeError("DIRECT_JDK_UNAVAILABLE")
    result = subprocess.run([str(JAVA), "-version"], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=10, check=False)
    output = result.stdout.decode("utf-8", errors="replace")
    match = re.search(r'version "(17(?:\.\d+){1,2}(?:\+[-A-Za-z0-9._]+)?)"', output)
    if result.returncode != 0 or not match:
        raise ProbeError("DIRECT_JDK_17_REQUIRED")
    return {"executable": "jdk-17/bin/java.exe", "version": match.group(1)}


def _source_identity() -> dict:
    identities = {}
    for name in _RUNTIME_FILES:
        path = ROOT / name
        if not path.is_file():
            raise ProbeError("RUNTIME_SOURCE_MISSING")
        identities[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": identities, "sha256": digest(identities)}


def _free_ports() -> tuple[int, int]:
    sockets = []
    try:
        for _ in range(2):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            sockets.append(sock)
        ports = tuple(int(sock.getsockname()[1]) for sock in sockets)
        if ports[0] == ports[1]:
            raise ProbeError("DUPLICATE_LOOPBACK_PORT")
        return ports
    except OSError:
        raise ProbeError("LOOPBACK_PORT_UNAVAILABLE") from None
    finally:
        for sock in sockets:
            sock.close()


def _write_exclusive(path: Path, raw: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise ProbeError("ONE_SHOT_FILE_ALREADY_EXISTS") from None


def _load_sdk_diagnostic() -> tuple[dict, bytes]:
    if (not SDK_DIAGNOSTIC_PATH.is_file()
            or _has_symlink(SDK_DIAGNOSTIC_PATH, ROOT)):
        raise ProbeError("SDK_DIAGNOSTIC_MISSING_OR_LINK")
    raw = SDK_DIAGNOSTIC_PATH.read_bytes()
    try:
        document = strict_json(raw)
    except Exception:
        raise ProbeError("SDK_DIAGNOSTIC_INVALID") from None
    fields = {
        "schema_version", "plan_id", "plan_revision", "mode", "status", "attempts",
        "runtime_source_identity", "diagnose_script_sha256", "sdk_identity",
        "java_started", "provider_requests", "tokens", "cost_cny", "finalized_at_utc",
    }
    if type(document) is not dict or set(document) != fields:
        raise ProbeError("SDK_DIAGNOSTIC_NOT_PASS")
    attempts = document["attempts"]
    if (document["schema_version"] != "rpf52-sdk-diagnostic-v1"
            or document["plan_id"] != "RPF-52"
            or document["plan_revision"] != PLAN_REVISION
            or document["mode"] != "FIXTURE_ONLY_NO_JAVA_NO_BUSINESS_EFFECT"
            or document["status"] != "PASS" or document["java_started"] is not False
            or document["provider_requests"] != 0 or document["tokens"] != 0
            or document["cost_cny"] != 0 or type(attempts) is not list
            or not 1 <= len(attempts) <= 2
            or any(type(item) is not dict for item in attempts)):
        raise ProbeError("SDK_DIAGNOSTIC_NOT_PASS")
    attempt_fields = {
        "attempt", "run_id", "status", "runtime_source_sha256", "sdk_error",
        "fixture_host_first_failure_code", "completions", "sdk_tool_calls", "tool_returns",
        "java_started", "real_business_http_requests", "cleanup",
    }
    for index, item in enumerate(attempts, start=1):
        cleanup = item.get("cleanup")
        sdk_error = item.get("sdk_error")
        counts = (item.get("completions"), item.get("sdk_tool_calls"),
                  item.get("tool_returns"))
        if (set(item) != attempt_fields or item.get("attempt") != index
                or item.get("status") not in {"PASS", "FAIL"}
                or not isinstance(item.get("run_id"), str)
                or type(item.get("runtime_source_sha256")) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", item["runtime_source_sha256"])
                or item.get("java_started") is not False
                or item.get("real_business_http_requests") != 0
                or type(counts[0]) is not int or not 0 <= counts[0] <= 4
                or (counts[1] is not None and
                    (type(counts[1]) is not int or not 0 <= counts[1] <= 3))
                or type(counts[2]) is not int or not 0 <= counts[2] <= 3
                or type(sdk_error) is not dict
                or set(sdk_error) != {
                    "status", "stage", "error_type", "guard_code", "guard_denials",
                    "parser_code"}
                or sdk_error.get("status") not in {"SDK_ERROR", "COMPLETED", None}
                or (item.get("fixture_host_first_failure_code") is not None
                    and (type(item["fixture_host_first_failure_code"]) is not str
                         or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}",
                                             item["fixture_host_first_failure_code"])))
                or cleanup != {
                    "sdk_child_exited": True, "fixture_host_closed": True,
                    "fixture_port_closed": True,
                    "sdk_child_external_connections": [],
                    "parent_process_external_connections": [],
                }):
            raise ProbeError("SDK_DIAGNOSTIC_ATTEMPT_CONTRACT")
        if item["status"] == "PASS" and (
                counts != (4, 3, 3) or item["fixture_host_first_failure_code"] is not None
                or sdk_error.get("status") != "COMPLETED"):
            raise ProbeError("SDK_DIAGNOSTIC_ATTEMPT_CONTRACT")
    if (attempts[-1]["status"] != "PASS"
            or (len(attempts) == 2 and attempts[0]["status"] != "FAIL")
            or type(document.get("sdk_identity")) is not dict
            or type(document.get("runtime_source_identity")) is not dict
            or document["runtime_source_identity"].get("sha256")
            != attempts[-1]["runtime_source_sha256"]
            or not isinstance(document.get("diagnose_script_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", document["diagnose_script_sha256"])
            or document["runtime_source_identity"].get("files", {}).get(
                "spikes/rpf-52/rev-3/diagnose.py") != document["diagnose_script_sha256"]):
        raise ProbeError("SDK_DIAGNOSTIC_NOT_PASS")
    return document, raw


def _diagnostic_source_delta(diagnostic: dict, scenario_source_identity: dict) -> list[str]:
    diagnostic_identity = diagnostic.get("runtime_source_identity")
    if (type(diagnostic_identity) is not dict
            or type(diagnostic_identity.get("files")) is not dict
            or type(scenario_source_identity) is not dict
            or type(scenario_source_identity.get("files")) is not dict
            or set(diagnostic_identity["files"]) != set(scenario_source_identity["files"])):
        raise ProbeError("SDK_DIAGNOSTIC_SOURCE_IDENTITY_MISMATCH")
    changed = sorted(name for name, sha in diagnostic_identity["files"].items()
                     if scenario_source_identity["files"].get(name) != sha)
    if changed not in ([], ["spikes/rpf-52/probe.py"]):
        raise ProbeError("SDK_DIAGNOSTIC_SOURCE_CHANGE_OUTSIDE_GATE_FIX")
    return changed


def _validate_diagnostic_task_root() -> None:
    if TASK_ROOT.is_symlink() or (TASK_ROOT.exists() and not TASK_ROOT.is_dir()):
        raise ProbeError("RPF52_REV3_TASK_ROOT_UNAVAILABLE")
    if not TASK_ROOT.exists():
        raise ProbeError("RPF52_REV3_DIAGNOSTIC_ROOT_MISSING")
    allowed = {"diagnostic-1", "diagnostic-2"}
    existing = {child.name: child for child in TASK_ROOT.iterdir()}
    if set(existing) - allowed:
        raise ProbeError("RPF52_REV3_TASK_ROOT_HAS_UNOWNED_CONTENT")
    for name, attempt in existing.items():
        if not attempt.is_dir() or attempt.is_symlink():
            raise ProbeError("RPF52_REV3_DIAGNOSTIC_ATTEMPT_PATH_INVALID")
        children = {child.name: child for child in attempt.iterdir()}
        if set(children) != {"attempt-started.json", "attempt.json", "sdk-tmp"}:
            raise ProbeError("RPF52_REV3_DIAGNOSTIC_CONTENT_INVALID")
        if (any(not children[key].is_file() or children[key].is_symlink()
                for key in ("attempt-started.json", "attempt.json"))
                or not children["sdk-tmp"].is_dir() or children["sdk-tmp"].is_symlink()):
            raise ProbeError("RPF52_REV3_DIAGNOSTIC_CONTENT_INVALID")
        sdk_tmp_children = {child.name: child for child in children["sdk-tmp"].iterdir()}
        if (not {"appdata", "localappdata"}.issubset(sdk_tmp_children)
                or any(not sdk_tmp_children[key].is_dir() or sdk_tmp_children[key].is_symlink()
                       for key in ("appdata", "localappdata"))):
            raise ProbeError("RPF52_REV3_DIAGNOSTIC_TEMP_CONTENT_INVALID")


def prepare() -> dict:
    _validate_diagnostic_task_root()
    if SCENARIO_ROOT.exists() or SCENARIO_ROOT.is_symlink():
        raise ProbeError("SCENARIO_ROOT_ALREADY_EXISTS")
    diagnostic, diagnostic_raw = _load_sdk_diagnostic()
    if not (ROOT / ".local").is_dir() or (ROOT / ".local").is_symlink():
        raise ProbeError("LOCAL_ROOT_UNAVAILABLE")
    if EVIDENCE_PATH.exists():
        raise ProbeError("EVIDENCE_ALREADY_EXISTS")
    repo = _check_repo_identity(require_remote_free=True)
    source = _verify_source_bundle()
    java = _java_identity()
    source_identity = _source_identity()
    source_delta = _diagnostic_source_delta(diagnostic, source_identity)
    java_port, agent_port = _free_ports()
    run_id = "rpf52-" + uuid.uuid4().hex
    prepared_at = _utc_now()
    SCENARIO_ROOT.mkdir()
    source["runtime_jar"] = _copy_task_jar()
    _verify_task_sdk_runtime()
    sdk = _sdk_identity()
    if sdk != diagnostic.get("sdk_identity"):
        raise ProbeError("SDK_DIAGNOSTIC_SDK_IDENTITY_MISMATCH")
    contracts = make_contracts(run_id=run_id,
        source_identity_sha256=source_identity["sha256"], sdk_identity=sdk,
        java_version=java["version"], java_port=java_port,
        agent_host_port=agent_port, prepared_at_utc=prepared_at)
    document = {
        "plan_id": "RPF-52", "plan_revision": PLAN_REVISION,
        "created_at_utc": prepared_at, "repo": repo, "source": source,
        "java_identity": java, "sdk_identity": sdk,
        "runtime_source_identity": source_identity,
        "sdk_diagnostic": {
            "path": "spikes/rpf-52/rev-3/sdk-diagnostic.json",
            "sha256": hashlib.sha256(diagnostic_raw).hexdigest(),
            "status": diagnostic["status"],
            "runtime_source_sha256": diagnostic["runtime_source_identity"]["sha256"],
            "scenario_runtime_source_sha256": source_identity["sha256"],
            "source_delta_files": source_delta,
            "source_delta_reason": (
                "PROBE_DIAGNOSTIC_SUMMARY_VALIDATION_ONLY" if source_delta else "IDENTICAL"),
            "sdk_identity": diagnostic["sdk_identity"],
        },
        "contracts": contracts,
        "java_argv_redacted": [
            "java", "-Djava.io.tmpdir=<task-owned>", "-jar",
            "<task-owned-source>/config-center-server-1.0.0.jar",
            "--spring.profiles.active=local", "--server.address=127.0.0.1",
            "--server.port=" + str(java_port),
            "--security.api-keys[0].key=" + "$" + "{CONFIG_CENTER_API_KEY}",
            "--security.api-keys[0].app=<synthetic>",
            "--security.api-keys[0].env=<synthetic>",
        ],
        "budgets": dict(contracts["execution"]["budgets"]),
        "provider_requests": 0, "tokens": 0, "cost_cny": 0,
    }
    validate_contracts(contracts)
    _write_exclusive(PREFLIGHT_PATH, canonical(document))
    return {"status": "PREFLIGHT_FROZEN", "run_id": run_id,
            "preflight_path": ".local/rpf-52-rev3/scenario/preflight.json",
            "task_jar_path": source["runtime_jar"]["path"],
            "source_manifest_sha256": MANIFEST_SHA, "jar_sha256": JAR_SHA,
            "runtime_source_sha256": source_identity["sha256"],
            "sdk_versions": {"pydantic-ai-slim": "2.57.0", "openai": "3.35.1"},
            "java_version": java["version"], "ports": [java_port, agent_port]}


def _load_preflight() -> dict:
    if (not PREFLIGHT_PATH.is_file() or _has_symlink(PREFLIGHT_PATH, TASK_ROOT)):
        raise ProbeError("PREFLIGHT_MISSING_OR_LINK")
    try:
        document = strict_json(PREFLIGHT_PATH.read_bytes())
        validate_contracts(document["contracts"])
    except Exception:
        raise ProbeError("PREFLIGHT_INVALID") from None
    if document.get("plan_id") != "RPF-52" or document.get("plan_revision") != PLAN_REVISION:
        raise ProbeError("PREFLIGHT_PLAN_IDENTITY")
    return document


def _check_frozen(preflight: dict) -> None:
    _check_repo_identity(require_remote_free=True)
    if _source_identity() != preflight["runtime_source_identity"]:
        raise ProbeError("RUNTIME_SOURCE_CHANGED_AFTER_FREEZE")
    diagnostic, diagnostic_raw = _load_sdk_diagnostic()
    frozen_diagnostic = preflight.get("sdk_diagnostic", {})
    source_delta = _diagnostic_source_delta(
        diagnostic, preflight["runtime_source_identity"])
    if (frozen_diagnostic.get("sha256") != hashlib.sha256(diagnostic_raw).hexdigest()
            or frozen_diagnostic.get("runtime_source_sha256")
            != diagnostic["runtime_source_identity"]["sha256"]
            or frozen_diagnostic.get("scenario_runtime_source_sha256")
            != preflight["runtime_source_identity"]["sha256"]
            or frozen_diagnostic.get("source_delta_files") != source_delta
            or frozen_diagnostic.get("source_delta_reason") != (
                "PROBE_DIAGNOSTIC_SUMMARY_VALIDATION_ONLY" if source_delta else "IDENTICAL")
            or frozen_diagnostic.get("sdk_identity") != preflight.get("sdk_identity")
            or diagnostic.get("sdk_identity") != preflight.get("sdk_identity")):
        raise ProbeError("SDK_DIAGNOSTIC_FREEZE_MISMATCH")
    source = _verify_source_bundle()
    source["runtime_jar"] = _verify_task_jar()
    if source != preflight["source"]:
        raise ProbeError("EXTERNAL_SOURCE_CHANGED_AFTER_FREEZE")
    if _sdk_identity() != preflight["sdk_identity"]:
        raise ProbeError("SDK_IDENTITY_CHANGED_AFTER_FREEZE")
    if _java_identity() != preflight["java_identity"]:
        raise ProbeError("JDK_IDENTITY_CHANGED_AFTER_FREEZE")
    contracts = preflight["contracts"]
    if preflight["runtime_source_identity"]["sha256"] != contracts["experiment"]["runtime_source_sha256"]:
        raise ProbeError("CONTRACT_SOURCE_IDENTITY")
    if not _port_free(contracts["experiment"]["java_port"]):
        raise ProbeError("JAVA_PORT_NO_LONGER_FREE")
    if not _port_free(contracts["experiment"]["agent_host_port"]):
        raise ProbeError("AGENT_PORT_NO_LONGER_FREE")
    if EVIDENCE_PATH.exists():
        raise ProbeError("EVIDENCE_ALREADY_EXISTS")


def _port_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def _netstat_rows() -> tuple[list[dict], int]:
    try:
        result = subprocess.run(["netstat.exe", "-ano", "-p", "tcp"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
            check=False, text=True)
    except (OSError, subprocess.TimeoutExpired):
        raise ProbeError("PROCESS_SOCKET_AUDIT_UNAVAILABLE") from None
    if result.returncode:
        raise ProbeError("PROCESS_SOCKET_AUDIT_UNAVAILABLE")
    rows, malformed = [], 0
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts or parts[0].upper() != "TCP":
            continue
        if len(parts) < 5 or not parts[-1].isdigit():
            malformed += 1
            continue
        rows.append({"local": parts[1], "remote": parts[2],
                     "state": parts[-2].upper(), "pid": int(parts[-1])})
    return rows, malformed


def _endpoint_port(endpoint: str) -> int | None:
    value = endpoint.rsplit(":", 1)[-1]
    return int(value) if value.isdigit() else None


def _listener_pids(rows: list[dict], port: int) -> list[int]:
    return sorted(row["pid"] for row in rows
                  if row["state"] == "LISTENING" and _endpoint_port(row["local"]) == port)


def _listener_is(pid: int, port: int) -> bool:
    rows, malformed = _netstat_rows()
    listeners = [row for row in rows
                 if row["state"] == "LISTENING" and _endpoint_port(row["local"]) == port]
    return (not malformed and len(listeners) == 1
            and listeners[0]["local"] == f"127.0.0.1:{port}"
            and listeners[0]["pid"] == pid)


def _external_connections(pid: int, *, allowed_listener_ports: set[int] | None = None,
                          allowed_remote_ports: set[int] | None = None) -> list[str]:
    external = []
    allowed_listener_ports = allowed_listener_ports or set()
    allowed_remote_ports = allowed_remote_ports or set()
    rows, malformed = _netstat_rows()
    if malformed:
        external.append("NETSTAT_OUTPUT_INCOMPLETE")
    for row in rows:
        if row["pid"] != pid:
            continue
        if row["state"] == "LISTENING":
            if (row["local"].rsplit(":", 1)[0].strip("[]") != "127.0.0.1"
                    or _endpoint_port(row["local"]) not in allowed_listener_ports):
                external.append("UNEXPECTED_LISTENER")
            continue
        local = row["local"]
        local_address = local.rsplit(":", 1)[0].strip("[]")
        if local_address != "127.0.0.1":
            external.append("NON_TASK_LOCAL_ENDPOINT")
        remote = row["remote"]
        if remote in ("0.0.0.0:0", "[::]:0", "*:*", "*:0"):
            continue
        address = remote.rsplit(":", 1)[0].strip("[]")
        if address != "127.0.0.1":
            external.append("NON_TASK_REMOTE_ENDPOINT")
        elif not (
                _endpoint_port(local) in allowed_listener_ports
                or _endpoint_port(remote) in allowed_remote_ports):
            external.append("UNEXPECTED_REMOTE_PORT")
    return sorted(set(external))


def _health_get(port: int, timeout: float = 5.0) -> dict:
    started = time.monotonic()
    connection = None
    observation = {"status": None, "body": None, "body_sha256": None,
                   "elapsed_ms": 0, "transport_error": None}
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port,
                                                timeout=min(5.0, timeout))
        connection.request("GET", "/actuator/health", headers={"Accept": "application/json",
                          "Connection": "close"})
        response = connection.getresponse()
        observation["status"] = response.status
        raw = response.read(16385)
        if len(raw) > 16384:
            observation["transport_error"] = "HEALTH_RESPONSE_TOO_LARGE"
        elif response.getheader("Content-Type", "").lower().startswith("application/json"):
            parsed = strict_json(raw)
            observation["body_sha256"] = digest(parsed)
            if type(parsed) is dict:
                observation["body"] = {"status": parsed.get("status")}
        else:
            observation["transport_error"] = "HEALTH_CONTENT_TYPE"
    except TimeoutError:
        observation["transport_error"] = "TIMEOUT"
    except (ConnectionError, OSError, http.client.HTTPException):
        observation["transport_error"] = "CONNECTION_OR_PROTOCOL_ERROR"
    except Exception:
        observation["transport_error"] = "HEALTH_PARSE_ERROR"
    finally:
        if connection is not None:
            connection.close()
        observation["elapsed_ms"] = max(0, int((time.monotonic() - started) * 1000))
    return observation


class _RedactedLog:
    def __init__(self, process, key: bytes):
        self.process = process
        self.key = key
        self.buffer = bytearray()
        self.leak = threading.Event()
        self.overflow = threading.Event()
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()

    def _drain(self):
        tail = b""
        while True:
            chunk = self.process.stdout.read(4096)
            if not chunk:
                return
            combined = tail + chunk
            if self.key in combined:
                self.leak.set()
            self.buffer.extend(chunk)
            if len(self.buffer) > 4 * 1024 * 1024:
                self.overflow.set()
                return
            tail = combined[-max(1, len(self.key) - 1):]

    def save(self, path: Path) -> dict:
        self.thread.join(timeout=3)
        raw = bytes(self.buffer)
        matches = raw.count(self.key)
        redacted = raw.replace(self.key, b"[REDACTED_CONFIG_CENTER_KEY]")
        _write_exclusive(path, redacted)
        return {"bytes": len(redacted), "sha256": hashlib.sha256(redacted).hexdigest(),
                "key_matches_redacted": matches,
                "overflow": self.overflow.is_set(),
                "reader_stopped": not self.thread.is_alive()}


def _minimal_env(directory: Path, *, api_key: str | None = None) -> dict:
    env = {}
    for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATH"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    env.update({"TEMP": str(directory), "TMP": str(directory),
                "USERPROFILE": str(directory), "APPDATA": str(directory / "appdata"),
                "LOCALAPPDATA": str(directory / "localappdata"),
                "PYTHONDONTWRITEBYTECODE": "1", "OTEL_SDK_DISABLED": "true",
                "LOGFIRE_SEND_TO_LOGFIRE": "false"})
    if api_key is not None:
        env["CONFIG_CENTER_API_KEY"] = api_key
    return env


def _java_args(contracts: dict) -> list[str]:
    effect = contracts["effect"]
    return [str(JAVA), f"-Djava.io.tmpdir={SCENARIO_ROOT / 'java-tmp'}",
            "-jar", str(TASK_JAR_PATH), "--spring.profiles.active=local",
            "--server.address=127.0.0.1",
            f"--server.port={contracts['experiment']['java_port']}",
            "--security.api-keys[0].key=" + "$" + "{CONFIG_CENTER_API_KEY}",
            "--security.api-keys[0].app=" + effect["app"],
            "--security.api-keys[0].env=" + effect["env"]]


def _java_process_report(process, health_observations: list[dict],
                         listener_pid: int | None, external: list[str]) -> dict:
    health = health_observations[-1] if health_observations else {}
    return {
        "executable": "jdk-17/bin/java.exe",
        "version": _load_preflight()["java_identity"]["version"],
        "pid": int(process.pid),
        "listener_pid": listener_pid,
        "health_gets": len(health_observations),
        "health_status": health.get("status"),
        "health_body": health.get("body"),
        "external_connections": external,
        "argv_redacted": [
            "java", "-Djava.io.tmpdir=<task-owned>", "-jar",
            "<task-owned-source>/config-center-server-1.0.0.jar",
            "--spring.profiles.active=local", "--server.address=127.0.0.1",
            "--server.port=<frozen-loopback>",
            "--security.api-keys[0].key=" + "$" + "{CONFIG_CENTER_API_KEY}",
            "--security.api-keys[0].app=<synthetic>",
            "--security.api-keys[0].env=<synthetic>",
        ],
        "exit_code": process.returncode,
        "process_exited": process.poll() is not None,
    }


def _check_initial_state(current: dict, history: dict) -> bool:
    current_body, history_body = current.get("response"), history.get("response")
    return (current.get("status") == 404 and current.get("transport_error") is None
            and current.get("content_type", "").startswith("application/json")
            and type(current_body) is dict
            and set(current_body) == {"code", "message", "data", "traceId"}
            and type(current_body.get("code")) is int and current_body.get("code") == 4041
            and isinstance(current_body.get("message"), str)
            and current_body.get("data") is None
            and (current_body.get("traceId") is None
                 or isinstance(current_body.get("traceId"), str))
            and history.get("status") == 200 and history.get("transport_error") is None
            and history.get("content_type", "").startswith("application/json")
            and type(history_body) is dict
            and set(history_body) == {"code", "message", "data", "traceId"}
            and type(history_body.get("code")) is int and history_body.get("code") == 0
            and isinstance(history_body.get("message"), str)
            and history_body.get("data") == [])


def _communicate_sdk(process, config: bytes, java_log: _RedactedLog | None,
                     timeout_seconds: float) -> tuple[bytes, bytes, str | None]:
    answer = {}
    def communicate():
        try:
            answer["value"] = process.communicate(input=config, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            answer["timeout"] = True
        except Exception:
            answer["error"] = True
    thread = threading.Thread(target=communicate, daemon=True)
    thread.start()
    started = time.monotonic()
    stop_code = None
    while thread.is_alive():
        if java_log is not None and java_log.leak.is_set():
            stop_code = "JAVA_LOG_SECRET_DETECTED"
            break
        if java_log is not None and java_log.overflow.is_set():
            stop_code = "JAVA_LOG_BUDGET_EXCEEDED"
            break
        if time.monotonic() - started >= timeout_seconds:
            stop_code = "SDK_RUNTIME_TIMEOUT"
            break
        time.sleep(0.1)
    if stop_code is not None and process.poll() is None:
        process.terminate()
    thread.join(timeout=12)
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)
    if "value" in answer:
        return answer["value"][0], answer["value"][1], stop_code
    return b"", b"", stop_code or ("SDK_RUNTIME_TIMEOUT" if answer.get("timeout") else "SDK_PROCESS_ERROR")


def _finish_process(process, grace: float = 10) -> bool:
    if process is None:
        return True
    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return False
        except OSError:
            return process.poll() is not None
    return process.poll() is not None


def _evidence_payload(preflight: dict, result: dict) -> dict:
    contracts = preflight["contracts"]
    observations = result["http_observations"]
    tools = result["tool_trace"]
    oracle = evaluate_config_target_effect(contracts["effect"], observations, tools)
    runtime_identity = preflight["sdk_identity"]
    java = result["java_process"]
    fixture = result["fixture_runtime"]
    return {
        "schema_version": CONTRACT_SCHEMA,
        "run_id": contracts["experiment"]["run_id"],
        "preflight_sha256": result["preflight_sha256"],
        "scenario_duration_ms": result["scenario_duration_ms"],
        "contracts": contracts,
        "runtime_source_identity": preflight["runtime_source_identity"],
        "runtime_identity": runtime_identity,
        "java_process": java,
        "fixture_runtime": fixture,
        "http_observations": observations,
        "tool_trace": tools,
        "oracle": oracle,
        "claims": {
            "agent_framework_runtime": "EXECUTED",
            "llm_autonomous_decision": "NOT_PROVEN",
            "target_effect": oracle["outcome"],
            "issuer_authenticity": "NOT_ESTABLISHED",
            "database_independent_authority": "NOT_ESTABLISHED",
            "reproduction": "NOT_TESTED",
            "workswarm": "NOT_PROVEN",
        },
        "security": {
            "business_api_key_in_sdk_child": False,
            "business_api_key_in_argv": False,
            "business_api_key_in_evidence": False,
            "java_log_key_matches": result["java_log"]["key_matches_redacted"],
            "evidence_secret_scan_matches": result["evidence_secret_scan_matches"],
            "provider_https_requests": 0,
        },
        "cleanup": result["cleanup"],
    }


def _wrap_evidence(payload: dict) -> bytes:
    envelope = {"schema_version": CONTRACT_SCHEMA, "source_level": SOURCE_LEVEL,
                "payload": payload, "payload_sha256": digest(payload)}
    return canonical(envelope)


def _verify_rehashed_attacks(payload: dict) -> list[dict]:
    import copy
    attacks = []
    def reject(name, mutation):
        candidate = copy.deepcopy(payload)
        mutation(candidate)
        raw = _wrap_evidence(candidate)
        anchor = hashlib.sha256(raw).hexdigest()
        try:
            verify_bytes(raw, anchor)
        except EvidenceRejected:
            attacks.append({"name": name, "rehashed": True, "rejected": True})
        else:
            raise ProbeError("OFFLINE_NEGATIVE_CONTROL_ACCEPTED_" + name.upper())
    reject("forged_sdk_execution", lambda p: p["fixture_runtime"]["sdk_child"].update(
        status="SKIPPED", exit_code=1))
    reject("swapped_tool_call_id", lambda p: p["tool_trace"][1].update(
        call_id=p["tool_trace"][0]["call_id"]))
    def delete_return(p):
        p["tool_trace"][2].pop("tool_return", None)
        p["fixture_runtime"]["completions"][3]["last_tool_return"] = None
    reject("deleted_tool_return", delete_return)
    def forge_history(p):
        row = p["http_observations"][6]["response"]["data"][0]
        row["version"] = 3
        row["value"] = "rpf52-forged"
        p["http_observations"][6]["response_body_sha256"] = digest(
            p["http_observations"][6]["response"])
        p["oracle"] = evaluate_config_target_effect(
            p["contracts"]["effect"], p["http_observations"], p["tool_trace"])
    reject("forged_final_history", forge_history)
    return attacks


def _reconcile_authority(reader: ConfigTargetAuthorityReader,
                         client: BoundedConfigHttp) -> None:
    client.stop_writes = True
    for kind in ("final_current", "final_history", "final_list"):
        if len(client.observations) >= 8:
            break
        if kind == "final_current":
            reader.current(kind, reconcile=True)
        elif kind == "final_history":
            reader.history(kind, reconcile=True)
        else:
            reader.list(reconcile=True)


def run_scenario() -> dict:
    preflight = _load_preflight()
    _check_frozen(preflight)
    if STARTED_PATH.exists() or STARTED_PATH.is_symlink():
        raise ProbeError("ONE_SHOT_SCENARIO_ALREADY_STARTED")
    if RESULT_PATH.exists() or RESULT_PATH.is_symlink():
        raise ProbeError("SCENARIO_RESULT_ALREADY_EXISTS")
    marker = {
        "plan_id": "RPF-52", "plan_revision": PLAN_REVISION,
        "run_id": preflight["contracts"]["experiment"]["run_id"],
        "started_at_utc": _utc_now(),
        "preflight_sha256": hashlib.sha256(PREFLIGHT_PATH.read_bytes()).hexdigest(),
        "contract_sha256": digest(preflight["contracts"]),
        "one_shot": True, "provider_https_requests": 0,
        "provider_requests": 0, "tokens": 0, "cost_cny": 0,
    }
    _write_exclusive(STARTED_PATH, canonical(marker))
    scenario_started_monotonic = time.monotonic()

    contracts = preflight["contracts"]
    scenario_deadline = scenario_started_monotonic + contracts["execution"]["budgets"][
        "runtime_seconds"]
    java_port = contracts["experiment"]["java_port"]
    agent_port = contracts["experiment"]["agent_host_port"]
    api_key = secrets.token_urlsafe(32)
    api_key_bytes = api_key.encode("ascii")
    java_process = sdk_process = None
    java_log = None
    fixture_host = None
    client = None
    sdk_report = None
    sdk_exit_code = None
    sdk_external = []
    parent_external = []
    health_observations = []
    listener_pid = None
    java_external = []
    java_log_info = {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest(),
                     "key_matches_redacted": 0, "overflow": False}
    stage = "JAVA_START"
    failure_code = None
    process_stopped = host_closed = child_stopped = True
    stderr_sha256 = None
    try:
        java_tmp = SCENARIO_ROOT / "java-tmp"
        sdk_tmp = SCENARIO_ROOT / "sdk-tmp"
        for directory in (java_tmp, sdk_tmp, java_tmp / "appdata",
                          java_tmp / "localappdata", sdk_tmp / "appdata",
                          sdk_tmp / "localappdata"):
            directory.mkdir(exist_ok=True)
        if time.monotonic() >= scenario_deadline:
            raise ProbeError("SCENARIO_DEADLINE_EXCEEDED")
        command = _java_args(contracts)
        if api_key in " ".join(command):
            raise ProbeError("API_KEY_IN_JAVA_ARGV")
        java_process = subprocess.Popen(command, cwd=SCENARIO_ROOT,
            env=_minimal_env(java_tmp, api_key=api_key), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        java_log = _RedactedLog(java_process, api_key_bytes)

        stage = "JAVA_READINESS"
        wait_until = min(time.monotonic() + 120, scenario_deadline)
        while time.monotonic() < wait_until:
            if java_process.poll() is not None:
                raise ProbeError("JAVA_EXITED_BEFORE_READY")
            if java_log.leak.is_set():
                raise ProbeError("JAVA_LOG_SECRET_DETECTED")
            if java_log.overflow.is_set():
                raise ProbeError("JAVA_LOG_BUDGET_EXCEEDED")
            if _listener_is(java_process.pid, java_port):
                listener_pid = java_process.pid
                break
            time.sleep(min(0.5, max(0, scenario_deadline - time.monotonic())))
        if listener_pid != java_process.pid:
            raise ProbeError("JAVA_LISTENER_PID_OR_BIND_MISMATCH")
        health_ok = False
        for _ in range(3):
            remaining = scenario_deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeError("SCENARIO_DEADLINE_EXCEEDED")
            observation = _health_get(java_port, timeout=min(5.0, remaining))
            health_observations.append(observation)
            if (observation["status"] == 200 and observation["transport_error"] is None
                    and type(observation["body"]) is dict
                    and observation["body"].get("status") == "UP"
                    and _listener_is(java_process.pid, java_port)):
                health_ok = True
                break
            if java_process.poll() is not None:
                break
            time.sleep(min(1.0, max(0, scenario_deadline - time.monotonic())))
        if not health_ok:
            raise ProbeError("JAVA_HEALTH_NOT_READY")
        if java_log.leak.is_set():
            raise ProbeError("JAVA_LOG_SECRET_DETECTED")
        java_external = _external_connections(java_process.pid,
                                              allowed_listener_ports={java_port})
        if java_external:
            raise ProbeError("JAVA_EXTERNAL_CONNECTION_OBSERVED")

        stage = "AGENT_HOST_START"
        client = BoundedConfigHttp(contracts, api_key, deadline=scenario_deadline)
        tool_host = ConfigTargetToolHost(contracts, client)
        fixture_host = ConfigTargetFixtureHost(
            contracts, tool_host, preflight["sdk_identity"]["sdk_source_sha256"],
            preflight["sdk_identity"]["openai_source_sha256"])
        fixture_host.start()
        if not _listener_is(os.getpid(), agent_port):
            raise ProbeError("AGENT_HOST_LISTENER_IDENTITY")
        parent_external = _external_connections(
            os.getpid(), allowed_listener_ports={agent_port},
            allowed_remote_ports={java_port})
        if parent_external:
            raise ProbeError("PARENT_PROCESS_NON_LOOPBACK_CONNECTION")

        stage = "AUTHORITY_INITIAL"
        authority = ConfigTargetAuthorityReader(client)
        authority.current("initial_current")
        authority.history("initial_history")
        if not _check_initial_state(client.observations[0], client.observations[1]):
            client.stop_writes = True
            raise ProbeError("INITIAL_NAMESPACE_NOT_EMPTY_OR_UNAVAILABLE")

        stage = "SDK_CHILD_START"
        child_config = {
            "port": agent_port, "run_id": contracts["experiment"]["run_id"],
            "write_root": str(SCENARIO_ROOT), "sdk_readonly_path": str(SDK_SITE_PACKAGES.resolve()),
            "timeout_seconds": max(0, scenario_deadline - time.monotonic()),
        }
        if child_config["timeout_seconds"] <= 0:
            raise ProbeError("SCENARIO_DEADLINE_EXCEEDED")
        child_input = canonical(child_config)
        child_env = _minimal_env(sdk_tmp)
        sdk_command = [str(SDK_PYTHON), "-B", "-I", str(SDK_CHILD)]
        if api_key in " ".join(sdk_command) or api_key in child_input.decode("utf-8"):
            raise ProbeError("API_KEY_IN_SDK_CHILD_INPUT")
        if "CONFIG_CENTER_API_KEY" in child_env:
            raise ProbeError("API_KEY_IN_SDK_CHILD_ENV")
        sdk_process = subprocess.Popen(sdk_command, cwd=SCENARIO_ROOT, env=child_env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        sdk_timeout_seconds = scenario_deadline - time.monotonic()
        if sdk_timeout_seconds <= 0:
            raise ProbeError("SCENARIO_DEADLINE_EXCEEDED")
        sdk_stdout, sdk_stderr, stop_code = _communicate_sdk(
            sdk_process, child_input, java_log, timeout_seconds=sdk_timeout_seconds)
        sdk_exit_code = sdk_process.returncode
        if sdk_stderr:
            stderr_sha256 = hashlib.sha256(sdk_stderr).hexdigest()
        if stop_code:
            raise ProbeError(stop_code)
        if len(sdk_stdout) > 8192:
            raise ProbeError("SDK_REPORT_TOO_LARGE")
        sdk_report, sdk_report_error = parse_sdk_child_report(sdk_stdout, sdk_exit_code)
        if sdk_report_error:
            raise ProbeError(sdk_report_error)
        if (type(sdk_report) is not dict or sdk_exit_code != 0
                or sdk_report.get("status") != "COMPLETED"
                or sdk_report.get("pid") != sdk_process.pid
                or sdk_report.get("framework") != "pydantic-ai-slim"
                or sdk_report.get("version") != "2.57.0"
                or sdk_report.get("openai_version") != "3.35.1"
                or sdk_report.get("requests") != 4
                or sdk_report.get("input_tokens") != 0
                or sdk_report.get("output_tokens") != 0
                or sdk_report.get("tool_calls") != 3
                or sdk_report.get("guard_denials") != []
                or sdk_report.get("final_text_persisted") is not False):
            raise ProbeError("SDK_RUNTIME_OR_USAGE_GATE")
        if (fixture_host.failure is not None or len(fixture_host.completions) != 4
                or len(tool_host.tool_trace) != 3
                or fixture_host.runtime is None
                or fixture_host.runtime.get("pid") != sdk_process.pid):
            raise ProbeError("SDK_TOOL_LOOP_LINEAGE")
        sdk_external = _external_connections(sdk_process.pid,
                                             allowed_remote_ports={agent_port})
        if sdk_external or fixture_host.client_sources != {"127.0.0.1"}:
            raise ProbeError("SDK_NON_LOOPBACK_CONNECTION")

        stage = "AUTHORITY_FINAL"
        authority.current("final_current")
        authority.history("final_history")
        authority.list()
        if (len(client.observations) != 8 or java_process.poll() is not None
                or not _listener_is(java_process.pid, java_port)):
            raise ProbeError("HTTP_REQUEST_BUDGET_OR_ORDER")
        parent_external = _external_connections(
            os.getpid(), allowed_listener_ports={agent_port},
            allowed_remote_ports={java_port})
        if parent_external:
            raise ProbeError("PARENT_PROCESS_NON_LOOPBACK_CONNECTION")
        oracle = evaluate_config_target_effect(contracts["effect"],
            client.observations, tool_host.tool_trace)
        if oracle["outcome"] != "CONTRACT_SATISFIED_IN_RUN":
            raise ProbeError("CONFIG_TARGET_ORACLE_NOT_SATISFIED")
        if java_log.leak.is_set() or java_log.overflow.is_set():
            raise ProbeError("JAVA_LOG_SECRET_OR_SIZE_GATE")
    except Exception as exc:
        failure_code = getattr(exc, "code", None) or type(exc).__name__
        if client is not None and len(client.observations) < 8:
            try:
                _reconcile_authority(ConfigTargetAuthorityReader(client), client)
            except Exception:
                pass
    finally:
        if sdk_process is not None:
            try:
                sdk_external = sorted(set(sdk_external + _external_connections(
                    sdk_process.pid, allowed_remote_ports={agent_port})))
            except Exception:
                sdk_external = sorted(set(sdk_external + ["PROCESS_SOCKET_AUDIT_UNAVAILABLE"]))
        child_stopped = _finish_process(sdk_process, grace=5)
        if fixture_host is not None:
            try:
                fixture_host.close()
            except Exception:
                host_closed = False
        if java_process is not None:
            try:
                java_external = sorted(set(java_external + _external_connections(
                    java_process.pid, allowed_listener_ports={java_port})))
            except Exception:
                java_external = ["PROCESS_SOCKET_AUDIT_UNAVAILABLE"]
            process_stopped = _finish_process(java_process)
            if java_log is not None:
                try:
                    java_log_info = java_log.save(SCENARIO_ROOT / "java-process.log")
                except Exception:
                    java_log_info["save_failed"] = True
        try:
            parent_external = sorted(set(parent_external + _external_connections(
                os.getpid(), allowed_listener_ports={agent_port},
                allowed_remote_ports={java_port})))
        except Exception:
            parent_external = sorted(set(parent_external + ["PROCESS_SOCKET_AUDIT_UNAVAILABLE"]))
        cleanup = {
            "java_process_exited": process_stopped,
            "java_port_closed": _port_free(java_port),
            "agent_host_closed": host_closed and _port_free(agent_port),
            "sdk_child_exited": child_stopped,
            "sdk_child_external_connections": sdk_external,
            "parent_process_external_connections": parent_external,
        }

    scenario_duration_ms = max(0, int((time.monotonic() - scenario_started_monotonic) * 1000))
    runtime_budget_ms = contracts["execution"]["budgets"]["runtime_seconds"] * 1000
    if failure_code is None and scenario_duration_ms > runtime_budget_ms:
        failure_code = "SCENARIO_RUNTIME_BUDGET_EXCEEDED"
    if sdk_report is None or client is None or fixture_host is None:
        sdk_report = sdk_report or {}
    java_report = None
    if java_process is not None:
        java_report = _java_process_report(java_process, health_observations,
                                           listener_pid, java_external)
    tool_trace = (fixture_host.tool_host.tool_trace
                  if fixture_host is not None else [])
    completions = fixture_host.completions if fixture_host is not None else []
    observations = client.observations if client is not None else []
    runtime = preflight["sdk_identity"]
    sdk_child_report = {
        "status": sdk_report.get("status", "NOT_COMPLETED"),
        "framework": sdk_report.get("framework", "pydantic-ai-slim"),
        "version": sdk_report.get("version", "2.57.0"),
        "openai_version": sdk_report.get("openai_version", "3.35.1"),
        "python_version": sdk_report.get("python_version", runtime["python_version"]),
        "pid": sdk_report.get("pid", sdk_process.pid if sdk_process is not None else 0),
        "exit_code": sdk_exit_code if sdk_exit_code is not None else -1,
        "requests": sdk_report.get("requests", 0),
        "input_tokens": sdk_report.get("input_tokens", 0),
        "output_tokens": sdk_report.get("output_tokens", 0),
        "tool_calls": sdk_report.get("tool_calls", len(tool_trace)),
        "guard_denials": sdk_report.get("guard_denials", []),
        "sdk_source_sha256": sdk_report.get("sdk_source_sha256",
            runtime["sdk_source_sha256"]),
        "openai_source_sha256": sdk_report.get("openai_source_sha256",
            runtime["openai_source_sha256"]),
        "final_output_sha256": sdk_report.get("final_output_sha256",
            hashlib.sha256(b"").hexdigest()),
        "final_text_persisted": sdk_report.get("final_text_persisted", True),
    }
    fixture_report = {
        "mode": "FIXTURE_SCRIPTED", "completions": completions,
        "sdk_ready": fixture_host.runtime if fixture_host is not None else None,
        "sdk_child": sdk_child_report,
        "python_network_guard": {
            "allowed_destination": f"127.0.0.1:{agent_port}",
            "external_connections": sdk_external, "is_os_sandbox": False,
            "parent_process_connections": parent_external,
            "host_client_addresses": sorted(
                fixture_host.client_sources if fixture_host is not None else []),
            "denied_attempts": sdk_child_report["guard_denials"],
        },
        "provider_https_attempts": 0, "provider_requests": 0,
        "tokens": sdk_child_report["input_tokens"] + sdk_child_report["output_tokens"],
        "cost_cny": 0,
    }
    result = {
        "plan_id": "RPF-52", "plan_revision": PLAN_REVISION,
        "repo": preflight["repo"], "source": preflight["source"],
        "run_id": contracts["experiment"]["run_id"],
        "scenario_status": "EVIDENCE_READY" if failure_code is None else "PARTIAL",
        "scenario_duration_ms": scenario_duration_ms,
        "failure_code": failure_code, "stage": stage,
        "preflight_sha256": hashlib.sha256(PREFLIGHT_PATH.read_bytes()).hexdigest(),
        "runtime_source_identity": preflight["runtime_source_identity"],
        "java_process": java_report,
        "parent_process_external_connections": parent_external,
        "java_log": java_log_info,
        "http_observations": observations, "tool_trace": tool_trace,
        "fixture_runtime": fixture_report, "cleanup": cleanup,
        "sdk_stderr_sha256": stderr_sha256,
        "sdk_error_stage": sdk_report.get("stage") if type(sdk_report) is dict else None,
        "sdk_error_type": sdk_report.get("error_type") if type(sdk_report) is dict else None,
        "sdk_guard_code": sdk_report.get("guard_code") if type(sdk_report) is dict else None,
        "fixture_host_first_failure_code": (
            fixture_host.first_failure_code if fixture_host is not None else None),
        "provider_https_attempts": 0, "provider_requests": 0,
        "tokens": fixture_report["tokens"], "cost_cny": 0,
    }
    if (java_log_info.get("key_matches_redacted", 0) or java_log_info.get("overflow")
            or java_log_info.get("save_failed")
            or not java_log_info.get("reader_stopped", True)):
        failure_code = failure_code or "JAVA_LOG_SECURITY_OR_SIZE_GATE"
        result["scenario_status"] = "PARTIAL"
        result["failure_code"] = failure_code
    if failure_code is None and not (
            cleanup["java_process_exited"] and cleanup["java_port_closed"]
            and cleanup["agent_host_closed"] and cleanup["sdk_child_exited"]
            and cleanup["sdk_child_external_connections"] == []
            and cleanup["parent_process_external_connections"] == []
            and java_external == []):
        failure_code = "RESOURCE_CLEANUP_FAILED"
        result["scenario_status"] = "PARTIAL"
        result["failure_code"] = failure_code
    if failure_code is None:
        try:
            oracle = evaluate_config_target_effect(contracts["effect"], observations, tool_trace)
            result["oracle"] = oracle
            result["evidence_secret_scan_matches"] = 0
            payload = _evidence_payload(preflight, result)
            evidence_raw = _wrap_evidence(payload)
            secret_matches = 0
            for path in SCENARIO_ROOT.rglob("*"):
                if path.is_file() and api_key_bytes in path.read_bytes():
                    secret_matches += 1
            secret_matches += evidence_raw.count(api_key_bytes)
            if secret_matches or java_log_info.get("key_matches_redacted") != 0:
                raise ProbeError("SECRET_SCAN_FAILED")
            payload["security"]["evidence_secret_scan_matches"] = secret_matches
            evidence_raw = _wrap_evidence(payload)
            expected_sha = hashlib.sha256(evidence_raw).hexdigest()
            if verify_bytes(evidence_raw, expected_sha) != "VERIFIED_ANCHORED":
                raise ProbeError("OFFLINE_ANCHORED_VERIFY_FAILED")
            if verify_bytes(evidence_raw, None) != "UNANCHORED_NOT_PROVEN":
                raise ProbeError("OFFLINE_MISSING_ANCHOR_NOT_REJECTED")
            try:
                verify_bytes(evidence_raw, "0" * 64)
            except EvidenceRejected:
                pass
            else:
                raise ProbeError("OFFLINE_WRONG_ANCHOR_NOT_REJECTED")
            attacks = _verify_rehashed_attacks(payload)
            result.update({"evidence_sha256": expected_sha,
                           "evidence_bytes": len(evidence_raw),
                           "offline_anchor_results": {"correct": 0, "missing": 2, "wrong": 3},
                           "negative_controls": attacks})
            local_raw = canonical(result)
            if api_key_bytes in local_raw:
                raise ProbeError("API_KEY_IN_SCENARIO_RESULT")
            _write_exclusive(EVIDENCE_PATH, evidence_raw)
            saved = EVIDENCE_PATH.read_bytes()
            if hashlib.sha256(saved).hexdigest() != expected_sha:
                raise ProbeError("EVIDENCE_WRITE_SHA_MISMATCH")
            if verify_bytes(saved, expected_sha) != "VERIFIED_ANCHORED":
                raise ProbeError("EVIDENCE_POST_WRITE_VERIFY_FAILED")
            _write_exclusive(RESULT_PATH, local_raw)
            return {"status": "COMPLETE", "run_id": result["run_id"],
                    "evidence_path": "spikes/rpf-52/rev-3/config-target-fixture-evidence.json",
                    "evidence_bytes": len(saved), "evidence_sha256": expected_sha,
                    "http_business_requests": len(observations),
                    "health_gets": len(health_observations),
                    "fixture_completions": len(completions), "tool_calls": len(tool_trace),
                    "provider_https_attempts": 0, "provider_requests": 0,
                    "tokens": result["tokens"], "cost_cny": 0,
                    "java_pid": java_report["pid"], "java_exit_code": java_report["exit_code"],
                    "cleanup": cleanup, "negative_controls": attacks}
        except Exception as exc:
            code = getattr(exc, "code", None)
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,96}", code):
                code = type(exc).__name__.upper()
            failure_code = "EVIDENCE_CLOSEOUT_" + code
            result["scenario_status"] = "PARTIAL"
            result["failure_code"] = failure_code
            result["evidence_file_written"] = EVIDENCE_PATH.is_file()
    if not RESULT_PATH.exists():
        result["oracle"] = (evaluate_config_target_effect(contracts["effect"], observations, tool_trace)
                            if observations else {"outcome": "INCONCLUSIVE", "violations": [],
                                                  "run_outcome": "PLATFORM_ERROR",
                                                  "agent_failure": "NOT_PROVEN",
                                                  "business_violation": "NOT_PROVEN",
                                                  "gaps": ["NO_HTTP_OBSERVATIONS"], "facts": {}})
        local_raw = canonical(result)
        if api_key_bytes in local_raw:
            local_raw = local_raw.replace(api_key_bytes, b"[REDACTED]")
        _write_exclusive(RESULT_PATH, local_raw)
    return {"status": "PARTIAL", "run_id": result["run_id"],
            "stage": result["stage"], "failure_code": result["failure_code"],
            "http_business_requests": len(observations),
            "health_gets": len(health_observations),
            "fixture_completions": len(completions), "tool_calls": len(tool_trace),
            "provider_https_attempts": 0, "provider_requests": 0,
            "tokens": result["tokens"], "cost_cny": 0, "cleanup": cleanup}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--run-scenario", action="store_true")
    action.add_argument("--diagnostic", action="store_true")
    action.add_argument("--finalize-diagnostic", action="store_true")
    parser.add_argument("--attempt", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            result = prepare()
        elif args.run_scenario:
            result = run_scenario()
        else:
            sys.modules.setdefault("probe", sys.modules[__name__])
            diagnostic_root = ROOT / "spikes" / "rpf-52" / "rev-3"
            if not diagnostic_root.is_dir() or _has_symlink(diagnostic_root, ROOT):
                raise ProbeError("SDK_DIAGNOSTIC_DRIVER_UNAVAILABLE")
            sys.path.insert(0, str(diagnostic_root))
            import diagnose
            result = (diagnose.run_attempt(args.attempt) if args.diagnostic
                      else diagnose.finalize_summary())
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["status"] in (
            "PREFLIGHT_FROZEN", "COMPLETE", "PASS", "SUMMARY_WRITTEN") else 2
    except ProbeError as exc:
        print(json.dumps({"status": "BLOCKED", "code": exc.code},
                         sort_keys=True, separators=(",", ":")))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
