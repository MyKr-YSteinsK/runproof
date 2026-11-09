"""Independent offline verifier. No Host or transport imports."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[3] / ".local" / "rpf-101-provider-presend"
NAMES = ("provider_barrier.py", "provider_transport.py", "provider_receipt_verify.py")
CASES = {"unknown-empty", "ready-restart", "unknown-restart", "send-first", "unknown-first",
         "flush-failure", "write-failure", "torn"}
PAYLOAD = b"RPF-101 synthetic local transport payload\n"


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def sha(raw):
    return sha256(raw).hexdigest()


def reject_unless(value, reason):
    if not value:
        raise ValueError(reason)


def decode(raw):
    def pairs(items):
        data = {}
        for key, val in items:
            reject_unless(key not in data, "DUPLICATE_KEY")
            data[key] = val
        return data
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    reject_unless(dump(value) == raw, "NONCANONICAL")
    return value


def source():
    return {name: sha(Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n")) for name in NAMES}


def bounded(path, maximum):
    reject_unless(path.is_absolute() and path.is_relative_to(ROOT), "OWNER_SCOPE")
    for item in reversed((path, *path.parents)):
        info = item.lstat()
        reject_unless(not stat.S_ISLNK(info.st_mode)
                      and not getattr(info, "st_file_attributes", 0) & 1024, "REPARSE")
    reject_unless(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= maximum, "MEMBER_TYPE_OR_SIZE")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        now = os.fstat(handle.fileno())
        reject_unless((info.st_ino, info.st_dev) == (now.st_ino, now.st_dev) and now.st_nlink == 1,
                      "MEMBER_REPLACED")
        data = handle.read(maximum + 1)
    reject_unless(len(data) <= maximum, "MEMBER_SIZE")
    return data


def replay(case, wal):
    reject_unless(case in CASES and wal.endswith(b"\n"), "TORN_OR_UNKNOWN_CASE")
    lines = wal.split(b"\n")[:-1]
    reject_unless(1 <= len(lines) <= 8, "WAL_LENGTH")
    previous = "0" * 64
    rows = []
    for index, line in enumerate(lines):
        row = decode(line)
        body = {key: row[key] for key in ("seq", "prev", "kind", "body")}
        reject_unless(set(row) == {*body, "sha256"} and type(row["seq"]) is int
                      and row["seq"] == index and row["prev"] == previous
                      and sha(dump(body)) == row["sha256"], "WAL_CHAIN")
        previous = row["sha256"]
        rows.append(row)
    initial = rows[0]["body"]
    reject_unless(rows[0]["kind"] == "READY" and
                  set(initial) == {"schema", "case", "source", "max_tickets", "max_sends", "receiver", "request_sha256"}
                  and initial["schema"] == "rpf101-presend-host-v1" and initial["case"] == case
                  and initial["source"] == source() and type(initial["max_tickets"]) is int
                  and initial["max_tickets"] == 1 and type(initial["max_sends"]) is int
                  and initial["max_sends"] == 1 and initial["request_sha256"] == sha(PAYLOAD), "READY_IDENTITY")
    ticket, unknown, phase = None, None, 0
    for row in rows[1:]:
        kind, body = row["kind"], row["body"]
        if kind == "UNKNOWN_OBSERVED":
            reject_unless(unknown is None and set(body) == {"domain"} and body["domain"] in ("order", "ops"), "UNKNOWN_SCHEMA")
            unknown = body
            continue
        if unknown is not None:
            raise ValueError("POST_UNKNOWN_" + ("NEW_RESERVE" if kind == "RESERVE" else "NEW_SEND"))
        if kind == "RESERVE":
            reject_unless(ticket is None and set(body) == {"domain", "role", "id", "request_sha256"}
                          and body["domain"] in ("order", "ops") and body["role"] in ("TARGET", "EXPLORER")
                          and body["request_sha256"] == sha(PAYLOAD), "TICKET_SCHEMA")
            core = {k: v for k, v in body.items() if k != "id"}
            reject_unless(sha(dump({"ready": rows[0]["sha256"], "ticket": core})) == body["id"], "TICKET_ID")
            ticket = body
        else:
            sequence = ("SEND_BEGIN", "SEND_ENTRY", "SEND_RETURN")
            reject_unless(ticket is not None and phase < len(sequence)
                          and kind == sequence[phase] and body == ticket, "SEND_SEQUENCE")
            phase += 1
    reject_unless(phase in (0, 3), "SEND_INCOMPLETE")
    return initial, ticket, unknown, phase


def verify_evidence(case, members, expected=None):
    anchor = sha(dump({name: sha(raw) for name, raw in members.items()}))
    reject_unless(expected is None or expected == anchor, "ANCHOR_MISMATCH")
    initial, ticket, unknown, phase = replay(case, members["wal"])
    names = {"wal"}
    if unknown:
        names.add("intent")
        reject_unless(decode(members["intent"]) == unknown, "UNKNOWN_INTENT")
    ready = initial["receiver"]
    if ready is not None:
        names.update({"ready", "launch", "exit", "raw", "receipt"})
        launch, done, receipt = (decode(members[name]) for name in ("launch", "exit", "receipt"))
        reject_unless(set(ready) == {"case", "host", "port", "pid", "exe_sha256", "nonce", "ready_ns"}
                      and decode(members["ready"]) == ready and ready["case"] == case
                      and ready["host"] == "127.0.0.1" and type(ready["port"]) is int
                      and 0 < ready["port"] < 65536 and type(ready["pid"]) is int and ready["pid"] > 0
                      and re.fullmatch(r"[a-f0-9]{64}", ready["exe_sha256"])
                      and re.fullmatch(r"[a-f0-9]{64}", ready["nonce"]), "RECEIVER_IDENTITY")
        reject_unless(launch == {"pid": ready["pid"], "exe_sha256": ready["exe_sha256"],
                                 "nonce": ready["nonce"], "start_ns": launch["start_ns"]}
                      and done == {"pid": ready["pid"], "exe_sha256": ready["exe_sha256"],
                                   "exit": 0, "exit_ns": done["exit_ns"]}
                      and 0 < launch["start_ns"] <= ready["ready_ns"] <= receipt["observed_ns"] <= done["exit_ns"],
                      "LAUNCH_EXIT_BINDING")
        raw = members["raw"]
        reject_unless(raw == (PAYLOAD if phase == 3 else b"") and
                      receipt == {"ready": ready, "connections": 1 if phase == 3 else 0,
                                  "bytes": len(raw), "sha256": sha(raw), "observed_ns": receipt["observed_ns"],
                                  "status": "ACTUAL_SOCKET_RECEIVED" if raw else "NO_BYTES_OBSERVED"},
                      "RECEIVER_BYTES")
        if phase == 3:
            names.add("sender")
            sender = decode(members["sender"])
            reject_unless(sender == {"case": case, "pid": sender["pid"], "exe_sha256": ready["exe_sha256"],
                                     "ticket_id": ticket["id"], "receiver_nonce": ready["nonce"],
                                     "bytes": len(raw), "sha256": sha(raw), "entry_ns": sender["entry_ns"],
                                     "return_ns": sender["return_ns"], "status": "SENDALL_RETURNED"}
                          and type(sender["pid"]) is int and sender["pid"] > 0 and sender["pid"] != ready["pid"]
                          and ready["ready_ns"] <= sender["entry_ns"] <= sender["return_ns"] <= receipt["observed_ns"],
                          "SENDER_RECEIPT")
    else:
        reject_unless(phase == 0, "RECEIVER_MISSING")
    if case in ("ready-restart", "unknown-restart"):
        names.update({"recovery", "recovery_launch"})
        recovery, process = (decode(members[name]) for name in ("recovery", "recovery_launch"))
        wanted = "SENT" if case == "ready-restart" else "DENIED"
        reject_unless(set(process) == {"pid", "exe_sha256", "exit", "start_ns", "exit_ns"}
                      and type(process["pid"]) is int and process["pid"] > 0
                      and process["pid"] != ready["pid"] and process["exit"] == 0
                      and process["exe_sha256"] == ready["exe_sha256"]
                      and ready["ready_ns"] <= process["start_ns"] <= process["exit_ns"]
                      and recovery == {"case": case, "pid": process["pid"],
                                       "exe_sha256": process["exe_sha256"], "decision": wanted}, "RECOVERY_IDENTITY")
        if wanted == "SENT":
            reject_unless(phase == 3 and sender["pid"] == process["pid"]
                          and process["start_ns"] <= sender["entry_ns"] <= sender["return_ns"] <= process["exit_ns"],
                          "RECOVERY_SEND")
        else:
            reject_unless(unknown and phase == 0, "RECOVERY_DENIAL")
    reject_unless(set(members) == names, "EVIDENCE_SET")
    return {"status": "VERIFIED_ANCHORED" if expected else "CONTENT_CHECKED_LOCAL",
            "case": case, "anchor": anchor, "received_bytes": len(members.get("raw", b"")),
            "send_entries": int(phase == 3), "unknown": bool(unknown),
            "pre_unknown_in_flight": bool(unknown and phase == 3), "issuer": "NOT_ESTABLISHED"}


def read_case(case):
    reject_unless(case in CASES, "CASE_SCOPE")
    session = ROOT / "sessions" / case
    wal = bounded(session / "wal.jsonl", 131072)
    reject_unless(not os.path.lexists(session / "active"), "PERSISTENCE_UNCERTAIN")
    initial, _, _, _ = replay(case, wal)
    members = {"wal": wal}
    for key, filename in (("intent", "unknown-intent.json"), ("sender", "sender-receipt.json"),
                          ("recovery", "recovery.json"), ("recovery_launch", "recovery-launch.json")):
        if os.path.lexists(session / filename):
            members[key] = bounded(session / filename, 4096)
    if initial["receiver"] is not None:
        receiver = ROOT / "receivers" / case
        for key, filename in (("ready", "ready.json"), ("launch", "launch.json"), ("exit", "exit.json"),
                              ("receipt", "receiver-receipt.json"), ("raw", "received.raw")):
            members[key] = bounded(receiver / filename, 4096)
    return members


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=sorted(CASES))
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_evidence(args.case, read_case(args.case), args.expected_sha256)))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError, AttributeError, OverflowError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc) if type(exc) is ValueError else "EVIDENCE_INVALID"}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
