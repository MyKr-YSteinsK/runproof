"""Scoped SQLite writer and separate read-only Authority entry point."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import stat

from .product_local_ports import OpsPort, OrderPort
from .product_sdk_contracts import binding, validate_frozen
from .sdk_presend_contracts import canonical, check, strict, sync_dir


def safe(path, *, directory=False, absent=False):
    path = Path(os.path.abspath(path))
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if part == path and absent:
                return path
            raise
        check(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 1024,
              "PATH_REPARSE")
        if part != path or directory:
            check(stat.S_ISDIR(info.st_mode), "PATH_DIRECTORY")
        else:
            check(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "PATH_FILE")
    check(not absent, "PATH_OCCUPIED")
    return path


def read(path, limit):
    with safe(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    check(0 < len(raw) <= limit, "FILE_SIZE")
    return raw


def create(path, raw):
    path = safe(path, absent=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(path.parent)


def case_scope(folder, frozen):
    folder = safe(folder, directory=True)
    check(folder.name == frozen["case"] and folder.parent.name == frozen["owner"], "CASE_SCOPE")
    return folder


def db_path(folder, frozen, domain, *, absent=False):
    folder = case_scope(folder, frozen)
    return safe(folder / binding(frozen, domain)["db_member"], absent=absent)


class Target:
    def __init__(self, folder, frozen):
        self.frozen = validate_frozen(frozen)
        self.folder = case_scope(folder, frozen)
        self.ports = {}

    def prepare(self, domain, identity):
        check(identity == binding(self.frozen, domain) and domain not in self.ports, "TARGET_IDENTITY")
        port = OrderPort if domain == "order" else OpsPort
        path = db_path(self.folder, self.frozen, domain, absent=True)
        self.ports[domain] = port(path, self.frozen["contracts"][domain])
        sync_dir(path.parent)

    def write_once(self, domain, identity):
        check(identity == binding(self.frozen, domain) and domain in self.ports, "TARGET_IDENTITY")
        port = self.ports.pop(domain)
        path = db_path(self.folder, self.frozen, domain)
        # Keep environment, compare-and-set, and the unique receipt in one transaction.
        with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            check(db.execute("SELECT environment FROM identity").fetchall() == [(identity["environment_id"],)]
                  and db.execute("SELECT operation FROM receipts LIMIT 1").fetchone() is None,
                  "WRITE_ENVIRONMENT_OR_RECEIPT")
            changed = db.execute("UPDATE state SET payload=? WHERE id=1 AND payload=?",
                                 (canonical(port.updated()), canonical(port.initial()))).rowcount
            check(changed == 1, "WRITE_PRECONDITION")
            db.execute("INSERT INTO receipts VALUES (?,?)",
                       (identity["operation_id"], canonical(port.receipt())))


def readback(folder, frozen, domain):
    identity = binding(frozen, domain)
    path = db_path(folder, frozen, domain)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        check(db.execute("PRAGMA query_only").fetchone() == (1,), "AUTHORITY_QUERY_ONLY")
        db.execute("BEGIN")
        check(db.execute("SELECT environment FROM identity").fetchall() == [(identity["environment_id"],)],
              "AUTHORITY_ENVIRONMENT")
        rows = db.execute("SELECT id,payload FROM state").fetchall()
        check(len(rows) == 1 and rows[0][0] == 1, "AUTHORITY_STATE")
        receipts = db.execute("SELECT operation,payload FROM receipts ORDER BY operation").fetchmany(2)
        check(len(receipts) <= 1 and all(op == identity["operation_id"] for op, _ in receipts),
              "AUTHORITY_RECEIPT_SCOPE")
        key = "order" if domain == "order" else "config"
        return {"binding": identity, "authority": "SQLITE_RO_QUERY_ONLY", "pid": os.getpid(),
                "snapshot": {key: strict(rows[0][1]), "receipts": [strict(raw) for _, raw in receipts]}}


def authority_main(domain):
    folder = Path.cwd()
    frozen = validate_frozen(strict(read(folder / "contract.json", 16384)))
    print(canonical(readback(folder, frozen, domain)).decode(), flush=True)
    return 0
