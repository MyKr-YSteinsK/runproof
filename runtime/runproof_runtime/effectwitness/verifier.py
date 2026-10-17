"""Order-domain oracle over authenticated observations from the authority port."""

from __future__ import annotations

from ..models import RuntimeFailure
from .contracts import FrozenContracts, digest, VERIFIER_ID
from .orders import AuthorityReader, AuthoritySnapshot


class OrderEffectVerifier:
    def __init__(self, contracts: FrozenContracts, reader: AuthorityReader):
        contracts.validate()
        self.contracts, self.reader = contracts, reader

    def __call__(self, before: AuthoritySnapshot | None, after: AuthoritySnapshot | None) -> dict:
        result = {"contract_outcome": "INCONCLUSIVE", "verifier_id": VERIFIER_ID,
                  "verifier_version": "1", "violated_rules": [], "evidence_gaps": []}
        try:
            b, a = self.reader.validate(before), self.reader.validate(after)
        except (RuntimeFailure, KeyError, TypeError, ValueError) as failure:
            result["evidence_gaps"] = [getattr(failure, "code", "AUTHORITY_MALFORMED")]
            return result
        e = self.contracts.effect
        initial = {"order_id": e["order_id"], "paid_minor": e["amount_minor"],
                   "refunded_minor": 0, "currency": e["currency"], "status": "PAID", "revision": 0}
        if b["order"] != initial or b["receipts"]:
            result["evidence_gaps"] = ["INITIAL_PRECONDITION_NOT_ESTABLISHED"]
            return result
        expected = {**initial, "refunded_minor": e["amount_minor"], "status": "REFUNDED", "revision": 1}
        violated = []
        if a["order"] != expected:
            violated.append("EXACTLY_ONE_FULL_REFUND_STATE")
        receipts = a["receipts"]
        if len(receipts) != 1:
            violated.append("EXACTLY_ONE_RECEIPT")
        else:
            expected_receipt = {"operation_id": e["operation_id"], "order_id": e["order_id"],
                                "amount_minor": e["amount_minor"], "currency": e["currency"],
                                "status": "COMMITTED", "committed_revision": 1,
                                "receipt_id": "receipt-" + digest({
                                    "environment": self.contracts.experiment["environment_id"],
                                    "operation_id": e["operation_id"]})[:24]}
            if receipts[0] != expected_receipt:
                violated.append("RECEIPT_BOUND_TO_FROZEN_OPERATION")
        result.update(contract_outcome="VIOLATION_CONFIRMED" if violated else "CONTRACT_SATISFIED_IN_RUN",
                      violated_rules=violated,
                      before=before.public(), after=after.public(), receipt_hash=digest(receipts),
                      state_diff={k: {"before": b["order"].get(k), "after": a["order"].get(k)}
                                  for k in set(b["order"]) | set(a["order"])
                                  if b["order"].get(k) != a["order"].get(k)})
        return result
