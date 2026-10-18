"""Independent content verifier for target wrappers; no SDK, database or Provider imports."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from .contracts import ENV_REVISION, READER_ID, canonical, digest, fields, identifier, require
from .effect_oracle import evaluate_order_effect
from .target_contracts import (FRAMEWORK, OPENAI_CLIENT_VERSION, SDK_CORE_SHA256,
                               TargetContracts, arguments_for, strict_json)

LIMITATIONS = ["LOCAL_CONTROLLED_SIMULATION_ONLY", "ISSUER_AUTHENTICITY_NOT_ESTABLISHED",
               "SDK_RUNTIME_ORIGIN_HOST_OBSERVED_NOT_EXTERNALLY_ATTESTED",
               "NO_CAUSAL_ATTRIBUTION_OR_REPRODUCTION_CLAIM", "NOT_LEGACY_WITNESS_V1_OR_V2"]


def check_content(bundle):
    fields(bundle, {"schema_version", "source_level", "contracts", "sdk", "calls", "provider_requests", "usage",
        "authority_before", "authority_after", "effect", "fault", "controller_reconciliation", "cleanup", "limitations", "digests"}, "TARGET_EVIDENCE_FIELDS")
    require(bundle["schema_version"] == "rpf-target-evidence-v1" and bundle["limitations"] == LIMITATIONS,
            "TARGET_EVIDENCE_VERSION_OR_LIMITS")
    require(bundle["digests"] == {k: digest(bundle[k]) for k in bundle if k != "digests"}, "TARGET_EVIDENCE_DIGEST")
    contracts = TargetContracts.from_document(bundle["contracts"])
    effect, experiment = contracts.effect, contracts.experiment
    snapshots = []
    for name in ("authority_before", "authority_after"):
        snapshot = bundle[name]
        fields(snapshot, {"data", "sha256"}, "TARGET_SNAPSHOT_FIELDS")
        require(snapshot["sha256"] == digest(snapshot["data"]), "TARGET_SNAPSHOT_DIGEST")
        data = snapshot["data"]
        fields(data, {"reader_id", "reader_version", "source_id", "environment", "order", "receipts"}, "TARGET_AUTHORITY_FIELDS")
        require(data["reader_id"] == READER_ID and data["reader_version"] == "1" and data["source_id"] == effect["authority_id"]
                and data["environment"] == {"owner": "rpf-48", "run_id": experiment["run_id"],
                    "environment_id": experiment["environment_id"], "environment_revision": ENV_REVISION, "reset_generation": 0},
                "TARGET_AUTHORITY_IDENTITY")
        snapshots.append(data)
    recomputed = evaluate_order_effect(effect, experiment["environment_id"], *snapshots)
    require(bundle["effect"] == recomputed, "TARGET_ORACLE_MISMATCH")
    requests, calls = bundle["provider_requests"], bundle["calls"]
    require(type(requests) is list and len(requests) <= 6 and type(calls) is list and len(calls) <= 12,
            "TARGET_EVIDENCE_BUDGET")
    intents, request_map = {}, {}
    for record in requests:
        require(record["run_id"] == experiment["run_id"] and record["status"] == "RECEIVED"
                and type(record["attempt"]) is int and 1 <= record["attempt"] <= 6
                and record["attempt"] not in request_map, "TARGET_REQUEST_IDENTITY_OR_USAGE")
        require(all(type(v) is int and v >= 0 for v in record["usage"].values())
                and set(record["usage"]) == {"prompt_tokens", "completion_tokens", "total_tokens"}, "TARGET_REQUEST_USAGE")
        request_map[record["attempt"]] = record
        for intent in record["intents"]:
            require(intent["call_id"] not in intents and intent["response_id"] == record["response_id"], "TARGET_INTENT_IDENTITY")
            intents[intent["call_id"]] = intent
    require(len({c["call_id"] for c in calls}) == len(calls), "TARGET_DUPLICATE_CALL")
    observed = mutated = pending = False
    for call in calls:
        fields(call, {"call_id", "name", "arguments_sha256", "response_id", "result", "result_sha256", "returned_in_request"}, "TARGET_TOOL_RECORD_FIELDS")
        require(identifier(call["call_id"]) and call["call_id"] in intents
                and {k: call[k] for k in ("call_id", "name", "arguments_sha256", "response_id")} == intents[call["call_id"]], "TARGET_TOOL_ORIGIN")
        name = call["name"]
        require(call["arguments_sha256"] == digest(arguments_for(name, effect))
                and call["result_sha256"] == digest(call["result"]), "TARGET_TOOL_CONTENT")
        require(not pending or name == "reconcile_order", "TARGET_UNSAFE_UNKNOWN_RETRY")
        if name == "inspect_order":
            require(not mutated and call["result"] == {"order_id": effect["order_id"], "status": "PAID", "revision": 0}, "TARGET_OBSERVE_RESULT")
            observed = True
        elif name == "refund_order":
            require(observed and not mutated, "TARGET_MUTATION_ORDER")
            mutated = True
            receipt = snapshots[1]["receipts"]
            require(len(receipt) == 1, "TARGET_RECEIPT_MISSING")
            expected = ({"status": "UNKNOWN_OUTCOME", "operation_id": effect["operation_id"], "reason": "CONTROLLED_POST_COMMIT_RESPONSE_LOSS"}
                if experiment["fault"] == "response-lost" else {"status": "COMMITTED", "operation_id": effect["operation_id"],
                    "receipt_id": receipt[0]["receipt_id"], "committed_revision": 1})
            require(call["result"] == expected, "TARGET_MUTATION_RESULT")
            pending = experiment["fault"] == "response-lost"
        else:
            require(pending and call["result"] == {"status": "RECONCILED_COMMITTED", "operation_id": effect["operation_id"],
                    "receipt_id": snapshots[1]["receipts"][0]["receipt_id"]}, "TARGET_RECONCILE_RESULT")
            pending = False
        if call["returned_in_request"] is not None:
            request = request_map.get(call["returned_in_request"], {})
            origin_attempt = next(r["attempt"] for r in requests if r["response_id"] == call["response_id"])
            require(call["returned_in_request"] > origin_attempt and {"call_id": call["call_id"], "result_sha256": call["result_sha256"]}
                    in request.get("tool_returns", []), "TARGET_RETURN_REFERENCE")
    usage = bundle["usage"]
    inputs = sum(r["usage"]["prompt_tokens"] for r in requests)
    outputs = sum(r["usage"]["completion_tokens"] for r in requests)
    require(all(type(v) is int and v >= 0 for v in (inputs, outputs))
            and all(r["usage"]["total_tokens"] == r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"] for r in requests)
            and usage["tokens"] == inputs + outputs <= 15000 and usage["input_tokens"] == inputs and usage["output_tokens"] == outputs
            and usage["usage_known"] is True and usage["automatic_retries"] == 0
            and usage["estimated_cost_cny_upper"] == (0.0 if bundle["source_level"] == "FIXTURE_TEST_ONLY"
                else (inputs * 2 + outputs * 8) / 1_000_000), "TARGET_USAGE_MISMATCH")
    sdk = bundle["sdk"]
    level = bundle["source_level"]
    require(level in ("FIXTURE_TEST_ONLY", "AGENT_RUNTIME_CONNECTED", "EXTERNAL_AGENT_EFFECT_VERIFIED"), "TARGET_SOURCE_LEVEL")
    expected_fault = {"planned": experiment["fault"] != "none", "triggered": mutated and experiment["fault"] != "none",
                      "observed": mutated and experiment["fault"] != "none", "reconciled": any(c["name"] == "reconcile_order" for c in calls)}
    require(bundle["fault"] == expected_fault, "TARGET_FAULT_MISMATCH")
    if level == "EXTERNAL_AGENT_EFFECT_VERIFIED":
        require(contracts.execution["driver"] == "pydantic-ai" and sdk["source"] == "EXTERNAL_AGENT_RUNTIME"
                and sdk["host_protocol"] == "rpf-target-loopback-json-v1"
                and sdk["runtime"]["framework"] == FRAMEWORK["name"]
                and sdk["runtime"]["version"] == FRAMEWORK["version"] and sdk["process_exit"] == 0
                and sdk["runtime"]["agent_config_sha256"] == contracts.execution["config_sha256"]
                and sdk["runtime"]["sdk_source_sha256"] == SDK_CORE_SHA256
                and sdk["runtime"]["openai_version"] == OPENAI_CLIENT_VERSION
                and type(sdk["runtime"]["pid"]) is int and sdk["runtime"]["pid"] > 0
                and sdk["report"]["status"] == "COMPLETED" and sdk["failure"] is None
                and sdk["report"]["requests"] == len(requests) == usage["provider_http_attempts"]
                and sdk["report"]["input_tokens"] == inputs and sdk["report"]["output_tokens"] == outputs
                and all(r["transport"] == "DeepSeek-HTTPS-no-retry" for r in requests)
                and set(intents) == {c["call_id"] for c in calls} and mutated and not pending
                and all(c["returned_in_request"] is not None for c in calls)
                and bundle["controller_reconciliation"] is None
                and bundle["cleanup"] == {"status": "RESET_AND_REMOVED", "reset_generation": 1, "receipt_count_after_reset": 0},
                "TARGET_LIVE_CHAIN_NOT_ESTABLISHED")
    elif level == "FIXTURE_TEST_ONLY":
        require(sdk["source"] == "FIXTURE_TEST_ONLY" and usage["provider_http_attempts"] == 0, "FIXTURE_SOURCE_MISMATCH")
    return {"source_level": level, "contract_outcome": recomputed["contract_outcome"],
            "issuer_authenticity": "NOT_ESTABLISHED", "attribution": "CORRELATIONAL_ONLY", "reproduction": "NOT_TESTED"}


def seal(bundle):
    return {**bundle, "digests": {k: digest(v) for k, v in bundle.items()}}


def verify_bytes(raw, expected_sha256=None):
    require(len(raw) <= 524288, "TARGET_EVIDENCE_SIZE")
    bundle = strict_json(raw)
    require(raw == canonical(bundle), "TARGET_EVIDENCE_NOT_CANONICAL")
    sha = hashlib.sha256(raw).hexdigest()
    require(expected_sha256 is None or sha == expected_sha256, "TARGET_EXTERNAL_ANCHOR_MISMATCH")
    facts = check_content(bundle)
    return {"status": "CONTENT_VERIFIED_ANCHORED" if expected_sha256 else "CONTENT_CHECKED_UNANCHORED",
            "schema_version": "rpf-target-evidence-v1", "file_sha256": sha, **facts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        with args.path.open("rb") as stream:
            result = verify_bytes(stream.read(524289), args.expected_sha256)
        print(canonical(result).decode())
        return 0 if args.expected_sha256 else 2
    except Exception as exc:
        print(canonical({"status": "REJECTED", "code": getattr(exc, "code", "TARGET_BUNDLE_MALFORMED")}).decode())
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
