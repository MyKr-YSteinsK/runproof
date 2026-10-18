"""Strict, offline verification for the RPF-50 controlled violation Witness."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from .effect_oracle import VERIFIER_ID, VERIFIER_VERSION, canonical, digest, evaluate_order_effect
from .target_contracts import TargetContracts

SCHEMA_VERSION = "rpf-effect-violation-witness-v1"
SOURCE_LEVEL = "CONTROLLED_DETERMINISTIC_SERVICE"
DEFECT_PROFILE = "KNOWN_DEFECT_HALF_REFUND_COMMITTED_V1"
LIMITATIONS = [
    "CONTROLLED_LOCAL_SIMULATION_ONLY",
    "KNOWN_DEFECT_PRE_REGISTERED_NOT_DISCOVERED_BY_AGENT",
    "AGENT_EXPOSURE_AND_AGENT_FAIL_NOT_APPLICABLE",
    "NO_NETWORK_FAULT_OR_PROVIDER_CALL",
    "SINGLE_RUN_NOT_REPRODUCTION",
    "ISSUER_AUTHENTICITY_NOT_ESTABLISHED",
]
SOURCE_FILES = (
    "runtime/runproof_runtime/models.py",
    "runtime/runproof_runtime/effectwitness/contracts.py",
    "runtime/runproof_runtime/effectwitness/effect_oracle.py",
    "runtime/runproof_runtime/effectwitness/orders.py",
    "runtime/runproof_runtime/effectwitness/target_contracts.py",
    "runtime/runproof_runtime/effectwitness/violation_lab.py",
    "runtime/runproof_runtime/effectwitness/violation_witness.py",
    "spikes/rpf-50/probe.py",
)


class WitnessRejected(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise WitnessRejected(code)


def _fields(value, names: set[str], code: str) -> None:
    _require(type(value) is dict and set(value) == names, code)


def _is_sha256(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _strict_json(raw: bytes) -> dict:
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, "DUPLICATE_JSON_KEY")
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: _require(False, "NONFINITE_JSON"))
    except WitnessRejected:
        raise
    except (UnicodeError, ValueError, TypeError):
        raise WitnessRejected("INVALID_JSON") from None
    _require(type(value) is dict, "TOP_LEVEL_OBJECT_REQUIRED")
    return value


def _validate_contracts(document: dict, run: dict) -> dict:
    try:
        contracts = TargetContracts.from_document(document)
    except Exception:
        raise WitnessRejected("CONTRACT_REJECTED") from None
    execution, effect, experiment = contracts.execution, contracts.effect, contracts.experiment
    _require(execution["driver"] == "deterministic-reference", "AGENT_DRIVER_NOT_APPLICABLE")
    _require(experiment["owner"] == "rpf-48" and experiment["fault"] == "none",
             "LOGICAL_OWNER_OR_NETWORK_FAULT")
    expected_run = {
        "run_id": experiment["run_id"],
        "environment_id": experiment["environment_id"],
        "environment_revision": experiment["environment_revision"],
        "logical_owner": experiment["owner"],
        "reset_generation": experiment["reset_generation"],
        "order_id": effect["order_id"],
        "operation_id": effect["operation_id"],
        "amount_minor": effect["amount_minor"],
        "currency": effect["currency"],
        "initial_status": effect["initial_status"],
        "required_status": effect["required_status"],
        "network_fault": "NOT_PLANNED",
    }
    _require(run == expected_run, "RUN_IDENTITY_MISMATCH")
    return {"execution": execution, "effect": effect, "experiment": experiment,
            "hashes": contracts.hashes}


def _validate_snapshot(snapshot: dict, *, expected_source: str, expected_run: dict,
                       after: bool) -> dict:
    _fields(snapshot, {"data", "sha256"}, "AUTHORITY_SNAPSHOT_FIELDS")
    data = snapshot["data"]
    _fields(data, {"reader_id", "reader_version", "source_id", "environment", "order", "receipts"},
            "AUTHORITY_DATA_FIELDS")
    _require(_is_sha256(snapshot["sha256"]) and digest(data) == snapshot["sha256"],
             "AUTHORITY_SNAPSHOT_DIGEST")
    _fields(data["environment"], {"owner", "run_id", "environment_id", "environment_revision",
                                  "reset_generation"}, "AUTHORITY_ENVIRONMENT_FIELDS")
    _require(type(data["environment"]["reset_generation"]) is int, "AUTHORITY_GENERATION_TYPE")
    _require(data["reader_id"] == "rpf41-sqlite-authority-reader" and data["reader_version"] == "1"
             and data["source_id"] == expected_source, "AUTHORITY_READER_IDENTITY")
    expected_environment = {
        "owner": "rpf-48", "run_id": expected_run["run_id"],
        "environment_id": expected_run["environment_id"],
        "environment_revision": "rpf41-sqlite-orders-v1", "reset_generation": 0,
    }
    _require(data["environment"] == expected_environment, "AUTHORITY_ENVIRONMENT_MISMATCH")
    _fields(data["order"], {"order_id", "paid_minor", "refunded_minor", "currency", "status", "revision"},
            "AUTHORITY_ORDER_FIELDS")
    _require(all(type(data["order"][key]) is int for key in
                 ("paid_minor", "refunded_minor", "revision"))
             and all(type(data["order"][key]) is str for key in
                     ("order_id", "currency", "status")), "AUTHORITY_ORDER_TYPES")
    initial_order = {"order_id": expected_run["order_id"], "paid_minor": 2500,
                     "refunded_minor": 0, "currency": "CNY", "status": "PAID", "revision": 0}
    if not after:
        _require(data["order"] == initial_order and data["receipts"] == [],
                 "AUTHORITY_BEFORE_NOT_INITIAL")
        return data

    expected_order = {**initial_order, "refunded_minor": 1250, "status": "REFUNDED", "revision": 1}
    _require(data["order"] == expected_order, "AUTHORITY_AFTER_NOT_DEFECT_STATE")
    _require(type(data["receipts"]) is list and len(data["receipts"]) == 1,
             "AUTHORITY_RECEIPT_COUNT")
    receipt = data["receipts"][0]
    _fields(receipt, {"operation_id", "order_id", "amount_minor", "currency", "receipt_id", "status",
                      "committed_revision"}, "AUTHORITY_RECEIPT_FIELDS")
    _require(all(type(receipt[key]) is int for key in ("amount_minor", "committed_revision"))
             and all(type(receipt[key]) is str for key in
                     ("operation_id", "order_id", "currency", "receipt_id", "status")),
             "AUTHORITY_RECEIPT_TYPES")
    expected_receipt_id = "receipt-" + digest({"environment": expected_run["environment_id"],
                                                 "operation_id": expected_run["operation_id"]})[:24]
    expected_receipt = {"operation_id": expected_run["operation_id"],
                        "order_id": expected_run["order_id"], "amount_minor": 2500,
                        "currency": "CNY", "receipt_id": expected_receipt_id,
                        "status": "COMMITTED", "committed_revision": 1}
    _require(receipt == expected_receipt, "AUTHORITY_RECEIPT_MISMATCH")
    return data


def _validate_events(events: list, run: dict, before: dict, after: dict, oracle: dict,
                     defect: dict, cleanup: dict) -> None:
    names = ["SERVICE_PROFILE_FROZEN", "ENVIRONMENT_INITIALIZED", "AUTHORITY_BEFORE_READ",
             "DEFECT_TXN_COMMITTED", "AUTHORITY_AFTER_READ", "ORACLE_EVALUATED",
             "SANDBOX_RESET_AND_REMOVED"]
    _require(type(events) is list and len(events) == len(names), "EVENT_COUNT")
    previous = None
    expected_facts = [
        {"profile_id": DEFECT_PROFILE, "run_id": run["run_id"]},
        {"environment_id": run["environment_id"], "owner": "rpf-48", "reset_generation": 0},
        {"snapshot_sha256": before["sha256"]},
        {"operation_id": run["operation_id"], "receipt_id": defect["receipt_id"],
         "refunded_minor": 1250, "status": "COMMITTED"},
        {"snapshot_sha256": after["sha256"]},
        {"contract_outcome": oracle["contract_outcome"], "violated_rules": oracle["violated_rules"],
         "evidence_gaps": oracle["evidence_gaps"]},
        cleanup,
    ]
    for seq, (event, name, facts) in enumerate(zip(events, names, expected_facts), start=1):
        _fields(event, {"seq", "event_id", "observed_at", "type", "facts", "facts_sha256"},
                "EVENT_FIELDS")
        _require(type(event["seq"]) is int and event["seq"] == seq
                 and event["event_id"] == f"event-{run['run_id']}-{seq:02d}"
                 and event["type"] == name and event["facts"] == facts
                 and event["facts_sha256"] == digest(facts), "EVENT_ORDER_OR_FACTS")
        try:
            observed = datetime.fromisoformat(event["observed_at"].replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            raise WitnessRejected("EVENT_TIME_INVALID") from None
        _require(observed.tzinfo is not None and (previous is None or observed >= previous),
                 "EVENT_TIME_ORDER")
        previous = observed


def validate_evidence(evidence: dict) -> None:
    _fields(evidence, {"issuer", "source_identity", "storage_task", "contracts", "control_reference",
                       "run", "service_profile", "defect_commit", "authority_before",
                       "authority_after", "effect_result", "dimensions", "events", "cleanup",
                       "budget", "limitations"}, "EVIDENCE_FIELDS")

    source_identity = evidence["source_identity"]
    _fields(source_identity, {"source_level", "source_sha256"}, "SOURCE_IDENTITY_FIELDS")
    _require(source_identity["source_level"] == SOURCE_LEVEL, "SOURCE_LEVEL")
    source_hashes = source_identity["source_sha256"]
    _require(type(source_hashes) is dict and set(source_hashes) == set(SOURCE_FILES)
             and all(_is_sha256(value) for value in source_hashes.values()), "SOURCE_HASHES")
    issuer = evidence["issuer"]
    _fields(issuer, {"issuer_id", "issuer_version", "attestation", "source_sha256"}, "ISSUER_FIELDS")
    _require(issuer == {"issuer_id": "runproof-rpf50-violation-witness-issuer", "issuer_version": "1",
                        "attestation": "UNSIGNED_LOCAL_TOOL",
                        "source_sha256": source_hashes["runtime/runproof_runtime/effectwitness/violation_witness.py"]},
             "ISSUER_IDENTITY")
    _require(evidence["storage_task"] == "rpf-50", "STORAGE_OWNER")

    run = evidence["run"]
    _fields(run, {"run_id", "environment_id", "environment_revision", "logical_owner", "reset_generation",
                  "order_id", "operation_id", "amount_minor", "currency", "initial_status",
                  "required_status", "network_fault"}, "RUN_FIELDS")
    contract = _validate_contracts(evidence["contracts"], run)
    effect, experiment = contract["effect"], contract["experiment"]

    profile = evidence["service_profile"]
    _fields(profile, {"profile_id", "profile_version", "pre_registered", "registered_before_run"},
            "PROFILE_FIELDS")
    _require(profile == {"profile_id": DEFECT_PROFILE, "profile_version": "1",
                         "pre_registered": True, "registered_before_run": True}, "PROFILE_IDENTITY")

    control = evidence["control_reference"]
    _fields(control, {"run_id", "environment_id", "order_id", "operation_id", "contract_outcome",
                      "effect_semantics_sha256", "authority_before_sha256", "authority_after_sha256",
                      "summary_sha256"}, "CONTROL_REFERENCE_FIELDS")
    semantics = {key: effect[key] for key in ("amount_minor", "currency", "initial_status", "required_status",
                                                "verifier_id", "verifier_version")}
    _require(all(isinstance(control[key], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}",
                                                                 control[key])
                 for key in ("run_id", "environment_id", "order_id", "operation_id")),
             "CONTROL_IDENTITY")
    _require(len({control["run_id"], run["run_id"]}) == 2
             and len({control["environment_id"], run["environment_id"]}) == 2
             and len({control["order_id"], run["order_id"]}) == 2
             and len({control["operation_id"], run["operation_id"]}) == 2
             and control["contract_outcome"] == "CONTRACT_SATISFIED_IN_RUN"
             and control["effect_semantics_sha256"] == digest(semantics)
             and _is_sha256(control["authority_before_sha256"])
             and _is_sha256(control["authority_after_sha256"])
             and _is_sha256(control["summary_sha256"]), "CONTROL_REFERENCE_MISMATCH")

    before = _validate_snapshot(evidence["authority_before"], expected_source=effect["authority_id"],
                                expected_run=run, after=False)
    after = _validate_snapshot(evidence["authority_after"], expected_source=effect["authority_id"],
                               expected_run=run, after=True)
    defect = evidence["defect_commit"]
    _fields(defect, {"transaction_mode", "precondition", "committed_refunded_minor", "committed_status",
                     "committed_revision", "receipt_id", "receipt_amount_minor", "commit_confirmed"},
            "DEFECT_COMMIT_FIELDS")
    receipt_id = after["receipts"][0]["receipt_id"]
    expected_defect = {"transaction_mode": "BEGIN IMMEDIATE",
                       "precondition": {"status": "PAID", "revision": 0, "refunded_minor": 0,
                                        "receipt_count": 0},
                       "committed_refunded_minor": 1250, "committed_status": "REFUNDED",
                       "committed_revision": 1, "receipt_id": receipt_id,
                       "receipt_amount_minor": 2500, "commit_confirmed": True}
    _require(defect == expected_defect, "DEFECT_COMMIT_FACTS")
    _require(type(defect["commit_confirmed"]) is bool
             and all(type(defect[key]) is int for key in
                     ("committed_refunded_minor", "committed_revision", "receipt_amount_minor"))
             and all(type(defect["precondition"][key]) is int
                     for key in ("revision", "refunded_minor", "receipt_count")), "DEFECT_COMMIT_TYPES")

    oracle = evidence["effect_result"]
    expected_oracle = evaluate_order_effect(effect, experiment["environment_id"], before, after)
    _require(oracle == expected_oracle
             and oracle["contract_outcome"] == "VIOLATION_CONFIRMED"
             and oracle["violated_rules"] == ["EXACTLY_ONE_FULL_REFUND_STATE"]
             and oracle["evidence_gaps"] == [], "ORACLE_RESULT_MISMATCH")

    dimensions = evidence["dimensions"]
    _fields(dimensions, {"business_contract", "fault_kind", "network_fault", "defect_activation",
                         "technical_attribution", "research_attribution", "reproduction",
                         "agent_exposure", "agent_fail", "run_outcome", "issuer_authenticity"},
            "DIMENSION_FIELDS")
    _require(dimensions == {"business_contract": "VIOLATION_CONFIRMED",
                            "fault_kind": "CONTROLLED_BUSINESS_SERVICE_DEFECT",
                            "network_fault": "NOT_PLANNED",
                            "defect_activation": "ACTIVATED_AND_OBSERVED",
                            "technical_attribution": "CONTROLLED_SERVICE_DEFECT_OBSERVED",
                            "research_attribution": "CORRELATIONAL_ONLY",
                            "reproduction": "NOT_TESTED", "agent_exposure": "NOT_APPLICABLE",
                            "agent_fail": "NOT_APPLICABLE", "run_outcome": "COMPLETED",
                            "issuer_authenticity": "NOT_ESTABLISHED"}, "DIMENSION_VALUES")

    cleanup = evidence["cleanup"]
    _fields(cleanup, {"status", "reset_generation", "receipt_count_after_reset", "database_removed",
                      "run_directory_removed"}, "CLEANUP_FIELDS")
    _require(cleanup == {"status": "RESET_AND_REMOVED", "reset_generation": 1,
                         "receipt_count_after_reset": 0, "database_removed": True,
                         "run_directory_removed": True}, "CLEANUP_RESULT")
    _require(type(cleanup["reset_generation"]) is int
             and type(cleanup["receipt_count_after_reset"]) is int
             and type(cleanup["database_removed"]) is bool
             and type(cleanup["run_directory_removed"]) is bool, "CLEANUP_TYPES")
    _validate_events(evidence["events"], run, evidence["authority_before"],
                     evidence["authority_after"], oracle, defect, cleanup)

    budget = evidence["budget"]
    _fields(budget, {"provider_http_calls", "tokens", "provider_cost_cny", "non_test_trials",
                     "business_steps"}, "BUDGET_FIELDS")
    _require(budget == {"provider_http_calls": 0, "tokens": 0, "provider_cost_cny": 0.0,
                        "non_test_trials": 2, "business_steps": 14}, "BUDGET_RESULT")
    _require(all(type(budget[key]) is int for key in
                 ("provider_http_calls", "tokens", "non_test_trials", "business_steps"))
             and type(budget["provider_cost_cny"]) is float, "BUDGET_TYPES")
    _require(evidence["limitations"] == LIMITATIONS, "LIMITATIONS")


def issue(evidence: dict) -> bytes:
    validate_evidence(evidence)
    document = {"schema_version": SCHEMA_VERSION, "evidence": evidence,
                "content_sha256": digest(evidence)}
    return canonical(document)


def verify_content(document: dict) -> dict:
    _fields(document, {"schema_version", "evidence", "content_sha256"}, "DOCUMENT_FIELDS")
    _require(document["schema_version"] == SCHEMA_VERSION, "SCHEMA_VERSION")
    _require(_is_sha256(document["content_sha256"])
             and document["content_sha256"] == digest(document["evidence"]), "CONTENT_DIGEST")
    validate_evidence(document["evidence"])
    return {"status": "CONTENT_VERIFIED", "verdict": "VIOLATION_CONFIRMED", "reasons": []}


def verify_bytes(raw: bytes, expected_sha256: str | None = None) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= 1_000_000, "DOCUMENT_SIZE")
    actual = hashlib.sha256(raw).hexdigest()
    document = _strict_json(raw)
    if expected_sha256 is not None:
        _require(_is_sha256(expected_sha256), "EXTERNAL_ANCHOR_FORMAT")
        _require(actual == expected_sha256, "EXTERNAL_ANCHOR_MISMATCH")
    _require(raw == canonical(document), "DOCUMENT_NOT_CANONICAL")
    result = verify_content(document)
    if expected_sha256 is None:
        return {"status": "UNANCHORED_INCONCLUSIVE", "verdict": "NOT_PROVEN",
                "reasons": ["EXTERNAL_ANCHOR_MISSING"], "exit_code": 2}
    return {**result, "status": "VERIFIED_ANCHORED", "exit_code": 0,
            "external_sha256": actual, "issuer_authenticity": "NOT_ESTABLISHED"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify an RPF-50 violation Witness offline.")
    parser.add_argument("witness_path")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        raw = Path(args.witness_path).read_bytes()
        result = verify_bytes(raw, args.expected_sha256)
    except WitnessRejected as error:
        result = {"status": "REJECTED", "verdict": "NOT_PROVEN", "code": error.code,
                  "exit_code": 3}
    except OSError:
        result = {"status": "REJECTED", "verdict": "NOT_PROVEN", "code": "FILE_UNAVAILABLE",
                  "exit_code": 3}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
