"""Pure and isolated-file controls. No SDK or sockets in this suite."""
from contextlib import contextmanager
import threading
import unittest
from uuid import uuid4

from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import (
    BUDGET, CALL, MODEL, PINS, PROMPT, ROOT, STOP, TOOL, Denied, canonical, identity,
    owner_path, response, safe, sha, strict, tool_value, validate_request,
)
from runtime.runproof_runtime.effectwitness.sdk_presend_host import Journal, Session
from runtime.runproof_runtime.effectwitness.sdk_presend_oracle import verify


def request(case, number):
    messages = [{"role": "user", "content": PROMPT}]
    if number == 2:
        messages.extend([{"role": "assistant", "tool_calls": response(case, 1)["choices"][0]["message"]["tool_calls"]},
                         {"role": "tool", "tool_call_id": CALL, "content": canonical(tool_value(case)).decode()}])
    return canonical({"model": MODEL, "messages": messages,
                      "tools": [{"type": "function", "function": {"name": TOOL}}]})


def chain(events):
    previous = "0" * 64
    lines = []
    for index, (kind, body) in enumerate(events):
        core = {"seq": index, "prev": previous, "kind": kind, "body": body}
        previous = sha(canonical(core))
        lines.append(canonical({**core, "sha256": previous}))
    return b"\n".join(lines) + b"\n"


def synthetic(case):
    """Falsification fixtures only. These objects claim no physical execution."""
    owner = "1" * 32
    exe = "2" * 64
    nonce = "3" * 64
    host = {"pid": 100, "port": 2222, "host": "127.0.0.1", "exe_sha256": exe}
    ready = {"pid": 101, "port": 2223, "host": "127.0.0.1", "exe_sha256": exe,
             "owner": owner, "case": case, "nonce": nonce, "ready_ns": 2}
    terminal = ({"status": "DENIED_AFTER_UNKNOWN", "error_type": "ModelHTTPError", "http_status": 409,
                 "usage_kind": "UNAVAILABLE"} if case == "UNKNOWN" else
                {"status": "COMPLETED", "output_sha256": sha(STOP.encode()), "sdk_reported_requests": 2,
                 "sdk_reported_tool_calls": 1, "usage_kind": "SYNTHETIC_LOCAL_MODEL_RESPONSE"})
    output = canonical({"pid": 102, "exe_sha256": exe, "terminal": terminal,
                        "tool_callbacks": [{"call_id": CALL, "value": tool_value(case)}],
                        "packages": {name: {"version": version, "source_sha256": exe, "record_sha256": exe}
                                     for name, version in PINS.items()}})
    files = {
        "sdk-launch.json": canonical({"pid": 102, "start_ns": 3, "exe_sha256": exe, "host": host, "network": "HOST_LOOPBACK_ONLY"}),
        "sdk-output.json": output,
        "sdk-exit.json": canonical({"pid": 102, "exit": 0, "exit_ns": 9, "stdout_sha256": sha(output)}),
        "receiver-ready.json": canonical(ready),
        "receiver-launch.json": canonical({"pid": 101, "nonce": nonce, "exe_sha256": exe, "start_ns": 1}),
        "receiver-exit.json": canonical({"pid": 101, "exit": 0, "exit_ns": 9, "exe_sha256": exe}),
    }
    events = [("READY", {"owner": owner, "case": case, "source": identity(), "budget": BUDGET[case]}),
              ("HOST_LISTEN", host)]
    for i in (1, 2):
        if i == 2:
            if case == "UNKNOWN":
                events.append(("UNKNOWN_OBSERVED", {"call_id": CALL}))
                files["unknown-intent.json"] = canonical({"case": case, "call_id": CALL})
            events.append(("TOOL_RETURN_TO_SDK", {"call_id": CALL, "value": tool_value(case)}))
        raw = request(case, i)
        files[f"sdk-post-{i}.raw"] = raw
        events.append(("SDK_POST_RECEIVED", {"number": i, "sha256": sha(raw), "bytes": len(raw)}))
        if i > BUDGET[case]:
            events.append(("DENY", {"number": i, "reason": "UNKNOWN_DURABLE"}))
            continue
        ticket = {"number": i, "domain": "order", "role": "TARGET", "request_sha256": sha(raw)}
        ready_hash = strict(chain(events[:1]).splitlines()[0])["sha256"]
        ticket["id"] = sha(canonical({"ready": ready_hash, "ticket": ticket}))
        files[f"sender-{i}.json"] = canonical({"pid": 100, "ticket": ticket, "nonce": nonce, "bytes": len(raw),
                                               "sha256": sha(raw), "entry_ns": 4, "return_ns": 5})
        files[f"receiver-{i}.raw"] = raw
        files[f"receiver-{i}.json"] = canonical({"index": i, "owner": owner, "case": case, "pid": 101,
                                                 "nonce": nonce, "bytes": len(raw), "sha256": sha(raw), "received_ns": 6})
        events.extend((kind, ticket) for kind in ("PROVIDER_RESERVE", "SEND_BEGIN", "SEND_ENTRY", "SEND_RETURN"))
        events.append(("SCRIPTED_MODEL_RESPONSE", {"number": i, "response_id": response(case, i)["id"],
                                                    "sha256": sha(canonical(response(case, i)))}))
    events.append(("SDK_TERMINAL", {"sha256": sha(output), "exit": 0}))
    files["wal.jsonl"] = chain(events)
    return owner, files, events


@contextmanager
def fresh(case):
    safe(ROOT)
    ROOT.parent.mkdir(exist_ok=True)
    ROOT.mkdir(exist_ok=True)
    folder = owner_path(uuid4().hex) / case
    folder.mkdir(parents=True, exist_ok=False)
    yield folder


