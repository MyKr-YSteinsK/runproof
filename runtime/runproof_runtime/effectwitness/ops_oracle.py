"""Pure release/config rules; no executor, database, provider or network imports."""
from .effect_oracle import digest

VERIFIER_ID = "rpf44-ops-effect-verifier"


def initial_state(effect):
    return {"config_id": effect["config_id"], "release": "release-v1", "revision": 0,
            "effect_count": 0, "operation_id": None, "dependency": "READY"}


def expected_receipt(effect, environment_id):
    return {"operation_id": effect["operation_id"], "config_id": effect["config_id"],
            "release": "release-v2", "revision": 1, "effect_count": 1, "status": "APPLIED",
            "receipt_id": "receipt-" + digest({"environment": environment_id,
                                                "operation_id": effect["operation_id"]})[:24]}


def evaluate_ops_effect(effect, environment_id, before, after):
    result = {"verifier_id": VERIFIER_ID, "verifier_version": "1",
              "contract_outcome": "INCONCLUSIVE", "violated_rules": [], "evidence_gaps": []}
    if not before or not after:
        return {**result, "evidence_gaps": ["AUTHORITY_EVIDENCE_MISSING"]}
    initial = initial_state(effect)
    if before["config"] != initial or before["receipts"]:
        return {**result, "evidence_gaps": ["OPS_INITIAL_PRECONDITION_NOT_ESTABLISHED"]}
    expected = {**initial, "release": "release-v2", "revision": 1, "effect_count": 1,
                "operation_id": effect["operation_id"]}
    violations = []
    if after["config"] != expected:
        violations.append("READY_DEPENDENCY_EXACTLY_ONE_CONFIG_TRANSITION")
    if len(after["receipts"]) != 1:
        violations.append("EXACTLY_ONE_OPS_RECEIPT")
    elif after["receipts"][0] != expected_receipt(effect, environment_id):
        violations.append("OPS_RECEIPT_BOUND_TO_FROZEN_OPERATION")
    return {**result, "contract_outcome": "VIOLATION_CONFIRMED" if violations else
            "CONTRACT_SATISFIED_IN_RUN", "violated_rules": violations,
            "receipt_hash": digest(after["receipts"]),
            "state_diff": {k: {"before": initial[k], "after": after["config"].get(k)}
                           for k in initial if initial[k] != after["config"].get(k)}}
