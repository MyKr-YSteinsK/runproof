"""RPF-58 full synthetic sessions, shared physical WAL and semantic rehash controls."""
import copy,hashlib,json,os,subprocess,sys,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_shared_contracts as c,pge_shared_core as core,pge_shared_verify as v
from runtime.runproof_runtime.effectwitness import pge_order_port as order,pge_config_port as config,pge_shared_feedback as feedback
from runtime.tests.test_effectwitness_config_experiment import synthetic_scene
WORK=c.WORK/"tests"

def make_plan():return c.plan("rpf58r2-session-"+uuid.uuid4().hex[:16],["rpf58r2-order-"+"1"*16,"rpf58r2-config-"+"2"*16],(45001,46001),c.sources())
def fake_order(contract,ledger):
    x,f=contract["experiment"],contract["effect"];timeline=[]
    def mark(kind,**data):
        e=ledger.event("ORDER_PORT_EVENT",port_kind=kind,**data);timeline.append({"kind":kind,"monotonic_ns":e["monotonic_ns"],"data":data})
    before={"reader_id":order.READER_ID,"reader_version":"1","source_id":f["authority_id"],"environment":{
        "owner":"rpf-58-rev2","run_id":x["run_id"],"environment_id":x["environment_id"],"environment_revision":order.ENV_REVISION,"reset_generation":0},
        "order":{"order_id":f["order_id"],"paid_minor":2500,"refunded_minor":0,"currency":"CNY","status":"PAID","revision":0},"receipts":[]}
    after=copy.deepcopy(before);after["order"].update(refunded_minor=2500,status="REFUNDED",revision=1)
    receipt={"operation_id":f["operation_id"],"order_id":f["order_id"],"amount_minor":2500,"currency":"CNY",
        "status":"COMMITTED","committed_revision":1,"receipt_id":"receipt-"+c.digest({"environment":x["environment_id"],"operation_id":f["operation_id"]})[:24]}
    after["receipts"]=[receipt]
    mark("PORT_ENTERED",run_id=x["run_id"]);mark("AUTHORITY_BEFORE",sha256=c.digest(before))
    res=ledger.reserve(c.DOMAINS[0],"refund_order",{"sqlite_mutation":1});ledger.settle(res,{"receipt_id":receipt["receipt_id"],"status":"COMMITTED"})
    mark("REFUND_COMMITTED",operation_id=f["operation_id"],receipt_id=receipt["receipt_id"]);mark("AUTHORITY_AFTER",sha256=c.digest(after))
    cleanup={"connections_closed":True,"exclusive_lock_probe":True,"database_retained_for_evidence":True};mark("CLEANUP_CONFIRMED",**cleanup)
    return {"schema":"rpf58r2-order-trial-v2","domain":c.DOMAINS[0],"source_kind":"SYNTHETIC_TEST_ONLY","executor_pid":0,
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
    return {"schema":"rpf58r2-config-trial-v2","domain":c.DOMAINS[1],"source_kind":"SYNTHETIC_TEST_ONLY","executor_pid":0,"scene":scene}
def synthetic_payload():
    WORK.mkdir(parents=True,exist_ok=True);plan=make_plan();ledger=core.Ledger(WORK/("synthetic-"+uuid.uuid4().hex),plan,create=True);session=core.SharedSession(ledger)
    with patch.object(order,"execute",fake_order),patch.object(config,"execute",fake_config):
        for t in plan["trials"]:session.execute_trial(t)
    state=ledger.read()
    cold=synthetic_cold(plan["trials"][1]);task=core.TaskGuard(WORK/("intents-"+uuid.uuid4().hex));source=c.digest(c.sources())
    n=task.reserve("METADATA",source);task.result(n,"PASS",identity_sha256="0"*64)
    n=task.reserve("COLD",source,offline_gate_sha256="0"*64);task.result(n,"PASS",capture_sha256=c.digest(cold))
    n=task.reserve("SESSION",source,plan_sha256=c.digest(plan),cold_capture_sha256=c.digest(cold));task.result(n,"PASS",ledger_sha256=c.digest(state),rows_sha256=c.digest(session.rows))
    return {"source_kind":"SYNTHETIC_TEST_ONLY","plan":plan,"rows":session.rows,"ledger":state,"ledger_chain_sha256":c.digest(ledger.chain),
        "boundaries":c.BOUNDARIES,"claim":"SYNTHETIC_TEST_ONLY","cold_fixture":cold,"task_intents":task.read()}

def synthetic_cold(contract):
    scene=synthetic_scene("planned-but-inhibited",1,c.sources())
    events=copy.deepcopy(scene["events"])
    for e in events:e["run_id"]=contract["experiment"]["run_id"]
    sdk=copy.deepcopy(scene["sdk"]);sdk.pop("identity")
    return {"schema":"rpf58-cold-capture-v2","source_kind":"SYNTHETIC_TEST_ONLY","attempt":1,"source_files":c.sources(),"contract":contract,
        "sdk":sdk,"events":events,"tool_trace":scene["tool_trace"],"completions":scene["completions"],
        "cleanup":{"sdk_exited":True,"host_thread_stopped":True,"host_port_closed":True}}

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
        "mixed_source":lambda p:p["rows"][1]["evidence"].update(source_kind=("SYNTHETIC_TEST_ONLY" if p["rows"][1]["evidence"]["source_kind"]!="SYNTHETIC_TEST_ONLY" else "REAL_LOCAL_SDK_FIXTURE_JAVA_HTTP")),
        "provider":lambda p:p["ledger"]["reservations"][0]["units"].update(provider=1),
        "cold_cross_source":lambda p:p["cold_fixture"]["source_files"].update({c.NEW_FILES[0]:"0"*64}),
        "old_failed_cold":lambda p:p["cold_fixture"]["sdk"]["report"].update(status="SDK_ERROR"),
        "cross_revision_order":lambda p:p["rows"][0]["contract"]["experiment"].update(owner="rpf-58"),
        "unused_health_forgery":lambda p:next(r for r in p["ledger"]["reservations"] if r["label"]=="health:2")["detail"].update(status="ACTUAL_GET"),
        "runtime_callable_splice":lambda p:next(e for e in p["ledger"]["events"] if e["kind"]=="SHARED_PORT_DISPATCH")["data"]["runtime_identity"].update(port_callable="wrong.execute")}

