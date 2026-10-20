"""RPF-58 full synthetic sessions, shared physical WAL and semantic rehash controls."""
import copy,hashlib,json,os,subprocess,sys,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_shared_contracts as c,pge_shared_core as core,pge_shared_verify as v
from runtime.runproof_runtime.effectwitness import pge_order_port as order,pge_config_port as config,pge_shared_feedback as feedback
from runtime.tests.test_effectwitness_config_experiment import synthetic_scene
WORK=c.WORK/"tests"

def make_plan():return c.plan("rpf58-session-"+uuid.uuid4().hex[:16],["rpf58-order-"+"1"*16,"rpf58-config-"+"2"*16],(45001,46001),c.sources())
def fake_order(contract,ledger):
    x,f=contract["experiment"],contract["effect"];timeline=[]
    def mark(kind,**data):
        e=ledger.event("ORDER_PORT_EVENT",port_kind=kind,**data);timeline.append({"kind":kind,"monotonic_ns":e["monotonic_ns"],"data":data})
    before={"reader_id":order.READER_ID,"reader_version":"1","source_id":f["authority_id"],"environment":{
        "owner":"rpf-58","run_id":x["run_id"],"environment_id":x["environment_id"],"environment_revision":order.ENV_REVISION,"reset_generation":0},
        "order":{"order_id":f["order_id"],"paid_minor":2500,"refunded_minor":0,"currency":"CNY","status":"PAID","revision":0},"receipts":[]}
    after=copy.deepcopy(before);after["order"].update(refunded_minor=2500,status="REFUNDED",revision=1)
    receipt={"operation_id":f["operation_id"],"order_id":f["order_id"],"amount_minor":2500,"currency":"CNY",
        "status":"COMMITTED","committed_revision":1,"receipt_id":"receipt-"+c.digest({"environment":x["environment_id"],"operation_id":f["operation_id"]})[:24]}
    after["receipts"]=[receipt]
    mark("PORT_ENTERED",run_id=x["run_id"]);mark("AUTHORITY_BEFORE",sha256=c.digest(before))
    res=ledger.reserve(c.DOMAINS[0],"refund_order",{"sqlite_mutation":1});ledger.settle(res,{"receipt_id":receipt["receipt_id"],"status":"COMMITTED"})
    mark("REFUND_COMMITTED",operation_id=f["operation_id"],receipt_id=receipt["receipt_id"]);mark("AUTHORITY_AFTER",sha256=c.digest(after))
    cleanup={"connections_closed":True,"exclusive_lock_probe":True,"database_retained_for_evidence":True};mark("CLEANUP_CONFIRMED",**cleanup)
    return {"schema":"rpf58-order-trial-v1","domain":c.DOMAINS[0],"source_kind":"SYNTHETIC_TEST_ONLY","executor_pid":0,
        "before":{"data":before,"sha256":c.digest(before)},"after":{"data":after,"sha256":c.digest(after)},
        "inspect":{"order_id":f["order_id"],"status":"PAID","revision":0},"tool_call":{"name":"refund_order","arguments":{k:f[k] for k in ("order_id","operation_id","amount_minor")},
            "result":{"status":"COMMITTED","operation_id":f["operation_id"],"receipt_id":receipt["receipt_id"],"committed_revision":1}},
        "fault":{"planned":False,"triggered":False,"observed":False},"database_sha256":"0"*64,"timeline":timeline,"cleanup":cleanup}
