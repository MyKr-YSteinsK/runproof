"""Trusted in-process adapter. Only Controller.apply can admit a business write."""
from base64 import b64encode
from copy import deepcopy
import os
from threading import RLock

from . import pge_r106_contracts as inner, pge_r106_oracle as oracle
from . import pge_r107_contracts as c, pge_r107_model_loopback as model
from .product_sdk_target import safe
from .sdk_presend_contracts import canonical, check, sha, sync_dir


def application(raw):
    return {"sha256": sha(raw), "size": len(raw), "base64": b64encode(raw).decode("ascii")}


class Journal:
    def __init__(self, path):
        self.path = safe(path, absent=True)
        self.poison = False
        self.raw = b""
        self.events = []
        self.stream = self.path.open("xb")
        try:
            sync_dir(path.parent)
        except OSError:
            self.stream.close()
            raise

    def close(self):
        self.stream.close()

    def append(self, kind, body):
        try:
            with safe(self.path).open("rb") as persisted:
                check(not self.poison and len(self.events) < c.MAX_EVENTS
                      and persisted.read(len(self.raw) + 1) == self.raw, "JOURNAL_UNAVAILABLE")
            core = {"revision": len(self.events) + 1, "previous": self.events[-1]["sha256"] if self.events
                    else "0" * 64, "kind": kind, "body": body}
            entry = {**core, "sha256": inner.digest(core)}
            raw = canonical(entry) + b"\n"
            check(self.stream.write(raw) == len(raw), "JOURNAL_WRITE")
            self.stream.flush()
            os.fsync(self.stream.fileno())
            self.raw += raw
            self.events.append(deepcopy(entry))
        except (OSError, ValueError):
            self.poison = True
            raise


class Host:
    def __init__(self, controller, frozen, journal):
        self.controller, self.frozen, self.journal = controller, deepcopy(frozen), journal
        self.lock = RLock()
        self.failure = None
        self.model_reserved = False
        self.called = False
        self.callback = None
        self.tool_result = None
        journal.append("OPEN", {"frozen_sha256": inner.digest(frozen)})

    def trusted_seed(self, view):
        self.controller.ledger.confirm()
        check(self.controller.frozen["scope"] == self.frozen["inner_scope"], "SEED_SCOPE")
        report = oracle.inspect(self.frozen["inner_scope"]["owner"])
        check(report["scope"] == self.frozen["inner_scope"]
              and report["claimed"] == [inner.SEED], "SEED_SCOPE")
        verdict = report["verified"][inner.SEED]
        check(canonical(c.project(self.controller.frozen, view, verdict)) == canonical(self.frozen["feedback"])
              and inner.digest(self.controller.frozen) == self.frozen["inner_sha256"], "SEED_FEEDBACK")

    def reply(self, kind, status, value, **facts):
        self.journal.append(kind, {"status": status, "application": application(canonical(value)), **facts})
        return status, value

    def handle(self, path, raw):
        with self.lock, self.controller.ledger.lock:
            try:
                return self._handle(path, raw)
            except oracle.READ_FAILURES:
                self.failure = "PLATFORM_OR_ADMISSION_ERROR"
                self.journal.poison = True
                return 400, {"error": {"message": "LOCAL_GUARD_REJECTED", "type": "guard_error"}}

    def _handle(self, path, raw):
        check(not self.journal.poison and self.failure is None and path in (model.MODEL_PATH, model.TOOL_PATH)
              and 0 < len(raw) <= c.MAX_HTTP, "INGRESS")
        self.journal.append("RECEIVED", {"route": path, "application": application(raw)})
        self.controller.ledger.confirm()
        view = self.controller.ledger.snapshot()
        if view["latched"] or view["phase"] == "STOPPED":
            echoed = False
            if path == model.MODEL_PATH and self.tool_result is not None:
                try:
                    model.validate_request(raw, self.frozen["feedback"], callback=self.callback,
                                           tool_result=self.tool_result)
                    echoed = True
                except oracle.READ_FAILURES:
                    pass
            return self.reply("DENIED", 409, model.denial(), sdk_echo=echoed, ledger_tip=view["tip"],
                              durable_latch=self.controller.ledger.state["latched"])
        self.trusted_seed(view)
        if path == model.MODEL_PATH:
            check(not self.model_reserved and not self.called, "MODEL_ALREADY_RESERVED")
            model.validate_request(raw, self.frozen["feedback"])
            self.journal.append("MODEL_RESERVE", {"request_sha256": sha(raw), "ledger_tip": view["tip"]})
            self.model_reserved = True
            return self.reply("SCRIPT_RESPONSE", 200, model.response(self.frozen))

        check(self.model_reserved and not self.called, "CALLBACK_SEQUENCE")
        call = c.tool_request(self.frozen["tool_call_id"], c.SELECTIONS[self.frozen["policy"]])
        candidate = c.validate_tool(raw, call)
        self.called = True
        offered = self.controller.proposal(candidate)
        decision = self.controller.evaluate(offered)
        check(decision["status"] == "ACCEPT" or (candidate == inner.STOP
              and decision["reason"] == "EXPLICIT_STOP"), "HOST_ADMISSION")
        self.journal.append("HOST_DECISION", {"proposal": offered, "decision": decision})
        result = self.controller.apply(offered, decision)
        if candidate == inner.STOP:
            check(result["reason"] == "EXPLICIT_STOP", "HOST_STOP")
            self.callback, self.tool_result = call, dict(c.STOPPED)
            return self.reply("TOOL_RESULT", 200, self.tool_result, ledger_tip=self.controller.ledger.snapshot()["tip"],
                              reconciliation="NOT_APPLICABLE", feedback_sha256=view["feedback_sha256"])
        check(result["execution"] == "VERIFIED" and result["tool_outcome"] == "UNKNOWN_OUTCOME",
              "CONTINUATION_UNCERTAIN")
        observed = self.controller.reconcile(result["oracle"]["binding"])
        check(observed["outcome"] == "COMMITTED", "RECONCILIATION_UNCERTAIN")
        report = self.controller.ledger.snapshot()
        check(report["latched"] and report["phase"] == "STOPPED", "NO_DURABLE_LATCH")
        self.callback, self.tool_result = call, dict(c.UNKNOWN)
        return self.reply("TOOL_RESULT", 200, self.tool_result, ledger_tip=report["tip"],
                          reconciliation=observed["outcome"], feedback_sha256=result["feedback_sha256"])
