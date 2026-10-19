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
    PLAN_REVISION, BASE_SHA, BASE_BRANCH, LIVE_BRANCH, EVIDENCE_SCHEMA, LIMITS, PROVIDER_MODEL, PROVIDER_NAME,
    PROVIDER_ORIGIN, PROVIDER_PATH, SDK_CORE_SHA256, SDK_NAME, SDK_VERSION,
    OPENAI_VERSION, SOURCE_COMMIT, SOURCE_JAR_BYTES, SOURCE_JAR_SHA256,
    SOURCE_MANIFEST_SHA256, TASK_OWNED_JAR_PATH,
    canonical, digest, make_contracts, sha256_bytes, strict_json,
)
from runtime.runproof_runtime.effectwitness.config_live_runtime import (
    ConfigLiveBusiness, ConfigLiveHost, ConfigLiveHttp, ConfigLiveMemoryBackend,
    LiveRuntimeRejected, ProviderLedger,
)
from runtime.runproof_runtime.effectwitness.config_live_verify import (
    LiveEvidenceRejected, evaluate_live_effect, verify_bytes, verify_file,
)


WORK_ROOT = ROOT / ".local" / "rpf-53-rev5"
PREFLIGHT_DIR = WORK_ROOT / "preflight"
BASE_PREFLIGHT = PREFLIGHT_DIR / "base-preflight.json"
SUPERSEDED_BASE_PREFLIGHT = PREFLIGHT_DIR / "base-preflight-superseded-before-fixture.json"
ATTEMPT_PREFLIGHTS = [BASE_PREFLIGHT,
    PREFLIGHT_DIR / "base-preflight-attempt-02.json"]
PREFLIGHT = PREFLIGHT_DIR / "preflight.json"
FIXTURE_ROOT = WORK_ROOT / "fixture"
SCENARIO_ROOT = WORK_ROOT / "scenario"
QUARANTINE_ROOT = WORK_ROOT / "quarantine"
TASK_JAR_DIR = WORK_ROOT / "jar"
TASK_OWNED_JAR = ROOT.joinpath(*TASK_OWNED_JAR_PATH.split("/"))
STARTED_PATH = SCENARIO_ROOT / "started.json"
CONTRACTS_PATH = SCENARIO_ROOT / "contracts.json"
LEDGER_PATH = SCENARIO_ROOT / "provider-ledger.json"
REV5_DIR = ROOT / "spikes" / "rpf-53" / "rev-5"
SUMMARY_PATH = REV5_DIR / "live-summary.json"
EVIDENCE_PATH = REV5_DIR / "config-live-evidence.json"
RESULT_PATH = REV5_DIR / "RESULT.md"
SDK_FIXTURE_PREFLIGHT_PATH = REV5_DIR / "sdk-fixture-preflight.json"
SDK_LAUNCHER = ROOT / ".local" / "rpf-48" / "venv" / "Scripts" / "python.exe"
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
ALLOWED_FILES = set(SOURCE_FILES) | {
    "spikes/rpf-53/rev-5/README.md", "spikes/rpf-53/rev-5/RESULT.md",
    "spikes/rpf-53/rev-5/live-summary.json",
    "spikes/rpf-53/rev-5/sdk-fixture-preflight.json",
    "spikes/rpf-53/rev-5/config-live-evidence.json",
}
MAX_JAVA_LOG_BYTES = 1_000_000
_DIRECT_SDK_PYTHON: Path | None = None


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


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _has_link_component(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    return any(_is_link(item) for item in (absolute, *absolute.parents))


def _copy_task_owned_jar(source_info: dict, *, create: bool = True,
                         allow_existing: bool = False) -> dict:
    root = WORK_ROOT.resolve(strict=True)
    source = SOURCE_JAR
    target = TASK_OWNED_JAR
    if (_has_link_component(source) or not source.is_file()
            or _has_link_component(target.parent) or not target.parent.is_dir()):
        raise ProbeError("TASK_JAR_PATH_OR_LINK_GATE")
    try:
        target_lexical = Path(os.path.abspath(target))
        target_lexical.relative_to(root)
    except ValueError:
        raise ProbeError("TASK_JAR_PATH_ESCAPE") from None
    if _has_link_component(target):
        raise ProbeError("TASK_JAR_PATH_OR_LINK_GATE")
    resolved_target = target.resolve(strict=False)
    if not resolved_target.is_relative_to(root):
        raise ProbeError("TASK_JAR_PATH_ESCAPE")
    source_before_bytes = source.stat().st_size
    source_before_sha = _sha_file(source)
    if (source_info.get("source_commit") != SOURCE_COMMIT
            or source_info.get("manifest_sha256") != SOURCE_MANIFEST_SHA256
            or source_info.get("jar_bytes") != SOURCE_JAR_BYTES
            or source_info.get("jar_sha256") != SOURCE_JAR_SHA256
            or source_before_bytes != SOURCE_JAR_BYTES
            or source_before_sha != SOURCE_JAR_SHA256):
        raise ProbeError("TASK_JAR_SOURCE_IDENTITY")
    if target.exists():
        if not create:
            raise ProbeError("TASK_JAR_COPY_MISSING")
        if not allow_existing:
            raise ProbeError("TASK_JAR_PREEXISTING_COPY")
        if (not target.is_file() or target.is_symlink()
                or target.stat().st_size != SOURCE_JAR_BYTES
                or _sha_file(target) != SOURCE_JAR_SHA256):
            raise ProbeError("TASK_JAR_EXISTING_COPY_MISMATCH")
    else:
        if not create:
            raise ProbeError("TASK_JAR_COPY_MISSING")
        try:
            with source.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
        except FileExistsError:
            raise ProbeError("TASK_JAR_COPY_RACE") from None
        except OSError:
            raise ProbeError("TASK_JAR_COPY_FAILED") from None
    if (_has_link_component(target) or not target.is_file()
            or not target.resolve(strict=True).is_relative_to(root)):
        raise ProbeError("TASK_JAR_COPY_PATH_INVALID")
    source_after_bytes = source.stat().st_size
    source_after_sha = _sha_file(source)
    copy_bytes = target.stat().st_size
    copy_sha = _sha_file(target)
    if (source_after_bytes != source_before_bytes
            or source_after_sha != source_before_sha
            or copy_bytes != source_after_bytes or copy_sha != source_after_sha):
        raise ProbeError("TASK_JAR_COPY_DIGEST_MISMATCH")
    return {
        "relative_path": TASK_OWNED_JAR_PATH,
        "source_commit": SOURCE_COMMIT,
        "manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_sha256": source_after_sha,
        "source_bytes": source_after_bytes,
        "copy_sha256": copy_sha,
        "copy_bytes": copy_bytes,
        "path_within_task_root": True,
        "no_link_components": True,
        "copy_verified": True,
    }


def _argv_jar_path_matches(argv: object, expected_jar: Path,
                           task_root: Path) -> bool:
    if type(argv) not in (list, tuple) or any(type(value) is not str for value in argv):
        return False
    jar_flags = [index for index, value in enumerate(argv) if value == "-jar"]
    if len(jar_flags) != 1 or jar_flags[0] + 1 >= len(argv):
        return False
    try:
        expected = expected_jar.resolve(strict=True)
        root = task_root.resolve(strict=True)
        actual = Path(argv[jar_flags[0] + 1]).resolve(strict=True)
        if (_has_link_component(expected_jar) or _has_link_component(actual)
                or not expected.is_file() or not actual.is_file()
                or not expected.is_relative_to(root) or actual != expected):
            return False
        return os.path.normcase(str(actual)) == os.path.normcase(str(expected))
    except (OSError, RuntimeError, ValueError):
        return False


def _actual_process_command_line(pid: int) -> str:
    if os.name != "nt" or type(pid) is not int or pid <= 0:
        raise ProbeError("JAVA_COMMAND_LINE_UNAVAILABLE")
    command = (f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; "
               "if($null -eq $p -or [string]::IsNullOrEmpty($p.CommandLine)){exit 2}; "
               "[Console]::Out.Write([Convert]::ToBase64String("
               "[Text.Encoding]::UTF8.GetBytes($p.CommandLine)))")
    try:
        result = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile",
            "-NonInteractive", "-Command", command], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
        encoded = result.stdout.decode("ascii", "strict").strip()
        if result.returncode != 0 or result.stderr or not encoded:
            raise ProbeError("JAVA_COMMAND_LINE_UNAVAILABLE")
        raw = base64.b64decode(encoded, validate=True)
        return raw.decode("utf-8", "strict")
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
        raise ProbeError("JAVA_COMMAND_LINE_UNAVAILABLE") from None


def _split_windows_command_line(command_line: str) -> list[str]:
    if os.name != "nt" or not command_line:
        raise ProbeError("JAVA_COMMAND_LINE_UNAVAILABLE")
    import ctypes
    argc = ctypes.c_int()
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p,
                                           ctypes.POINTER(ctypes.c_int)]
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    pointer = shell32.CommandLineToArgvW(command_line, ctypes.byref(argc))
    if not pointer:
        raise ProbeError("JAVA_COMMAND_LINE_UNAVAILABLE")
    try:
        return [pointer[index] for index in range(argc.value)]
    finally:
        kernel32.LocalFree(pointer)


def _actual_java_jar_proof(process: subprocess.Popen, task_jar: dict) -> dict:
    expected = ROOT.joinpath(*TASK_OWNED_JAR_PATH.split("/"))
    if not _argv_jar_path_matches(process.args, expected, WORK_ROOT):
        raise ProbeError("JAVA_POPEN_JAR_PATH_MISMATCH")
    command_line = _actual_process_command_line(process.pid)
    actual_argv = _split_windows_command_line(command_line)
    if not _argv_jar_path_matches(actual_argv, expected, WORK_ROOT):
        raise ProbeError("JAVA_PROCESS_JAR_PATH_MISMATCH")
    if (task_jar.get("relative_path") != TASK_OWNED_JAR_PATH
            or task_jar.get("copy_sha256") != SOURCE_JAR_SHA256
            or task_jar.get("copy_bytes") != SOURCE_JAR_BYTES
            or task_jar.get("copy_verified") is not True):
        raise ProbeError("JAVA_TASK_JAR_IDENTITY_MISMATCH")
    return {
        "task_relative_path": TASK_OWNED_JAR_PATH,
        "source_sha256": task_jar["source_sha256"],
        "copy_sha256": task_jar["copy_sha256"],
        "copy_bytes": task_jar["copy_bytes"],
        "source_commit": task_jar["source_commit"],
        "manifest_sha256": task_jar["manifest_sha256"],
        "popen_argv_matches_copy": True,
        "actual_process_argv_matches_copy": True,
        "actual_command_line_sha256": sha256_bytes(command_line.encode("utf-8")),
    }


