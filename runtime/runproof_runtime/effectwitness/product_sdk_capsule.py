"""Publish and recheck bounded public projections, never private case files."""
import argparse
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .product_sdk_contracts import freeze, sources
from .product_sdk_oracle import exact, load_physical, verify_case
from .product_sdk_probe import admission, owner_scope
from .product_sdk_target import create, read, safe
from .sdk_presend_contracts import CASES, canonical, check, sha, strict
from .sdk_presend_diagnostic import validate_sdk_error

SCHEMA = "rpf104-public-capsule-v1"
LIMIT = 327680
PRIVATE = re.compile(
    rb'(?i)(?:\bBearer\s+|\bsk-[a-z0-9_-]{12,}|\bgh[pousr]_[a-z0-9]{16,}|'
    rb'\bgithub_pat_[a-z0-9_]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|'
    rb'"(?:authorization|api_key|password|token|cookie|private_key)"\s*:|'
    rb'(?<![a-z0-9_])[a-z]:[\\/]|"(?:/(?:home|Users|root|tmp|opt|run|var|etc)/|\\\\))'
)


def safe_public(raw):
    check(0 < len(raw) <= 131072 and not PRIVATE.search(raw), "PUBLIC_SCOPE")
    row = strict(raw)
    check(canonical(row) == raw, "PUBLIC_CANONICAL")
    return row


def diagnostic(folder):
    row = {"state": "UNAVAILABLE", "contract_present": False, "sdk_error": None,
           "sdk_exit": None, "sdk_posts": None, "business_writes": None, "receiver_bytes": None}
    try:
        safe(folder, directory=True)
    except FileNotFoundError:
        return {**row, "state": "NOT_RUN"}
    try:
        row["contract_present"] = bool(read(folder / "contract.json", 16384))
        output = read(folder / "sdk-output.json", 8192)
        done = exact(strict(read(folder / "sdk-exit.json", 8192)), "pid", "exit", "exit_ns", "stdout_sha256")
        launch = exact(strict(read(folder / "sdk-launch.json", 8192)), "pid", "start_ns", "host", "exe_sha256")
        check(done["stdout_sha256"] == sha(output) and type(done["pid"]) is int and done["pid"] > 0
              and done["pid"] == launch["pid"] and type(done["exit"]) is int and -255 <= done["exit"] <= 255,
              "DIAGNOSTIC_EXIT_BINDING")
        row["sdk_exit"] = done["exit"]
        raw = strict(output)
        if done["exit"] != 0 and raw.get("status") == "SDK_ERROR":
            row["sdk_error"] = validate_sdk_error(raw)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        pass
    return row


def validate_diagnostic(row, case_states):
    exact(row, *[case for case in CASES if case_states[case] != "VERIFIED"])
    for case, value in row.items():
        exact(value, "state", "contract_present", "sdk_error", "sdk_exit", "sdk_posts", "business_writes", "receiver_bytes")
        check(value["state"] == case_states[case] and value["state"] in ("NOT_RUN", "UNAVAILABLE")
              and type(value["contract_present"]) is bool
              and all(value[k] is None for k in ("sdk_posts", "business_writes", "receiver_bytes")),
              "DIAGNOSTIC_STATE")
        check(value["sdk_exit"] is None or (type(value["sdk_exit"]) is int and -255 <= value["sdk_exit"] <= 255
              and value["state"] == "UNAVAILABLE" and value["contract_present"]), "DIAGNOSTIC_EXIT")
        if value["sdk_error"] is not None:
            validate_sdk_error(value["sdk_error"])
            check(value["sdk_exit"] not in (None, 0), "DIAGNOSTIC_BINDING")


def build(folder, source, run, owner):
    expected = admission(source, run, owner)
    check(read(folder / "admission.json", 16384) == canonical(expected), "ADMISSION_BINDING")
    files, states, diagnostics = {}, {}, {}
    for case in CASES:
        location = folder / case
        try:
            value = load_physical(location)
            check(value["frozen"] == freeze(source, run, owner, case)
                  and canonical(value) == read(location / "oracle-public.json", 131072), "ORACLE_RECEIPT")
            states[case] = "VERIFIED"
            files[f"{case}.json"] = canonical(value)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
            diagnostics[case] = diagnostic(location)
            states[case] = diagnostics[case]["state"]
    if diagnostics:
        files["diagnostic.json"] = canonical(diagnostics)
    manifest = {"schema": SCHEMA, "admission": expected, "states": states,
                "members": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in files.items()},
                "issuer": "NOT_ESTABLISHED", "provider_kind": "SCRIPTED_LOCAL", "real_explorer": "NOT_RUN",
                "external_provider_requests": 0}
    files["manifest.json"] = canonical(manifest)
    raw = pack(files)
    verify_zip(raw, source, run, owner)
    return raw


