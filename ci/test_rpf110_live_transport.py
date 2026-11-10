"""Loopback HTTP and parser controls, with no SDK, credentials or remote sockets."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import socket
import ssl
from threading import Thread
import unittest
from unittest.mock import patch

from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r110_live_contracts as c
from runtime.runproof_runtime.effectwitness import pge_r110_live_provider as provider, pge_r110_live_transport as wire
from runtime.runproof_runtime.effectwitness.pge_r110_live_session import Session
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import Denied, canonical, sha, strict

LOCAL = os.environ.get("RPF110_LOCAL_SQLITE") == "1"
SOURCE = os.environ.get("RPF110_SOURCE_SHA", c.BASE)


def body(choice):
    return {"id": "stub-response:2026", "model": c.MODEL, "object": "chat.completion", "created": 1,
            "system_fingerprint": "stub-fingerprint", "choices": [{"index": 0, "finish_reason": "tool_calls",
            "logprobs": None, "message": {"role": "assistant", "content": None, "reasoning_content": None,
            "tool_calls": [{"id": "stub-call-dynamic", "type": "function", "function": {"name": c.TOOL,
                          "arguments": canonical({"candidate_id": choice}).decode()}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 18, "total_tokens": 118,
                      "prompt_cache_hit_tokens": 0}}


@contextmanager
def stub(choice=inner.OPS, *, code=200, partial=False, header=None, reply=None):
    received = []
    raw = canonical(body(choice)) if reply is None else reply

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            request = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, request, "Authorization" in self.headers))
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            if code in (301, 302):
                self.send_header("Location", "/unexpected-redirect")
            if header:
                self.send_header("x-request-id", header)
            self.end_headers()
            self.wfile.write(raw[:10] if partial else raw)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.03}, daemon=True)
        thread.start()
        try:
            yield server.server_port, received
        finally:
            server.shutdown()
            thread.join(timeout=3)
            if thread.is_alive():
                raise RuntimeError("LOOPBACK_STILL_RUNNING")


class ParserTests(unittest.TestCase):
    def parse_response(self, raw, status=200):
        receipt = {"status": status, "header_request_id": "UNAVAILABLE",
                   "response_size": len(raw), "response_sha256": sha(raw)}
        return provider.parse(raw, receipt, {"kind": c.STUB, "approval": None})

    def test_nonstreaming_tool_uses_dynamic_ids_and_observed_usage(self):
        response = body(inner.OPS)
        response["id"] = "chatcmpl-dynamic-83"
        response["choices"][0]["message"]["tool_calls"][0]["id"] = "dynamic-tool-72"
        selected = self.parse_response(canonical(response))
        self.assertEqual(selected["response_id"], "chatcmpl-dynamic-83")
        self.assertEqual(selected["tool_call_id"], "dynamic-tool-72")
        self.assertEqual(selected["arguments"], {"candidate_id": inner.OPS})
        self.assertEqual(selected["usage"], {"prompt_tokens": 100, "completion_tokens": 18, "total_tokens": 118})

    def test_field_diagnostics_distinguish_each_layer_and_delta(self):
        marker = "synthetic_private_field"
        for layer, field in (("TOOL_CALL", "id"), ("TOOL_FUNCTION", "name"), ("TOOL_ARGUMENT", "candidate_id")):
            for delta in ("EXTRA", "MISSING", "MIXED"):
                with self.subTest(layer=layer, delta=delta):
                    response = body(inner.OPS)
                    call = response["choices"][0]["message"]["tool_calls"][0]
                    function = call["function"]
                    arguments = strict(function["arguments"].encode())
                    target = {"TOOL_CALL": call, "TOOL_FUNCTION": function, "TOOL_ARGUMENT": arguments}[layer]
                    if delta != "EXTRA":
                        del target[field]
                    if delta != "MISSING":
                        target[marker] = "synthetic_private_value"
                    function["arguments"] = canonical(arguments).decode()
                    with self.assertRaises(Denied) as raised:
                        self.parse_response(canonical(response))
                    reason = str(raised.exception)
                    self.assertEqual(reason, f"{layer}_FIELDS_{delta}")
                    self.assertRegex(reason, r"^[A-Z_]{3,60}$")
                    self.assertNotIn(marker, reason)

    def test_nonstreaming_index_and_non_json_stay_separate_from_fields(self):
        response = body(inner.OPS)
        choice = response["choices"][0]
        call = choice["message"]["tool_calls"][0]
        call["index"] = 0
        with self.assertRaisesRegex(Denied, "^TOOL_CALL_FIELDS_EXTRA$"):
            self.parse_response(canonical(response))
        del call["index"]
        call["function"]["arguments"] = "{bad"
        with self.assertRaisesRegex(Denied, "^TOOL_ARGUMENT_JSON$"):
            self.parse_response(canonical(response))
        with self.assertRaisesRegex(Denied, "^RESPONSE_JSON$"):
            self.parse_response(b"{bad")
        choice["finish_reason"] = "synthetic_invalid_reason"
        with self.assertRaisesRegex(Denied, "^FINISH_REASON$"):
            self.parse_response(canonical(response))
        choice["finish_reason"] = "tool_calls"
        choice["message"]["tool_calls"] = [call, call]
        with self.assertRaisesRegex(Denied, "^TOOL_COUNT$"):
            self.parse_response(canonical(response))
        for status in (400, 403, 429):
            with self.subTest(status=status), self.assertRaisesRegex(Denied, "^HTTP_STATUS$"):
                self.parse_response(canonical(response), status)

    def test_native_factory_is_fixed_and_uses_system_tls_validation(self):
        with patch("http.client.HTTPSConnection") as connection:
            wire._native_connection(2)
        args, kwargs = connection.call_args
        self.assertEqual(args, ("api.deepseek.com", 443))
        self.assertEqual(kwargs["timeout"], 2)
        self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(kwargs["context"].check_hostname)
        self.assertEqual(kwargs["context"].minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_usage_identity_and_tool_negatives(self):
        data = body(inner.OPS)
        raw = canonical(data)
        contract = {"kind": c.STUB, "approval": None}

        def parse(value):
            raw = canonical(value)
            receipt = {"status": 200, "header_request_id": "UNAVAILABLE",
                       "response_size": len(raw), "response_sha256": sha(raw)}
            return provider.parse(raw, receipt, contract)

        self.assertEqual(parse(data)["tool_call_id"], "stub-call-dynamic")
        self.assertEqual(parse(data)["request_id"], "UNAVAILABLE")
        for usage in (None, {"prompt_tokens": -1, "completion_tokens": 18, "total_tokens": 17},
                      {"prompt_tokens": 100, "completion_tokens": 18, "total_tokens": 119},
                      {"prompt_tokens": 100, "completion_tokens": 129, "total_tokens": 229}):
            with self.assertRaises(ValueError):
                parse(data | {"usage": usage})
        row = data["choices"][0]
        message = row["message"]
        tool = message["tool_calls"][0]
        variants = [row | {"finish_reason": reason} for reason in ("stop", "aborted", "content_filter", "length")]
        variants += [row | {"message": message | {"tool_calls": calls}} for calls in (
            [tool, tool], [tool | {"function": tool["function"] | {"arguments": '{"candidate_id":"STOP","sql":"x"}'}}],
            [tool | {"function": tool["function"] | {"arguments": "{bad"}}],
            [tool | {"function": tool["function"] | {"arguments": '{"candidate_id":"unsupported"}'}}])]
        for item in variants:
            with self.assertRaises(ValueError):
                parse(data | {"choices": [item]})
        with self.assertRaises(ValueError):
            provider.identity("stub-response", "ID", c.NATIVE)
        with self.assertRaises(ValueError):
            provider.parse(raw[:-1], {"status": 200, "response_size": len(raw), "response_sha256": sha(raw)}, contract)


@unittest.skipUnless(LOCAL, "Requires admitted RPF-110 fresh SQLite and loopback")
class TransportTests(unittest.TestCase):
    def test_extra_business_field_stops_after_loopback_receipt(self):
        response = body(inner.OPS)
        function = response["choices"][0]["message"]["tool_calls"][0]["function"]
        function["arguments"] = canonical({"candidate_id": inner.OPS, "extra_parameter": "fixture"}).decode()
        with Session(SOURCE, c.STUB) as session, stub(reply=canonical(response)) as (port, seen):
            before = session.host.ledger.path.read_bytes()
            with self.assertRaisesRegex(Denied, "^TOOL_ARGUMENT_FIELDS_EXTRA$"):
                session.run(port=port)
            self.assertEqual(seen, [(c.PATH, c.request(session.contract), False)])
            self.assertEqual(session.edge.phase, "UNCERTAIN")
            self.assertIsNone(session.reserve(c.request(session.contract)))
            self.assertEqual(session.host.ledger.path.read_bytes(), before)
            events = [event["kind"] for event in session.edge.journal.events]
            self.assertIn("STUB_RESPONSE", events)
            self.assertNotIn("TOOL_SELECTION", events)
            self.assertNotIn("SEND_ENTRY", events)

    def test_rechained_loopback_response_cannot_expand_arguments(self):
        from ci.test_rpf110_live_witness import rechain
        from runtime.runproof_runtime.effectwitness import pge_r110_live_verify as verify
        from runtime.runproof_runtime.effectwitness.pge_r107_host import application
        from runtime.runproof_runtime.effectwitness.pge_r108_verify import bytes_for, presend_rows
        from runtime.runproof_runtime.effectwitness.pge_r110_live_witness import build

        with Session(SOURCE, c.STUB) as session, stub() as (port, _):
            session.run(port=port)
            valid, _ = build(session)
        bundle = strict(valid)
        response = strict(bytes_for(bundle["stub_response"], c.RESPONSE_CAP))
        function = response["choices"][0]["message"]["tool_calls"][0]["function"]
        function["arguments"] = canonical({"candidate_id": inner.OPS, "extra_parameter": "fixture"}).decode()
        raw = canonical(response)
        bundle["stub_response"] = application(raw)
        events = presend_rows(bytes_for(bundle["presend_wal"], verify.TRACE_LIMIT))
        receipt = next(row["body"] for row in events if row["kind"] == "STUB_RESPONSE")
        receipt.update(response_size=len(raw), response_sha256=sha(raw))
        selection = next(row["body"] for row in events if row["kind"] == "TOOL_SELECTION")
        selection["response_sha256"] = sha(raw)
        next(row["body"] for row in events if row["kind"] == "UNKNOWN")["selection_sha256"] = inner.digest(selection)
        bundle["presend_wal"] = rechain(events)
        tampered = canonical(bundle)
        with self.assertRaisesRegex(Denied, "^TOOL_ARGUMENT_FIELDS_EXTRA$"):
            verify.verify(tampered, SOURCE, sha(tampered))

    def test_loopback_posts_frozen_bytes_once_and_observes_optional_header(self):
        with Session(SOURCE, c.STUB) as session, stub(header="stub-header:1") as (port, seen):
            self.assertEqual(session.run(port=port), inner.OPS)
            self.assertEqual(seen, [(c.PATH, c.request(session.contract), False)])
            events = session.edge.journal.events
            receipt = next(row["body"] for row in events if row["kind"] == "STUB_RESPONSE")
            self.assertEqual(receipt["header_request_id"], "stub-header:1")
            with self.assertRaisesRegex(ValueError, "RETURN_PHASE"):
                session.edge.observe(receipt)
            self.assertEqual(len(seen), 1)
            self.assertNotIn("SEND_ENTRY", [row["kind"] for row in events])

    def test_redirect_and_partial_response_do_not_retry(self):
        for code, partial in ((301, False), (302, False), (200, True)):
            with self.subTest(code=code, partial=partial), Session(SOURCE, c.STUB) as session:
                with stub(code=code, partial=partial) as (port, seen):
                    with self.assertRaises((OSError, ValueError)):
                        session.run(port=port)
                    self.assertEqual(len(seen), 1)
                    self.assertIsNone(session.reserve(c.request(session.contract)))
                self.assertEqual(session.host.ledger.snapshot()["remaining"], inner.COST)

    def test_connect_errors_and_wrong_mode_leave_no_write_or_retry(self):
        for error in (socket.gaierror("fixture"), ssl.SSLCertVerificationError("fixture"), TimeoutError("fixture")):
            with self.subTest(error=type(error)), Session(SOURCE, c.STUB) as session:
                raw = c.request(session.contract)
                permit = session.reserve(raw)
                with self.assertRaisesRegex(ValueError, "NATIVE_ADMISSION"):
                    wire.native(session.edge, permit, raw, session.host.ledger.snapshot(), None)

                def broken(_):
                    raise error

                with self.assertRaises(type(error)):
                    wire._exchange(session.edge, permit, raw, session.host.ledger.snapshot(), c.STUB,
                                   3, broken, {})
                self.assertIsNone(session.reserve(raw))
                self.assertEqual(session.host.ledger.snapshot()["remaining"], inner.COST)
