"""Durable session admission and the bounded two-domain policy loop."""
from contextlib import closing, contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import threading
from uuid import uuid4

from .product_local_contracts import (BOUNDARY, LIMITS, MODE, REQUEST, SCHEMA, SUCCESS, canonical,
                                      decide, digest, fault_flags, feedback, frozen, outcome,
                                      source_identity, strict)
from .product_local_ports import OrderPort, OpsPort

ROOT = Path(__file__).resolve().parents[3] / ".local" / "rpf-100-product"


class Conflict(ValueError):
    pass


class ResponseLost(Exception):
    pass


def safe_path(path):
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(ROOT):
        raise ValueError("OWNER_SCOPE")
    for parent in (path, *path.parents):
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            if parent.is_symlink() or getattr(info, "st_file_attributes", 0) & 1024:
                raise ValueError("OWNER_REPARSE")
            if parent == path and stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("OWNER_HARDLINK")
    return path


@contextmanager
def writer_lock(path):
    # The lock file is retained. The OS releases the lock if the process exits.
    with safe_path(path).open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def add_event(record, kind, domain=None):
    events = record["events"]
    events.append({"seq": len(events) + 1, "kind": kind, "domain": domain})


class Product:
    """One active worker. Interrupted reservations remain consumed."""

    def __init__(self, owner, *, reject_order_authority=False):
        self.owner = safe_path(owner)
        if self.owner == ROOT or not self.owner.is_dir():
            raise ValueError("OWNER_REQUIRED")
        self.ledger = safe_path(self.owner / "ledger.sqlite")
        self.guard = threading.Lock()
        self.reject_order_authority = reject_order_authority
        self.source = source_identity()

    def connect(self):
        db = sqlite3.connect(safe_path(self.ledger))
        try:
            db.execute("PRAGMA synchronous=FULL")
        except sqlite3.Error:
            db.close()
            raise
        return db

    @contextmanager
    def open(self):
        with writer_lock(self.owner / "writer.lock"):
            with closing(self.connect()) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, request TEXT UNIQUE, "
                           "payload BLOB NOT NULL, witness BLOB)")
                for ident, raw in db.execute("SELECT id,payload FROM sessions WHERE witness IS NULL").fetchall():
                    data = strict(raw)
                    if data["status"] in {"ACCEPTED", "RUNNING"}:
                        data["status"] = "RECONCILE_REQUIRED"
                        add_event(data, "INTERRUPTED_NO_REPLAY")
                        db.execute("UPDATE sessions SET payload=? WHERE id=?", (canonical(data), ident))
            yield self

    def capability(self):
        with closing(self.connect()) as db:
            records = [strict(row[0]) for row in db.execute("SELECT payload FROM sessions ORDER BY rowid")]
        return {"mode": MODE, "remaining": max(0, LIMITS["sessions"] - len(records)),
                "blocked": any(row["status"] != "COMPLETED" for row in records),
                "provider_reservations": 0, "latest": records[-1]["session_id"] if records else None}

    def lookup(self, field, identity):
        if field not in {"id", "request"}:
            raise ValueError("LOOKUP_SCOPE")
        with closing(self.connect()) as db:
            row = db.execute(f"SELECT payload,witness FROM sessions WHERE {field}=?", (identity,)).fetchone()
        return (strict(row[0]), row[1]) if row else (None, None)

    def save(self, record, witness=None):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE sessions SET payload=?,witness=? WHERE id=?",
                       (canonical(record), witness, record["session_id"]))

    def event(self, record, kind, domain=None):
        add_event(record, kind, domain)
        self.save(record)

    def create(self, body):
        if (type(body) is not dict or set(body) != {"mode", "request_id"}
                or body["mode"] != MODE or not isinstance(body["request_id"], str)
                or not REQUEST.fullmatch(body["request_id"])):
            raise ValueError("INVALID_REQUEST")
        with self.guard:
            request = body["request_id"]
            existing, _ = self.lookup("request", request)
            if existing:
                return existing
            cap = self.capability()
            if cap["blocked"] or not cap["remaining"]:
                raise Conflict("SESSION_NOT_ADMITTED")
            ident = uuid4().hex
            record = {"session_id": ident, "mode": MODE, "status": "ACCEPTED",
                      "source": self.source, "limits": dict(LIMITS), "provider_reservations": 0,
                      "candidates": frozen(ident), "rounds": [], "events": [], "selection": None,
                      "storage_owner": "TASK_OWNED", "cleanup": "RETAINED_FOR_READBACK"}
            add_event(record, "CONTRACTS_FROZEN")
            with closing(self.connect()) as db, db:
                db.execute("INSERT INTO sessions VALUES (?,?,?,NULL)", (ident, request, canonical(record)))
            try:
                record["status"] = "RUNNING"
                self.event(record, "RUNNING")
                folder = safe_path(self.owner / ident)
                folder.mkdir(exist_ok=False)
                first = self.run_round(record, folder, 0)
                record["selection"] = decide(record["candidates"], first["feedback"], first["feedback_sha256"], ident)
                self.event(record, record["selection"]["decision"])
                if record["selection"]["decision"] != "SELECT_OPS":
                    record["status"] = "RECONCILE_REQUIRED"
                    self.save(record)
                    return record
                second = self.run_round(record, folder, 1)
                if second["outcome"]["contract_outcome"] != SUCCESS:
                    record["status"] = "INCONCLUSIVE"
                    self.save(record)
                    return record
                record["status"] = "COMPLETED"
                add_event(record, "COMPLETED")
                witness = canonical({"schema": SCHEMA, "session": record, "limitations": BOUNDARY})
                self.save(record, witness)
            except (OSError, ValueError, sqlite3.Error):
                record["status"] = "RECONCILE_REQUIRED"
                if record["selection"] is None:
                    record["selection"] = decide(record["candidates"], None, None, ident)
                    add_event(record, "MUST_STOP")
                add_event(record, "READBACK_REQUIRED_NO_REPLAY")
                self.save(record)
            return record

    def run_round(self, record, folder, index):
        contract = record["candidates"][index]
        domain = contract["candidate"]
        port = (OrderPort, OpsPort)[index](safe_path(folder / (domain + ".sqlite")), contract)
        before = port.read()
        self.event(record, "WRITE_INTENT", domain)
        try:
            port.write_once()
            if index == 0:
                raise ResponseLost
        except ResponseLost:
            self.event(record, "UNKNOWN_OBSERVED", domain)
        else:
            self.event(record, "WRITE_RETURNED", domain)
        if index == 0 and self.reject_order_authority:
            # Test-only injection of a real readback identity mismatch.
            port.environment = "untrusted-environment"
        after = port.read()
        result = outcome(contract, before, after)
        fault = fault_flags(domain)
        value = feedback(contract, result, fault, before, after)
        row = {"domain": domain, "contract_sha256": contract["sha256"],
               "tool_status": "UNKNOWN_OUTCOME" if index == 0 else "RETURNED",
               "authority": "INDEPENDENT_SQLITE_READ_ONLY", "before": before, "after": after,
               "fault": fault, "outcome": result, "feedback": value, "feedback_sha256": digest(value)}
        record["rounds"].append(row)
        self.event(record, "FEEDBACK_FROZEN", domain)
        return row


def file_sha(raw):
    return hashlib.sha256(raw).hexdigest()
