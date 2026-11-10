"""Admission checks and one isolated two-domain competition test."""
from contextlib import closing
from hashlib import sha256
from io import BytesIO
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from runtime.runproof_runtime.effectwitness.product_local_contracts import MODE, canonical
from runtime.runproof_runtime.effectwitness.product_local_gateway import ORIGIN, PREFIX, server_for
from runtime.runproof_runtime.effectwitness.product_local_session import ROOT, Conflict, safe_path
from runtime.runproof_runtime.effectwitness.product_local_verify import verify
from runtime.runproof_runtime.effectwitness.rpf112_competition_gateway import CompetitionProduct, competition_owner


class CompetitionTests(unittest.TestCase):
    def test_only_exact_nonce_is_admitted(self):
        nonce = "a" * 32
        self.assertEqual(competition_owner(nonce), ROOT / f"competition-rpf112-{nonce}")
        for wrong in ("live", str(ROOT / "live"), "../live", nonce.upper(), nonce + "\n"):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, "COMPETITION_NONCE_REQUIRED"):
                competition_owner(wrong)

    def test_missing_http_admission_never_calls_product(self):
        token = "a" * 64
        # Exercise the original HTTP handler with real request bytes and no extra listener.
        with patch("http.server.HTTPServer.__init__", autospec=True, return_value=None) as init:
            server_for(None, token)
        handler_type = init.call_args.args[2]
        body = canonical({"mode": MODE, "request_id": "competition-http"})
        for origin, auth in (("", token), (ORIGIN, ""), ("http://wrong.invalid", token)):
            headers = f"Host: 127.0.0.1:8780\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
            if origin:
                headers += f"Origin: {origin}\r\n"
            if auth:
                headers += f"Authorization: Bearer {auth}\r\n"
            handler = object.__new__(handler_type)
            handler.rfile = BytesIO(f"POST {PREFIX}/session HTTP/1.1\r\n{headers}\r\n".encode() + body)
            handler.wfile = BytesIO()
            handler.client_address = ("127.0.0.1", 1)
            handler.server = type("Server", (), {"server_port": 8780})()
            handler.handle_one_request()
            self.assertTrue(handler.wfile.getvalue().startswith(b"HTTP/1.0 403"))

    def test_budget_duplicate_and_cross_source_witness(self):
        owner = safe_path(ROOT / "tests" / f"rpf112-{uuid4().hex}")
        owner.mkdir(parents=True, exist_ok=False)
        request = {"mode": MODE, "request_id": "competition-test"}
        with CompetitionProduct(owner).open() as product:
            self.assertEqual(product.capability()["remaining"], 1)
            record = product.create(request)
            self.assertEqual(record["status"], "COMPLETED")
            self.assertEqual(product.create(request), record)
            self.assertEqual(product.capability()["remaining"], 0)
            self.assertEqual(product.capability()["provider_reservations"], 0)
            with self.assertRaises(Conflict):
                product.create({**request, "request_id": "not-admitted"})
            raw = product.lookup("id", record["session_id"])[1]
        for domain in ("order", "ops"):
            db_uri = (owner / record["session_id"] / f"{domain}.sqlite").as_uri() + "?mode=ro"
            with closing(sqlite3.connect(db_uri, uri=True)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM receipts").fetchone()[0], 1)
        anchor = sha256(raw).hexdigest()
        self.assertEqual(verify(raw, anchor)["status"], "VERIFIED_ANCHORED")
        with self.assertRaisesRegex(ValueError, "ANCHOR_MISMATCH"):
            verify(raw, "0" * 64)
        for field, changed in (("session_id", "0" * 32), ("source", {})):
            candidate = json.loads(raw)
            candidate["session"][field] = changed
            changed_bytes = canonical(candidate)
            with self.assertRaises(ValueError):
                verify(changed_bytes, sha256(changed_bytes).hexdigest())
