"""One-shot RPF-53 preflight, SDK diagnostic, live Provider and evidence workflow."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import http.client
import importlib.metadata as metadata
import ipaddress
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

from runtime.runproof_runtime.effectwitness.config_live_contracts import (
    BASE_SHA, BASE_BRANCH, LIVE_BRANCH, LIMITS, PROVIDER_MODEL, PROVIDER_NAME,
    PROVIDER_ORIGIN, PROVIDER_PATH, SDK_CORE_SHA256, SDK_NAME, SDK_VERSION,
    OPENAI_VERSION, SOURCE_COMMIT, SOURCE_JAR_SHA256, SOURCE_MANIFEST_SHA256,
    canonical, digest, make_contracts, sha256_bytes, strict_json,
)
from runtime.runproof_runtime.effectwitness.config_live_runtime import (
    ConfigLiveBusiness, ConfigLiveHost, ConfigLiveHttp, ConfigLiveMemoryBackend,
    LiveRuntimeRejected, ProviderLedger,
)
from runtime.runproof_runtime.effectwitness.config_live_verify import (
    LiveEvidenceRejected, evaluate_live_effect, verify_bytes, verify_file,
)


WORK_ROOT = ROOT / ".local" / "rpf-53"
PREFLIGHT_DIR = WORK_ROOT / "preflight"
BASE_PREFLIGHT = PREFLIGHT_DIR / "base-preflight.json"
SECOND_BASE_PREFLIGHT = PREFLIGHT_DIR / "base-preflight-attempt-02.json"
PREFLIGHT = PREFLIGHT_DIR / "preflight.json"
DIAGNOSTIC_ROOT = WORK_ROOT / "diagnostic"
SCENARIO_ROOT = WORK_ROOT / "scenario"
QUARANTINE_ROOT = WORK_ROOT / "quarantine"
STARTED_PATH = SCENARIO_ROOT / "started.json"
CONTRACTS_PATH = SCENARIO_ROOT / "contracts.json"
LEDGER_PATH = SCENARIO_ROOT / "provider-ledger.json"
SUMMARY_PATH = ROOT / "spikes" / "rpf-53" / "live-summary.json"
EVIDENCE_PATH = ROOT / "spikes" / "rpf-53" / "config-live-evidence.json"
RESULT_PATH = ROOT / "spikes" / "rpf-53" / "RESULT.md"
SDK_PYTHON = ROOT / ".local" / "rpf-48" / "venv" / "Scripts" / "python.exe"
SDK_SITE = ROOT / ".local" / "rpf-48" / "venv" / "Lib" / "site-packages"
JAVA = Path(r"C:\Program Files\Java\jdk-17\bin\java.exe")
SOURCE_ROOT = ROOT / ".local" / "rpf-51-rev4" / "upstream-config-center"
SOURCE_MANIFEST = ROOT / ".local" / "rpf-51-rev4" / "upstream-source-manifest.json"
SOURCE_JAR = SOURCE_ROOT / "config-center-server" / "target" / "config-center-server-1.0.0.jar"
SOURCE_FILES = (
    "runtime/runproof_runtime/effectwitness/config_live_contracts.py",
    "runtime/runproof_runtime/effectwitness/config_live_runtime.py",
    "runtime/runproof_runtime/effectwitness/config_live_external.py",
    "runtime/runproof_runtime/effectwitness/config_live_verify.py",
    "runtime/tests/test_effectwitness_config_live.py",
    "spikes/rpf-53/probe.py",
)
ALLOWED_DIRS = ("spikes/rpf-53/",)
ALLOWED_FILES = set(SOURCE_FILES) | {
    "spikes/rpf-53/README.md", "spikes/rpf-53/RESULT.md",
    "spikes/rpf-53/live-summary.json", "spikes/rpf-53/config-live-evidence.json",
}
MAX_JAVA_LOG_BYTES = 1_000_000


class ProbeError(RuntimeError):
    def __init__(self, code: str, domain: str = "PLATFORM"):
        self.code, self.domain = code, domain
        super().__init__(code)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _write_once(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ProbeError("TASK_FILE_ALREADY_EXISTS")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + secrets.token_hex(6))
    try:
        with temp.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _git(*args: str, binary: bool = False):
    completed = subprocess.run(["git", *args], cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, check=False)
    if completed.returncode != 0:
        raise ProbeError("GIT_COMMAND_FAILED")
    return completed.stdout if binary else completed.stdout.decode("utf-8", "replace").strip()


def _status_paths() -> list[str]:
    raw = _git("status", "--porcelain=v1", "-z", binary=True)
    entries = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        if len(entry) < 4:
            raise ProbeError("GIT_STATUS_PARSE")
        entries.append(entry[3:].decode("utf-8", "replace"))
    return entries


def _check_status_scope() -> list[str]:
    paths = _status_paths()
    for path in paths:
        if path == "docs/reviews/" or path == "docs/reviews":
            continue
        normalized = path.replace("\\", "/")
        if normalized in ALLOWED_FILES or any(normalized.startswith(prefix) for prefix in ALLOWED_DIRS):
            continue
        raise ProbeError("UNAPPROVED_WORKTREE_CHANGE")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
        raise ProbeError("UNEXPECTED_STAGED_CHANGE")
    return paths


def _remote_refs() -> dict[str, str]:
    output = _git("ls-remote", "--heads", "origin", "refs/heads/main",
                  "refs/heads/" + BASE_BRANCH, "refs/heads/" + LIVE_BRANCH)
    result = {}
    for line in output.splitlines():
        sha, ref = line.split("\t", 1)
        result[ref.removeprefix("refs/heads/")] = sha
    return result


def _check_repo_identity() -> dict:
    top = Path(_git("rev-parse", "--show-toplevel")).resolve()
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    fetch_url = _git("remote", "get-url", "origin")
    push_url = _git("remote", "get-url", "--push", "origin")
    if (top != ROOT.resolve() or branch != LIVE_BRANCH or head != BASE_SHA
            or fetch_url != "https://github.com/MyKr-YSteinsK/runproof.git"
            or push_url != "https://github.com/MyKr-YSteinsK/runproof.git"):
        raise ProbeError("REPOSITORY_IDENTITY_MISMATCH")
    refs = _remote_refs()
    if (refs.get("main") != "bda0cd49e50e3181f604324e94877a24b9885334"
            or refs.get(BASE_BRANCH) != BASE_SHA or LIVE_BRANCH in refs):
        raise ProbeError("REMOTE_BASE_OR_TARGET_CHANGED")
    status = _check_status_scope()
    if "docs/reviews/" not in status and "docs/reviews" not in status:
        # The path is protected; its prior untracked presence is part of this task baseline.
        raise ProbeError("PROTECTED_USER_DIRECTORY_STATUS_CHANGED")
    return {"root": str(top), "branch": branch, "head": head,
            "origin_fetch": fetch_url, "origin_push": push_url,
            "main_sha": refs["main"], "base_branch_sha": refs[BASE_BRANCH],
            "target_remote_absent": True, "status_paths": status,
            "docs_reviews_untracked_untouched": True}


def _check_worktree_directories() -> None:
    for path in (ROOT / "spikes" / "rpf-53", WORK_ROOT):
        if path.is_symlink():
            raise ProbeError("TASK_ROOT_IS_SYMLINK")
    if not (ROOT / "spikes" / "rpf-53").is_dir():
        raise ProbeError("SPIKE_DIRECTORY_MISSING")
    if not WORK_ROOT.exists():
        WORK_ROOT.mkdir()
    if not WORK_ROOT.is_dir() or WORK_ROOT.is_symlink():
        raise ProbeError("TASK_LOCAL_ROOT_INVALID")
    expected = {"preflight", "diagnostic", "scenario", "quarantine", "tests"}
    for child in WORK_ROOT.iterdir():
        if child.name not in expected or child.is_symlink():
            raise ProbeError("TASK_LOCAL_ROOT_NOT_EXCLUSIVE")
    for name in expected:
        (WORK_ROOT / name).mkdir(exist_ok=True)


def _verify_source_bundle() -> dict:
    if SOURCE_ROOT.is_symlink() or SOURCE_MANIFEST.is_symlink() or SOURCE_JAR.is_symlink():
        raise ProbeError("SOURCE_PATH_IS_LINK")
    raw = SOURCE_MANIFEST.read_bytes()
    if sha256_bytes(raw) != SOURCE_MANIFEST_SHA256:
        raise ProbeError("SOURCE_MANIFEST_SHA256_MISMATCH")
    try:
        manifest = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        raise ProbeError("SOURCE_MANIFEST_INVALID") from None
    if (type(manifest) is not dict or set(manifest) != {
            "source_commit", "file_count", "total_bytes", "files"}
            or manifest["source_commit"] != SOURCE_COMMIT
            or manifest["file_count"] != 110 or type(manifest["files"]) is not list
            or len(manifest["files"]) != 110 or manifest["total_bytes"] != 393800):
        raise ProbeError("SOURCE_MANIFEST_IDENTITY")
    seen, total = set(), 0
    for item in manifest["files"]:
        if type(item) is not dict or set(item) != {"path", "bytes", "sha256"}:
            raise ProbeError("SOURCE_MANIFEST_ENTRY")
        relative = PurePosixPath(item["path"].replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts or item["path"] in seen:
            raise ProbeError("SOURCE_MANIFEST_PATH")
        seen.add(item["path"])
        path = SOURCE_ROOT.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            raise ProbeError("SOURCE_FILE_MISSING_OR_LINK")
        data = path.read_bytes()
        if len(data) != item["bytes"] or sha256_bytes(data) != item["sha256"]:
            raise ProbeError("SOURCE_FILE_DIGEST_MISMATCH")
        total += len(data)
    if total != 393800:
        raise ProbeError("SOURCE_TREE_BYTE_COUNT")
    if not SOURCE_JAR.is_file() or SOURCE_JAR.stat().st_size != 66981576:
        raise ProbeError("SOURCE_JAR_SIZE")
    jar_sha = _sha_file(SOURCE_JAR)
    if jar_sha != SOURCE_JAR_SHA256:
        raise ProbeError("SOURCE_JAR_SHA256_MISMATCH")
    return {"source_commit": SOURCE_COMMIT, "manifest_sha256": SOURCE_MANIFEST_SHA256,
            "source_file_count": 110, "source_total_bytes": total,
            "jar_bytes": SOURCE_JAR.stat().st_size, "jar_sha256": jar_sha}


def _sdk_identity() -> dict:
    if not SDK_PYTHON.is_file() or SDK_PYTHON.is_symlink() or not SDK_SITE.is_dir():
        raise ProbeError("PINNED_SDK_RUNTIME_MISSING")
    script = r'''
import base64, csv, hashlib, importlib.metadata as md, inspect, json, pathlib, sys
from openai import AsyncOpenAI
from pydantic_ai import Agent
base=pathlib.Path(sys.prefix,"Lib","site-packages").resolve()
venv_root=pathlib.Path(sys.prefix).resolve()
dists={d.metadata.get("Name","").lower().replace("-","_"):d for d in md.distributions(path=[str(base)])}
def inspect_dist(key,expected):
 d=dists[key]; record=pathlib.Path(d._path)/"RECORD"
 with record.open(encoding="utf-8",newline="") as f: rows=list(csv.reader(f))
 hashed=mismatch=0
 for row in rows:
  if len(row)<2 or not row[1]: continue
  rel=pathlib.PurePosixPath(row[0].replace("\\","/"))
  if rel.is_absolute(): raise RuntimeError("RECORD_PATH")
  target=base.joinpath(*rel.parts).resolve()
  if target!=venv_root and venv_root not in target.parents: raise RuntimeError("RECORD_PATH")
  if target.is_symlink() or not target.is_file(): raise RuntimeError("RECORD_FILE")
  data=target.read_bytes(); alg, encoded=row[1].split("=",1)
  if alg!="sha256": raise RuntimeError("RECORD_HASH_ALGORITHM")
  hashed+=1
  actual=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
  if actual!=encoded: mismatch+=1
 if d.version!=expected: raise RuntimeError("SDK_VERSION")
 return {"version":d.version,"record_entries":len(rows),"record_hashed_entries":hashed,
         "record_mismatches":mismatch,"record_sha256":hashlib.sha256(record.read_bytes()).hexdigest()}
p=inspect_dist("pydantic_ai_slim","2.57.0")
o=inspect_dist("openai","3.35.1")
core=pathlib.Path(inspect.getfile(Agent)).resolve()
openai_core=pathlib.Path(inspect.getfile(AsyncOpenAI)).resolve()
result={"python_version":sys.version.split()[0],"python_executable_sha256":hashlib.sha256(pathlib.Path(sys.executable).read_bytes()).hexdigest(),
 "pydantic":p,"openai":o,"sdk_core_sha256":hashlib.sha256(core.read_bytes()).hexdigest(),
 "openai_core_sha256":hashlib.sha256(openai_core.read_bytes()).hexdigest()}
print(json.dumps(result,sort_keys=True,separators=(",",":")))
'''
    result = subprocess.run([str(SDK_PYTHON), "-B", "-X", "utf8", "-c", script], cwd=ROOT,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=30, check=False)
    if result.returncode != 0 or result.stderr:
        raise ProbeError("PINNED_SDK_RECORD_VERIFY_FAILED")
    try:
        value = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise ProbeError("PINNED_SDK_IDENTITY_INVALID") from None
    if (value.get("python_version") != "3.12.13"
            or value.get("sdk_core_sha256") != SDK_CORE_SHA256
            or value.get("pydantic", {}).get("version") != SDK_VERSION
            or value.get("pydantic", {}).get("record_entries") != 444
            or value.get("pydantic", {}).get("record_hashed_entries") != 443
            or value.get("pydantic", {}).get("record_mismatches") != 0
            or value.get("openai", {}).get("version") != OPENAI_VERSION
            or value.get("openai", {}).get("record_entries") != 2000
            or value.get("openai", {}).get("record_hashed_entries") != 1999
            or value.get("openai", {}).get("record_mismatches") != 0):
        raise ProbeError("PINNED_SDK_IDENTITY_MISMATCH")
    return value


def _java_identity() -> dict:
    if not JAVA.is_file() or JAVA.is_symlink():
        raise ProbeError("DIRECT_JDK17_MISSING")
    java_tmp = WORK_ROOT / "preflight" / "java-tmp"
    java_tmp.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(JAVA), f"-Djava.io.tmpdir={java_tmp}", "-version"],
                            cwd=java_tmp, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30, check=False)
    version_text = result.stderr.decode("utf-8", "replace")
    match = re.search(r'java version "([0-9.]+)', version_text)
    if result.returncode != 0 or not match or match.group(1) != "17.0.12":
        raise ProbeError("DIRECT_JDK17_IDENTITY_MISMATCH")
    return {"version": match.group(1), "executable_sha256": _sha_file(JAVA)}


def _runtime_source_identity() -> dict:
    files = {}
    for name in SOURCE_FILES:
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            raise ProbeError("RUNTIME_SOURCE_MISSING_OR_LINK")
        files[name] = _sha_file(path)
    return {"files": files, "sha256": digest(files)}


def _check_key_presence() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def _preflight() -> dict:
    repo = _check_repo_identity()
    source = _verify_source_bundle()
    sdk = _sdk_identity()
    java = _java_identity()
    runtime = _runtime_source_identity()
    if (sdk["sdk_core_sha256"] != SDK_CORE_SHA256
            or source["manifest_sha256"] != SOURCE_MANIFEST_SHA256):
        raise ProbeError("A01_SOURCE_IDENTITY")
    return {
        "schema_version": "rpf53-base-preflight-v1",
        "plan_id": "RPF-53", "plan_revision": "rev-1", "checked_at_utc": _utc(),
        "repo": repo, "source": source, "sdk": sdk, "java": java,
        "runtime_source": runtime,
        "provider": {"key_present": _check_key_presence(),
            "name": PROVIDER_NAME, "origin": PROVIDER_ORIGIN,
            "model": PROVIDER_MODEL, "path": PROVIDER_PATH,
            "official_pricing_url": "https://api-docs.deepseek.com/quick_start/pricing/",
            "official_tool_calls_url": "https://api-docs.deepseek.com/guides/tool_calls/",
            "official_chat_completion_url": "https://api-docs.deepseek.com/api/create-chat-completion/",
            "peak_input_usd_per_million_cache_miss": 0.30,
            "peak_output_usd_per_million": 1.20,
            "budget_conversion_multiplier_cny_per_usd": 15.0,
            "budget_input_cny_per_million_bound": LIMITS["input_cny_per_million_peak_bound"],
            "budget_output_cny_per_million_bound": LIMITS["output_cny_per_million_peak_bound"],
            "conversion_multiplier_is_fx_quote": False,
            "maximum_cost_estimate_cny": LIMITS["estimated_cost_cny_upper"],
            "maximum_token_usage": LIMITS["total_tokens"]},
        "push_effect": {"release_gate_push_branch": "main",
            "feature_branch_push_triggers_release_gate": False,
            "release_or_deploy": "NOT_CONFIGURED_FOR_THIS_FEATURE_BRANCH"},
    }


def prepare() -> dict:
    _check_worktree_directories()
    if BASE_PREFLIGHT.exists() or BASE_PREFLIGHT.is_symlink() or PREFLIGHT.exists() or PREFLIGHT.is_symlink():
        raise ProbeError("PREFLIGHT_ALREADY_FROZEN")
    value = _preflight()
    _write_once(BASE_PREFLIGHT, canonical(value))
    return value


def _load_base_preflight(path: Path = BASE_PREFLIGHT) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ProbeError("BASE_PREFLIGHT_NOT_RUN")
    value = strict_json(path.read_bytes())
    current = _preflight()
    if (value.get("repo") != current.get("repo")
            or value.get("source") != current.get("source")
            or value.get("sdk") != current.get("sdk")
            or value.get("java") != current.get("java")
            or value.get("runtime_source") != current.get("runtime_source")):
        raise ProbeError("PREFLIGHT_SOURCE_DRIFT")
    return value


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _sdk_env(home: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH") if key in os.environ}
    env.update({"HOME": str(home), "USERPROFILE": str(home), "TEMP": str(home),
                "TMP": str(home), "PYTHONDONTWRITEBYTECODE": "1",
                "OTEL_SDK_DISABLED": "true", "LOGFIRE_SEND_TO_LOGFIRE": "false"})
    return env


def _offline_fake_failure_control(base: dict, tools: list[dict], tool_schema_sha256: str,
                                  attempt: int) -> dict:
    suffix = uuid.uuid4().hex[:16]
    run_id = "rpf53-faildiag-" + suffix
    port = _free_port()
    identity = base["sdk"]
    contracts = make_contracts(run_id=run_id, suffix=suffix, java_port=None,
        agent_port=port, prepared_at_utc=_utc(),
        runtime_source_sha256=base["runtime_source"]["sha256"],
        sdk_identity={
            "python_version": identity["python_version"],
            "python_executable_sha256": identity["python_executable_sha256"],
            "pydantic_record_sha256": identity["pydantic"]["record_sha256"],
            "pydantic_record_entries": identity["pydantic"]["record_entries"],
            "pydantic_record_mismatches": identity["pydantic"]["record_mismatches"],
            "openai_record_sha256": identity["openai"]["record_sha256"],
            "openai_record_entries": identity["openai"]["record_entries"],
            "openai_record_mismatches": identity["openai"]["record_mismatches"],
            "openai_core_sha256": identity["openai_core_sha256"],
        }, mode="FIXTURE_TEST_ONLY")
    ledger = ProviderLedger.fixture_only(run_id)
    host = ConfigLiveHost(contracts, ledger, ConfigLiveMemoryBackend(), fixture=True,
        expected_tool_schema_sha256=tool_schema_sha256,
        fixture_failure_code="OFFLINE_REPLAY_PROVIDER_HTTP_503")
    negative_dir = SCENARIO_ROOT / f"sdk-diagnostic-negative-{attempt:02d}"
    negative_dir.mkdir(exist_ok=False)
    process = None
    stdout = stderr = b""
    try:
        host.start(port)
        config = {"port": port, "token": host.token,
            "write_root": str(negative_dir),
            "instructions": contracts["execution"]["agent_instructions"],
            "task_prompt": contracts["execution"]["task_prompt"],
            "model": "rpf53-fixture-only", "max_runtime_seconds": 60,
            "fixture": True}
        process = subprocess.Popen([str(SDK_PYTHON), "-I", "-B",
            str(ROOT / "runtime/runproof_runtime/effectwitness/config_live_external.py")],
            cwd=negative_dir, env=_sdk_env(negative_dir), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(canonical(config), timeout=90)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
        report = strict_json(stdout) if stdout and len(stdout) <= 8192 else {}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=10)
        host.close()
    passed = (process is not None and process.returncode == 1 and not stderr
        and type(report) is dict and set(report) == {
            "status", "stage", "error_type", "guard_code", "guard_denials",
            "denied_file_basenames"}
        and report["status"] == "SDK_ERROR" and report["stage"] == "sdk_run"
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", report["error_type"]) is not None
        and report["guard_denials"] == []
        and report["denied_file_basenames"] == []
        and host.failure == {"domain": "PROVIDER", "code": "OFFLINE_REPLAY_PROVIDER_HTTP_503"}
        and ledger.usage()["provider_https_requests"] == 0 and not host.tool_trace
        and process.poll() is not None and host._server is None)
    return {"status": "PASS" if passed else "FAIL", "source": "OFFLINE_REPLAY",
        "provider_https_requests": 0, "business_http_requests": 0, "java_processes": 0,
        "host_http_status": 502, "host_failure": host.failure,
        "sdk_status": report.get("status") if type(report) is dict else None,
        "sdk_stage": report.get("stage") if type(report) is dict else None,
        "sdk_error_type": report.get("error_type") if type(report) is dict else None,
        "sdk_exit_code": process.returncode if process else None,
        "sdk_stdout_sha256": sha256_bytes(stdout), "sdk_stderr_bytes": len(stderr),
        "sdk_stderr_sha256": sha256_bytes(stderr), "tool_calls": len(host.tool_trace)}


def _diagnostic_attempt_context() -> tuple[dict, int, Path, Path]:
    first_dir = DIAGNOSTIC_ROOT / "attempt-01"
    second_dir = DIAGNOSTIC_ROOT / "attempt-02"
    if not first_dir.exists() and not first_dir.is_symlink():
        if (second_dir.exists() or second_dir.is_symlink()
                or PREFLIGHT.exists() or PREFLIGHT.is_symlink()
                or SECOND_BASE_PREFLIGHT.exists() or SECOND_BASE_PREFLIGHT.is_symlink()):
            raise ProbeError("DIAGNOSTIC_ATTEMPT_STATE_INVALID")
        return _load_base_preflight(BASE_PREFLIGHT), 1, first_dir, BASE_PREFLIGHT

    if (first_dir.is_symlink() or not first_dir.is_dir()
            or second_dir.exists() or second_dir.is_symlink()
            or PREFLIGHT.exists() or PREFLIGHT.is_symlink()
            or SECOND_BASE_PREFLIGHT.exists() or SECOND_BASE_PREFLIGHT.is_symlink()):
        raise ProbeError("DIAGNOSTIC_ATTEMPT_STATE_INVALID")
    started_path = first_dir / "started.json"
    result_path = first_dir / "result.json"
    if (started_path.is_symlink() or not started_path.is_file()
            or result_path.is_symlink() or not result_path.is_file()):
        raise ProbeError("SECOND_DIAGNOSTIC_ATTEMPT_NOT_AUTHORIZED")
    started = strict_json(started_path.read_bytes())
    result = strict_json(result_path.read_bytes())
    report = result.get("sdk_report") if type(result) is dict else None
    fake_control = result.get("fake_transport_negative_control") if type(result) is dict else None
    if (type(started) is not dict or type(result) is not dict
            or started.get("plan_id") != "RPF-53"
            or started.get("attempt") != 1 or started.get("model_source") != "FIXTURE_TEST_ONLY"
            or started.get("run_id") != result.get("run_id")
            or result.get("schema_version") != "rpf53-sdk-diagnostic-v1"
            or result.get("status") != "FAIL"
            or result.get("provider_https_requests") != 0
            or result.get("business_http_requests") != 0
            or result.get("java_processes") != 0
            or result.get("sdk_exit_code") != 1
            or result.get("stderr_bytes") != 0
            or result.get("tool_trace") != [] or result.get("tool_schema_sha256") is not None
            or result.get("fake_backend_calls") != []
            or type(fake_control) is not dict or fake_control.get("status") != "NOT_RUN"
            or result.get("failure") is not None
            or type(report) is not dict
            or report.get("status") != "SDK_ERROR"
            or report.get("stage") != "sdk_import"
            or report.get("error_type") != "PermissionError"
            or report.get("guard_code") != "RPF53_FILE_ACCESS_DENIED"
            or report.get("guard_denials") != ["FILE_ACCESS_DENIED"]):
        raise ProbeError("SECOND_DIAGNOSTIC_ATTEMPT_NOT_AUTHORIZED")

    if not BASE_PREFLIGHT.is_file() or BASE_PREFLIGHT.is_symlink():
        raise ProbeError("BASE_PREFLIGHT_NOT_RUN")
    original = strict_json(BASE_PREFLIGHT.read_bytes())
    current = _preflight()
    for key in ("repo", "source", "sdk", "java"):
        if original.get(key) != current.get(key):
            raise ProbeError("PREFLIGHT_SOURCE_DRIFT")
    if (original.get("runtime_source") == current.get("runtime_source")
            or original.get("runtime_source", {}).get("sha256")
               == current.get("runtime_source", {}).get("sha256")):
        raise ProbeError("SECOND_ATTEMPT_SOURCE_NOT_REPAIRED")
    _write_once(SECOND_BASE_PREFLIGHT, canonical(current))
    return current, 2, second_dir, SECOND_BASE_PREFLIGHT


def run_diagnostic() -> dict:
    base, attempt, attempt_dir, base_path = _diagnostic_attempt_context()
    attempt_dir.mkdir(parents=True)
    sdk_dir = SCENARIO_ROOT / f"sdk-diagnostic-{attempt:02d}"
    sdk_dir.mkdir(exist_ok=False)
    suffix = uuid.uuid4().hex[:16]
    run_id = "rpf53-diag-" + suffix
    host_port = _free_port()
    contracts = make_contracts(run_id=run_id, suffix=suffix, java_port=None,
        agent_port=host_port, prepared_at_utc=_utc(),
        runtime_source_sha256=base["runtime_source"]["sha256"],
        sdk_identity={
            "python_version": base["sdk"]["python_version"],
            "python_executable_sha256": base["sdk"]["python_executable_sha256"],
            "pydantic_record_sha256": base["sdk"]["pydantic"]["record_sha256"],
            "pydantic_record_entries": base["sdk"]["pydantic"]["record_entries"],
            "pydantic_record_mismatches": base["sdk"]["pydantic"]["record_mismatches"],
            "openai_record_sha256": base["sdk"]["openai"]["record_sha256"],
            "openai_record_entries": base["sdk"]["openai"]["record_entries"],
            "openai_record_mismatches": base["sdk"]["openai"]["record_mismatches"],
            "openai_core_sha256": base["sdk"]["openai_core_sha256"],
        }, mode="FIXTURE_TEST_ONLY")
    marker = {"plan_id": "RPF-53", "attempt": attempt, "run_id": run_id,
              "started_at_utc": _utc(), "model_source": "FIXTURE_TEST_ONLY",
              "base_preflight_sha256": _sha_file(base_path),
              "provider_https_requests": 0, "business_http_requests": 0,
              "java_processes": 0, "one_shot": True}
    _write_once(attempt_dir / "started.json", canonical(marker))
    ledger = ProviderLedger.fixture_only(run_id)
    backend = ConfigLiveMemoryBackend()
    host = ConfigLiveHost(contracts, ledger, backend, fixture=True)
    process = None
    report = None
    stdout = stderr = b""
    try:
        host.start(host_port)
        config = {"port": host.port, "token": host.token,
                  "write_root": str(sdk_dir), "instructions": contracts["execution"]["agent_instructions"],
                  "task_prompt": contracts["execution"]["task_prompt"],
                  "model": "rpf53-fixture-only", "max_runtime_seconds": 360,
                  "fixture": True}
        process = subprocess.Popen([str(SDK_PYTHON), "-I", "-B",
            str(ROOT / "runtime/runproof_runtime/effectwitness/config_live_external.py")],
            cwd=sdk_dir, env=_sdk_env(sdk_dir), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(canonical(config), timeout=360)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
        if stdout and len(stdout) <= 8192:
            report = strict_json(stdout)
    finally:
        host.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=10)
    passed = (process is not None and process.returncode == 0
        and type(report) is dict and report.get("status") == "COMPLETED"
        and report.get("framework") == SDK_NAME and report.get("version") == SDK_VERSION
        and report.get("openai_version") == OPENAI_VERSION
        and report.get("sdk_source_sha256") == SDK_CORE_SHA256
        and report.get("openai_source_sha256") == base["sdk"]["openai_core_sha256"]
        and report.get("provider_key_present") is False
        and report.get("business_key_present") is False
        and report.get("guard_denials") == []
        and report.get("requests") == 4 and report.get("tool_calls") == 3
        and report.get("tool_callbacks") == 3
        and len(host.tool_trace) == 3 and len(backend.calls) == 3
        and host.failure is None and not stderr
        and ledger.usage()["provider_https_requests"] == 0)
    fake_negative = _offline_fake_failure_control(base, host.tool_definitions or [],
        host.tool_schema_sha256 or "", attempt) if passed else {
        "status": "NOT_RUN", "source": "OFFLINE_REPLAY", "provider_https_requests": 0}
    passed = passed and fake_negative["status"] == "PASS"
    result = {"schema_version": "rpf53-sdk-diagnostic-v1", "run_id": run_id,
        "status": "PASS" if passed else "FAIL", "model_source": "FIXTURE_TEST_ONLY",
        "provider_https_requests": 0, "business_http_requests": 0, "java_processes": 0,
        "sdk_report": report if type(report) is dict else None,
        "tool_trace": host.tool_trace, "fake_backend_calls": backend.calls,
        "fake_transport_negative_control": fake_negative,
        "tool_schema_sha256": host.tool_schema_sha256,
        "failure": host.failure,
        "sdk_exit_code": process.returncode if process else None,
        "stdout_sha256": sha256_bytes(stdout), "stderr_bytes": len(stderr),
        "stderr_sha256": sha256_bytes(stderr), "completed_at_utc": _utc()}
    _write_once(attempt_dir / "result.json", canonical(result))
    if not passed:
        raise ProbeError("SDK_FIXTURE_DIAGNOSTIC_FAILED")
    preflight = {"schema_version": "rpf53-preflight-v1", "base": base,
                 "diagnostic": {"attempt": attempt, "status": "PASS",
                    "base_preflight_path": str(base_path.relative_to(ROOT)).replace("\\", "/"),
                    "base_preflight_sha256": _sha_file(base_path),
                    "result_sha256": _sha_file(attempt_dir / "result.json"),
                    "tool_schema_sha256": host.tool_schema_sha256}}
    _write_once(PREFLIGHT, canonical(preflight))
    return preflight


def _netstat_rows() -> list[dict]:
    result = subprocess.run(["netstat", "-ano", "-p", "tcp"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=15, check=False)
    if result.returncode != 0:
        raise ProbeError("NETSTAT_UNAVAILABLE")
    rows = []
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) != 5 or parts[0].upper() != "TCP":
            continue
        local, remote, state, pid_text = parts[1:]
        if not pid_text.isdigit():
            continue
        rows.append({"local": local, "remote": remote, "state": state.upper(),
                     "pid": int(pid_text)})
    return rows


def _endpoint_port(endpoint: str) -> int | None:
    try:
        return int(endpoint.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None


def _listener_owned(pid: int, port: int) -> bool:
    return any(row["pid"] == pid and row["state"] == "LISTENING"
               and _endpoint_port(row["local"]) == port for row in _netstat_rows())


def _port_closed(port: int) -> bool:
    if any(row["state"] == "LISTENING" and _endpoint_port(row["local"]) == port
           for row in _netstat_rows()):
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _external_connections(pid: int) -> list[dict]:
    external = []
    for row in _netstat_rows():
        if row["pid"] != pid or row["state"] not in ("ESTABLISHED", "SYN_SENT", "SYN_RECEIVED"):
            continue
        remote = row["remote"].rsplit(":", 1)[0].strip("[]")
        try:
            address = ipaddress.ip_address(remote)
        except ValueError:
            external.append({"state": row["state"], "remote": "UNPARSEABLE"})
            continue
        if not address.is_loopback:
            external.append({"state": row["state"], "remote": "NON_LOOPBACK"})
    return external


def _health_get(port: int, timeout: float = 5.0) -> dict:
    connection = None
    result = {"method": "GET", "path": "/actuator/health", "status": None,
              "content_type": None, "body": None, "transport_error": None}
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        connection.request("GET", "/actuator/health", headers={
            "Accept": "application/json", "Connection": "close"})
        response = connection.getresponse()
        result["status"] = response.status
        result["content_type"] = response.getheader("Content-Type", "").lower()
        body = response.read(16385)
        if len(body) > 16384:
            result["transport_error"] = "RESPONSE_TOO_LARGE"
        else:
            result["body"] = strict_json(body)
    except TimeoutError:
        result["transport_error"] = "TIMEOUT"
    except (OSError, http.client.HTTPException):
        result["transport_error"] = "CONNECTION_OR_PROTOCOL_ERROR"
    finally:
        if connection is not None:
            connection.close()
    return result


class _RedactedJavaLog:
    def __init__(self, process: subprocess.Popen, secret: bytes):
        self.process, self.secret = process, secret
        self.buffer = bytearray()
        self.digest = hashlib.sha256()
        self.total = 0
        self.redactions = 0
        self.overflow = False
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()

    def _append(self, data: bytes) -> None:
        self.total += len(data)
        self.digest.update(data)
        if len(self.buffer) + len(data) > MAX_JAVA_LOG_BYTES:
            self.overflow = True
            return
        self.buffer.extend(data)

    def _drain(self) -> None:
        assert self.process.stdout is not None
        pending = b""
        overlap = max(0, len(self.secret) - 1)
        while True:
            block = self.process.stdout.read(4096)
            if not block:
                break
            combined = pending + block
            if overlap and len(combined) > overlap:
                safe, pending = combined[:-overlap], combined[-overlap:]
            else:
                safe, pending = b"", combined
            self.redactions += safe.count(self.secret)
            self._append(safe.replace(self.secret, b"[REDACTED]"))
        self.redactions += pending.count(self.secret)
        self._append(pending.replace(self.secret, b"[REDACTED]"))

    def close(self, path: Path) -> dict:
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            return {"log_saved": False, "overflow": True, "redactions": self.redactions}
        if self.buffer and not path.exists() and not path.is_symlink():
            _write_once(path, bytes(self.buffer))
        return {"log_saved": bool(path.exists()), "bytes": len(self.buffer),
                "sha256": self.digest.hexdigest(), "redactions": self.redactions,
                "overflow": self.overflow}


def _java_env(temp_dir: Path, api_key: str) -> dict[str, str]:
    system = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR") or r"C:\Windows"
    env = {"SYSTEMROOT": system, "WINDIR": system,
           "JAVA_HOME": str(JAVA.parent.parent),
           "PATH": str(JAVA.parent) + os.pathsep + str(Path(system) / "System32"),
           "TEMP": str(temp_dir), "TMP": str(temp_dir),
           "CONFIG_CENTER_API_KEY": api_key,
           "SERVER_ADDRESS": "127.0.0.1"}
    return env


def _start_java(contracts: dict, api_key: str, scenario: Path):
    temp_dir = scenario / "java-tmp"
    temp_dir.mkdir(exist_ok=False)
    effect = contracts["effect"]
    port = contracts["experiment"]["java_port"]
    args = [str(JAVA), f"-Djava.io.tmpdir={temp_dir}", "-jar", str(SOURCE_JAR),
            "--spring.profiles.active=local", "--server.address=127.0.0.1",
            f"--server.port={port}", "--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}",
            "--security.api-keys[0].app=" + effect["app"],
            "--security.api-keys[0].env=" + effect["env"]]
    if api_key.encode("ascii") in " ".join(args).encode("ascii"):
        raise ProbeError("API_KEY_IN_JAVA_ARGV")
    process = subprocess.Popen(args, cwd=scenario, env=_java_env(temp_dir, api_key),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        bufsize=0)
    log = _RedactedJavaLog(process, api_key.encode("ascii"))
    return process, log


def _wait_for_java(process: subprocess.Popen, port: int, log: _RedactedJavaLog,
                   deadline: float, health_observations: list[dict]) -> bool:
    listener_ok = False
    until = min(deadline, time.monotonic() + 150)
    while time.monotonic() < until:
        if process.poll() is not None or log.overflow:
            return False
        try:
            if _listener_owned(process.pid, port):
                listener_ok = True
                break
        except ProbeError:
            return False
        time.sleep(0.25)
    if not listener_ok:
        return False
    while len(health_observations) < LIMITS["health_gets"] and time.monotonic() < deadline:
        item = _health_get(port, timeout=min(5.0, max(0.1, deadline - time.monotonic())))
        health_observations.append(item)
        if (item["status"] == 200 and item["transport_error"] is None
                and type(item["body"]) is dict and item["body"].get("status") == "UP"
                and _listener_owned(process.pid, port)):
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.5)
    return False


def _sdk_report(stdout: bytes, stderr: bytes, process: subprocess.Popen) -> dict | None:
    if process.returncode != 0 or stderr or not stdout or len(stdout) > 8192:
        return None
    try:
        value = strict_json(stdout)
    except Exception:
        return None
    expected = {"status", "framework", "version", "openai_version", "pid", "requests",
        "input_tokens", "output_tokens", "tool_calls", "tool_callbacks",
        "sdk_source_sha256", "openai_source_sha256", "final_output_sha256",
        "final_text_persisted", "guard_denials", "provider_key_present",
        "business_key_present"}
    return value if type(value) is dict and set(value) == expected else None


def _live_preflight() -> dict:
    if not PREFLIGHT.is_file() or PREFLIGHT.is_symlink():
        raise ProbeError("A03_DIAGNOSTIC_NOT_PASSED")
    value = strict_json(PREFLIGHT.read_bytes())
    if (value.get("schema_version") != "rpf53-preflight-v1"
            or value.get("diagnostic", {}).get("status") != "PASS"
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("diagnostic", {}).get("tool_schema_sha256", ""))):
        raise ProbeError("A03_DIAGNOSTIC_NOT_PASSED")
    base = value.get("base")
    current = _preflight()
    for key in ("repo", "source", "sdk", "java", "runtime_source"):
        if base.get(key) != current.get(key):
            raise ProbeError("PREFLIGHT_SOURCE_DRIFT")
    if not current["provider"]["key_present"]:
        raise ProbeError("DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
    return value


def _public_attempt(record: dict) -> dict:
    fields = ("attempt", "run_id", "request_sha256", "reservation_tokens", "status",
        "transport", "response_id", "returned_model", "usage", "tool_schema_sha256",
        "tool_call_ids", "returned_tool_ids", "tool_returns")
    return {key: record.get(key) for key in fields}


def _make_payload(preflight: dict, contracts: dict, source_identity: dict,
                  report: dict, host: ConfigLiveHost, ledger: ProviderLedger,
                  client: ConfigLiveHttp, authority_before: dict,
                  authority_after: dict, java_safety: dict, safety: dict) -> dict:
    attempts = []
    for index, record in enumerate(ledger.data["requests"]):
        public = _public_attempt(record)
        response = host.provider_responses[index] if index < len(host.provider_responses) else None
        if response is not None:
            public["response_id"] = response["response_id"]
            public["returned_model"] = response["model"]
            public["usage"] = response["usage"]
            public["tool_call_ids"] = [item["call_id"] for item in response["tool_calls"]]
            public["tool_schema_sha256"] = host.tool_schema_sha256
            public["returned_tool_ids"] = [item["call_id"] for item in response["tool_returns"]]
            public["tool_returns"] = response["tool_returns"]
        attempts.append(public)
    source = preflight["base"]["source"]
    sdk_identity = preflight["base"]["sdk"]
    source_identity = {
        "provider": PROVIDER_NAME, "provider_model": PROVIDER_MODEL,
        "provider_endpoint": PROVIDER_ORIGIN + PROVIDER_PATH,
        "config_center_source_commit": SOURCE_COMMIT,
        "config_center_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "config_center_jar_sha256": SOURCE_JAR_SHA256,
        "runtime_source_sha256": preflight["base"]["runtime_source"]["sha256"],
        "sdk_core_sha256": SDK_CORE_SHA256,
        "python_version": sdk_identity["python_version"],
        "python_executable_sha256": sdk_identity["python_executable_sha256"],
        "pydantic_record_sha256": sdk_identity["pydantic"]["record_sha256"],
        "pydantic_record_entries": sdk_identity["pydantic"]["record_entries"],
        "pydantic_record_mismatches": sdk_identity["pydantic"]["record_mismatches"],
        "openai_record_sha256": sdk_identity["openai"]["record_sha256"],
        "openai_record_entries": sdk_identity["openai"]["record_entries"],
        "openai_record_mismatches": sdk_identity["openai"]["record_mismatches"],
        "openai_core_sha256": sdk_identity["openai_core_sha256"],
        "java_version": java_safety["version"],
        "java_executable_sha256": java_safety["executable_sha256"],
    }
    sdk = {
        "framework": report["framework"], "version": report["version"],
        "openai_version": report["openai_version"], "pid": report["pid"],
        "exit_code": report["exit_code"], "requests": report["requests"],
        "input_tokens": report["input_tokens"], "output_tokens": report["output_tokens"],
        "tool_calls": report["tool_calls"], "tool_callbacks": report["tool_callbacks"],
        "sdk_source_sha256": report["sdk_source_sha256"],
        "openai_source_sha256": report["openai_source_sha256"],
        "final_output_sha256": report["final_output_sha256"],
        "final_text_persisted": False, "guard_denials": report["guard_denials"],
        "provider_key_present": report["provider_key_present"],
        "business_key_present": report["business_key_present"],
        "stderr_bytes": report["stderr_bytes"], "stderr_sha256": report["stderr_sha256"],
    }
    provider = {"name": PROVIDER_NAME, "origin": PROVIDER_ORIGIN,
                "requested_model": PROVIDER_MODEL, "attempts": attempts,
                "usage": ledger.usage()}
    before = {"current_seq": authority_before["current_seq"],
              "history_seq": authority_before["history_seq"]}
    after = {"current_seq": authority_after["current_seq"],
             "history_seq": authority_after["history_seq"],
             "list_seq": authority_after["list_seq"]}
    oracle = evaluate_live_effect(contracts["effect"], client.observations, host.tool_trace)
    return {"schema_version": "rpf-config-live-target-evidence-v1", "plan_id": "RPF-53",
        "contracts": contracts, "source_identity": source_identity, "sdk": sdk,
        "provider": provider, "tool_trace": host.tool_trace,
        "http_observations": client.observations,
        "authority_before": before, "authority_after": after,
        "oracle": oracle, "safety": safety,
        "limitations": {"issuer_authenticity": "NOT_ESTABLISHED",
            "database_independent_authority": "NOT_ESTABLISHED",
            "independent_reproduction": "NOT_TESTED", "PGE": "PGE_NOT_EXECUTED",
            "workswarm": "NOT_PROVEN"}}


def _verify_in_independent_process(path: Path, anchor: str | None) -> int:
    args = [str(SDK_PYTHON), "-B", str(Path(__file__).resolve()), "--verify", str(path)]
    if anchor is not None:
        args.extend(["--sha256", anchor])
    result = subprocess.run(args, cwd=ROOT, env=_sdk_env(WORK_ROOT / "preflight"),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=30, check=False)
    return result.returncode


def _tamper_controls(raw: bytes) -> list[dict]:
    envelope = strict_json(raw)
    base_payload = envelope["payload"]
    cases = []

    def reseal(name: str, mutate):
        payload = json.loads(json.dumps(base_payload))
        mutate(payload)
        data = canonical({"schema_version": envelope["schema_version"],
                          "payload_sha256": digest(payload), "payload": payload})
        path = QUARANTINE_ROOT / (name + ".json")
        _write_once(path, data)
        exit_code = _verify_in_independent_process(path, sha256_bytes(data))
        cases.append({"name": name, "external_hash_recomputed": True,
                      "exit_code": exit_code, "rejected": exit_code == 4})

    reseal("tamper-provider-source", lambda p: p["provider"].update(name="FAKE_PROVIDER"))
    reseal("tamper-sdk-call-lineage", lambda p: p["tool_trace"][0].update(call_id="call-forged"))

    def tamper_history(payload):
        row = payload["http_observations"][payload["authority_after"]["history_seq"] - 1]["response"]["data"][0]
        row["value"] = "forged-history"
        payload["http_observations"][payload["authority_after"]["history_seq"] - 1][
            "response_body_sha256"] = digest(payload["http_observations"][
                payload["authority_after"]["history_seq"] - 1]["response"])
    reseal("tamper-authority-history", tamper_history)
    reseal("tamper-cost-source-contract", lambda p: p["provider"]["usage"].update(
        estimated_cost_cny_upper=p["provider"]["usage"]["estimated_cost_cny_upper"] + 0.25))
    return cases


def run_scenario() -> dict:
    preflight = _live_preflight()
    _check_repo_identity()
    _verify_source_bundle()
    if any(path.exists() or path.is_symlink() for path in (
            STARTED_PATH, CONTRACTS_PATH, LEDGER_PATH, SUMMARY_PATH, EVIDENCE_PATH)):
        raise ProbeError("ONE_SHOT_SCENARIO_ALREADY_STARTED")
    scenario = SCENARIO_ROOT / ("live-" + uuid.uuid4().hex[:12])
    if not scenario.parent.is_dir():
        raise ProbeError("SCENARIO_PARENT_MISSING")
    suffix = uuid.uuid4().hex[:16]
    run_id = "rpf53-live-" + suffix
    java_port, host_port = _free_port(), _free_port()
    while host_port == java_port:
        host_port = _free_port()
    contracts = make_contracts(run_id=run_id, suffix=suffix,
        java_port=java_port, agent_port=host_port, prepared_at_utc=_utc(),
        runtime_source_sha256=preflight["base"]["runtime_source"]["sha256"],
        sdk_identity={
            "python_version": preflight["base"]["sdk"]["python_version"],
            "python_executable_sha256": preflight["base"]["sdk"]["python_executable_sha256"],
            "pydantic_record_sha256": preflight["base"]["sdk"]["pydantic"]["record_sha256"],
            "pydantic_record_entries": preflight["base"]["sdk"]["pydantic"]["record_entries"],
            "pydantic_record_mismatches": preflight["base"]["sdk"]["pydantic"]["record_mismatches"],
            "openai_record_sha256": preflight["base"]["sdk"]["openai"]["record_sha256"],
            "openai_record_entries": preflight["base"]["sdk"]["openai"]["record_entries"],
            "openai_record_mismatches": preflight["base"]["sdk"]["openai"]["record_mismatches"],
            "openai_core_sha256": preflight["base"]["sdk"]["openai_core_sha256"],
        }, tool_schema_sha256=preflight["diagnostic"]["tool_schema_sha256"])
    _write_once(CONTRACTS_PATH, canonical(contracts))
    marker = {"plan_id": "RPF-53", "plan_revision": "rev-1", "run_id": run_id,
        "started_at_utc": _utc(), "preflight_sha256": _sha_file(PREFLIGHT),
        "contracts_sha256": digest(contracts), "one_shot": True,
        "provider_https_requests": 0, "total_tokens_reserved_limit": LIMITS["total_tokens"],
        "cost_cny_upper_limit": LIMITS["estimated_cost_cny_upper"],
        "automatic_retries": 0}
    _write_once(STARTED_PATH, canonical(marker))
    ledger = ProviderLedger(LEDGER_PATH, run_id, create=True)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        ledger.finish(False)
        raise ProbeError("DEEPSEEK_KEY_DISAPPEARED_AFTER_MARKER", "PROVIDER")
    business_key = secrets.token_urlsafe(32)
    deadline = time.monotonic() + LIMITS["scenario_seconds"]
    client = ConfigLiveHttp(contracts, business_key, deadline=deadline)
    business = ConfigLiveBusiness(contracts, client)
    host = ConfigLiveHost(contracts, ledger, business, api_key=api_key,
                          expected_tool_schema_sha256=preflight["diagnostic"]["tool_schema_sha256"])
    java_process = sdk_process = None
    java_log = None
    sdk_report = None
    stdout = stderr = b""
    health = []
    authority_before = {}
    authority_after = {}
    failure = None
    java_log_info = {"log_saved": False, "bytes": 0, "sha256": sha256_bytes(b""),
                     "redactions": 0, "overflow": False}
    java_listener_pid = None
    java_exit_code = None
    sdk_exit_code = None
    sdk_external = []
    java_external = []
    process_stopped = host_closed = False
    scenario.mkdir()
    sdk_dir = scenario / "sdk"
    sdk_dir.mkdir()
    try:
        if time.monotonic() >= deadline:
            raise ProbeError("SCENARIO_DEADLINE_EXCEEDED")
        java_process, java_log = _start_java(contracts, business_key, scenario)
        if not _wait_for_java(java_process, java_port, java_log, deadline, health):
            raise ProbeError("JAVA_HEALTH_NOT_READY")
        java_listener_pid = java_process.pid if _listener_owned(java_process.pid, java_port) else None
        java_external = _external_connections(java_process.pid)
        if java_external:
            raise ProbeError("JAVA_EXTERNAL_CONNECTION_OBSERVED")
        if java_log.redactions or java_log.overflow:
            raise ProbeError("JAVA_LOG_SECRET_OR_SIZE_GUARD")
        if not client.initial_state_valid():
            raise ProbeError("INITIAL_STATE_NOT_ABSENT")
        authority_before = {"current_seq": 1, "history_seq": 2}
        java_external = _external_connections(java_process.pid)
        if java_external:
            raise ProbeError("JAVA_EXTERNAL_CONNECTION_OBSERVED")
        host.start(host_port)
        config = {"port": host.port, "token": host.token,
            "write_root": str(sdk_dir),
            "instructions": contracts["execution"]["agent_instructions"],
            "task_prompt": contracts["execution"]["task_prompt"],
            "model": PROVIDER_MODEL,
            "max_runtime_seconds": LIMITS["scenario_seconds"], "fixture": False}
        child_env = _sdk_env(sdk_dir)
        if "DEEPSEEK_API_KEY" in child_env or "CONFIG_CENTER_API_KEY" in child_env:
            raise ProbeError("SDK_CHILD_SECRET_ENVIRONMENT")
        sdk_process = subprocess.Popen([str(SDK_PYTHON), "-I", "-B",
            str(ROOT / "runtime/runproof_runtime/effectwitness/config_live_external.py")],
            cwd=sdk_dir, env=child_env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        remaining = max(0.1, deadline - time.monotonic())
        try:
            stdout, stderr = sdk_process.communicate(canonical(config), timeout=remaining)
        except subprocess.TimeoutExpired:
            sdk_process.kill()
            stdout, stderr = sdk_process.communicate(timeout=10)
            raise ProbeError("SDK_CHILD_TIMEOUT")
        sdk_exit_code = sdk_process.returncode
        sdk_report = _sdk_report(stdout, stderr, sdk_process)
        if sdk_report is None:
            if host.failure:
                raise ProbeError(host.failure["code"], host.failure["domain"])
            raise ProbeError("SDK_CHILD_REPORT_INVALID")
        sdk_report["exit_code"] = sdk_exit_code
        sdk_report["stderr_bytes"] = len(stderr)
        sdk_report["stderr_sha256"] = sha256_bytes(stderr)
        if sdk_report["pid"] != sdk_process.pid:
            raise ProbeError("SDK_PID_MISMATCH")
        if (sdk_report["provider_key_present"] is not False
                or sdk_report["business_key_present"] is not False
                or sdk_report["guard_denials"] != []):
            raise ProbeError("SDK_CHILD_SECRET_OR_GUARD_FAILURE")
        sdk_external = _external_connections(sdk_process.pid)
        if sdk_external:
            raise ProbeError("SDK_EXTERNAL_CONNECTION_OBSERVED")
        if host.failure is not None:
            raise ProbeError(host.failure["code"], host.failure["domain"])
        if (sdk_report["requests"] != len(ledger.data["requests"])
                or sdk_report["tool_calls"] != len(host.tool_trace)
                or sdk_report["tool_callbacks"] != len(host.tool_trace)):
            raise ProbeError("SDK_PROVIDER_TOOL_TRACE_COUNT_MISMATCH")
        after = client.final_readback()
        authority_after = {"current_seq": after[0]["seq"],
                           "history_seq": after[1]["seq"], "list_seq": after[2]["seq"]}
        java_external = _external_connections(java_process.pid)
        if java_external:
            raise ProbeError("JAVA_EXTERNAL_CONNECTION_OBSERVED")
    except (ProbeError, LiveRuntimeRejected) as exc:
        failure = {"domain": getattr(exc, "domain", "PLATFORM"),
                   "code": getattr(exc, "code", "SCENARIO_ERROR")}
        if isinstance(exc, LiveRuntimeRejected) and exc.domain == "PROVIDER":
            failure["provider_usage_state"] = ledger.data["requests"][-1]["status"] if ledger.data["requests"] else "NO_ATTEMPT"
    except Exception:
        failure = {"domain": "PLATFORM", "code": "SCENARIO_UNEXPECTED_ERROR"}
    finally:
        if sdk_process is not None and sdk_process.poll() is None:
            sdk_process.terminate()
            try:
                stdout, stderr = sdk_process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                sdk_process.kill()
                stdout, stderr = sdk_process.communicate(timeout=10)
        if sdk_process is not None:
            sdk_exit_code = sdk_process.returncode
            try:
                sdk_external = _external_connections(sdk_process.pid)
            except Exception:
                sdk_external = [{"remote": "UNAVAILABLE"}]
        try:
            host.close()
            host_closed = host._server is None and host._thread is None
        except Exception:
            host_closed = False
        if java_process is not None:
            try:
                java_external = _external_connections(java_process.pid)
            except Exception:
                java_external = [{"remote": "UNAVAILABLE"}]
            if java_process.poll() is None:
                java_process.terminate()
                try:
                    java_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    java_process.kill()
                    java_process.wait(timeout=10)
            java_exit_code = java_process.returncode
            process_stopped = java_process.poll() is not None
            if java_log is not None:
                java_log_info = java_log.close(SCENARIO_ROOT / "java-redacted.log")
        else:
            process_stopped = False
        if java_process is not None:
            try:
                listener_closed = _port_closed(java_port)
            except Exception:
                listener_closed = False
        else:
            listener_closed = False
        sdk_stopped = sdk_process is not None and sdk_process.poll() is not None
        cleanup_ok = (process_stopped and listener_closed and host_closed and sdk_stopped
                      and not sdk_external and not java_external and not java_log_info["overflow"]
                      and java_log_info["redactions"] == 0)
        ledger.finish(cleanup_ok and failure is None)

    report = sdk_report or {}
    if sdk_report is not None and sdk_exit_code is not None:
        report["exit_code"] = sdk_exit_code
        report["stderr_bytes"] = len(stderr)
        report["stderr_sha256"] = sha256_bytes(stderr)
    if sdk_process is not None:
        report.setdefault("pid", sdk_process.pid)
    after_readback = authority_after
    unknown_post = any(item.get("method") == "POST"
        and (item.get("status") is None or item.get("transport_error") is not None)
        for item in client.observations)
    if not after_readback and unknown_post:
        # A failed run may reconcile once, using read-only current/history only.
        try:
            reconcile = client.final_readback(reconcile=True)
            after_readback = {"reconcile_current_seq": reconcile[0]["seq"],
                              "reconcile_history_seq": reconcile[1]["seq"]}
        except Exception:
            after_readback = {}
    oracle = evaluate_live_effect(contracts["effect"], client.observations, host.tool_trace)
    status = "COMPLETE" if (failure is None and oracle["outcome"] == "CONTRACT_SATISFIED_IN_RUN"
                            and cleanup_ok and ledger.usage()["usage_known"]) else "PARTIAL"
    if host.failure and host.failure.get("domain") == "PROVIDER":
        status = "PARTIAL"
    summary = {
        "schema_version": "rpf53-live-summary-v1", "plan_id": "RPF-53",
        "status": status, "run_id": run_id, "started_marker_sha256": _sha_file(STARTED_PATH),
        "contracts_sha256": digest(contracts), "runtime_source_sha256": preflight["base"]["runtime_source"]["sha256"],
        "provider_key_present": True, "provider_requests": ledger.data["requests"],
        "provider_usage": ledger.usage(), "sdk": report,
        "tool_trace": host.tool_trace, "http_observations": client.observations,
        "authority_before": {"current_seq": 1, "history_seq": 2} if authority_before else None,
        "authority_after": after_readback, "oracle": oracle,
        "java": {"pid": java_process.pid if java_process else None,
                 "listener_pid": java_listener_pid, "health_gets": health,
                 "exit_code": java_exit_code, "stopped": process_stopped,
                 "listener_closed": listener_closed if java_process else False,
                 "external_connections": java_external, "log": java_log_info,
                 "version": preflight["base"]["java"]["version"],
                 "executable_sha256": preflight["base"]["java"]["executable_sha256"]},
        "sdk_process": {"pid": sdk_process.pid if sdk_process else None,
                        "exit_code": sdk_exit_code, "stopped": sdk_stopped,
                        "external_connections": sdk_external,
                        "stderr_bytes": len(stderr), "stderr_sha256": sha256_bytes(stderr)},
        "host_closed": host_closed, "cleanup_ok": cleanup_ok,
        "failure": failure, "limitations": {
            "issuer_authenticity": "NOT_ESTABLISHED",
            "database_independent_authority": "NOT_ESTABLISHED",
            "independent_reproduction": "NOT_TESTED",
            "PGE": "PGE_NOT_EXECUTED", "workswarm": "NOT_PROVEN"},
        "completed_at_utc": _utc(),
    }
    summary["status"] = "PARTIAL" if status == "COMPLETE" else status
    _write_once(SUMMARY_PATH, canonical(summary))
    if status != "COMPLETE":
        return summary

    safety = {"java_pid": java_process.pid, "java_listener_pid": java_listener_pid,
        "java_exit_code": java_exit_code, "java_stopped": process_stopped,
        "java_listener_closed": listener_closed, "java_external_connections": java_external,
        "sdk_pid": sdk_process.pid, "sdk_stopped": sdk_stopped,
        "sdk_external_connections": sdk_external, "host_closed": host_closed,
        "parent_external_connections": [],
        "sdk_provider_key_absent": report["provider_key_present"] is False,
        "sdk_business_key_absent": report["business_key_present"] is False,
        "sdk_guard_denials": report["guard_denials"]}
    source_identity = {
        "provider": PROVIDER_NAME, "provider_model": PROVIDER_MODEL,
        "provider_endpoint": PROVIDER_ORIGIN + PROVIDER_PATH,
        "config_center_source_commit": SOURCE_COMMIT,
        "config_center_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "config_center_jar_sha256": SOURCE_JAR_SHA256,
        "runtime_source_sha256": preflight["base"]["runtime_source"]["sha256"],
        "sdk_core_sha256": SDK_CORE_SHA256,
        "python_version": preflight["base"]["sdk"]["python_version"],
        "python_executable_sha256": preflight["base"]["sdk"]["python_executable_sha256"],
        "pydantic_record_sha256": preflight["base"]["sdk"]["pydantic"]["record_sha256"],
        "pydantic_record_entries": preflight["base"]["sdk"]["pydantic"]["record_entries"],
        "pydantic_record_mismatches": preflight["base"]["sdk"]["pydantic"]["record_mismatches"],
        "openai_record_sha256": preflight["base"]["sdk"]["openai"]["record_sha256"],
        "openai_record_entries": preflight["base"]["sdk"]["openai"]["record_entries"],
        "openai_record_mismatches": preflight["base"]["sdk"]["openai"]["record_mismatches"],
        "openai_core_sha256": preflight["base"]["sdk"]["openai_core_sha256"],
        "java_version": preflight["base"]["java"]["version"],
        "java_executable_sha256": preflight["base"]["java"]["executable_sha256"]}
    result = {"status": status, "provider_responses": host.provider_responses,
              "sdk_report": report, "tool_schema_sha256": host.tool_schema_sha256,
              "tool_trace": host.tool_trace, "http_observations": client.observations,
              "authority_before": authority_before, "authority_after": authority_after,
              "java_safety": {**safety, "version": preflight["base"]["java"]["version"],
                              "executable_sha256": preflight["base"]["java"]["executable_sha256"]}}
    payload = _make_payload(preflight, contracts, source_identity, {
        **report, "exit_code": sdk_exit_code, "stderr_bytes": len(stderr),
        "stderr_sha256": sha256_bytes(stderr)}, host, ledger, client,
        authority_before, authority_after, result["java_safety"], safety)
    try:
        evidence_raw = canonical({"schema_version": "rpf-config-live-target-evidence-v1",
            "payload_sha256": digest(payload), "payload": payload})
        verify_bytes(evidence_raw)
    except (LiveEvidenceRejected, Exception) as exc:
        summary["status"] = "PARTIAL"
        summary["failure"] = {"domain": "PLATFORM", "code": "LIVE_EVIDENCE_SELF_CHECK_FAILED",
                               "detail_code": getattr(exc, "code", type(exc).__name__)}
        _atomic_write(SUMMARY_PATH, canonical(summary))
        raise ProbeError("LIVE_EVIDENCE_SELF_CHECK_FAILED") from None
    _write_once(EVIDENCE_PATH, evidence_raw)
    anchor = sha256_bytes(evidence_raw)
    correct_exit = _verify_in_independent_process(EVIDENCE_PATH, anchor)
    missing_exit = _verify_in_independent_process(EVIDENCE_PATH, None)
    wrong_exit = _verify_in_independent_process(EVIDENCE_PATH, "0" * 64)
    tamper = _tamper_controls(evidence_raw)
    controls_pass = (correct_exit == 0 and missing_exit == 2 and wrong_exit == 3
                     and len(tamper) >= 4 and all(item["rejected"] for item in tamper))
    if not controls_pass:
        summary["status"] = "PARTIAL"
        summary["failure"] = {"domain": "PLATFORM", "code": "LIVE_EVIDENCE_OFFLINE_CONTROLS_FAILED"}
        _atomic_write(SUMMARY_PATH, canonical(summary))
        raise ProbeError("LIVE_EVIDENCE_OFFLINE_CONTROLS_FAILED")
    summary["status"] = "COMPLETE"
    summary["evidence"] = {"path": "spikes/rpf-53/config-live-evidence.json",
        "bytes": len(evidence_raw), "sha256": anchor,
        "verifier_exit_codes": {"correct_anchor": correct_exit,
                                 "missing_anchor": missing_exit, "wrong_anchor": wrong_exit},
        "tamper_controls": tamper}
    summary["offline_acceptance"] = "PASS"
    _atomic_write(SUMMARY_PATH, canonical(summary))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--diagnostic", action="store_true")
    modes.add_argument("--run-scenario", action="store_true")
    modes.add_argument("--verify", metavar="EVIDENCE")
    parser.add_argument("--sha256")
    args = parser.parse_args(argv)
    if args.verify is not None:
        return verify_file(args.verify, args.sha256)
    try:
        if args.prepare:
            value = prepare()
            print(json.dumps({"status": "PREFLIGHT_READY",
                "provider_key_present": value["provider"]["key_present"],
                "provider_requests": 0, "source_file_count": value["source"]["source_file_count"],
                "jar_sha256": value["source"]["jar_sha256"],
                "sdk_core_sha256": value["sdk"]["sdk_core_sha256"]},
                sort_keys=True, separators=(",", ":")))
            return 0
        if args.diagnostic:
            value = run_diagnostic()
            print(json.dumps({"status": value["diagnostic"]["status"],
                "model_source": "FIXTURE_TEST_ONLY", "provider_https_requests": 0,
                "tool_schema_sha256": value["diagnostic"]["tool_schema_sha256"]},
                sort_keys=True, separators=(",", ":")))
            return 0
        value = run_scenario()
        print(json.dumps({"status": value["status"], "run_id": value["run_id"],
            "provider_requests": value["provider_usage"]["provider_https_requests"],
            "tokens": value["provider_usage"]["tokens"],
            "estimated_cost_cny_upper": value["provider_usage"]["estimated_cost_cny_upper"],
            "effect_outcome": value["oracle"]["outcome"],
            "evidence": value.get("evidence")}, sort_keys=True, separators=(",", ":")))
        return 0 if value["status"] == "COMPLETE" else 1
    except ProbeError as exc:
        print(json.dumps({"status": "BLOCKED" if exc.code in (
            "DEEPSEEK_KEY_UNAVAILABLE", "A03_DIAGNOSTIC_NOT_PASSED") else "FAILED",
            "code": exc.code, "domain": exc.domain}, sort_keys=True, separators=(",", ":")))
        return 1
    except Exception:
        print(json.dumps({"status": "FAILED", "code": "PROBE_UNEXPECTED_ERROR"},
                         sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
