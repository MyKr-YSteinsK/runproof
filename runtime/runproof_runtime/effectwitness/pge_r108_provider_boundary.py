"""Durable reservation and one-use send intent for a simulated transport."""
from copy import deepcopy
from threading import RLock

from . import pge_r106_contracts as inner, pge_r106_oracle as oracle
from . import pge_r108_candidate as candidate, pge_r108_contracts as c
from .pge_r107_contracts import project
from .pge_r107_host import Journal, application
from .sdk_presend_contracts import check, sha


class Boundary:
    def __init__(self, adapter, seed, *, fault=None, strategy="SIMULATED_EXPLORER"):
        self.adapter = adapter
        adapter.ledger.confirm()
        view = adapter.ledger.snapshot()
        self.contract = c.freeze(adapter.frozen["scope"], view, project(adapter.frozen, view, seed), strategy)
        self.journal = Journal(adapter.owner / "presend.jsonl")
        self.lock = RLock()
        self.phase = "READY"
        self.permit = None
        self.request_sha = None
        self._selected = None
        self.fault = fault
        try:
            self.journal.append("OPEN", {"contract": self.contract})
        except oracle.READ_FAILURES:
            self.journal.close()
            raise

    def close(self):
        with self.lock:
            self.phase = "CLOSED"
            self.permit = None
            self.journal.close()

    def inject(self, stage):
        if self.fault == stage:
            raise OSError("INJECTED_" + stage)

    def reserve(self, raw):
        with self.lock, self.adapter.ledger.lock:
            try:
                check(type(raw) is bytes and 0 < len(raw) <= c.LIMIT and self.phase != "CLOSED", "INGRESS_BOUND")
                self.adapter.ledger.confirm()
                self.journal.append("MODEL_POST_RECEIVED", application(raw))
                view = self.adapter.ledger.snapshot()
                if self.phase != "READY" or view["latched"] or raw != c.request(self.contract) or (
                        inner.digest(view) != self.contract["seed_view_sha256"]):
                    reason = "UNKNOWN_LATCH" if view["latched"] and self.phase == "UNKNOWN" else "NOT_ADMITTED"
                    self.journal.append("DENIED", {"reason": reason, "ledger_tip": view["tip"]})
                    if self.phase == "READY":
                        self.phase = "UNCERTAIN"
                    return None
                request_sha = sha(raw)
                self.inject("BEFORE_RESERVE")
                self.journal.append("PROVIDER_RESERVE", {"request_sha256": request_sha, "ledger_tip": view["tip"]})
                self.inject("AFTER_RESERVE")
                self.phase = "RESERVED"
                self.permit, self.request_sha = object(), request_sha
                return self.permit
            except oracle.READ_FAILURES:
                self.phase = "UNCERTAIN"
                self.permit = None
                return None

    def simulate(self, permit, response_bytes, elapsed_ms):
        with self.lock, self.adapter.ledger.lock:
            check(self.phase == "RESERVED" and self.permit is not None and self.permit is permit, "SEND_PERMIT")
            self.permit = None
            try:
                self.adapter.ledger.confirm()
                view = self.adapter.ledger.snapshot()
                check(not view["latched"] and inner.digest(view) == self.contract["seed_view_sha256"], "SEND_VIEW")
                self.journal.append("SEND_INTENT", {"request_sha256": self.request_sha, "mode": "SIMULATED_ONLY"})
                self.inject("AFTER_SEND_INTENT")
                self.journal.append("SIMULATED_SEND_ENTRY", {"request_sha256": self.request_sha})
                self.inject("AFTER_SIMULATED_ENTRY")
                selected = candidate.parse(response_bytes, self.request_sha, elapsed_ms)
                check(self.contract["strategy"] != "FIXED_ORDER_B0" or selected["candidate_id"] == inner.ORDER,
                      "FIXED_ORDER_B0")
                self.journal.append("SIMULATED_RESPONSE", {"application": application(response_bytes),
                                                           "elapsed_ms": elapsed_ms})
                self._selected = selected
                self.phase = "CALLBACK"
                return deepcopy(selected)
            except oracle.READ_FAILURES:
                self.phase = "UNCERTAIN"
                raise

    def apply_callback(self, raw):
        with self.lock, self.adapter.ledger.lock:
            check(self.phase == "CALLBACK", "CALLBACK_PHASE")
            try:
                self.adapter.ledger.confirm()
                view = self.adapter.ledger.snapshot()
                check(not view["latched"] and inner.digest(view) == self.contract["seed_view_sha256"],
                      "CALLBACK_VIEW")
                choice = candidate.callback(raw, self._selected)
                self.journal.append("TOOL_CALLBACK", {"application": application(raw), "selected": self._selected})
                result = self.adapter.apply(choice)
                state = self.adapter.ledger.snapshot()
                if choice == inner.STOP:
                    check(state["phase"] == "STOPPED" and not state["latched"], "STOP_TERMINAL")
                    self.phase = "STOPPED"
                else:
                    check(state["phase"] == "STOPPED" and state["latched"], "UNKNOWN_TERMINAL")
                    self.inject("BEFORE_OUTER_UNKNOWN")
                    self.phase = "UNKNOWN"
                self.journal.append(self.phase, {"ledger_tip": state["tip"], "candidate_id": choice})
                return result
            except oracle.READ_FAILURES:
                self.phase = "UNCERTAIN"
                raise
