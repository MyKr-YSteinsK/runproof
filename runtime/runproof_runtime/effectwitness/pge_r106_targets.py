"""Only the controller can arm the one-use writer after the durable intent."""
from contextlib import closing
import sqlite3

from . import pge_r106_contracts as c
from .pge_r106_authority import database
from .product_local_ports import OpsPort, OrderPort
from .sdk_presend_contracts import canonical, check, sync_dir


class Target:
    def __init__(self, owner, ledger):
        self.owner = owner
        self.ledger = ledger
        self.port = None
        self.armed = None
        self.prepared = set()

    def _check(self, contract, phase):
        state = self.ledger.state
        check(not self.ledger.closed and not self.ledger.poison and not state["latched"]
              and state["phase"] == phase
              and canonical(contract) == canonical(state["frozen"]["catalog"].get(state["candidate"])),
              "WRITER_SCOPE")
        self.ledger.confirm()

    def prepare(self, contract):
        with self.ledger.lock:
            self._check(contract, "CLAIMED")
            identity = c.binding(contract)
            check(identity["operation_id"] not in self.prepared, "WRITER_PREPARED")
            self.prepared.add(identity["operation_id"])
            path = database(self.owner, contract, absent=True)
            port = OrderPort if identity["domain"] == "order" else OpsPort
            self.port = port(path, contract)
            sync_dir(path.parent)

    def arm(self, contract):
        with self.ledger.lock:
            self._check(contract, "INTENT")
            check(self.port is not None and self.armed is None, "WRITER_NOT_ARMABLE")
            permit = object()
            self.armed = (permit, self.ledger.state["intent_sha256"], contract["contract_sha256"])
            return permit

    def apply(self, contract, permit):
        with self.ledger.lock:
            self._check(contract, "INTENT")
            check(self.armed is not None and self.armed[0] is permit and self.armed[1:] ==
                  (self.ledger.state["intent_sha256"], contract["contract_sha256"]), "WRITER_PERMIT")
            port = self.port
            self.armed = self.port = None
            path = database(self.owner, contract)
            identity = c.binding(contract)
            with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                check(db.execute("SELECT environment FROM identity LIMIT 2").fetchall() ==
                      [(identity["environment_id"],)] and
                      db.execute("SELECT operation FROM receipts LIMIT 1").fetchone() is None,
                      "WRITE_ENVIRONMENT_OR_RECEIPT")
                updated = db.execute("UPDATE state SET payload=? WHERE id=1 AND payload=?",
                                     (canonical(port.updated()), canonical(port.initial()))).rowcount
                check(updated == 1, "WRITE_PRECONDITION")
                db.execute("INSERT INTO receipts VALUES (?,?)",
                           (identity["operation_id"], canonical(port.receipt())))
