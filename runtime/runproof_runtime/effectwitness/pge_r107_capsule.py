"""Export only the independently verified, bounded public projection."""
import argparse
from io import BytesIO
import re
from zipfile import BadZipFile, ZIP_STORED, ZipFile, ZipInfo

from . import pge_r106_contracts as inner, pge_r106_oracle as inner_oracle
from . import pge_r107_contracts as c, pge_r107_oracle as oracle
from .pge_r107_session import admission, owner_path
from .product_sdk_target import create, read, safe
from .sdk_presend_contracts import canonical, check, sha, strict

MAX_ZIP = 64 * 1024
MEMBERS = ("manifest.json", "public.json")
SENSITIVE = re.compile(rb'(?i)(bearer |sk-(?:proj-)?[A-Za-z0-9]{12,}|https?://|[A-Z]:\\|\.env\b|"(?:token|api_key|authorization|base64|headers|messages|prompt|stdout|site|path)")')


def projection(source, run, owner, hosted):
    folder = safe(owner_path(owner), directory=True)
    check(read(folder / "admission.json", c.MAX_HTTP) == canonical(admission(source, run, owner, hosted))
          and strict(read(folder / "physical-claim.json", 4096)) ==
          {"owner": owner, "run_id": run, "source_git_sha": source}, "PHYSICAL_CLAIM")
    cases = [oracle.verify_case(folder / policy, source, run, owner, policy, hosted) for policy in c.POLICIES]
    return {"schema": "rpf107-public-v1", "source_git_sha": source, "run_id": run, "owner": owner, "cases": cases,
            "issuer": "NOT_ESTABLISHED", "external_provider_requests": 0, "real_explorer": "NOT_RUN",
            "evidence_kind": "VERIFIED_LOCAL_SCRIPTED_SDK_PROJECTION"}


def validate(row, source, run, owner):
    inner.exact(row, "schema", "source_git_sha", "run_id", "owner", "cases", "issuer",
                "external_provider_requests", "real_explorer", "evidence_kind")
    check((row["source_git_sha"], row["run_id"], row["owner"]) == (source, run, owner)
          and inner.hex_id(source, 40) and inner.hex_id(owner, 32)
          and row["schema"] == "rpf107-public-v1" and row["issuer"] == "NOT_ESTABLISHED"
          and row["real_explorer"] == "NOT_RUN" and row["external_provider_requests"] == 0
          and row["evidence_kind"] == "VERIFIED_LOCAL_SCRIPTED_SDK_PROJECTION"
          and type(row["cases"]) is list and len(row["cases"]) == 2, "CAPSULE_SCOPE")
    owners, runs, calls = set(), set(), set()
    for case, policy in zip(row["cases"], c.POLICIES):
        inner.exact(case, "schema", "source_git_sha", "run_id", "owner", "policy", "model_source", "inner_scope",
                    "inner_policy", "candidate_id", "call_id", "bridge_sha256", "wal_sha256", "wal_revision",
                    "frozen_sha256", "source_identity", "feedback", "sdk", "wheel_sha256", "application",
                    "proposal_sha256", "decision_sha256", "oracle", "authority", "fault", "reconciliation",
                    "post_unknown_inbound_model_post", "post_unknown_model_reservations", "receiver",
                    "post_unknown_receiver_bytes", "post_unknown_business_writes", "model_reservations",
                    "business_transactions", "external_provider_requests", "provider_usage", "agent_outcome",
                    "platform_outcome", "issuer")
        check((case["source_git_sha"], case["run_id"], case["owner"], case["policy"]) ==
              (source, run, owner, policy) and case["schema"] == "rpf107-case-v1"
              and case["issuer"] == "NOT_ESTABLISHED" and case["model_source"] == c.SOURCE_KIND
              and case["candidate_id"] == c.POLICIES[policy], "CAPSULE_CASE")
        scope = inner.exact(case["inner_scope"], "origin", "source_git_sha", "owner", "run_id")
        check(scope["origin"] == "LOCAL" and scope["source_git_sha"] == source
              and scope["owner"] == c.inner_owner(source, run, owner, policy) and inner.hex_id(scope["run_id"], 32)
              and case["inner_policy"] == inner.POLICY and case["call_id"].startswith("call_")
              and inner.hex_id(case["call_id"][5:], 32), "CAPSULE_INNER")
        owners.add(scope["owner"])
        runs.add(scope["run_id"])
        calls.add(case["call_id"])
        check(case["model_reservations"] == 1 and case["business_transactions"] == 2
              and case["post_unknown_inbound_model_post"] == 1 and case["post_unknown_model_reservations"] == 0
              and case["post_unknown_receiver_bytes"] == case["post_unknown_business_writes"] == 0
              and case["receiver"] == "NOT_RUN"
              and case["external_provider_requests"] == 0 and case["provider_usage"] == "NOT_RUN"
              and case["agent_outcome"] == "NOT_RUN" and case["reconciliation"] == "COMMITTED"
              and case["authority"]["receipt_count"] == 1 and case["oracle"]["outcome"] == inner.SUCCESS
              and case["oracle"]["issuer"] == "NOT_ESTABLISHED"
              and case["oracle"]["receipt_sha256"] == case["authority"]["receipt_sha256"]
              and case["oracle"]["authority_after_sha256"] == case["authority"]["snapshot_sha256"], "CAPSULE_FACTS")
        verify_projection_fields(case)
    check(len(owners) == len(runs) == len(calls) == 2, "CAPSULE_DISTINCT")


