"""RPF65 synthetic state machine and independently reanchored semantic attacks."""
import copy, hashlib, inspect, os, subprocess, sys, unittest, uuid
from pathlib import Path
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_r65_context as c, pge_r65_target_config as config, pge_r65_session as session, pge_r65_verify as v
from runtime.runproof_runtime.effectwitness.config_live_contracts import TOOL_ARGUMENT_KEYS

def registry():
    return [{'type':'function','function':{'name':n,'description':c.TOOL_HELP[n],'parameters':{'type':'object','properties':{k:{'type':'integer' if k=='expected_version' else 'string'} for k in TOOL_ARGUMENT_KEYS[n]},'required':list(TOOL_ARGUMENT_KEYS[n]),'additionalProperties':False},'strict':True}} for n in c.TOOLS]

def drive(host,ct,pid,*,cold=False):
    pin=c.pinned_sdk_fields(); ready=dict(framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=pid,python_executable_sha256=pin['python_executable_sha256'],sdk_source_sha256=c.SDK_CORE_SHA256,openai_source_sha256=pin['openai_core_sha256'],sdk_site_root_binding_sha256=pin['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=pin['python_runtime_mapping_sha256'])
    host._ready(ready); messages=[{'role':'system','content':ct['execution']['agent_instructions']},{'role':'user','content':ct['execution']['task_prompt']}]
    def response(body):
        data=host._fixture_response(body); data['id']=str(uuid.uuid4()); data['model']=c.MODEL; data['usage']=dict(prompt_tokens=500,completion_tokens=50,total_tokens=550); return data
    with patch.object(host,'_provider_request',response):
        for _ in range(5):
            data=host._completion(dict(model='rpf53-fixture-only' if cold else c.MODEL,messages=copy.deepcopy(messages),tools=registry(),tool_choice='auto',parallel_tool_calls=False,max_tokens=256))
            msg=data['choices'][0]['message']; messages.append(msg)
            for call in msg.get('tool_calls',[]):
                result=host._tool(dict(call_id=call['id'],name=call['function']['name'],arguments=c.strict_json(call['function']['arguments'].encode())))
                messages.append(dict(role='tool',tool_call_id=call['id'],content=c.canonical(result).decode()))
    r=dict(status='COMPLETED',framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=pid,python_executable_sha256=pin['python_executable_sha256'],sdk_source_sha256=c.SDK_CORE_SHA256,openai_source_sha256=pin['openai_core_sha256'],guard_denials=[],provider_key_present=False,business_key_present=False,final_text_persisted=False,tool_calls=4,tool_callbacks=4,requests=5,input_tokens=0 if cold else 2500,output_tokens=0 if cold else 250)
    return dict(popen_pid=pid,ready=ready,report=r,returncode=0,stderr_bytes=0)

class FakeHttp(config.Http):
 def request(self,kind,*,reconcile=False):
  method,path,body=config._http_contract(self.effect,kind);c.require(method!='POST' or not self.stop_writes,'WRITE_AFTER_UNKNOWN');kw={'domain':c.DOMAIN,'run_id':self.contracts['experiment']['run_id'],'http_seq':len(self.observations)+1,'operation':kind,'method':method};ticket=self.total.reserve('http',**kw);post=self.total.reserve('post',**kw) if method=='POST' else None;self.journal.add('HTTP_RESERVED',**{k:kw[k] for k in ('http_seq','operation','method')})
  def item(version):return {**{k:self.effect[k] for k in ('app','env','key')},'version':version,'value':'rpf53-v'+str(version),'description':None,'updatedAt':'2026-10-22T00:00:00Z'}
  def history(version):
   row=item(version);row['createdAt']=row.pop('updatedAt');row.update(action='UPSERT',operator=None,reason=None);return row
  absent=kind=='initial_current' or kind=='inspect_config' and len(self.observations)==2;data=[] if kind=='initial_history' else None if absent else [history(2),history(1)] if kind.endswith('history') else [item(2)] if kind=='final_list' else item(1 if kind=='create_config_v1' else 2);status=404 if absent else 200;response={'code':4041 if absent else 0,'message':'synthetic','data':data,'traceId':None};o={'seq':len(self.observations)+1,'kind':kind,'method':method,'path':path,'request':body,'status':status,'content_type':'application/json','response':response,'response_body_sha256':c.digest(response),'elapsed_ms':0,'transport_error':None};self.observations.append(o);self.total.settle(ticket,status=status,response_sha256=o['response_body_sha256'],transport_error=None)
  if post:self.total.settle(post,status=status,unknown=False)
  self.journal.add('HTTP_COMPLETED',http_seq=o['seq'],status=status,response_sha256=o['response_body_sha256']);return o

def fake_scene(self,ctx,ct,ledger):
    run=ct['experiment']['run_id']; j=config.Journal(ledger,run); client=FakeHttp(ctx,ct,'synthetic-only',j,ledger)
    jvm=ledger.reserve('jvm',domain=c.DOMAIN,run_id=run); ledger.settle(jvm,popen_pid=456,status='STARTED')
    h=ledger.reserve('health',domain=c.DOMAIN,run_id=run); ledger.settle(h,status=200,response_sha256=c.digest({'status':'UP'}))
    client.initial_state_valid(); broker=config.BrokerLedger(ledger,run); host=config.Host(ct,broker,config.ConfigLiveBusiness(ct,client),j,api_key='synthetic-only')
    sd=ledger.reserve('sdk',domain=c.DOMAIN,run_id=run); sdk=drive(host,ct,789); ledger.settle(sd,popen_pid=789,status='COMPLETED'); ledger.append('PROCESS_CLEANUP',resource='sdk',pid=789,process_exited=True)
    client.stop_writes=True; client.final_readback(reconcile=True); client.request('final_list'); ledger.append('PROCESS_CLEANUP',resource='jvm',pid=456,process_exited=True)
    env=dict(source_level='REAL_JAVA_H2_LOCAL_SIMULATION',authority='SAME_SERVICE_READ_ONLY_HTTP',jar_sha256=c.SOURCE_JAR_SHA256,jar_bytes=c.SOURCE_JAR_BYTES,java_pid=456,jar_command_verified=True,listener_owned=True,health=[dict(status=200,body={'status':'UP'},raw_body_sha256=c.digest({'status':'UP'}),transport_error=None)],cleanup=dict.fromkeys(('java_exited','java_port_closed','sdk_exited','host_port_closed','host_thread_stopped','local_key_released'),True))
    return dict(contracts=ct,requests=broker.data['requests'],tool_rejections=[],http=client.observations,events=j.events,tool_trace=host.tool_trace,completions=host.provider_responses,visibility=host.visible_contract_checks,sdk=sdk,environment=env,original_success=host.original_success,host_failure=None)

def synthetic_payload():
    ctx=c.make_context(uuid.uuid4().hex[:16],(45001,45002),(45003,45004),synthetic=True); ctx.root.mkdir(parents=True,exist_ok=False); ledger=c.Ledger(ctx,ctx.root/'account',create=True)
    m=ledger.reserve('metadata'); ledger.settle(m,status='PASS'); ct=ctx.public()['cold_contract']; j=config.Journal(ledger,ct['experiment']['run_id'])
    host=config.Host(ct,config.ProviderLedger.fixture_only(ct['experiment']['run_id']),config.ConfigLiveMemoryBackend(),j,fixture=True)
    t=ledger.reserve('cold',domain=c.DOMAIN,run_id=ct['experiment']['run_id']); sdk=drive(host,ct,123,cold=True); ledger.settle(t,popen_pid=123,status='COMPLETED'); ledger.append('PROCESS_CLEANUP',resource='cold',pid=123,process_exited=True)
    cold=dict(status='PASS',source_kind='FIXTURE_SCRIPTED',contract=ct,sources=c.sources(),sdk=sdk,tool_trace=host.tool_trace,completions=host.provider_responses,events=j.events,checks={'protocol':True,'provider_zero':True,'cleanup':True})
    with patch.object(config.ConfigPort,'execute',fake_scene),patch.object(config.ConfigPort,'cleanup',lambda self,ctx,ct,e:e['environment']['cleanup']):
        row=session.Session().execute(ctx,ledger,config.ConfigPort())
    return dict(source_kind=c.SYNTHETIC,context=ctx.public(),row=row,cold=cold,ledger=ledger.frames,boundaries=c.BOUNDARIES)

def rechain(p):
    previous=None
    for i,f in enumerate(p['ledger']):
        f.update(seq=i,previous=previous); f['sha256']=c.digest({k:v for k,v in f.items() if k!='sha256'}); previous=c.digest(f)

def mutations():
    def resource(p,key,value):
        next(f['event'] for f in p['ledger'] if f['event'].get('resource')=='provider' and f['event']['kind']=='RESERVE')[key]=value; rechain(p)
    def source(p): p['source_kind']=c.REAL
    def both(p): p['source_kind']=p['context']['source_kind']=c.REAL
    return {
        'source_promotion':source,'double_source_promotion':both,
        'owner':lambda p:p['context'].update(owner='rpf-64'),
        'abi':lambda p:p['context'].update(abi='rpf64-domain-port-v1'),
        'source_map':lambda p:p['context']['sources'].pop(c.NEW_FILES[0]),
        'role_spoof':lambda p:resource(p,'role','EXPLORER'),
        'input_cap':lambda p:resource(p,'input_upper',50000),
        'cost_omission':lambda p:resource(p,'cost_micro_cny_upper',0),
        'usage_unknown':lambda p:p['row']['evidence']['requests'][0].update(status='RESERVED_USAGE_UNKNOWN'),
        'provider_model':lambda p:p['row']['evidence']['completions'][0].update(model='untrusted'),
        'call_id':lambda p:p['row']['evidence']['tool_trace'][0].update(call_id='spoofed'),
        'tool_return':lambda p:p['row']['evidence']['tool_trace'][2].update(result={'status':'COMMITTED'}),
        'repeat_post':lambda p:p['row']['evidence']['http'].append(copy.deepcopy(p['row']['evidence']['http'][4])),
        'missing_readback':lambda p:p['row']['evidence']['http'].pop(),
        'false_authority':lambda p:p['row']['evidence']['environment'].update(authority='MODEL_SELF_REPORT'),
        'fault_truth':lambda p:p['row']['evidence'].update(original_success=None),
        'pid_spoof':lambda p:p['row']['evidence']['sdk'].update(popen_pid=1),
        'child_zombie':lambda p:p['row']['evidence']['environment']['cleanup'].update(java_exited=False),
        'feedback_explorer':lambda p:p['row']['feedback'].update(explorer_consumed=True),
        'cold_pid':lambda p:p['cold']['sdk'].update(popen_pid=42),
        'usage_omitted':lambda p:p['row']['evidence']['requests'].pop(),
        'authority_history':lambda p:p['row']['evidence']['http'][-2]['response'].update(data=[]),
    }

def controls(payload,folder):
    folder.mkdir(parents=True,exist_ok=False)
    def cli(raw,anchor):
        path=folder/'input.json'; path.write_bytes(raw); args=[sys.executable,'-B','-X','utf8','-m','runtime.runproof_runtime.effectwitness.pge_r65_verify',str(path)]
        if anchor is not None: args+=['--sha256',anchor]
        env={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH','TEMP','TMP','HOME','USERPROFILE') if k in os.environ}
        result=subprocess.run(args,cwd=c.ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)
        c.require(not result.stderr,'CLI_STDERR'); return result.returncode
    raw=c.canonical(v.seal(payload)); codes=[cli(raw,hashlib.sha256(raw).hexdigest()),cli(raw,None),cli(raw,'0'*64)]; c.require(codes==[0,2,3],'CLI_CODES'); attacks={}
    for name,mutate in mutations().items():
        p=copy.deepcopy(payload); mutate(p); raw=c.canonical(v.seal(p)); attacks[name]=cli(raw,hashlib.sha256(raw).hexdigest())
    c.require(set(attacks.values())=={3},'SEMANTIC_ATTACK_ACCEPTED'); return {'correct_missing_wrong':codes,'rehashed_semantic_controls':attacks}

class R65Tests(unittest.TestCase):
    def fresh(self):
        ctx=c.make_context(uuid.uuid4().hex[:16],(45001,45002),(45003,45004),synthetic=True)
        ctx.root.mkdir(parents=True,exist_ok=False)
        return ctx,c.Ledger(ctx,ctx.root/'account',create=True)
    def test_production_factory_signature_and_identity(self):
        ctx,ledger=self.fresh(); ct=ctx.contract()
        with patch('subprocess.Popen') as spawn,patch('socket.socket') as network:
            client,broker,host,journal=config.assemble_host(ctx,ct,ledger)
            bound=inspect.signature(config.Host).bind(ct,broker,host.business,journal,fixture=False,api_key=None)
            self.assertIs(bound.arguments['ledger'],broker)
            self.assertIs(host.ledger.total,ledger); self.assertIs(host.journal.ledger,ledger)
            self.assertIs(host.business.client,client); self.assertIs(client.total,ledger)
            self.assertIsNone(host.api_key); self.assertFalse(host.fixture)
            spawn.assert_not_called();network.assert_not_called()
        self.assertEqual(sum(ledger.read()['counts'].values()),0)
    def test_missing_broker_factory_mutation_is_rejected(self):
        ctx,ledger=self.fresh(); original=config.Host
        def omitted(ct,broker,business,journal,**kw): return original(ct,business,journal,**kw)
        with patch.object(config,'Host',side_effect=omitted),patch('subprocess.Popen') as spawn,patch('socket.socket') as network:
            with self.assertRaisesRegex(TypeError,'journal'):config.assemble_host(ctx,ctx.contract(),ledger)
            spawn.assert_not_called();network.assert_not_called()
        with self.assertRaises(TypeError):inspect.signature(original).bind(ctx.contract(),object(),object(),fixture=False,api_key=None)
    def test_actual_execute_reaches_same_factory_and_cleans_setup_error(self):
        ctx,ledger=self.fresh(); original=config.assemble_host; built=[]
        def observed(*args,**kw):
            value=original(*args,**kw);built.append(value);return value
        port=config.ConfigPort()
        # execute itself is never replaced. Stop only after its real factory.
        with patch.object(config,'assemble_host',side_effect=observed) as factory,patch.object(c,'helpers',side_effect=RuntimeError('SYNTHETIC_AFTER_FACTORY')),patch('subprocess.Popen') as spawn,patch('socket.socket') as network:
            with self.assertRaisesRegex(RuntimeError,'SYNTHETIC_AFTER_FACTORY'):port.execute(ctx,ctx.contract(),ledger)
            factory.assert_called_once_with(ctx,ctx.contract(),ledger,api_key=None)
            spawn.assert_not_called();network.assert_not_called()
        client,broker,host,journal=built[0]
        self.assertIs(host.ledger,broker);self.assertIsNone(client._api_key);self.assertIsNone(host.api_key);self.assertIsNone(port.api_key)
        self.assertEqual(ledger.read()['counts']['jvm'],0)
        self.assertTrue((ctx.folder(ctx.contract())/'environment-cleanup.json').exists())
    def test_context_rejects_rev1_root_and_probe_identity(self):
        ctx,ledger=self.fresh();p=ctx.public();p['workspace']='.local/rpf-65'
        with self.assertRaises(Exception):c.TaskContext(c.ROOT/p['workspace'],c.canonical(p))
        self.assertIn('spikes/rpf-65/rev-2/probe.py',ctx.public()['sources'])
        self.assertNotIn('spikes/rpf-65/probe.py',ctx.public()['sources'])
        with self.assertRaises(Exception):c.make_context('98e1e526fcc24743',(45001,45002),(45003,45004),synthetic=True)
    def test_actual_execute_full_nonmodel_protocol(self):
        ctx,ledger=self.fresh();ct=ctx.contract();jar=ctx.root/'jar/config-center-server-1.0.0.jar';jar.parent.mkdir()
        with jar.open('wb') as f:f.truncate(c.SOURCE_JAR_BYTES)
        ctx.once(ctx.root/'preflight/metadata.json',{'sources':c.sources(),'java':{'synthetic':True},'sdk':c.pinned_sdk_fields()})
        class Proc:
            pid=456
            def __init__(self,*a,**kw):self.returncode=None
            def poll(self):return self.returncode
            def terminate(self):self.returncode=0
            def kill(self):self.returncode=0
            def wait(self,timeout=None):return self.returncode
        class Log:
            overflow=False
            def __init__(self,*a):pass
            def close(self,*a):pass
        class Old:
            JAVA=Path('synthetic-java')
            _java_identity=staticmethod(lambda:{'synthetic':True})
            _sha_file=staticmethod(lambda p:c.SOURCE_JAR_SHA256)
            _port_closed=staticmethod(lambda p:True)
            _java_env=staticmethod(lambda *a:{})
            _RedactedJavaLog=Log
            _actual_process_command_line=staticmethod(lambda p:'synthetic')
            _split_windows_command_line=staticmethod(lambda s:[])
            _argv_jar_path_matches=staticmethod(lambda *a:True)
            _listener_owned=staticmethod(lambda *a:True)
            _external_connections=staticmethod(lambda p:[])
            _health_get=staticmethod(lambda *a,**k:{'status':200,'body':{'status':'UP'},'transport_error':None})
        def sdk_stub(ctx,ct,ledger,sdk,folder,host,**kw):
            t=ledger.reserve('sdk',domain=c.DOMAIN,run_id=ct['experiment']['run_id']);result=drive(host,ct,789)
            ledger.settle(t,popen_pid=789,status='COMPLETED');ledger.append('PROCESS_CLEANUP',resource='sdk',pid=789,process_exited=True);return result
        # Only external boundaries are synthetic; Session/Port/factory/Host/Broker
        # and real ConfigLiveBusiness/Oracle implementations execute unchanged.
        with patch.object(c,'helpers',return_value=(None,Old())),patch.object(config,'Http',FakeHttp),patch('subprocess.Popen',Proc),patch.object(config,'run_sdk',sdk_stub),patch('socket.socket') as network:
            row=session.Session().execute(ctx,ledger,config.ConfigPort('synthetic-only-no-credential'))
            network.assert_not_called()
        self.assertEqual(row['verdict']['effect'],'CONTRACT_SATISFIED_IN_RUN')
        self.assertTrue(row['verdict']['fault']['agent_exposed']);self.assertTrue(all(row['cleanup'].values()))
        self.assertIsNone(c.strict_json((ctx.folder(ct)/'scene-capture.json').read_bytes())['host_failure'])
    def test_post_limit_and_nonrefund(self):
        ctx,ledger=self.fresh()
        for operation in c.TOOLS[1:]:
            t=ledger.reserve('post',operation=operation);ledger.settle(t,status=200,unknown=False)
        with self.assertRaises(Exception):ledger.reserve('post',operation='update_config_v2')
        with self.assertRaises(Exception):ledger.settle('post-1',status=200)
        self.assertEqual(ledger.read()['counts']['post'],2)
    def test_provider_usage_unknown_blocks_broker(self):
        ctx,ledger=self.fresh();broker=config.BrokerLedger(ledger,ctx.contract()['experiment']['run_id'])
        record=broker.reserve({'messages':[]},[]);broker.fail_unknown(record,'SYNTHETIC_TRANSPORT_UNKNOWN')
        with self.assertRaises(Exception):broker.reserve({'messages':[]},[])
        with self.assertRaises(Exception):ledger.reserve('sdk')
        self.assertTrue(ledger.read()['unknown'])
    def test_guarded_error_report_uses_ready_pid(self):
        p=synthetic_payload();s=copy.deepcopy(p['row']['evidence']['sdk'])
        s['report']={'status':'SDK_ERROR','stage':'sdk_run','error_type':'APIStatusError','guard_code':None,'guard_denials':[]};s['returncode']=1
        # The fixed SDK error report deliberately omits pid; ready/Popen bind it.
        v.verify_sdk(s,[],[],guarded=True)
        s['ready']['pid']=999
        with self.assertRaises(Exception):v.verify_sdk(s,[],[],guarded=True)
    def test_synthetic_session(self):
        p=synthetic_payload(); result=v.verify_payload(p); self.assertEqual(result['source_kind'],c.SYNTHETIC); self.assertEqual(result['physical']['provider'],5)
    def test_semantic_controls(self):
        p=synthetic_payload()
        for name,mutate in mutations().items():
            with self.subTest(name=name):
                q=copy.deepcopy(p); mutate(q); raw=c.canonical(v.seal(q))
                with self.assertRaises(Exception): v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    def test_budget_unknown_and_lock(self):
        ctx=c.make_context(uuid.uuid4().hex[:16],(45001,45002),(45003,45004),synthetic=True); ctx.root.mkdir(parents=True); ledger=c.Ledger(ctx,ctx.root/'account',create=True)
        kw=dict(role='TARGET',run_id=ctx.contract()['experiment']['run_id'],request_sha256='0'*64,token_upper=3000,input_upper=1000,output_cap=256,proof={},cost_micro_cny_upper=9108)
        t=ledger.reserve('provider',**kw)
        with self.assertRaises(Exception): ledger.reserve('post')
        ledger.settle(t,status='UNKNOWN',unknown=True)
        with self.assertRaises(Exception): ledger.reserve('provider',**kw)
        r=ledger.reserve('http',method='GET'); ledger.settle(r,status=200)
        with (ledger.path/'mutation.lock').open('xb'): pass
        with self.assertRaises(FileExistsError): ledger.append('TEST')
    def test_host_rejects_write_before_io(self):
        ctx=c.make_context(uuid.uuid4().hex[:16],(45001,45002),(45003,45004),synthetic=True); ct=ctx.contract(); journal=type('J',(),{'add':lambda *a,**k:None})()
        backend=config.ConfigLiveMemoryBackend(); host=config.Host(ct,config.ProviderLedger.fixture_only('synthetic'),backend,journal,api_key='synthetic-only'); host.tool_trace=[{}, {}, {}]; host.activated=True
        with self.assertRaises(config.LiveRuntimeRejected): host._tool(dict(call_id='invalid',name='update_config_v2',arguments={'value':'rpf53-v2','expected_version':1}))
        self.assertEqual(len(host.tool_rejections),1); self.assertEqual(backend.version,0)
    def test_scope_and_static_port(self):
        ctx=c.make_context(uuid.uuid4().hex[:16],(45001,45002),(45003,45004),synthetic=True)
        with self.assertRaises(Exception): ctx.scope(c.ROOT/'.local/rpf-64')
        with self.assertRaises(Exception): session.Session().execute(ctx,None,object())
    def test_supervisor_failed_start_cleanup(self):
        ctx=c.make_context(uuid.uuid4().hex[:16],(45001,45002),(45003,45004),synthetic=True); ctx.root.mkdir(parents=True); ledger=c.Ledger(ctx,ctx.root/'account',create=True); sup=c.ProcessSupervisor(ctx,ledger,ctx.contract(),'sdk')
        with patch('subprocess.Popen',side_effect=OSError('synthetic')):
            with self.assertRaises(OSError): sup.start(['synthetic'],{},ctx.root)
        self.assertFalse(sup.close()['process_exited']); self.assertEqual(ledger.read()['counts']['sdk'],1)
if __name__=='__main__': unittest.main()
