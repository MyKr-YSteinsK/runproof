"""Read-only verification of the pinned public RPF-102 Actions artifact."""
import argparse
import io
import json
import re
import stat
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from ci import rpf102_rev3_capsule as capsule
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import CASES, canonical, check, sha, strict
from runtime.runproof_runtime.effectwitness.sdk_presend_diagnostic import REPORT, source_sha, validate_public
from runtime.runproof_runtime.effectwitness.sdk_presend_oracle import member_names, replay

RUN_ID = 42631302508
ARTIFACT_ID = 13681255432
SOURCE = "cb181bcced89384cc1f2f9a3e7ec43d0456af34b"
OWNER = "0c4a3cd80f534a0eb72fa2d430d1a6ee"
ZIP_SHA = "a730b4dd390704ea9503e6de3d7842b6352a5b48b37c41f3acbe389a2633fd19"
MANIFEST_SHA = "a88c0c61e4a5cf85207338030d42a949351796e7876e3a1857b57b538b8dae9b"
ARCHIVE = Path("spikes/rpf-103/evidence/rpf102-run-42631302508-public.zip")
ZIP_SIZE = 17235
INDEX = {capsule.LEDGER, "environment.json"} | {
    f"{case}/{name}" for case in CASES for name in (*member_names(case), REPORT)
}
MEMBERS = INDEX | {capsule.MANIFEST}
PRIVATE_PATTERN = re.compile(
    r"(?i)\b(?:sk-[a-z0-9_-]{12,}|gh[pousr]_[a-z0-9]{16,}|github_pat_[a-z0-9_]{16,}|"
    r"bearer\s+\S+|AKIA[A-Z0-9]{16})|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?<![a-z0-9_])[a-z]:[\\/]|\\\\[a-z0-9]|(?:^|[\s\"'])/(?:home|Users|root|tmp|run|opt|etc|var)/"
)
PRIVATE_KEYS = {"authorization", "proxy-authorization", "cookie", "set-cookie", "password",
                "api_key", "apikey", "secret", "access_token", "refresh_token", "token"}


def scan(value):
    if isinstance(value, dict):
        check(not any(key.casefold() in PRIVATE_KEYS for key in value), "PRIVATE_FIELD")
        for key, item in value.items():
            scan(key)
            scan(item)
    elif isinstance(value, list):
        for item in value:
            scan(item)
    elif isinstance(value, str):
        check(not PRIVATE_PATTERN.search(value), "PRIVATE_LITERAL")


def unpack(raw):
    check(len(raw) <= 65536, "ZIP_SIZE")
    with ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        check(len(entries) == len(MEMBERS) and {e.filename for e in entries} == MEMBERS
              and not archive.comment, "ZIP_MEMBERS")
        payloads = {}
        for entry in entries:
            leaf = entry.filename.rsplit("/", 1)[-1]
            limit = 32768 if leaf == capsule.MANIFEST else capsule.member_limit(leaf)
            check(entry.create_system == 3 and stat.S_ISREG(entry.external_attr >> 16)
                  and entry.compress_type == ZIP_DEFLATED and entry.flag_bits == 8
                  and not entry.extra and not entry.comment and 0 < entry.file_size <= limit, "ZIP_ENTRY")
            with archive.open(entry) as stream:
                payloads[entry.filename] = stream.read(limit + 1)
            check(len(payloads[entry.filename]) == entry.file_size, "ZIP_MEMBER_SIZE")
        return payloads


