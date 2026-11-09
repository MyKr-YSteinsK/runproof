"""Independent stdlib verifier for SDK-backed local admission evidence."""
import argparse
import json
import re

from .sdk_presend_contracts import (BUDGET, CALL, CASES, LIMIT, PINS, STOP, bounded, canonical,
                                   check, identity, owner_path, response, safe, sha, strict,
                                   tool_value, validate_request)


def replay(raw):
    check(raw.endswith(b"\n") and len(raw) <= 131072, "TORN_WAL")
    rows = []
    prev = "0" * 64
    unknown = False
    for line in raw.split(b"\n")[:-1]:
        row = strict(line)
        body = {"seq": len(rows), "prev": prev, "kind": row["kind"], "body": row["body"]}
        check(type(row["seq"]) is int and canonical(row) == line
              and row == {**body, "sha256": sha(canonical(body))}, "WAL_CHAIN")
        kind = row["kind"]
        if unknown and kind in ("PROVIDER_RESERVE", "SEND_BEGIN", "SEND_ENTRY", "SEND_RETURN"):
            raise ValueError("POST_UNKNOWN_" + kind)
        unknown |= kind == "UNKNOWN_OBSERVED"
        rows.append(row)
        prev = row["sha256"]
    check(1 <= len(rows) <= 40, "WAL_LENGTH")
    return rows


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def receiver_identity(owner, case, ready, launch, done):
    check(set(ready) == {"owner", "case", "host", "port", "pid", "exe_sha256", "nonce", "ready_ns"}
          and ready["case"] == case and ready["owner"] == owner and ready["host"] == "127.0.0.1"
          and type(ready["port"]) is int and 0 < ready["port"] < 65536
          and digest(ready["exe_sha256"]) and ready["exe_sha256"] == launch["exe_sha256"] == done["exe_sha256"]
          and all(type(p) is int for p in (launch["pid"], ready["pid"], done["pid"]))
          and ready["pid"] > 0 and launch["pid"] == ready["pid"] == done["pid"]
          and digest(ready["nonce"]) and ready["nonce"] == launch["nonce"]
          and type(done["exit"]) is int
          and all(type(t) is int for t in (launch["start_ns"], ready["ready_ns"], done["exit_ns"]))
          and 0 < launch["start_ns"] <= ready["ready_ns"] <= done["exit_ns"], "RECEIVER_LAUNCH")
    return ready, launch, done


def receiver_payload(owner, case, ready, done, index, raw, receipt):
    check(0 < len(raw) <= LIMIT and all(type(receipt.get(k)) is int for k in ("index", "pid", "bytes"))
          and receipt == {
        "index": index, "owner": owner, "case": case, "pid": ready["pid"], "nonce": ready["nonce"],
        "bytes": len(raw), "sha256": sha(raw), "received_ns": receipt["received_ns"],
    } and type(receipt["received_ns"]) is int and ready["ready_ns"] <= receipt["received_ns"] <= done["exit_ns"],
          "RECEIVER_BYTES")
    return len(raw)


