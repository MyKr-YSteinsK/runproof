"""Build and verify bounded RPF-102 capsules without SDK or network access."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import (
    CASES, LIMIT, PINS, ROOT, STOP, canonical, check, sha, strict, sync_dir, validate_request,
)
from runtime.runproof_runtime.effectwitness.sdk_presend_diagnostic import (
    CONTEXT, REPORT, context, source_sha, validate_public,
)
from runtime.runproof_runtime.effectwitness.sdk_presend_oracle import member_names, verify

SCHEMA = "rpf102-rev3-capsule-v1"
LEDGER = "rev3-admission.json"
MANIFEST = "manifest.json"
CAPSULE_ROOT = ROOT.parent / "rpf-102-rev3-capsule"
HISTORICAL_RUN = 42580171633
FORMAL = {"cases": list(CASES), "max_sends": 3, "max_bytes": 3 * LIMIT}
CAPS = {"dispatches": 1, "sdk_children": 2, "receivers": 2, "simultaneous_children": 2,
        "completion_posts": 4, "forwards": 3, "forward_bytes": 3 * LIMIT, "tool_callbacks": 2,
        "job_seconds": 480, "sdk_child_seconds": 45, "provider_calls": 0, "provider_tokens": 0,
        "provider_fees": 0, "real_business_writes": 0, "key_probes": 0}
OWNER_DIRS = {"venv", "tmp", *CASES}
OWNER_MEMBERS = {LEDGER, "install-report.json", "environment.json", "formal.json", *OWNER_DIRS}
READ_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError)
STATES = ("VERIFIED", "FAILURE_DIAGNOSTIC", "UNAVAILABLE", "NOT_RUN")


def hexadecimal(value, length):
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def checked_path(path, *, directory=False, missing=False):
    path = Path(os.path.abspath(path))
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if missing and part == path:
                return path
            raise
        check(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 1024,
              "CAPSULE_LINK")
        if part != path or directory:
            check(stat.S_ISDIR(info.st_mode), "CAPSULE_DIRECTORY")
        else:
            check(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "CAPSULE_FILE")
    return path


def read(path, limit=8192):
    with checked_path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    check(len(raw) <= limit, "CAPSULE_MEMBER_LIMIT")
    return raw


def create(path, raw):
    with checked_path(path, missing=True).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(path.parent)


def ledger(owner, source, run_id):
    check(hexadecimal(owner, 32) and hexadecimal(source, 40)
          and type(run_id) is int and 0 < run_id < 10**16, "CAPSULE_ADMISSION")
    return {"schema": "rpf102-rev3-admission-v1", "owner": owner, "source_git_sha": source,
            "github_run_id": run_id, "github_run_attempt": 1, "caps": CAPS,
            "direct_pins": PINS, "case_policy": "NORMAL_BEFORE_CONDITIONAL_UNKNOWN",
            "sdk_network": "LOOPBACK_ONLY",
            "historical_run": HISTORICAL_RUN, "historical_normal": "FAIL_CONSUMED"}


def exact(row, *keys):
    check(type(row) is dict and set(row) == set(keys), "CAPSULE_FIELDS")
    return row


def integer(value, low=0, high=2**63 - 1):
    check(type(value) is int and low <= value <= high, "CAPSULE_INTEGER")


def digests(row, *keys):
    check(all(hexadecimal(row[k], 64) for k in keys), "CAPSULE_DIGEST")


def validate_environment(raw):
    row = exact(strict(raw), "python", "exe_sha256", "packages")
    check(type(row["python"]) is str and re.fullmatch(r"3\.12\.[0-9]{1,3}", row["python"]), "CAPSULE_PYTHON")
    digests(row, "exe_sha256")
    packages = row["packages"]
    check(type(packages) is dict and len(packages) <= 80 and all(packages.get(k) == v for k, v in PINS.items()),
          "CAPSULE_PACKAGES")
    for name, version in packages.items():
        check(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name)
              and not name.startswith(("sk-", "ghp-", "github-pat-", "bearer-"))
              and type(version) is str and re.fullmatch(r"[0-9][0-9a-z.+!-]{0,47}", version), "CAPSULE_PACKAGE")
    return row


def validate_post(raw, case, number):
    body = validate_request(raw, number, case)
    check(set(body) <= {"model", "messages", "tools", "tool_choice", "stream", "parallel_tool_calls",
                        "max_tokens", "max_completion_tokens", "n"}, "CAPSULE_POST_FIELDS")
    for key in ("max_tokens", "max_completion_tokens"):
        if key in body:
            integer(body[key], 1, 128)
    exact(body["messages"][0], "role", "content")
    tool = exact(body["tools"][0], "type", "function")["function"]
    check(set(tool) <= {"name", "description", "parameters", "strict"}
          and tool.get("description", "") in ("", "Read the result of the fixed fictional conformance tool.")
          and type(tool.get("strict", False)) is bool, "CAPSULE_TOOL")
    if "parameters" in tool:
        schema = tool["parameters"]
        check(type(schema) is dict and set(schema) <= {"type", "properties", "additionalProperties", "required"}
              and schema.get("type") == "object" and schema.get("properties", {}) == {}
              and schema.get("additionalProperties", False) is False
              and schema.get("required", []) == [], "CAPSULE_TOOL_SCHEMA")
    if number == 2:
        assistant, result = body["messages"][1:]
        check(set(assistant) <= {"role", "content", "tool_calls"}
              and assistant.get("content") in (None, ""), "CAPSULE_ASSISTANT")
        call = exact(assistant["tool_calls"][0], "id", "type", "function")
        exact(call["function"], "name", "arguments")
        exact(result, "role", "tool_call_id", "content")


def check_sdk_output(row, case):
    exact(row, "pid", "exe_sha256", "packages", "tool_callbacks", "terminal")
    integer(row["pid"], 1)
    digests(row, "exe_sha256")
    terminal = row["terminal"]
    if case == "NORMAL":
        exact(terminal, "status", "output_sha256", "sdk_reported_requests", "sdk_reported_tool_calls",
              "sdk_reported_usage", "usage_kind")
        check(terminal["output_sha256"] == sha(STOP.encode()), "CAPSULE_OUTPUT")
        integer(terminal["sdk_reported_requests"], 2, 2)
        integer(terminal["sdk_reported_tool_calls"], 1, 1)
        usage = exact(terminal["sdk_reported_usage"], "input_tokens", "output_tokens")
        for count in usage.values():
            integer(count, 0, 4096)
    # The independent Oracle binds package pins, terminal vocabulary and callback contents.


def check_receipt(name, row, case):
    if name == "sdk-output.json":
        check_sdk_output(row, case)
    elif name == "sdk-launch.json":
        exact(row, "pid", "start_ns", "exe_sha256", "host", "network")
        for key in ("pid", "start_ns"):
            integer(row[key], 1)
    elif name == "sdk-exit.json":
        exact(row, "pid", "exit", "exit_ns", "stdout_sha256")
        integer(row["pid"], 1)
        integer(row["exit"], 0, 0)
        integer(row["exit_ns"], 1)
    elif name == "receiver-launch.json":
        exact(row, "pid", "nonce", "exe_sha256", "start_ns")
    elif name == "receiver-exit.json":
        exact(row, "pid", "exit", "exit_ns", "exe_sha256")
    elif name.startswith("sender-"):
        integer(row["pid"], 1)
        for key in ("entry_ns", "return_ns", "bytes"):
            integer(row[key], 1)
    # Remaining JSON members have exact schemas and bindings in the Oracle.


def nonce_member(name):
    return name in ("receiver-ready.json", "receiver-launch.json") or bool(
        re.fullmatch(r"(?:sender|receiver)-[12]\.json", name)
    )


def verify_members(owner, case, members):
    for i in (1, 2):
        validate_post(members[f"sdk-post-{i}.raw"], case, i)
    result = verify(owner, case, members)
    for name, raw in members.items():
        if name.endswith(".json"):
            check_receipt(name, strict(raw), case)
    return result


def project(name, raw):
    if not nonce_member(name):
        return raw
    row = strict(raw)
    row["nonce"] = sha(b"rpf102-public-receiver-binding-v1\0" + row["nonce"].encode("ascii"))
    return canonical(row)


def member_limit(name):
    if name == "wal.jsonl":
        return 131072
    return LIMIT if name.endswith(".raw") else 8192


def case_evidence(folder, case):
    names = member_names(case)
    expected = {*names, CONTEXT, REPORT, "writer.lock", "active"}
    entries = {entry.name for entry in checked_path(folder, directory=True).iterdir()}
    check(entries <= expected, "CAPSULE_PRIVATE_EXTRA")
    for name in entries:
        checked_path(folder / name)
    check("active" not in entries, "CAPSULE_ACTIVE_WAL")
    check(strict(read(folder / CONTEXT)) == context(folder, case), "CAPSULE_CONTEXT")
    return {name: read(folder / name, member_limit(name)) for name in names}


def bind_result(result, environment, diagnostic, case):
    check(environment and result["python_exe_sha256"] == environment["exe_sha256"]
          and diagnostic["final_classification"] == (
              "NORMAL_VERIFIED" if case == "NORMAL" else "UNKNOWN_EXPECTED_DENIAL"),
          "CAPSULE_PROVENANCE")
    for counter, observed in (("sdk_post_count", "sdk_posts"), ("tool_callback_count", "tool_callbacks"),
                              ("provider_reserve_count", "provider_tickets"), ("send_entry_count", "send_entries"),
                              ("receiver_receipt_count", "send_entries"), ("received_bytes", "received_bytes")):
        check(diagnostic[counter] == result[observed], "CAPSULE_DIAGNOSTIC_COUNT")


def collect_case(folder, case, environment, *, allow_full):
    files = {}
    if not folder.exists() and not folder.is_symlink():
        return "NOT_RUN", files
    try:
        checked_path(folder, directory=True)
        check(strict(read(folder / CONTEXT)) == context(folder, case), "CAPSULE_CONTEXT")
        raw = read(folder / REPORT)
        diagnostic = validate_public(raw)
        check(diagnostic["case"] == case and diagnostic["source_sha256"] == source_sha(),
              "CAPSULE_DIAGNOSTIC")
        files[REPORT] = (raw, raw)
    except READ_ERRORS:
        return "UNAVAILABLE", {}
    if allow_full and environment is not None:
        try:
            originals = case_evidence(folder, case)
            result = verify_members(folder.parent.name, case, originals)
            bind_result(result, environment, diagnostic, case)
            published = {name: project(name, raw) for name, raw in originals.items()}
            verify_members(folder.parent.name, case, published)
            files.update({name: (raw, published[name]) for name, raw in originals.items()})
            return "VERIFIED", files
        except READ_ERRORS:
            pass
    return "FAILURE_DIAGNOSTIC", files


def build(owner_dir, output, expected_sha, run_id):
    owner_dir = checked_path(owner_dir, directory=True)
    owner = owner_dir.name
    admission = ledger(owner, expected_sha, run_id)
    check(read(owner_dir / LEDGER) == canonical(admission), "CAPSULE_ADMISSION_BINDING")
    files = {LEDGER: (canonical(admission), canonical(admission))}
    entries = {entry.name for entry in owner_dir.iterdir()}
    root_valid = entries <= OWNER_MEMBERS
    for name in entries & OWNER_MEMBERS:
        try:
            checked_path(owner_dir / name, directory=name in OWNER_DIRS)
        except READ_ERRORS:
            root_valid = False
    environment = None
    if root_valid and "environment.json" in entries:
        try:
            raw = read(owner_dir / "environment.json")
            environment = validate_environment(raw)
            files["environment.json"] = (raw, raw)
        except READ_ERRORS:
            root_valid = False
    try:
        formal_bound = strict(read(owner_dir / "formal.json")) == FORMAL
    except READ_ERRORS:
        formal_bound = False
    states = {}
    for case in CASES:
        allow_full = root_valid and formal_bound and (case == "NORMAL" or states["NORMAL"] == "VERIFIED")
        state, members = collect_case(owner_dir / case, case, environment, allow_full=allow_full)
        states[case] = state
        files.update({f"{case}/{name}": pair for name, pair in members.items()})
    manifest = {"capsule_schema": SCHEMA, "owner": owner, "source_git_sha": expected_sha,
                "source_sha256": source_sha(), "github_run_id": run_id, "cases": states, "files": {}}
    output = checked_path(output, directory=True, missing=True)
    output.mkdir()
    for case in CASES:
        if states[case] in ("VERIFIED", "FAILURE_DIAGNOSTIC"):
            (output / case).mkdir()
    for name, (original, published) in files.items():
        create(output / name, published)
        manifest["files"][name] = {"original_sha256": sha(original), "sha256": sha(published),
                                   "bytes": len(published), "nonce_projected": "/" in name
                                   and nonce_member(name.split("/")[1])}
    create(output / MANIFEST, canonical(manifest))
    return inspect(output, expected_sha, run_id)


def inspect(folder, expected_sha, run_id, expected_manifest_sha=None):
    folder = checked_path(folder, directory=True)
    raw_manifest = read(folder / MANIFEST, 32768)
    check(expected_manifest_sha is None or expected_manifest_sha == sha(raw_manifest), "CAPSULE_ANCHOR")
    manifest = exact(strict(raw_manifest), "capsule_schema", "owner", "source_git_sha", "source_sha256",
                     "github_run_id", "cases", "files")
    owner = manifest["owner"]
    admission = ledger(owner, expected_sha, run_id)
    check(manifest["capsule_schema"] == SCHEMA and manifest["source_git_sha"] == expected_sha
          and manifest["source_sha256"] == source_sha() and manifest["github_run_id"] == run_id,
          "CAPSULE_SOURCE")
    states = exact(manifest["cases"], *CASES)
    check(all(state in STATES for state in states.values())
          and (states["UNKNOWN"] != "VERIFIED" or states["NORMAL"] == "VERIFIED"), "CAPSULE_STATE")
    index = manifest["files"]
    check(type(index) is dict, "CAPSULE_INDEX")
    top = {LEDGER} | ({"environment.json"} if "environment.json" in index else set())
    expected = set(top)
    grouped = {}
    for case, state in states.items():
        if state in ("VERIFIED", "FAILURE_DIAGNOSTIC"):
            grouped[case] = {REPORT, *(member_names(case) if state == "VERIFIED" else [])}
            expected.update(f"{case}/{name}" for name in grouped[case])
    check(set(index) == expected, "CAPSULE_INDEX")
    check({p.name for p in folder.iterdir()} == {MANIFEST, *top, *grouped}, "CAPSULE_EXTRA")
    for case, names in grouped.items():
        check({p.name for p in checked_path(folder / case, directory=True).iterdir()} == names, "CAPSULE_EXTRA")
    payloads = {}
    for name in expected:
        item = exact(index[name], "original_sha256", "sha256", "bytes", "nonce_projected")
        digests(item, "original_sha256", "sha256")
        leaf = name.rsplit("/", 1)[-1]
        projected = "/" in name and nonce_member(leaf)
        raw = read(folder / name, member_limit(leaf))
        integer(item["bytes"], 0, member_limit(leaf))
        check(item["bytes"] == len(raw) and item["sha256"] == sha(raw)
              and item["nonce_projected"] is projected
              and (item["original_sha256"] != item["sha256"]) is projected, "CAPSULE_MEMBER_HASH")
        payloads[name] = raw
    check(payloads[LEDGER] == canonical(admission), "CAPSULE_ADMISSION_BINDING")
    environment = validate_environment(payloads["environment.json"]) if "environment.json" in top else None
    results = {}
    for case, names in grouped.items():
        diag = validate_public(payloads[f"{case}/{REPORT}"])
        check(diag["case"] == case and diag["source_sha256"] == source_sha(), "CAPSULE_DIAGNOSTIC")
        if states[case] == "VERIFIED":
            result = verify_members(owner, case, {name: payloads[f"{case}/{name}"] for name in names - {REPORT}})
            bind_result(result, environment, diag, case)
            results[case] = result
    return {"capsule_sha256": sha(raw_manifest), "cases": states, "oracle": results}


def run_admitted(owner, admission):
    from runtime.runproof_runtime.effectwitness.sdk_presend_probe import run

    check(read(owner / LEDGER) == canonical(admission), "CAPSULE_ADMISSION_BINDING")
    environment = validate_environment(read(owner / "environment.json"))
    check(Path(sys.prefix) == owner / "venv" and environment["python"] == sys.version.split()[0]
          and environment["exe_sha256"] == sha(Path(sys.executable).read_bytes()), "CAPSULE_VENV")

    def accept_case(folder, case):
        check(strict(read(owner / "formal.json")) == FORMAL, "CAPSULE_FORMAL_BINDING")
        status, _ = collect_case(folder, case, environment, allow_full=True)
        check(status == "VERIFIED", "CAPSULE_CASE_UNAVAILABLE")

    run(owner, accept_case=accept_case)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("admit", "environment", "physical", "export", "verify"))
    parser.add_argument("--owner", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        admission = ledger(args.owner, args.expected_sha, args.run_id)
        owner = ROOT / args.owner
        if args.mode == "verify":
            check(args.folder is not None, "CAPSULE_FOLDER")
            check(strict(read(args.folder / MANIFEST, 32768))["owner"] == args.owner, "CAPSULE_OWNER")
            result = inspect(args.folder, args.expected_sha, args.run_id, args.expected_manifest_sha256)
            print(json.dumps(result, sort_keys=True))
            return int(args.require_complete and not all(x == "VERIFIED" for x in result["cases"].values()))
        check(args.folder is None and args.expected_manifest_sha256 is None and not args.require_complete,
              "CAPSULE_OPTIONS")
        if args.mode == "admit":
            checked_path(ROOT, directory=True, missing=True).mkdir(exist_ok=True)
            checked_path(owner, directory=True, missing=True).mkdir()
            create(owner / LEDGER, canonical(admission))
        elif args.mode == "environment":
            check(read(owner / LEDGER) == canonical(admission), "CAPSULE_ADMISSION_BINDING")
            check(Path(sys.prefix) == owner / "venv", "CAPSULE_VENV")
            from importlib.metadata import distributions
            package_versions = {}
            for dist in distributions():
                name = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
                check(name not in package_versions, "CAPSULE_DUPLICATE_PACKAGE")
                package_versions[name] = dist.version
            raw = canonical({"python": sys.version.split()[0], "exe_sha256": sha(Path(sys.executable).read_bytes()),
                             "packages": package_versions})
            validate_environment(raw)
            create(owner / "environment.json", raw)
        elif args.mode == "physical":
            run_admitted(owner, admission)
        else:
            checked_path(CAPSULE_ROOT, directory=True, missing=True).mkdir(exist_ok=True)
            print(json.dumps(build(owner, CAPSULE_ROOT / args.owner, args.expected_sha, args.run_id), sort_keys=True))
        return 0
    except READ_ERRORS:
        print("CAPSULE_UNAVAILABLE", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