def verify_members(payloads, *, manifest_anchor=MANIFEST_SHA):
    """Verify a complete public projection. A supplied anchor is for in-memory controls."""
    check(set(payloads) == MEMBERS, "CAPSULE_EXTRA")
    raw_manifest = payloads[capsule.MANIFEST]
    check(sha(raw_manifest) == manifest_anchor, "CAPSULE_ANCHOR")
    manifest = capsule.exact(strict(raw_manifest), "capsule_schema", "owner", "source_git_sha",
                             "source_sha256", "github_run_id", "cases", "files")
    check(manifest["capsule_schema"] == capsule.SCHEMA and manifest["owner"] == OWNER
          and manifest["source_git_sha"] == SOURCE and manifest["source_sha256"] == source_sha()
          and type(manifest["github_run_id"]) is int and manifest["github_run_id"] == RUN_ID
          and manifest["cases"] == dict.fromkeys(CASES, "VERIFIED"), "CAPSULE_IDENTITY")
    index = manifest["files"]
    check(type(index) is dict and len(index) == 32 and set(index) == INDEX, "CAPSULE_INDEX")
    projected = 0
    for name, item in index.items():
        capsule.exact(item, "original_sha256", "sha256", "bytes", "nonce_projected")
        capsule.digests(item, "original_sha256", "sha256")
        leaf = name.rsplit("/", 1)[-1]
        projection = "/" in name and capsule.nonce_member(leaf)
        raw = payloads[name]
        capsule.integer(item["bytes"], 1, capsule.member_limit(leaf))
        check(item["bytes"] == len(raw) and item["sha256"] == sha(raw)
              and item["nonce_projected"] is projection
              and (item["original_sha256"] != item["sha256"]) is projection, "CAPSULE_MEMBER_HASH")
        projected += projection
        for line in raw.splitlines() if leaf == "wal.jsonl" else (raw,):
            scan(strict(line))
    scan(manifest)
    check(payloads[capsule.LEDGER] == canonical(capsule.ledger(OWNER, SOURCE, RUN_ID)), "CAPSULE_LEDGER")
    environment = capsule.validate_environment(payloads["environment.json"])
    results = {}
    for case, expected in (("NORMAL", (2, 1092)), ("UNKNOWN", (1, 421))):
        members = {name: payloads[f"{case}/{name}"] for name in member_names(case)}
        result = capsule.verify_members(OWNER, case, members)
        diag = validate_public(payloads[f"{case}/{REPORT}"])
        check(diag["case"] == case and diag["source_sha256"] == manifest["source_sha256"], "CAPSULE_DIAGNOSTIC")
        capsule.bind_result(result, environment, diag, case)
        rows = replay(members["wal.jsonl"])
        kinds = [row["kind"] for row in rows]
        sends, size = expected
        check(kinds.count("SDK_POST_RECEIVED") == 2 and result["tool_callbacks"] == 1
              and all(kinds.count(kind) == sends for kind in ("PROVIDER_RESERVE", "SEND_BEGIN", "SEND_ENTRY"))
              and result["received_bytes"] == size and diag["receiver_receipt_count"] == sends,
              "OBSERVED_TOTALS")
        unknown = kinds.index("UNKNOWN_OBSERVED") if "UNKNOWN_OBSERVED" in kinds else None
        after = kinds[unknown + 1:] if unknown is not None else []
        check((case == "NORMAL" and unknown is None)
              or (case == "UNKNOWN" and unknown == 8 and after ==
                  ["TOOL_RETURN_TO_SDK", "SDK_POST_RECEIVED", "DENY", "SDK_TERMINAL"]), "UNKNOWN_SEQUENCE")
        results[case] = {**result, "receiver_receipts": sends, "send_begins": kinds.count("SEND_BEGIN"),
                         "wal_events": len(rows), "wal_tip_sha256": rows[-1]["sha256"], "unknown_seq": unknown}
    return {"run_id": RUN_ID, "artifact_id": ARTIFACT_ID, "owner": OWNER, "source_git_sha": SOURCE,
            "manifest_sha256": sha(raw_manifest), "indexed_members": len(index), "zip_members": len(payloads),
            "nonce_projected_members": projected, "cases": results}


def verify_archive(path):
    raw = capsule.read(path, 65536)
    check(len(raw) == ZIP_SIZE and sha(raw) == ZIP_SHA, "ZIP_ANCHOR")
    return {**verify_members(unpack(raw)), "zip_sha256": sha(raw), "zip_bytes": len(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, nargs="?", default=ARCHIVE)
    args = parser.parse_args()
    try:
        result = verify_archive(args.zip)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, BadZipFile):
        print('{"status":"REJECTED"}')
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
