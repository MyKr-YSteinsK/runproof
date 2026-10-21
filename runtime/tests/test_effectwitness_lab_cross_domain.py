"""RPF-58 full synthetic sessions, shared physical WAL and semantic rehash controls."""
import copy,hashlib,json,os,subprocess,sys,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import lab_cross_domain_contracts as c,lab_cross_domain as core,lab_cross_domain_verify as v
from runtime.runproof_runtime.effectwitness import lab_cross_domain as config,lab_cross_domain_contracts as feedback
order=config.ORDER_PORT
from runtime.tests.test_effectwitness_config_experiment import synthetic_scene
WORK=c.WORK/"tests"

from runtime.runproof_runtime.effectwitness import lab_cross_domain_contracts as explorer

def make_plan():
    slots=[("rpf60-order-"+uuid.uuid4().hex[:16],"rpf60-config-"+uuid.uuid4().hex[:16],45001+i*2,45002+i*2) for i in range(2)]
    return c.plan("rpf60-session-"+uuid.uuid4().hex[:16],slots,c.sources())
def config_contract():return make_plan()["rounds"][0]["candidates"][c.CANDIDATES[1]]

def fake_order(contract,ledger):
    x,f=contract["experiment"],contract["effect"];timeline=[]
    def mark(kind,**data):
        e=ledger.event("ORDER_PORT_EVENT",port_kind=kind,**data);timeline.append({"kind":kind,"monotonic_ns":e["monotonic_ns"],"data":data})
    before={"reader_id":order.READER_ID,"reader_version":"1","source_id":f["authority_id"],"environment":{
        "owner":"rpf-60","run_id":x["run_id"],"environment_id":x["environment_id"],"environment_revision":order.ENV_REVISION,"reset_generation":0},
        "order":{"order_id":f["order_id"],"paid_minor":2500,"refunded_minor":0,"currency":"CNY","status":"PAID","revision":0},"receipts":[]}
    after=copy.deepcopy(before);after["order"].update(refunded_minor=2500,status="REFUNDED",revision=1)
    receipt={"operation_id":f["operation_id"],"order_id":f["order_id"],"amount_minor":2500,"currency":"CNY",
        "status":"COMMITTED","committed_revision":1,"receipt_id":"receipt-"+c.digest({"environment":x["environment_id"],"operation_id":f["operation_id"]})[:24]}
    after["receipts"]=[receipt]
    mark("PORT_ENTERED",run_id=x["run_id"]);mark("AUTHORITY_BEFORE",sha256=c.digest(before))
    res=ledger.reserve(c.DOMAINS[0],"refund_order",{"sqlite_mutation":1});ledger.settle(res,{"receipt_id":receipt["receipt_id"],"status":"COMMITTED"})
    mark("REFUND_COMMITTED",operation_id=f["operation_id"],receipt_id=receipt["receipt_id"]);mark("AUTHORITY_AFTER",sha256=c.digest(after))
    cleanup={"connections_closed":True,"exclusive_lock_probe":True,"database_retained_for_evidence":True};mark("CLEANUP_CONFIRMED",**cleanup)
    return {"schema":"rpf60-order-trial-v1","domain":c.DOMAINS[0],"source_kind":"SYNTHETIC_TEST_ONLY","executor_pid":0,
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
    return {"schema":"rpf60-config-trial-v1","domain":c.DOMAINS[1],"source_kind":"SYNTHETIC_TEST_ONLY","executor_pid":0,"scene":scene}
def synthetic_cold(contract):
    scene=synthetic_scene("planned-but-inhibited",1,c.sources())
    events=copy.deepcopy(scene["events"])
    for e in events:e["run_id"]=contract["experiment"]["run_id"]
    sdk=copy.deepcopy(scene["sdk"]);sdk.pop("identity")
    return {"schema":"rpf60-cold-capture-v1","source_kind":"SYNTHETIC_TEST_ONLY","attempt":1,"source_files":c.sources(),"contract":contract,
        "sdk":sdk,"events":events,"tool_trace":scene["tool_trace"],"completions":scene["completions"],
        "cleanup":{"sdk_exited":True,"host_thread_stopped":True,"host_port_closed":True}}

def fake_response(candidate,index):
    call={"id":"call-synthetic-"+str(index),"type":"function","function":{"name":"select_experiment","arguments":c.canonical({"candidate_id":candidate}).decode()}}
    return {"id":"synthetic-response-"+str(index),"model":c.MODEL,"usage":{"prompt_tokens":100,"completion_tokens":20,"total_tokens":120},
        "choices":[{"finish_reason":"tool_calls","message":{"role":"assistant","content":None,"tool_calls":[call]}}]}

def synthetic_payload(sequence=(0,1)):
    WORK.mkdir(parents=True,exist_ok=True);plan=make_plan();ledger=core.Ledger(WORK/("synthetic-"+uuid.uuid4().hex),plan,create=True);session=core.SharedSession(ledger)
    with patch.object(order,"execute",fake_order),patch.object(config.CONFIG_PORT,"execute",fake_config):
        for index,candidate_index in enumerate(sequence,1):
            body=explorer.body_for(explorer.messages_for(session.rows));attempt=ledger.reserve_request("EXPLORER",index,body)
            data=fake_response(c.CANDIDATES[candidate_index],index)
            observation={"shape":explorer.safe_response_shape(data),"attempt":attempt,"request_sha256":c.digest(body),"http_status":200,"received_monotonic_ns":time.monotonic_ns()}
            ledger.received(attempt,data);call=explorer.parse_selection(data,{r["selection"]["id"] for r in session.rows})
            session.execute_trial(call,body,observation,attempt)
    cold=synthetic_cold(plan["rounds"][0]["candidates"][c.CANDIDATES[1]]);task=core.TaskGuard(WORK/("intents-"+uuid.uuid4().hex));source=c.digest(c.sources())
    n=task.reserve("METADATA",source);task.result(n,"PASS",identity_sha256="0"*64)
    n=task.reserve("COLD",source,offline_gate_sha256=source);task.result(n,"PASS",capture_sha256=c.digest(cold))
    n=task.reserve("SESSION",source,plan_sha256=c.digest(plan),cold_capture_sha256=c.digest(cold));task.result(n,"PASS",ledger_chain_sha256=c.digest(ledger.chain),rows_sha256=c.digest(session.rows))
    return {"source_kind":"SYNTHETIC_TEST_ONLY","claim":"SYNTHETIC_TEST_ONLY","plan":plan,"rows":session.rows,"ledger_chain":ledger.chain,"cold_fixture":cold,
        "task_intents":task.read(),"boundaries":c.BOUNDARIES,"research":v.research(session.rows)}

def mutations():
    def bad_effect(p):
        e=p['rows'][0]['evidence']
        if 'after' in e:e['after']['data']['order']['status']='PAID'
        else:e['scene']['http'][-2]['response']['data']=[]
    def cleanup(p):
        e=p['rows'][0]['evidence']
        if 'cleanup' in e:e['cleanup']['connections_closed']=False
        else:e['scene']['environment']['cleanup']['java_exited']=False
    def authority(p):
        e=p['rows'][0]['evidence']
        if 'before' in e:e['before']['data']['reader_id']='SAME_SERVICE_READ_ONLY_HTTP'
        else:e['scene']['environment']['authority']='SQLITE_READ_ONLY_RECEIPT_READER'
    return {
        'false_effect':bad_effect,'cleanup':cleanup,'wrong_authority':authority,
        'future_feedback':lambda p:p['rows'][0]['input'].update(prior_feedback_sha256=['0'*64]),
        'missing_tool':lambda p:p['rows'][0]['observation']['shape']['choices'][0].update(tool_calls_count=0),
        'multiple_tools':lambda p:p['rows'][0]['observation']['shape']['choices'][0].update(tool_calls_count=2),
        'illegal_tool':lambda p:p['rows'][0]['selection']['function'].update(name='run_command'),
        'illegal_candidate':lambda p:p['rows'][0]['selection']['function'].update(arguments='{"candidate_id":"../../shell"}'),
        'tool_call_id':lambda p:p['rows'][0]['selection'].update(id='forged-call'),
        'duplicate_call_id':lambda p:p['rows'][1]['selection'].update(id=p['rows'][0]['selection']['id']),
        'wrong_slot':lambda p:p['rows'][1].update(contract=p['rows'][0]['contract']),
        'unknown_usage':lambda p:p['rows'][0]['observation']['shape']['usage'].update(total_tokens=None),
        'feedback_fact_splice':lambda p:p['rows'][1]['feedback'].update(verified_fact_ids=['forged:fact']),
        'mixed_source':lambda p:p['rows'][0]['evidence'].update(source_kind=('SYNTHETIC_TEST_ONLY' if p['rows'][0]['evidence']['source_kind']!='SYNTHETIC_TEST_ONLY' else 'REAL_LOCAL_SQLITE_DETERMINISTIC')),
        'old_owner':lambda p:p['rows'][0]['contract']['experiment'].update(owner='rpf-58-rev2'),
        'source':lambda p:p['plan']['source_files'].update({c.NEW_FILES[0]:'0'*64}),
        'cold_source':lambda p:p['cold_fixture']['source_files'].update({c.NEW_FILES[0]:'0'*64}),
        'cold_failed':lambda p:p['cold_fixture']['sdk']['report'].update(status='SDK_ERROR'),
        'runtime_callable':lambda p:next(e for e in p['ledger_chain'][-1]['state']['events'] if e['kind']=='SHARED_PORT_DISPATCH')['data']['runtime_identity'].update(port_callable='wrong.execute'),
        'budget_extra':lambda p:p['ledger_chain'][-1]['state']['reservations'][0]['units'].update(provider=3),
        'usage_reset':lambda p:p['ledger_chain'][-1]['state']['reservations'][0].update(status='RESERVED',detail=None),
        'duplicate_write':lambda p:p['ledger_chain'][-1]['state']['reservations'].append(copy.deepcopy(p['ledger_chain'][-1]['state']['reservations'][-1])),
        'time_reverse':lambda p:p['ledger_chain'][-1]['state']['events'].reverse(),
        'research_overclaim':lambda p:p['research'].update(H1='PROVEN'),
        'schema_downgrade':lambda p:p['plan'].update(schema='rpf58-shared-session-v2')}

def rehash(p):
    for row in p['rows']:
        e=row['evidence']
        for name in ('before','after'):
            if name in e:e[name]['sha256']=c.digest(e[name]['data'])
        if 'scene' in e:
            scene=e['scene'];scene['contracts_sha256']=c.digest(scene['contracts'])
            for o in scene['http']:o['response_body_sha256']=c.digest(o['response'])
    prev=None
    for frame in p['ledger_chain']:
        frame['previous_sha256']=prev;frame['state_sha256']=c.digest(frame['state']);prev=c.digest(frame)
    prev=None
    for frame in p['task_intents']:
        r=frame['record']
        if r['action']=='RESULT':
            reserve=p['task_intents'][r['reservation_id']-1]['record']
            if reserve['kind']=='COLD' and r['status']=='PASS':r['detail']={'capture_sha256':c.digest(p['cold_fixture'])}
            if reserve['kind']=='SESSION' and r['status']=='PASS':r['detail']={'ledger_chain_sha256':c.digest(p['ledger_chain']),'rows_sha256':c.digest(p['rows'])}
        frame['previous_sha256']=prev;frame['record_sha256']=c.digest(r);prev=c.digest(frame)

def controls(raw,folder):
    folder.mkdir(parents=True,exist_ok=False);path=folder/'valid.json';path.write_bytes(raw)
    def cli(path,anchor):
        args=[sys.executable,'-B','-m','runtime.runproof_runtime.effectwitness.lab_cross_domain_verify',str(path)]
        if anchor is not None:args+=['--sha256',anchor]
        env={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH') if k in os.environ}
        return subprocess.run(args,cwd=c.ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40).returncode
    codes=[cli(path,hashlib.sha256(raw).hexdigest()),cli(path,None),cli(path,'0'*64)];c.require(codes==[0,2,3],'CLI_CODES')
    results={}
    for name,mutate in mutations().items():
        p=c.strict_json(raw)['payload'];original=c.canonical(p);mutate(p);c.require(c.canonical(p)!=original,'NOOP_'+name);rehash(p)
        bad=c.canonical(v.seal(p));target=folder/(name+'.json');target.write_bytes(bad)
        results[name]=cli(target,hashlib.sha256(bad).hexdigest())
    c.require(all(code==3 for code in results.values()),'SEMANTIC_TAMPER_ACCEPTED')
    return {'correct_missing_wrong':codes,'rehashed_semantic_tamper':results}

class SelectTests(unittest.TestCase):
    def test_competing_processes_share_provider_reservation(self):
        plan=make_plan();t=core.Ledger(WORK/('race-'+uuid.uuid4().hex),plan,create=True)
        code='''import sys,json
from pathlib import Path
from runtime.runproof_runtime.effectwitness import lab_cross_domain as s,lab_cross_domain_contracts as e
d=json.loads(sys.stdin.read())
try:
 t=s.Ledger(Path(d['path']),d['plan']);t.reserve_request('EXPLORER',1,e.body_for(e.messages_for([])));print('RESERVED')
except Exception:print('REJECTED')
'''
        env={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH') if k in os.environ}
        children=[subprocess.Popen([sys.executable,'-B','-c',code],cwd=c.ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        results=[child.communicate(c.canonical({'path':str(t.path),'plan':plan}),timeout=30) for child in children]
        self.assertEqual(sum(out.strip()==b'RESERVED' for out,err in results),1)
        self.assertTrue(all(not err for out,err in results))
        t.read();self.assertEqual(len(t.state['reservations']),1);self.assertEqual(t.state['reservations'][0]['status'],'RESERVED')
    def test_deadline_source_namespace_and_no_extra_requests(self):
        plan=make_plan();t=core.Ledger(WORK/('stops-'+uuid.uuid4().hex),plan,create=True)
        with patch.object(core.time,'monotonic_ns',return_value=t.state['started_ns']+2401*10**9):
            with self.assertRaisesRegex(ValueError,'DEADLINE'):t.event('EXPIRED')
        with patch.object(core,'sources',return_value={}):
            with self.assertRaisesRegex(ValueError,'SOURCE'):t.event('DRIFT')
        body=explorer.body_for(explorer.messages_for([]));n=t.reserve_request('EXPLORER',1,body)
        data=fake_response(c.CANDIDATES[0],1);data['usage']['total_tokens']=None
        with self.assertRaises((ValueError,TypeError)):t.received(n,data)
        self.assertEqual(t.read()['reservations'][0]['status'],'RESERVED')
        with self.assertRaises(ValueError):t.reserve_request('EXPLORER',1,body)
        plan['rounds'][1]=copy.deepcopy(plan['rounds'][0])
        with self.assertRaises(ValueError):c.validate_plan(plan)
    def test_no_free_text_in_safe_projection(self):
        d=fake_response(c.CANDIDATES[0],1);d['choices'][0]['message'].update(content='PRIVATE_TEXT_MARKER',reasoning_content='PRIVATE_REASON_MARKER')
        shape=explorer.safe_response_shape(d);explorer.validate_response_shape(shape)
        self.assertNotIn('PRIVATE_TEXT_MARKER',c.canonical(shape).decode());self.assertNotIn('PRIVATE_REASON_MARKER',c.canonical(shape).decode())
    def test_rehashed_semantic_controls_all_sequences(self):
        for seq in ((0,0),(0,1),(1,0),(1,1)):
            original=synthetic_payload(seq)
            for name,mutate in mutations().items():
                with self.subTest(sequence=seq,control=name):
                    p=copy.deepcopy(original);mutate(p);self.assertNotEqual(c.canonical(p),c.canonical(original));rehash(p)
                    with self.assertRaises((ValueError,KeyError,IndexError,TypeError)):v.verify_payload(p)
    def test_unknown_write_lock_torn_restart_and_no_refund(self):
        p=make_plan();t=core.Ledger(WORK/('budget-'+uuid.uuid4().hex),p,create=True)
        body=explorer.body_for(explorer.messages_for([]));n=t.reserve_request('EXPLORER',1,body)
        again=core.Ledger(t.path,p)
        with self.assertRaises(ValueError):again.reserve_request('EXPLORER',1,body)
        t.received(n,fake_response(c.CANDIDATES[0],1));account=core.RoundAccount(t,1)
        account.reserve(c.DOMAINS[0],'trial',{'trial':1,'order_trial':1});account.reserve(c.DOMAINS[0],'refund_order',{'sqlite_mutation':1})
        with self.assertRaises(ValueError):account.reserve(c.DOMAINS[0],'retry',{'sqlite_mutation':1})
        (t.path/'mutation.lock').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'COLLISION'):t.event('LOCKED')
        (t.path/'mutation.lock').unlink();(t.path/'snapshot-0000.json').write_bytes(b'{')
        with self.assertRaises(ValueError):t.read()
    def test_provider_shape_failure_modes(self):
        for mode in ('empty','multi','badname','candidate','id','usage'):
            d=fake_response(c.CANDIDATES[0],1)
            if mode=='empty':d['choices'][0]['message']['tool_calls']=[]
            elif mode=='multi':d['choices'][0]['message']['tool_calls']*=2
            elif mode=='badname':d['choices'][0]['message']['tool_calls'][0]['function']['name']='shell'
            elif mode=='candidate':d['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{"candidate_id":"bad"}'
            elif mode=='id':d['choices'][0]['message']['tool_calls'][0]['id']='../../bad'
            elif mode=='usage':d['usage']['total_tokens']=None
            with self.subTest(mode=mode),self.assertRaises((ValueError,TypeError)):explorer.parse_selection(d,set())
    def test_old_certificate_and_synthetic_upgrade_rejected(self):
        p=synthetic_payload();p.update(source_kind=v.REAL,claim=v.CLAIM)
        with self.assertRaises(ValueError):v.verify_payload(p)
        raw=(c.ROOT/'spikes/rpf-58/rev-2/cross-domain-portability-evidence.json').read_bytes()
        with self.assertRaises(ValueError):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    def test_oracle_copy_and_fixture_no_provider(self):
        import inspect
        from runtime.runproof_runtime.effectwitness.config_experiment_verify import verify_scene
        self.assertEqual(inspect.getsource(config._verify_scene).replace('def _verify_scene(','def verify_scene('),inspect.getsource(verify_scene).replace('CANDIDATES','CONFIG_CANDIDATES'))
        contract=config_contract();journal=config.MemoryJournal(None,contract['experiment']['run_id'])
        host=config.Host(contract,config.ProviderLedger.fixture_only(journal.run_id),config.ConfigLiveMemoryBackend(),journal)
        with self.assertRaises(ValueError):host._provider_request({})
    def test_four_sequences(self):
        for seq in ((0,0),(0,1),(1,0),(1,1)):
            with self.subTest(sequence=seq):
                p=synthetic_payload(seq);result=v.verify_payload(p)
                self.assertEqual(result["research"]["domain_changed"],seq[0]!=seq[1])
                if seq[0]==seq[1]:self.assertEqual(p["rows"][1]["feedback"]["new_fact_ids"],[])

