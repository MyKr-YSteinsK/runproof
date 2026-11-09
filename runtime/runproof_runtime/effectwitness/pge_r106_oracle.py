"""Read-only verification of the actual SQLite receipts against the durable history."""
import argparse
import sqlite3

from . import pge_r106_contracts as c
from .effect_oracle import evaluate_order_effect
from .ops_oracle import evaluate_ops_effect
from .pge_r106_authority import owner_path, readback
from .pge_r106_ledger import MAX_BYTES, WAL, replay
from .product_sdk_target import read, safe
from .sdk_presend_contracts import canonical, check

READ_FAILURES = (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error, RecursionError)


def evaluate(contract, before, after):
    identity = c.binding(contract)
    key = "order" if identity["domain"] == "order" else "config"
    for row in (before, after):
        c.exact(row, "schema", "mode", "binding", "snapshot")
        check(row["schema"] == "rpf106-authority-v1" and row["mode"] == "SQLITE_RO_QUERY_ONLY"
              and canonical(row["binding"]) == canonical(identity), "ORACLE_AUTHORITY")
        c.exact(row["snapshot"], key, "receipts")
        check(type(row["snapshot"]["receipts"]) is list, "ORACLE_RECEIPTS")
        for item in (row["snapshot"][key], *row["snapshot"]["receipts"]):
            check(type(item) is dict and all(type(item[k]) is int for k in (
                "paid_minor", "refunded_minor", "amount_minor", "revision", "committed_revision", "effect_count")
                if k in item), "ORACLE_NUMERIC")
    evaluator = evaluate_order_effect if key == "order" else evaluate_ops_effect
    return evaluator(contract["effect"], identity["environment_id"], before["snapshot"], after["snapshot"])


def verify_round(owner, contract, rows):
    name = contract["candidate_id"]
    positions = [i for i, row in enumerate(rows)
                 if row["kind"] == "CLAIMED" and row["body"]["proposal"]["candidate_id"] == name]
    check(len(positions) == 1, "ORACLE_CLAIM")
    events = rows[positions[0] + 1:]
    lost = contract["experiment"]["fault"] == c.FAULT
    expected = ["AUTHORITY_BEFORE", "WRITE_INTENT", "WRITE_COMMIT"]
    if lost:
        expected.append("UNKNOWN")
    expected.append("AUTHORITY_AFTER")
    check([row["kind"] for row in events] == expected, "ORACLE_SEQUENCE")
    before, after = events[0]["body"], events[-1]["body"]
    actual = readback(owner, contract)
    check(canonical(actual) == canonical(after), "ORACLE_DB_READBACK")
    effect = evaluate(contract, before, actual)
    check(effect["contract_outcome"] == c.SUCCESS and len(actual["snapshot"]["receipts"]) == 1,
          "ORACLE_EFFECT")
    return {"schema": "rpf106-oracle-v1", "binding": c.binding(contract), "outcome": c.SUCCESS,
            "fault": c.faults(contract, triggered=lost, observed=lost), "intent_sha256": events[1]["sha256"],
            "authority_before_sha256": c.digest(before), "authority_after_sha256": c.digest(actual),
            "receipt_sha256": c.digest(actual["snapshot"]["receipts"][0]),
            "agent_outcome": "NOT_RUN", "platform_outcome": "LOCAL_TRANSACTION_OBSERVED",
            "verification": "CONTENT_CHECKED_LOCAL", "issuer": "NOT_ESTABLISHED"}


def reconcile(owner, contract, rows):
    """Observe the original operation without unlocking or creating a database."""
    try:
        actual = readback(owner, contract)
        before = next((row["body"] for row in rows if row["kind"] == "AUTHORITY_BEFORE"
                       and row["body"]["binding"] == c.binding(contract)), None)
        if before is None:
            return {"outcome": "INCONCLUSIVE", "authority": actual}
        effect = evaluate(contract, before, actual)
        if effect["contract_outcome"] == c.SUCCESS:
            status = "COMMITTED"
        elif not actual["snapshot"]["receipts"] and canonical(before["snapshot"]) == canonical(actual["snapshot"]):
            status = "NOT_COMMITTED"
        else:
            status = "INCONCLUSIVE"
        return {"outcome": status, "authority": actual}
    except READ_FAILURES:
        return {"outcome": "UNAVAILABLE", "authority": None}


def inspect(owner_id):
    owner = safe(owner_path(owner_id), directory=True)
    raw = read(owner / WAL, MAX_BYTES)
    state, rows = replay(raw)
    frozen = state["frozen"]
    check(frozen["scope"]["owner"] == owner_id, "ORACLE_OWNER")
    verified = {}
    claimed = []
    for index, row in enumerate(rows):
        if row["kind"] == "CLAIMED":
            claimed.append(row["body"]["proposal"]["candidate_id"])
        if row["kind"] == "VERIFIED":
            name = row["body"]["verdict"]["binding"]["candidate_id"]
            verdict = verify_round(owner, frozen["catalog"][name], rows[:index])
            check(canonical(verdict) == canonical(row["body"]["verdict"]), "ORACLE_PIN_CONTENT")
            verified[name] = verdict
    for name in set(frozen["catalog"]) - set(claimed):
        safe(owner / frozen["catalog"][name]["execution"]["db_member"], absent=True)
    unsettled = {name: reconcile(owner, frozen["catalog"][name], rows) for name in claimed if name not in verified}
    unknown = next((i for i, row in enumerate(rows) if row["kind"] == "UNKNOWN"), None)
    return {"scope": frozen["scope"], "phase": state["phase"], "latched": state["latched"],
            "revision": state["revision"], "wal_sha256": c.sha(raw), "wal_tip_sha256": state["tip"],
            "remaining": state["remaining"], "claimed": claimed, "verified": verified, "unsettled": unsettled,
            "verified_business_transactions": len(verified), "post_unknown_effect_events":
                sum(row["kind"] in ("CLAIMED", "WRITE_INTENT", "WRITE_COMMIT") for row in rows[unknown + 1:])
                if unknown is not None else None,
            "write_recovery": "PROHIBITED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner")
    try:
        print(canonical(inspect(parser.parse_args().owner)).decode())
    except READ_FAILURES:
        print('{"verification":"REJECTED"}')
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