def pack(files):
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        for name, raw in sorted(files.items()):
            safe_public(raw)
            item = ZipInfo(name)
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, raw, compress_type=ZIP_DEFLATED)
    return stream.getvalue()


def verify_zip(raw, source, run, owner, *, manifest_sha=None, zip_sha=None, require_complete=False):
    check(0 < len(raw) <= LIMIT and (zip_sha is None or zip_sha == sha(raw)), "ZIP_BOUND")
    with ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = {item.filename for item in entries}
        check(len(entries) == len(names) and 2 <= len(names) <= 4 and not archive.comment
              and names <= {"manifest.json", "NORMAL.json", "UNKNOWN.json", "diagnostic.json"}
              and "manifest.json" in names, "ZIP_MEMBERS")
        files = {}
        for item in entries:
            check(item.create_system == 3 and item.external_attr >> 16 == 0o100644
                  and item.compress_type == ZIP_DEFLATED and item.flag_bits == 0
                  and not item.extra and not item.comment and 0 < item.file_size <= 131072, "ZIP_ENTRY")
            with archive.open(item) as stream:
                files[item.filename] = stream.read(item.file_size + 1)
            check(len(files[item.filename]) == item.file_size, "ZIP_SIZE")
    check(manifest_sha is None or sha(files["manifest.json"]) == manifest_sha, "MANIFEST_ANCHOR")
    manifest = exact(safe_public(files.pop("manifest.json")), "schema", "admission", "states", "members",
                     "issuer", "provider_kind", "real_explorer", "external_provider_requests")
    check(manifest["schema"] == SCHEMA and canonical(manifest["admission"]) == canonical(admission(source, run, owner))
          and manifest["admission"]["sources"] == sources() and manifest["issuer"] == "NOT_ESTABLISHED"
          and manifest["provider_kind"] == "SCRIPTED_LOCAL" and manifest["real_explorer"] == "NOT_RUN"
          and type(manifest["external_provider_requests"]) is int and manifest["external_provider_requests"] == 0,
          "MANIFEST_IDENTITY")
    states = exact(manifest["states"], *CASES)
    check(all(states[case] in ("NOT_RUN", "UNAVAILABLE", "VERIFIED") for case in CASES)
          and (states["UNKNOWN"] != "VERIFIED" or states["NORMAL"] == "VERIFIED"), "MANIFEST_STATES")
    expected = {f"{case}.json" for case in CASES if states[case] == "VERIFIED"}
    complete = len(expected) == 2
    if not complete:
        expected.add("diagnostic.json")
    check(set(files) == set(manifest["members"]) == expected and (not require_complete or complete), "CAPSULE_COMPLETE")
    reports = {}
    for name, payload in files.items():
        item = exact(manifest["members"][name], "sha256", "bytes")
        check(type(item["bytes"]) is int and item["bytes"] == len(payload) and item["sha256"] == sha(payload),
              "MEMBER_BINDING")
        row = safe_public(payload)
        if name == "diagnostic.json":
            validate_diagnostic(row, states)
        else:
            case = name.removesuffix(".json")
            check(row["frozen"] == freeze(source, run, owner, case), "CASE_BINDING")
            reports[case] = verify_case(row)
    return {"status": "VERIFIED" if complete else "DIAGNOSTIC", "zip_sha256": sha(raw),
            "manifest_sha256": sha(canonical(manifest)), "states": states, "cases": reports,
            "anchor": "EXTERNAL_DIGEST_CHECKED" if manifest_sha or zip_sha else "CONTENT_CHECKED",
            "issuer": "NOT_ESTABLISHED"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("export", "verify"))
    parser.add_argument("source")
    parser.add_argument("run")
    parser.add_argument("owner")
    parser.add_argument("--zip", type=Path)
    parser.add_argument("--zip-sha")
    parser.add_argument("--manifest-sha")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "export":
            check(args.zip is None and args.zip_sha is None and args.manifest_sha is None
                  and not args.require_complete, "EXPORT_OPTIONS")
            folder = safe(owner_scope(args.owner), directory=True)
            raw = build(folder, args.source, args.run, args.owner)
            create(folder / "public.zip", raw)
        else:
            check(args.zip is not None, "ZIP_PATH")
            raw = read(args.zip, LIMIT)
        result = verify_zip(raw, args.source, args.run, args.owner, manifest_sha=args.manifest_sha,
                            zip_sha=args.zip_sha, require_complete=args.require_complete)
        print(canonical(result).decode())
    except Exception:
        print("RPF104_CAPSULE_REJECTED")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