def verify_projection_fields(case):
    def digests(row, names):
        check(all(inner.hex_id(row[name], 64) for name in names), "CAPSULE_DIGEST")

    digests(case, ("bridge_sha256", "wal_sha256", "frozen_sha256", "proposal_sha256", "decision_sha256"))
    source = inner.exact(case["source_identity"], *("pge_r107_" + part for part in c.PARTS), *c.DIRECT)
    digests(source, source)
    wheels = inner.exact(case["wheel_sha256"], *c.PINS)
    digests(wheels, wheels)
    feed = inner.exact(case["feedback"], "schema", "seed", "candidates", "remaining")
    seed = inner.exact(feed["seed"], "domain", "outcome", "feedback_sha256")
    digests(seed, ("feedback_sha256",))
    check(feed["schema"] == "rpf107-feedback-v1" and feed["candidates"] == list(c.CHOICES)
          and feed["remaining"] == inner.COST and seed["domain"] == "order" and seed["outcome"] == inner.SUCCESS,
          "CAPSULE_FEEDBACK")
    sdk = inner.exact(case["sdk"], "pid", "parent_pid", "stdout_sha256", "stdout_size", "packages", "terminal",
                      "exe_sha256", "duration_ns", "server_stopped")
    digests(sdk, ("stdout_sha256", "exe_sha256"))
    check(sdk["terminal"] == {"status": "DENIED_AFTER_UNKNOWN", "http_status": 409, "usage_kind": "UNAVAILABLE"}
          and sdk["server_stopped"] is True, "CAPSULE_SDK")
    for name, pkg in inner.exact(sdk["packages"], *c.PINS).items():
        inner.exact(pkg, "version", "source_sha256", "record_sha256")
        check(pkg["version"] == c.PINS[name], "CAPSULE_PACKAGE")
        digests(pkg, ("source_sha256", "record_sha256"))
    check([row["kind"] for row in case["application"]] ==
          ["RECEIVED", "SCRIPT_RESPONSE", "RECEIVED", "TOOL_RESULT", "RECEIVED", "DENIED"], "CAPSULE_APPLICATION")
    for item in case["application"]:
        inner.exact(item, "kind", "size", "sha256")
        check(type(item["size"]) is int and 0 < item["size"] <= c.MAX_HTTP, "CAPSULE_APPLICATION_SIZE")
        digests(item, ("sha256",))
    outcome = inner.exact(case["oracle"], "schema", "binding", "outcome", "fault", "intent_sha256",
                          "authority_before_sha256", "authority_after_sha256", "receipt_sha256", "agent_outcome",
                          "platform_outcome", "verification", "issuer")
    digests(outcome, ("intent_sha256", "authority_before_sha256", "authority_after_sha256", "receipt_sha256"))
    binding = inner.exact(outcome["binding"], "origin", "source_git_sha", "run_id", "owner", "domain", "db_member",
                          "environment_id", "operation_id", "policy", "candidate_id", "contract_sha256")
    digests(binding, ("operation_id", "contract_sha256"))
    order = case["candidate_id"] == inner.ORDER
    check(binding["candidate_id"] == case["candidate_id"]
          and all(binding[key] == value for key, value in case["inner_scope"].items())
          and binding["environment_id"] == "env-" + binding["operation_id"]
          and binding["policy"] == inner.POLICY and binding["domain"] == ("order" if order else "ops")
          and binding["db_member"] == ("fault-order.sqlite" if order else "fault-ops.sqlite"), "CAPSULE_BINDING")
    authority = inner.exact(case["authority"], "mode", "effect", "receipt_count", "receipt_sha256", "snapshot_sha256")
    expected = ({"revision": 1, "status": "REFUNDED", "refunded_minor": 2500} if order
                else {"revision": 1, "release": "release-v2", "effect_count": 1})
    check(authority["mode"] == "SQLITE_RO_QUERY_ONLY" and canonical(authority["effect"]) == canonical(expected),
          "CAPSULE_EFFECT")
    check(case["fault"] == {"planned": True, "triggered": True, "observed": True, "agent_exposed": True,
          "exposure_kind": "SDK_SCRIPTED_TOOL_RETURN"} and outcome["fault"] ==
          {"planned": True, "triggered": True, "observed": True, "agent_exposed": False}, "CAPSULE_FAULT")


