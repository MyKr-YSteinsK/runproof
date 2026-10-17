"""HTTP security, durable single writer, real domains and offline content boundary."""
import concurrent.futures
import hashlib
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from runtime.runproof_runtime.effectwitness.cross_trial import run_trial
from runtime.runproof_runtime.effectwitness.lab_gateway import Gateway, PREFIX
from runtime.runproof_runtime.effectwitness.lab_store import SessionStore, LabError, canonical

ROOT = Path(__file__).resolve().parents[2]
TEMP = ROOT / ".local/rpf-45/tmp"
TOKEN = "test-only-gateway-secret-" + "x" * 32
ORIGIN = "http://127.0.0.1:4185"


def req(domain="order", key=None):
    return {"domain": domain, "mode": "LOCAL_CONTROLLED_CAPTURE", "request_id": key or str(uuid.uuid4())}


class LabTests(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=TEMP)
        self.root = Path(self.temp.name)
        self.store = SessionStore(self.root)
        self.server = Gateway(0, TOKEN, ORIGIN, self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02})
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(2)
        self.server.server_close()
        self.store.close()
        self.temp.cleanup()

    def http(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        default = {"Authorization": "Bearer " + TOKEN, "Origin": ORIGIN, "Content-Type": "application/json"}
        default.update(headers or {})
        if body is not None and not isinstance(body, bytes):
            body = canonical(body)
        connection.request(method, PREFIX + path, body, default)
        response = connection.getresponse()
        data = response.read()
        status, response_headers = response.status, dict(response.getheaders())
        connection.close()
        return status, json.loads(data), data, response_headers

    def wait(self):
        for thread in self.store.threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())

    def test_auth_origin_host_content_type_body_and_paths_fail_closed(self):
        cases = [("POST", "/sessions", req(), {"Authorization": ""}, 401),
            ("POST", "/sessions", req(), {"Origin": "https://evil.invalid"}, 403),
            ("POST", "/sessions", req(), {"Origin": "null"}, 403),
            ("POST", "/sessions", req(), {"Host": "evil.invalid"}, 403),
            ("POST", "/sessions", req(), {"Sec-Fetch-Site": "cross-site"}, 403),
            ("POST", "/sessions", req(), {"Content-Type": "text/plain"}, 415),
            ("POST", "/sessions", b"x" * 1025, {}, 413),
            ("POST", "/sessions", b'{"domain":"order","domain":"ops"}', {}, 400),
            ("POST", "/sessions", {**req(), "path": "../../outside"}, {}, 400),
            ("POST", "/sessions", req("unknown"), {}, 400),
            ("GET", "/sessions/../ledger.json", None, {}, 404),
            ("GET", "/capabilities?command=exec", None, {}, 404),
            ("OPTIONS", "/sessions", None, {}, 403)]
        for method, path, body, headers, expected in cases:
            with self.subTest(path=path, headers=headers):
                status, value, raw, response_headers = self.http(method, path, body, headers)
                self.assertEqual(status, expected, value)
                self.assertNotIn(TOKEN.encode(), raw)
                self.assertNotIn(b"D:\\", raw)
                self.assertNotIn("Access-Control-Allow-Origin", response_headers)
        self.assertEqual(self.store.capabilities()["remaining_reservations"], 3)

    def test_explicit_opt_in_and_missing_origin_are_rejected(self):
        result = subprocess.run([sys.executable, "-m", "runtime.runproof_runtime.effectwitness.lab_gateway"],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Explicit --enable-local-simulation required", result.stderr)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request("POST", PREFIX + "/sessions", canonical(req()),
                           {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
        response = connection.getresponse()
        self.assertEqual(response.status, 403)
        self.assertEqual(json.loads(response.read())["error_code"], "ORIGIN_REJECTED")
        connection.close()

    def test_actual_two_domains_http_idempotency_download_and_guarded_offline(self):
        sessions = []
        for domain in ("order", "ops"):
            request = req(domain)
            status, accepted, _, _ = self.http("POST", "/sessions", request)
            self.assertEqual(status, 202)
            self.wait()
            sid = accepted["session_id"]
            status, session, _, _ = self.http("GET", "/sessions/" + sid)
            self.assertEqual((status, session["status"]), (200, "COMPLETED"))
            self.assertEqual(session["usage"]["steps"], 7)
            self.assertEqual(session["usage"]["provider_requests"], 0)
            self.assertFalse(session["witness"]["external_anchor"])
            self.assertEqual(session["witness"]["status"], "CONTENT_CHECKED_LOCAL")
            self.assertEqual(session["result"]["claims"]["fault_activation"], "TRIGGERED")
            self.assertEqual(session["result"]["observation"]["cleanup"]["status"], "RESET_AND_REMOVED")
            self.assertFalse((ROOT / ".local/rpf-45" / session["run_id"]).exists())
            self.assertEqual(self.http("POST", "/sessions", request)[1]["session_id"], sid)
            self.assertEqual(self.http("POST", "/sessions", {**request, "domain": "ops" if domain == "order" else "order"})[0], 409)
            status, bundle, raw, headers = self.http("GET", "/sessions/" + sid + "/witness")
            self.assertEqual(status, 200)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), session["witness"]["sha256"])
            self.assertIn("attachment", headers["Content-Disposition"])
            self.assertEqual(bundle, session["result"])
            path = self.root / "offline.json"
            path.write_bytes(raw)
            code = """import sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,n,*a):
  if n.split('.')[0] in ('sqlite3','socket','docker') or n.endswith(('.provider','.pge_provider','.engine','.cross_trial','.ops','.orders','.lab_store')): raise AssertionError(n)
sys.meta_path.insert(0,Block())
from runtime.runproof_runtime.effectwitness.witness_verify import main
raise SystemExit(main())
"""
            env = {k:v for k,v in os.environ.items() if k not in ("DEEPSEEK_API_KEY", "RPF_EW_LAB_GATEWAY_TOKEN")}
            result = subprocess.run([sys.executable, "-c", code, str(path)], env=env, cwd=ROOT, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "UNANCHORED_INCONCLUSIVE")
            sessions.append(session)
        self.assertNotEqual(sessions[0]["run_id"], sessions[1]["run_id"])
        self.assertEqual(self.store.capabilities()["remaining_reservations"], 1)
        self.store.close()
        self.store = SessionStore(self.root)
        self.server.store = self.store
        self.assertEqual(self.store.get(sessions[0]["session_id"])["status"], "COMPLETED")
        self.assertEqual(self.store.create(req("order", sessions[0]["request_id"]))["session_id"], sessions[0]["session_id"])

    def test_concurrent_duplicate_busy_and_running_cancel_reconciles(self):
        entered, release = threading.Event(), threading.Event()
        def runner(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return run_trial(*args, **kwargs)
        self.store.runner = runner
        request = req()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                values = list(pool.map(lambda _: self.store.create(request), range(4)))
            self.assertEqual(len({s["session_id"] for s in values}), 1)
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.http("POST", "/sessions", req())[1]["error_code"], "GATEWAY_BUSY")
            sid = values[0]["session_id"]
            cancel = self.http("POST", "/sessions/" + sid + "/cancel", {})
            self.assertEqual(cancel[1]["status"], "CANCEL_REQUESTED")
            self.assertEqual(self.http("GET", "/sessions/" + sid + "/witness")[0], 409)
        finally:
            release.set()
        self.wait()
        completed = self.store.get(sid)
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertTrue(completed["cancel_requested"])
        self.assertEqual(completed["result"]["observation"]["fault"]["activation"], "TRIGGERED")

    def test_cancel_before_running_quota_and_process_lock(self):
        with self.assertRaisesRegex(LabError, "SESSION_STORE_ALREADY_OWNED"):
            SessionStore(self.root)
        for _ in range(3):
            with self.store.lock:
                s = self.store.create(req())
                cancelled = self.store.cancel(s["session_id"])
                self.assertEqual(cancelled["status"], "CANCELLED")
        self.wait()
        self.assertEqual(self.http("POST", "/sessions", req())[1]["error_code"], "TRIAL_QUOTA_EXHAUSTED")
        self.assertFalse(self.store.threads[0].is_alive())

    def test_failure_restart_and_corrupt_witness_never_replay_or_show_success(self):
        with patch.object(self.store, "runner", side_effect=RuntimeError("secret traceback should not escape")) as runner:
            accepted = self.store.create(req())
            self.wait()
            self.assertEqual(runner.call_count, 1)
        sid = accepted["session_id"]
        self.assertEqual(self.store.get(sid)["status"], "RECONCILE_REQUIRED")
        self.assertEqual(self.http("POST", "/sessions", req())[1]["error_code"], "RECONCILE_REQUIRED")
        self.store.close()
        ledger = json.loads((self.root / "sessions/ledger.json").read_bytes())
        ledger["sessions"][0]["status"] = "RUNNING"
        (self.root / "sessions/ledger.json").write_bytes(canonical(ledger))
        self.store = SessionStore(self.root)
        self.server.store = self.store
        self.assertEqual(self.store.get(sid)["error_code"], "RESTART_WITH_UNRESOLVED_EXECUTION")
        self.assertEqual(len(self.store.threads), 0)

    def test_missing_or_tampered_artifact_is_inconclusive_and_freezes_new_writes(self):
        s = self.store.create(req())
        self.wait()
        (self.root / "sessions" / s["session_id"] / "witness.json").write_bytes(b'{}')
        value = self.store.create({"domain": "order", "mode": "LOCAL_CONTROLLED_CAPTURE", "request_id": s["request_id"]})
        self.assertEqual(value["status"], "INCONCLUSIVE")
        self.assertIsNone(value["result"])
        self.assertEqual(self.http("GET", "/sessions/" + s["session_id"] + "/witness")[0], 409)
        self.assertEqual(self.http("GET", "/sessions/session-" + "0" * 32)[0], 404)
        self.assertFalse(self.store.capabilities()["enabled"])

    def test_committed_but_unresolved_state_is_owned_quarantined_and_never_reset(self):
        import sqlite3
        from contextlib import closing
        from runtime.runproof_runtime.effectwitness.ops import OpsSandbox
        captures = []
        def interrupted(contracts, **kwargs):
            sandbox = OpsSandbox(contracts, storage_task="rpf-45")
            sandbox.initialize()
            sandbox.apply(**{k: contracts.effect[k] for k in ("config_id", "operation_id", "release")})
            captures.append((contracts, sandbox))
            raise RuntimeError("simulated interrupted response")
        self.store.runner = interrupted
        accepted = self.store.create(req("ops"))
        self.wait()
        s = self.store.get(accepted["session_id"])
        quarantine = ROOT / ".local/quarantine/rpf-45" / s["session_id"]
        try:
            self.assertEqual(s["status"], "RECONCILE_REQUIRED")
            self.assertEqual(s["quarantine_status"], "QUARANTINED")
            with closing(sqlite3.connect(quarantine / "ops.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT release,effect_count FROM config").fetchone(), ("release-v2", 1))
                self.assertEqual(db.execute("SELECT reset_generation FROM environment").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT count(*) FROM receipts").fetchone()[0], 1)
            with self.assertRaisesRegex(LabError, "RECONCILE_REQUIRED"):
                self.store.create(req())
        finally:
            contracts, sandbox = captures[0]
            quarantine.rename(sandbox.directory)
            sandbox.cleanup()


if __name__ == "__main__":
    unittest.main()
