"""RPF-106 ledger and domain ports in a fresh RPF-108 owner."""
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import uuid4

from . import pge_r106_contracts as inner, pge_r106_oracle as oracle
from .pge_r106_ledger import Ledger
from .product_local_ports import OpsPort, OrderPort
from .product_sdk_target import safe
from .sdk_presend_contracts import REPO, check, strict, sync_dir

ROOT = REPO / ".local" / "rpf-108"


def fresh():
    for path in (ROOT.parent, ROOT):
        try:
            safe(path, directory=True)
        except FileNotFoundError:
            safe(path, directory=True, absent=True).mkdir()
            sync_dir(path.parent)
    owner = safe(ROOT / uuid4().hex, directory=True, absent=True)
    owner.mkdir()
    sync_dir(ROOT)
    return owner


def readback(owner, contract):
    identity = inner.binding(contract)
    check(owner == ROOT / identity["owner"], "AUTHORITY_OWNER")
    path = safe(owner / identity["db_member"])
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        check(db.execute("PRAGMA query_only").fetchone() == (1,), "QUERY_ONLY")
        db.execute("BEGIN")
        check(db.execute("SELECT environment FROM identity LIMIT 2").fetchall() == [(identity["environment_id"],)],
              "AUTHORITY_ENVIRONMENT")
        rows = db.execute("SELECT id,payload FROM state LIMIT 2").fetchall()
        receipts = db.execute("SELECT operation,payload FROM receipts LIMIT 2").fetchall()
        check(len(rows) == 1 and rows[0][0] == 1 and len(receipts) <= 1 and
              all(op == identity["operation_id"] for op, _ in receipts), "AUTHORITY_ROWS")
        key = "order" if identity["domain"] == "order" else "config"
        snapshot = {key: strict(rows[0][1]), "receipts": [strict(value) for _, value in receipts]}
    return {"schema": "rpf106-authority-v1", "mode": "SQLITE_RO_QUERY_ONLY", "binding": identity,
            "snapshot": snapshot}


def verdict(contract, before, after, intent):
    result = oracle.evaluate(contract, before, after)
    check(result["contract_outcome"] == inner.SUCCESS and len(after["snapshot"]["receipts"]) == 1, "ORACLE_EFFECT")
    lost = contract["experiment"]["fault"] == inner.FAULT
    return {"schema": "rpf106-oracle-v1", "binding": inner.binding(contract), "outcome": inner.SUCCESS,
            "fault": inner.faults(contract, triggered=lost, observed=lost), "intent_sha256": intent,
            "authority_before_sha256": inner.digest(before), "authority_after_sha256": inner.digest(after),
            "receipt_sha256": inner.digest(after["snapshot"]["receipts"][0]), "agent_outcome": "NOT_RUN",
            "platform_outcome": "LOCAL_TRANSACTION_OBSERVED", "verification": "CONTENT_CHECKED_LOCAL",
            "issuer": "NOT_ESTABLISHED"}


class Adapter:
    def __init__(self, owner, source, *, fault=None):
        check(isinstance(owner, Path) and owner.parent == ROOT and inner.hex_id(owner.name, 32), "OWNER_SCOPE")
        self.owner = safe(owner, directory=True)
        self.fault = fault
        self.frozen = inner.freeze(source, uuid4().hex, owner.name, inner.source_identity())
        self.ledger = Ledger(owner, self.frozen, self.inject)

    def inject(self, phase):
        if self.fault == phase:
            raise OSError("INJECTED_" + phase)

    def apply(self, choice):
        with self.ledger.lock:
            view = self.ledger.snapshot()
            offered = inner.proposal(self.frozen, view, choice, uuid4().hex)
            decision = inner.gate(self.frozen, view, offered)
            try:
                if decision["reason"] == "EXPLICIT_STOP":
                    self.ledger.append("STOPPED", {"reason": "EXPLICIT_STOP", "proposal": offered, "decision": decision})
                    return None
                check(decision["status"] == "ACCEPT", "BUSINESS_ADMISSION")
                remaining = {key: view["remaining"][key] - inner.COST[key] for key in inner.LIMIT}
                self.ledger.append("CLAIMED", {"proposal": offered, "decision": decision, "remaining": remaining})
                contract = self.frozen["catalog"][choice]
                scope = inner.binding(contract)
                path = safe(self.owner / scope["db_member"], absent=True)
                port = (OrderPort if scope["domain"] == "order" else OpsPort)(path, contract)
                sync_dir(self.owner)
                before = readback(self.owner, contract)
                self.ledger.append("AUTHORITY_BEFORE", before)
                intent = self.ledger.append("WRITE_INTENT", scope)
                self.ledger.confirm()
                port.write_once()
                self.inject("AFTER_SQLITE_COMMIT")
                self.ledger.append("WRITE_COMMIT", scope)
                if choice != inner.SEED:
                    self.ledger.append("UNKNOWN", scope)
                after = readback(self.owner, contract)
                self.ledger.append("AUTHORITY_AFTER", after)
                result = verdict(contract, before, readback(self.owner, contract), intent)
                self.ledger.append("VERIFIED", {"verdict": result, "feedback_sha256": inner.digest(result)})
                if choice != inner.SEED:
                    self.ledger.append("STOPPED", {"reason": "UNKNOWN_TERMINAL"})
                return result
            except oracle.READ_FAILURES:
                self.ledger.poison = True
                raise
