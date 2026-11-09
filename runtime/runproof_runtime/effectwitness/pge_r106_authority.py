"""Independent read-only SQLite facts for the frozen operation."""
from contextlib import closing
from pathlib import Path
import sqlite3

from . import pge_r106_contracts as c
from .product_sdk_target import safe
from .sdk_presend_contracts import REPO, check, strict

ROOT = REPO / ".local" / "rpf-106"


def owner_path(owner):
    check(c.hex_id(owner, 32), "OWNER_ID")
    return ROOT / owner


def database(owner, contract, *, absent=False):
    owner = Path(owner)
    identity = c.binding(contract)
    check(owner == owner_path(identity["owner"]) and identity["db_member"] in
          ("seed-order.sqlite", "fault-order.sqlite", "fault-ops.sqlite"), "OWNER_OR_DB_SCOPE")
    return safe(owner / identity["db_member"], absent=absent)


def readback(owner, contract):
    identity = c.binding(contract)
    path = database(owner, contract)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        check(db.execute("PRAGMA query_only").fetchone() == (1,), "AUTHORITY_QUERY_ONLY")
        db.execute("BEGIN")
        check(db.execute("SELECT environment FROM identity LIMIT 2").fetchall() == [(identity["environment_id"],)],
              "AUTHORITY_ENVIRONMENT")
        rows = db.execute("SELECT id,payload FROM state LIMIT 2").fetchall()
        check(len(rows) == 1 and rows[0][0] == 1 and 0 < len(rows[0][1]) <= 8192, "AUTHORITY_STATE")
        receipts = db.execute("SELECT operation,payload FROM receipts ORDER BY operation LIMIT 2").fetchall()
        check(len(receipts) <= 1 and all(key == identity["operation_id"] and 0 < len(raw) <= 8192
                                        for key, raw in receipts), "AUTHORITY_OPERATION")
        key = "order" if identity["domain"] == "order" else "config"
        snapshot = {key: strict(rows[0][1]), "receipts": [strict(raw) for _, raw in receipts]}
    return {"schema": "rpf106-authority-v1", "mode": "SQLITE_RO_QUERY_ONLY",
            "binding": identity, "snapshot": snapshot}
