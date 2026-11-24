"""Durable session admission and the bounded two-domain policy loop."""
from contextlib import closing, contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import threading
from uuid import uuid4

from .product_local_contracts import (BOUNDARY, LIMITS, MODE, REQUEST, SESSION, SCHEMA, SUCCESS, canonical,
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
        self.guard = threading.RLock()
        self.readonly = False
        self.writable = False
        self.reject_order_authority = reject_order_authority
        self.source = source_identity()

    family = "local-product"
    mode = MODE
    schema = "CREATE TABLE sessions (id TEXT PRIMARY KEY, request TEXT UNIQUE, payload BLOB NOT NULL, witness BLOB)"

    @classmethod
    def initialize(cls, owner):
        owner = safe_path(owner)
        if owner == ROOT:
            raise ValueError("OWNER_REQUIRED")
        owner.mkdir(parents=True, exist_ok=False)
        product = cls(owner)
        identity = {"format": 1, "owner": owner.name, "instance": uuid4().hex,
                    "family": cls.family, "source": product.source}
        with writer_lock(owner / "writer.lock"):
            with closing(sqlite3.connect(product.ledger)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                db.execute(cls.schema)
                db.execute("CREATE TABLE identity (binding BLOB NOT NULL)")
                db.execute("INSERT INTO identity VALUES (?)", (canonical(identity),))
            # Published last. Interruption retains the directory and cannot authorize reinitialization.
            product.write_marker("owner.json", identity)
        return owner

    def write_marker(self, name, data):
        with safe_path(self.owner / name).open("xb") as handle:
            handle.write(canonical(data))
            handle.flush()
            os.fsync(handle.fileno())

    def connect(self, *, write=False):
        if write and not self.writable:
            raise Conflict("READ_ONLY_OWNER")
        for suffix in ("-journal", "-wal", "-shm"):
            safe_path(str(self.ledger) + suffix)
        uri = safe_path(self.ledger).as_uri() + ("?mode=rw" if write else "?mode=ro")
        db = sqlite3.connect(uri, uri=True)
        try:
            if not write:
                db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            schema = db.execute("SELECT sql FROM sqlite_master WHERE name='sessions'").fetchone()
            if schema != (self.schema,):
                raise sqlite3.DatabaseError("LEDGER_SCHEMA")
            marker = safe_path(self.owner / "owner.json")
            existing = db.execute("SELECT name FROM sqlite_master WHERE name='identity'").fetchone()
            rows = db.execute("SELECT id, request, payload FROM sessions ORDER BY rowid").fetchall()
            if existing or marker.exists():
                identity = strict(marker.read_bytes())
                if (db.execute("SELECT binding FROM identity").fetchall() != [(canonical(identity),)]
                        or identity.get("owner") != self.owner.name or identity.get("family") != self.family
                        or identity.get("format") != 1 or not SESSION.fullmatch(identity["instance"])
                        or (write and identity["source"] != self.source)):
                    raise sqlite3.DatabaseError("OWNER_BINDING")
                for index, (ident, request, _) in enumerate(rows):
                    expected = {"instance": identity["instance"], "id": ident, "request": request}
                    if strict(safe_path(self.owner / f"reservation-{index}").read_bytes()) != expected:
                        raise sqlite3.DatabaseError("RESERVATION_BINDING")
                if len(list(self.owner.glob("reservation-*"))) != len(rows):
                    raise sqlite3.DatabaseError("RESERVATION_COUNT")
            elif not self.readonly or not rows or list(self.owner.glob("reservation-*")):
                raise sqlite3.DatabaseError("OWNER_BINDING_MISSING")
            for ident, request, raw in rows:
                record = strict(raw)
                if (not SESSION.fullmatch(ident) or not REQUEST.fullmatch(request)
                        or record["session_id"] != ident or record["mode"] != self.mode
                        or record["candidates"] != frozen(ident)
                        or (existing and record["source"] != identity["source"])
                        or (existing and (record.get("request_id"), record.get("owner_id"))
                            != (request,identity["instance"]))):
                    raise sqlite3.DatabaseError("SESSION_BINDING")
            return db
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            db.close()
            raise sqlite3.DatabaseError("LEDGER_CONTENT") from exc
        except Exception:
            db.close()
            raise

    def reserve(self, record, request):
        with closing(self.connect(write=True)) as db, db:
            identity = strict(db.execute("SELECT binding FROM identity").fetchone()[0])
            index = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
            record.update(request_id=request, owner_id=identity["instance"])
            self.write_marker(f"reservation-{index}", {"instance": identity["instance"],
                                                       "id": record["session_id"], "request": request})
            db.execute("INSERT INTO sessions VALUES (?,?,?,NULL)",
                       (record["session_id"], request, canonical(record)))

    def interrupted(self, record):
        record["status"] = "RECONCILE_REQUIRED"
        add_event(record, "INTERRUPTED_NO_REPLAY")

    @contextmanager
    def open(self, *, readonly=False):
        self.readonly = readonly
        if readonly:
            with closing(self.connect()):
                pass
            yield self
            return
        if not safe_path(self.owner / "writer.lock").is_file():
            raise sqlite3.DatabaseError("OWNER_INCOMPLETE")
        with writer_lock(self.owner / "writer.lock"):
            self.writable = True
            try:
                with closing(self.connect(write=True)) as db, db:
                    for ident, raw in db.execute("SELECT id,payload FROM sessions WHERE witness IS NULL").fetchall():
                        record = strict(raw)
                        if record["status"] in {"ACCEPTED", "RUNNING"}:
                            self.interrupted(record)
                            db.execute("UPDATE sessions SET payload=? WHERE id=?", (canonical(record), ident))
                yield self
            finally:
                self.writable = False

    def capability(self):
        with self.guard, closing(self.connect()) as db:
            identity_row = db.execute("SELECT name FROM sqlite_master WHERE name='identity'").fetchone()
            instance = strict(db.execute("SELECT binding FROM identity").fetchone()[0])["instance"] if identity_row else None
            records = [strict(row[0]) for row in db.execute("SELECT payload FROM sessions ORDER BY rowid")]
        return {"mode": MODE, "instance": instance, "remaining": 0 if self.readonly else max(0, LIMITS["sessions"] - len(records)),
                "blocked": any(row["status"] != "COMPLETED" for row in records),
                "provider_reservations": 0, "latest": records[-1]["session_id"] if records else None}

    def lookup(self, field, identity):
        if field not in {"id", "request"}:
            raise ValueError("LOOKUP_SCOPE")
        with self.guard, closing(self.connect()) as db:
            row = db.execute(f"SELECT payload,witness FROM sessions WHERE {field}=?", (identity,)).fetchone()
        return (strict(row[0]), row[1]) if row else (None, None)

    def save(self, record, witness=None):
        with closing(self.connect(write=True)) as db, db:
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
            if not self.writable:
                raise Conflict("READ_ONLY_OWNER")
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
            self.reserve(record, request)
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
