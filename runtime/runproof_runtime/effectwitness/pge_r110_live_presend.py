"""Exclusive durable send ticket. An old owner has no writable reopen path."""
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from time import monotonic_ns
from uuid import uuid4

from . import pge_r106_contracts as inner, pge_r110_live_contracts as c
from .pge_r107_host import Journal
from .pge_r110_oracle import ROOT
from .product_sdk_target import safe
from .sdk_presend_contracts import check, sha


class Presend:
    def __init__(self, owner, contract, *, hook=None):
        check(owner.parent == ROOT and inner.hex_id(owner.name, 32)
              and owner.name == contract["scope"]["owner"], "LIVE_OWNER")
        self.contract = deepcopy(contract)
        self.journal = Journal(safe(owner, directory=True) / "presend-live.jsonl")
        self.lock = RLock()
        self.phase = "READY"
        self._permit = None
        self._ticket = None
        self._selection_sha = None
        self.hook = hook
        try:
            self.journal.append("OPEN", self.contract)
        except BaseException:
            self.close()
            raise

    def close(self):
        with self.lock:
            self._permit = None
            self.phase = "CLOSED"
            self.journal.close()

    def event(self, kind, body):
        if self.hook:
            self.hook("BEFORE_" + kind)
        self.journal.append(kind, body)
        if self.hook:
            self.hook("AFTER_" + kind)

    def uncertain(self, reason):
        with self.lock:
            self._permit = None
            if self.phase != "UNCERTAIN":
                self.phase = "UNCERTAIN"
                if not self.journal.poison:
                    self.journal.append("UNCERTAIN", {"stage": reason})

    def reserve(self, raw, view, *, terminal_probe=False):
        with self.lock:
            check(self.phase != "CLOSED" and type(raw) is bytes and 0 < len(raw) <= c.BODY_CAP, "LIVE_INGRESS")
            try:
                check(not terminal_probe or self.phase in ("UNKNOWN", "STOPPED"), "PROBE_PHASE")
                self.event("LOCAL_TERMINAL_PROBE" if terminal_probe else "HOST_REQUEST_READY",
                           {"request_sha256": sha(raw), "size": len(raw)})
                if (self.phase != "READY" or self.contract["max_requests"] != 1 or view["latched"]
                    or inner.digest(view) != self.contract["seed_view_sha256"] or raw != c.request(self.contract)):
                    self.event("DENIED", {"phase": self.phase, "ledger_tip": view["tip"]})
                    if self.phase == "READY":
                        self.phase = "UNCERTAIN"
                    return None
                self._ticket = {"ticket_id": uuid4().hex, "request_sha256": sha(raw),
                                "owner": self.contract["scope"]["owner"], "run_id": self.contract["scope"]["run_id"],
                                "seed_tip": view["tip"]}
                self.event("PROVIDER_RESERVE", self._ticket)
                self.phase, self._permit = "RESERVED", object()
                return self._permit
            except (OSError, ValueError, KeyError, TypeError):
                self.uncertain("RESERVE")
                raise

    def enter(self, permit, raw, view, mode):
        with self.lock:
            check(self.phase == "RESERVED" and self._permit is not None and self._permit is permit, "LIVE_PERMIT")
            self._permit = None
            try:
                check(self.contract["kind"] == mode and not view["latched"]
                      and inner.digest(view) == self.contract["seed_view_sha256"]
                      and raw == c.request(self.contract), "SEND_BINDING")
                self.event("SEND_INTENT", self._ticket)
                entry = {"ticket": self._ticket, "kind": mode, "entered_ns": monotonic_ns(),
                         "entered_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
                if mode == c.NATIVE:
                    approval = self.contract["approval"]
                    c.validate_budget(approval["budget"], self.contract["scope"]["source_git_sha"],
                                      approval["github_run_id"], now=c.utc(entry["entered_utc"]))
                self.event("SEND_ENTRY" if mode == c.NATIVE else "STUB_SEND_ENTRY", entry)
                self.phase = "ENTERED"
                return deepcopy(entry)
            except (OSError, ValueError, KeyError, TypeError):
                self.uncertain("ENTRY")
                raise

    def observe(self, receipt):
        with self.lock:
            check(self.phase == "ENTERED" and receipt["ticket"] == self._ticket, "RETURN_PHASE")
            self.event("HTTP_RESPONSE" if self.contract["kind"] == c.NATIVE else "STUB_RESPONSE", receipt)
            self.phase = "RESPONSE"

    def select(self, selected):
        with self.lock:
            check(self.phase == "RESPONSE", "SELECTION_PHASE")
            self.event("TOOL_SELECTION", selected)
            self._selection_sha = inner.digest(selected)
            self.phase = "BUSINESS_PENDING"

    def baseline(self):
        with self.lock:
            check(self.phase == "READY" and self.contract["kind"] == c.B0, "BASELINE_PHASE")
            self.event("BASELINE_CHOICE", {"candidate_id": c.CHOICES[0]})
            self.phase = "BUSINESS_PENDING"

    def finish(self, choice, view):
        with self.lock:
            check(self.phase == "BUSINESS_PENDING" and view["phase"] == "STOPPED"
                  and view["latched"] is (choice != inner.STOP), "TERMINAL_PHASE")
            phase = "STOPPED" if choice == inner.STOP else "UNKNOWN"
            self.event(phase, {"candidate_id": choice, "ledger_tip": view["tip"],
                               "selection_sha256": self._selection_sha})
            self.phase = phase
