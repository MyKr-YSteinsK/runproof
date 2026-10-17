"""Pure order-effect rules shared by live authenticated reads and offline Witness checks."""
from __future__ import annotations

import hashlib
import json

VERIFIER_ID = "rpf41-order-effect-verifier"
VERIFIER_VERSION = "1"


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def evaluate_order_effect(effect: dict, environment_id: str, before: dict, after: dict) -> dict:
    """Recompute one full-refund contract result from already validated authority data."""
    result = {"contract_outcome": "INCONCLUSIVE", "verifier_id": VERIFIER_ID,
              "verifier_version": VERIFIER_VERSION, "violated_rules": [], "evidence_gaps": []}
    initial = {"order_id": effect["order_id"], "paid_minor": effect["amount_minor"],
               "refunded_minor": 0, "currency": effect["currency"], "status": "PAID", "revision": 0}
    if before["order"] != initial or before["receipts"]:
        result["evidence_gaps"] = ["INITIAL_PRECONDITION_NOT_ESTABLISHED"]
        return result
    expected = {**initial, "refunded_minor": effect["amount_minor"],
                "status": "REFUNDED", "revision": 1}
    violated = []
    if after["order"] != expected:
        violated.append("EXACTLY_ONE_FULL_REFUND_STATE")
    receipts = after["receipts"]
    if len(receipts) != 1:
        violated.append("EXACTLY_ONE_RECEIPT")
    else:
        expected_receipt = {"operation_id": effect["operation_id"], "order_id": effect["order_id"],
                            "amount_minor": effect["amount_minor"], "currency": effect["currency"],
                            "status": "COMMITTED", "committed_revision": 1,
                            "receipt_id": "receipt-" + digest({"environment": environment_id,
                                                                "operation_id": effect["operation_id"]})[:24]}
        if receipts[0] != expected_receipt:
            violated.append("RECEIPT_BOUND_TO_FROZEN_OPERATION")
    result.update(contract_outcome="VIOLATION_CONFIRMED" if violated else "CONTRACT_SATISFIED_IN_RUN",
                  violated_rules=violated,
                  receipt_hash=digest(receipts),
                  state_diff={key: {"before": before["order"].get(key), "after": after["order"].get(key)}
                              for key in set(before["order"]) | set(after["order"])
                              if before["order"].get(key) != after["order"].get(key)})
    return result
