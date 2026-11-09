"""RPF-100 isolated local conformance tests. No Provider or old owners."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from http.client import HTTPConnection
import json
import os
import sqlite3
import subprocess
import sys
import threading
import unittest
from uuid import uuid4

from runtime.runproof_runtime.effectwitness.product_local_contracts import MODE, canonical, decide, digest, strict
from runtime.runproof_runtime.effectwitness.product_local_gateway import ORIGIN, PREFIX, server_for
from runtime.runproof_runtime.effectwitness.product_local_session import ROOT, Conflict, Product, safe_path
from runtime.runproof_runtime.effectwitness.product_local_verify import verify


class ProductTests(unittest.TestCase):
    def owner(self):
        owner = safe_path(ROOT / "tests" / uuid4().hex)
        owner.mkdir(parents=True, exist_ok=False)
        return owner

    def test_real_commits_reconcile_idempotency_and_offline_witness(self):
        owner = self.owner()
        request = {"mode": MODE, "request_id": "positive-request"}
        with Product(owner).open() as product:
            with ThreadPoolExecutor(2) as pool:
                first, duplicate = list(pool.map(product.create, [request, request]))
            self.assertEqual(first, duplicate)
            self.assertEqual(first["status"], "COMPLETED")
            self.assertEqual(first["rounds"][0]["tool_status"], "UNKNOWN_OUTCOME")
            self.assertEqual(first["selection"]["input_feedback_sha256"], first["rounds"][0]["feedback_sha256"])
            self.assertEqual(first["provider_reservations"], 0)
            for domain in ("order", "ops"):
                with closing(sqlite3.connect((owner / first["session_id"] / (domain + ".sqlite")).as_uri() + "?mode=ro", uri=True)) as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM receipts").fetchone()[0], 1)
            with self.assertRaises(OSError):
                with Product(owner).open():
                    self.fail("second writer was admitted")
            raw = product.lookup("id", first["session_id"])[1]
            self.assertEqual(verify(raw)["status"], "CONTENT_CHECKED_LOCAL")
        with Product(owner).open() as reopened:
            self.assertEqual(reopened.create(request), first)
        from hashlib import sha256
        anchor = sha256(raw).hexdigest()
        file = owner / "witness.json"
        file.write_bytes(raw)
        result = subprocess.run([sys.executable, "-B", "-m", "runtime.runproof_runtime.effectwitness.product_local_verify",
                                 str(file), "--expected-sha256", anchor], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "VERIFIED_ANCHORED")
        for mutate in (
            lambda d: d["rounds"][0]["after"]["receipts"][0].update(amount_minor=1),
            lambda d: d["rounds"][0]["outcome"].update(state_diff={}),
            lambda d: d["rounds"][0]["fault"].update(observed=False),
            lambda d: d["selection"].update(input_feedback_sha256="bad"),
            lambda d: d["selection"].update(decision="MUST_STOP"),
            lambda d: d["candidates"][0]["effect"].update(amount_minor=1),
            lambda d: d["source"].clear(),
            lambda d: d["rounds"].reverse(),
            lambda d: d["events"].reverse(),
            lambda d: d.update(session_id="0" * 32),
        ):
            bad = strict(raw)
            mutate(bad["session"])
            with self.assertRaises(ValueError):
                verify(canonical(bad))
            with self.assertRaisesRegex(ValueError, "ANCHOR_MISMATCH"):
                verify(canonical(bad), anchor)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_KEY"):
            verify(raw.replace(b'{', b'{"schema":"forged",', 1))
        trusted = first["rounds"][0]["feedback"]
        for field, value in (("contract_outcome", "INCONCLUSIVE"), ("fault", {}), ("domain", "ops")):
            changed = {**trusted, field: value}
            self.assertEqual(decide(first["candidates"], changed, digest(changed), first["session_id"])["decision"], "MUST_STOP")
        self.assertEqual(decide(first["candidates"], trusted, "bad", first["session_id"])["decision"], "MUST_STOP")

    def test_real_identity_failure_retains_order_and_blocks_ops_and_new_requests(self):
        owner = self.owner()
        request = {"mode": MODE, "request_id": "negative-request"}
        with Product(owner, reject_order_authority=True).open() as product:
            record = product.create(request)
            self.assertEqual(record["status"], "RECONCILE_REQUIRED")
            self.assertEqual(record["selection"]["decision"], "MUST_STOP")
            self.assertIn("UNKNOWN_OBSERVED", [e["kind"] for e in record["events"]])
            self.assertIsNone(product.lookup("id", record["session_id"])[1])
        folder = owner / record["session_id"]
        self.assertFalse((folder / "ops.sqlite").exists())
        with closing(sqlite3.connect((folder / "order.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM receipts").fetchone()[0], 1)
        with Product(owner).open() as product:
            self.assertEqual(product.create(request), record)
            self.assertEqual(product.capability()["provider_reservations"], 0)
            with self.assertRaises(Conflict):
                product.create({"mode": MODE, "request_id": "different-request"})

    def test_interruption_after_write_intent_is_never_replayed(self):
        owner = self.owner()
        code = """
