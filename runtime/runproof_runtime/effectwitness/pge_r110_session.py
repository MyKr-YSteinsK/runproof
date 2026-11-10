"""Phase A trusted controller and Provider-0 fixture orchestration."""
from contextlib import closing
import sqlite3
from uuid import uuid4

from . import pge_r106_contracts as inner, pge_r106_ledger as history
from . import pge_r110_contracts as c, pge_r110_explorer as explorer, pge_r110_provider as provider
from .pge_r106_oracle import READ_FAILURES
from .pge_r106_targets import Target
from .pge_r108_controller_adapter import verdict
from .pge_r110_oracle import ROOT, database, fresh, readback
from .pge_r110_presend import Presend
from .product_local_ports import OpsPort, OrderPort
from .product_sdk_target import safe
from .sdk_presend_contracts import canonical, check, sync_dir


class OwnedTarget(Target):
    """Keep RPF-106's arm and intent checks; bind both DB operations to the new root."""
    def prepare(self, contract):
        with self.ledger.lock:
            self._check(contract, "CLAIMED")
            scope = inner.binding(contract)
            check(scope["operation_id"] not in self.prepared, "WRITER_PREPARED")
            self.prepared.add(scope["operation_id"])
            path = database(self.owner, contract, absent=True)
            self.port = (OrderPort if scope["domain"] == "order" else OpsPort)(path, contract)
            sync_dir(path.parent)

    def apply(self, contract, permit):
        with self.ledger.lock:
            self._check(contract, "INTENT")
            check(self.armed is not None and self.armed[0] is permit and self.armed[1:] ==
                  (self.ledger.state["intent_sha256"], contract["contract_sha256"]), "WRITER_PERMIT")
            port = self.port
            self.armed = self.port = None
            scope = inner.binding(contract)
            path = database(self.owner, contract)
            with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=4)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                check(db.execute("SELECT environment FROM identity LIMIT 2").fetchall() ==
                      [(scope["environment_id"],)] and not db.execute("SELECT operation FROM receipts LIMIT 1").fetchone(),
                      "WRITE_SCOPE")
                check(db.execute("UPDATE state SET payload=? WHERE id=1 AND payload=?",
                                 (canonical(port.updated()), canonical(port.initial()))).rowcount == 1,
                      "WRITE_PRECONDITION")
                db.execute("INSERT INTO receipts VALUES (?,?)", (scope["operation_id"], canonical(port.receipt())))


class Controller:
    def __init__(self, owner, source):
        check(owner.parent == ROOT and inner.hex_id(owner.name, 32), "BUSINESS_OWNER")
        self.owner = safe(owner, directory=True)
        self.frozen = inner.freeze(source, uuid4().hex, owner.name, inner.source_identity())
        self.fault = None
        self.ledger = history.Ledger(owner, self.frozen, self.inject)
        self.target = OwnedTarget(owner, self.ledger)

    def inject(self, phase):
        if self.fault == phase:
            raise OSError("INJECTED_" + phase)

    def apply(self, choice):
        with self.ledger.lock:
            view = self.ledger.snapshot()
            offered = inner.proposal(self.frozen, view, choice, uuid4().hex)
            decision = inner.gate(self.frozen, view, offered)
            try:
                if choice == inner.STOP and decision["reason"] == "EXPLICIT_STOP":
                    self.ledger.append("STOPPED", {"reason": "EXPLICIT_STOP", "proposal": offered, "decision": decision})
                    return None
                check(decision["status"] == "ACCEPT", "BUSINESS_GATE")
                remaining = {key: view["remaining"][key] - decision["requested_debit"][key] for key in inner.LIMIT}
                self.ledger.append("CLAIMED", {"proposal": offered, "decision": decision, "remaining": remaining})
                contract = self.frozen["catalog"][choice]
                scope = inner.binding(contract)
                self.target.prepare(contract)
                before = readback(self.owner, contract)
                check(before["snapshot"]["receipts"] == [], "PREEXISTING_RECEIPT")
                self.ledger.append("AUTHORITY_BEFORE", before)
                intent = self.ledger.append("WRITE_INTENT", scope)
                self.target.apply(contract, self.target.arm(contract))
                self.inject("AFTER_SQLITE_COMMIT")
                self.ledger.append("WRITE_COMMIT", scope)
                if choice != inner.SEED:
                    self.ledger.append("UNKNOWN", scope)
                after = readback(self.owner, contract)
                self.ledger.append("AUTHORITY_AFTER", after)
                independent = readback(self.owner, contract)
                check(canonical(after) == canonical(independent), "AUTHORITY_CHANGED")
                result = verdict(contract, before, independent, intent)
                self.ledger.append("VERIFIED", {"verdict": result, "feedback_sha256": inner.digest(result)})
                if choice != inner.SEED:
                    self.ledger.append("STOPPED", {"reason": "UNKNOWN_TERMINAL"})
                return result
            except READ_FAILURES:
                self.ledger.poison = True
                raise


class Session:
    def __init__(self, source, strategy):
        self.owner = fresh()
        self.controller = Controller(self.owner, source)
        try:
            seed = self.controller.apply(inner.SEED)
            contract = c.freeze(self.controller.frozen, self.controller.ledger.snapshot(), seed, strategy)
            self.presend = Presend(self.owner, contract)
        except BaseException:
            self.controller.ledger.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.presend.close()
        self.controller.ledger.close()

    def reserve(self, raw):
        with self.presend.lock, self.controller.ledger.lock:
            self.controller.ledger.confirm()
            return self.presend.reserve(raw, self.controller.ledger.snapshot())

    def exchange(self, permit, response):
        with self.presend.lock, self.controller.ledger.lock:
            try:
                self.controller.ledger.confirm()
                check(inner.digest(self.controller.ledger.snapshot()) == self.presend.contract["seed_view_sha256"],
                      "SEND_VIEW")
            except READ_FAILURES:
                self.presend.mark_uncertain()
                raise
            return self.presend.fixture_exchange(permit, response)

    def select(self, raw):
        with self.presend.lock, self.controller.ledger.lock:
            try:
                self.controller.ledger.confirm()
                choice = self.presend.claim_choice(raw, self.controller.ledger.snapshot())
                self.controller.apply(choice)
                self.presend.finish(choice, self.controller.ledger.snapshot())
            except READ_FAILURES:
                if self.presend.phase != "UNCERTAIN":
                    self.presend.mark_uncertain()
                raise

    def run(self, choice):
        request = c.request(self.presend.contract)
        if self.presend.contract["strategy"] == "FIXED_ORDER_B0":
            check(choice == inner.ORDER, "FIXED_ORDER_B0")
            self.select(None)
        else:
            permit = self.reserve(request)
            check(permit is not None, "FIXTURE_RESERVE")
            selected = self.exchange(permit, provider.fixture(choice, uuid4().hex))
            self.select(explorer.callback(selected))
        check(self.reserve(request) is None, "TERMINAL_RESERVE")
