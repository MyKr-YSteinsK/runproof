"""Verify Phase A bundles using only their bytes and two independent pins."""
import argparse
from pathlib import Path

from . import pge_r106_contracts as inner, pge_r106_ledger as ledger
from . import pge_r110_contracts as c, pge_r110_explorer as explorer, pge_r110_provider as provider
from .pge_r108_verify import SECRET, business, bytes_for, presend_rows
from .sdk_presend_contracts import canonical, check, sha, strict

MAX_BUNDLE = 256 * 1024
MAX_TRACE = 64 * 1024
FIELDS = {"schema", "kind", "strategy", "issuer", "provider", "presend_wal", "business_wal", "authority"}
NO_PROVIDER = {"request": "NOT_RUN", "sdk": "NOT_RUN", "usage": "NOT_RUN", "fees": "NOT_RUN",
               "physical_send": "NOT_RUN"}


def fixture_sequence(events, contract, request):
    check([e["kind"] for e in events] ==
          ["MODEL_POST_RECEIVED", "PROVIDER_RESERVE", "SEND_INTENT", "FIXTURE_SEND_ENTRY",
           "FIXTURE_RETURN", "TOOL_CALLBACK"], "FIXTURE_SEQUENCE")
    received, ticket, intent, entry, returned, callback = (row["body"] for row in events)
    inner.exact(ticket, "ticket_id", "request_sha256", "run_id", "seed_tip")
    check(bytes_for(received, c.INPUT_FIXTURE_BYTES) == request and ticket == intent == entry
          and inner.hex_id(ticket["ticket_id"], 32) and ticket["run_id"] == contract["scope"]["run_id"]
          and ticket["request_sha256"] == sha(request) and ticket["seed_tip"] == contract["seed_tip"], "TICKET_BINDING")
    inner.exact(returned, "status", "elapsed_ms", "request_id", "response")
    inner.exact(callback, "application", "selection")
    response = bytes_for(returned["response"], c.MAX_REPLY)
    tool = bytes_for(callback["application"], c.INPUT_FIXTURE_BYTES)
    check(not SECRET.search(request + response + tool), "PRIVATE_WIRE")
    check(returned["request_id"] == "fixture-request-" + ticket["ticket_id"], "REQUEST_ID_BINDING")
    selected = provider.parse(response, returned["status"], returned["elapsed_ms"], returned["request_id"])
    check(canonical(callback["selection"]) == canonical(selected), "SELECTION_BINDING")
    return explorer.validate_callback(tool, selected)


def verify(raw, source, content_sha):
    check(inner.hex_id(source, 40) and inner.hex_id(content_sha, 64)
          and 0 < len(raw) <= MAX_BUNDLE and sha(raw) == content_sha, "BUNDLE_ANCHOR")
    row = strict(raw)
    check(type(row) is dict, "BUNDLE_SHAPE")
    if set(row) < FIELDS:
        return {"status": "UNAVAILABLE", "missing": sorted(FIELDS - set(row))}
    check(set(row) == FIELDS and canonical(row) == raw and not SECRET.search(raw)
          and row["schema"] == "rpf110-witness-v1" and row["kind"] == "PHASE_A_FIXTURE"
          and row["issuer"] == "NOT_ESTABLISHED" and row["provider"] == NO_PROVIDER, "BUNDLE_SCOPE")
    frozen, seed_view, seed, final, choice, transactions = business(
        bytes_for(row["business_wal"], ledger.MAX_BYTES), row["authority"], source)
    contract = c.freeze(frozen, seed_view, seed, row["strategy"])
    events = presend_rows(bytes_for(row["presend_wal"], MAX_TRACE))
    check(len(events) >= 5 and events[0]["kind"] == "OPEN" and events[0]["body"] == contract, "FROZEN_SCOPE")
    expected_phase = "STOPPED" if choice == inner.STOP else "UNKNOWN"
    terminal, later, denied = events[-3:]
    request = c.request(contract)
    check((terminal["kind"], later["kind"], denied["kind"]) ==
          (expected_phase, "MODEL_POST_RECEIVED", "DENIED")
          and terminal["body"] == {"candidate_id": choice, "ledger_tip": final["tip"]}
          and bytes_for(later["body"], c.INPUT_FIXTURE_BYTES) == request
          and denied["body"] == {"phase": expected_phase, "ledger_tip": final["tip"]}, "TERMINAL_DENIAL")
    if row["strategy"] == "FIXED_ORDER_B0":
        check(len(events) == 5 and events[1]["kind"] == "BASELINE_CHOICE"
              and events[1]["body"] == {"candidate_id": inner.ORDER} and choice == inner.ORDER, "B0_BINDING")
    else:
        check(fixture_sequence(events[1:-3], contract, request) == choice, "CHOICE_EFFECT")
    effect = None if choice == inner.STOP else row["authority"][choice]["after"]["snapshot"]
    if effect is not None:
        state = effect["config"] if choice == inner.OPS else effect["order"]
        effect = {"revision": state["revision"], "receipt_count": len(effect["receipts"]),
                  **({"release": state["release"]} if choice == inner.OPS else
                     {"refunded_minor": state["refunded_minor"], "status": state["status"]})}
    projection = {"schema": "rpf110-demo-v1", "source_kind": row["strategy"],
                  "real_explorer": "NOT_RUN", "provider": "NOT_RUN", "agent_outcome": "NOT_RUN",
                  "candidate_id": choice, "candidates": list(c.CHOICES), "seed": contract["feedback"]["seed"],
                  "remaining_before_choice": contract["feedback"]["remaining"],
                  "business_transactions": transactions, "effect": effect, "terminal": expected_phase,
                  "fault": inner.faults(frozen["catalog"][choice], triggered=True, observed=True)
                           if choice != inner.STOP else {"planned": False, "triggered": False,
                                                       "observed": False, "agent_exposed": False},
                  "post_terminal_new_reservations": 0, "post_terminal_new_writes": 0,
                  "selection_causality": "NOT_PROVEN", "issuer": "NOT_ESTABLISHED", "release_eligible": False}
    return {"status": "FIXTURE_PORTABLE_REPLAY", "scope": frozen["scope"], "demo_projection": projection}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("source")
    parser.add_argument("content_sha")
    args = parser.parse_args()
    with args.bundle.open("rb") as stream:
        row = verify(stream.read(MAX_BUNDLE + 1), args.source, args.content_sha)
    print(canonical(row).decode())


if __name__ == "__main__":
    main()