def reanchor_task_integrity(payload):
    """Rehash task wrappers so domain tamper reaches semantic predicates."""
    for row in payload["rows"]:
        evidence=row["evidence"]
        for name in ("before","after"):
            if name in evidence:evidence[name]["sha256"]=c.digest(evidence[name]["data"])
        if "scene" in evidence:
            scene=evidence["scene"];scene["contracts_sha256"]=c.digest(scene["contracts"])
            for observation in scene["http"]:observation["response_body_sha256"]=c.digest(observation["response"])
    previous=None
    for frame in payload["task_intents"]:
        record=frame["record"]
        if record["action"]=="RESULT":
            reservation=payload["task_intents"][record["reservation_id"]-1]["record"]
            if reservation["kind"]=="COLD" and record["status"]=="PASS":record["detail"]={"capture_sha256":c.digest(payload["cold_fixture"])}
            if reservation["kind"]=="SESSION" and record["status"]=="PASS":record["detail"]={"ledger_sha256":c.digest(payload["ledger"]),"rows_sha256":c.digest(payload["rows"])}
        frame["previous_sha256"]=previous;frame["record_sha256"]=c.digest(record);previous=c.digest(frame)
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
        original=c.strict_json(raw)["payload"];payload=copy.deepcopy(original);mutate(payload)
        c.require(c.canonical(payload)!=c.canonical(original),"TAMPER_NOOP_"+name)
        reanchor_task_integrity(payload);bad=c.canonical(v.seal(payload));target=folder/(name+".json");target.write_bytes(bad)
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
                q=copy.deepcopy(p);mutate(q);self.assertNotEqual(c.canonical(q),c.canonical(p));reanchor_task_integrity(q);raw=c.canonical(v.seal(q))
                with self.assertRaises((ValueError,KeyError,IndexError)):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    def test_repeat_has_no_new_fact_but_authority_namespaces_stay_separate(self):
        p=synthetic_payload();a=p["rows"][0];f=feedback.project(a["contract"],a["evidence"],[a["feedback"]]);self.assertEqual(f["new_fact_ids"],[])
        self.assertTrue(set(a["feedback"]["verified_fact_ids"]).isdisjoint(p["rows"][1]["feedback"]["verified_fact_ids"]))
    def test_controls_change_both_synthetic_and_real_source_shapes(self):
        p=synthetic_payload()
        for source in ("SYNTHETIC_TEST_ONLY","BOTH_REAL_CONTROLLED"):
            original=copy.deepcopy(p);original["source_kind"]=source
            if source=="BOTH_REAL_CONTROLLED":original["rows"][1]["evidence"]["source_kind"]="REAL_LOCAL_SDK_FIXTURE_JAVA_HTTP"
            for name,mutate in mutations().items():
                q=copy.deepcopy(original);mutate(q)
                with self.subTest(source=source,control=name):self.assertNotEqual(c.canonical(q),c.canonical(original))
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
    def cold_mock(self,host,contract,sdk,folder,**kw):
        capture=synthetic_cold(contract)
        host.tool_trace=capture["tool_trace"];host.provider_responses=capture["completions"];host.journal.events=capture["events"]
        config.once(folder/"sdk-cleanup.json",{"source_files":c.sources(),"cleanup":capture["cleanup"]})
        return capture["sdk"]
    def test_cold_closed_host_capture_first_and_no_second_after_pass(self):
        root=WORK/("cold-"+uuid.uuid4().hex);(root/"preflight").mkdir(parents=True);contract=make_plan()["trials"][1]
        with patch.object(config,"WORK",root),patch.object(config,"run_sdk",side_effect=self.cold_mock):
            result=config.cold_fixture(contract,{})
            self.assertEqual(result["status"],"PASS")
            with self.assertRaises(ValueError):config.cold_fixture(contract,{})
        self.assertTrue((root/"preflight/cold-attempt-01/capture.json").exists())
    def test_cold_malformed_report_captured_failure_spent_no_same_source_retry(self):
        root=WORK/("cold-fail-"+uuid.uuid4().hex);(root/"preflight").mkdir(parents=True);contract=make_plan()["trials"][1]
        def bad(*a,**kw):
            sdk=self.cold_mock(*a,**kw);sdk["report"]={"status":"REPORT_UNAVAILABLE"};return sdk
        with patch.object(config,"WORK",root),patch.object(config,"run_sdk",side_effect=bad):
            with self.assertRaises((ValueError,KeyError)):config.cold_fixture(contract,{})
            with self.assertRaises(ValueError):config.cold_fixture(contract,{})
        folder=root/"preflight/cold-attempt-01"
        self.assertTrue((folder/"capture.json").exists());self.assertTrue((folder/"failure.json").exists());self.assertFalse((folder/"result.json").exists())
    def test_cold_cleanup_failure_keeps_capture(self):
        root=WORK/("cold-cleanup-"+uuid.uuid4().hex);(root/"preflight").mkdir(parents=True);contract=make_plan()["trials"][1]
        def bad(host,contract,sdk,folder,**kw):
            result=self.cold_mock(host,contract,sdk,folder,**kw)
            path=folder/"sdk-cleanup.json";value=json.loads(path.read_text());value["cleanup"]["host_port_closed"]=False
            path.write_bytes(c.canonical(value));return result
        with patch.object(config,"WORK",root),patch.object(config,"run_sdk",side_effect=bad):
            with self.assertRaises(ValueError):config.cold_fixture(contract,{})
        self.assertTrue((root/"preflight/cold-attempt-01/capture.json").exists())
    def test_capture_write_failure_never_passes_or_reuses_attempt(self):
        root=WORK/("cold-write-"+uuid.uuid4().hex);(root/"preflight").mkdir(parents=True);contract=make_plan()["trials"][1];original=config.once
        def fail(path,value):
            if path.name=="capture.json":raise OSError("SIMULATED_CAPTURE_FAILURE")
            original(path,value)
        with patch.object(config,"WORK",root),patch.object(config,"run_sdk",side_effect=self.cold_mock),patch.object(config,"once",side_effect=fail):
            with self.assertRaises(OSError):config.cold_fixture(contract,{})
        task=core.TaskGuard(root/"task-intents");task.read();self.assertEqual(task.rows[0]["status"],"FAIL")
        self.assertFalse((root/"preflight/cold-attempt-01/result.json").exists())
    def test_task_intent_retry_source_limits_torn_and_metadata(self):
        WORK.mkdir(parents=True,exist_ok=True);task=core.TaskGuard(WORK/("task-"+uuid.uuid4().hex))
        n=task.reserve("COLD","1"*64);task.result(n,"FAIL",error="IMPLEMENTATION_DEFECT")
        with self.assertRaises(ValueError):task.reserve("COLD","1"*64,offline_gate_sha256="x")
        n=task.reserve("COLD","2"*64,offline_gate_sha256="x");task.result(n,"PASS",capture_sha256="x")
        with self.assertRaises(ValueError):task.reserve("COLD","3"*64,offline_gate_sha256="x")
        for i in range(4):n=task.reserve("METADATA","2"*64);task.result(n,"PASS",identity_sha256="x")
        with self.assertRaises(ValueError):task.reserve("METADATA","2"*64)
        n=task.reserve("SESSION","2"*64)
        with self.assertRaises(ValueError):task.reserve("SESSION","2"*64)
        core.verify_task_records(task.read())
        (task.path/"intent-0001.json").write_bytes(b"{")
        with self.assertRaises(ValueError):task.read()
    def test_cross_version_and_source_gate_rejects(self):
        p=make_plan();p["schema"]="rpf58-shared-session-v1"
        with self.assertRaises(ValueError):c.validate_plan(p)
        cold=synthetic_cold(make_plan()["trials"][1]);cold["source_files"][c.NEW_FILES[0]]="0"*64
        with self.assertRaises(ValueError):config.validate_cold_capture(cold)
    def test_run_sdk_closes_real_host_and_persists_before_postcheck_no_sdk(self):
        for mode in ("success","malformed","capture-failure"):
            with self.subTest(mode=mode):
                folder=WORK/("lifecycle-"+uuid.uuid4().hex);folder.mkdir(parents=True)
                contract=c.trial(c.DOMAINS[1],"rpf58r2-config-"+uuid.uuid4().hex[:16],c.digest(c.sources()),config.old._free_port(),config.old._free_port())
                cold=synthetic_cold(contract);journal=config.MemoryJournal(None,contract["experiment"]["run_id"])
                host=config.Host(contract,config.ProviderLedger.fixture_only(journal.run_id),config.ConfigLiveMemoryBackend(),journal)
                class Process:
                    pid=cold["sdk"]["popen_pid"];returncode=0
                    def communicate(self,*a,**kw):
                        host.runtime=cold["sdk"]["ready"];host.tool_trace=cold["tool_trace"];host.provider_responses=cold["completions"];host.journal.events=cold["events"]
                        return (b"PRIVATE_MALFORMED_REPORT" if mode=="malformed" else c.canonical(cold["sdk"]["report"])),b""
                    def poll(self):return 0
                original=config.once
                def write(path,value):
                    if mode=="capture-failure" and path.name=="sdk-received.json":raise OSError("WRITE_FAILPOINT")
                    original(path,value)
                pin=c.pinned_sdk_fields()
                def closed(port):
                    import socket
                    with socket.socket() as sock:sock.settimeout(.5);return sock.connect_ex(("127.0.0.1",port))!=0
                with patch.object(config.h55,"resolve_direct_python",return_value=Path(sys.executable)),patch.object(config.subprocess,"Popen",return_value=Process()),patch.object(config,"once",side_effect=write),patch.object(config.old,"_port_closed",side_effect=closed):
                    if mode=="capture-failure":
                        with self.assertRaises(OSError):config.run_sdk(host,contract,pin,folder,fixture=True)
                    else:
                        result=config.run_sdk(host,contract,pin,folder,fixture=True)
                        self.assertEqual(result["report"]["status"],"REPORT_UNAVAILABLE" if mode=="malformed" else "COMPLETED")
                        self.assertTrue((folder/"sdk-received.json").exists())
                        self.assertNotIn("PRIVATE_MALFORMED_REPORT",(folder/"sdk-received.json").read_text())
                self.assertTrue(all(json.loads((folder/"sdk-cleanup.json").read_text())["cleanup"].values()))
                with self.assertRaises(Exception):_ = host.port
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