class Controls(unittest.TestCase):
    def test_valid_requests_and_binding_rejection(self):
        for case in ("NORMAL", "UNKNOWN"):
            for i in (1, 2):
                validate_request(request(case, i), i, case)
            wrong = strict(request(case, 2))
            wrong["messages"][2]["tool_call_id"] = "other"
            with self.assertRaisesRegex(ValueError, "TOOL_RETURN_BINDING"):
                validate_request(canonical(wrong), 2, case)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_KEY"):
            strict(b'{"model":1,"model":2}')

    def test_normal_reserved_recovery_and_unknown_latch(self):
        with fresh("NORMAL") as folder:
            raw = request("NORMAL", 1)
            with Journal(folder, "NORMAL").open(create=True) as journal:
                ticket = journal.reserve(sha(raw))
                with self.assertRaises(OSError):
                    with Journal(folder, "NORMAL").open():
                        self.fail("second lock admitted")
            with Journal(folder, "NORMAL").open() as journal:
                with self.assertRaisesRegex(Denied, "TICKET_BINDING"):
                    journal.begin({**ticket, "id": "forged"}, raw)
                journal.begin(ticket, raw)  # Filesystem-only test, no transport.
                journal.append("SEND_ENTRY", ticket)
                journal.append("SEND_RETURN", ticket)
                journal.unknown()
            with Journal(folder, "NORMAL").open() as journal:
                for domain in ("order", "ops"):
                    for role in ("TARGET", "EXPLORER"):
                        with self.assertRaisesRegex(Denied, "UNKNOWN"):
                            journal.reserve(sha(raw), domain, role)
                with self.assertRaisesRegex(Denied, "UNKNOWN"):
                    journal.begin(ticket, raw)
                self.assertEqual(sum(r["kind"] == "PROVIDER_RESERVE" for r in journal.rows()), 1)

    def test_durability_failures_and_torn_wal(self):
        for fault in ("write", "flush"):
            with fresh("UNKNOWN") as folder:
                with Journal(folder, "UNKNOWN", fault=fault).open(create=True) as journal:
                    with self.assertRaisesRegex(OSError, "INJECTED_"):
                        journal.unknown()
                    with self.assertRaisesRegex(Denied, "PERSISTENCE"):
                        journal.reserve(sha(b"new"))
                with self.assertRaisesRegex(Denied, "PERSISTENCE"):
                    with Journal(folder, "UNKNOWN").open():
                        self.fail("replayed uncertain operation")
        with fresh("NORMAL") as folder:
            with Journal(folder, "NORMAL").open(create=True):
                pass
            with (folder / "wal.jsonl").open("ab") as stream:
                stream.write(b"torn")
            with self.assertRaisesRegex(Denied, "TORN_WAL"):
                with Journal(folder, "NORMAL").open():
                    self.fail("torn WAL admitted")

    def test_unknown_wins_serial_admission(self):
        with fresh("NORMAL") as folder, Journal(folder, "NORMAL").open(create=True) as journal:
            session = Session(journal, None)
            arrived, denied = threading.Event(), threading.Event()

            def reserve():
                arrived.set()
                with session.lock:
                    try:
                        journal.reserve(sha(request("NORMAL", 1)), "ops", "EXPLORER")
                    except Denied:
                        denied.set()

            with session.lock:
                worker = threading.Thread(target=reserve)
                worker.start()
                self.assertTrue(arrived.wait(3))
                journal.unknown()
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertTrue(denied.is_set())
            self.assertEqual([r["kind"] for r in journal.rows()], ["READY", "UNKNOWN_OBSERVED"])

    def test_independent_oracle_reanchored_semantic_rejections(self):
        owner, files, events = synthetic("UNKNOWN")
        self.assertEqual(verify(owner, "UNKNOWN", files)["provider_tickets"], 1)
        for kind in ("PROVIDER_RESERVE", "SEND_BEGIN"):
            wrong = {**files, "wal.jsonl": chain([*events, (kind, {})])}
            anchor = sha(canonical({k: sha(v) for k, v in wrong.items()}))
            with self.assertRaisesRegex(ValueError, "POST_UNKNOWN_"):
                verify(owner, "UNKNOWN", wrong, anchor)
        wrong = {**files, "wal.jsonl": chain([(k, {"call_id": "wrong", "value": tool_value("UNKNOWN")})
                                                if k == "TOOL_RETURN_TO_SDK" else (k, b) for k, b in events])}
        anchor = sha(canonical({k: sha(v) for k, v in wrong.items()}))
        with self.assertRaisesRegex(ValueError, "TRANSCRIPT_SEMANTICS"):
            verify(owner, "UNKNOWN", wrong, anchor)
        with self.assertRaisesRegex(ValueError, "RECEIVER_BYTES"):
            verify(owner, "UNKNOWN", {**files, "receiver-1.raw": b""})
        _, normal, _ = synthetic("NORMAL")
        with self.assertRaises(ValueError):
            verify(owner, "UNKNOWN", {**files, "sdk-post-2.raw": normal["sdk-post-2.raw"]})
        with self.assertRaisesRegex(ValueError, "RECEIVER_BYTES"):
            verify(owner, "UNKNOWN", {**files, "receiver-1.json": normal["receiver-1.json"]})
        missing_response = {**files, "wal.jsonl": chain([(k, b) for k, b in events if k != "SCRIPTED_MODEL_RESPONSE"])}
        with self.assertRaisesRegex(ValueError, "TRANSCRIPT_SEMANTICS"):
            verify(owner, "UNKNOWN", missing_response)
        with self.assertRaisesRegex(ValueError, "ANCHOR_MISMATCH"):
            verify(owner, "UNKNOWN", files, "0" * 64)
        self.assertEqual(verify(owner, "NORMAL", normal)["provider_tickets"], 2)