def build(row, source, run, owner):
    validate(row, source, run, owner)
    raw = canonical(row)
    check(len(raw) < MAX_ZIP // 2 and not SENSITIVE.search(raw), "PUBLIC_REDACTION")
    manifest = canonical({"schema": "rpf107-manifest-v1", "public_sha256": sha(raw), "public_size": len(raw)})
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_STORED) as archive:
        for name, data in zip(MEMBERS, (manifest, raw)):
            archive.writestr(ZipInfo(name), data)
    return buffer.getvalue()


def verify(raw, expected_sha, source, run, owner):
    check(inner.hex_id(expected_sha, 64) and len(raw) <= MAX_ZIP and sha(raw) == expected_sha, "CAPSULE_ANCHOR")
    with ZipFile(BytesIO(raw)) as archive:
        infos = archive.infolist()
        check(tuple(info.filename for info in infos) == MEMBERS and
              all(info.compress_type == ZIP_STORED and info.file_size < MAX_ZIP // 2 for info in infos),
              "CAPSULE_MEMBERS")
        manifest, public = (archive.read(info) for info in infos)
    row = strict(public)
    validate(row, source, run, owner)
    check(build(row, source, run, owner) == raw and strict(manifest)["public_sha256"] == sha(public), "CAPSULE_BYTES")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("run")
    parser.add_argument("owner")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    try:
        row = projection(args.source, args.run, args.owner, not args.local)
        raw = build(row, args.source, args.run, args.owner)
        verify(raw, sha(raw), args.source, args.run, args.owner)
        create(owner_path(args.owner) / "public.zip", raw)
    except (*inner_oracle.READ_FAILURES, BadZipFile):
        print('{"status":"REJECTED","stage":"CAPSULE"}')
        return 3
    print(canonical({"status": "PASS", "sha256": sha(raw), "size": len(raw)}).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
