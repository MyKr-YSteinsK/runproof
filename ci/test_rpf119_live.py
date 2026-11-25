"""Provider 0 tests of RPF-119 using a loopback receiver and real child termination."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic, sleep
import unittest
from unittest.mock import patch
from uuid import uuid4

from runtime.runproof_runtime.effectwitness import rpf119_journal as journal
from runtime.runproof_runtime.effectwitness import rpf119_live as live
from runtime.runproof_runtime.effectwitness import rpf119_protocol as protocol
from runtime.runproof_runtime.effectwitness.product_local_contracts import canonical, digest, strict


def provider_reply(raw, *, outcome="AUTOMATIC"):
    payload = strict(raw)
    inputs = strict(payload["messages"][1]["content"].encode("ascii"))
    obs = inputs["observation"]
    function = payload["tools"][0]["function"]
    operation = function["parameters"]["properties"]["operation_id"]["enum"][0]
    take_tool = (obs["step"] == 1 or inputs["visible_feedback_status"] == "VERIFIED"
                 or outcome in {"WRONG_ARGUMENT", "WRONG_TOOL", "PARALLEL"})
    message = {"role": "assistant", "content": '{"decision":"STOP"}', "reasoning_content": None}
    if take_tool:
        if outcome == "WRONG_ARGUMENT":
            operation = "wrong-operation"
        name = function["name"] if outcome != "WRONG_TOOL" else "unknown_function"
        call = {"id": "call-" + uuid4().hex, "type": "function",
                "function": {"name": name, "arguments": canonical({"operation_id": operation}).decode("ascii")}}
        message.update(content=None, tool_calls=[call])
        if outcome == "PARALLEL":
            message["tool_calls"].append(call | {"id": "call-extra"})
    if outcome == "UNSAFE_REASONING":
        message["reasoning_content"] = "private sentinel prose"
    if outcome == "MISSING_ARGUMENT":
        message["tool_calls"][0]["function"]["arguments"] = "{}"
    reply = {"id": str(uuid4()), "model": protocol.ALIAS, "created": 1780000000, "object": "chat.completion",
             "choices": [{"index": 0, "finish_reason": "tool_calls" if take_tool else "stop", "message": message}],
             "usage": {"prompt_tokens": 512, "completion_tokens": 45, "total_tokens": 557,
                       "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 512},
             "system_fingerprint": "fp_example", "unused": "external-response-field"}
    if outcome == "UNKNOWN_USAGE":
        del reply["usage"]
    if outcome == "MODEL_MISMATCH":
        reply["model"] = "another-model"
    if outcome == "OUT_OF_BOUNDS":
        reply["usage"] = {"prompt_tokens": 16385, "completion_tokens": 45, "total_tokens": 16430}
    if outcome == "TRUNCATED":
        reply["choices"][0].update(finish_reason="length", message={"role": "assistant", "content": "unfinished prose"})
    if outcome == "NON_JSON":
        return b"synthetic malformed response"
    return canonical(reply)


def local_sender(port):
    return lambda raw, record: protocol._post(
        lambda seconds: http.client.HTTPConnection("127.0.0.1", port, timeout=seconds),
        {"Content-Type": "application/json", "Connection": "close", "Accept-Encoding": "identity"},
        raw, record, timeout=20)


@contextmanager
def receiver(folder, *, block=False, status=200, outcome="AUTOMATIC"):
    received = []
    signal = Event()
    release = Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            received.append("UNEXPECTED_GET")
            self.send_error(400)

        def do_POST(self):
            size = int(self.headers["Content-Length"])
            if self.path != protocol.PATH or not 0 < size <= protocol.LIMITS["per_input"] or "Authorization" in self.headers:
                self.send_error(400)
                return
            raw = self.rfile.read(size)
            received.append(live.storage.file_sha(raw))
            journal.write(folder / f"received-{len(received)}.json", {"path": self.path, "sha256": received[-1]})
            signal.set()
            if block:
                release.wait(22)
                return
            reply = provider_reply(raw, outcome=outcome)
            self.send_response(status)
            self.send_header("Content-Length", str(len(reply)))
            self.send_header("x-request-id", "loopback-" + str(len(received)))
            if status == 307:
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/redirected")
            self.end_headers()
            self.wfile.write(reply)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        executor = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        executor.start()
        try:
            yield server.server_port, received, signal
        finally:
            release.set()
            server.shutdown()
            executor.join(timeout=5)


def hashes(root):
    return {str(item.relative_to(root)): live.storage.file_sha(item.read_bytes())
            for item in root.rglob("*") if item.is_file()}


def setup_case(root, manifest, case, sender):
    ledger = journal.Journal(root, manifest)
    ledger.claim()
    (root / "cases").mkdir()
    ledger.begin(case)
    owner = live.AgentProduct.initialize(live._owner(manifest, case, "DEEPSEEK"))
    live.evaluation._execute(owner, case, journal.request_id(manifest, case, "DEEPSEEK"), live.LivePolicy(ledger, case, sender))
    return ledger


def child(root, business, window, port):
    with patch.object(live.storage, "ROOT", business):
        manifest = live._load(root)
        append = journal.Journal._append
        write = live.evaluation.OrderPort.write_once

        def pause(point):
            if point == window:
                journal.write(root / "paused.json", {"point": point, "pid": os.getpid()})
                sleep(45)
                raise RuntimeError("expected supervisor termination")

        def checkpoint(ledger, kind, data):
            if kind == "RESERVED":
                pause("BEFORE_RESERVE")
            append(ledger, kind, data)
            if kind in {"RESERVED", "SEND_ENTRY", "HTTP_RESPONSE", "TERMINAL"}:
                pause(kind)

        def checkpoint_write(port):
            pause("BEFORE_BUSINESS_COMMIT")
            write(port)
            pause("AFTER_BUSINESS_COMMIT")

        with patch.object(journal.Journal, "_append", checkpoint), \
                patch.object(live.evaluation.OrderPort, "write_once", checkpoint_write):
            setup_case(root, manifest, live.evaluation.VALID, local_sender(port))


class LiveTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(dir=os.environ.get("RPF114_TEST_ROOT"))
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.root = self.folder / "experiment"
        scope = patch.object(live.storage, "ROOT", self.folder / "business")
        scope.start()
        self.addCleanup(scope.stop)

    def test_full_loopback_and_credential_free_readback(self):
        spec = live._prepare(self.root, live.STUB, "USD")
        with receiver(self.folder) as (port, receipts, _):
            summary = live._run(self.root, spec, local_sender(port))
        self.assertEqual(len(receipts), 11)
        self.assertEqual((summary["provider"]["calls"], summary["provider"]["tokens"]), (0, 0))
        self.assertEqual(summary["totals"]["DEEPSEEK"]["agent_step_1"]["PASS"], 6)
        self.assertEqual(summary["totals"]["DEEPSEEK"]["agent_step_2"]["PASS"], 5)
        self.assertEqual(summary["totals"]["DEEPSEEK"]["host_safety_pass"], 6)
        self.assertEqual(summary["totals"]["DEEPSEEK"]["task_completed"], 1)
        data = summary["loopback"]
        self.assertEqual((data["reservations"], data["posts_written"], data["responses_observed"]), (11, 11, 11))
        _, state = journal.Journal(self.root, spec).snapshot()
        self.assertEqual([a["reservation"]["request_sha256"] for a in state["attempts"]], receipts)
        authority = [r for r in summary["cases"] if r["case"] == live.evaluation.AUTHORITY and r["policy"] == "DEEPSEEK"][0]
        self.assertEqual(authority["agent_step_2"], "NOT_EVALUATED")
        self.assertEqual(len(authority["provider_attempts"]), 1)
        self.assertEqual(authority["receipts"], {"order": 1, "ops": 0})
        before = hashes(self.folder)
        with patch.object(protocol, "_configured_sender", side_effect=AssertionError("key lookup")) as key, \
                patch.object(protocol, "_post", side_effect=AssertionError("network")) as send:
            self.assertEqual(live.verify(self.root), summary)
            key.assert_not_called()
            send.assert_not_called()
        self.assertEqual(hashes(self.folder), before)

    def test_prep_is_one_time_and_concurrent_claims(self):
        spec = live._prepare(self.root, live.STUB, "CNY")

        def claim(_):
            try:
                journal.Journal(self.root, spec).claim()
            except (ValueError, FileExistsError):
                return False
            return True

        with ThreadPoolExecutor(2) as workers:
            self.assertEqual(sorted(workers.map(claim, range(2))), [False, True])
        with self.assertRaises((FileExistsError, ValueError)):
            live._prepare(self.folder / "replacement", live.STUB, "CNY")
        ledger = journal.Journal(self.root, spec)
        self.assertEqual(ledger.snapshot()[1]["held"], journal.ZERO)
        with self.assertRaisesRegex(ValueError, "TASK_ALREADY_CLAIMED"):
            ledger.claim()
        ledger.folder.rename(self.folder / "retained-journal")
        with self.assertRaises(FileNotFoundError):
            ledger.claim()
        (self.folder / "retained-journal").rename(ledger.folder)
        grant = ledger.grant
        grant.rename(self.folder / "retained-grant.json")
        with self.assertRaises(FileNotFoundError):
            ledger.claim()

    def test_real_process_interruptions_and_no_reopen_send(self):
        windows = {"BEFORE_RESERVE": (0, 0, 0, 0, 0), "RESERVED": (1, 0, 0, 0, 0),
                   "SEND_ENTRY": (1, 1, 0, 0, 0), "IN_FLIGHT": (1, 1, 1, 0, 0),
                   "HTTP_RESPONSE": (1, 1, 1, 1, 0), "TERMINAL": (1, 1, 1, 1, 0),
                   "BEFORE_BUSINESS_COMMIT": (1, 1, 1, 1, 0), "AFTER_BUSINESS_COMMIT": (1, 1, 1, 1, 1)}
        for window, expected in windows.items():
            with self.subTest(window=window):
                self._interruption(window, expected)

    def _interruption(self, window, expected):
        folder = self.folder / window
        folder.mkdir()
        root, biz = folder / "run", folder / "business"
        with patch.object(live.storage, "ROOT", biz):
            spec = live._prepare(root, live.STUB, "USD")
            ledger = journal.Journal(root, spec)
            with receiver(folder, block=window == "IN_FLIGHT") as (port, receipts, signal):
                env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR")
                       if name in os.environ}
                cmd = [sys.executable, "-B", "-m", "ci.test_rpf119_live", "--interrupt-child",
                       str(root), str(biz), window, str(port)]
                with (folder / "child.log").open("wb") as log, \
                        subprocess.Popen(cmd, env=env, stdout=log, stderr=log) as proc:
                    try:
                        deadline = monotonic() + 22
                        while proc.poll() is None and monotonic() < deadline:
                            if window == "IN_FLIGHT":
                                if signal.is_set() and (ledger.folder / "0006.json").is_file():
                                    try:
                                        if ledger.snapshot()[1]["attempts"][0]["post_written"]:
                                            break
                                    except (OSError, ValueError):
                                        pass
                            elif (root / "paused.json").is_file():
                                break
                            sleep(0.04)
                        else:
                            self.fail("child did not reach " + window + ": " + (folder / "child.log").read_text())
                        proc.kill()
                    finally:
                        if proc.poll() is None:
                            proc.kill()
                        proc.wait(timeout=8)
                checked = live.verify(root)
                used = checked["loopback"]
                first = [r for r in checked["cases"] if r["case"] == live.evaluation.VALID and r["policy"] == "DEEPSEEK"][0]
                found = (used["reservations"], used["send_entries"], len(receipts), used["responses_observed"],
                         first["receipts"]["order"])
                self.assertEqual(found, expected)
                if window in {"SEND_ENTRY", "IN_FLIGHT", "HTTP_RESPONSE"}:
                    self.assertEqual(used["unknown_consumption"], 1)
                    self.assertIsNone(used["actual_prompt_tokens"])
                if window == "AFTER_BUSINESS_COMMIT":
                    self.assertIsNone(first["fault"]["triggered"])
                    self.assertEqual(first["agent_step_2"], "NOT_EVALUATED")
                with self.assertRaisesRegex(ValueError, "TASK_ALREADY_CLAIMED"):
                    ledger.claim()
                self.assertEqual(len(receipts), expected[2])
                journal.write(folder / "verified.json", {"window": window, "observed": list(found),
                    "unknown_consumption": used["unknown_consumption"], "held": used["held"], "fault": first["fault"],
                    "post_written": used["posts_written"], "child_exit": proc.returncode, "reopen_send": 0})

    def test_projected_protocol_and_charge_failure(self):
        for case, verdict in (("WRONG_TOOL", "INTENT_REJECTED"), ("WRONG_ARGUMENT", "INTENT_REJECTED"),
                              ("MISSING_ARGUMENT", "INTENT_REJECTED"), ("TRUNCATED", "REPLY_TRUNCATED"),
                              ("NON_JSON", "REPLY_JSON_OR_TEXT"),
                              ("PARALLEL", "PARALLEL_TOOL_CALLS"), ("UNSAFE_REASONING", "THINKING_NOT_DISABLED"),
                              ("UNKNOWN_USAGE", "USAGE_UNKNOWN"), ("MODEL_MISMATCH", "RESPONSE_MODEL_IDENTITY"),
                              ("OUT_OF_BOUNDS", "USAGE_EXCEEDS_HOLD"), (429, "PROVIDER_HTTP_STATUS"),
                              (503, "PROVIDER_HTTP_STATUS"), (307, "PROVIDER_HTTP_STATUS")):
            with self.subTest(fixture=case):
                folder = self.folder / str(case)
                folder.mkdir()
                root = folder / "experiment"
                spec = live._prepare(root, live.STUB, "USD")
                with receiver(folder, status=case if type(case) is int else 200, outcome=case) as (port, receipts, _):
                    ledger = setup_case(root, spec, live.evaluation.VALID, local_sender(port))
                self.assertEqual(len(receipts), 1)
                _, state = ledger.snapshot()
                attempt = state["attempts"][0]
                safely_saved = canonical(attempt)
                self.assertNotIn(b"private sentinel prose", safely_saved)
                self.assertNotIn(b"external-response-field", safely_saved)
                row, _, _ = live._case_row(spec, live.evaluation.VALID, "DEEPSEEK", state["attempts"])
                self.assertEqual(row["receipts"], {"order": 0, "ops": 0})
                if verdict == "INTENT_REJECTED":
                    self.assertEqual(row["step_1_verdict"], verdict)
                    self.assertEqual(row["agent_step_1"], "FAIL")
                else:
                    self.assertEqual(row["reason"], verdict)
                    self.assertEqual(row["agent_step_1"], "NOT_EVALUATED")
                    with self.assertRaisesRegex(ValueError, "RESERVATION_AFTER_STOP"):
                        ledger.reserve(live.evaluation.VALID, attempt["reservation"]["inputs"]["observation"], None)
                if verdict in {"USAGE_UNKNOWN", "PROVIDER_HTTP_STATUS"}:
                    self.assertEqual(live._costs(spec, state)["unknown_consumption"], 1)

    def test_transport_timeout_consumes_hold_and_stops_suite(self):
        spec = live._prepare(self.root, live.STUB, "USD")
        calls = []

        def timeout(raw, _):
            calls.append(live.storage.file_sha(raw))
            raise TimeoutError

        count = live._run(self.root, spec, timeout)
        self.assertEqual(len(calls), 1)
        self.assertEqual(count["loopback"]["unknown_consumption"], 1)
        self.assertEqual(count["totals"]["DEEPSEEK"]["outcomes"]["NOT_RUN"], 5)
        self.assertEqual(count["totals"]["DEEPSEEK"]["agent_step_1"]["denominator"], 0)
        self.assertEqual(live.verify(self.root), count)

    def test_credential_echo_cannot_enter_projection(self):
        nested = canonical({"arguments": '{"operation_id":"\\u0073k-local-marker"}'})
        self.assertTrue(protocol._contains_credential(nested, "sk-local-marker"))
        self.assertFalse(protocol._contains_credential(b'{"content":null}', "sk-local-marker"))

    def test_unknown_business_readback_blocks_second_reservation(self):
        spec = live._prepare(self.root, live.STUB, "USD")
        original = live.evaluation.OrderPort.read

        def read_without_receipts(port):
            return original(port) | {"receipts": []}

        with receiver(self.folder) as (port, receipts, _), patch.object(live.evaluation.OrderPort, "read", read_without_receipts):
            ledger = setup_case(self.root, spec, live.evaluation.VALID, local_sender(port))
        self.assertEqual(len(receipts), 1)
        _, state = ledger.snapshot()
        row, _, _ = live._case_row(spec, live.evaluation.VALID, "DEEPSEEK", state["attempts"])
        self.assertEqual(row["stop_reason"], "EFFECT_UNCONFIRMED")
        self.assertEqual(row["agent_step_2"], "NOT_EVALUATED")
        self.assertEqual(row["receipts"], {"order": 1, "ops": 0})
        self.assertEqual(state["held"]["requests"], 1)

    def test_chain_rehash_does_not_hide_tampering(self):
        spec = live._prepare(self.root, live.STUB, "USD")
        with receiver(self.folder) as (port, receipts, _):
            ledger = setup_case(self.root, spec, live.evaluation.VALID, local_sender(port))
        self.assertEqual(len(receipts), 2)
        original, state = ledger.snapshot()

        def replace(events):
            rows = []
            for row in events:
                entry = ledger._event(rows, row["kind"], row["data"])
                (ledger.folder / f"{entry['seq']:04}.json").write_bytes(canonical(entry))
                rows.append(entry)

        # Use deep copies because every negative starts from the identical valid original.
        def modified(kind, edit):
            rows = strict(canonical(original))
            record = next(r for r in rows if r["kind"] == kind)
            edit(record["data"])
            replace(rows)

        modified("RESERVED", lambda d: d["held_total"].update(requests=12))
        with self.assertRaisesRegex(ValueError, "RESERVATION_BINDING"):
            live.verify(self.root)
        modified("RESERVED", lambda d: d["hold"].update(usd_nanodollars=0))
        with self.assertRaisesRegex(ValueError, "RESERVATION_BINDING"):
            live.verify(self.root)
        modified("RESERVED", lambda d: d.update(request="rpf119-other-owner"))
        with self.assertRaisesRegex(ValueError, "RESERVATION_BINDING"):
            live.verify(self.root)
        modified("CASE_BEGIN", lambda d: d.update(owner_nonce="0" * 32))
        with self.assertRaisesRegex(ValueError, "CASE_ORDER_OR_ABORT"):
            live.verify(self.root)

        def reparse(data):
            payload = data["evidence"]["reply"]
            fn = payload["projection"]["choices"][0]["message"]["tool_calls"][0]["function"]
            fn["arguments"] = '{"operation_id":"wrong-operation"}'
            projected = journal.terminal(state["attempts"][0], payload)
            data["evidence"] = projected

        modified("TERMINAL", reparse)
        with self.assertRaisesRegex(ValueError, "PROVIDER_INTENT_MISMATCH"):
            live.verify(self.root)
        replace(original)
        path = ledger.folder / "0004.json"
        moved = self.folder / "retained-reservation.json"
        path.rename(moved)
        with self.assertRaisesRegex(ValueError, "JOURNAL_FILE_SET"):
            live.verify(self.root)
        moved.rename(path)
        replace(original[:4] + [original[3]] + original[4:])
        with self.assertRaisesRegex(ValueError, "RESERVATION_STEP_OR_AUTHORITY"):
            live.verify(self.root)

    def test_no_default_credential_lookup_or_automatic_bootstrap(self):
        with patch.object(live, "_root", return_value=self.root), \
                patch.object(protocol, "_configured_sender", side_effect=AssertionError("looked up")) as configure:
            with self.assertRaises(FileNotFoundError):
                live._preflight()
            with self.assertRaises(FileNotFoundError):
                live.verify(self.root)
            configure.assert_not_called()
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[1] == "--interrupt-child":
        child(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], int(sys.argv[5]))
    else:
        unittest.main()