def fake_config(contract,ledger):
    scene=synthetic_scene("planned-but-inhibited",1,c.sources());old=scene["contracts"];text=c.canonical(scene).decode()
    for k in ("app","env","key"):text=text.replace(old["effect"][k],contract["effect"][k])
    text=text.replace(old["experiment"]["run_id"],contract["experiment"]["run_id"])
    scene=c.strict_json(text.encode());scene["contracts"]=contract;scene["contracts_sha256"]=c.digest(contract)
    for o in scene["http"]:o["response_body_sha256"]=c.digest(o["response"])
    def reserve(label,units,detail):
        r=ledger.reserve(c.DOMAINS[1],label,units);ledger.settle(r,detail)
    reserve("java",{"jvm":1},{"pid":scene["environment"]["java_pid"]})
    for i in range(3):reserve(f"health:{i}",{"health":1},{"health_sha256":"0"*64} if i==0 else {"status":"UNUSED_RESERVED_NO_IO"})
    reserve("sdk",{"sdk":1},{"pid":scene["sdk"]["popen_pid"],"report_sha256":c.digest(scene["sdk"]["report"])})
    for o in scene["http"]:reserve("http:"+o["kind"],{"business_http":1,**({"post":1} if o["method"]=="POST" else {})},{"http_seq":o["seq"],"observation_sha256":c.digest(o)})
    for e in scene["events"]:ledger.event("CONFIG_TOOL_EVENT",event=e)
    return {"schema":"rpf58-config-trial-v1","domain":c.DOMAINS[1],"source_kind":"SYNTHETIC_TEST_ONLY","executor_pid":0,"scene":scene}
def synthetic_payload():
    WORK.mkdir(parents=True,exist_ok=True);plan=make_plan();ledger=core.Ledger(WORK/("synthetic-"+uuid.uuid4().hex),plan,create=True);session=core.SharedSession(ledger)
    with patch.object(order,"execute",fake_order),patch.object(config,"execute",fake_config):
        for t in plan["trials"]:session.execute_trial(t)
    state=ledger.read()
    return {"source_kind":"SYNTHETIC_TEST_ONLY","plan":plan,"rows":session.rows,"ledger":state,"ledger_chain_sha256":c.digest(ledger.chain),
        "boundaries":c.BOUNDARIES,"claim":"SYNTHETIC_TEST_ONLY"}

def mutations():
    def bad_order(p):
        e=p["rows"][0]["evidence"];e["after"]["data"]["order"]["status"]="PAID";e["after"]["sha256"]=c.digest(e["after"]["data"])
    return {"domain_swap":lambda p:p["rows"].reverse(),
        "authority_swap":lambda p:p["rows"][0]["evidence"]["before"]["data"].update(reader_id="SAME_SERVICE_READ_ONLY_HTTP"),
        "source":lambda p:p["plan"]["source_files"].update({c.NEW_FILES[0]:"0"*64}),
        "budget_split":lambda p:p["ledger"].update(plan_sha256="0"*64),
        "false_effect":bad_order,
        "duplicate_write":lambda p:p["rows"][1]["evidence"]["scene"]["http"].append(copy.deepcopy(p["rows"][1]["evidence"]["scene"]["http"][4])),
        "fault_overclaim":lambda p:p["rows"][1]["evidence"]["scene"]["fault"].update(triggered=True,observed=True),
        "cleanup":lambda p:p["rows"][1]["evidence"]["scene"]["environment"]["cleanup"].update(java_exited=False),
        "cross_domain_fact_splice":lambda p:p["rows"][1]["feedback"].update(verified_fact_ids=p["rows"][0]["feedback"]["verified_fact_ids"]),
        "schema_downgrade":lambda p:p["plan"].update(schema="rpf57-config-pge-session-v1"),
        "future_feedback":lambda p:p["rows"][0]["input"].update(prior_feedback_sha256=["0"*64]),
        "empty_authority":lambda p:p["rows"][1]["evidence"]["scene"]["http"].pop(),
        "time_reverse":lambda p:p["ledger"]["events"].reverse(),
        "mixed_source":lambda p:p["rows"][1]["evidence"].update(source_kind="REAL_LOCAL_SDK_FIXTURE_JAVA_HTTP"),
        "provider":lambda p:p["ledger"]["reservations"][0]["units"].update(provider=1)}
