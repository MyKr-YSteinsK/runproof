"""Independent case replay over closed files or a sanitized public projection."""
import argparse
from pathlib import Path
import re

from .ops_oracle import expected_receipt, initial_state
from .product_sdk_contracts import (DOMAINS, FORWARDS, POSTS, STOP, SUCCESS, binding, call, feedback,
                                    flags, hex_id, reconciliation, response, select_ops, tool_value, validate_frozen,
                                    validate_request)
from .product_sdk_host import EFFECT_EVENTS, MAX_WAL
from .product_sdk_target import case_scope, read, readback, safe
from .sdk_presend_contracts import LIMIT, PINS, canonical, check, sha, strict

SCHEMA = "rpf104-case-projection-v1"
NEGATIVES = tuple(f"reserve_{domain}_{role}" for domain in DOMAINS for role in ("TARGET", "EXPLORER")) + (
    "retry_order", "cross_domain_write", "forged_owner", "forged_contract")


def exact(row, *fields):
    check(type(row) is dict and set(row) == set(fields), "EVIDENCE_FIELDS")
    return row


def positive(value):
    return type(value) is int and value > 0


def replay(raw):
    check(0 < len(raw) <= MAX_WAL and raw.endswith(b"\n"), "WAL_TORN")
    rows = []
    prev, stamp, latched = "0" * 64, 0, False
    for line in raw.split(b"\n")[:-1]:
        row = exact(strict(line), "seq", "prev", "kind", "body", "time_ns", "sha256")
        body = {k: v for k, v in row.items() if k != "sha256"}
        check(type(row["seq"]) is int and row["seq"] == len(rows) and row["prev"] == prev
              and positive(row["time_ns"]) and row["time_ns"] >= stamp and type(row["kind"]) is str
              and type(row["body"]) is dict and canonical(row) == line and row["sha256"] == sha(canonical(body)),
              "WAL_CHAIN")
        check(not (latched and row["kind"] in EFFECT_EVENTS), "POST_UNKNOWN_EFFECT")
        check(not (latched and row["kind"] == "UNKNOWN_OBSERVED"), "DUPLICATE_UNKNOWN")
        latched |= row["kind"] == "UNKNOWN_OBSERVED"
        prev, stamp = row["sha256"], row["time_ns"]
        rows.append(row)
    check(1 <= len(rows) <= 80, "WAL_ROWS")
    return rows


def snapshot(frozen, domain, after):
    contract = frozen["contracts"][domain]
    effect = contract["effect"]
    environment = contract["execution"]["environment_id"]
    if domain == "order":
        value = {"order_id": effect["order_id"], "paid_minor": effect["amount_minor"],
                 "refunded_minor": effect["amount_minor"] if after else 0, "currency": effect["currency"],
                 "status": "REFUNDED" if after else "PAID", "revision": int(after)}
        receipt = {**effect, "status": "COMMITTED", "committed_revision": 1,
                   "receipt_id": "receipt-" + sha(canonical({"environment": environment,
                                                              "operation_id": effect["operation_id"]}))[:24]}
        return {"order": value, "receipts": [receipt] if after else []}
    value = initial_state(effect)
    if after:
        value.update(release="release-v2", revision=1, effect_count=1, operation_id=effect["operation_id"])
    return {"config": value, "receipts": [expected_receipt(effect, environment)] if after else []}


def verify_environment(row):
    exact(row, "python", "exe_sha256", "pins", "wheels")
    check(type(row["python"]) is str and re.fullmatch(r"3\.12\.[0-9]{1,3}", row["python"])
          and hex_id(row["exe_sha256"], 64) and row["pins"] == PINS
          and type(row["wheels"]) is dict and set(row["wheels"]) == set(PINS)
          and all(hex_id(value, 64) for value in row["wheels"].values()), "ENVIRONMENT_IDENTITY")
    return row["exe_sha256"]


