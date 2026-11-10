"""Exclusive owner journal and non-reusable Phase A fixture ticket."""
from threading import RLock
from uuid import uuid4

from . import pge_r106_contracts as inner
from . import pge_r110_contracts as c, pge_r110_explorer as explorer, pge_r110_provider as provider
from .pge_r107_host import Journal, application
from .pge_r110_oracle import ROOT
from .product_sdk_target import safe
from .sdk_presend_contracts import check, sha


class Presend:
    def __init__(self, owner, contract, *, fault=None):
        check(owner.parent == ROOT and inner.hex_id(owner.name, 32)
              and owner.name == contract["scope"]["owner"], "PRESEND_OWNER")
        self.journal = Journal(safe(owner, directory=True) / "presend.jsonl")  # O_EXCL arbitrates across processes.
        self.lock = RLock()
        self.contract = contract
        self.fault = fault
        self.phase = "READY"
        self.permit = None
        self.ticket = None
        self.selection = None
        try:
            self.journal.append("OPEN", contract)
        except BaseException:
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

    def mark_uncertain(self):
        self.permit = None
        self.phase = "UNCERTAIN"
        if not self.journal.poison:
            try:
                self.journal.append("UNCERTAIN", {"reason": "INCOMPLETE"})
            except (OSError, ValueError):
                pass

    def reserve(self, request, view):
        with self.lock:
            check(self.phase != "CLOSED" and type(request) is bytes
                  and 0 < len(request) <= c.INPUT_FIXTURE_BYTES, "INGRESS")
            try:
                self.journal.append("MODEL_POST_RECEIVED", application(request))
                if (self.phase != "READY" or self.contract["request_budget"] != 1 or view["latched"]
                    or inner.digest(view) != self.contract["seed_view_sha256"] or request != c.request(self.contract)):
                    self.journal.append("DENIED", {"phase": self.phase, "ledger_tip": view["tip"]})
                    if self.phase == "READY":
                        self.phase = "UNCERTAIN"
                    return None
                self.ticket = {"ticket_id": uuid4().hex, "request_sha256": sha(request),
                               "run_id": self.contract["scope"]["run_id"], "seed_tip": view["tip"]}
                self.inject("BEFORE_RESERVE")
                self.journal.append("PROVIDER_RESERVE", self.ticket)
                self.inject("AFTER_RESERVE")
                self.phase, self.permit = "RESERVED", object()
                return self.permit
            except (OSError, ValueError):
                self.mark_uncertain()
                raise

    def fixture_exchange(self, permit, response, *, status=200, elapsed_ms=1):
        with self.lock:
            check(self.phase == "RESERVED" and self.permit is not None and self.permit is permit, "SEND_PERMIT")
            self.permit = None
            try:
                self.journal.append("SEND_INTENT", self.ticket)
                self.inject("AFTER_SEND_INTENT")
                self.journal.append("FIXTURE_SEND_ENTRY", self.ticket)
                self.inject("AFTER_ENTRY")
                check(type(response) is bytes and 0 < len(response) <= c.MAX_REPLY, "RESPONSE_SIZE")
                request_id = "fixture-request-" + self.ticket["ticket_id"]
                self.journal.append("FIXTURE_RETURN", {"status": status, "elapsed_ms": elapsed_ms,
                                                      "request_id": request_id, "response": application(response)})
                self.selection = provider.parse(response, status, elapsed_ms, request_id)
                self.phase = "SELECTED"
                return self.selection.copy()
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                self.mark_uncertain()
                raise

    def claim_choice(self, raw, view):
        with self.lock:
            try:
                check(not view["latched"] and inner.digest(view) == self.contract["seed_view_sha256"], "CALLBACK_VIEW")
                if self.contract["strategy"] == "FIXED_ORDER_B0":
                    check(self.phase == "READY" and raw is None, "B0_PHASE")
                    choice = c.CHOICES[0]
                    self.journal.append("BASELINE_CHOICE", {"candidate_id": choice})
                else:
                    check(self.phase == "SELECTED", "CALLBACK_PHASE")
                    choice = explorer.validate_callback(raw, self.selection)
                    self.journal.append("TOOL_CALLBACK", {"application": application(raw), "selection": self.selection})
                self.phase = "BUSINESS_PENDING"
                return choice
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                self.mark_uncertain()
                raise

    def finish(self, choice, view):
        with self.lock:
            try:
                check(self.phase == "BUSINESS_PENDING" and view["phase"] == "STOPPED"
                      and view["latched"] is (choice != inner.STOP), "BUSINESS_TERMINAL")
                self.inject("BEFORE_TERMINAL")
                self.phase = "STOPPED" if choice == inner.STOP else "UNKNOWN"
                self.journal.append(self.phase, {"candidate_id": choice, "ledger_tip": view["tip"]})
            except (OSError, ValueError):
                self.mark_uncertain()
                raise
