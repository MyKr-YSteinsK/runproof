"""Task-root binding and independent read-only Authority for local transactions."""
from contextlib import closing
import sqlite3
from uuid import uuid4

from . import pge_r106_contracts as inner
from .product_sdk_target import safe
from .sdk_presend_contracts import REPO, check, strict, sync_dir

ROOT = REPO / ".local" / "rpf-110"


def fresh():
    for folder in (ROOT.parent, ROOT):
        try:
            safe(folder, directory=True)
        except FileNotFoundError:
            safe(folder, directory=True, absent=True).mkdir()
            sync_dir(folder.parent)
    owner = safe(ROOT / uuid4().hex, directory=True, absent=True)
    owner.mkdir()
    sync_dir(ROOT)
    return owner


def database(owner, contract, *, absent=False):
    identity = inner.binding(contract)
    check(owner.parent == ROOT and inner.hex_id(owner.name, 32) and owner.name == identity["owner"]
          and identity["db_member"] in ("seed-order.sqlite", "fault-order.sqlite", "fault-ops.sqlite"), "DB_SCOPE")
    return safe(owner / identity["db_member"], absent=absent)


def readback(owner, contract):
    identity = inner.binding(contract)
    path = database(owner, contract)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=4)) as db:
        db.execute("PRAGMA query_only=ON")
        check(db.execute("PRAGMA query_only").fetchone() == (1,), "QUERY_ONLY")
        db.execute("BEGIN")
        check(db.execute("SELECT environment FROM identity LIMIT 2").fetchall() ==
              [(identity["environment_id"],)], "AUTHORITY_ENVIRONMENT")
        rows = db.execute("SELECT id,payload FROM state LIMIT 2").fetchall()
        receipts = db.execute("SELECT operation,payload FROM receipts LIMIT 2").fetchall()
        check(len(rows) == 1 and rows[0][0] == 1 and 0 < len(rows[0][1]) <= 8192 and len(receipts) <= 1
              and all(op == identity["operation_id"] and 0 < len(value) <= 8192
                      for op, value in receipts), "AUTHORITY_ROWS")
        key = "order" if identity["domain"] == "order" else "config"
        snapshot = {key: strict(rows[0][1]), "receipts": [strict(raw) for _, raw in receipts]}
    return {"schema": "rpf106-authority-v1", "mode": "SQLITE_RO_QUERY_ONLY",
            "binding": identity, "snapshot": snapshot}
