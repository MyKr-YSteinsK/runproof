"""Task-owned targets with one transaction and independent query-only readback."""
from contextlib import closing
import sqlite3

from .product_local_contracts import canonical, digest, strict
from .ops_oracle import initial_state, expected_receipt


class DomainPort:
    def __init__(self, path, contract):
        self.path, self.contract = path, contract
        self.effect = contract["effect"]
        self.environment = contract["execution"]["environment_id"]
        # Exclusive filesystem creation prevents reusing a prior domain database.
        with path.open("xb"):
            pass
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB NOT NULL)")
            db.execute("CREATE TABLE receipts (operation TEXT PRIMARY KEY, payload BLOB NOT NULL)")
            db.execute("CREATE TABLE identity (environment TEXT PRIMARY KEY)")
            db.execute("INSERT INTO identity VALUES (?)", (self.environment,))
            db.execute("INSERT INTO state VALUES (1, ?)", (canonical(self.initial()),))

    def read(self):
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            if db.execute("SELECT environment FROM identity").fetchall() != [(self.environment,)]:
                raise ValueError("AUTHORITY_IDENTITY_MISMATCH")
            row = db.execute("SELECT payload FROM state WHERE id=1").fetchone()
            receipts = [strict(raw) for (raw,) in db.execute("SELECT payload FROM receipts ORDER BY operation")]
            return {self.key: strict(row[0]), "receipts": receipts}

    def write_once(self):
        operation = self.effect["operation_id"]
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True)) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            before = canonical(self.initial())
            changed = db.execute("UPDATE state SET payload=? WHERE id=1 AND payload=?",
                                 (canonical(self.updated()), before)).rowcount
            if changed != 1:
                raise ValueError("WRITE_PRECONDITION_LOST")
            db.execute("INSERT INTO receipts VALUES (?,?)", (operation, canonical(self.receipt())))


class OrderPort(DomainPort):
    key = "order"

    def initial(self):
        return {"order_id": self.effect["order_id"], "paid_minor": self.effect["amount_minor"],
                "refunded_minor": 0, "currency": self.effect["currency"], "status": "PAID", "revision": 0}

    def updated(self):
        return {**self.initial(), "refunded_minor": self.effect["amount_minor"], "status": "REFUNDED", "revision": 1}

    def receipt(self):
        return {**self.effect, "status": "COMMITTED", "committed_revision": 1,
                "receipt_id": "receipt-" + digest({"environment": self.environment,
                                                    "operation_id": self.effect["operation_id"]})[:24]}


class OpsPort(DomainPort):
    key = "config"

    def initial(self):
        return initial_state(self.effect)

    def updated(self):
        return {**self.initial(), "release": "release-v2", "revision": 1, "effect_count": 1,
                "operation_id": self.effect["operation_id"]}

    def receipt(self):
        return expected_receipt(self.effect, self.environment)
