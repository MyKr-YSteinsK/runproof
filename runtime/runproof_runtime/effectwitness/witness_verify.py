"""Pure offline validation for RPF-43 Witness bundles (standard library only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from .effect_oracle import evaluate_order_effect

SCHEMA_VERSION = "rpf-effect-witness-v1"
ISSUER_ID = "runproof-effectwitness-witness-issuer"
VERIFIER_ID = "runproof-effectwitness-offline-verifier"
VERIFIER_VERSION = "1"
MAX_BUNDLE_BYTES = 128 * 1024
HEX_256 = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
EVENT_ORDER = ("contracts_preregistered", "environment_initialized", "authority_before_verified",
               "tool_result_observed", "fault_activation_observed", "receipt_reconciled",
               "authority_after_verified", "effect_verified", "cleanup_completed")
LIMITATIONS = ["NO_ISSUER_SIGNATURE", "NO_PROVIDER_SESSION", "SINGLE_RUN_NOT_REPRODUCTION",
               "CONTROLLED_LOCAL_SIMULATION_ONLY"]


class VerificationRejected(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _reject(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationRejected(code)


def _fields(value, names: set[str], code: str) -> dict:
    _reject(type(value) is dict and set(value) == names, code)
    return value


def _identifier(value) -> bool:
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def _timestamp(value) -> datetime:
    _reject(isinstance(value, str), "TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise VerificationRejected("TIMESTAMP_INVALID") from error
    _reject(parsed.tzinfo is not None, "TIMESTAMP_TIMEZONE_REQUIRED")
    return parsed


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationRejected("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _verify_contracts(contracts: dict, capture_id: str) -> tuple[dict, dict, dict]:
    _fields(contracts, {"execution", "effect", "experiment", "sha256"}, "CONTRACT_BUNDLE_FIELDS")
    execution, effect, experiment = contracts["execution"], contracts["effect"], contracts["experiment"]
    _fields(execution, {"schema_version", "agent_id", "driver", "tools", "budgets"},
            "EXECUTION_FIELDS")
    _reject(execution["schema_version"] == "rpf-agent-execution-v1"
            and execution["agent_id"] == "rpf41-refund-agent-v1"
            and execution["driver"] == "deterministic"
            and execution["tools"] == ["inspect_order", "refund_order"], "EXECUTION_CONTRACT")
    budgets = _fields(execution["budgets"], {"provider_requests", "steps", "tokens", "cost_cny",
                            "seconds", "request_seconds", "fault_trials"}, "BUDGET_FIELDS")
    ceilings = {"provider_requests": 4, "steps": 8, "tokens": 10_000, "cost_cny": 1.0,
                "seconds": 1200, "request_seconds": 90, "fault_trials": 3}
    _reject(all((type(value) in (int, float) if key == "cost_cny" else type(value) is int)
                and 0 < value <= ceilings[key] for key, value in budgets.items()), "BUDGET_INVALID")

    _fields(effect, {"schema_version", "contract_id", "order_id", "operation_id", "amount_minor",
                     "currency", "initial_status", "required_status", "authority_id", "verifier_id",
                     "verifier_version"}, "EFFECT_FIELDS")
    _reject(effect["schema_version"] == "rpf-order-effect-v1"
            and effect["contract_id"] == "full-refund-v1"
            and type(effect["amount_minor"]) is int and 0 < effect["amount_minor"] <= 1_000_000
            and effect["currency"] == "CNY" and effect["initial_status"] == "PAID"
            and effect["required_status"] == "REFUNDED"
            and effect["verifier_id"] == "rpf41-order-effect-verifier"
            and effect["verifier_version"] == "1", "EFFECT_CONTRACT")

    _fields(experiment, {"schema_version", "run_id", "scenario_id", "environment_id",
                         "environment_revision", "owner", "reset_generation", "fault",
                         "execution_digest", "effect_digest", "capture_id", "capture_mode"},
            "EXPERIMENT_FIELDS")
    run_id = experiment["run_id"]
    _reject(experiment["schema_version"] == "rpf-experiment-v3"
            and experiment["owner"] == "rpf-43"
            and experiment["capture_id"] == capture_id
            and experiment["capture_mode"] == "DETERMINISTIC_CAPTURE"
            and experiment["scenario_id"] == "order-full-refund"
            and experiment["environment_revision"] == "rpf41-sqlite-orders-v1"
            and experiment["fault"] == "response-lost"
            and type(experiment["reset_generation"]) is int
            and experiment["reset_generation"] == 0
            and all(_identifier(experiment[k]) for k in ("run_id", "environment_id", "capture_id")),
            "EXPERIMENT_IDENTITY")
    _reject(effect["order_id"] == "order-" + run_id
            and effect["operation_id"] == "refund-" + run_id
            and effect["authority_id"] == "authority-" + run_id
            and experiment["environment_id"] == "env-" + run_id, "RUN_REFERENCE_MISMATCH")
    _reject(experiment["execution_digest"] == digest(execution)
            and experiment["effect_digest"] == digest(effect), "CONTRACT_REFERENCE_MISMATCH")
    hashes = _fields(contracts["sha256"], {"execution", "effect", "experiment"}, "CONTRACT_HASH_FIELDS")
    _reject(hashes == {"execution": digest(execution), "effect": digest(effect),
                       "experiment": digest(experiment)}, "CONTRACT_HASH_MISMATCH")
    return execution, effect, experiment


def _verify_snapshot(snapshot: dict, *, effect: dict, experiment: dict, before: bool) -> dict:
    _fields(snapshot, {"data", "sha256"}, "AUTHORITY_SNAPSHOT_FIELDS")
    data = _fields(snapshot["data"], {"reader_id", "reader_version", "source_id", "environment",
                                      "order", "receipts"}, "AUTHORITY_DATA_FIELDS")
    _reject(isinstance(snapshot["sha256"], str) and HEX_256.fullmatch(snapshot["sha256"])
            and snapshot["sha256"] == digest(data), "AUTHORITY_SNAPSHOT_HASH")
    _reject(data["reader_id"] == "rpf41-sqlite-authority-reader" and data["reader_version"] == "1"
            and data["source_id"] == effect["authority_id"], "AUTHORITY_READER_IDENTITY")
    environment = _fields(data["environment"], {"owner", "run_id", "environment_id",
                             "environment_revision", "reset_generation"}, "ENVIRONMENT_FIELDS")
    _reject(type(environment["reset_generation"]) is int and environment["reset_generation"] == 0,
            "AUTHORITY_ENVIRONMENT_GENERATION")
    _reject(environment == {"owner": "rpf-43", "run_id": experiment["run_id"],
                            "environment_id": experiment["environment_id"],
                            "environment_revision": "rpf41-sqlite-orders-v1", "reset_generation": 0},
            "AUTHORITY_ENVIRONMENT_IDENTITY")
    order = _fields(data["order"], {"order_id", "paid_minor", "refunded_minor", "currency",
                                    "status", "revision"}, "ORDER_FIELDS")
    _reject(order["order_id"] == effect["order_id"] and order["paid_minor"] == effect["amount_minor"]
            and order["currency"] == effect["currency"] and type(order["refunded_minor"]) is int
            and type(order["revision"]) is int, "AUTHORITY_ORDER_IDENTITY")
    _reject(type(data["receipts"]) is list, "AUTHORITY_RECEIPTS_TYPE")
    for receipt in data["receipts"]:
        _fields(receipt, {"operation_id", "order_id", "amount_minor", "currency", "receipt_id",
                          "status", "committed_revision"}, "RECEIPT_FIELDS")
        _reject(all(isinstance(receipt[key], str) for key in
                    ("operation_id", "order_id", "currency", "receipt_id", "status"))
                and type(receipt["amount_minor"]) is int
                and type(receipt["committed_revision"]) is int, "RECEIPT_TYPES")
    expected_before = {"order_id": effect["order_id"], "paid_minor": effect["amount_minor"],
                       "refunded_minor": 0, "currency": effect["currency"],
                       "status": "PAID", "revision": 0}
    if before:
        _reject(order == expected_before and data["receipts"] == [], "AUTHORITY_BEFORE_STATE")
    return data


def _business_oracle(effect: dict, before: dict, after: dict) -> tuple[str, list[str], list[str]]:
    result = evaluate_order_effect(effect, before["environment"]["environment_id"], before, after)
    return result["contract_outcome"], result["violated_rules"], result["evidence_gaps"]


def _derive_fault_activation(fault: dict) -> str:
    _fields(fault, {"planned", "triggered", "observed", "reconciled", "activation"}, "FAULT_FIELDS")
    _reject(all(type(fault[k]) is bool for k in ("planned", "triggered", "observed", "reconciled")),
            "FAULT_BOOLEAN_FIELDS")
    if not fault["planned"]:
        derived = "NOT_PLANNED" if not any(fault[k] for k in ("triggered", "observed", "reconciled")) else "UNKNOWN"
    elif fault["triggered"] and fault["observed"] and fault["reconciled"]:
        derived = "TRIGGERED"
    elif not any(fault[k] for k in ("triggered", "observed", "reconciled")):
        derived = "NOT_TRIGGERED"
    else:
        derived = "UNKNOWN"
    _reject(fault["activation"] == derived, "FAULT_ACTIVATION_MISMATCH")
    return derived


def _verify_events(events, observation: dict) -> None:
    _reject(type(events) is list and tuple(event.get("type") for event in events if type(event) is dict)
            == EVENT_ORDER and len(events) == len(EVENT_ORDER), "EVENT_ORDER")
    seen_ids = set()
    prior_time = None
    for index, event in enumerate(events, start=1):
        _fields(event, {"seq", "event_id", "observed_at", "type", "facts", "facts_sha256"},
                "EVENT_FIELDS")
        _reject(type(event["seq"]) is int and event["seq"] == index and _identifier(event["event_id"])
                and event["event_id"] not in seen_ids, "EVENT_IDENTITY")
        seen_ids.add(event["event_id"])
        stamp = _timestamp(event["observed_at"])
        _reject(prior_time is None or stamp >= prior_time, "EVENT_TIME_ORDER")
        prior_time = stamp
        _reject(event["facts_sha256"] == digest(event["facts"]), "EVENT_FACT_HASH")

    exp, effect = observation["experiment"], observation["effect"]
    contracts = observation["contracts"]
    before, after = observation["authority_before"], observation["authority_after"]
    tool_call, reconciliation, cleanup = (observation["tool_calls"][0], observation["reconciliation"],
                                           observation["cleanup"])
    fault = observation["fault"]
    expected_facts = [
        {"owner": exp["owner"], "capture_id": exp["capture_id"],
         "contract_hashes": contracts["sha256"]},
        {"owner": exp["owner"], "run_id": exp["run_id"], "environment_id": exp["environment_id"]},
        {"snapshot_sha256": before["sha256"]},
        {"name": tool_call["name"], "arguments": tool_call["arguments"], "result": tool_call["result"]},
        {key: fault[key] for key in ("planned", "triggered", "observed")},
        reconciliation,
        {"snapshot_sha256": after["sha256"]},
        {"contract_outcome": effect["contract_outcome"], "before_sha256": effect["before_sha256"],
         "after_sha256": effect["after_sha256"], "verifier_id": effect["verifier_id"],
         "verifier_version": effect["verifier_version"]},
        cleanup,
    ]
    for event, expected in zip(events, expected_facts):
        _reject(event["facts"] == expected, "EVENT_FACT_REFERENCE_MISMATCH")


def _validate_bundle(bundle: dict) -> None:
    _fields(bundle, {"schema_version", "issuer", "capture", "contracts", "observation", "events",
                     "claims", "digests", "limitations"}, "WITNESS_FIELDS")
    _reject(bundle["schema_version"] == SCHEMA_VERSION, "WITNESS_SCHEMA_VERSION")
    issuer = _fields(bundle["issuer"], {"issuer_id", "issuer_version", "attestation", "source_digest"},
                     "ISSUER_FIELDS")
    _reject(issuer["issuer_id"] == ISSUER_ID and issuer["issuer_version"] == "1"
            and issuer["attestation"] == "UNSIGNED_LOCAL_TOOL"
            and isinstance(issuer["source_digest"], str) and HEX_256.fullmatch(issuer["source_digest"]),
            "ISSUER_IDENTITY")
    capture = _fields(bundle["capture"], {"capture_id", "captured_at", "source_level", "target_driver",
                                         "session_reference", "environment"}, "CAPTURE_FIELDS")
    _reject(_identifier(capture["capture_id"])
            and capture["source_level"] == "MANAGED_LOCAL_SIMULATION"
            and capture["target_driver"] == "DETERMINISTIC_CONTROLLED_TARGET", "CAPTURE_SOURCE_LEVEL")
    _timestamp(capture["captured_at"])
    session = _fields(capture["session_reference"], {"kind", "session_id", "session_digest", "policy"},
                      "SESSION_REFERENCE_FIELDS")
    _reject(session == {"kind": "DETERMINISTIC_CAPTURE", "session_id": None,
                        "session_digest": None, "policy": "NOT_APPLICABLE"}, "SESSION_REFERENCE_MISMATCH")

    execution, effect_contract, experiment = _verify_contracts(bundle["contracts"], capture["capture_id"])
    environment = _fields(capture["environment"], {"owner", "run_id", "environment_id", "revision"},
                          "CAPTURE_ENVIRONMENT_FIELDS")
    _reject(environment == {"owner": experiment["owner"], "run_id": experiment["run_id"],
                            "environment_id": experiment["environment_id"],
                            "revision": experiment["environment_revision"]}, "CAPTURE_ENVIRONMENT_MISMATCH")

    observation = _fields(bundle["observation"], {"run_outcome", "effect", "fault", "tool_calls",
                               "reconciliation", "authority_before", "authority_after", "cleanup"},
                         "OBSERVATION_FIELDS")
    before_data = _verify_snapshot(observation["authority_before"], effect=effect_contract,
                                   experiment=experiment, before=True)
    after_data = _verify_snapshot(observation["authority_after"], effect=effect_contract,
                                  experiment=experiment, before=False)
    effect = _fields(observation["effect"], {"contract_outcome", "verifier_id", "verifier_version",
                             "violated_rules", "evidence_gaps", "receipt_hash", "before_sha256",
                             "after_sha256"}, "LIVE_EFFECT_FIELDS")
    _reject(effect["verifier_id"] == "rpf41-order-effect-verifier" and effect["verifier_version"] == "1"
            and effect["before_sha256"] == observation["authority_before"]["sha256"]
            and effect["after_sha256"] == observation["authority_after"]["sha256"]
            and effect["receipt_hash"] == digest(after_data["receipts"]), "LIVE_EFFECT_IDENTITY")
    oracle, violations, gaps = _business_oracle(effect_contract, before_data, after_data)
    _reject(effect["contract_outcome"] == oracle and effect["violated_rules"] == violations
            and effect["evidence_gaps"] == gaps, "LIVE_ORACLE_MISMATCH")
    _reject(observation["run_outcome"] == "PASS", "RUN_OUTCOME_NOT_PASS")

    calls = observation["tool_calls"]
    _reject(type(calls) is list and len(calls) == 1, "TOOL_CALL_COUNT")
    call = _fields(calls[0], {"name", "arguments", "result"}, "TOOL_CALL_FIELDS")
    expected_args = {k: effect_contract[k] for k in ("order_id", "operation_id", "amount_minor")}
    _reject(call["name"] == "refund_order" and call["arguments"] == expected_args
            and call["result"] == {"status": "UNKNOWN_OUTCOME", "operation_id": effect_contract["operation_id"],
                                   "reason": "CONTROLLED_POST_COMMIT_RESPONSE_LOSS"}, "TOOL_RESULT_MISMATCH")
    reconciliation = _fields(observation["reconciliation"], {"status", "receipt_id", "operation_id"},
                             "RECONCILIATION_FIELDS")
    _reject(len(after_data["receipts"]) == 1, "RECONCILIATION_RECEIPT_CARDINALITY")
    _reject(reconciliation == {"status": "RECONCILED_COMMITTED",
                               "receipt_id": after_data["receipts"][0]["receipt_id"],
                               "operation_id": effect_contract["operation_id"]}, "RECONCILIATION_MISMATCH")
    cleanup = _fields(observation["cleanup"], {"status", "reset_generation", "receipt_count_after_reset"},
                      "CLEANUP_FIELDS")
    _reject(cleanup["status"] == "RESET_AND_REMOVED"
            and type(cleanup["reset_generation"]) is int and cleanup["reset_generation"] == 1
            and type(cleanup["receipt_count_after_reset"]) is int
            and cleanup["receipt_count_after_reset"] == 0, "CLEANUP_NOT_VERIFIED")

    activation = _derive_fault_activation(observation["fault"])
    _reject(observation["fault"] == {"planned": True, "triggered": True, "observed": True,
                                      "reconciled": True, "activation": "TRIGGERED"}
            and activation == "TRIGGERED", "FAULT_EVIDENCE_MISMATCH")
    _verify_events(bundle["events"], {"experiment": experiment, "contracts": bundle["contracts"],
                    "effect": effect, "fault": observation["fault"],
                    "authority_before": observation["authority_before"],
                    "authority_after": observation["authority_after"],
                    "tool_calls": calls, "reconciliation": reconciliation, "cleanup": cleanup})
    _reject(bundle["capture"]["captured_at"] == bundle["events"][-1]["observed_at"],
            "CAPTURE_TIME_MISMATCH")

    claims = _fields(bundle["claims"], {"contract_outcome", "fault_activation", "attribution_strength",
                                        "reproduction", "run_outcome"}, "CLAIM_FIELDS")
    _reject(claims == {"contract_outcome": oracle, "fault_activation": activation,
                       "attribution_strength": "CORRELATIONAL_ONLY", "reproduction": "NOT_TESTED",
                       "run_outcome": observation["run_outcome"]}, "CLAIM_OVERREACH_OR_MISMATCH")
    _reject(bundle["limitations"] == LIMITATIONS, "LIMITATIONS_MISSING")
    digests = _fields(bundle["digests"], {"contracts", "observation", "events", "claims"}, "DIGEST_FIELDS")
    expected_digests = {"contracts": digest(bundle["contracts"]),
                        "observation": digest(bundle["observation"]),
                        "events": digest(bundle["events"]), "claims": digest(bundle["claims"])}
    _reject(digests == expected_digests, "INTERNAL_DIGEST_MISMATCH")


def verify_bytes(raw: bytes, expected_sha256: str | None = None) -> dict:
    _reject(type(raw) is bytes, "BUNDLE_BYTES_REQUIRED")
    file_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        _reject(isinstance(expected_sha256, str) and HEX_256.fullmatch(expected_sha256) is not None,
                "TRUSTED_ANCHOR_FORMAT")
        _reject(file_sha256 == expected_sha256, "FILE_SHA256_MISMATCH")
    _reject(type(raw) is bytes and 0 < len(raw) <= MAX_BUNDLE_BYTES, "BUNDLE_SIZE")
    try:
        bundle = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                            parse_constant=lambda _: (_ for _ in ()).throw(VerificationRejected("JSON_CONSTANT")))
    except VerificationRejected:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise VerificationRejected("JSON_INVALID") from error
    try:
        is_canonical = canonical(bundle) == raw
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise VerificationRejected("JSON_NONCANONICAL_VALUE") from error
    _reject(is_canonical, "BUNDLE_NOT_CANONICAL")
    _reject(type(bundle) is dict, "WITNESS_FIELDS")
    schema = bundle.get("schema_version")
    try:
        if schema == SCHEMA_VERSION:
            _validate_bundle(bundle)
        elif schema == "rpf-effect-witness-v2":
            # Static, pure module; no runtime/executor imports on the offline path.
            from .cross_core import validate_bundle
            validate_bundle(bundle)
        else:
            raise VerificationRejected("WITNESS_SCHEMA_VERSION")
    except (KeyError, TypeError, IndexError, AttributeError, RecursionError) as error:
        raise VerificationRejected("WITNESS_STRUCTURE_INVALID") from error
    anchored = expected_sha256 is not None
    return {"status": "VERIFIED_ANCHORED" if anchored else "UNANCHORED_INCONCLUSIVE",
            "trust_level": ("MANAGED_LOCAL_SIMULATION_BOUNDED" if schema == SCHEMA_VERSION else
                            "CONTROLLED_LOCAL_SIMULATION_BOUNDED") if anchored else "UNANCHORED",
            "issuer_authenticity": "NOT_ESTABLISHED", "file_sha256": file_sha256,
            "schema_version": schema, "verifier_id": VERIFIER_ID,
            "verifier_version": VERIFIER_VERSION if schema == SCHEMA_VERSION else "2",
            "contract_outcome": bundle["claims"]["contract_outcome"],
            "fault_activation": bundle["claims"]["fault_activation"],
            "attribution_strength": bundle["claims"]["attribution_strength"],
            "reproduction": bundle["claims"]["reproduction"],
            "reason_codes": [] if anchored else ["TRUSTED_EXTERNAL_SHA256_REQUIRED"]}


def verify_file(path: Path, expected_sha256: str | None = None) -> dict:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BUNDLE_BYTES + 1)
            if len(raw) > MAX_BUNDLE_BYTES or stream.read(1):
                raise VerificationRejected("BUNDLE_SIZE")
    except VerificationRejected:
        raise
    except OSError as error:
        raise VerificationRejected("WITNESS_FILE_UNAVAILABLE") from error
    return verify_bytes(raw, expected_sha256)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("witness", type=Path)
    parser.add_argument("--expected-sha256", help="trusted full-file SHA-256 obtained out of band")
    args = parser.parse_args(argv)
    try:
        result = verify_file(args.witness, args.expected_sha256)
    except VerificationRejected as error:
        result = {"status": "REJECTED", "verifier_id": VERIFIER_ID,
                  "verifier_version": VERIFIER_VERSION, "reason_codes": [error.code]}
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 3
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "VERIFIED_ANCHORED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
