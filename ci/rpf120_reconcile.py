"""Read archived coverage reports and reconcile their existing required-method dispositions."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from runtime.runproof_runtime.effectwitness.product_local_contracts import strict

SCHEMAS = {
    "handoff": "rpf85-coverage-handoff-v1",
    "rpf87": "rpf87-required-coverage-reconciliation-v1",
    "rpf89": "rpf89-required-coverage-v2",
    "rpf90": "rpf90-router-failure-observation-v1",
}
HOSTED_KINDS = {
    "handoff": "ROUTER_PROCESS_RECEIPTS",
    "rpf87": "HOSTED_SAME_RUN_PROCESS_RECEIPTS",
    "rpf89": "HOSTED_SAME_RUN_POSTCHECK_AND_PRIVATE_RECEIPTS",
    "rpf90": "HOSTED_SAME_RUN",
}
ROUTES = ("DEDICATED_RUNNER", "FROZEN_PRIVATE_ARTIFACT", "LEGACY_OWNER_ROOT",
          "LEGACY_SDK_PRECONDITION", "PORTABLE", "WINDOWS_NATIVE")
STATES = ("PASS", "SKIP", "UNAVAILABLE")
ORIGINAL = "ORIGINAL_ROUTER"
RPF86 = "RPF86_DEDICATED"
RPF88 = "RPF88_R72_DEDICATED"
METHOD = re.compile(r"test_[a-zA-Z_0-9]+(?:\.[a-zA-Z_][a-zA-Z_0-9]*){2,}")
HEX = re.compile(r"[a-f0-9]{64}")
MAX_JSON = 8 * 1024 * 1024


class Invalid(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise Invalid(code)


def read_input(path, role):
    try:
        need(path.is_file(), f"{role}:INPUT_FILE")
        with path.open("rb") as handle:
            return handle.read(MAX_JSON + 1)
    except OSError as exc:
        raise Invalid(f"{role}:INPUT_READ") from exc


def decode(raw, role):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_JSON, f"{role}:INPUT_SIZE")
    try:
        value = strict(raw)
    except (ValueError, RecursionError) as exc:
        raise Invalid(f"{role}:INVALID_JSON") from exc
    need(type(value) is dict and value.get("schema") == SCHEMAS[role], f"{role}:SCHEMA")
    return value


def identity(report, role, synthetic):
    run, attempt, commit = report["run_id"], report["run_attempt" if role == "rpf89" else "attempt"], report["commit"]
    need(all(type(x) is str and re.fullmatch(r"[1-9][0-9]*", x) for x in (run, attempt))
         and type(commit) is str and re.fullmatch(r"[a-f0-9]{40}", commit), f"{role}:INVALID_IDENTITY")
    kind = ("SYNTHETIC_OFFLINE_TEST" if role == "handoff" else "LOCAL_SYNTHETIC_CONTROL_ONLY") if synthetic else HOSTED_KINDS[role]
    need(report["evidence_kind"] == kind, f"{role}:EVIDENCE_KIND")
    need(all(report[key] is False for key in ("release_eligible", "release_executed", "deployment_authorized")),
         f"{role}:AUTHORITY_FIELDS")
    return {"run_id": run, "attempt": attempt, "commit": commit}


def count_is(value, expected):
    return type(value) is int and value == expected


def counts_are(value, expected):
    return type(value) is dict and all(type(n) is int for n in value.values()) and value == dict(expected)


def routes_are(value, expected):
    return (type(value) is dict and value.keys() == expected.keys()
            and all(counts_are(value[route], counts) for route, counts in expected.items()))


def index_methods(block, total, stage):
    required = block["required"]
    rows = block["methods"]
    need(count_is(required, total) and type(rows) is list, f"{stage}:REQUIRED_COUNT")
    fields = {"id", "route", "required", "original_actual", "effective_actual", "source_lane"}
    result = {}
    for row in rows:
        need(type(row) is dict and set(row) == fields, f"{stage}:METHOD_FIELDS")
        key, route, original = row["id"], row["route"], row["original_actual"]
        need(type(key) is str and METHOD.fullmatch(key) is not None, f"{stage}:METHOD_ID")
        need(key not in result, f"{stage}:DUPLICATE_METHOD")
        need(row["required"] is True and route in ROUTES and original in STATES
             and (route == "PORTABLE") == (original in ("PASS", "SKIP"))
             and row["effective_actual"] in STATES, f"{stage}:METHOD_DISPOSITION")
        result[key] = row
    need(len(result) == total, f"{stage}:METHOD_COUNT")
    return result


def admitted_ids(report, stage):
    earlier = stage == "rpf87"
    block = report["admitted_dedicated" if earlier else "new_admitted"]
    need(type(block) is list, f"{stage}:ADMISSION_FIELDS")
    reason = report["not_admitted"]
    need((bool(block) and reason is None) or (not block and type(reason) is str and bool(reason)),
         f"{stage}:ADMISSION_STATUS")
    module_prefix = "test_effectwitness_pge_dual.DualTests." if earlier else "test_effectwitness_pge_r72."
    lane = RPF86 if earlier else RPF88
    anchors = report["evidence_anchors"]
    proof_fields = {"native_receipt_sha256": "native_receipt", "journal_sha256": "native_journal"}
    if earlier:
        proof_fields.update(independent_receipt_sha256="independent_receipt", manifest_sha256="physical_manifest")
    else:
        proof_fields.update(verification_receipt_sha256="verify_receipt", checkpoint_sha256="checkpoint")
    found = set()
    for row in block:
        need(type(row) is dict, f"{stage}:ADMISSION_FIELDS")
        key = row["router_id"]
        need(type(key) is str and METHOD.fullmatch(key) and key.startswith(module_prefix)
             and row["full_id"] == "runtime.tests." + key and row["source_lane"] == lane
             and (not earlier or row["actual"] == "PASS"), f"{stage}:ADMISSION_IDENTITY")
        need(key not in found, f"{stage}:DUPLICATE_ADMISSION")
        need(all(type(row[field]) is str and HEX.fullmatch(row[field]) and row[field] == anchors[anchor]
                 for field, anchor in proof_fields.items()), f"{stage}:ADMISSION_ANCHOR")
        found.add(key)
    return found


def reconcile(inputs, *, synthetic=False):
    reports = {role: decode(raw, role) for role, raw in inputs.items()}
    digests = {role: sha256(raw).hexdigest() for role, raw in inputs.items()}
    handoff, old, new = (reports[role] for role in ("handoff", "rpf87", "rpf89"))
    binding = identity(handoff, "handoff", synthetic)
    for role, report in reports.items():
        if role != "handoff":
            need(identity(report, role, synthetic) == binding, f"{role}:MIXED_RUN")

    previous = old["original_router"]
    anchors = old["evidence_anchors"]
    need(previous["ledger_sha256"] == anchors["router_ledger"] == handoff["router_ledger_sha256"]
         and previous["status_sha256"] == anchors["handoff_status"] == digests["handoff"]
         and previous["evidence_manifest_sha256"] == handoff["evidence_manifest_sha256"], "rpf87:HANDOFF_ANCHOR")
    need(new["evidence_anchors"]["r87"] == digests["rpf87"], "rpf89:UPSTREAM_ANCHOR")
    need(new["github_job"] == "canonical-release-gate", "rpf89:JOB_IDENTITY")
    need(new["old_admitted"] == old["admitted_dedicated"], "rpf89:OLD_ADMISSIONS")

    source = handoff["source_validation"]
    bound_hashes = (handoff["router_ledger_sha256"], handoff["evidence_manifest_sha256"], source["matrix_lf_sha256"])
    need(all(type(value) is str and HEX.fullmatch(value) for value in bound_hashes), "handoff:SOURCE_HASHES")
    total = source["required_methods"]
    need(type(total) is int and total > 0, "handoff:REQUIRED_COUNT")
    a = index_methods(old["effective_required"], total, "rpf87")
    b = index_methods(new["effective_required"], total, "rpf89")
    need(a.keys() == b.keys(), "METHOD_SET_MISMATCH")
    need(count_is(source["modules"], len({key.split(".")[0] for key in a})), "handoff:MODULE_COUNT")
    first, second = admitted_ids(old, "rpf87"), admitted_ids(new, "rpf89")
    need(not first & second and (first | second) <= a.keys(), "ADMISSION_METHOD_SET")

    methods = []
    original_counts, phase87, phase89 = (Counter(), Counter(), Counter())
    router_routes = {route: Counter() for route in ROUTES}
    residual_routes, residual_modules = Counter(), Counter()
    remaining = []
    for method_id in sorted(a):
        row, later = a[method_id], b[method_id]
        route = row["route"]
        original = row["original_actual"]
        need((route, original) == (later["route"], later["original_actual"]), "ORIGINAL_METHOD_MISMATCH")
        in_first, in_second = method_id in first, method_id in second
        if in_first or in_second:
            need(route == "DEDICATED_RUNNER" and original == "UNAVAILABLE", "ADMISSION_ORIGINAL_DISPOSITION")
        after87 = "PASS" if in_first else original
        after89 = "PASS" if in_second else after87
        lane87 = RPF86 if in_first else ORIGINAL
        lane89 = RPF88 if in_second else lane87
        need((row["effective_actual"], row["source_lane"]) == (after87, lane87), "rpf87:ADMISSION_TRANSITION")
        need((later["effective_actual"], later["source_lane"]) == (after89, lane89), "rpf89:ADMISSION_TRANSITION")
        module = method_id.split(".")[0]
        methods.append({"id": method_id, "module": module, "required": row["required"], "route": route,
                        "original_actual": original, "rpf87_actual": after87, "rpf89_actual": after89,
                        "rpf87_source_lane": lane87, "rpf89_source_lane": lane89})
        original_counts[original] += 1
        phase87[after87] += 1
        phase89[after89] += 1
        router_routes[route][original] += 1
        if after89 == "UNAVAILABLE":
            remaining.append(method_id)
            residual_routes[route] += 1
            residual_modules[module] += 1

    gaps = original_counts["UNAVAILABLE"]
    expected_routes = {route: dict(counts) for route, counts in router_routes.items()}
    need(counts_are(handoff["counts"], original_counts) and counts_are(previous["counts"], original_counts)
         and routes_are(handoff["routes"], expected_routes),
         "handoff:ORIGINAL_COUNTS")
    original_exit = int(gaps > 0)
    dedicated = router_routes["DEDICATED_RUNNER"]["UNAVAILABLE"]
    need(count_is(handoff["unavailable_required_count"], gaps) and count_is(previous["unavailable"], gaps)
         and count_is(previous["dedicated_unavailable"], dedicated)
         and count_is(handoff["router_exit"], original_exit) and count_is(previous["enforce_exit"], original_exit)
         and handoff["all_required_status"] == ("UNAVAILABLE" if gaps else "PASS")
         and handoff["portable_status"] == "PASS"
         and handoff["diagnostic_continuation"] == "CONTINUE_DIAGNOSTIC_ONLY", "handoff:GATE_DISPOSITION")
    if router := reports.get("rpf90"):
        need(router["ledger_sha256"] == handoff["router_ledger_sha256"]
             and counts_are(router["counts"], original_counts) and routes_are(router["routes"], expected_routes)
             and router["coverage_promoted"] is False and router["validation_status"] == "VALIDATED_NO_PORTABLE_ERROR",
             "rpf90:ROUTER_HANDOFF_MISMATCH")

    need(counts_are(new["upstream_rpf87_counts"], phase87), "rpf89:UPSTREAM_COUNTS")
    for report, stage, count, admitted in ((old, "rpf87", phase87, len(first)),
                                           (new, "rpf89", phase89, len(first | second))):
        need(counts_are(report["effective_required"]["counts"], count)
             and count_is(report["unavailable_remaining"], count["UNAVAILABLE"])
             and count_is(report["dedicated_unavailable_remaining"], dedicated - admitted),
             f"{stage}:EFFECTIVE_COUNTS")

    return {"schema": "rpf120-required-coverage-diagnostic/v1", "identity": binding,
            "evidence_kind": "LOCAL_SYNTHETIC_CONTROL_ONLY" if synthetic else "SUPPLIED_HOSTED_REPORTS",
            "input_sha256": digests, "reconciliation_status": "VALID",
            "matrix_lf_sha256": source["matrix_lf_sha256"],
            "coverage_gate": "BLOCKED_BY_REQUIRED_COVERAGE" if remaining else "REQUIRED_COVERAGE_SATISFIED",
            "coverage_promoted": False, "release_authority": "NONE",
            "stages": {stage: {"counts": {state: counts[state] for state in STATES},
                               "required_coverage": "UNAVAILABLE" if counts["UNAVAILABLE"] else "PASS"}
                       for stage, counts in (("router", original_counts), ("rpf87", phase87), ("rpf89", phase89))},
            "required_methods": total, "admitted_rpf87": sorted(first), "admitted_rpf89": sorted(second),
            "remaining": {"count": len(remaining), "method_ids": remaining,
                          "by_route": dict(residual_routes), "by_module": dict(residual_modules)},
            "methods": methods}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True, help="Original RPF-85 JSON")
    parser.add_argument("--rpf87", type=Path, required=True, help="RPF-87 JSON from the same run and attempt")
    parser.add_argument("--rpf89", type=Path, required=True, help="RPF-89 JSON from the same run and attempt")
    parser.add_argument("--rpf90", type=Path, help="Optional Router observation from the same run and attempt")
    parser.add_argument("--synthetic", action="store_true", help="Permit explicitly labelled synthetic reports")
    args = parser.parse_args(argv)
    try:
        inputs = {role: read_input(getattr(args, role), role) for role in SCHEMAS if getattr(args, role) is not None}
        report = reconcile(inputs, synthetic=args.synthetic)
    except (Invalid, KeyError, TypeError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, Invalid) else "MALFORMED_SCHEMA"
        print(f"RPF120_INVALID {reason}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
