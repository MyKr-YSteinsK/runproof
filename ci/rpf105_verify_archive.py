"""Verify the exact RPF-104 Actions ZIP and its public capsule without extraction."""
import argparse
from io import BytesIO
import json
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile
from zlib import error as CompressionError

from ci.rpf103_verify_archive import scan
from runtime.runproof_runtime.effectwitness import product_sdk_capsule as capsule
from runtime.runproof_runtime.effectwitness.product_sdk_oracle import replay
from runtime.runproof_runtime.effectwitness.product_sdk_target import read
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, check, sha

SOURCE = "4f52e9595d55f1ea6a683f7ad7f1f814db452d04"
RUN = "42647430199"
OWNER = "7529d60e439b4ff3abb332b41022d387"
ARTIFACT = 13687917824
OUTER_SHA = "c917ce175f1fb56c4ee768ab1aee184e2d710cdba65fa0390d10d79807bd67b3"
INNER_SHA = "763d9d5faec3a2fbee5322df80c8e2256d4edeba4ba9b0a1345d6146313e960b"
MANIFEST_SHA = "8288f4b301ca3feefbe7472be93133b074de7320975c2db7060d3b2fd8356052"
ARCHIVE = Path("spikes/rpf-105/evidence/rpf104-run-42647430199-actions.zip")
INDEX = {
    "NORMAL.json": (27606, "c34c8e8b90ee57ed25d8473649df038868b0e01a424671060d3d78fed4e6298a"),
    "UNKNOWN.json": (17670, "af1120f2174faba2670a2bd68acf4e2b48213259f345caed3889c7fec85942c3"),
    "manifest.json": (2217, MANIFEST_SHA),
}
AFTER_UNKNOWN = {"PROVIDER_RESERVE", "SEND_BEGIN", "SEND_ENTRY", "WRITE_INTENT", "WRITE_COMMIT"}


def outer_payload(raw):
    check(0 < len(raw) <= 16384, "ACTIONS_SIZE")
    with ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        check(not archive.comment and len(entries) == 1 and entries[0].filename == "public.zip",
              "ACTIONS_MEMBERS")
        item = entries[0]
        check(item.create_system == 3 and item.external_attr >> 16 == 0o100644
              and item.compress_type == ZIP_DEFLATED and item.flag_bits == 8
              and not item.extra and not item.comment and item.file_size == 11050, "ACTIONS_ENTRY")
        with archive.open(item) as stream:
            payload = stream.read(11051)
        check(len(payload) == 11050, "ACTIONS_PAYLOAD_SIZE")
        return payload


def verify_bytes(raw):
    check(len(raw) == 11072 and sha(raw) == OUTER_SHA, "ACTIONS_ANCHOR")
    inner = outer_payload(raw)
    verified = capsule.verify_zip(inner, SOURCE, RUN, OWNER, manifest_sha=MANIFEST_SHA,
                                  zip_sha=INNER_SHA, require_complete=True)
    checks = {}
    with ZipFile(BytesIO(inner)) as archive:
        check(len(archive.infolist()) == len(INDEX) and set(archive.namelist()) == set(INDEX), "INNER_MEMBERS")
        for name, (size, digest) in INDEX.items():
            with archive.open(name) as stream:
                payload = stream.read(size + 1)
            check(len(payload) == size and sha(payload) == digest, "INNER_MEMBER_ANCHOR")
            value = capsule.safe_public(payload)
            scan(value)
            if name == "manifest.json":
                continue
            case = name.removesuffix(".json")
            rows = replay(b"".join(canonical(row) + b"\n" for row in value["wal"]))
            kinds = [row["kind"] for row in rows]
            result = verified["cases"][case]
            wanted = (36, 3, 2, 2, 3, 2854) if case == "NORMAL" else (28, 2, 1, 1, 1, 582)
            check((len(rows), result["sdk_posts"], result["tool_callbacks"], result["business_writes"],
                   result["forwards"], result["receiver_bytes"]) == wanted
                  and result["verification"] == "PUBLIC_PROJECTION_CHECKED", "OBSERVED_TOTALS")
            after = None
            if case == "UNKNOWN":
                index = kinds.index("UNKNOWN_OBSERVED")
                tail = kinds[index + 1:]
                after = dict.fromkeys(sorted(AFTER_UNKNOWN), 0)
                for kind in tail:
                    if kind in after:
                        after[kind] += 1
                check(index == 12 and not any(after.values())
                      and "READ_ONLY_RECONCILIATION" in tail and "DENY" in tail, "UNKNOWN_STOP")
            else:
                policy = kinds.index("POLICY_DECISION")
                check(kinds.index("VERIFIED_FEEDBACK") < policy
                      and kinds.index("TOOL_ACCEPTED", policy) > policy, "FEEDBACK_ORDER")
            checks[case] = {"wal_rows": len(rows), "wal_tip_sha256": rows[-1]["sha256"],
                            "post_unknown": after, **{key: result[key] for key in (
                                "sdk_posts", "tool_callbacks", "business_writes", "forwards",
                                "receiver_bytes", "verification")}}
    return {"run_id": RUN, "artifact_id": ARTIFACT, "source_git_sha": SOURCE, "owner": OWNER,
            "outer_bytes": len(raw), "outer_sha256": sha(raw), "inner_bytes": len(inner),
            "inner_sha256": sha(inner), "manifest_sha256": verified["manifest_sha256"],
            "cases": checks, "issuer": "NOT_ESTABLISHED", "provider_kind": "SCRIPTED_LOCAL",
            "real_explorer": "NOT_RUN", "external_provider_requests": 0}


def verify_archive(path=ARCHIVE):
    return verify_bytes(read(path, 16384))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, nargs="?", default=ARCHIVE)
    try:
        print(json.dumps(verify_archive(parser.parse_args().zip), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, BadZipFile, CompressionError):
        print('{"status":"REJECTED"}')
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
