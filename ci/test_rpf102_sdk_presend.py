"""Pure and isolated-file controls. No SDK or sockets in this suite."""
from contextlib import contextmanager
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import (
    BUDGET, CALL, MODEL, PINS, PROMPT, ROOT, STOP, TOOL, Denied, canonical, exclusive, identity,
    response, safe, sha, strict, tool_value, validate_request,
)
from runtime.runproof_runtime.effectwitness.sdk_presend_diagnostic import (
    CONTEXT, REPORT, MAX_BYTES, collect, context, inspect_diagnostic, validate_public,
)
from runtime.runproof_runtime.effectwitness.sdk_presend_host import Journal, Session, transfer
from runtime.runproof_runtime.effectwitness.sdk_presend_oracle import verify
from runtime.runproof_runtime.effectwitness.sdk_presend_probe import finish, launch


def request(case, number):
    """SYNTHETIC_CONTRACT_ONLY. Constructed from the fixed schema and tagged source."""
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
    folder = safe(ROOT / "rev2-unit-only" / uuid4().hex / case)
    folder.mkdir(parents=True, exist_ok=False)
    yield folder


class Controls(unittest.TestCase):
    def test_isolated_entry_point_propagates_exit_status(self):
        with fresh("NORMAL") as folder:
            for argument, expected in (("", 0), ("error", 1)):
                with self.subTest(expected=expected):
                    child = launch(folder, "operator", "truth", [argument])
                    self.assertEqual(finish(child, 5), expected)

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
        for kind in ("PROVIDER_RESERVE", "SEND_BEGIN", "SEND_ENTRY"):
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

    def test_tagged_request_variants_and_structural_fail_closed(self):
        for case in ("NORMAL", "UNKNOWN"):
            for turn in (1, 2):
                for field in ("max_tokens", "max_completion_tokens"):
                    sample = {**strict(request(case, turn)), field: 128, "stream": False,
                              "parallel_tool_calls": False, "tool_choice": "auto"}
                    self.assertEqual(validate_request(canonical(sample), turn, case), sample)
        for patch_values, code in (({"n": True}, "REQUEST_SCHEMA"), ({"tools": [None]}, "TOOL_ALLOWLIST"),
                                   ({"messages": [None]}, "MESSAGE_COUNT"),
                                   ({"tools": [{"type": "function", "function": None}]}, "TOOL_ALLOWLIST")):
            sample = {**strict(request("NORMAL", 1)), **patch_values}
            with self.assertRaisesRegex(Denied, code):
                validate_request(canonical(sample), 1, "NORMAL")
        bad = strict(request("NORMAL", 2))
        bad["messages"][2]["content"] = tool_value("NORMAL")
        with self.assertRaisesRegex(Denied, "TOOL_RETURN_BINDING"):
            validate_request(canonical(bad), 2, "NORMAL")

    def test_send_begin_precedes_socket_and_rejects_forged_ticket_without_socket(self):
        with fresh("NORMAL") as folder, Journal(folder, "NORMAL").open(create=True) as journal:
            _, files, _ = synthetic("NORMAL")
            ready = {**strict(files["receiver-ready.json"]), "owner": folder.parent.name}
            exclusive(folder / "receiver-ready.json", canonical(ready))
            exclusive(folder / "receiver-launch.json", files["receiver-launch.json"])
            raw = request("NORMAL", 1)
            ticket = journal.reserve(sha(raw))
            with patch("runtime.runproof_runtime.effectwitness.sdk_presend_host.socket.socket") as socket_guard:
                with self.assertRaisesRegex(Denied, "TICKET_BINDING"):
                    transfer(journal, {**ticket, "id": "forged"}, raw, ready)
                socket_guard.assert_not_called()

                def reject_before_socket(*_):
                    self.assertEqual(journal.rows()[-1]["kind"], "SEND_BEGIN")
                    raise OSError("NO_NETWORK_TEST")

                socket_guard.side_effect = reject_before_socket
                with self.assertRaisesRegex(OSError, "NO_NETWORK_TEST"):
                    transfer(journal, ticket, raw, ready)
                self.assertNotIn("SEND_ENTRY", [r["kind"] for r in journal.rows()])

    def test_session_durable_unknown_and_normal_controls_without_transport(self):
        def synthetic_transfer(journal, ticket, raw, _):
            journal.begin(ticket, raw)
            journal.append("SEND_ENTRY", ticket)
            journal.append("SEND_RETURN", ticket)

        for case in ("NORMAL", "UNKNOWN"):
            with fresh(case) as folder, Journal(folder, case).open(create=True) as journal:
                session = Session(journal, None)
                with patch("runtime.runproof_runtime.effectwitness.sdk_presend_host.transfer",
                           side_effect=synthetic_transfer) as forward:
                    with patch.object(journal, "append", side_effect=OSError("INJECTED_POST_WRITE")):
                        with self.assertRaisesRegex(OSError, "INJECTED_POST_WRITE"):
                            session.handle("/v1/chat/completions", request(case, 1))
                        self.assertEqual(session.posts, 0)
                        forward.assert_not_called()
                    self.assertFalse(any(r["kind"] == "SDK_POST_RECEIVED" for r in journal.rows()))
                # The failed request already created its raw receipt. Keep that failure site.
            with fresh(case) as folder, Journal(folder, case).open(create=True) as journal:
                session = Session(journal, None)
                with patch("runtime.runproof_runtime.effectwitness.sdk_presend_host.transfer",
                           side_effect=synthetic_transfer) as forward:
                    self.assertEqual(session.handle("/v1/chat/completions", request(case, 1))[0], 200)
                    code, value = session.handle("/tool", canonical({"call_id": CALL, "name": TOOL}))
                    self.assertEqual((code, value), (200, tool_value(case)))
                    kinds = [r["kind"] for r in journal.rows()]
                    if case == "UNKNOWN":
                        self.assertLess(kinds.index("UNKNOWN_OBSERVED"), kinds.index("TOOL_RETURN_TO_SDK"))
                    self.assertEqual(session.handle("/v1/chat/completions", request(case, 2))[0],
                                     409 if case == "UNKNOWN" else 200)
                    self.assertEqual(forward.call_count, BUDGET[case])
                    kinds = [r["kind"] for r in journal.rows()]
                    if case == "UNKNOWN":
                        after = kinds[kinds.index("UNKNOWN_OBSERVED") + 1:]
                        self.assertEqual(after, ["TOOL_RETURN_TO_SDK", "SDK_POST_RECEIVED", "DENY"])

    def test_diagnostic_child_exit_stdout_and_independent_host_code(self):
        for raw, code, expected in (
            (b'{"status":"SDK_ERROR","error_type":"ImportError"}', 7, "SDK_CHILD_NONZERO"),
            (b'{"status":"SDK_ERROR","error_type":"ImportError","stage":"SDK_IMPORT"}', 7,
             "SDK_IMPORT_OR_INIT_FAILURE"),
            (b'{"status":', 7, "SDK_OUTPUT_INVALID"),
            (b'x' * (MAX_BYTES + 1), 7, "SDK_OUTPUT_INVALID"),
        ):
            with self.subTest(expected=expected), fresh("NORMAL") as folder:
                exclusive(folder / CONTEXT, canonical(context(folder, "NORMAL")))
                with Journal(folder, "NORMAL").open(create=True):
                    pass
                exclusive(folder / "sdk-launch.json", canonical({"pid": 123}))
                exclusive(folder / "sdk-exit.json", canonical({"pid": 123, "exit": code, "stdout_sha256": sha(raw)}))
                exclusive(folder / "sdk-output.json", raw)
                row = collect(folder, "NORMAL", phase="SDK", attempted=True)
                self.assertEqual((row["sdk_exit"], row["final_classification"]), (code, expected))
                self.assertEqual(row["sdk_post_count"], 0)
                for key in ("provider_reserve_count", "send_begin_count", "send_entry_count",
                            "receiver_receipt_count", "received_bytes"):
                    self.assertIsNone(row[key], key)
                self.assertEqual(collect(folder, "NORMAL", phase="SDK", attempted=True, timed_out=True)
                                 ["final_classification"], "SDK_CHILD_TIMEOUT")
                for host, label in (("TOOL_POLICY", "HOST_CONTRACT_REJECTED"), ("HTTP_ADMISSION", "HOST_HTTP_REJECTED")):
                    row = collect(folder, "NORMAL", phase="SDK", attempted=True, host_code=host)
                    self.assertEqual((row["sdk_exit"], row["host_failure_code"], row["final_classification"]),
                                     (code, host, label))

    def test_diagnostic_rejects_secrets_and_never_rewrites_case_evidence(self):
        with fresh("UNKNOWN") as folder:
            exclusive(folder / "wal.jsonl", b"legacy-evidence")
            with self.assertRaises(FileNotFoundError):
                inspect_diagnostic(folder, "UNKNOWN")
            self.assertEqual((folder / "wal.jsonl").read_bytes(), b"legacy-evidence")
            self.assertFalse((folder / REPORT).exists())
            exclusive(folder / CONTEXT, canonical(context(folder, "UNKNOWN")))
            secrets = (r"C:\Users\example\private.log", "/home/example/private", "Bearer example",
                       "sk-fictitious-example", "failure: private text")
            raw = canonical({"status": "SDK_ERROR", "error_type": secrets[0], "stage": secrets[1],
                             "exception": secrets[4], "extra": secrets[2]})
            exclusive(folder / "sdk-launch.json", canonical({"pid": 123}))
            exclusive(folder / "sdk-exit.json", canonical({"pid": 123, "exit": 1, "stdout_sha256": sha(raw)}))
            exclusive(folder / "sdk-output.json", raw)
            report = collect(folder, "UNKNOWN", phase="SDK", attempted=True, host_code=secrets[3])
            self.assertEqual(report["final_classification"], "SDK_CHILD_NONZERO")
            self.assertEqual(report["host_failure_code"], "HOST_STATE_FAILURE")
            self.assertIsNone(report["sdk_stage"])
            self.assertIsNone(report["sdk_error_type"])
            for bad in secrets:
                with self.subTest(bad=bad), self.assertRaisesRegex(Denied, "DIAGNOSTIC_ENUM"):
                    validate_public(canonical({**report, "sdk_error_type": bad}))
            for extra in ({"stdout": secrets[4]}, {"owner": folder.parent.name}):
                with self.assertRaisesRegex(Denied, "DIAGNOSTIC_FIELDS"):
                    validate_public(canonical({**report, **extra}))
            with self.assertRaisesRegex(Denied, "DIAGNOSTIC_COUNT"):
                validate_public(canonical({**report, "send_entry_count": True}))
            with self.assertRaisesRegex(Denied, "DIAGNOSTIC_LIMIT"):
                validate_public(b"x" * (MAX_BYTES + 1))
            sealed = canonical(report)
            exclusive(folder / REPORT, sealed)
            self.assertEqual(inspect_diagnostic(folder, "UNKNOWN"), report)
            self.assertEqual((folder / REPORT).read_bytes(), sealed)
            self.assertEqual((folder / "sdk-output.json").read_bytes(), raw)
            self.assertEqual((folder / "wal.jsonl").read_bytes(), b"legacy-evidence")
            with self.assertRaisesRegex(Denied, "DIAGNOSTIC_CONTEXT"):
                inspect_diagnostic(folder, "NORMAL")
            with self.assertRaisesRegex(Denied, "DIAGNOSTIC_VERIFIED_BINDING"):
                validate_public(canonical({**report, "final_classification": "UNKNOWN_EXPECTED_DENIAL"}))

    def test_diagnostic_receiver_bytes_require_independent_case_identity(self):
        with fresh("UNKNOWN") as folder:
            _, files, _ = synthetic("UNKNOWN")
            exclusive(folder / CONTEXT, canonical(context(folder, "UNKNOWN")))
            for name in ("receiver-ready.json", "receiver-launch.json", "receiver-exit.json",
                         "receiver-1.json", "receiver-1.raw"):
                data = files[name]
                if name.endswith(".json") and "owner" in strict(data):
                    data = canonical({**strict(data), "owner": folder.parent.name})
                exclusive(folder / name, data)
            report = collect(folder, "UNKNOWN", phase="SDK", attempted=False)
            self.assertEqual(report["receiver_receipt_count"], 1)
            self.assertEqual(report["received_bytes"], len(files["receiver-1.raw"]))
            self.assertIsNone(report["send_entry_count"])
            bad = {**strict((folder / "receiver-1.json").read_bytes()), "case": "NORMAL"}
            (folder / "receiver-1.json").write_bytes(canonical(bad))
            report = collect(folder, "UNKNOWN", phase="SDK", attempted=False)
            self.assertEqual(report["final_classification"], "RECEIVER_RECEIPT_MISMATCH")
            self.assertIsNone(report["received_bytes"])
