"""Portable fixture verifier. Inputs are bundle bytes and expected source/content pins."""
from base64 import b64decode
import re

from . import pge_r106_contracts as inner, pge_r106_ledger as ledger
from . import pge_r108_candidate as candidate, pge_r108_contracts as c
from .pge_r107_contracts import project
from .pge_r107_host import application
from .pge_r108_controller_adapter import verdict
from .sdk_presend_contracts import canonical, check, sha, strict

MAX_BUNDLE = 256 * 1024
MAX_PRESEND = 64 * 1024
MEMBERS = {"schema", "kind", "issuer", "presend_wal", "business_wal", "authority", "physical", "strategy"}
PHYSICAL = {"provider": "NOT_RUN", "provider_usage": "NOT_RUN", "sdk": "NOT_RUN", "http": "NOT_RUN"}
SECRET = re.compile(rb'(?i)(bearer |sk-(?:proj-)?[a-z0-9_-]{12,}|https?://|[A-Z]:\\|\.env\b)')


def bytes_for(row, limit):
    inner.exact(row, "sha256", "size", "base64")
    check(type(row["base64"]) is str and len(row["base64"]) <= (limit + 2) // 3 * 4, "B64_BOUND")
    raw = b64decode(row["base64"], validate=True)
    check(0 < len(raw) <= limit and canonical(row) == canonical(application(raw)), "BYTES_BINDING")
    return raw


def presend_rows(raw):
    check(raw.endswith(b"\n"), "PRESEND_TORN")
    rows = []
    tip = "0" * 64
    for index, line in enumerate(raw.split(b"\n")[:-1], 1):
        row = inner.exact(strict(line), "revision", "previous", "kind", "body", "sha256")
        core = {k: v for k, v in row.items() if k != "sha256"}
        check(type(row["revision"]) is int and row["revision"] == index and row["previous"] == tip
              and row["sha256"] == inner.digest(core) and canonical(row) == line, "PRESEND_CHAIN")
        tip = row["sha256"]
        rows.append(row)
    return rows


def business(raw, authority, source):
    state, rows = ledger.replay(raw)
    frozen = state["frozen"]
    check(frozen["scope"]["source_git_sha"] == source and state["phase"] == "STOPPED", "BUSINESS_SCOPE")
    expected = {}
    live = ledger.initial(frozen)
    rounds = []
    for row in rows:
        live = ledger.transition(live, row)
        if row["kind"] == "CLAIMED":
            rounds.append(row["body"]["proposal"]["candidate_id"])
        if row["kind"] == "AUTHORITY_BEFORE":
            before = row["body"]
        if row["kind"] == "WRITE_INTENT":
            intent = row["sha256"]
        if row["kind"] == "AUTHORITY_AFTER":
            after = row["body"]
        if row["kind"] == "VERIFIED":
            choice = live["candidate"]
            current = verdict(frozen["catalog"][choice], before, after, intent)
            check(canonical(row["body"]["verdict"]) == canonical(current), "ORACLE_PIN")
            expected[choice] = {"before": before, "after": after}
            if choice == inner.SEED:
                seed_view, seed = ledger.view(live), current
    check(rounds in ([inner.SEED], [inner.SEED, inner.ORDER], [inner.SEED, inner.OPS])
          and canonical(expected) == canonical(authority) and set(expected) == set(rounds), "AUTHORITY_MEMBERS")
    if len(rounds) == 1:
        check(not state["latched"], "STOP_LATCH")
        choice = inner.STOP
    else:
        check(state["latched"] and state["remaining"] == inner.ZERO, "UNKNOWN_LATCH")
        choice = rounds[1]
    return frozen, seed_view, seed, state, choice, len(rounds)


def verify(raw, expected_source, expected_sha256):
    check(inner.hex_id(expected_source, 40) and inner.hex_id(expected_sha256, 64) and
          0 < len(raw) <= MAX_BUNDLE and sha(raw) == expected_sha256, "BUNDLE_ANCHOR")
    row = strict(raw)
    check(type(row) is dict, "BUNDLE_SHAPE")
    if set(row) < MEMBERS:
        return {"status": "UNAVAILABLE", "missing": sorted(MEMBERS - set(row))}
    check(set(row) == MEMBERS and canonical(row) == raw and not SECRET.search(raw)
          and row["schema"] == "rpf108-witness-v1" and row["kind"] == "FIXTURE_PORTABLE_REPLAY"
          and row["issuer"] == "NOT_ESTABLISHED" and row["physical"] == PHYSICAL
          and row["strategy"] in ("SIMULATED_EXPLORER", "FIXED_ORDER_B0"), "BUNDLE_SCHEMA")
    frozen, seed_view, seed, final, choice, count = business(
        bytes_for(row["business_wal"], ledger.MAX_BYTES), row["authority"], expected_source)
    contract = c.freeze(frozen["scope"], seed_view, project(frozen, seed_view, seed), row["strategy"])
    events = presend_rows(bytes_for(row["presend_wal"], MAX_PRESEND))
    terminal = "STOPPED" if choice == inner.STOP else "UNKNOWN"
    check([e["kind"] for e in events] ==
          ["OPEN", "MODEL_POST_RECEIVED", "PROVIDER_RESERVE", "SEND_INTENT", "SIMULATED_SEND_ENTRY",
           "SIMULATED_RESPONSE", "TOOL_CALLBACK", terminal, "MODEL_POST_RECEIVED", "DENIED"], "PRESEND_SEQUENCE")
    opened, post, reserve, intent, entry, response, tool, end, late, denied = (e["body"] for e in events)
    request = c.request(contract)
    check(opened == {"contract": contract} and bytes_for(post, c.LIMIT) == bytes_for(late, c.LIMIT) == request,
          "FEEDBACK_REQUEST")
    req_sha = sha(request)
    check(reserve == {"request_sha256": req_sha, "ledger_tip": seed_view["tip"]}
          and intent == {"request_sha256": req_sha, "mode": "SIMULATED_ONLY"}
          and entry == {"request_sha256": req_sha}, "PRESEND_BINDING")
    inner.exact(response, "application", "elapsed_ms")
    response_raw = bytes_for(response["application"], c.LIMIT)
    inner.exact(tool, "application", "selected")
    tool_raw = bytes_for(tool["application"], c.LIMIT)
    check(not SECRET.search(request + response_raw + tool_raw), "PRIVATE_WIRE")
    selected = candidate.parse(response_raw, req_sha, response["elapsed_ms"])
    check(tool["selected"] == selected and candidate.callback(tool_raw, selected) == choice
          and (row["strategy"] != "FIXED_ORDER_B0" or choice == c.CHOICES[0]), "SELECTED_BUSINESS")
    check(end == {"ledger_tip": final["tip"], "candidate_id": choice} and
          denied == {"reason": "NOT_ADMITTED" if choice == inner.STOP else "UNKNOWN_LATCH",
                     "ledger_tip": final["tip"]}, "TERMINAL_DENIAL")
    return {"status": "FIXTURE_PORTABLE_REPLAY", "scope": frozen["scope"], "choice": choice,
            "business_transactions": count, "simulated_model_reservations": 1,
            "post_terminal_reservations": 0, "post_terminal_writes": 0, "issuer": "NOT_ESTABLISHED",
            "provider": "NOT_RUN"}