import os,sys
from runtime.runproof_runtime.effectwitness.product_local_session import Product
from runtime.runproof_runtime.effectwitness.product_local_contracts import MODE
class Interrupted(Product):
    def event(self, record, kind, domain=None):
        super().event(record, kind, domain)
        if kind == 'UNKNOWN_OBSERVED':
            os._exit(79)
with Interrupted(sys.argv[1]).open() as service:
    service.create({'mode': MODE, 'request_id':'crash-request'})
"""
        result = subprocess.run([sys.executable, "-B", "-c", code, str(owner)], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 79, result.stderr)
        with Product(owner).open() as product:
            record, witness = product.lookup("request", "crash-request")
            self.assertEqual(record["status"], "RECONCILE_REQUIRED")
            self.assertIsNone(witness)
            self.assertTrue(product.capability()["blocked"])
            self.assertFalse((owner / record["session_id"] / "ops.sqlite").exists())
            self.assertEqual(record["provider_reservations"], 0)

    def test_http_rejects_bad_admission_and_reads_back_real_session(self):
        owner = self.owner()
        token = "a" * 64
        with Product(owner).open() as product, server_for(product, token, 0) as server:
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                headers = {"Authorization": "Bearer " + token, "Origin": ORIGIN, "Content-Type": "application/json"}

                def request(method, route, body=None, overrides=None):
                    with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=8)) as connection:
                        connection.request(method, PREFIX + route, body, {**headers, **(overrides or {})})
                        response = connection.getresponse()
                        return response.status, response.read()

                self.assertEqual(request("GET", "/capability", overrides={"Host": "example.invalid"})[0], 403)
                self.assertEqual(request("GET", "/capability", overrides={"Authorization": "Bearer wrong"})[0], 403)
                self.assertEqual(request("POST", "/session", b"{}", {"Origin": "http://example.invalid"})[0], 403)
                self.assertEqual(request("POST", "/session", b" " * 4097)[0], 413)
                self.assertEqual(request("POST", "/session", b'{"mode":0,"mode":1}')[0], 400)
                self.assertEqual(request("POST", "/session", canonical({"mode": MODE, "request_id": "http-request", "path": "x"}))[0], 400)
                self.assertEqual(request("POST", "/unknown", b"{}")[0], 404)
                self.assertEqual(product.capability()["remaining"], 2)
                status, body = request("POST", "/session", canonical({"mode": MODE, "request_id": "http-request"}))
                self.assertEqual(status, 200)
                data = strict(body)
                self.assertEqual(data["status"], "COMPLETED")
                self.assertEqual(request("GET", "/request/http-request")[1], body)
                status, raw = request("GET", "/witness/" + data["session_id"])
                self.assertEqual(status, 200)
                self.assertEqual(verify(raw)["status"], "CONTENT_CHECKED_LOCAL")
            finally:
                server.shutdown()
                worker.join()

    def test_owner_escape_rejected(self):
        with self.assertRaisesRegex(ValueError, "OWNER_SCOPE"):
            safe_path(ROOT / ".." / "other")
        owner = self.owner()
        original = owner / "original"
        original.write_bytes(b"sentinel")
        alias = owner / "alias"
        os.link(original, alias)
        with self.assertRaisesRegex(ValueError, "OWNER_HARDLINK"):
            safe_path(alias)
        self.assertEqual(original.read_bytes(), b"sentinel")

    def test_failed_durable_unknown_checkpoint_stops_second_domain(self):
        class FailedCheckpoint(Product):
            def event(self, record, kind, domain=None):
                if kind == "UNKNOWN_OBSERVED":
                    raise sqlite3.OperationalError("synthetic durable checkpoint failure")
                super().event(record, kind, domain)

        owner = self.owner()
        with FailedCheckpoint(owner).open() as product:
            record = product.create({"mode": MODE, "request_id": "checkpoint-failure"})
            self.assertEqual(record["status"], "RECONCILE_REQUIRED")
            self.assertEqual(record["selection"]["decision"], "MUST_STOP")
            self.assertEqual(record["provider_reservations"], 0)
            self.assertFalse((owner / record["session_id"] / "ops.sqlite").exists())
