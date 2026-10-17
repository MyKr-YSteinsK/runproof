"""Owned SQLite business state and a separate read-only authority connection."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import RuntimeFailure
from .contracts import (ENV_REVISION, LOCAL_ROOT, READER_ID, FrozenContracts,
                        canonical, digest, fields, identifier, owned_path, require)


@dataclass(frozen=True)
class AuthoritySnapshot:
    payload: bytes
    sha256: str
    _attestation: bytes = field(repr=False)

    def public(self) -> dict:
        return {"data": json.loads(self.payload), "sha256": self.sha256}


class AuthorityReader:
    """Only this reader issues snapshots to the verifier.

    The ephemeral seal prevents Tool dictionaries being mistaken for reader
    observations through this API. It is not a security boundary against Python
    code or an administrator in this process and is not an offline Witness.
    """
    def __init__(self, path: Path, contracts: FrozenContracts):
        self.path = owned_path(path, task=contracts.experiment["owner"])
        self.contracts = contracts
        self._seal = secrets.token_bytes(32)
        self.available = True

    def read(self) -> AuthoritySnapshot:
        require(self.available and self.path.is_file(), "AUTHORITY_UNAVAILABLE", "ENVIRONMENT")
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only=ON")
                db.execute("BEGIN")
                meta = dict(db.execute("SELECT * FROM environment").fetchone())
                order = dict(db.execute("SELECT * FROM orders WHERE order_id=?",
                                        (self.contracts.effect["order_id"],)).fetchone())
                receipts = [dict(row) for row in db.execute(
                    "SELECT * FROM refunds ORDER BY operation_id")]
                db.commit()
        except (sqlite3.Error, TypeError) as error:
            raise RuntimeFailure("ENVIRONMENT", "AUTHORITY_READ_ERROR") from error
        data = {"reader_id": READER_ID, "reader_version": "1",
                "source_id": self.contracts.effect["authority_id"],
                "environment": meta, "order": order, "receipts": receipts}
        raw = canonical(data)
        return AuthoritySnapshot(raw, hashlib.sha256(raw).hexdigest(),
                                 hmac.digest(self._seal, raw, "sha256"))

    def validate(self, snapshot: AuthoritySnapshot | None) -> dict:
        require(isinstance(snapshot, AuthoritySnapshot), "AUTHORITY_SNAPSHOT_MISSING", "ENVIRONMENT")
        require(hashlib.sha256(snapshot.payload).hexdigest() == snapshot.sha256
                and hmac.compare_digest(snapshot._attestation,
                                        hmac.digest(self._seal, snapshot.payload, "sha256")),
                "AUTHORITY_HASH_OR_ISSUER_MISMATCH", "ENVIRONMENT")
        data = json.loads(snapshot.payload)
        experiment, effect = self.contracts.experiment, self.contracts.effect
        expected = {"owner": experiment["owner"], "run_id": experiment["run_id"],
                    "environment_id": experiment["environment_id"],
                    "environment_revision": ENV_REVISION,
                    "reset_generation": experiment["reset_generation"]}
        require(data["reader_id"] == READER_ID and data["reader_version"] == "1"
                and data["source_id"] == effect["authority_id"]
                and data["order"]["order_id"] == effect["order_id"]
                and data["environment"] == expected, "AUTHORITY_IDENTITY_MISMATCH", "ENVIRONMENT")
        return data

    def reconcile(self, operation_id: str) -> dict:
        data = self.validate(self.read())
        receipts = [r for r in data["receipts"] if r["operation_id"] == operation_id]
        e = self.contracts.effect
        require(len(receipts) == 1, "RECONCILE_RECEIPT_MISSING", "ENVIRONMENT")
        receipt = receipts[0]
        require(receipt["order_id"] == e["order_id"] and receipt["amount_minor"] == e["amount_minor"]
                and receipt["currency"] == e["currency"] and receipt["status"] == "COMMITTED",
                "RECONCILE_RECEIPT_MISMATCH", "ENVIRONMENT")
        return receipt


class OrderSandbox:
    def __init__(self, contracts: FrozenContracts, directory: Path | None = None):
        contracts.validate()
        self.contracts = contracts
        self.owner = contracts.experiment["owner"]
        root = {"rpf-41": LOCAL_ROOT, "rpf-42": LOCAL_ROOT.parent / "rpf-42",
                "rpf-43": LOCAL_ROOT.parent / "rpf-43",
                "rpf-44": LOCAL_ROOT.parent / "rpf-44"}[self.owner]
        self.directory = owned_path(directory or root / contracts.experiment["run_id"], task=self.owner)
        self.path = owned_path(self.directory / "orders.sqlite3", task=self.owner)
        self.created = False
        self.generation = 0

    def initialize(self) -> None:
        require(not self.directory.exists(), "ENVIRONMENT_ALREADY_EXISTS", "ENVIRONMENT")
        self.directory.mkdir(parents=True)
        self.created = True
        e, x = self.contracts.effect, self.contracts.experiment
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("""
                PRAGMA journal_mode=DELETE;
                CREATE TABLE environment(owner TEXT, run_id TEXT, environment_id TEXT,
                    environment_revision TEXT, reset_generation INTEGER);
                CREATE TABLE orders(order_id TEXT PRIMARY KEY, paid_minor INTEGER NOT NULL,
                    refunded_minor INTEGER NOT NULL, currency TEXT NOT NULL,
                    status TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE refunds(operation_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL UNIQUE, amount_minor INTEGER NOT NULL,
                    currency TEXT NOT NULL, receipt_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL, committed_revision INTEGER NOT NULL);
            """)
            db.execute("INSERT INTO environment VALUES(?,?,?,?,0)",
                       (self.owner, x["run_id"], x["environment_id"], ENV_REVISION))
            db.execute("INSERT INTO orders VALUES(?,?,0,?,'PAID',0)",
                       (e["order_id"], e["amount_minor"], e["currency"]))
            db.commit()

    def _check_owner(self, db: sqlite3.Connection) -> None:
        row = db.execute("SELECT * FROM environment").fetchone()
        x = self.contracts.experiment
        require(row == (self.owner, x["run_id"], x["environment_id"], ENV_REVISION,
                        self.generation), "ENVIRONMENT_OWNER_OR_GENERATION", "ENVIRONMENT")

    def refund(self, order_id: str, operation_id: str, amount_minor: int) -> dict:
        """Business transaction. Replay binds the same operation to identical input."""
        e = self.contracts.effect
        require(self.generation == 0, "ENVIRONMENT_RESET_REQUIRES_NEW_EXPERIMENT", "ENVIRONMENT")
        require(order_id == e["order_id"] and identifier(operation_id)
                and type(amount_minor) is int and amount_minor == e["amount_minor"],
                "REFUND_ARGUMENTS_REJECTED", "AGENT")
        require(self.path.is_file(), "ENVIRONMENT_MISSING", "ENVIRONMENT")
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("BEGIN IMMEDIATE")
            self._check_owner(db)
            old = db.execute("SELECT order_id,amount_minor,currency,receipt_id,status,committed_revision "
                             "FROM refunds WHERE operation_id=?", (operation_id,)).fetchone()
            if old:
                require(old[:3] == (order_id, amount_minor, e["currency"]),
                        "OPERATION_IDENTITY_CONFLICT", "AGENT")
                db.commit()
                return {"status": "IDEMPOTENT_REPLAY", "operation_id": operation_id,
                        "receipt_id": old[3], "committed_revision": old[5]}
            row = db.execute("SELECT paid_minor,refunded_minor,currency,status,revision FROM orders "
                             "WHERE order_id=?", (order_id,)).fetchone()
            require(row == (amount_minor, 0, e["currency"], "PAID", 0),
                    "ORDER_NOT_REFUNDABLE", "AGENT")
            receipt_id = "receipt-" + digest({"environment": self.contracts.experiment["environment_id"],
                                             "operation_id": operation_id})[:24]
            db.execute("INSERT INTO refunds VALUES(?,?,?,?,?,'COMMITTED',1)",
                       (operation_id, order_id, amount_minor, e["currency"], receipt_id))
            db.execute("UPDATE orders SET refunded_minor=?,status='REFUNDED',revision=1 WHERE order_id=?",
                       (amount_minor, order_id))
            db.commit()
        return {"status": "COMMITTED", "operation_id": operation_id,
                "receipt_id": receipt_id, "committed_revision": 1}

    def inspect(self) -> dict:
        # Business-facing read, deliberately not an AuthoritySnapshot.
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT order_id,status,revision FROM orders WHERE order_id=?",
                             (self.contracts.effect["order_id"],)).fetchone()
        require(row is not None, "ORDER_MISSING", "ENVIRONMENT")
        return dict(zip(("order_id", "status", "revision"), row))

    def reset(self) -> int:
        e = self.contracts.effect
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            self._check_owner(db)
            db.execute("DELETE FROM refunds")
            db.execute("UPDATE orders SET paid_minor=?,refunded_minor=0,currency=?,status='PAID',revision=0",
                       (e["amount_minor"], e["currency"]))
            db.execute("UPDATE environment SET reset_generation=reset_generation+1")
            db.commit()
            require(db.execute("SELECT count(*) FROM refunds").fetchone()[0] == 0
                    and db.execute("SELECT refunded_minor,status,revision FROM orders").fetchone()
                    == (0, "PAID", 0), "RESET_READBACK_FAILED", "ENVIRONMENT")
            self.generation = db.execute("SELECT reset_generation FROM environment").fetchone()[0]
            return self.generation

    def cleanup(self) -> dict:
        generation = self.reset()
        # Only exact task-created SQLite files; no recursive deletion.
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = owned_path(Path(str(self.path) + suffix), task=self.owner)
            if path.exists():
                path.unlink()
        self.directory.rmdir()
        return {"status": "RESET_AND_REMOVED", "reset_generation": generation,
                "receipt_count_after_reset": 0}


class OrderAdapter:
    def __init__(self, sandbox: OrderSandbox):
        self.sandbox = sandbox
        self.contracts = sandbox.contracts
        planned = self.contracts.experiment["fault"] != "none"
        self.fault = {"planned": planned, "triggered": False, "observed": False, "reconciled": False}

    def tool_definitions(self) -> list[dict]:
        e = self.contracts.effect
        properties = {"order_id": {"type": "string", "enum": [e["order_id"]]},
                      "operation_id": {"type": "string", "enum": [e["operation_id"]]},
                      "amount_minor": {"type": "integer", "enum": [e["amount_minor"]]}}
        return [{"type": "function", "function": {
            "name": name, "description": "Inspect the order" if name == "inspect_order" else
            "Commit the one authorized full refund in the local simulation",
            "parameters": {"type": "object", "properties":
                           ({"order_id": properties["order_id"]} if name == "inspect_order" else properties),
                           "required": ["order_id"] if name == "inspect_order" else list(properties),
                           "additionalProperties": False}}}
                for name in self.contracts.execution["tools"]]

    def invoke(self, name: str, arguments: dict) -> dict:
        require(name in self.contracts.execution["tools"], "TOOL_NOT_ALLOWLISTED", "AGENT")
        e = self.contracts.effect
        expected = {"order_id"} if name == "inspect_order" else {"order_id", "operation_id", "amount_minor"}
        require(type(arguments) is dict and set(arguments) == expected, "TOOL_ARGUMENT_FIELDS", "AGENT")
        require(arguments["order_id"] == e["order_id"], "ORDER_NOT_ALLOWLISTED", "AGENT")
        if name == "inspect_order":
            return self.sandbox.inspect()
        require(arguments["operation_id"] == e["operation_id"]
                and type(arguments["amount_minor"]) is int
                and arguments["amount_minor"] == e["amount_minor"], "REFUND_NOT_ALLOWLISTED", "AGENT")
        result = self.sandbox.refund(**arguments)
        if result["status"] == "COMMITTED" and self.contracts.experiment["fault"] in (
                "response-lost", "reconcile-unavailable"):
            self.fault.update(triggered=True, observed=True)
            return {"status": "UNKNOWN_OUTCOME", "operation_id": e["operation_id"],
                    "reason": "CONTROLLED_POST_COMMIT_RESPONSE_LOSS"}
        return result