def verify_case(witness, *, sdk_posts=None, receiver_raw=None, final_snapshots=None):
    exact(witness, "schema", "frozen", "environment", "wal", "sdk", "sdk_launch", "sdk_exit",
          "receiver_ready", "receiver_launch", "receiver_exit", "transfers")
    check(witness["schema"] == SCHEMA, "CASE_SCHEMA")
    frozen = validate_frozen(witness["frozen"])
    case = frozen["case"]
    scope = sha(canonical(frozen))
    exe = verify_environment(witness["environment"])
    rows = replay(b"".join(canonical(row) + b"\n" for row in witness["wal"]))
    offset = 0

    def event(kind, body=None):
        nonlocal offset
        check(offset < len(rows) and rows[offset]["kind"] == kind, "EVENT_ORDER")
        row = rows[offset]
        check(body is None or canonical(row["body"]) == canonical(body), "EVENT_BODY")
        offset += 1
        return row

    event("CASE_OPEN", {"contract_sha256": scope})
    host = exact(event("HOST_LISTEN")["body"], "pid", "host", "port", "exe_sha256")
    sdk = exact(witness["sdk"], "pid", "exe_sha256", "packages", "callbacks", "terminal")
    launch = exact(witness["sdk_launch"], "pid", "start_ns", "host", "exe_sha256")
    done = exact(witness["sdk_exit"], "pid", "exit", "exit_ns", "stdout_sha256")
    ready = exact(witness["receiver_ready"], "scope_sha256", "host", "port", "pid", "exe_sha256",
                  "nonce", "ready_ns")
    rstart = exact(witness["receiver_launch"], "pid", "nonce", "exe_sha256", "start_ns")
    rdone = exact(witness["receiver_exit"], "pid", "exit", "exit_ns", "exe_sha256")
    pids = {host["pid"], sdk["pid"], ready["pid"]}
    check(len(pids) == 3 and all(positive(pid) for pid in pids)
          and host["host"] == ready["host"] == "127.0.0.1"
          and all(positive(row["port"]) and row["port"] < 65536 for row in (ready, host))
          and host["port"] != ready["port"] and ready["scope_sha256"] == scope
          and launch["host"] == host and sdk["pid"] == launch["pid"] == done["pid"]
          and ready["pid"] == rstart["pid"] == rdone["pid"]
          and all(row["exe_sha256"] == exe for row in (host, sdk, launch, ready, rstart, rdone))
          and ready["nonce"] == rstart["nonce"] and hex_id(ready["nonce"], 64)
          and type(done["exit"]) is int and type(rdone["exit"]) is int and done["exit"] == rdone["exit"] == 0
          and done["stdout_sha256"] == sha(canonical(sdk) + b"\n")
          and all(positive(x) for x in (rstart["start_ns"], ready["ready_ns"], launch["start_ns"],
                                        done["exit_ns"], rdone["exit_ns"]))
          and rstart["start_ns"] <= ready["ready_ns"] <= launch["start_ns"] <= done["exit_ns"]
          and ready["ready_ns"] <= rdone["exit_ns"], "PROCESS_BINDING")
    check(type(sdk["packages"]) is dict and set(sdk["packages"]) == set(PINS), "SDK_PACKAGES")
    for name, package in sdk["packages"].items():
        exact(package, "version", "source_sha256", "record_sha256")
        check(package["version"] == PINS[name] and hex_id(package["source_sha256"], 64)
              and hex_id(package["record_sha256"], 64), "SDK_PACKAGE")

    tools, callbacks, effects = [], [], {}
    total = 0
    transfers = witness["transfers"]
    check(type(transfers) is list and len(transfers) == FORWARDS[case], "TRANSFER_COUNT")
    if sdk_posts is not None:
        check(len(sdk_posts) == POSTS[case] and receiver_raw is not None
              and len(receiver_raw) == len(transfers) and set(final_snapshots) == set(frozen["contracts"]),
              "PHYSICAL_MEMBER_COUNT")
    for number in range(1, POSTS[case] + 1):
        post = event("SDK_POST_RECEIVED")
        request = exact(post["body"], "number", "sha256", "bytes")
        check(type(request["number"]) is int and request["number"] == number and hex_id(request["sha256"], 64)
              and positive(request["bytes"]) and request["bytes"] <= LIMIT
              and launch["start_ns"] <= post["time_ns"] <= done["exit_ns"], "REQUEST_BINDING")
        if sdk_posts is not None:
            check(request == validate_request(frozen, sdk_posts[number - 1], tools), "REQUEST_BYTES")
        if case == "UNKNOWN" and number == 2:
            event("DENY", {"number": 2, "reason": "UNKNOWN_DURABLE", "sdk_echoed_unknown": True})
            break
        domain = "order" if number == 1 else "ops"
        if number == 2:
            verified = effects["order"]["feedback"]
            check(select_ops(frozen, verified, latched=False) == "SELECT_OPS", "POLICY_STOP")
            event("POLICY_DECISION", {"decision": "SELECT_OPS", "feedback_sha256": verified["sha256"],
                                      "policy": frozen["policy"]})
        ticket = {"request": request, "domain": domain, "role": "TARGET", "case_sha256": scope}
        event("PROVIDER_RESERVE", ticket)
        event("SEND_BEGIN", ticket)
        entry = event("SEND_ENTRY", ticket)
        returned = event("SEND_RETURN", ticket)
        transfer = exact(transfers[number - 1], "sender", "receiver")
        sender = exact(transfer["sender"], "pid", "ticket", "nonce", "entry_ns", "return_ns", "sha256", "bytes")
        recv = exact(transfer["receiver"], "scope_sha256", "number", "pid", "nonce", "bytes", "sha256", "received_ns")
        check(canonical(sender["ticket"]) == canonical(ticket) and sender["pid"] == host["pid"]
              and recv["pid"] == ready["pid"] and sender["nonce"] == recv["nonce"] == ready["nonce"]
              and recv["scope_sha256"] == scope and recv["number"] == number
              and sender["sha256"] == recv["sha256"] == request["sha256"]
              and type(sender["bytes"]) is int and type(recv["bytes"]) is int
              and sender["bytes"] == recv["bytes"] == request["bytes"]
              and positive(sender["return_ns"]) and positive(recv["received_ns"])
              and sender["entry_ns"] == entry["time_ns"]
              and entry["time_ns"] <= sender["return_ns"] <= returned["time_ns"] <= done["exit_ns"]
              and entry["time_ns"] <= recv["received_ns"] <= min(rdone["exit_ns"], returned["time_ns"]),
              "TRANSFER_BINDING")
        if receiver_raw is not None:
            check(receiver_raw[number - 1] == sdk_posts[number - 1], "RECEIVER_BYTES")
        total += recv["bytes"]
        event("SCRIPTED_RESPONSE", {"number": number, "sha256": sha(canonical(response(frozen, number)))})
        if number == 3:
            continue
        identity = binding(frozen, domain)
        event("TOOL_ACCEPTED", identity)
        before = event("AUTHORITY_BEFORE")["body"]
        event("WRITE_INTENT", identity)
        event("WRITE_COMMIT", identity)
        lost = case == "UNKNOWN"
        if lost:
            event("UNKNOWN_OBSERVED", identity)
        after = event("AUTHORITY_AFTER")["body"]
        for row, committed in ((before, False), (after, True)):
            check(canonical(row["snapshot"]) == canonical(snapshot(frozen, domain, committed))
                  and row["pid"] not in pids, "AUTHORITY_FACTS")
        if final_snapshots is not None:
            check(canonical(final_snapshots[domain]["snapshot"]) == canonical(after["snapshot"])
                  and final_snapshots[domain]["binding"] == identity
                  and final_snapshots[domain]["pid"] not in pids, "AUTHORITY_DB_MISMATCH")
        fault = flags(frozen["contracts"][domain], triggered=lost, observed=lost)
        verified = feedback(frozen, domain, before, after, fault)
        check(verified["value"]["outcome"] == SUCCESS, "EFFECT_OUTCOME")
        if lost:
            outcome = reconciliation(frozen, before, after, verified)
            check(outcome == "COMMITTED", "RECONCILE_OUTCOME")
            event("READ_ONLY_RECONCILIATION", {"binding": identity, "outcome": outcome})
        feedback_event = event("VERIFIED_FEEDBACK", verified)
        if lost:
            for attempt in NEGATIVES:
                event("NEGATIVE_DENIAL", {"attempt": attempt})
        effects[domain] = {"feedback": verified, "feedback_time_ns": feedback_event["time_ns"],
                           "fault": flags(frozen["contracts"][domain], triggered=lost,
                                          observed=lost, agent_exposed=lost)}
        value = tool_value(domain, None if lost else verified)
        event("TOOL_RETURN_TO_SDK", {"domain": domain, "value": value})
        tools.append((domain, value))
        expected = call(frozen, domain)
        callbacks.append({"call_id": expected["id"], "name": expected["function"]["name"], "value": value})
    event("SDK_TERMINAL", done)
    terminal = ({"status": "COMPLETED", "output_sha256": sha(STOP.encode()), "sdk_reported_requests": 3,
                 "sdk_reported_tool_calls": 2, "usage_kind": "SYNTHETIC_LOCAL_MODEL_RESPONSE"} if case == "NORMAL"
                else {"status": "DENIED_AFTER_UNKNOWN", "http_status": 409, "usage_kind": "UNAVAILABLE"})
    check(offset == len(rows) and canonical(sdk["callbacks"]) == canonical(callbacks)
          and canonical(sdk["terminal"]) == canonical(terminal)
          and total <= frozen["budget"]["max_receiver_bytes"], "TERMINAL_BINDING")
    return {"case": case, "verification": "RAW_CONTENT_CHECKED" if sdk_posts is not None else "PUBLIC_PROJECTION_CHECKED",
            "effect_outcome": SUCCESS, "agent_outcome": terminal["status"], "platform_outcome": "COMPLETED",
            "sdk_posts": POSTS[case], "tool_callbacks": len(callbacks), "business_writes": len(effects),
            "forwards": len(transfers), "receiver_bytes": total, "effects": effects,
            "post_unknown_reserves": 0 if case == "UNKNOWN" else None,
            "post_unknown_sends": 0 if case == "UNKNOWN" else None,
            "post_unknown_writes": 0 if case == "UNKNOWN" else None,
            "issuer": "NOT_ESTABLISHED", "provider_kind": "SCRIPTED_LOCAL",
            "external_provider_requests": 0, "real_explorer": "NOT_RUN"}


