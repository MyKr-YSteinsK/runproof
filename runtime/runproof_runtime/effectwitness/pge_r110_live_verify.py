"""Independent proof of business effects and redacted transport event semantics."""
import argparse
from pathlib import Path

from . import pge_r106_contracts as inner, pge_r106_ledger as ledger
from . import pge_r110_live_contracts as c, pge_r110_live_provider as provider
from .pge_r108_verify import SECRET, business, bytes_for, presend_rows
from .sdk_presend_contracts import canonical, check, sha, strict

LIMIT = 240 * 1024
COMPARISON_LIMIT = 512 * 1024
TRACE_LIMIT = 80 * 1024
FIELDS = {"schema", "kind", "issuer", "approval", "request", "stub_response", "presend_wal",
          "business_wal", "authority"}


def wire(events, contract, request, stub_response):
    mode = contract["kind"]
    kinds = ["HOST_REQUEST_READY", "PROVIDER_RESERVE", "SEND_INTENT",
             "SEND_ENTRY" if mode == c.NATIVE else "STUB_SEND_ENTRY",
             "HTTP_RESPONSE" if mode == c.NATIVE else "STUB_RESPONSE", "TOOL_SELECTION"]
    check([row["kind"] for row in events] == kinds, "LIVE_SEND_SEQUENCE")
    post, ticket, intent, entry, receipt, selection = (row["body"] for row in events)
    inner.exact(ticket, "ticket_id", "request_sha256", "owner", "run_id", "seed_tip")
    inner.exact(entry, "ticket", "kind", "entered_ns", "entered_utc")
    check(post == {"request_sha256": sha(request), "size": len(request)} and ticket == intent == entry["ticket"]
          and inner.hex_id(ticket["ticket_id"], 32) and ticket["request_sha256"] == sha(request)
          and ticket["owner"] == contract["scope"]["owner"] and ticket["run_id"] == contract["scope"]["run_id"]
          and ticket["seed_tip"] == contract["seed_tip"], "LIVE_TICKET_BINDING")
    entered = c.utc(entry["entered_utc"])
    if mode == c.NATIVE:
        approval = contract["approval"]
        c.validate_budget(approval["budget"], contract["scope"]["source_git_sha"], approval["github_run_id"],
                          now=entered)
    provider.receipt_facts(receipt, contract, entry)
    check(receipt["status"] == 200 and receipt["response_size"] > 0, "COMPLETE_HTTP_RESPONSE")
    choice = provider.verify_selection(selection, receipt, contract)
    if mode == c.STUB:
        raw = bytes_for(stub_response, c.RESPONSE_CAP)
        check(not SECRET.search(raw) and canonical(provider.parse(raw, receipt, contract)) ==
              canonical(selection), "STUB_BYTES")
    else:
        check(stub_response is None, "PRIVATE_RESPONSE")
    return choice, selection


