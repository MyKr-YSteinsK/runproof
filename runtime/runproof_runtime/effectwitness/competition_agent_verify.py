"""Independent offline checks of Agent intent, gate, effect and feedback bindings."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from .competition_agent import INVARIANTS, LIMITS, MODE, PROFILE, attestation_matches, tool_intent
from .competition_agent_session import SCHEMA, append, observation, readback, sources
from .product_local_contracts import SESSION, SUCCESS, canonical, digest, frozen, strict
from .product_local_verify import MAX_WITNESS


def verify(raw, anchor=None):
    actual = sha256(raw).hexdigest()
    if len(raw) > MAX_WITNESS or (anchor is not None and actual != anchor):
        raise ValueError("WITNESS_DIGEST")
    envelope = strict(raw)
    session = envelope["session"]
    ident = session["session_id"]
    if not SESSION.fullmatch(ident) or len(session["rounds"]) != 2:
        raise ValueError("SESSION_SHAPE")
    expected = {"session_id": ident, "mode": MODE, "profile": PROFILE, "status": "COMPLETED",
                "source": sources(), "limits": LIMITS, "provider_reservations": 0,
                "candidates": frozen(ident), "rounds": [], "events": [], "invariants": list(INVARIANTS)}
    append(expected, "CONTRACTS_FROZEN", "controller", {"source_sha256": digest(expected["source"])})
    trusted = None
    for step, (contract, row) in enumerate(zip(expected["candidates"], session["rounds"], strict=True), 1):
        domain = contract["candidate"]
        before, after = row["before"], row["after"]
        key = "order" if domain == "order" else "config"
        for snapshot in (before, after):
            if set(snapshot) != {key, "receipts"}:
                raise ValueError("AUTHORITY_SCHEMA")
            for entry in (snapshot[key], *snapshot["receipts"]):
                for field in ("paid_minor", "refunded_minor", "amount_minor", "revision",
                              "committed_revision", "effect_count"):
                    if field in entry and type(entry[field]) is not int:
                        raise ValueError("AUTHORITY_TYPE")
        independent = readback(contract, before, after, expected)
        if independent["outcome"]["contract_outcome"] != SUCCESS:
            raise ValueError("EFFECT_UNCONFIRMED")
        if step == 2:
            if not attestation_matches(trusted, expected["candidates"][0], ident, digest(expected["source"])):
                raise ValueError("FEEDBACK_UNBOUND")
            append(expected, "AGENT_REPLAN", "agent", {"input_feedback_sha256": trusted["sha256"]})
        observed = observation(expected, step, trusted)
        proposed = tool_intent(contract, step, digest(observed), trusted["sha256"] if trusted else None)
        append(expected, "AGENT_OBSERVATION", "agent", observed)
        append(expected, "AGENT_INTENT", "agent", {"intent": proposed})
        append(expected, "GATE_DECISION", "controller", {"verdict": "APPROVED", "step": step})
        append(expected, "WRITE_INTENT", "controller", {"action_id": proposed["action_id"], "contract_sha256": contract["sha256"]})
        append(expected, "UNKNOWN_OBSERVED" if step == 1 else "OPS_EFFECT", "tool",
               {"action_id": proposed["action_id"], "status": independent["tool_status"]})
        append(expected, "AUTHORITY_READBACK", "authority", {"domain": domain, "after_sha256": digest(after)})
        expected["rounds"].append(independent)
        trusted = independent["feedback"]
        append(expected, "VERIFIED_FEEDBACK", "oracle", trusted)
    append(expected, "WITNESS_FROZEN", "controller", {"rounds": 2})
    if raw != canonical({"schema": SCHEMA, "issuer": "NOT_ESTABLISHED", "session": expected}):
        raise ValueError("WITNESS_CHAIN")
    return {"status": "VERIFIED_ANCHORED" if anchor is not None else "CONTENT_CHECKED_LOCAL",
            "sha256": actual, "session_id": ident, "issuer": "NOT_ESTABLISHED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("witness", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        with args.witness.open("rb") as handle:
            result = verify(handle.read(MAX_WITNESS + 1), args.expected_sha256)
    except (ValueError, KeyError, TypeError, AttributeError, OSError, RecursionError):
        print(json.dumps({"status": "REJECTED"}))
        return 3
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