def load_physical(folder):
    frozen = validate_frozen(strict(read(folder / "contract.json", 16384)))
    case_scope(folder, frozen)
    case = frozen["case"]
    if case == "UNKNOWN":
        safe(folder / "ops.sqlite", absent=True)
    def member(name):
        return strict(read(folder / name, 8192))
    data = {"schema": SCHEMA, "frozen": frozen, "environment": strict(read(folder.parent / "environment.json", 8192)),
            "wal": replay(read(folder / "wal.jsonl", MAX_WAL)), "sdk": member("sdk-output.json"),
            "sdk_launch": member("sdk-launch.json"), "sdk_exit": member("sdk-exit.json"),
            "receiver_ready": member("receiver-ready.json"), "receiver_launch": member("receiver-launch.json"),
            "receiver_exit": member("receiver-exit.json"),
            "transfers": [{"sender": member(f"sender-{i}.json"), "receiver": member(f"receiver-{i}.json")}
                          for i in range(1, FORWARDS[case] + 1)]}
    verify_case(data, sdk_posts=[read(folder / f"sdk-post-{i}.raw", LIMIT) for i in range(1, POSTS[case] + 1)],
                receiver_raw=[read(folder / f"receiver-{i}.raw", LIMIT) for i in range(1, FORWARDS[case] + 1)],
                final_snapshots={domain: readback(folder, frozen, domain) for domain in frozen["contracts"]})
    for row in (data["receiver_ready"], data["receiver_launch"],
                *(record[k] for record in data["transfers"] for k in ("sender", "receiver"))):
        row["nonce"] = sha(b"rpf104-public-nonce\0" + row["nonce"].encode())
    verify_case(data)
    return data


def physical_main():
    print(canonical(load_physical(Path.cwd())).decode(), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    args = parser.parse_args()
    try:
        print(canonical(load_physical(args.case)).decode())
    except Exception:
        print("RPF104_ORACLE_REJECTED")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