def _query_base_python(expected_base_sha256: str | None = None,
                      expected_launcher_sha256: str | None = None) -> tuple[Path, str, str]:
    if not SDK_LAUNCHER.is_file() or SDK_LAUNCHER.is_symlink():
        raise ProbeError("PINNED_SDK_LAUNCHER_MISSING")
    script = r'''import hashlib,json,pathlib,sys
launcher=pathlib.Path(sys.argv[1]).resolve(strict=True)
actual=pathlib.Path(sys.executable).resolve(strict=True)
base=pathlib.Path(getattr(sys,"_base_executable",sys.executable)).resolve(strict=True)
if actual!=launcher: raise RuntimeError("SDK_LAUNCHER_IDENTITY")
print(json.dumps({"python_version":sys.version.split()[0],"base_executable":str(base),
 "base_executable_sha256":hashlib.sha256(base.read_bytes()).hexdigest(),
 "launcher_sha256":hashlib.sha256(launcher.read_bytes()).hexdigest()},sort_keys=True,separators=(",",":")))
'''
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH") if key in os.environ}
    result = subprocess.run([str(SDK_LAUNCHER), "-I", "-B", "-X", "utf8", "-c", script,
                             str(SDK_LAUNCHER.resolve(strict=True))], cwd=ROOT, env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=20, check=False)
    if result.returncode != 0 or result.stderr:
        raise ProbeError("PINNED_SDK_LAUNCHER_INSPECTION_FAILED")
    try:
        value = json.loads(result.stdout.decode("utf-8"))
        base = Path(value["base_executable"]).resolve(strict=True)
    except (UnicodeError, ValueError, KeyError, OSError, TypeError):
        raise ProbeError("PINNED_SDK_LAUNCHER_IDENTITY_INVALID") from None
    if (type(value) is not dict or set(value) != {"python_version", "base_executable",
            "base_executable_sha256", "launcher_sha256"}
            or value["python_version"] != "3.12.13"
            or not re.fullmatch(r"[0-9a-f]{64}", value["base_executable_sha256"])
            or not re.fullmatch(r"[0-9a-f]{64}", value["launcher_sha256"])
            or not base.is_file() or _sha_file(base) != value["base_executable_sha256"]
            or _sha_file(SDK_LAUNCHER) != value["launcher_sha256"]
            or (expected_base_sha256 is not None
                and value["base_executable_sha256"] != expected_base_sha256)
            or (expected_launcher_sha256 is not None
                and value["launcher_sha256"] != expected_launcher_sha256)):
        raise ProbeError("PINNED_SDK_LAUNCHER_IDENTITY_MISMATCH")
    return base, value["base_executable_sha256"], value["launcher_sha256"]


def _direct_sdk_executable(sdk_identity: dict) -> Path:
    global _DIRECT_SDK_PYTHON
    if _DIRECT_SDK_PYTHON is not None:
        base = _DIRECT_SDK_PYTHON.resolve(strict=True)
        if (not base.is_file() or _sha_file(base) != sdk_identity.get(
                "python_executable_sha256")
                or not SDK_LAUNCHER.is_file()
                or _sha_file(SDK_LAUNCHER) != sdk_identity.get("python_launcher_sha256")):
            raise ProbeError("PINNED_SDK_RUNTIME_DRIFT")
        return base
    base, base_sha, launcher_sha = _query_base_python(
        sdk_identity.get("python_executable_sha256"),
        sdk_identity.get("python_launcher_sha256"))
    if (_DIRECT_SDK_PYTHON is not None
            and (_DIRECT_SDK_PYTHON.resolve(strict=True) != base
                 or _sha_file(_DIRECT_SDK_PYTHON) != base_sha)):
        raise ProbeError("PINNED_SDK_RUNTIME_DRIFT")
    _DIRECT_SDK_PYTHON = base
    return base


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
        if normalized in ("spikes/rpf-53/rev-5/", "spikes/rpf-53/rev-5"):
            if not REV5_DIR.is_dir() or REV5_DIR.is_symlink():
                raise ProbeError("REV5_OUTPUT_ROOT_INVALID")
            allowed_names = {Path(item).name for item in ALLOWED_FILES
                             if item.startswith("spikes/rpf-53/rev-5/")}
            if any(child.name not in allowed_names or child.is_symlink()
                   or not child.is_file() for child in REV5_DIR.iterdir()):
                raise ProbeError("UNAPPROVED_REV5_OUTPUT")
            continue
        if normalized in ALLOWED_FILES:
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
    def is_link(path: Path) -> bool:
        return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())

    for path in (ROOT / "spikes" / "rpf-53", REV5_DIR, WORK_ROOT):
        if is_link(path):
            raise ProbeError("TASK_ROOT_IS_SYMLINK")
    if not (ROOT / "spikes" / "rpf-53").is_dir():
        raise ProbeError("SPIKE_DIRECTORY_MISSING")
    if REV5_DIR.exists() and not REV5_DIR.is_dir():
        raise ProbeError("REV5_OUTPUT_ROOT_INVALID")
    REV5_DIR.mkdir(exist_ok=True)
    if not WORK_ROOT.exists():
        WORK_ROOT.mkdir()
    if not WORK_ROOT.is_dir() or is_link(WORK_ROOT):
        raise ProbeError("TASK_LOCAL_ROOT_INVALID")
    expected = {"preflight", "fixture", "scenario", "quarantine", "tests", "jar"}
    for child in WORK_ROOT.iterdir():
        if child.name not in expected or is_link(child):
            raise ProbeError("TASK_LOCAL_ROOT_NOT_EXCLUSIVE")
    for name in expected:
        (WORK_ROOT / name).mkdir(exist_ok=True)


def _verify_source_bundle() -> dict:
    if any(_has_link_component(path) for path in (SOURCE_ROOT, SOURCE_MANIFEST, SOURCE_JAR)):
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
        if _has_link_component(path) or not path.is_file():
            raise ProbeError("SOURCE_FILE_MISSING_OR_LINK")
        data = path.read_bytes()
        if len(data) != item["bytes"] or sha256_bytes(data) != item["sha256"]:
            raise ProbeError("SOURCE_FILE_DIGEST_MISMATCH")
        total += len(data)
    if total != 393800:
        raise ProbeError("SOURCE_TREE_BYTE_COUNT")
    if not SOURCE_JAR.is_file() or SOURCE_JAR.stat().st_size != SOURCE_JAR_BYTES:
        raise ProbeError("SOURCE_JAR_SIZE")
    jar_sha = _sha_file(SOURCE_JAR)
    if jar_sha != SOURCE_JAR_SHA256:
        raise ProbeError("SOURCE_JAR_SHA256_MISMATCH")
    return {"source_commit": SOURCE_COMMIT, "manifest_sha256": SOURCE_MANIFEST_SHA256,
            "source_file_count": 110, "source_total_bytes": total,
            "jar_bytes": SOURCE_JAR.stat().st_size, "jar_sha256": jar_sha}