def verify(raw, source, expected_sha):
    check(inner.hex_id(source, 40) and inner.hex_id(expected_sha, 64)
          and 0 < len(raw) <= LIMIT and sha(raw) == expected_sha, "BUNDLE_ANCHOR")
    row = strict(raw)
    check(type(row) is dict, "BUNDLE_SHAPE")
    if set(row) < FIELDS:
        return {"status": "UNAVAILABLE", "missing": sorted(FIELDS - set(row))}
    check(set(row) == FIELDS and canonical(row) == raw and row["schema"] == "rpf110-live-witness-v1"
          and row["kind"] in (c.NATIVE, c.STUB, c.B0) and row["issuer"] == "NOT_ESTABLISHED"
          and not SECRET.search(raw.replace(c.PRICING.encode(), b"")), "BUNDLE_SCOPE")
    kind, approval = row["kind"], row["approval"]
    if kind == c.NATIVE:
        c.validate_approval(approval, source)
    frozen, seed_view, seed, final, choice, transactions = business(
        bytes_for(row["business_wal"], ledger.MAX_BYTES), row["authority"], source)
    contract = c.freeze(frozen, seed_view, seed, kind, approval)
    events = presend_rows(bytes_for(row["presend_wal"], TRACE_LIMIT))
    check(len(events) >= 5 and events[0]["kind"] == "OPEN" and events[0]["body"] == contract, "FROZEN_LIVE")
    request = bytes_for(row["request"], c.BODY_CAP)
    check(request == c.request(contract) and not SECRET.search(request), "FROZEN_REQUEST")
    phase = "STOPPED" if choice == inner.STOP else "UNKNOWN"
    terminal, late, denied = events[-3:]
    check((terminal["kind"], late["kind"], denied["kind"]) == (phase, "LOCAL_TERMINAL_PROBE", "DENIED")
          and late["body"] == {"request_sha256": sha(request), "size": len(request)}
          and denied["body"] == {"phase": phase, "ledger_tip": final["tip"]}, "TERMINAL_DENIAL")
    selected = None
    if kind == c.B0:
        check(len(events) == 5 and events[1]["kind"] == "BASELINE_CHOICE"
              and events[1]["body"] == {"candidate_id": inner.ORDER} and choice == inner.ORDER
              and row["stub_response"] is None, "B0_BINDING")
    else:
        chosen, selected = wire(events[1:-3], contract, request, row["stub_response"])
        check(chosen == choice, "CHOICE_EFFECT")
    check(terminal["body"] == {"candidate_id": choice, "ledger_tip": final["tip"],
                               "selection_sha256": inner.digest(selected) if selected else None}, "TERMINAL_BINDING")
    snapshot = None if choice == inner.STOP else row["authority"][choice]["after"]["snapshot"]
    effect = None
    if snapshot:
        state = snapshot["config"] if choice == inner.OPS else snapshot["order"]
        effect = {"revision": state["revision"], "receipt_count": len(snapshot["receipts"]),
                  **({"release": state["release"]} if choice == inner.OPS else
                     {"refunded_minor": state["refunded_minor"], "status": state["status"]})}
    # The seed pin is run-local. The visible fact and budget are comparable across owners.
    comparable = {"candidates": contract["feedback"]["candidates"],
                  "seed": {key: contract["feedback"]["seed"][key] for key in ("domain", "outcome")},
                  "remaining": contract["feedback"]["remaining"], "continuations": contract["continuation_budget"]}
    return {"status": "PORTABLE_REPLAY", "scope": frozen["scope"], "kind": kind, "choice": choice,
            "comparable": comparable, "effect": effect, "business_transactions": transactions,
            "terminal": phase, "selection": selected,
            "provider_requests": int(kind == c.NATIVE), "provider_usage": selected["usage"] if kind == c.NATIVE
            else "NOT_RUN", "provider_cost": selected["estimated_cost"] if kind == c.NATIVE else "NOT_RUN",
            "provider_authenticity": "PROVIDER_AUTHENTICITY_NOT_INDEPENDENTLY_VERIFIED" if kind == c.NATIVE
            else "NOT_RUN", "post_terminal_reservations": 0, "post_terminal_business_writes": 0,
            "post_terminal_send_entries": 0, "issuer": "NOT_ESTABLISHED", "selection_causality": "NOT_PROVEN",
            "fault": inner.faults(frozen["catalog"][choice], triggered=True, observed=True) if choice != inner.STOP
            else {"planned": False, "triggered": False, "observed": False, "agent_exposed": False},
            "release_eligible": False}


def verify_comparison(raw, source, expected_sha):
    check(0 < len(raw) <= COMPARISON_LIMIT and sha(raw) == expected_sha, "COMPARISON_ANCHOR")
    row = inner.exact(strict(raw), "schema", "source", "explorer", "baseline", "projection")
    check(canonical(row) == raw and row["schema"] == "rpf110-live-comparison-v1"
          and row["source"] == source, "COMPARISON_SCOPE")
    a = verify(bytes_for(row["explorer"], LIMIT), source, row["explorer"]["sha256"])
    b = verify(bytes_for(row["baseline"], LIMIT), source, row["baseline"]["sha256"])
    check(a["kind"] in (c.NATIVE, c.STUB) and b["kind"] == c.B0 and a["comparable"] == b["comparable"]
          and all(a["scope"][key] != b["scope"][key] for key in ("owner", "run_id")), "COMPARISON_FAIRNESS")
    expected = {"schema": "rpf110-demo-v2", "explorer": a, "baseline": b, "causality": "NOT_PROVEN",
                "comparison": "OBSERVED_SINGLE_TRIAL" if a["kind"] == c.NATIVE else "LOCAL_STUB_CONTROL"}
    check(canonical(expected) == canonical(row["projection"]), "COMPARISON_PROJECTION")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("source")
    parser.add_argument("sha256")
    parser.add_argument("--comparison", action="store_true")
    args = parser.parse_args()
    with args.bundle.open("rb") as file:
        raw = file.read((COMPARISON_LIMIT if args.comparison else LIMIT) + 1)
    result = (verify_comparison if args.comparison else verify)(raw, args.source, args.sha256)
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