def verify(owner, case, files, expected=None):
    check(case in CASES and re.fullmatch(r"[a-f0-9]{32}", owner), "CASE_IDENTITY")
    anchor = sha(canonical({name: sha(data) for name, data in files.items()}))
    check(expected is None or anchor == expected, "ANCHOR_MISMATCH")
    rows = replay(files["wal.jsonl"])
    base = {"case": case, "owner": owner, "source": identity(), "budget": BUDGET[case]}
    events = [("READY", base)]
    launch = strict(files["sdk-launch.json"])
    output = strict(files["sdk-output.json"])
    done = strict(files["sdk-exit.json"])
    host = launch["host"]
    ready, _, receiver_done = receiver_identity(owner, case, strict(files["receiver-ready.json"]),
                                                strict(files["receiver-launch.json"]),
                                                strict(files["receiver-exit.json"]))
    exe = launch["exe_sha256"]
    check(digest(exe) and type(host["pid"]) is int and type(ready["pid"]) is int
          and type(output["pid"]) is int and min(host["pid"], ready["pid"], output["pid"]) > 0
          and len({host["pid"], ready["pid"], output["pid"]}) == 3, "PROCESS_PID")
    check(set(host) == {"pid", "port", "host", "exe_sha256"} and host["host"] == "127.0.0.1"
          and host["exe_sha256"] == exe and type(host["port"]) is int and 0 < host["port"] < 65536
          and launch["network"] == "HOST_LOOPBACK_ONLY" and launch["pid"] == output["pid"] == done["pid"]
          and output["exe_sha256"] == exe and done["exit"] == 0 and launch["start_ns"] <= done["exit_ns"]
          and done["stdout_sha256"] == sha(files["sdk-output.json"]), "SDK_PROCESS_BINDING")
    check(ready["port"] != host["port"] and ready["exe_sha256"] == exe and receiver_done["exit"] == 0
          and ready["ready_ns"] <= launch["start_ns"], "RECEIVER_LAUNCH")
    packages = output["packages"]
    check(set(packages) == set(PINS), "SDK_PACKAGE_SET")
    for name, version in PINS.items():
        package = packages[name]
        check(set(package) == {"version", "source_sha256", "record_sha256"} and package["version"] == version
              and digest(package["source_sha256"]) and digest(package["record_sha256"]), "SDK_PACKAGE")
    check(output["tool_callbacks"] == [{"call_id": CALL, "value": tool_value(case)}], "SDK_CALLBACK")
    terminal = output["terminal"]
    if case == "NORMAL":
        check(terminal["status"] == "COMPLETED" and terminal["output_sha256"] == sha(STOP.encode())
              and terminal["sdk_reported_requests"] == 2 and terminal["sdk_reported_tool_calls"] == 1
              and terminal["usage_kind"] == "SYNTHETIC_LOCAL_MODEL_RESPONSE", "NORMAL_TERMINAL")
    else:
        check(terminal == {"status": "DENIED_AFTER_UNKNOWN", "error_type": "ModelHTTPError",
                           "http_status": 409, "usage_kind": "UNAVAILABLE"}
              and strict(files["unknown-intent.json"]) == {"case": case, "call_id": CALL}, "UNKNOWN_TERMINAL")
    events.append(("HOST_LISTEN", host))
    responses = []
    total = 0
    for i in (1, 2):
        if i == 2:
            if case == "UNKNOWN":
                events.append(("UNKNOWN_OBSERVED", {"call_id": CALL}))
            events.append(("TOOL_RETURN_TO_SDK", {"call_id": CALL, "value": tool_value(case)}))
        raw = files[f"sdk-post-{i}.raw"]
        validate_request(raw, i, case)
        events.append(("SDK_POST_RECEIVED", {"number": i, "sha256": sha(raw), "bytes": len(raw)}))
        if i > BUDGET[case]:
            events.append(("DENY", {"number": i, "reason": "UNKNOWN_DURABLE"}))
            continue
        receiver_raw = files[f"receiver-{i}.raw"]
        receipt = strict(files[f"receiver-{i}.json"])
        sender = strict(files[f"sender-{i}.json"])
        check(receiver_raw == raw, "RECEIVER_BYTES")
        receiver_payload(owner, case, ready, receiver_done, i, receiver_raw, receipt)
        core = {"number": i, "domain": "order", "role": "TARGET", "request_sha256": sha(raw)}
        ticket = {**core, "id": sha(canonical({"ready": rows[0]["sha256"], "ticket": core}))}
        check(sender == {"pid": host["pid"], "ticket": ticket, "nonce": ready["nonce"],
                         "bytes": len(raw), "sha256": sha(raw), "entry_ns": sender["entry_ns"],
                         "return_ns": sender["return_ns"]}
              and launch["start_ns"] <= sender["entry_ns"] <= sender["return_ns"] <= done["exit_ns"]
              and sender["entry_ns"] <= receipt["received_ns"] <= receiver_done["exit_ns"], "SEND_RECEIPT")
        events.extend((kind, ticket) for kind in ("PROVIDER_RESERVE", "SEND_BEGIN", "SEND_ENTRY", "SEND_RETURN"))
        scripted = response(case, i)
        responses.append(scripted["id"])
        events.append(("SCRIPTED_MODEL_RESPONSE", {"number": i, "response_id": scripted["id"],
                                                   "sha256": sha(canonical(scripted))}))
        total += len(receiver_raw)
    events.append(("SDK_TERMINAL", {"sha256": done["stdout_sha256"], "exit": 0}))
    check(canonical([(r["kind"], r["body"]) for r in rows]) == canonical(events), "TRANSCRIPT_SEMANTICS")
    check(set(files) == set(member_names(case)), "EVIDENCE_SET")
    return {"status": "VERIFIED_ANCHORED" if expected else "CONTENT_CHECKED_LOCAL",
            "case": case, "anchor": anchor, "sdk_posts": 2, "tool_callbacks": 1,
            "provider_tickets": BUDGET[case], "send_entries": BUDGET[case], "received_bytes": total,
            "post_unknown_reserves": 0, "post_unknown_send_entries": 0,
            "response_ids": responses, "sdk_terminal": terminal["status"], "packages": packages,
            "python_exe_sha256": exe, "provider_requests": 0, "issuer": "NOT_ESTABLISHED"}


def member_names(case):
    names = ["wal.jsonl", "sdk-launch.json", "sdk-output.json", "sdk-exit.json",
             "receiver-ready.json", "receiver-launch.json", "receiver-exit.json",
             "sdk-post-1.raw", "sdk-post-2.raw"]
    for index in range(1, BUDGET[case] + 1):
        names.extend((f"sender-{index}.json", f"receiver-{index}.json", f"receiver-{index}.raw"))
    if case == "UNKNOWN":
        names.append("unknown-intent.json")
    return names


def inspect_case(owner, case, expected=None):
    check(case in CASES, "CASE_SCOPE")
    folder = safe(owner_path(owner) / case)
    check(not safe(folder / "active").exists(), "PERSISTENCE_UNCERTAIN")
    names = member_names(case)
    allowed = set(names) | {"writer.lock", "diagnostic-context.json", "diagnostic.json"}
    check({entry.name for entry in folder.iterdir()} <= allowed, "UNEXPECTED_CASE_MEMBER")
    files = {name: bounded(folder / name, 131072 if name == "wal.jsonl" else LIMIT) for name in names}
    return verify(owner, case, files, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner")
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_case(args.owner, args.case, args.expected_sha256), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
