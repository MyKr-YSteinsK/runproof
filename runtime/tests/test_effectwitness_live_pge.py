"""RPF-46 free protocol, authority, quota, HTTP, crash and negative controls."""
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from runtime.runproof_runtime.effectwitness.contracts import ROOT, canonical, digest
from runtime.runproof_runtime.effectwitness.cross_trial import run_trial
from runtime.runproof_runtime.effectwitness.lab_store import SessionStore, LabError
from runtime.runproof_runtime.effectwitness.lab_exploration import ExplorationStore
from runtime.runproof_runtime.effectwitness.lab_evidence import verify_session, validate_trial, LIMITS
from runtime.runproof_runtime.effectwitness.lab_gateway import Gateway, PREFIX
from runtime.runproof_runtime.effectwitness.witness_verify import verify_bytes
from runtime.runproof_runtime.effectwitness.provider import request_completion

TEMP = ROOT / ".local/rpf-46/tmp"
TOKEN = "test-only-gateway-" + "x" * 40
ORIGIN = "http://127.0.0.1:4185"


def request(key=None):
    return {"domain": "order", "mode": "PGE_LIVE_ORDER", "request_id": key or str(uuid.uuid4())}


def response(k, n=1):
    return {"id": "response-" + str(n), "model": "deepseek-flash", "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            "choices": [{"finish_reason": "tool_calls", "message": {"content": "DO_NOT_PERSIST_FREE_TEXT", "reasoning_content": "DO_NOT_PERSIST_REASONING",
                "tool_calls": [{"id": "call-" + str(n), "type": "function", "function": {"name": "select_experiment", "arguments": canonical({"candidate_id": k}).decode()}}]}}]}


def fake_provider(choices, bodies):
    def invoke(body, budget, records, checkpoint):
        n = len(records)+1
        bodies.append(copy.deepcopy(body))
        budget.reserve_request(len(canonical(body))+1024, body["max_tokens"])
        record = {"attempt": n, "status": "ATTEMPTED", "requested_model": body["model"]}
        records.append(record)
        checkpoint()
        data = response(choices[n-1], n)
        budget.record_usage(data["usage"])
        record.update(status="RECEIVED", http_status=200, response_id=data["id"], returned_model=data["model"], usage=data["usage"])
        checkpoint()
        return data
    return invoke


