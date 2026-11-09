"""Trusted same-run consumer of pure decisions and independent Oracle receipts."""
from copy import deepcopy
from uuid import uuid4

from . import pge_r106_contracts as c, pge_r106_oracle as oracle
from .pge_r106_authority import ROOT, owner_path, readback
from .pge_r106_ledger import Ledger
from .pge_r106_targets import Target
from .product_sdk_target import safe
from .sdk_presend_contracts import canonical, check, strict, sync_dir

FAULTS = {None, "WRITE_INTENT", "AFTER_SQLITE_COMMIT", "UNKNOWN", "AUTHORITY_AFTER", "ORACLE_VERDICT"}


class Controller:
    def __init__(self, source, *, owner_id=None, failure=None):
        check(failure in FAULTS, "FAULT_SCOPE")
        self.failure = failure
        safe(ROOT, directory=True)
        self.owner_id = owner_id if owner_id is not None else uuid4().hex
        self.owner = safe(owner_path(self.owner_id), directory=True, absent=True)
        self.frozen = c.freeze(source, uuid4().hex, self.owner_id, c.source_identity())
        self.owner.mkdir()
        sync_dir(ROOT)
        self.ledger = Ledger(self.owner, self.frozen, self._inject)
        self.target = Target(self.owner, self.ledger)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.ledger.close()

    def _inject(self, where):
        if self.failure == where:
            raise OSError("INJECTED_FAILURE")

    def proposal(self, candidate, nonce=None):
        return c.proposal(self.frozen, self.ledger.snapshot(), candidate, nonce or uuid4().hex)

    def evaluate(self, offered):
        return c.gate(self.frozen, self.ledger.snapshot(), offered)

    def apply(self, offered, decision):
        """Recheck under the writer lock; neither proposal nor decision is a permit."""
        with self.ledger.lock:
            try:
                offered = strict(canonical(offered))
                supplied = canonical(decision)
            except (ValueError, TypeError, RecursionError):
                return {"execution": "NOT_RUN", "reason": "INPUT_ENCODING"}
            current = self.ledger.snapshot()
            actual = c.gate(self.frozen, current, offered)
            if supplied != canonical(actual):
                return {"execution": "NOT_RUN", "reason": "DECISION_CHANGED", "admission": actual}
            if actual["status"] != "ACCEPT" and actual["reason"] != "EXPLICIT_STOP":
                return {"execution": "NOT_RUN", "reason": actual["reason"], "admission": actual}
            attempted = False
            try:
                if actual["reason"] == "EXPLICIT_STOP":
                    self.ledger.append("STOPPED", {"reason": "EXPLICIT_STOP", "proposal": offered,
                                                   "decision": actual})
                    return {"execution": "NOT_RUN", "reason": "EXPLICIT_STOP", "admission": actual}
                remaining = {key: current["remaining"][key] - actual["requested_debit"][key] for key in c.LIMIT}
                self.ledger.append("CLAIMED", {"proposal": offered, "decision": actual, "remaining": remaining})
                contract = self.frozen["catalog"][offered["candidate_id"]]
                identity = c.binding(contract)
                self.target.prepare(contract)
                before = readback(self.owner, contract)
                check(before["snapshot"]["receipts"] == [], "PREEXISTING_RECEIPT")
                self.ledger.append("AUTHORITY_BEFORE", before)
                self.ledger.append("WRITE_INTENT", identity)
                permit = self.target.arm(contract)
                attempted = True
                self.target.apply(contract, permit)
                self._inject("AFTER_SQLITE_COMMIT")
                self.ledger.append("WRITE_COMMIT", identity)
                lost = contract["experiment"]["fault"] == c.FAULT
                if lost:
                    self.ledger.append("UNKNOWN", identity)
                self._inject("AUTHORITY_AFTER")
                self.ledger.append("AUTHORITY_AFTER", readback(self.owner, contract))
                _, rows = self.ledger.persisted()
                self._inject("ORACLE_VERDICT")
                verdict = oracle.verify_round(self.owner, contract, rows)
                pin = c.digest(verdict)
                self.ledger.append("VERIFIED", {"verdict": verdict, "feedback_sha256": pin})
                if lost:
                    self.ledger.append("STOPPED", {"reason": "UNKNOWN_TERMINAL"})
                return {"execution": "VERIFIED", "admission": actual, "feedback_sha256": pin,
                        "tool_outcome": "UNKNOWN_OUTCOME" if lost else "RETURNED",
                        "oracle": deepcopy(verdict)}
            except oracle.READ_FAILURES:
                self.ledger.poison = True
                return {"execution": "INCONCLUSIVE", "admission": actual, "writer_attempted": attempted,
                        "reason": "DURABILITY_OR_AUTHORITY_UNAVAILABLE"}

    def reconcile(self, identity):
        with self.ledger.lock:
            check(self.ledger.poison or self.ledger.state["latched"], "RECONCILIATION_NOT_ADMITTED")
            contract = self.frozen["catalog"].get(self.ledger.state["candidate"])
            check(contract is not None and canonical(identity) == canonical(c.binding(contract)),
                  "RECONCILIATION_SCOPE")
            try:
                _, rows = self.ledger.persisted()
            except oracle.READ_FAILURES:
                return {"outcome": "UNAVAILABLE", "authority": None}
            return oracle.reconcile(self.owner, contract, rows)