def _sdk_identity() -> dict:
    def has_link_component(path: Path) -> bool:
        absolute = Path(path).absolute()
        return any(item.is_symlink() or bool(getattr(item, "is_junction", lambda: False)())
                   for item in (absolute, *absolute.parents))

    if (not SDK_LAUNCHER.is_file() or not SDK_SITE.is_dir()
            or has_link_component(SDK_LAUNCHER) or has_link_component(SDK_SITE)):
        raise ProbeError("PINNED_SDK_RUNTIME_MISSING")
    script = r'''
import base64, csv, hashlib, importlib.metadata as md, inspect, json, pathlib, sys, sysconfig, os
base=pathlib.Path(sys.prefix,"Lib","site-packages").resolve(strict=True)
venv_root=pathlib.Path(sys.prefix).resolve(strict=True)
expected=pathlib.Path(sys.argv[1]).resolve(strict=True)
configured_executable=pathlib.Path(sys.argv[2]).resolve(strict=True)
if base!=expected or not base.is_dir(): raise RuntimeError("SDK_ROOT_IDENTITY")
def is_link(path):
 p=pathlib.Path(path)
 return p.is_symlink() or bool(getattr(p,"is_junction",lambda:False)())
if is_link(expected): raise RuntimeError("SDK_ROOT_LINK")
dists={d.metadata.get("Name","").lower().replace("-","_"):d for d in md.distributions(path=[str(base)])}
def inspect_dist(key,expected):
 d=dists[key]; record=pathlib.Path(d._path)/"RECORD"
 if is_link(record) or not record.resolve(strict=True).is_relative_to(base): raise RuntimeError("RECORD_PATH")
 with record.open(encoding="utf-8",newline="") as f: rows=list(csv.reader(f))
 hashed=mismatch=0
 for row in rows:
  if len(row)<2 or not row[1]: continue
  rel=pathlib.PurePosixPath(row[0].replace("\\","/"))
  if rel.is_absolute() or any(":" in part for part in rel.parts): raise RuntimeError("RECORD_PATH")
  lexical=base.joinpath(*rel.parts)
  cursor=base
  for part in rel.parts:
   cursor=cursor/part
   if is_link(cursor): raise RuntimeError("RECORD_LINK")
  target=lexical.resolve(strict=True)
  if target!=venv_root and venv_root not in target.parents: raise RuntimeError("RECORD_PATH")
  if not target.is_file(): raise RuntimeError("RECORD_FILE")
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
from openai import AsyncOpenAI
from pydantic_ai import Agent
core=pathlib.Path(inspect.getfile(Agent)).resolve()
openai_core=pathlib.Path(inspect.getfile(AsyncOpenAI)).resolve()
if base not in core.parents or base not in openai_core.parents: raise RuntimeError("SDK_MODULE_OUTSIDE_ROOT")
base_executable=pathlib.Path(getattr(sys,"_base_executable",sys.executable)).resolve(strict=True)
stdlib=pathlib.Path(sysconfig.get_paths()["stdlib"]).resolve(strict=True)
base_prefix=pathlib.Path(sys.base_prefix).resolve(strict=True)
if not stdlib.is_dir() or not base_executable.is_file(): raise RuntimeError("PYTHON_RUNTIME_MAPPING")
archive_name=f"python{sys.version_info.major}{sys.version_info.minor}.zip"
archive_expected=base_prefix/archive_name
archive=None
for item in sys.path:
 if not item: continue
 entry=pathlib.Path(item)
 if not entry.is_absolute() or ".." in entry.parts or entry.name.casefold()!=archive_name.casefold(): continue
 try:
  if entry.resolve()==archive_expected: archive=archive_expected; break
 except OSError: pass
root_binding=hashlib.sha256(os.path.normcase(str(base)).casefold().encode("utf-8")).hexdigest()
result={"python_version":sys.version.split()[0],"python_executable_sha256":hashlib.sha256(pathlib.Path(sys.executable).read_bytes()).hexdigest(),
 "configured_executable_matches_sys":pathlib.Path(sys.executable).resolve(strict=True)==configured_executable,
 "base_executable_sha256":hashlib.sha256(base_executable.read_bytes()).hexdigest(),
 "pydantic":p,"openai":o,"sdk_site_root_binding_sha256":root_binding,
 "python_runtime_mapping_sha256":hashlib.sha256((str(base_executable)+"\n"+str(stdlib)+"\n"+(str(archive) if archive else "")).casefold().encode("utf-8")).hexdigest(),
 "sdk_core_sha256":hashlib.sha256(core.read_bytes()).hexdigest(),
 "openai_core_sha256":hashlib.sha256(openai_core.read_bytes()).hexdigest()}
print(json.dumps(result,sort_keys=True,separators=(",",":")))
'''
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH") if key in os.environ}
    result = subprocess.run([str(SDK_LAUNCHER), "-I", "-B", "-X", "utf8", "-c", script,
                             str(SDK_SITE.resolve(strict=True)), str(SDK_LAUNCHER.resolve(strict=True))], cwd=ROOT, env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=30, check=False)
    if result.returncode != 0 or result.stderr:
        safe_causes = ("SDK_ROOT_IDENTITY", "SDK_ROOT_LINK", "RECORD_PATH",
            "RECORD_LINK", "RECORD_FILE", "RECORD_HASH_ALGORITHM", "SDK_VERSION",
            "SDK_MODULE_OUTSIDE_ROOT", "PYTHON_RUNTIME_MAPPING")
        stderr_text = result.stderr.decode("utf-8", "replace")
        for cause in safe_causes:
            if cause in stderr_text:
                raise ProbeError("PINNED_SDK_RECORD_VERIFY_FAILED_" + cause)
        raise ProbeError("PINNED_SDK_RECORD_VERIFY_FAILED")
    try:
        value = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise ProbeError("PINNED_SDK_IDENTITY_INVALID") from None
    direct_python, direct_sha, launcher_sha = _query_base_python(
        value.get("base_executable_sha256"), value.get("python_executable_sha256"))
    direct_script = r'''
import hashlib, importlib.metadata as md, inspect, json, os, pathlib, sys, sysconfig
site=pathlib.Path(sys.argv[1]).resolve(strict=True)
expected=pathlib.Path(sys.argv[2]).resolve(strict=True)
launcher=pathlib.Path(sys.argv[3]).resolve(strict=True)
actual=pathlib.Path(sys.executable).resolve(strict=True)
base_executable=pathlib.Path(getattr(sys,"_base_executable",sys.executable)).resolve(strict=True)
if actual!=expected or base_executable!=expected: raise RuntimeError("SDK_DIRECT_PYTHON_IDENTITY")
sys.path.insert(0,str(site))
from openai import AsyncOpenAI
from pydantic_ai import Agent
sdk_core=pathlib.Path(inspect.getfile(Agent)).resolve()
openai_core=pathlib.Path(inspect.getfile(AsyncOpenAI)).resolve()
if site not in sdk_core.parents or site not in openai_core.parents: raise RuntimeError("SDK_MODULE_OUTSIDE_ROOT")
stdlib=pathlib.Path(sysconfig.get_paths()["stdlib"]).resolve(strict=True)
base_prefix=pathlib.Path(sys.base_prefix).resolve(strict=True)
if not stdlib.is_dir(): raise RuntimeError("PYTHON_RUNTIME_MAPPING")
archive_name=f"python{sys.version_info.major}{sys.version_info.minor}.zip"
archive_expected=base_prefix/archive_name
archive=None
for item in sys.path:
 if not item: continue
 entry=pathlib.Path(item)
 if not entry.is_absolute() or ".." in entry.parts or entry.name.casefold()!=archive_name.casefold(): continue
 try:
  if entry.resolve()==archive_expected: archive=archive_expected; break
 except OSError: pass
material=str(actual)+"\n"+str(stdlib)+"\n"+(str(archive) if archive else "")
print(json.dumps({"python_version":sys.version.split()[0],
 "python_executable_sha256":hashlib.sha256(actual.read_bytes()).hexdigest(),
 "python_launcher_sha256":hashlib.sha256(launcher.read_bytes()).hexdigest(),
 "configured_executable_matches_sys":actual==expected,
 "python_runtime_mapping_sha256":hashlib.sha256(material.casefold().encode("utf-8")).hexdigest(),
 "sdk_site_root_binding_sha256":hashlib.sha256(os.path.normcase(str(site)).casefold().encode("utf-8")).hexdigest(),
 "sdk_core_sha256":hashlib.sha256(sdk_core.read_bytes()).hexdigest(),
 "openai_core_sha256":hashlib.sha256(openai_core.read_bytes()).hexdigest(),
 "pydantic_version":md.version("pydantic-ai-slim"),"openai_version":md.version("openai")},
 sort_keys=True,separators=(",",":")))
'''
    direct_result = subprocess.run([str(direct_python), "-I", "-B", "-X", "utf8", "-c",
        direct_script, str(SDK_SITE.resolve(strict=True)), str(direct_python),
        str(SDK_LAUNCHER.resolve(strict=True))], cwd=ROOT, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, check=False)
    if direct_result.returncode != 0 or direct_result.stderr:
        raise ProbeError("PINNED_DIRECT_PYTHON_IDENTITY_FAILED")
    try:
        direct = json.loads(direct_result.stdout.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise ProbeError("PINNED_DIRECT_PYTHON_IDENTITY_INVALID") from None
    if (type(direct) is not dict or direct.get("python_version") != "3.12.13"
            or direct.get("python_executable_sha256") != direct_sha
            or direct.get("python_launcher_sha256") != launcher_sha
            or direct.get("configured_executable_matches_sys") is not True
            or direct.get("pydantic_version") != SDK_VERSION
            or direct.get("openai_version") != OPENAI_VERSION
            or direct.get("sdk_core_sha256") != value.get("sdk_core_sha256")
            or direct.get("openai_core_sha256") != value.get("openai_core_sha256")
            or direct.get("sdk_site_root_binding_sha256") != value.get("sdk_site_root_binding_sha256")
            or not re.fullmatch(r"[0-9a-f]{64}", direct.get("python_runtime_mapping_sha256", ""))):
        raise ProbeError("PINNED_DIRECT_PYTHON_IDENTITY_MISMATCH")
    value["python_launcher_sha256"] = launcher_sha
    value["python_executable_sha256"] = direct["python_executable_sha256"]
    value["python_runtime_mapping_sha256"] = direct["python_runtime_mapping_sha256"]
    value["configured_executable_matches_sys"] = direct["configured_executable_matches_sys"]
    value.pop("base_executable_sha256", None)
    _DIRECT_SDK_PYTHON = direct_python
    if (value.get("python_version") != "3.12.13"
            or value.get("configured_executable_matches_sys") is not True
            or value.get("sdk_core_sha256") != SDK_CORE_SHA256
            or value.get("pydantic", {}).get("version") != SDK_VERSION
            or value.get("pydantic", {}).get("record_entries") != 444
            or value.get("pydantic", {}).get("record_hashed_entries") != 443
            or value.get("pydantic", {}).get("record_mismatches") != 0
            or value.get("openai", {}).get("version") != OPENAI_VERSION
            or value.get("openai", {}).get("record_entries") != 2000
            or value.get("openai", {}).get("record_hashed_entries") != 1999
            or value.get("openai", {}).get("record_mismatches") != 0
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("sdk_site_root_binding_sha256", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("python_executable_sha256", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("python_launcher_sha256", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("python_runtime_mapping_sha256", ""))):
        raise ProbeError("PINNED_SDK_IDENTITY_MISMATCH")
    return value


def _java_identity() -> dict:
    if not JAVA.is_file() or JAVA.is_symlink():
        raise ProbeError("DIRECT_JDK17_MISSING")
    release = JAVA.parent.parent / "release"
    if release.is_symlink() or not release.is_file():
        raise ProbeError("DIRECT_JDK17_RELEASE_MISSING")
    release_raw = release.read_bytes()
    version_text = release_raw.decode("utf-8", "strict")
    match = re.search(r'^JAVA_VERSION="([0-9.]+)"\r?$', version_text, re.MULTILINE)
    if not match or match.group(1) != "17.0.12":
        raise ProbeError("DIRECT_JDK17_RELEASE_IDENTITY_MISMATCH")
    return {"version": match.group(1), "executable_sha256": _sha_file(JAVA),
            "release_sha256": sha256_bytes(release_raw),
            "identity_source": "JDK_RELEASE_FILE_NO_PROCESS"}


def _verify_java_runtime() -> dict:
    static = _java_identity()
    java_tmp = WORK_ROOT / "preflight" / "java-runtime-check"
    java_tmp.mkdir(parents=True, exist_ok=False)
    result = subprocess.run([str(JAVA), f"-Djava.io.tmpdir={java_tmp}", "-version"],
                            cwd=java_tmp, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30, check=False)
    version_text = result.stderr.decode("utf-8", "replace")
    match = re.search(r'java version "([0-9.]+)', version_text)
    if (result.returncode != 0 or not match or match.group(1) != "17.0.12"
            or _sha_file(JAVA) != static["executable_sha256"]):
        raise ProbeError("DIRECT_JDK17_IDENTITY_MISMATCH")
    return {"version": match.group(1), "executable_sha256": static["executable_sha256"],
            "release_sha256": static["release_sha256"],
            "identity_source": "DIRECT_JDK_VERSION_PROCESS"}


def _runtime_source_identity() -> dict:
    files = {}
    for name in SOURCE_FILES:
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            raise ProbeError("RUNTIME_SOURCE_MISSING_OR_LINK")
        files[name] = _sha_file(path)
    return {"files": files, "sha256": digest(files)}


def _has_prior_task_jar_proof() -> bool:
    for path in (BASE_PREFLIGHT, SUPERSEDED_BASE_PREFLIGHT):
        if not path.is_file() or _has_link_component(path):
            continue
        try:
            value = strict_json(path.read_bytes())
        except Exception:
            continue
        jar = value.get("task_owned_jar") if type(value) is dict else None
        if (type(value) is dict and value.get("schema_version") == "rpf53-rev5-base-preflight-v1"
                and value.get("plan_revision") == PLAN_REVISION
                and type(jar) is dict
                and jar.get("relative_path") == TASK_OWNED_JAR_PATH
                and jar.get("source_commit") == SOURCE_COMMIT
                and jar.get("manifest_sha256") == SOURCE_MANIFEST_SHA256
                and jar.get("source_sha256") == SOURCE_JAR_SHA256
                and jar.get("source_bytes") == SOURCE_JAR_BYTES
                and jar.get("copy_sha256") == SOURCE_JAR_SHA256
                and jar.get("copy_bytes") == SOURCE_JAR_BYTES
                and jar.get("path_within_task_root") is True
                and jar.get("no_link_components") is True
                and jar.get("copy_verified") is True):
            return True
    return False


def _check_key_presence() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def _preflight() -> dict:
    repo = _check_repo_identity()
    source = _verify_source_bundle()
    task_owned_jar = _copy_task_owned_jar(source, allow_existing=_has_prior_task_jar_proof())
    sdk = _sdk_identity()
    java = _java_identity()
    runtime = _runtime_source_identity()
    if (sdk["sdk_core_sha256"] != SDK_CORE_SHA256
            or source["manifest_sha256"] != SOURCE_MANIFEST_SHA256):
        raise ProbeError("A01_SOURCE_IDENTITY")
    return {
        "schema_version": "rpf53-rev5-base-preflight-v1",
        "plan_id": "RPF-53", "plan_revision": PLAN_REVISION, "checked_at_utc": _utc(),
        "repo": repo, "source": source, "task_owned_jar": task_owned_jar,
        "sdk": sdk, "java": java,
        "runtime_source": runtime,
        "provider": {"key_present": _check_key_presence(),
            "name": PROVIDER_NAME, "origin": PROVIDER_ORIGIN,
            "model": PROVIDER_MODEL, "path": PROVIDER_PATH,
            "model_version": "DeepSeek-V4.1-Flash-1017",
            "tool_calls_supported": True,
            "official_docs_snapshot_date": "2026-10-19",
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
    if (value.get("schema_version") != "rpf53-rev5-base-preflight-v1"
            or value.get("plan_revision") != PLAN_REVISION):
        raise ProbeError("BASE_PREFLIGHT_REVISION")
    current = _preflight()
    if (value.get("repo") != current.get("repo")
            or value.get("source") != current.get("source")
            or value.get("sdk") != current.get("sdk")
            or value.get("java") != current.get("java")
            or value.get("task_owned_jar") != current.get("task_owned_jar")
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


def _diagnostic_attempt_context() -> tuple[dict, int, Path, Path]:
    _check_worktree_directories()
    if PREFLIGHT.exists() or PREFLIGHT.is_symlink():
        raise ProbeError("DIAGNOSTIC_ALREADY_PASSED_OR_RECORDED")
    if not FIXTURE_ROOT.is_dir() or FIXTURE_ROOT.is_symlink():
        raise ProbeError("FIXTURE_ROOT_INVALID")
    attempt_dirs: dict[int, Path] = {}
    for child in FIXTURE_ROOT.iterdir():
        match = re.fullmatch(r"attempt-(0[1-2])", child.name)
        if (not match or child.is_symlink()
                or bool(getattr(child, "is_junction", lambda: False)())
                or not child.is_dir()):
            raise ProbeError("DIAGNOSTIC_ATTEMPT_STATE_INVALID")
        number = int(match.group(1))
        if number in attempt_dirs:
            raise ProbeError("DIAGNOSTIC_ATTEMPT_STATE_INVALID")
        attempt_dirs[number] = child

    preflight_paths = {
        1: ATTEMPT_PREFLIGHTS[0],
        2: ATTEMPT_PREFLIGHTS[1],
    }
    numbers = sorted(attempt_dirs)
    if numbers != list(range(1, len(numbers) + 1)):
        raise ProbeError("DIAGNOSTIC_ATTEMPT_STATE_INVALID")
    if not numbers:
        if any(path.exists() or path.is_symlink() for path in ATTEMPT_PREFLIGHTS[1:]):
            raise ProbeError("DIAGNOSTIC_ATTEMPT_STATE_INVALID")
        return _load_base_preflight(BASE_PREFLIGHT), 1, FIXTURE_ROOT / "attempt-01", BASE_PREFLIGHT

    if len(numbers) >= 2:
        raise ProbeError("DIAGNOSTIC_BUDGET_EXHAUSTED")
    last_base = None
    for number in numbers:
        attempt_dir = attempt_dirs[number]
        allowed = {"started.json", "result.json", "sdk-scratch"}
        if any(child.name not in allowed or child.is_symlink()
               or bool(getattr(child, "is_junction", lambda: False)())
               for child in attempt_dir.iterdir()):
            raise ProbeError("DIAGNOSTIC_ATTEMPT_STATE_INVALID")
        started_path, result_path = attempt_dir / "started.json", attempt_dir / "result.json"
        base_path = preflight_paths[number]
        if (not started_path.is_file() or started_path.is_symlink()
                or not result_path.is_file() or result_path.is_symlink()
                or not base_path.is_file() or base_path.is_symlink()):
            raise ProbeError("DIAGNOSTIC_ATTEMPT_RECORD_INCOMPLETE")
        started = strict_json(started_path.read_bytes())
        result = strict_json(result_path.read_bytes())
        base = strict_json(base_path.read_bytes())
        report = result.get("sdk_report") if type(result) is dict else None
        cleanup = result.get("cleanup") if type(result) is dict else None
        runtime_hash = started.get("runtime_source_sha256") if type(started) is dict else None
        if (type(started) is not dict or type(result) is not dict or type(base) is not dict
                or started.get("plan_id") != "RPF-53"
                or started.get("plan_revision") != PLAN_REVISION
                or started.get("attempt") != number
                or started.get("model_source") != "FIXTURE_TEST_ONLY"
                or started.get("one_shot") is not True
                or not re.fullmatch(r"[0-9a-f]{64}", runtime_hash or "")
                or started.get("run_id") != result.get("run_id")
                or started.get("base_preflight_sha256") != _sha_file(base_path)
                or base.get("schema_version") != "rpf53-rev5-base-preflight-v1"
                or base.get("plan_revision") != PLAN_REVISION
                or base.get("runtime_source", {}).get("sha256") != runtime_hash
                or result.get("schema_version") != "rpf53-rev5-sdk-fixture-diagnostic-v1"
                or result.get("plan_revision") != PLAN_REVISION
                or type(result.get("pids")) is not dict
                or type(result["pids"].get("popen_pid")) is not int
                or result["pids"]["popen_pid"] <= 0
                or type(result["pids"].get("host_ready_pid")) is not int
                or result["pids"]["host_ready_pid"] <= 0
                or type(result["pids"].get("completed_report_pid")) is not int
                or result["pids"]["completed_report_pid"] <= 0
                or type(result.get("acceptance_checks")) is not dict
                or not result["acceptance_checks"]
                or any(type(value) is not bool
                       for value in result["acceptance_checks"].values())
                or result.get("attempt") != number
                or result.get("status") != "FAIL"
                or result.get("provider_https_requests") != 0
                or result.get("business_http_requests") != 0
                or result.get("java_processes") != 0
                or type(result.get("fixture_completions_observed")) is not int
                or type(result.get("sdk_tool_calls_observed")) is not int
                or type(result.get("tool_returns_reinjected")) is not int
                or type(cleanup) is not dict
                or cleanup.get("sdk_child_started") not in (True, False)
                or (cleanup.get("sdk_child_started") is True
                    and (cleanup.get("sdk_child_exited") is not True
                         or type(result.get("sdk_exit_code")) is not int))
                or cleanup.get("sdk_child_external_connections") != []
                or cleanup.get("fixture_host_closed") is not True
                or cleanup.get("fixture_host_thread_stopped") is not True
                or cleanup.get("fixture_port_closed") is not True
                or (report is not None and type(report) is not dict)):
            raise ProbeError("DIAGNOSTIC_ATTEMPT_NOT_SAFE_TO_RETRY")
        if result.get("status") == "PASS":
            raise ProbeError("DIAGNOSTIC_SUCCESS_WITHOUT_PREFLIGHT")
        if (report is not None and type(report.get("guard_denials_count")) is int
                and report["guard_denials_count"] > 0):
            raise ProbeError("DIAGNOSTIC_GUARD_FAILURE_NOT_RETRYABLE")
        last_base = base

    if last_base is None:
        raise ProbeError("DIAGNOSTIC_ATTEMPT_STATE_INVALID")
    next_attempt = len(numbers) + 1
    next_base_path = preflight_paths[next_attempt]
    if next_base_path.exists() or next_base_path.is_symlink():
        raise ProbeError("DIAGNOSTIC_ATTEMPT_STATE_INVALID")
    current = _preflight()
    if not _diagnostic_retry_identity_valid(last_base, current):
        raise ProbeError("DIAGNOSTIC_SOURCE_NOT_REPAIRED")
    _write_once(next_base_path, canonical(current))
    return current, next_attempt, FIXTURE_ROOT / f"attempt-{next_attempt:02d}", next_base_path


def _diagnostic_retry_identity_valid(previous: object, current: object) -> bool:
    if type(previous) is not dict or type(current) is not dict:
        return False
    previous_repo_raw, current_repo_raw = previous.get("repo"), current.get("repo")
    if type(previous_repo_raw) is not dict or type(current_repo_raw) is not dict:
        return False
    previous_repo, current_repo = dict(previous_repo_raw), dict(current_repo_raw)
    previous_repo.pop("status_paths", None)
    current_repo.pop("status_paths", None)
    if (previous_repo != current_repo
            or any(previous.get(key) != current.get(key)
                   for key in ("source", "task_owned_jar", "sdk", "java", "provider", "push_effect"))):
        return False
    previous_runtime, current_runtime = previous.get("runtime_source"), current.get("runtime_source")
    if type(previous_runtime) is not dict or type(current_runtime) is not dict:
        return False
    previous_hash = previous_runtime.get("sha256")
    current_hash = current_runtime.get("sha256")
    return (re.fullmatch(r"[0-9a-f]{64}", previous_hash or "") is not None
            and re.fullmatch(r"[0-9a-f]{64}", current_hash or "") is not None
            and previous_hash != current_hash)


def _fixture_lineage_valid(host: ConfigLiveHost) -> bool:
    responses, trace = host.provider_responses, host.tool_trace
    expected_names = ("inspect_config", "create_config_v1", "update_config_v2")
    if len(responses) != 4 or len(trace) != 3:
        return False
    if any(type(item) is not dict for item in (*responses, *trace)):
        return False
    ids = [item.get("call_id") for item in trace]
    if (ids != [f"call_rpf53_fixture_{index}" for index in (1, 2, 3)]
            or [item.get("name") for item in trace] != list(expected_names)):
        return False
    for index, response in enumerate(responses):
        if (response.get("response_id") != f"chatcmpl-rpf53-fixture-{index + 1}"
                or response.get("model") != "rpf53-fixture-only"):
            return False
        expected_calls = [] if index == 3 else [trace[index]]
        actual_calls = response.get("tool_calls")
        if (type(actual_calls) is not list or len(actual_calls) != len(expected_calls)
                or any(type(call) is not dict for call in actual_calls)):
            return False
        for call, expected in zip(actual_calls, expected_calls):
            if (call.get("call_id") != expected.get("call_id")
                    or call.get("name") != expected.get("name")
                    or expected.get("provider_response_id") != response.get("response_id")):
                return False
        expected_returns = trace[:index]
        actual_returns = response.get("tool_returns")
        if (type(actual_returns) is not list or len(actual_returns) != len(expected_returns)
                or any(type(item) is not dict for item in actual_returns)):
            return False
        for returned, expected in zip(actual_returns, expected_returns):
            if (returned.get("call_id") != expected.get("call_id")
                    or returned.get("result_sha256") != expected.get("result_sha256")
                    or expected.get("returned_in_request") != expected.get("sequence") + 1):
                return False
    return all(item.get("sequence") == index + 1
               and item.get("provider_response_id") == responses[index]["response_id"]
               and item.get("returned_in_request") == index + 2
               and type(item.get("result_sha256")) is str
               and re.fullmatch(r"[0-9a-f]{64}", item["result_sha256"]) is not None
               for index, item in enumerate(trace))


def _fixture_report_checks(report: object, popen_pid: object,
                           ready_pid: object, sdk: dict) -> dict[str, bool]:
    expected = {"status", "framework", "version", "openai_version", "pid",
        "python_executable_sha256",
        "usage_type", "usage_fields", "requests", "input_tokens", "output_tokens",
        "tool_calls", "tool_callbacks", "sdk_source_sha256", "openai_source_sha256",
        "final_output_sha256", "final_text_persisted", "guard_denials",
        "provider_key_present", "business_key_present"}
    is_report = type(report) is dict
    value = report if is_report else {}
    report_pid = value.get("pid")
    pids_valid = type(popen_pid) is int and popen_pid > 0
    ready_valid = type(ready_pid) is int and ready_pid > 0
    report_pid_valid = type(report_pid) is int and report_pid > 0
    numeric = {name: value.get(name) for name in (
        "requests", "input_tokens", "output_tokens", "tool_calls", "tool_callbacks")}
    numeric_int = {name: type(item) is int for name, item in numeric.items()}
    numeric_nonnegative = {name: numeric_int[name] and numeric[name] >= 0
                           for name in numeric}
    usage_fields = ["input_tokens", "output_tokens", "requests", "tool_calls"]
    return {
        "report_type_exact": is_report,
        "report_fields_exact": is_report and set(value) == expected,
        "report_status_completed": value.get("status") == "COMPLETED",
        "report_framework_pinned": value.get("framework") == SDK_NAME,
        "report_pydantic_version_pinned": value.get("version") == SDK_VERSION,
        "report_openai_version_pinned": value.get("openai_version") == OPENAI_VERSION,
        "report_python_executable_hash_valid": type(value.get("python_executable_sha256")) is str
            and re.fullmatch(r"[0-9a-f]{64}", value["python_executable_sha256"]) is not None,
        "report_python_executable_hash_pinned": value.get("python_executable_sha256")
            == sdk.get("python_executable_sha256"),
        "popen_pid_positive_int": pids_valid,
        "host_ready_pid_positive_int": ready_valid,
        "completed_pid_positive_int": report_pid_valid,
        "popen_ready_pid_equal": pids_valid and ready_valid and popen_pid == ready_pid,
        "ready_completed_pid_equal": ready_valid and report_pid_valid and ready_pid == report_pid,
        "popen_completed_pid_equal": pids_valid and report_pid_valid and popen_pid == report_pid,
        "report_runusage_type_pinned": value.get("usage_type") == "pydantic_ai.usage.RunUsage",
        "report_usage_fields_list": type(value.get("usage_fields")) is list,
        "report_usage_fields_exact": type(value.get("usage_fields")) is list
            and value["usage_fields"] == usage_fields,
        "usage_requests_integer": numeric_int["requests"],
        "usage_requests_nonnegative": numeric_nonnegative["requests"],
        "usage_requests_four": numeric_nonnegative["requests"] and numeric["requests"] == 4,
        "usage_input_tokens_integer": numeric_int["input_tokens"],
        "usage_input_tokens_nonnegative": numeric_nonnegative["input_tokens"],
        "usage_output_tokens_integer": numeric_int["output_tokens"],
        "usage_output_tokens_nonnegative": numeric_nonnegative["output_tokens"],
        "usage_tool_calls_integer": numeric_int["tool_calls"],
        "usage_tool_calls_nonnegative": numeric_nonnegative["tool_calls"],
        "usage_tool_calls_three": numeric_nonnegative["tool_calls"]
            and numeric["tool_calls"] == 3,
        "usage_tool_callbacks_integer": numeric_int["tool_callbacks"],
        "usage_tool_callbacks_nonnegative": numeric_nonnegative["tool_callbacks"],
        "usage_tool_callbacks_three": numeric_nonnegative["tool_callbacks"]
            and numeric["tool_callbacks"] == 3,
        "sdk_source_hash_valid": type(value.get("sdk_source_sha256")) is str
            and re.fullmatch(r"[0-9a-f]{64}", value["sdk_source_sha256"]) is not None,
        "sdk_source_hash_pinned": value.get("sdk_source_sha256") == SDK_CORE_SHA256,
        "openai_source_hash_valid": type(value.get("openai_source_sha256")) is str
            and re.fullmatch(r"[0-9a-f]{64}", value["openai_source_sha256"]) is not None,
        "openai_source_hash_pinned": value.get("openai_source_sha256")
            == sdk.get("openai_core_sha256"),
        "final_output_hash_valid": type(value.get("final_output_sha256")) is str
            and re.fullmatch(r"[0-9a-f]{64}", value["final_output_sha256"]) is not None,
        "final_text_not_persisted": value.get("final_text_persisted") is False,
        "guard_denials_list": type(value.get("guard_denials")) is list,
        "guard_denials_empty": type(value.get("guard_denials")) is list
            and value["guard_denials"] == [],
        "provider_key_absent": value.get("provider_key_present") is False,
        "business_key_absent": value.get("business_key_present") is False,
    }


def _safe_report_field_names(report: object) -> dict:
    expected = {"status", "framework", "version", "openai_version", "pid",
        "python_executable_sha256",
        "usage_type", "usage_fields", "requests", "input_tokens", "output_tokens",
        "tool_calls", "tool_callbacks", "sdk_source_sha256", "openai_source_sha256",
        "final_output_sha256", "final_text_persisted", "guard_denials",
        "provider_key_present", "business_key_present"}
    if type(report) is not dict:
        return {"missing_fields": sorted(expected), "unexpected_field_names": []}
    names = set(report)
    safe_extra = [name if type(name) is str and re.fullmatch(r"[a-zA-Z0-9_]{1,64}", name)
                  else "REDACTED" for name in names - expected]
    return {"missing_fields": sorted(expected - names),
            "unexpected_field_names": sorted(safe_extra)}


def _safe_sdk_report(report: object) -> dict | None:
    """Keep only typed, non-secret report observations; never persist arbitrary child text."""
    if type(report) is not dict:
        return None
    expected_usage = ["input_tokens", "output_tokens", "requests", "tool_calls"]
    def text_if(value: object, expected: str) -> str:
        return value if type(value) is str and value == expected else "INVALID"
    def count_if(value: object) -> int | None:
        return value if type(value) is int and value >= 0 else None
    def sha_if(value: object) -> str | None:
        return value if type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) else None
    raw_usage_fields = report.get("usage_fields")
    safe_usage_fields = (list(raw_usage_fields) if type(raw_usage_fields) is list
        and len(raw_usage_fields) <= 8
        and all(type(item) is str and item in expected_usage for item in raw_usage_fields)
        else None)
    return {
        "status": text_if(report.get("status"), "COMPLETED"),
        "framework": text_if(report.get("framework"), SDK_NAME),
        "version": text_if(report.get("version"), SDK_VERSION),
        "openai_version": text_if(report.get("openai_version"), OPENAI_VERSION),
        "pid": report.get("pid") if type(report.get("pid")) is int and report["pid"] > 0 else None,
        "python_executable_sha256": sha_if(report.get("python_executable_sha256")),
        "usage_type": text_if(report.get("usage_type"), "pydantic_ai.usage.RunUsage"),
        "usage_fields": safe_usage_fields,
        "requests": count_if(report.get("requests")),
        "input_tokens": count_if(report.get("input_tokens")),
        "output_tokens": count_if(report.get("output_tokens")),
        "tool_calls": count_if(report.get("tool_calls")),
        "tool_callbacks": count_if(report.get("tool_callbacks")),
        "sdk_source_sha256": sha_if(report.get("sdk_source_sha256")),
        "openai_source_sha256": sha_if(report.get("openai_source_sha256")),
        "final_output_sha256": sha_if(report.get("final_output_sha256")),
        "final_text_persisted": report.get("final_text_persisted")
            if type(report.get("final_text_persisted")) is bool else None,
        "guard_denials_count": len(report["guard_denials"])
            if type(report.get("guard_denials")) is list else None,
        "provider_key_present": report.get("provider_key_present")
            if type(report.get("provider_key_present")) is bool else None,
        "business_key_present": report.get("business_key_present")
            if type(report.get("business_key_present")) is bool else None,
    }


def _public_diagnostic_attempt(result: dict) -> dict:
    report = result.get("sdk_report")
    return {
        "attempt": result["attempt"], "run_id": result["run_id"],
        "runtime_source_sha256": result["runtime_source_sha256"],
        "status": result["status"], "model_source": "FIXTURE_TEST_ONLY",
        "official_provider_capability": result["official_provider_capability"],
        "pids": result["pids"], "popen_executable_sha256": result["popen_executable_sha256"],
        "source_identity": result["source_identity"],
        "sdk_identity": result["sdk_identity"],
        "tool_schema_sha256": result["tool_schema_sha256"],
        "report_field_diagnostics": result["report_field_diagnostics"],
        "acceptance_checks": result["acceptance_checks"],
        "failed_checks": [name for name, passed in result["acceptance_checks"].items()
                          if passed is False],
        "fixture_completions_observed": result["fixture_completions_observed"],
        "sdk_tool_calls_observed": result["sdk_tool_calls_observed"],
        "tool_returns_observed": result["tool_returns_observed"],
        "tool_return_message_observations": result["tool_return_message_observations"],
        "tool_returns_reinjected": result["tool_returns_reinjected"],
        "sdk_tool_call_ids": result["sdk_tool_call_ids"],
        "returned_tool_ids": result["returned_tool_ids"],
        "fixture_completion_trace": result["fixture_completion_trace"],
        "visible_contract_checks": result["visible_contract_checks"],
        "tool_trace": result["tool_trace"],
        "returned_in_request": result["returned_in_request"],
        "sdk_report": report,
        "cleanup": result["cleanup"], "failure": result["failure"],
        "failure_attribution": result["failure_attribution"],
        "runtime_error_stage": result["runtime_error_stage"],
        "runtime_error_type": result["runtime_error_type"],
        "sdk_exit_code": result["sdk_exit_code"],
        "stdout_sha256": result["stdout_sha256"],
        "stderr_bytes": result["stderr_bytes"],
        "stderr_sha256": result["stderr_sha256"],
        "provider_https_requests": 0, "provider_tokens": 0,
        "business_http_requests": 0, "business_post_requests": 0, "java_processes": 0,
        "completed_at_utc": result["completed_at_utc"],
    }


def _record_public_diagnostic_attempt(result: dict) -> None:
    record = _public_diagnostic_attempt(result)
    artifact = {"schema_version": "rpf53-rev5-sdk-fixture-diagnostic-v1",
                "plan_id": "RPF-53", "plan_revision": PLAN_REVISION,
                "attempts": [record]}
    if SDK_FIXTURE_PREFLIGHT_PATH.exists() or SDK_FIXTURE_PREFLIGHT_PATH.is_symlink():
        previous = strict_json(SDK_FIXTURE_PREFLIGHT_PATH.read_bytes())
        if (type(previous) is not dict
                or previous.get("schema_version") != artifact["schema_version"]
                or previous.get("plan_revision") != PLAN_REVISION
                or type(previous.get("attempts")) is not list
                or len(previous["attempts"]) != result["attempt"] - 1):
            raise ProbeError("PUBLIC_DIAGNOSTIC_STATE_INVALID")
        artifact["attempts"] = [*previous["attempts"], record]
        _atomic_write(SDK_FIXTURE_PREFLIGHT_PATH, canonical(artifact))
    else:
        if result["attempt"] != 1:
            raise ProbeError("PUBLIC_DIAGNOSTIC_STATE_INVALID")
        _write_once(SDK_FIXTURE_PREFLIGHT_PATH, canonical(artifact))


def _fixture_return_message_ids(responses: list[dict]) -> list[str]:
    return [item.get("call_id") for response in responses
            for item in response.get("tool_returns", [])]


def _fixture_completion_trace(responses: list[dict]) -> list[dict]:
    return [{"response_id": response.get("response_id"), "model": response.get("model"),
        "tool_calls": [{"call_id": item.get("call_id"), "name": item.get("name")}
                       for item in response.get("tool_calls", [])],
        "tool_returns": [{"call_id": item.get("call_id"),
                          "result_sha256": item.get("result_sha256")}
                         for item in response.get("tool_returns", [])]}
        for response in responses]


def run_diagnostic() -> dict:
    base, attempt, attempt_dir, base_path = _diagnostic_attempt_context()
    sdk_python = _direct_sdk_executable(base["sdk"])
    attempt_dir.mkdir(parents=True)
    sdk_dir = attempt_dir / "sdk-scratch"
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
            "python_launcher_sha256": base["sdk"]["python_launcher_sha256"],
            "pydantic_record_sha256": base["sdk"]["pydantic"]["record_sha256"],
            "pydantic_record_entries": base["sdk"]["pydantic"]["record_entries"],
            "pydantic_record_mismatches": base["sdk"]["pydantic"]["record_mismatches"],
            "openai_record_sha256": base["sdk"]["openai"]["record_sha256"],
            "openai_record_entries": base["sdk"]["openai"]["record_entries"],
            "openai_record_mismatches": base["sdk"]["openai"]["record_mismatches"],
            "openai_core_sha256": base["sdk"]["openai_core_sha256"],
            "sdk_site_root_binding_sha256": base["sdk"]["sdk_site_root_binding_sha256"],
            "python_runtime_mapping_sha256": base["sdk"]["python_runtime_mapping_sha256"],
        }, task_owned_jar=base["task_owned_jar"], mode="FIXTURE_TEST_ONLY")
    marker = {"plan_id": "RPF-53", "plan_revision": PLAN_REVISION,
              "runtime_source_sha256": base["runtime_source"]["sha256"],
              "attempt": attempt, "run_id": run_id,
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
    host_thread_stopped = False
    runtime_error_type = None
    runtime_error_stage = None
    process_started = False
    timed_out = False
    stage = "host_start"
    try:
        host.start(host_port)
        config = {"port": host.port, "token": host.token,
                  "write_root": str(sdk_dir),
                  "sdk_readonly_path": str(SDK_SITE.resolve(strict=True)),
                  "sdk_site_root_binding_sha256": base["sdk"]["sdk_site_root_binding_sha256"],
                  "python_runtime_mapping_sha256": base["sdk"]["python_runtime_mapping_sha256"],
                  "instructions": contracts["execution"]["agent_instructions"],
                  "task_prompt": contracts["execution"]["task_prompt"],
                  "model": "rpf53-fixture-only", "max_runtime_seconds": 360,
                  "fixture": True}
        process = subprocess.Popen([str(sdk_python), "-I", "-B",
            str(ROOT / "runtime/runproof_runtime/effectwitness/config_live_external.py")],
            cwd=sdk_dir, env=_sdk_env(sdk_dir), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process_started = True
        stage = "sdk_run"
        try:
            stdout, stderr = process.communicate(canonical(config), timeout=360)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
        if stdout and len(stdout) <= 8192:
            try:
                report = strict_json(stdout)
            except Exception as exc:
                runtime_error_type = type(exc).__name__
                runtime_error_stage = "sdk_report_parse"
    except Exception as exc:
        runtime_error_type = type(exc).__name__
        runtime_error_stage = stage
    finally:
        host_thread = host._thread
        try:
            host.close()
        except Exception as exc:
            runtime_error_type = runtime_error_type or type(exc).__name__
            runtime_error_stage = runtime_error_stage or "fixture_host_cleanup"
        host_thread_stopped = host_thread is None or not host_thread.is_alive()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=10)
    try:
        sdk_external = _external_connections(process.pid) if process is not None else [
            {"state": "UNAVAILABLE", "remote": "UNAVAILABLE"}]
    except Exception:
        sdk_external = [{"state": "UNAVAILABLE", "remote": "UNAVAILABLE"}]
    try:
        host_port_closed = _port_closed(host_port)
    except Exception:
        host_port_closed = False
    tool_return_message_ids = _fixture_return_message_ids(host.provider_responses)
    returned_tool_ids = list(dict.fromkeys(tool_return_message_ids))
    returned_tool_count = len(returned_tool_ids)
    sdk_tool_ids = [item.get("call_id") for response in host.provider_responses
                    for item in response.get("tool_calls", [])]
    expected_call_ids = [f"call_rpf53_fixture_{index}" for index in (1, 2, 3)]
    popen_pid = process.pid if process is not None else None
    ready_pid = host.runtime.get("pid") if type(host.runtime) is dict else None
    report_checks = _fixture_report_checks(report, popen_pid, ready_pid, base["sdk"])
    checks = {
        "child_exit_zero": process is not None and process.returncode == 0,
        "sdk_child_process_started": process_started and process is not None,
        "popen_argv_is_pinned_interpreter": process is not None
            and type(process.args) is list and len(process.args) == 4
            and process.args[0] == str(sdk_python)
            and process.args[1:3] == ["-I", "-B"]
            and process.args[3] == str(ROOT / "runtime/runproof_runtime/effectwitness/config_live_external.py"),
        "popen_executable_hash_matches_preflight": process is not None
            and type(process.args) is list and len(process.args) == 4
            and _sha_file(Path(process.args[0])) == base["sdk"]["python_executable_sha256"],
        "pinned_interpreter_identity_matches": base["sdk"].get(
            "configured_executable_matches_sys") is True
            and re.fullmatch(r"[0-9a-f]{64}", base["sdk"].get(
                "python_executable_sha256", "")) is not None
            and re.fullmatch(r"[0-9a-f]{64}", base["sdk"].get(
                "python_launcher_sha256", "")) is not None,
        "fixture_completions_four": len(host.provider_responses) == 4,
        "agent_contract_visible_each_completion": len(host.visible_contract_checks) == 4
            and all(item.get("instructions_present") is True
                    and item.get("task_prompt_present") is True
                    and item.get("tool_help_exact") is True
                    and re.fullmatch(r"[0-9a-f]{64}", item.get("messages_sha256", ""))
                        is not None for item in host.visible_contract_checks),
        "sdk_tool_calls_three": len(host.tool_trace) == 3 and sdk_tool_ids == expected_call_ids,
        "tool_returns_three_unique": returned_tool_count == 3
            and returned_tool_ids == expected_call_ids,
        "tool_return_lineage_complete": _fixture_lineage_valid(host),
        "memory_backend_calls_three": len(backend.calls) == 3,
        "host_error_free": host.failure is None,
        "stderr_empty": not stderr,
        "runtime_error_absent": runtime_error_type is None,
        "not_timed_out": not timed_out,
        "provider_https_zero": ledger.usage()["provider_https_requests"] == 0,
        "business_http_zero": contracts["execution"]["service"]
            == {"transport": "IN_MEMORY_FIXTURE_ONLY"},
        "java_process_zero": process_started and process is not None
            and type(process.args) is list
            and process.args == [str(sdk_python), "-I", "-B",
                str(ROOT / "runtime/runproof_runtime/effectwitness/config_live_external.py")],
        "sdk_child_exited": process is not None and process.poll() is not None,
        "sdk_external_connections_empty": not sdk_external,
        "fixture_host_closed": host._server is None and host._thread is None,
        "fixture_host_thread_stopped": host_thread_stopped,
        "fixture_port_closed": host_port_closed,
    }
    checks.update({"sdk_report_" + name: passed
                   for name, passed in report_checks.items()})
    passed = all(checks.values())
    report_fields = _safe_report_field_names(report)
    denied_files = report.get("denied_files", []) if type(report) is dict else []
    safe_denied_files = [_safe_denied_basename(item) for item in denied_files
                         if type(item) is str] if type(denied_files) is list else []
    safe_error_type = (report.get("error_type") if type(report) is dict
        and type(report.get("error_type")) is str
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", report["error_type"])
        else None)
    safe_stage = (report.get("stage") if type(report) is dict
        and type(report.get("stage")) is str
        and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", report["stage"])
        else None)
    safe_guard_code = (report.get("guard_code") if type(report) is dict
        and type(report.get("guard_code")) is str
        and re.fullmatch(r"[A-Z0-9_]{1,80}", report["guard_code"])
        else None)
    failure_attribution = None if passed else {
        "failed_checks": [name for name, ok in checks.items() if not ok],
        "stage": safe_stage, "error_type": safe_error_type,
        "guard_code": safe_guard_code, "denied_files": safe_denied_files,
        "report_fields": report_fields,
    }
    result = {"schema_version": "rpf53-rev5-sdk-fixture-diagnostic-v1",
        "plan_revision": PLAN_REVISION, "attempt": attempt, "run_id": run_id,
        "runtime_source_sha256": base["runtime_source"]["sha256"],
        "source_identity": {"config_center_source_commit": base["source"]["source_commit"],
            "config_center_manifest_sha256": base["source"]["manifest_sha256"],
            "config_center_jar_sha256": base["source"]["jar_sha256"],
            "task_owned_jar": base["task_owned_jar"],
            "config_center_file_count": base["source"]["source_file_count"],
            "config_center_total_bytes": base["source"]["source_total_bytes"],
            "java_version": base["java"]["version"],
            "java_executable_sha256": base["java"]["executable_sha256"],
            "java_release_sha256": base["java"]["release_sha256"]},
        "official_provider_capability": {"model": base["provider"]["model"],
            "model_version": base["provider"]["model_version"],
            "tool_calls_supported": base["provider"]["tool_calls_supported"],
            "official_docs_snapshot_date": base["provider"]["official_docs_snapshot_date"],
            "peak_input_usd_per_million_cache_miss": base["provider"][
                "peak_input_usd_per_million_cache_miss"],
            "peak_output_usd_per_million": base["provider"][
                "peak_output_usd_per_million"]},
        "sdk_identity": {"python_version": base["sdk"]["python_version"],
            "configured_executable_matches_sys": base["sdk"]["configured_executable_matches_sys"],
            "python_executable_sha256": base["sdk"]["python_executable_sha256"],
            "python_launcher_sha256": base["sdk"]["python_launcher_sha256"],
            "pydantic_record_sha256": base["sdk"]["pydantic"]["record_sha256"],
            "pydantic_record_entries": base["sdk"]["pydantic"]["record_entries"],
            "pydantic_record_mismatches": base["sdk"]["pydantic"]["record_mismatches"],
            "openai_record_sha256": base["sdk"]["openai"]["record_sha256"],
            "openai_record_entries": base["sdk"]["openai"]["record_entries"],
            "openai_record_mismatches": base["sdk"]["openai"]["record_mismatches"],
            "sdk_core_sha256": base["sdk"]["sdk_core_sha256"],
            "openai_core_sha256": base["sdk"]["openai_core_sha256"],
            "sdk_site_root_binding_sha256": base["sdk"]["sdk_site_root_binding_sha256"],
            "python_runtime_mapping_sha256": base["sdk"]["python_runtime_mapping_sha256"]},
        "pids": {"popen_pid": popen_pid, "host_ready_pid": ready_pid,
                 "completed_report_pid": report.get("pid") if type(report) is dict
                    and type(report.get("pid")) is int else None},
        "popen_executable_sha256": base["sdk"].get("python_executable_sha256"),
        "report_field_diagnostics": report_fields,
        "status": "PASS" if passed else "FAIL", "model_source": "FIXTURE_TEST_ONLY",
        "provider_https_requests": 0, "business_http_requests": 0, "java_processes": 0,
        "fixture_completions_observed": len(host.provider_responses),
        "sdk_tool_calls_observed": len(host.tool_trace),
        "tool_returns_observed": returned_tool_count,
        "tool_return_message_observations": len(tool_return_message_ids),
        "tool_returns_reinjected": returned_tool_count,
        "sdk_tool_call_ids": sdk_tool_ids, "returned_tool_ids": returned_tool_ids,
        "tool_return_message_call_ids": tool_return_message_ids,
        "fixture_completion_trace": _fixture_completion_trace(host.provider_responses),
        "visible_contract_checks": host.visible_contract_checks,
        "acceptance_checks": checks,
        "returned_in_request": [item.get("returned_in_request") for item in host.tool_trace],
        "sdk_report": _safe_sdk_report(report),
        "tool_trace": host.tool_trace, "fake_backend_calls": backend.calls,
        "tool_schema_summary": host.tool_schema_summary,
        "cleanup": {"sdk_child_started": process_started,
                    "sdk_child_exited": process is not None and process.poll() is not None,
                    "sdk_child_external_connections": sdk_external,
                    "fixture_host_closed": host._server is None and host._thread is None,
                    "fixture_host_thread_stopped": host_thread_stopped,
                    "fixture_port_closed": host_port_closed},
        "tool_schema_sha256": host.tool_schema_sha256,
        "failure": host.failure,
        "runtime_error_stage": runtime_error_stage,
        "runtime_error_type": runtime_error_type,
        "timed_out": timed_out,
        "failure_attribution": failure_attribution,
        "sdk_exit_code": process.returncode if process else None,
        "stdout_sha256": sha256_bytes(stdout), "stderr_bytes": len(stderr),
        "stderr_sha256": sha256_bytes(stderr), "completed_at_utc": _utc()}
    _write_once(attempt_dir / "result.json", canonical(result))
    _record_public_diagnostic_attempt(result)
    if not passed:
        raise ProbeError("SDK_FIXTURE_DIAGNOSTIC_FAILED")
    preflight = {"schema_version": "rpf53-rev5-preflight-v1", "base": base,
                 "diagnostic": {"attempt": attempt, "status": "PASS",
                    "base_preflight_path": str(base_path.relative_to(ROOT)).replace("\\", "/"),
                    "base_preflight_sha256": _sha_file(base_path),
                    "result_sha256": _sha_file(attempt_dir / "result.json"),
                    "tool_schema_sha256": host.tool_schema_sha256,
                    "fixture_completions": len(host.provider_responses),
                    "sdk_tool_calls": len(host.tool_trace),
                    "tool_returns_reinjected": returned_tool_count,
                    "runtime_source_sha256": base["runtime_source"]["sha256"]}}
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
    args = [str(JAVA), f"-Djava.io.tmpdir={temp_dir}", "-jar", str(TASK_OWNED_JAR),
            "--spring.profiles.active=local", "--server.address=127.0.0.1",
            f"--server.port={port}", "--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}",
            "--security.api-keys[0].app=" + effect["app"],
            "--security.api-keys[0].env=" + effect["env"]]
    if api_key.encode("ascii") in " ".join(args).encode("ascii"):
        raise ProbeError("API_KEY_IN_JAVA_ARGV")
    if not _argv_jar_path_matches(args, TASK_OWNED_JAR, WORK_ROOT):
        raise ProbeError("JAVA_POPEN_JAR_PATH_MISMATCH")
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
    expected = {"status", "framework", "version", "openai_version", "pid",
        "python_executable_sha256", "usage_type",
        "usage_fields", "requests", "input_tokens", "output_tokens", "tool_calls", "tool_callbacks",
        "sdk_source_sha256", "openai_source_sha256", "final_output_sha256",
        "final_text_persisted", "guard_denials", "provider_key_present",
        "business_key_present"}
    return value if type(value) is dict and set(value) == expected else None


def _live_preflight() -> dict:
    if not PREFLIGHT.is_file() or PREFLIGHT.is_symlink():
        raise ProbeError("A03_DIAGNOSTIC_NOT_PASSED")
    value = strict_json(PREFLIGHT.read_bytes())
    if (value.get("schema_version") != "rpf53-rev5-preflight-v1"
            or value.get("diagnostic", {}).get("status") != "PASS"
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("diagnostic", {}).get("tool_schema_sha256", ""))):
        raise ProbeError("A03_DIAGNOSTIC_NOT_PASSED")
    base = value.get("base")
    current = _preflight()
    for key in ("repo", "source", "task_owned_jar", "sdk", "java", "runtime_source"):
        if base.get(key) != current.get(key):
            raise ProbeError("PREFLIGHT_SOURCE_DRIFT")
    if not current["provider"]["key_present"]:
        raise ProbeError("DEEPSEEK_KEY_UNAVAILABLE", "PROVIDER")
    java_runtime = _verify_java_runtime()
    if any(java_runtime.get(key) != current["java"].get(key)
           for key in ("version", "executable_sha256", "release_sha256")):
        raise ProbeError("DIRECT_JDK17_RUNTIME_DRIFT")
    value["java_runtime_verification"] = java_runtime
    return value


def _public_attempt(record: dict) -> dict:
    fields = ("attempt", "run_id", "request_sha256", "reservation_tokens", "status",
        "transport", "response_id", "returned_model", "usage", "tool_schema_sha256",
        "tool_call_ids", "returned_tool_ids", "tool_returns")
    return {key: record.get(key) for key in fields}


def _make_payload(preflight: dict, contracts: dict, report: dict,
                  host: ConfigLiveHost, ledger: ProviderLedger,
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
    sdk_identity = preflight["base"]["sdk"]
    task_jar = contracts["experiment"]["task_owned_jar"]
    source_identity = {
        "provider": PROVIDER_NAME, "provider_model": PROVIDER_MODEL,
        "provider_endpoint": PROVIDER_ORIGIN + PROVIDER_PATH,
        "config_center_source_commit": SOURCE_COMMIT,
        "config_center_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "config_center_jar_sha256": SOURCE_JAR_SHA256,
        "task_owned_jar_relative_path": task_jar["relative_path"],
        "task_owned_jar_sha256": task_jar["copy_sha256"],
        "task_owned_jar_bytes": task_jar["copy_bytes"],
        "runtime_source_sha256": preflight["base"]["runtime_source"]["sha256"],
        "sdk_core_sha256": SDK_CORE_SHA256,
        "python_version": sdk_identity["python_version"],
        "python_executable_sha256": sdk_identity["python_executable_sha256"],
        "python_launcher_sha256": sdk_identity["python_launcher_sha256"],
        "pydantic_record_sha256": sdk_identity["pydantic"]["record_sha256"],
        "pydantic_record_entries": sdk_identity["pydantic"]["record_entries"],
        "pydantic_record_mismatches": sdk_identity["pydantic"]["record_mismatches"],
        "openai_record_sha256": sdk_identity["openai"]["record_sha256"],
        "openai_record_entries": sdk_identity["openai"]["record_entries"],
        "openai_record_mismatches": sdk_identity["openai"]["record_mismatches"],
        "openai_core_sha256": sdk_identity["openai_core_sha256"],
        "sdk_site_root_binding_sha256": sdk_identity["sdk_site_root_binding_sha256"],
        "python_runtime_mapping_sha256": sdk_identity["python_runtime_mapping_sha256"],
        "java_version": java_safety["version"],
        "java_executable_sha256": java_safety["executable_sha256"],
    }
    sdk = {
        "framework": report["framework"], "version": report["version"],
        "openai_version": report["openai_version"], "popen_pid": report["popen_pid"],
        "ready_pid": report["ready_pid"], "pid": report["pid"],
        "python_executable_sha256": report["python_executable_sha256"],
        "exit_code": report["exit_code"], "usage_type": report["usage_type"],
        "usage_fields": report["usage_fields"], "requests": report["requests"],
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
    return {"schema_version": EVIDENCE_SCHEMA, "plan_id": "RPF-53",
        "contracts": contracts, "source_identity": source_identity, "sdk": sdk,
        "provider": provider, "agent_contract_visibility": host.visible_contract_checks,
        "tool_trace": host.tool_trace,
        "http_observations": client.observations,
        "authority_before": before, "authority_after": after,
        "oracle": oracle, "safety": safety,
        "limitations": {"issuer_authenticity": "NOT_ESTABLISHED",
            "database_independent_authority": "NOT_ESTABLISHED",
            "independent_reproduction": "NOT_TESTED", "PGE": "PGE_NOT_EXECUTED",
            "workswarm": "NOT_PROVEN"}}


def _verify_in_independent_process(path: Path, anchor: str | None) -> int:
    verifier_python = _DIRECT_SDK_PYTHON or Path(sys.executable).resolve(strict=True)
    args = [str(verifier_python), "-B", str(Path(__file__).resolve()), "--verify", str(path)]
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
    sdk_python = _direct_sdk_executable(preflight["base"]["sdk"])
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
        task_owned_jar=preflight["base"]["task_owned_jar"],
        sdk_identity={
            "python_version": preflight["base"]["sdk"]["python_version"],
            "python_executable_sha256": preflight["base"]["sdk"]["python_executable_sha256"],
            "python_launcher_sha256": preflight["base"]["sdk"]["python_launcher_sha256"],
            "pydantic_record_sha256": preflight["base"]["sdk"]["pydantic"]["record_sha256"],
            "pydantic_record_entries": preflight["base"]["sdk"]["pydantic"]["record_entries"],
            "pydantic_record_mismatches": preflight["base"]["sdk"]["pydantic"]["record_mismatches"],
            "openai_record_sha256": preflight["base"]["sdk"]["openai"]["record_sha256"],
            "openai_record_entries": preflight["base"]["sdk"]["openai"]["record_entries"],
            "openai_record_mismatches": preflight["base"]["sdk"]["openai"]["record_mismatches"],
            "openai_core_sha256": preflight["base"]["sdk"]["openai_core_sha256"],
            "sdk_site_root_binding_sha256": preflight["base"]["sdk"]["sdk_site_root_binding_sha256"],
            "python_runtime_mapping_sha256": preflight["base"]["sdk"]["python_runtime_mapping_sha256"],
        }, tool_schema_sha256=preflight["diagnostic"]["tool_schema_sha256"])
    business_key = secrets.token_urlsafe(32)
    deadline = time.monotonic() + LIMITS["scenario_seconds"]
    client = ConfigLiveHttp(contracts, business_key, deadline=deadline)
    business = ConfigLiveBusiness(contracts, client)
    ledger = None
    host = None
    api_key = ""
    java_jar_proof = None
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
        java_jar_proof = _actual_java_jar_proof(
            java_process, preflight["base"]["task_owned_jar"])
        java_listener_pid = java_process.pid if _listener_owned(java_process.pid, java_port) else None
        java_external = _external_connections(java_process.pid)
        if java_external:
            raise ProbeError("JAVA_EXTERNAL_CONNECTION_OBSERVED")
        if java_log.redactions or java_log.overflow:
            raise ProbeError("JAVA_LOG_SECRET_OR_SIZE_GUARD")
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise ProbeError("DEEPSEEK_KEY_DISAPPEARED_BEFORE_MARKER", "PROVIDER")
        _write_once(CONTRACTS_PATH, canonical(contracts))
        marker = {"plan_id": "RPF-53", "plan_revision": PLAN_REVISION, "run_id": run_id,
            "started_at_utc": _utc(), "preflight_sha256": _sha_file(PREFLIGHT),
            "java_runtime_verification": preflight["java_runtime_verification"],
            "task_owned_jar": preflight["base"]["task_owned_jar"],
            "java_jar_launch_proof": java_jar_proof,
            "contracts_sha256": digest(contracts), "one_shot": True,
            "provider_https_requests": 0, "total_tokens_reserved_limit": LIMITS["total_tokens"],
            "cost_cny_upper_limit": LIMITS["estimated_cost_cny_upper"],
            "automatic_retries": 0}
        _write_once(STARTED_PATH, canonical(marker))
        ledger = ProviderLedger(LEDGER_PATH, run_id, create=True)
        host = ConfigLiveHost(contracts, ledger, business, api_key=api_key,
                              expected_tool_schema_sha256=preflight["diagnostic"]["tool_schema_sha256"])
        if not client.initial_state_valid():
            raise ProbeError("INITIAL_STATE_NOT_ABSENT")
        authority_before = {"current_seq": 1, "history_seq": 2}
        java_external = _external_connections(java_process.pid)
        if java_external:
            raise ProbeError("JAVA_EXTERNAL_CONNECTION_OBSERVED")
        host.start(host_port)
        config = {"port": host.port, "token": host.token,
            "write_root": str(sdk_dir),
            "sdk_readonly_path": str(SDK_SITE.resolve(strict=True)),
            "sdk_site_root_binding_sha256": preflight["base"]["sdk"]["sdk_site_root_binding_sha256"],
            "python_runtime_mapping_sha256": preflight["base"]["sdk"]["python_runtime_mapping_sha256"],
            "instructions": contracts["execution"]["agent_instructions"],
            "task_prompt": contracts["execution"]["task_prompt"],
            "model": PROVIDER_MODEL,
            "max_runtime_seconds": LIMITS["scenario_seconds"], "fixture": False}
        child_env = _sdk_env(sdk_dir)
        if "DEEPSEEK_API_KEY" in child_env or "CONFIG_CENTER_API_KEY" in child_env:
            raise ProbeError("SDK_CHILD_SECRET_ENVIRONMENT")
        sdk_process = subprocess.Popen([str(sdk_python), "-I", "-B",
            str(ROOT / "runtime/runproof_runtime/effectwitness/config_live_external.py")],
            cwd=sdk_dir, env=child_env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if (sdk_process.args[0] != str(sdk_python)
                or _sha_file(Path(sdk_process.args[0]))
                    != preflight["base"]["sdk"]["python_executable_sha256"]):
            raise ProbeError("SDK_POPEN_EXECUTABLE_IDENTITY_MISMATCH")
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
        if (sdk_report["python_executable_sha256"]
                != preflight["base"]["sdk"]["python_executable_sha256"]):
            raise ProbeError("SDK_REPORT_EXECUTABLE_IDENTITY_MISMATCH")
        sdk_report["exit_code"] = sdk_exit_code
        sdk_report["stderr_bytes"] = len(stderr)
        sdk_report["stderr_sha256"] = sha256_bytes(stderr)
        ready_pid = host.runtime.get("pid") if type(host.runtime) is dict else None
        sdk_report["popen_pid"] = sdk_process.pid
        sdk_report["ready_pid"] = ready_pid
        if not (type(ready_pid) is int and ready_pid > 0
                and type(sdk_report["pid"]) is int and sdk_report["pid"] > 0
                and sdk_report["pid"] == sdk_process.pid == ready_pid):
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
            failure["provider_usage_state"] = (
                ledger.data["requests"][-1]["status"]
                if ledger is not None and ledger.data["requests"] else "NO_ATTEMPT")
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
        if host is not None:
            try:
                host.close()
                host_closed = host._server is None and host._thread is None
            except Exception:
                host_closed = False
        else:
            host_closed = True
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
        if ledger is not None:
            ledger.finish(cleanup_ok and failure is None)

    if ledger is None or host is None:
        pre_marker_summary = {
            "schema_version": "rpf53-rev5-live-summary-v1", "plan_id": "RPF-53",
            "plan_revision": PLAN_REVISION, "status": "BLOCKED",
            "run_id": run_id, "marker_created": False,
            "task_owned_jar": preflight["base"]["task_owned_jar"],
            "java_jar_launch_proof": java_jar_proof,
            "java": {"pid": java_process.pid if java_process else None,
                "listener_pid": java_listener_pid, "health_gets": health,
                "exit_code": java_exit_code, "stopped": process_stopped,
                "listener_closed": listener_closed if java_process else False,
                "external_connections": java_external, "log": java_log_info},
            "provider_key_present": bool(api_key), "provider_requests": [],
            "provider_usage": {"provider_https_requests": 0, "tokens": 0,
                "confirmed_tokens": 0, "usage_known": True,
                "automatic_retries": 0, "trials": 0},
            "sdk": None, "business_http_requests": len(client.observations),
            "cleanup_ok": cleanup_ok,
            "failure": failure or {"domain": "PLATFORM", "code": "PRE_MARKER_STOP"},
            "completed_at_utc": _utc(),
        }
        _write_once(SUMMARY_PATH, canonical(pre_marker_summary))
        return pre_marker_summary

    report = sdk_report or {}
    if sdk_report is not None and sdk_exit_code is not None:
        report["exit_code"] = sdk_exit_code
        report["stderr_bytes"] = len(stderr)
        report["stderr_sha256"] = sha256_bytes(stderr)
    if sdk_process is not None:
        report.setdefault("pid", sdk_process.pid)
        report.setdefault("popen_pid", sdk_process.pid)
        report.setdefault("ready_pid", host.runtime.get("pid")
                          if type(host.runtime) is dict else None)
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
                            and cleanup_ok and ledger.usage()["usage_known"]
                            and type(java_jar_proof) is dict
                            and java_jar_proof.get("actual_process_argv_matches_copy") is True) else "PARTIAL"
    if host.failure and host.failure.get("domain") == "PROVIDER":
        status = "PARTIAL"
    summary = {
        "schema_version": "rpf53-rev5-live-summary-v1", "plan_id": "RPF-53",
        "status": status, "run_id": run_id, "started_marker_sha256": _sha_file(STARTED_PATH),
        "contracts_sha256": digest(contracts), "runtime_source_sha256": preflight["base"]["runtime_source"]["sha256"],
        "provider_key_present": True, "provider_requests": ledger.data["requests"],
        "provider_usage": ledger.usage(), "sdk": report,
        "tool_trace": host.tool_trace, "tool_rejections": host.tool_rejections,
        "http_observations": client.observations,
        "authority_before": {"current_seq": 1, "history_seq": 2} if authority_before else None,
        "authority_after": after_readback, "oracle": oracle,
        "java": {"pid": java_process.pid if java_process else None,
                 "listener_pid": java_listener_pid, "health_gets": health,
                 "exit_code": java_exit_code, "stopped": process_stopped,
                 "listener_closed": listener_closed if java_process else False,
                 "external_connections": java_external, "log": java_log_info,
                 "jar_provenance": java_jar_proof,
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
        "java_jar_provenance": java_jar_proof,
        "sdk_pid": sdk_process.pid, "sdk_stopped": sdk_stopped,
        "sdk_external_connections": sdk_external, "host_closed": host_closed,
        "parent_external_connections": [],
        "sdk_provider_key_absent": report["provider_key_present"] is False,
        "sdk_business_key_absent": report["business_key_present"] is False,
        "sdk_guard_denials": report["guard_denials"]}
    result = {"status": status, "provider_responses": host.provider_responses,
              "sdk_report": report, "tool_schema_sha256": host.tool_schema_sha256,
              "tool_trace": host.tool_trace, "tool_rejections": host.tool_rejections,
              "http_observations": client.observations,
              "authority_before": authority_before, "authority_after": authority_after,
              "java_safety": {**safety, "version": preflight["base"]["java"]["version"],
                              "executable_sha256": preflight["base"]["java"]["executable_sha256"]}}
    payload = _make_payload(preflight, contracts, {
        **report, "exit_code": sdk_exit_code, "stderr_bytes": len(stderr),
        "stderr_sha256": sha256_bytes(stderr)}, host, ledger, client,
        authority_before, authority_after, result["java_safety"], safety)
    try:
        evidence_raw = canonical({"schema_version": EVIDENCE_SCHEMA,
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
    summary["evidence"] = {"path": "spikes/rpf-53/rev-5/config-live-evidence.json",
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
                "task_owned_jar": value["task_owned_jar"],
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
        usage = value.get("provider_usage", {})
        oracle = value.get("oracle", {})
        print(json.dumps({"status": value["status"], "run_id": value["run_id"],
            "provider_requests": usage.get("provider_https_requests", 0),
            "tokens": usage.get("tokens", 0),
            "estimated_cost_cny_upper": usage.get("estimated_cost_cny_upper"),
            "effect_outcome": oracle.get("outcome", "NOT_RUN"),
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