def controls(raw,folder):
    folder.mkdir(parents=True,exist_ok=False);path=folder/"valid.json";path.write_bytes(raw)
    def cli(path,sha):
        args=[sys.executable,"-B","-m","runtime.runproof_runtime.effectwitness.pge_shared_verify",str(path)]
        if sha is not None:args += ["--sha256",sha]
        env={k:os.environ[k] for k in ("SYSTEMROOT","WINDIR","PATH") if k in os.environ}
        p=subprocess.run(args,cwd=c.ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        return p.returncode
    codes=[cli(path,hashlib.sha256(raw).hexdigest()),cli(path,None),cli(path,"0"*64)];c.require(codes==[0,2,3],"CLI_CODES")
    result={}
    for name,mutate in mutations().items():
        payload=copy.deepcopy(c.strict_json(raw)["payload"]);mutate(payload);bad=c.canonical(v.seal(payload));target=folder/(name+".json");target.write_bytes(bad)
        result[name]=cli(target,hashlib.sha256(bad).hexdigest())
    c.require(all(code==3 for code in result.values()),"SEMANTIC_TAMPER_ACCEPTED")
    return {"correct_missing_wrong":codes,"rehashed_semantic_tamper":result}

class SharedTests(unittest.TestCase):
    def test_two_domains_same_real_core_entry_and_complete_envelope(self):
        p=synthetic_payload();v.verify_payload(p)
        self.assertEqual([e["data"]["entry"] for e in p["ledger"]["events"] if e["kind"]=="SHARED_PORT_DISPATCH"],["SharedSession.execute_trial"]*2)
    def test_all_rehashed_semantic_predicates(self):
        p=synthetic_payload()
        for name,mutate in mutations().items():
            with self.subTest(control=name):
                q=copy.deepcopy(p);mutate(q);self.assertNotEqual(c.canonical(q),c.canonical(p));raw=c.canonical(v.seal(q))
                with self.assertRaises((ValueError,KeyError,IndexError)):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    def test_repeat_has_no_new_fact_but_authority_namespaces_stay_separate(self):
        p=synthetic_payload();a=p["rows"][0];f=feedback.project(a["contract"],a["evidence"],[a["feedback"]]);self.assertEqual(f["new_fact_ids"],[])
        self.assertTrue(set(a["feedback"]["verified_fact_ids"]).isdisjoint(p["rows"][1]["feedback"]["verified_fact_ids"]))
    def test_invalid_missing_authority_never_emits_facts(self):
        p=synthetic_payload();row=p["rows"][0];row["evidence"]["after"]["data"]["receipts"]=[]
        with self.assertRaises(ValueError):feedback.project(row["contract"],row["evidence"],[])
    def ledger(self):
        WORK.mkdir(parents=True,exist_ok=True);return core.Ledger(WORK/("budget-"+uuid.uuid4().hex),make_plan(),create=True)
    def test_unknown_write_and_restart_prevent_new_domain(self):
        t=self.ledger();t.reserve(c.DOMAINS[0],"trial",{"trial":1,"order_trial":1});t.reserve(c.DOMAINS[0],"refund_order",{"sqlite_mutation":1})
        again=core.Ledger(t.path,t.plan)
        with self.assertRaisesRegex(ValueError,"UNKNOWN_WRITE_STOP"):again.reserve(c.DOMAINS[0],"retry",{"sqlite_mutation":1})
        with self.assertRaises(ValueError):again.reserve(c.DOMAINS[1],"trial",{"trial":1,"config_trial":1})
    def test_double_write_torn_record_lock_and_budget(self):
        t=self.ledger();t.reserve(c.DOMAINS[0],"trial",{"trial":1,"order_trial":1});r=t.reserve(c.DOMAINS[0],"refund_order",{"sqlite_mutation":1});t.settle(r,{})
        with self.assertRaises(ValueError):t.reserve(c.DOMAINS[0],"refund_order",{"sqlite_mutation":1})
        (t.path/"mutation.lock").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError,"COLLISION"):t.event("BLOCKED")
        (t.path/"snapshot-0000.json").write_bytes(b"{")
        with self.assertRaises(ValueError):core.Ledger(t.path,t.plan)
    def test_strict_ports_paths_domains_and_no_provider(self):
        for d in ("ops","arbitrary", "https://example.com", "subprocess"):
            with self.assertRaises(ValueError):core.domain_port(d)
        with self.assertRaises(ValueError):c.scoped(c.ROOT/".local/rpf-57/NEVER_ACCESSED")
        p=make_plan();p["trials"][0]["execution"]["exe"]="anything"
        with self.assertRaises(ValueError):c.validate_plan(p)
        t=self.ledger()
        with self.assertRaises(ValueError):t.reserve(c.DOMAINS[0],"trial",{"trial":1,"order_trial":1,"provider":1})
    def test_synthetic_promotion_and_old_witness_rejected(self):
        p=synthetic_payload();p.update(source_kind="BOTH_REAL_CONTROLLED",claim=v.CLAIM)
        with self.assertRaises(ValueError):v.verify_payload(p)
        raw=(c.ROOT/"spikes/rpf-57/config-pge-coverage-evidence.json").read_bytes()
        with self.assertRaises(ValueError):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    def test_config_oracle_copy_is_identical_and_fixture_cannot_call_provider(self):
        import inspect
        from runtime.runproof_runtime.effectwitness.config_experiment_verify import verify_scene
        self.assertEqual(inspect.getsource(config._verify_scene).replace('def _verify_scene(','def verify_scene('),inspect.getsource(verify_scene))
        c1=make_plan()["trials"][1];journal=config.MemoryJournal(None,c1["experiment"]["run_id"])
        host=config.Host(c1,config.ProviderLedger.fixture_only(journal.run_id),config.ConfigLiveMemoryBackend(),journal)
        with self.assertRaises(ValueError):host._provider_request({})
    def test_cold_closeout_uses_frozen_port_and_saves_capture_before_checks(self):
        root=WORK/("cold-export-"+uuid.uuid4().hex);(root/"preflight").mkdir(parents=True)
        contract=make_plan()["trials"][1]
        def fake_sdk(host,*a,**kw):
            host.tool_trace=[{"returned_in_request":i} for i in (2,3,4)]
            host.journal.add("FAULT_INHIBITED",reason="PRE_REGISTERED_GATE_DISABLED")
            # The host was closed, so its live port property is unavailable.
            return {"report":{"status":"COMPLETED"},"returncode":0,"stderr_bytes":0,"ready":{"pid":123},"popen_pid":123}
        with patch.object(config,"WORK",root),patch.object(config,"run_sdk",side_effect=fake_sdk),patch.object(config.old,"_port_closed",return_value=True) as closed:
            result=config.cold_fixture(contract,{})
            self.assertEqual(result["status"],"PASS");closed.assert_called_once_with(contract["execution"]["agent_host"]["port"])
        self.assertTrue((root/"preflight/cold-fixture/capture.json").exists())
        root2=WORK/("cold-error-capture-"+uuid.uuid4().hex);(root2/"preflight").mkdir(parents=True)
        with patch.object(config,"WORK",root2),patch.object(config,"run_sdk",side_effect=fake_sdk),patch.object(config.old,"_port_closed",return_value=False):
            with self.assertRaisesRegex(ValueError,"COLD_FIXTURE"):config.cold_fixture(contract,{})
        self.assertTrue((root2/"preflight/cold-fixture/capture.json").exists())
    def test_competing_processes_only_one_shared_trial(self):
        t=self.ledger();code='''import sys,json
from pathlib import Path
from runtime.runproof_runtime.effectwitness.pge_shared_core import Ledger
p=json.loads(sys.stdin.read());t=Ledger(Path(p['path']),p['plan'])
try:t.reserve('order-refund','trial',{'trial':1,'order_trial':1});print('RESERVED')
except Exception:print('REJECTED')
'''
        env={k:os.environ[k] for k in ("SYSTEMROOT","WINDIR","PATH") if k in os.environ}
        children=[subprocess.Popen([sys.executable,"-B","-c",code],cwd=c.ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        out=[p.communicate(json.dumps({"path":str(t.path),"plan":t.plan}).encode(),timeout=30) for p in children]
        self.assertTrue(all(not e for o,e in out));self.assertEqual(sum(b"RESERVED" in o for o,e in out),1)
if __name__=="__main__":unittest.main()
