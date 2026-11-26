"""Run the three frozen R72r2 tests and independently recheck their local evidence."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import subprocess
import sys
import tarfile
import unittest
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4


SELF = Path(__file__).absolute()
REPO = SELF.parents[1]
MODULE = "runtime.tests.test_effectwitness_pge_r72r2"
TEST = MODULE.replace(".", "/") + ".py"
MATRIX = "ci/runtime-contract-test-matrix.json"
METHODS = (
    "test_no_operation_no_sqlite_setup",
    "test_session_reserve_settle_native_parity",
    "test_real_sqlite_unknown_readonly_gate_and_policy",
)
IDS = tuple(f"{MODULE}.BudgetTests.{method}" for method in METHODS)
OWNER_ROOT = Path(".local/rpf-72-rev-2/tests")
TASK_ROOT = Path(".local/rpf-124")
OWNER_ID = re.compile(r"rpf72r2-[a-f0-9]{16}")
FLAGS = ("-I", "-S", "-B", "-X", "utf8")
SCHEMA = "runproof-rpf124-r72r2/v1"
MARKER = b"RPF124_ORIGINAL "
TIMEOUT = 180
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024

# RPF-123 observed these same LF and raw bytes. No archived artifact is needed.
TEST_SHA = "93c8a5ec4bb7142d8bff54b7fb1c9e2615b23ecb96e251bc0b6b61af2a4ec3af"
MATRIX_SHA = "6cebea668a48894277fc65dece2e27c4349610bd9a92c080947ef62c6fcc7a4b"
CAPSULE_SHA = "beeede73244c33998b0e7492143c27064b372cbd537b43cdc33b01fbb5e27f06"
PACKAGE_SHA = {
    "runtime/__init__.py": "c6e0c83d22491539f41a81edc96d7db4d834ee80fa266e70b6acb2ea36243778",
    "runtime/tests/__init__.py": "9bdd237c2661d4ea0decc14c6cc221785d9d2150336ae50dcef64de5fa73218f",
    "runtime/runproof_runtime/__init__.py": "aa545c76886ce9c02d3d7f04f2f27a1cf797a5b1e8e7845f0879328206a12757",
    "runtime/runproof_runtime/effectwitness/__init__.py": "eed7d971a9b3fc80994c5458e21599dcc6df6b0b4734c67fcb6455561613b90b",
}
PROVIDER_ZERO = {"reservations": 0, "sends": 0, "tokens": 0}


class Refused(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def plain(path):
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            return None
        reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        require(not reparse and not stat.S_ISLNK(info.st_mode), f"LINK_OR_REPARSE: {part.name}")
    if stat.S_ISREG(info.st_mode):
        require(info.st_nlink == 1, f"HARD_LINK: {path.name}")
    return info


def read_file(path):
    info = plain(path)
    require(info is not None, f"FILE_MISSING: {path.name}")
    require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_EVIDENCE_BYTES,
            f"INVALID_FILE: {path.name}")
    return path.read_bytes()


def write_json(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")


def read_json(path):
    raw = read_file(path)
    try:
        value = json.loads(raw)
        require(type(value) is dict and raw == canonical(value) + b"\n", f"RECORD_FORMAT: {path.name}")
    except (ValueError, UnicodeError) as exc:
        raise Refused(f"RECORD_FORMAT: {path.name}") from exc
    return value


def task_directory(value, repo, *, fresh):
    path = Path(os.path.abspath(value))
    namespace = repo / TASK_ROOT
    require(path.parent == namespace and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", path.name),
            "OUTPUT_SCOPE: choose a direct child of .local/rpf-124")
    info = plain(path)
    if fresh:
        require(info is None, "OUTPUT_EXISTS: choose a new run directory")
    else:
        require(info is not None and stat.S_ISDIR(info.st_mode), "RUN_DIRECTORY_MISSING")
    return path


def windows_ntfs(path):
    require(os.name == "nt" and sys.implementation.name == "cpython" and sys.version_info >= (3, 12),
            "WINDOWS_CPYTHON_3_12_REQUIRED")
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
            "PYTHON_FLAGS: use -I -S -B -X utf8")
    from ctypes import WinDLL, create_unicode_buffer, c_wchar_p

    require(re.fullmatch(r"[a-zA-Z]:\\", path.anchor), "LOCAL_DRIVE_REQUIRED")
    kernel = WinDLL("kernel32", use_last_error=True)
    drive = c_wchar_p(path.anchor)
    fs = create_unicode_buffer(32)
    require(kernel.GetDriveTypeW(drive) in (2, 3), "LOCAL_DRIVE_REQUIRED")
    require(kernel.GetVolumeInformationW(drive, None, 0, None, None, None, fs, len(fs)) and fs.value == "NTFS",
            "NTFS_REQUIRED")


def child_environment():
    return {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "SystemDrive", "ComSpec")
            if key in os.environ}


def git_read(git, *args):
    require(git.is_absolute() and git.is_file(), "GIT_EXE: supply the verified absolute Git executable")
    env = child_environment()
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS="0",
               GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
    result = subprocess.run(
        [str(git), "-c", "core.fsmonitor=false", "-C", str(REPO), *args],
        stdin=subprocess.DEVNULL, capture_output=True, env=env, timeout=30, check=False,
    )
    require(result.returncode == 0, f"GIT_{args[0].upper()}_FAILED: exit={result.returncode}")
    return result.stdout


def capsule_paths():
    names = read_file(SELF.with_name("rpf124-r72r2-source-paths.txt")).decode("ascii").splitlines()
    require(len(names) == len(set(names)) == 71 and TEST in names, "SOURCE_LIST")
    for name in names:
        path = PurePosixPath(name)
        require(not path.is_absolute() and path.as_posix() == name and ".." not in path.parts
                and re.fullmatch(r"(?:runtime/|spikes/rpf-(?:53|55|68|70|71|72)/)[a-z0-9_./-]+", name),
                "SOURCE_LIST_PATH")
    return names


def source_paths():
    return [*capsule_paths(), *PACKAGE_SHA, MATRIX]


def source_identity(files):
    hashes = {name: sha(raw) for name, raw in files.items()}
    require(set(hashes) == set(source_paths()), "SOURCE_FILE_SET")
    require(hashes[TEST] == TEST_SHA, "FROZEN_TEST_SHA")
    require(hashes[MATRIX] == MATRIX_SHA, "FROZEN_MATRIX_SHA")
    for name, expected in PACKAGE_SHA.items():
        require(hashes[name] == expected, f"FROZEN_PACKAGE_SHA: {name}")
    capsule = sha(canonical({name: hashes[name] for name in capsule_paths()}))
    require(capsule == CAPSULE_SHA, "FROZEN_SOURCE_CAPSULE_SHA")

    rows = [row for row in json.loads(files[MATRIX])["modules"] if row["path"] == TEST]
    require(len(rows) == 1 and rows[0]["source_sha256"] == TEST_SHA, "MATRIX_TEST_BINDING")
    for method in METHODS:
        rules = [row["route"] for row in rows[0]["rules"] if row["selector"] == f"BudgetTests.{method}"]
        require(rules == ["DEDICATED_RUNNER"], f"MATRIX_ROUTE: {method}")
    classes = [node for node in ast.parse(files[TEST]).body
               if isinstance(node, ast.ClassDef) and node.name == "BudgetTests"]
    require(len(classes) == 1, "FROZEN_TEST_CLASS")
    selectors = [node.name for node in classes[0].body if isinstance(node, ast.FunctionDef)]
    require(all(selectors.count(method) == 1 for method in METHODS), "FROZEN_METHOD_IDS")
    return {"files": len(hashes), "files_sha256": sha(canonical(hashes)), "capsule_sha256": capsule,
            "test_lf_sha256": TEST_SHA, "matrix_lf_sha256": MATRIX_SHA}


def git_blobs(git, revision):
    require(isinstance(revision, str) and re.fullmatch(r"[a-f0-9]{40}", revision), "FULL_SOURCE_SHA_REQUIRED")
    require(Path(os.fsdecode(git_read(git, "rev-parse", "--show-toplevel").strip())) == REPO,
            "GIT_ROOT_MISMATCH")
    commit = git_read(git, "rev-parse", "--verify", revision + "^{commit}").decode("ascii").strip()
    require(commit == revision, "GIT_SOURCE_COMMIT")
    names = source_paths()
    blobs = {}
    for row in git_read(git, "ls-tree", "-rz", commit, "--", *names).split(b"\0"):
        if not row:
            continue
        header, name = row.decode("ascii").split("\t", 1)
        mode, kind, blob = header.split()
        require(kind == "blob" and mode in ("100644", "100755"), f"GIT_SOURCE_BLOB: {name}")
        blobs[name] = blob
    require(set(blobs) == set(names), "GIT_SOURCE_FILE_SET")
    return blobs


def check_blobs(files, blobs):
    require(files.keys() == blobs.keys(), "GIT_SOURCE_FILE_SET")
    for name, raw in files.items():
        blob = hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()
        require(blob == blobs[name], f"GIT_BLOB_MISMATCH: {name}")


def git_snapshot(git, revision):
    blobs = git_blobs(git, revision)
    raw = git_read(git, "archive", "--format=tar", revision, "--", *blobs)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for item in archive:
            if item.isdir():
                continue
            require(item.isfile() and item.name in blobs and item.name not in files
                    and item.size <= MAX_EVIDENCE_BYTES, "GIT_ARCHIVE_MEMBER")
            with archive.extractfile(item) as source:
                files[item.name] = source.read()
    check_blobs(files, blobs)
    return files


def tree_files(root, *, skip=None, directories=None):
    info = plain(root)
    require(info is not None and stat.S_ISDIR(info.st_mode), f"DIRECTORY_MISSING: {root.name}")
    files = {}
    pending = [root]
    while pending:
        for path in pending.pop().iterdir():
            info = plain(path)
            require(info is not None, f"FILE_MISSING: {path.name}")
            if stat.S_ISDIR(info.st_mode):
                if path != skip:
                    require(directories is None or path in directories, f"UNEXPECTED_DIRECTORY: {path.name}")
                    pending.append(path)
            else:
                require(stat.S_ISREG(info.st_mode), f"INVALID_FILE: {path.name}")
                files[path.relative_to(root).as_posix()] = path
    return files


def read_snapshot(root):
    names = source_paths()
    directories = {root / path for name in names for path in Path(name).parents}
    paths = tree_files(root, skip=root / ".local", directories=directories)
    require(set(paths) == set(names), "SNAPSHOT_FILE_SET")
    return {name: read_file(path) for name, path in paths.items()}


def owned_paths(owner, index):
    require(isinstance(owner, str) and OWNER_ID.fullmatch(owner), "OWNER_ID")
    root = OWNER_ROOT / owner
    wal = root / "wal.jsonl"
    database = root / "runs" / f"{owner}-2" / "business/orders.sqlite3" if index == 2 else None
    return wal, database


def owner_evidence(root, owner, index):
    wal, database = owned_paths(owner, index)
    paths = (wal, database) if database else (wal,)
    folder = root / OWNER_ROOT / owner
    observed = {path.relative_to(root) for path in tree_files(folder).values()}
    missing = set(paths) - observed
    require(not missing, "EVIDENCE_MISSING: " + ", ".join(sorted(path.as_posix() for path in missing)))
    require(observed == set(paths), f"UNEXPECTED_EVIDENCE_FILES: {owner}")
    records = {}
    for relative in paths:
        path = root / relative
        before = plain(path)
        require(before is not None, f"EVIDENCE_MISSING: {relative.as_posix()}")
        data = read_file(path)
        after = plain(path)
        require(after is not None and (before.st_mtime_ns, before.st_size) == (after.st_mtime_ns, after.st_size)
                and len(data) == after.st_size, f"EVIDENCE_CHANGED_DURING_READ: {relative.as_posix()}")
        records[relative.as_posix()] = {"sha256": sha(data), "bytes": len(data), "mtime_ns": after.st_mtime_ns}
    return records


class Guard:
    """Constrain the audited Python interfaces used by the frozen methods."""

    def __init__(self, root, *, database_allowed, read_only=False, owner=None):
        self.root = root
        self.work = root / OWNER_ROOT
        self.python_root = Path(sys.base_prefix).resolve()
        self.database_allowed = database_allowed
        self.read_only = read_only
        self.owner = owner
        self.database = None
        self.denied = []
        self.writes = Counter()
        self.connections = Counter()

    def deny(self, reason):
        self.denied.append(reason)
        raise PermissionError(reason)

    def owned(self, value, *, mkdir=False):
        if isinstance(value, int):
            self.deny("FD_MUTATION")
        path = Path(os.path.abspath(os.fsdecode(value)))
        if mkdir and path in (self.root / ".local", self.work.parent, self.work):
            plain(path)
            return path
        if not path.is_relative_to(self.work) or path == self.work:
            self.deny("OUTSIDE_OWNER")
        owner = path.relative_to(self.work).parts[0]
        if not OWNER_ID.fullmatch(owner):
            self.deny("OWNER_ID")
        if self.owner is None:
            if plain(self.work / owner) is not None:
                self.deny("OWNER_EXISTS")
            self.owner = owner
        if self.owner != owner:
            self.deny("SECOND_OWNER")
        plain(path)
        return path

    def sqlite(self, value):
        name = os.fsdecode(value)
        mode = None
        if name.startswith("file:"):
            uri = urlsplit(name)
            if uri.netloc or uri.fragment:
                self.deny("SQLITE_URI")
            name = unquote(uri.path)
            if re.match(r"^/[a-zA-Z]:/", name):
                name = name[1:]
            mode = parse_qs(uri.query).get("mode")
        if not self.database_allowed or (self.read_only and mode != ["ro"]):
            self.deny("SQLITE_NOT_ALLOWED")
        path = self.owned(name)
        _, relative = owned_paths(self.owner, 2)
        if path != self.root / relative or self.database not in (None, path):
            self.deny("SQLITE_TARGET")
        self.database = path
        self.connections["read_only" if mode == ["ro"] else "ordinary"] += 1

    def audit(self, event, args):
        if event.startswith(("socket.", "http.client.", "subprocess.", "ctypes.", "winreg.",
                             "os.exec", "os.spawn", "os.posix_spawn")) or event in (
            "os.system", "os.fork", "os.link", "os.symlink", "os.chdir", "os.rename",
            "os.chmod", "os.utime", "os.truncate",
        ):
            self.deny("DISALLOWED_CALL: " + event)
        if event == "import" and args[0].split(".")[0] in {"openjiuwen", "openai", "deepseek", "jiuwen"}:
            self.deny("SDK_IMPORT")
        if event == "open":
            path, _, flags = args
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
                if self.read_only:
                    self.deny("READ_ONLY_WRITE")
                self.owned(path)
                self.writes[event] += 1
            elif not isinstance(path, int):
                path = Path(os.path.abspath(os.fsdecode(path)))
                if not path.is_relative_to(self.root) and not path.is_relative_to(self.python_root):
                    self.deny("OUTSIDE_READ")
        if event in ("os.mkdir", "os.remove", "os.rmdir"):
            if self.read_only or args[-1] != -1:
                self.deny("DISALLOWED_MUTATION: " + event)
            self.owned(args[0], mkdir=event == "os.mkdir")
            self.writes[event] += 1
        if event == "sqlite3.connect":
            self.sqlite(args[0])


def observe_capsule(root):
    sys.path.insert(0, str(root))
    from runtime.runproof_runtime.effectwitness import config_experiment_verify as config
    from runtime.runproof_runtime.effectwitness import pge_r68_context as native
    from runtime.runproof_runtime.effectwitness import pge_r72r2_owner_source as source

    require(source.ROOT == native.ROOT == config.ROOT == root, "IMPORT_ROOT_MISMATCH")
    probe = source.OwnerScope("rpf72r2-0000000000000000")
    require(probe.root.parent == root / OWNER_ROOT and probe.root.resolve().parent == root / OWNER_ROOT,
            "OWNER_ROOT_MISMATCH")
    capsule = source.SourceCapsule.observe()
    public = capsule.public()
    require(public["raw_digest"] == public["lf_digest"] == CAPSULE_SHA, "OBSERVED_CAPSULE_MISMATCH")
    return source, capsule


def interpreter_identity():
    return {"implementation": sys.implementation.name, "python": sys.version.split()[0],
            "sha256": sha(Path(sys.executable).read_bytes()), "sqlite": sqlite3.sqlite_version,
            "windows_build": sys.getwindowsversion().build, "filesystem": "NTFS"}


def manifest(path):
    data = read_json(path / "run.json")
    run_id = data.get("run_id")
    require(data.get("schema") == SCHEMA and isinstance(run_id, str) and re.fullmatch(r"[a-f0-9]{32}", run_id)
            and data.get("methods") == list(IDS) and data.get("owner_root") == OWNER_ROOT.as_posix(),
            "RUN_IDENTITY")
    require(data.get("tool_lf_sha256") == sha(SELF.read_bytes().replace(b"\r\n", b"\n")),
            "RUN_TOOL_MISMATCH")
    return data


def method_paths(output, index):
    label = f"method{index + 1}"
    return output / f"{label}.log", output / f"{label}.json"


def child_argv(binding, index):
    return [*FLAGS, f"ci/{SELF.name}", "_method", binding, IDS[index]]


def original(binding, test_id):
    require(test_id in IDS, "METHOD_NOT_ALLOWED")
    index = IDS.index(test_id)
    root = Path.cwd()
    output = task_directory(root.parent, REPO, fresh=False)
    require(root == output / "source" == root.resolve(strict=True), "SNAPSHOT_ROOT")
    log, receipt = method_paths(output, index)
    launch_log = plain(log)
    require(launch_log is not None and launch_log.st_size == 0 and plain(receipt) is None,
            "METHOD_LAUNCH_NOT_FRESH")
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, "PYTHON_FLAGS")
    header = manifest(output)
    require(sha(canonical(header)) == binding, "METHOD_RUN_BINDING")
    require(source_identity(read_snapshot(root)) == header["source_identity"], "METHOD_SOURCE_BINDING")

    guard = Guard(root, database_allowed=index == 2)
    sys.addaudithook(guard.audit)
    observe_capsule(root)
    suite = unittest.defaultTestLoader.loadTestsFromName(test_id)
    tests = list(suite)
    require(len(tests) == 1 and tests[0].id() == test_id, "EXACT_ORIGINAL_METHOD")
    execution = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    passed = execution.testsRun == 1 and execution.wasSuccessful() and not execution.skipped and not guard.denied
    database = guard.database.relative_to(root).as_posix() if guard.database else None
    report = {"binding": binding, "id": test_id, "pid": os.getpid(), "status": "PASS" if passed else "FAIL",
              "test_count": execution.testsRun, "owner": guard.owner, "database": database,
              "sqlite_connections": dict(guard.connections), "python_write_events": dict(guard.writes),
              "denied": guard.denied}
    print(MARKER.decode("ascii") + canonical(report).decode("ascii"), flush=True)
    return 0 if passed else 1


def original_observation(log, process, binding, index):
    method = IDS[index]
    require(process.get("binding") == binding and process.get("id") == method
            and process.get("argv") == child_argv(binding, index), f"PROCESS_RUN_BINDING: {method}")
    require(type(process.get("exit")) is int and process["exit"] == 0 and process.get("timed_out") is False,
            f"ORIGINAL_PROCESS_FAILED: {method} exit={process.get('exit')} timeout={process.get('timed_out')}")
    pid = process.get("pid")
    require(type(pid) is int and pid > 0, f"PROCESS_PID: {method}")
    require(sha(log) == process.get("log_sha256"), f"LOG_DIGEST_MISMATCH: {method}")
    lines = log.splitlines()
    terminal = lines[-1] if lines else b""
    require(terminal.startswith(MARKER), f"ORIGINAL_RECEIPT_MISSING: {method}")
    try:
        row = json.loads(terminal[len(MARKER):])
    except (ValueError, UnicodeError) as exc:
        raise Refused(f"ORIGINAL_RECEIPT_FORMAT: {method}") from exc
    require(type(row) is dict and row.get("binding") == binding and row.get("id") == method
            and row.get("pid") == pid and row.get("status") == "PASS" and row.get("denied") == []
            and type(row.get("test_count")) is int and row["test_count"] == 1,
            f"ORIGINAL_RECEIPT_BINDING: {method}")
    _, database = owned_paths(row.get("owner"), index)
    require(row.get("database") == (database.as_posix() if database else None), f"ORIGINAL_DATABASE: {method}")
    connections = row.get("sqlite_connections")
    if database:
        require(type(connections) is dict and set(connections) == {"ordinary", "read_only"}
                and all(type(count) is int and count > 0 for count in connections.values()),
                f"ORIGINAL_CONNECTIONS: {method}")
    else:
        require(connections == {}, f"ORIGINAL_CONNECTIONS: {method}")
    return row


def run_method(output, root, binding, index):
    log, receipt = method_paths(output, index)
    argv = child_argv(binding, index)
    env = child_environment()
    env.update(TEMP=str(output / "tmp"), TMP=str(output / "tmp"), TMPDIR=str(output / "tmp"))
    started = datetime.now(timezone.utc).isoformat()
    with log.open("xb") as stream:
        with subprocess.Popen([sys.executable, *FLAGS, str(SELF), *argv[len(FLAGS) + 1:]],
                              cwd=root, env=env, stdin=subprocess.DEVNULL,
                              stdout=stream, stderr=subprocess.STDOUT) as child:
            timed_out = False
            try:
                child.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                timed_out = True
                child.kill()
                child.wait()
            exit_code, pid = child.returncode, child.pid
    raw = log.read_bytes()
    process = {"binding": binding, "id": IDS[index], "pid": pid, "launch_requested_utc": started,
               "argv": argv, "exit": exit_code, "timed_out": timed_out, "log_sha256": sha(raw)}
    try:
        result = original_observation(raw, process, binding, index)
        process["files"] = owner_evidence(root, result["owner"], index)
    finally:
        write_json(receipt, process)
    return {"id": IDS[index], "pid": pid, "exit": exit_code, "status": result["status"],
            "owner": result["owner"]}


def run(git, revision, output):
    output = task_directory(output, REPO, fresh=True)
    windows_ntfs(output)
    files = git_snapshot(git, revision)
    identity = source_identity(files)
    interpreter = interpreter_identity()
    output.parent.mkdir(parents=True, exist_ok=True)
    require(plain(output) is None, "OUTPUT_EXISTS: choose a new run directory")
    output.mkdir()
    root = output / "source"
    (output / "tmp").mkdir()
    for name, raw in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    require(plain(root / ".local") is None and root == root.resolve(strict=True), "SNAPSHOT_NOT_FRESH")
    header = {"schema": SCHEMA, "run_id": uuid4().hex, "source_sha": revision, "source_identity": identity,
              "tool_lf_sha256": sha(SELF.read_bytes().replace(b"\r\n", b"\n")), "interpreter": interpreter,
              "methods": list(IDS), "owner_root": OWNER_ROOT.as_posix()}
    write_json(output / "run.json", header)
    binding = sha(canonical(header))
    methods = [run_method(output, root, binding, index) for index in range(len(IDS))]
    write_json(output / "complete.json", completion(output, binding))
    return {"status": "ORIGINAL_TESTS_PASS", "run_id": header["run_id"], "source_sha": revision,
            "output": output.relative_to(REPO).as_posix(), "methods": methods}


def refund_facts(database, context, state):
    returned = [event["row"] for event in state["events"] if event["kind"] == "TOOL_RETURN"]
    require([row["name"] for row in returned] == ["inspect_order", "refund_order", "reconcile_order"],
            "ORIGINAL_REFUND_ROUTE")
    unknown, reconciled = returned[1]["result"], returned[2]["result"]
    require(unknown["status"] == "UNKNOWN_OUTCOME" and reconciled["readonly"] is True, "UNKNOWN_READ_ONLY_ROUTE")
    faults = [event["fault"] for event in state["events"] if event["kind"] == "FAULT"]
    require(len(faults) == 1 and all(faults[0].get(flag) is True
            for flag in ("planned", "triggered", "observed", "agent_exposed")), "REFUND_FAULT_EVIDENCE")

    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        environments = db.execute("SELECT owner, environment_id, reset_generation FROM environment").fetchall()
        orders = db.execute("SELECT order_id, refunded_minor, currency, status, revision FROM orders").fetchall()
        refunds = db.execute("SELECT * FROM refunds").fetchall()
        db.rollback()
    require(len(environments) == len(orders) == len(refunds) == 1, "SQLITE_SINGLE_REFUND")
    environment, order, refund = environments[0], orders[0], dict(refunds[0])
    declared = context.public()
    fault_contracts = [row["experiment"] for row in declared["rounds"][1].values()
                       if row["experiment"]["fault_enabled"]]
    require(len(fault_contracts) == 1 and environment["owner"] == declared["owner"]
            and environment["environment_id"] == fault_contracts[0]["environment_id"]
            and environment["reset_generation"] == 0, "SQLITE_OWNER_BINDING")
    settled = state["results"]["sqlite_refund-1"]["receipt"]
    require(refund == reconciled["receipt"] and refund["receipt_id"] == settled["receipt_id"]
            and refund["operation_id"] == settled["operation_id"] == unknown["operation_id"]
            and refund["order_id"] == order["order_id"]
            and refund["amount_minor"] == order["refunded_minor"] == 2500
            and refund["currency"] == order["currency"] == "CNY"
            and refund["status"] == "COMMITTED" and order["status"] == "REFUNDED"
            and refund["committed_revision"] == order["revision"] == 1, "SQLITE_REFUND_BINDING")
    return {"original_response": unknown["status"], "fault": faults[0], "receipt_count": 1,
            "receipt": refund, "order_status": order["status"], "order_revision": order["revision"]}


def readback(source, capsule, root, row, index):
    from runtime.runproof_runtime.effectwitness import pge_r72r2_budget_policy as policy
    from runtime.runproof_runtime.effectwitness.pge_r72r2_budget_ledger import NativeLedger

    context = source.Context(source.OwnerScope(row["owner"]), capsule, (29001, 29002, 29003))
    ledger = NativeLedger(context)
    state = ledger.read()
    counts = {name: value for name, value in state["counts"].items() if value}
    require(state["counts"]["provider"] == state["reserved_tokens"] == state["reserved_cost_micro_cny"] == 0
            and not any(event["kind"] in {"MODEL_REQUEST", "MODEL_RESPONSE", "PROCESS_START"}
                        for event in state["events"]), "PROVIDER_OR_SDK_EVIDENCE")
    facts = {"wal_frames": len(ledger.frames), "nonzero_budget_counts": counts}
    if index == 0:
        rejections = [event["reason"] for event in state["events"]
                      if event.get("audit_type") == policy.TAG and event.get("status") == "REJECTED"]
        require(rejections == ["CURRENT_OWNER_OPERATION_REQUIRED"] and not counts and not state["tickets"],
                "SQLITE_SETUP_REJECTION")
        facts.update(sqlite_setup=0, rejection=rejections[0])
        return facts

    audit = policy.audit(ledger.frames, context, policy.BudgetPolicy.create(context))
    require(audit["status"] == "PASS" and audit["physical_wal"] == "NATIVE_ONLY", "NATIVE_POLICY_AUDIT")
    facts["policy_native_transactions"] = len(audit["transactions"])
    if index == 1:
        session = [(entry["action"], entry["resource"], entry["ticket"]) for entry in audit["transactions"]]
        expected = [("RESERVE", "session", "session-1"), ("SETTLE", "session", "session-1")]
        require(counts == {"session": 1} and session == expected
                and state["results"]["session-1"]["status"] == "COMPLETED", "SESSION_PARITY")
        facts["session_ticket_status"] = "COMPLETED"
        return facts

    require(counts == {"sqlite_setup": 1, "sqlite_refund": 1, "authority_read": 3}, "REFUND_BUDGET_COUNTS")
    _, database = owned_paths(row["owner"], index)
    facts.update(refund_facts(root / database, context, state))
    return facts


def completion(output, binding):
    receipts = [method_paths(output, index)[1] for index in range(len(IDS))]
    return {"binding": binding, "process_sha256": {receipt.name: sha(read_file(receipt)) for receipt in receipts}}


def verify(git, output):
    output = task_directory(output, REPO, fresh=False)
    windows_ntfs(output)
    header = manifest(output)
    binding = sha(canonical(header))
    root = output / "source"
    originals = []
    records = []
    for index in range(len(IDS)):
        log, receipt = method_paths(output, index)
        process = read_json(receipt)
        originals.append(original_observation(read_file(log), process, binding, index))
        records.append(process.get("files"))
    require(read_json(output / "complete.json") == completion(output, binding), "PROCESS_RECORD_DIGEST_MISMATCH")

    files = read_snapshot(root)
    require(source_identity(files) == header.get("source_identity"), "RUN_SOURCE_IDENTITY")
    check_blobs(files, git_blobs(git, header.get("source_sha")))
    owners = {row["owner"] for row in originals}
    work = root / OWNER_ROOT
    require(plain(work) is not None and len(owners) == len(IDS)
            and {entry.name for entry in work.iterdir()} == owners, "RUN_OWNER_SET")
    before = []
    for index, row in enumerate(originals):
        observed = owner_evidence(root, row["owner"], index)
        require(observed == records[index], f"EVIDENCE_DIGEST_OR_MTIME_MISMATCH: {row['id']}")
        before.append(observed)

    guard = Guard(root, database_allowed=True, read_only=True, owner=originals[2]["owner"])
    sys.addaudithook(guard.audit)
    source, capsule = observe_capsule(root)
    methods = []
    for index, row in enumerate(originals):
        try:
            facts = readback(source, capsule, root, row, index)
        except (KeyError, ValueError, OSError, sqlite3.Error) as exc:
            raise Refused(f"READBACK_FAILED: {row['id']}: {exc}") from exc
        methods.append({"id": row["id"], "owner": row["owner"], "assertion": "PASS",
                        "original_pid": row["pid"], "readback": facts})
    after = [owner_evidence(root, row["owner"], index) for index, row in enumerate(originals)]
    require(after == before and not guard.denied and guard.connections == {"read_only": 1},
            "READ_ONLY_EVIDENCE_CHANGED")
    return {"status": "CONTENT_CHECKED_LOCAL", "issuer": "NOT_ESTABLISHED",
            "run_id": header["run_id"], "source_sha": header["source_sha"], "methods": methods,
            "provider": PROVIDER_ZERO, "unchanged_files": sum(map(len, before)),
            "read_only_sqlite_connections": guard.connections["read_only"]}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv and argv[0] == "_method":
            require(len(argv) == 3, "METHOD_ARGUMENTS")
            return original(argv[1], argv[2])
        parser = argparse.ArgumentParser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True)
        for command in ("run", "verify"):
            action = commands.add_parser(command)
            action.add_argument("--git", type=Path, required=True, help="absolute path to verified Git executable")
            action.add_argument("--output", required=True, help="run directory under .local/rpf-124/")
            if command == "run":
                action.add_argument("--source", required=True, help="full local Git commit SHA")
        args = parser.parse_args(argv)
        if args.command == "run":
            result = run(args.git, args.source, args.output)
        else:
            result = verify(args.git, args.output)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, tarfile.TarError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "NOT_CHECKED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
