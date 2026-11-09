"""Offline verification of a frozen RPF-100 envelope."""
import argparse
import hashlib
import json
from pathlib import Path

from .product_local_contracts import (BOUNDARY, LIMITS, MODE, SCHEMA, SESSION, SUCCESS, canonical,
                                      decide, digest, fault_flags, feedback, frozen, outcome,
                                      source_identity, strict)

MAX_WITNESS = 65536


def verify(raw, expected_sha256=None):
    actual = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and actual != expected_sha256:
        raise ValueError("ANCHOR_MISMATCH")
    if len(raw) > MAX_WITNESS:
        raise ValueError("WITNESS_TOO_LARGE")
    envelope = strict(raw)
    data = envelope["session"]
    ident = data["session_id"]
    if not isinstance(ident, str) or not SESSION.fullmatch(ident):
        raise ValueError("IDENTITY_INVALID")
    candidates = frozen(ident)
    if len(data["rounds"]) != 2:
        raise ValueError("ROUNDS_INVALID")
    rounds = []
    for contract, row in zip(candidates, data["rounds"], strict=True):
        domain = contract["candidate"]
        before, after = row["before"], row["after"]
        key = "order" if domain == "order" else "config"
        if set(before) != {key, "receipts"} or set(after) != {key, "receipts"}:
            raise ValueError("AUTHORITY_SCHEMA")
        for snapshot in (before, after):
            for entry in (snapshot[key], *snapshot["receipts"]):
                for field in ("paid_minor", "refunded_minor", "amount_minor", "revision",
                              "committed_revision", "effect_count"):
                    if field in entry and type(entry[field]) is not int:
                        raise ValueError("AUTHORITY_NUMERIC_TYPE")
        result = outcome(contract, before, after)
        if result["contract_outcome"] != SUCCESS:
            raise ValueError("EFFECT_NOT_SATISFIED")
        fault = fault_flags(domain)
        value = feedback(contract, result, fault, before, after)
        rounds.append({"domain": domain, "contract_sha256": contract["sha256"],
                       "tool_status": "UNKNOWN_OUTCOME" if domain == "order" else "RETURNED",
                       "authority": "INDEPENDENT_SQLITE_READ_ONLY", "before": before, "after": after,
                       "fault": fault, "outcome": result, "feedback": value, "feedback_sha256": digest(value)})
    selection = decide(candidates, rounds[0]["feedback"], rounds[0]["feedback_sha256"], ident)
    sequence = [
        ("CONTRACTS_FROZEN", None), ("RUNNING", None), ("WRITE_INTENT", "order"),
        ("UNKNOWN_OBSERVED", "order"), ("FEEDBACK_FROZEN", "order"), ("SELECT_OPS", None),
        ("WRITE_INTENT", "ops"), ("WRITE_RETURNED", "ops"), ("FEEDBACK_FROZEN", "ops"), ("COMPLETED", None),
    ]
    expected = {"schema": SCHEMA, "limitations": BOUNDARY,
                "session": {"session_id": ident, "mode": MODE, "status": "COMPLETED",
                            "source": source_identity(), "limits": LIMITS, "provider_reservations": 0,
                            "storage_owner": "TASK_OWNED", "cleanup": "RETAINED_FOR_READBACK",
                            "candidates": candidates, "rounds": rounds, "selection": selection,
                            "events": [{"seq": i, "kind": kind, "domain": domain}
                                       for i, (kind, domain) in enumerate(sequence, 1)]}}
    if canonical(envelope) != canonical(expected) or selection["decision"] != "SELECT_OPS":
        raise ValueError("WITNESS_LINK_MISMATCH")
    return {"status": "VERIFIED_ANCHORED" if expected_sha256 is not None else "CONTENT_CHECKED_LOCAL",
            "sha256": actual, "session_id": ident, "issuer": "NOT_ESTABLISHED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("witness", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        with args.witness.open("rb") as stream:
            result = verify(stream.read(MAX_WITNESS + 1), args.expected_sha256)
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print(json.dumps({"status": "REJECTED"}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