class LiveTests(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=TEMP)
        self.root = Path(self.temp.name)
        self.owner = SessionStore(self.root, storage_task="rpf-46")
        self.key = patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only-not-a-credential"})
        self.key.start()
        self.bodies = []

    def tearDown(self):
        self.owner.close()
        self.key.stop()
        self.temp.cleanup()

    def live(self, choices=("normal", "response-lost"), **kw):
        return ExplorationStore(self.owner, root=self.root, enabled=True,
            provider=kw.pop("provider", fake_provider(choices, self.bodies)), **kw)

    def wait(self, live):
        for t in live.threads:
            t.join(8)
            self.assertFalse(t.is_alive())

    def test_two_round_authority_feedback_exact_reinjection_and_v2_eligibility(self):
        live = self.live()
        req = request()
        sid = live.create(req)["session_id"]
        self.wait(live)
        s = live.get(sid)
        self.assertEqual(s["status"], "COMPLETED", s["error_code"])
        self.assertEqual((s["usage"]["provider_requests"], s["usage"]["steps"], s["usage"]["fault_trials"]), (2,16,2))
        self.assertEqual(live.create(req)["session_id"], sid)
        self.assertEqual(len(live.threads), 1)
        with self.assertRaisesRegex(LabError, "QUOTA_EXHAUSTED"): live.create(request())
        self.assertEqual(s["research"]["L1"], True)
        self.assertEqual(s["research"]["L2"], True)
        first, second = s["trials"]
        self.assertEqual(self.bodies[1]["messages"][-1], {"role":"tool", "tool_call_id":s["selections"][0]["tool_call_id"],
                "content":canonical(first["feedback"]).decode()})
        self.assertEqual(digest(self.bodies[1]["messages"]), s["selections"][1]["input_messages_hash"])
        self.assertEqual(self.bodies[0]["tools"], self.bodies[1]["tools"])
        self.assertNotIn("feedback_sha256", self.bodies[0]["messages"][1]["content"])
        self.assertEqual(second["observation"]["reconciliation"]["status"], "RECONCILED_COMMITTED")
        self.assertEqual(first["witness"]["status"], "NOT_ISSUED_PROFILE_NOT_ELIGIBLE")
        with self.assertRaisesRegex(LabError, "NOT_ISSUED"): live.witness(sid,"1")
        raw = live.witness(sid,"2")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), second["witness"]["sha256"])
        self.assertEqual(verify_bytes(raw)["schema_version"], "rpf-effect-witness-v2")
        self.assertEqual(verify_session(s)["status"], "CONTENT_CHECKED_LOCAL")
        seq = [e["type"] for e in s["events"]]
        feedback_idx = seq.index("AUTHORITY_FEEDBACK_VALIDATED")
        next_input = seq.index("PROVIDER_INPUT_FROZEN", feedback_idx)
        self.assertGreater(next_input, feedback_idx)
        for t in s["trials"]:
            self.assertFalse((ROOT / ".local/rpf-46" / t["run_id"]).exists())
            self.assertEqual(len(t["observation"]["authority_after"]["data"]["receipts"]), 1)
        self.assertNotEqual(first["run_id"],second["run_id"])
        persisted = live.path.read_text()
        for forbidden in ("test-only-not-a-credential", "DO_NOT_PERSIST_FREE_TEXT", "DO_NOT_PERSIST_REASONING", "Authorization", '"messages"'):
            self.assertNotIn(forbidden, persisted)
        self.owner.close()
        self.owner = SessionStore(self.root, storage_task="rpf-46")
        again = self.live()
        self.assertEqual(again.get(sid)["status"], "COMPLETED")
        self.assertEqual(again.capabilities()["remaining_sessions"], 0)
        self.assertEqual(again.threads, [])

    def test_repeat_is_legal_negative_research_and_untriggered_never_witness(self):
        live = self.live(("planned-untriggered", "planned-untriggered"))
        sid=live.create(request())["session_id"];self.wait(live);s=live.get(sid)
        self.assertEqual(s["status"], "COMPLETED", s["error_code"])
        self.assertTrue(s["research"]["L1"]);self.assertFalse(s["research"]["L2"])
        self.assertEqual(s["research"]["H1"], "NOT_PROVEN_IN_THIS_RUN")
        self.assertEqual(s["trials"][1]["new_facts"], [])
        self.assertTrue(all(t["claims"]["fault_activation"]=="NOT_TRIGGERED" for t in s["trials"]))

    def test_provider_attempt_is_durable_before_transport_unknown_usage_blocks_both_modes(self):
        def unknown(body,budget,records,checkpoint):
            budget.reserve_request(1000,128)
            records.append({"attempt":1,"status":"ATTEMPTED"})
            checkpoint()
            saved=json.loads(live.path.read_bytes())["data"]["session"]
            self.assertEqual(saved["provider_requests"][0]["status"],"ATTEMPTED")
            self.assertFalse(saved["usage"]["usage_known"])
            self.assertIsNone(saved["usage"]["tokens"])
            raise TimeoutError()
        live=self.live(provider=unknown);sid=live.create(request())["session_id"];self.wait(live)
        s=live.get(sid)
        self.assertEqual(s["status"],"RECONCILE_REQUIRED");self.assertEqual(s["trials"],[])
        self.assertFalse(self.owner.capabilities()["enabled"])
        with self.assertRaisesRegex(LabError,"RECONCILE_REQUIRED"):
            self.owner.create({"domain":"order","mode":"LOCAL_CONTROLLED_CAPTURE","request_id":"free-request"})

    def test_cross_mode_busy_and_cancel_after_provider_does_not_start_trial(self):
        entered,release=threading.Event(),threading.Event()
        base=fake_provider(("normal","normal"),self.bodies)
        def waiting(*args):
            entered.set();self.assertTrue(release.wait(5));return base(*args)
        live=self.live(provider=waiting)
        try:
            sid=live.create(request())["session_id"]
            self.assertTrue(entered.wait(2))
            self.assertTrue(self.owner.capabilities()["busy"])
            with self.assertRaisesRegex(LabError,"GATEWAY_BUSY"):
                self.owner.create({"domain":"ops","mode":"LOCAL_CONTROLLED_CAPTURE","request_id":"free-request"})
            self.assertEqual(live.cancel(sid)["status"],"CANCEL_REQUESTED")
        finally:release.set()
        self.wait(live);s=live.get(sid)
        self.assertEqual(s["status"],"CANCELLED");self.assertEqual(s["trial_reservations"],[])
        self.assertEqual(s["usage"]["provider_requests"],1)

    def test_free_capture_busy_blocks_paid_without_consuming_quota(self):
        entered,release=threading.Event(),threading.Event()
        def waiting(*a,**kw):
            entered.set();self.assertTrue(release.wait(5));return run_trial(*a,**kw)
        self.owner.runner=waiting;live=self.live()
        try:
            self.owner.create({"domain":"order","mode":"LOCAL_CONTROLLED_CAPTURE","request_id":"free-request"})
            self.assertTrue(entered.wait(2))
            with self.assertRaisesRegex(LabError,"GATEWAY_BUSY"):live.create(request())
            self.assertEqual(live.capabilities()["remaining_sessions"],1)
        finally:release.set()
        for t in self.owner.threads:t.join(8)

    def test_cancel_before_execute_consumes_session_and_zero_requests(self):
        live=self.live()
        with self.owner.lock:
            sid=live.create(request())["session_id"];live.cancel(sid)
        self.wait(live);s=live.get(sid)
        self.assertEqual(s["status"],"CANCELLED");self.assertEqual(self.bodies,[])
        self.assertEqual(live.capabilities()["remaining_sessions"],0)

    def test_restart_running_or_missing_reserved_ledger_never_reopens_quota(self):
        live=self.live()
        with self.owner.lock:
            sid=live.create(request())["session_id"];live.cancel(sid)
        self.wait(live)
        live.data["session"]["status"]="RUNNING";live._save()
        self.owner.close();self.owner=SessionStore(self.root,storage_task="rpf-46")
        new=self.live();s=new.get(sid)
        self.assertEqual(s["status"],"RECONCILE_REQUIRED");self.assertEqual(new.threads,[])
        self.owner.close();self.owner=SessionStore(self.root,storage_task="rpf-46")
        new.path.unlink()
        with self.assertRaisesRegex(LabError,"LEDGER_UNAVAILABLE"):self.live()

    def test_invalid_choice_wrong_model_extra_parameters_and_duplicate_json_stop(self):
        for change in ("candidate","tool","extra","duplicate","model","callid","multiple"):
            with self.subTest(change=change):
                root=self.root/change
                owner=SessionStore(root,storage_task="rpf-46")
                def malicious(body,budget,records,checkpoint):
                    d=fake_provider(("normal",),[])(body,budget,records,checkpoint)
                    f=d["choices"][0]["message"]["tool_calls"][0]["function"]
                    if change=="candidate":f["arguments"]='{"candidate_id":"shell"}'
                    if change=="tool":f["name"]="shell"
                    if change=="extra":f["arguments"]='{"candidate_id":"normal","path":"outside"}'
                    if change=="duplicate":f["arguments"]='{"candidate_id":"normal","candidate_id":"response-lost"}'
                    if change=="model":d["model"]="unapproved"
                    if change=="callid":d["choices"][0]["message"]["tool_calls"][0]["id"]="unsafe text"
                    if change=="multiple":d["choices"].append(d["choices"][0])
                    return d
                live=ExplorationStore(owner,root=root,enabled=True,provider=malicious)
                try:
                    sid=live.create(request())["session_id"];self.wait(live);s=live.get(sid)
                    self.assertIn(s["status"],("ERROR","RECONCILE_REQUIRED"));self.assertEqual(s["trials"],[])
                    self.assertEqual(s["usage"]["provider_requests"],1)
                finally:owner.close()

    def test_negative_evidence_missing_authority_wrong_issuer_hash_and_session(self):
        live=self.live();sid=live.create(request())["session_id"];self.wait(live);s=live.get(sid)
        changes=[lambda t:t["observation"]["authority_after"].update(sha256="0"*64),
            lambda t:t.update(plan_digest="0"*64),lambda t:t["feedback"].update(fault_activation="TRIGGERED"),
            lambda t:t["observation"]["authority_before"]["data"].update(reader_id="tool"),
            lambda t:t["witness"].update(status="CONTENT_CHECKED_LOCAL"),lambda t:t["claims"].update(attribution_strength="CAUSAL")]
        for change in changes:
            t=copy.deepcopy(s["trials"][0]);change(t)
            with self.assertRaises(Exception):validate_trial(t,s["plan"])
        path=live.root/sid/"trial-2.json"
        b=json.loads(path.read_bytes());b["issuer"]["issuer_id"]="wrong-issuer"
        with self.assertRaises(Exception):verify_bytes(canonical(b))
        path.write_bytes(b'{}')
        with self.assertRaisesRegex(LabError,"EVIDENCE_INVALID"):live.get(sid)
        self.assertFalse(self.owner.capabilities()["enabled"])

    def test_strict_http_new_routes_do_not_expand_old_schema(self):
        live=self.live();server=Gateway(0,TOKEN,ORIGIN,self.owner)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01});thread.start()
        def hreq(method,path,body=None,extra=None):
            c=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
            headers={"Authorization":"Bearer "+TOKEN,"Origin":ORIGIN,"Content-Type":"application/json",**(extra or {})}
            c.request(method,PREFIX+path,canonical(body) if body is not None else None,headers)
            r=c.getresponse();raw=r.read();status=r.status;c.close();self.assertNotIn(TOKEN.encode(),raw)
            return status,json.loads(raw)
        try:
            self.assertEqual(hreq("GET","/explorations/capabilities")[1]["explorer"],"AVAILABLE")
            self.assertEqual(hreq("POST","/sessions",request())[0],400)
            for extra in ({"Origin":"https://evil.invalid"},{"Host":"evil.invalid"},{"Sec-Fetch-Site":"cross-site"},{"Authorization":""}):
                self.assertIn(hreq("POST","/explorations",request(),extra)[0],(401,403))
            for body in ({**request(),"path":"../"},{**request(),"domain":"ops"},{**request(),"candidate_id":"normal"}):
                self.assertEqual(hreq("POST","/explorations",body)[0],400)
            self.assertEqual(hreq("GET","/explorations/../ledger.json")[0],404)
            sid=hreq("POST","/explorations",request())[1]["session_id"];self.wait(live)
            self.assertEqual(hreq("GET","/explorations/"+sid)[1]["status"],"COMPLETED")
            self.assertEqual(hreq("GET","/explorations/"+sid+"/witness/1")[0],409)
            self.assertEqual(hreq("GET","/explorations/"+sid+"/witness/2")[0],200)
            self.assertEqual(hreq("POST","/explorations/"+sid+"/cancel",{})[0],409)
        finally:server.shutdown();thread.join(2);server.server_close()

    def test_real_transport_mock_unknown_usage_http_timeout_no_auto_retry(self):
        from unittest.mock import MagicMock
        for condition in ("missing-usage","http-error","timeout"):
            with self.subTest(condition=condition):
                root=self.root/condition;owner=SessionStore(root,storage_task="rpf-46")
                c=MagicMock();r=c.getresponse.return_value;r.status=200;r.getheader.return_value="safe-request-id"
                d=response("normal");d.pop("usage");r.read.return_value=canonical(d)
                if condition=="http-error":r.status=503
                if condition=="timeout":c.request.side_effect=TimeoutError()
                with patch("runtime.runproof_runtime.effectwitness.provider.http.client.HTTPSConnection",return_value=c) as factory:
                    live=ExplorationStore(owner,root=root,enabled=True,provider=request_completion)
                    try:
                        sid=live.create(request())["session_id"];self.wait(live);s=live.get(sid)
                        self.assertEqual(factory.call_count,1);self.assertEqual(s["usage"]["provider_requests"],1)
                        self.assertIsNone(s["usage"]["tokens"]);self.assertEqual(s["status"],"RECONCILE_REQUIRED")
                        self.assertEqual(s["trials"],[])
                    finally:owner.close()

    def test_opt_in_missing_key_and_hard_budget(self):
        from runtime.runproof_runtime.effectwitness.engine import Budget
        live=self.live()
        live.enabled=False;self.assertEqual(live.capabilities()["explorer"],"DISABLED")
        with self.assertRaises(LabError):live.create(request())
        live.enabled=True
        with patch.dict(os.environ,{"DEEPSEEK_API_KEY":""}):
            self.assertEqual(live.capabilities()["explorer"],"KEY_MISSING")
            with self.assertRaises(LabError):live.create(request())
        for key,value,method in (("provider_requests",0,lambda b:b.reserve_request(1,1)),("tokens",1,lambda b:b.reserve_request(2,1)),
                ("cost_cny",0,lambda b:b.reserve_request(1,1)),("steps",0,lambda b:b.step()),("fault_trials",0,lambda b:b.fault_trial()),
                ("seconds",0,lambda b:b.check_time())):
            with self.subTest(limit=key):
                b=Budget({**LIMITS,key:value})
                with self.assertRaises(Exception):method(b)

    def test_trial_reserved_before_sqlite_and_interrupted_commit_preserved(self):
        from runtime.runproof_runtime.effectwitness.orders import OrderSandbox
        import sqlite3
        from contextlib import closing
        captured=[]
        def interrupted(c,**kw):
            saved=json.loads(live.path.read_bytes())["data"]["session"]
            self.assertEqual(saved["trial_reservations"][0]["status"],"ATTEMPTED")
            self.assertEqual(saved["usage"]["steps"],8)
            self.assertEqual(kw["storage_task"],"rpf-46")
            sandbox=OrderSandbox(c,storage_task="rpf-46");sandbox.initialize()
            f=c.effect;sandbox.refund(f["order_id"],f["operation_id"],f["amount_minor"])
            captured.append(sandbox)
            raise RuntimeError("simulated crash after commit")
        live=self.live(runner=interrupted)
        sid=live.create(request())["session_id"];self.wait(live);s=live.get(sid)
        sandbox=captured[0];destination=ROOT/".local/quarantine/rpf-46"/sandbox.contracts.experiment["run_id"]
        try:
            self.assertEqual(s["status"],"RECONCILE_REQUIRED");self.assertEqual(len(s["provider_requests"]),1)
            self.assertEqual(s["trial_reservations"][0]["quarantine_status"],"PRESERVED_QUARANTINE")
            with closing(sqlite3.connect((destination/"orders.sqlite3").as_uri()+"?mode=ro",uri=True)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM refunds").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT reset_generation FROM environment").fetchone()[0],0)
        finally:
            # Fixture-only recovery after independently confirming the one receipt.
            destination.rename(sandbox.directory);sandbox.cleanup()

    def test_corrupt_ledger_duplicate_owner_and_repeat_response_lost(self):
        live=self.live(("response-lost","response-lost"))
        with self.assertRaisesRegex(LabError,"ALREADY_OWNED"):self.live()
        sid=live.create(request())["session_id"];self.wait(live);s=live.get(sid)
        self.assertEqual(s["status"],"COMPLETED");self.assertFalse(s["research"]["L2"])
        self.assertEqual(verify_bytes(live.witness(sid,"1"))["schema_version"],"rpf-effect-witness-v2")
        self.owner.close();self.owner=SessionStore(self.root,storage_task="rpf-46")
        live.path.write_bytes(b'{"data":{}}')
        with self.assertRaisesRegex(LabError,"LEDGER_UNAVAILABLE"):self.live()

    def test_session_offline_checker_requires_no_provider_database_or_socket(self):
        import subprocess
        import sys
        live=self.live();sid=live.create(request())["session_id"];self.wait(live)
        session=live.get(sid);path=self.root/"session.json";path.write_bytes(canonical(session))
        code="""import sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,n,*a):
  if n.split('.')[0] in ('socket','sqlite3','docker','http') or n.endswith(('.provider','.pge_provider','.engine','.cross_trial','.orders','.lab_exploration')): raise AssertionError(n)
sys.meta_path.insert(0,Block())
from runtime.runproof_runtime.effectwitness.lab_evidence import main
raise SystemExit(main())
"""
        env={k:v for k,v in os.environ.items() if k not in ("DEEPSEEK_API_KEY","RPF_EW_LAB_GATEWAY_TOKEN")}
        result=subprocess.run([sys.executable,"-B","-c",code,str(path)],cwd=ROOT,env=env,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"],"CONTENT_CHECKED_LOCAL")
        session["research"]["attribution"]="CAUSAL";path.write_bytes(canonical(session))
        result=subprocess.run([sys.executable,"-B","-c",code,str(path)],cwd=ROOT,env=env,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,2)

    def test_failed_durable_reservation_starts_no_thread_and_cannot_reopen(self):
        live=self.live()
        with patch("runtime.runproof_runtime.effectwitness.lab_exploration.atomic_write",side_effect=OSError("fixture storage failure")):
            with self.assertRaises(OSError):live.create(request())
        self.assertEqual(live.threads,[]);self.assertEqual(self.bodies,[])
        self.assertTrue(live.seal.exists());self.assertTrue(self.owner.capabilities()["busy"])
        self.owner.close();self.owner=SessionStore(self.root,storage_task="rpf-46")
        with self.assertRaisesRegex(LabError,"LEDGER_UNAVAILABLE"):self.live()


if __name__=="__main__":unittest.main()
