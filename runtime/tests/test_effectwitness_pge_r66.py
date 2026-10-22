"""RPF66 synthetic state machine and independently reanchored semantic attacks."""
import copy, hashlib, inspect, os, subprocess, sys, unittest, uuid
from pathlib import Path
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_r66_context as c, pge_r66_target_config as config, pge_r66_session as session, pge_r66_verify as v
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
            if not msg.get('tool_calls'):break
            for call in msg.get('tool_calls',[]):
                result=host._tool(dict(call_id=call['id'],name=call['function']['name'],arguments=c.strict_json(call['function']['arguments'].encode())))
                messages.append(dict(role='tool',tool_call_id=call['id'],content=c.canonical(result).decode()))
    r=dict(status='COMPLETED',framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=pid,python_executable_sha256=pin['python_executable_sha256'],sdk_source_sha256=c.SDK_CORE_SHA256,openai_source_sha256=pin['openai_core_sha256'],guard_denials=[],provider_key_present=False,business_key_present=False,final_text_persisted=False,tool_calls=len(host.tool_trace),tool_callbacks=len(host.tool_trace),requests=len(host.provider_responses),input_tokens=0 if cold else 500*len(host.provider_responses),output_tokens=0 if cold else 50*len(host.provider_responses))
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
    index=ct['experiment']['round'];run=ct['experiment']['run_id']; j=config.Journal(ledger,run); client=FakeHttp(ctx,ct,'synthetic-only',j,ledger)
    jvm=ledger.reserve('jvm',domain=c.DOMAIN,run_id=run); ledger.settle(jvm,popen_pid=456+index,status='STARTED')
    h=ledger.reserve('health',domain=c.DOMAIN,run_id=run); ledger.settle(h,status=200,response_sha256=c.digest({'status':'UP'}))
    client.initial_state_valid(); broker=config.BrokerLedger(ledger,run); host=config.Host(ct,broker,config.ConfigLiveBusiness(ct,client),j,api_key='synthetic-only')
    sd=ledger.reserve('sdk',domain=c.DOMAIN,run_id=run); sdk=drive(host,ct,789+index); ledger.settle(sd,popen_pid=789+index,status='COMPLETED'); ledger.append('PROCESS_CLEANUP',resource='sdk',pid=789+index,process_exited=True)
    client.stop_writes=True; client.final_readback(reconcile=True); client.request('final_list'); ledger.append('PROCESS_CLEANUP',resource='jvm',pid=456+index,process_exited=True)
    env=dict(source_level='REAL_JAVA_H2_LOCAL_SIMULATION',authority='SAME_SERVICE_READ_ONLY_HTTP',jar_sha256=c.SOURCE_JAR_SHA256,jar_bytes=c.SOURCE_JAR_BYTES,java_pid=456+index,jar_command_verified=True,listener_owned=True,health=[dict(status=200,body={'status':'UP'},raw_body_sha256=c.digest({'status':'UP'}),transport_error=None)],cleanup=dict.fromkeys(('java_exited','java_port_closed','sdk_exited','host_port_closed','host_thread_stopped','local_key_released'),True))
    return dict(contracts=ct,requests=broker.data['requests'],tool_rejections=[],http=client.observations,events=j.events,tool_trace=host.tool_trace,completions=host.provider_responses,visibility=host.visible_contract_checks,sdk=sdk,environment=env,original_success=host.original_success,host_failure=None)

from runtime.runproof_runtime.effectwitness import pge_r66_explorer as explorer

def synthetic_choice(candidates):
 def choose(ctx,ledger,index,key,rows):
    body=explorer.body_for(rows);meter=explorer.ExplorerMeter(ledger,index,ctx.contract(index)['experiment']['run_id']);ticket=meter.reserve_request('EXPLORER',index,body)
    selection={'id':'select_round_'+str(index),'type':'function','function':{'name':'select_experiment','arguments':c.canonical({'candidate_id':candidates[index-1]}).decode()}}
    data={'id':str(uuid.uuid4()),'model':c.MODEL,'usage':dict(prompt_tokens=300,completion_tokens=30,total_tokens=330),'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[selection]}}]}
    observation={'shape':explorer.safe_response_shape(data),'attempt':ticket,'request_sha256':c.digest(body),'http_status':200,'received_monotonic_ns':__import__('time').monotonic_ns()}
    meter.received(ticket,data);selection=explorer.parse_selection(data,{r['selection']['id'] for r in rows})
    return dict(body=body,observation=observation,provider_ticket=ticket,selection=selection)
 return choose

def fresh():
 ctx=c.make_context(uuid.uuid4().hex[:16],(45001,45002,45003,45004),(45005,45006),synthetic=True);ctx.root.mkdir(parents=True,exist_ok=False);return ctx,c.Ledger(ctx,ctx.root/'account',create=True)

def synthetic_payload(candidates=None):
    candidates=candidates or (c.CANDIDATES[1],)*2;ctx,ledger=fresh()
    m=ledger.reserve('metadata');ledger.settle(m,status='PASS');ct=ctx.public()['cold_contract'];j=config.Journal(ledger,ct['experiment']['run_id'])
    host=config.Host(ct,config.ProviderLedger.fixture_only(ct['experiment']['run_id']),config.ConfigLiveMemoryBackend(),j,fixture=True)
    t=ledger.reserve('cold',domain=c.DOMAIN,run_id=ct['experiment']['run_id']);sdk=drive(host,ct,123,cold=True);ledger.settle(t,popen_pid=123,status='COMPLETED');ledger.append('PROCESS_CLEANUP',resource='cold',pid=123,process_exited=True)
    cold=dict(status='PASS',source_kind='FIXTURE_SCRIPTED',contract=ct,sources=c.sources(),sdk=sdk,tool_trace=host.tool_trace,completions=host.provider_responses,events=j.events,checks={'protocol':True,'provider_zero':True,'cleanup':True})
    with patch.object(config.ConfigPort,'execute',fake_scene),patch.object(config.ConfigPort,'cleanup',lambda self,ctx,ct,e:e['environment']['cleanup']):
        rows=session.Session().execute(ctx,ledger,config.ConfigPort(),choose=synthetic_choice(candidates))
    return dict(source_kind=c.SYNTHETIC,context=ctx.public(),rows=rows,cold=cold,ledger=ledger.frames,boundaries=c.BOUNDARIES)

def rechain(p):
 previous=None
 for i,f in enumerate(p['ledger']):
    f.update(seq=i,previous=previous);f['sha256']=c.digest({k:v for k,v in f.items() if k!='sha256'});previous=c.digest(f)

def mutations():
 def reserve(p,key,value):
    next(f['event'] for f in p['ledger'] if f['event'].get('resource')=='provider' and f['event']['kind']=='RESERVE')[key]=value;rechain(p)
 def scene(p):return p['rows'][0]['evidence']
 def drop_frame(p):p['ledger'].pop(3);rechain(p)
 def reorder(p):p['ledger'][2],p['ledger'][3]=p['ledger'][3],p['ledger'][2];rechain(p)
 def normal_false(p):
    row=next((r for r in p['rows'] if r['candidate_id']==c.CANDIDATES[0]),p['rows'][0]);row['verdict']['fault']['triggered']=not row['verdict']['fault']['triggered']
 return {
 'source_promotion':lambda p:p.update(source_kind=c.REAL if p['source_kind']==c.SYNTHETIC else c.SYNTHETIC),
 'double_source_promotion':lambda p:(p.update(source_kind=c.REAL if p['source_kind']==c.SYNTHETIC else c.SYNTHETIC),p['context'].update(source_kind=p['source_kind'])),
 'owner':lambda p:p['context'].update(owner='rpf-65'),
 'abi':lambda p:p['context'].update(abi='rpf64-domain-port-v1'),
 'source_map':lambda p:p['context']['sources'].pop(c.NEW_FILES[0]),
 'root':lambda p:p['context'].update(workspace='.local/rpf-63'),
 'role':lambda p:reserve(p,'role','TARGET'),
 'round':lambda p:reserve(p,'round',2),
 'input_cap':lambda p:reserve(p,'input_upper',50000),
 'cost_omission':lambda p:reserve(p,'cost_micro_cny_upper',0),
 'token_pool':lambda p:reserve(p,'token_upper',35001),
 'usage_unknown':lambda p:scene(p)['requests'][0].update(status='RESERVED_USAGE_UNKNOWN'),
 'model':lambda p:scene(p)['completions'][0].update(model='untrusted'),
 'call_id':lambda p:scene(p)['tool_trace'][0].update(call_id='spoofed'),
 'tool_result':lambda p:scene(p)['tool_trace'][2].update(result={'status':'COMMITTED'}),
 'repeat_post':lambda p:scene(p)['http'].append(copy.deepcopy(scene(p)['http'][4])),
 'missing_oracle':lambda p:scene(p)['http'].pop(),
 'authority':lambda p:scene(p)['environment'].update(authority='THIRD_PARTY_AUTHORITY'),
 'fault_truth':lambda p:scene(p).update(original_success={'fake':True}),
 'pid':lambda p:scene(p)['sdk'].update(popen_pid=1),
 'cleanup':lambda p:scene(p)['environment']['cleanup'].update(java_exited=False),
 'future_feedback':lambda p:p['rows'][1]['body']['messages'].append({'role':'user','content':'future facts'}),
 'feedback_hash':lambda p:p['rows'][0]['feedback'].update(oracle_sha256='0'*64),
 'cold_pid':lambda p:p['cold']['sdk'].update(popen_pid=42),
 'missing_usage':lambda p:scene(p)['requests'][0].update(usage=None),
 'history':lambda p:scene(p)['http'][-2]['response'].update(data=[]),
 'candidate':lambda p:p['rows'][1].update(candidate_id='write-anything'),
 'explorer_tool_id':lambda p:p['rows'][1]['selection'].update(id=p['rows'][0]['selection']['id']),
 'explorer_response_id':lambda p:p['rows'][1]['observation']['shape'].update(response_id=p['rows'][0]['observation']['shape']['response_id']),
 'wal_missing':drop_frame,'wal_reorder':reorder,
 'normal_false_trigger':normal_false,
 'cold_promotion':lambda p:p['cold'].update(source_kind=c.REAL),
 'issuer_claim':lambda p:p['boundaries'].update(issuer='SIGNED'),
 'L2_fabrication':lambda p:p['rows'][1]['feedback'].update(new_facts=['fabricated']),
 }

def controls(payload,folder):
 folder.mkdir(parents=True,exist_ok=False)
 def cli(raw,anchor):
    path=folder/'input.json';path.write_bytes(raw);args=[sys.executable,'-B','-X','utf8','-m','runtime.runproof_runtime.effectwitness.pge_r66_verify',str(path)]
    if anchor is not None:args+=['--sha256',anchor]
    env={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH','COMSPEC','PATHEXT') if k in os.environ};env.update(HOME=str(folder),USERPROFILE=str(folder),TEMP=str(folder),TMP=str(folder),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run(args,cwd=c.ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40);c.require(not result.stderr,'CLI_STDERR');return result.returncode
 raw=c.canonical(v.seal(payload));codes=[cli(raw,hashlib.sha256(raw).hexdigest()),cli(raw,None),cli(raw,'0'*64)];c.require(codes==[0,2,3],'CLI_CODES');attacks={}
 for name,mutate in mutations().items():
    q=copy.deepcopy(payload);before=c.digest(q);mutate(q);c.require(c.digest(q)!=before,'NO_OP_ATTACK');raw=c.canonical(v.seal(q));attacks[name]=cli(raw,hashlib.sha256(raw).hexdigest())
 c.require(set(attacks.values())=={3},'SEMANTIC_ATTACK_ACCEPTED');return {'correct_missing_wrong':codes,'reanchored_semantic_controls':attacks}

class R66Tests(unittest.TestCase):
 def test_four_sequences(self):
    import itertools
    for candidates in itertools.product(c.CANDIDATES,repeat=2):
        with self.subTest(candidates=candidates):
            p=synthetic_payload(candidates);result=v.verify_payload(p);self.assertEqual(result['source_kind'],c.SYNTHETIC);self.assertEqual(result['L2_observed'],candidates[0]!=candidates[1]);self.assertEqual(result['physical']['post'],4)
 def test_semantic_attacks(self):
    p=synthetic_payload()
    for name,mutate in mutations().items():
        with self.subTest(name=name):
            q=copy.deepcopy(p);before=c.digest(q);mutate(q);self.assertNotEqual(c.digest(q),before);raw=c.canonical(v.seal(q))
            with self.assertRaises(Exception):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
 def test_factory_same_objects_and_no_io(self):
    ctx,ledger=fresh()
    with patch('subprocess.Popen') as spawn,patch('socket.socket') as network:
        for i in (1,2):
            for candidate in c.CANDIDATES:
                ct=ctx.contract(i,candidate);client,broker,host,j=config.assemble_host(ctx,ct,ledger)
                self.assertIs(host.ledger,broker);self.assertIs(broker.total,ledger);self.assertIs(host.business.client,client);self.assertIs(j.ledger,ledger)
        spawn.assert_not_called();network.assert_not_called()
 def test_actual_execute_factory_setup_error_cleanup(self):
    ctx,ledger=fresh();ct=ctx.contract();original=config.assemble_host;built=[]
    def observed(*a,**kw):value=original(*a,**kw);built.append(value);return value
    with patch.object(config,'assemble_host',side_effect=observed),patch.object(c,'helpers',side_effect=RuntimeError('SYNTHETIC_AFTER_FACTORY')),patch('subprocess.Popen') as spawn,patch('socket.socket') as network:
        with self.assertRaisesRegex(RuntimeError,'SYNTHETIC_AFTER_FACTORY'):config.ConfigPort().execute(ctx,ct,ledger)
        spawn.assert_not_called();network.assert_not_called()
    self.assertIsNone(built[0][0]._api_key);self.assertTrue((ctx.folder(ct)/'environment-cleanup.json').exists())
 def test_actual_execute_full_nonmodel_protocol(self):
     ctx,ledger=fresh();ct=ctx.contract();jar=ctx.root/'jar/config-center-server-1.0.0.jar';jar.parent.mkdir()
     with jar.open('wb') as f:f.truncate(c.SOURCE_JAR_BYTES)
     ctx.once(ctx.root/'preflight/metadata.json',{'sources':c.sources(),'java':{'synthetic':True},'sdk':c.pinned_sdk_fields()})
     class Proc:
         counter=0
         pid=None
         def __init__(self,*a,**kw):
             Proc.counter+=1;self.pid=456+Proc.counter;self.returncode=None
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
         t=ledger.reserve('sdk',domain=c.DOMAIN,run_id=ct['experiment']['run_id']);result=drive(host,ct,789+ct['experiment']['round'])
         ledger.settle(t,popen_pid=789+ct['experiment']['round'],status='COMPLETED');ledger.append('PROCESS_CLEANUP',resource='sdk',pid=789+ct['experiment']['round'],process_exited=True);return result
     # Only external boundaries are synthetic; Session/Port/factory/Host/Broker
     # and real ConfigLiveBusiness/Oracle implementations execute unchanged.
     with patch.object(c,'helpers',return_value=(None,Old())),patch.object(config,'Http',FakeHttp),patch('subprocess.Popen',Proc),patch.object(config,'run_sdk',sdk_stub),patch('socket.socket') as network:
         rows=session.Session().execute(ctx,ledger,config.ConfigPort('synthetic-only-no-credential'),choose=synthetic_choice((c.CANDIDATES[0],c.CANDIDATES[1])))
         row=rows[1]
         network.assert_not_called()
     self.assertEqual(row['verdict']['effect'],'CONTRACT_SATISFIED_IN_RUN')
     self.assertTrue(row['verdict']['fault']['agent_exposed']);self.assertTrue(all(row['cleanup'].values()))
     self.assertIsNone(c.strict_json((ctx.folder(ct)/'scene-capture.json').read_bytes())['host_failure'])
 def test_unknown_blocks_both_roles_and_writes(self):
    ctx,ledger=fresh();broker=config.BrokerLedger(ledger,ctx.contract()['experiment']['run_id']);record=broker.reserve({'messages':[]},[]);broker.fail_unknown(record,'SYNTHETIC_UNKNOWN')
    with self.assertRaises(Exception):explorer.ExplorerMeter(ledger,2,ctx.contract(2)['experiment']['run_id']).reserve_request('EXPLORER',2,explorer.body_for([]))
    with self.assertRaises(Exception):ledger.reserve('post',run_id=ctx.contract()['experiment']['run_id'])
    t=ledger.reserve('http',run_id=ctx.contract()['experiment']['run_id'],method='GET');ledger.settle(t,status=200)
 def test_round_limits_and_nonrefund(self):
    ctx,ledger=fresh();run=ctx.contract()['experiment']['run_id']
    for _ in range(2):t=ledger.reserve('post',run_id=run);ledger.settle(t,status=200)
    with self.assertRaises(Exception):ledger.reserve('post',run_id=run)
    with self.assertRaises(Exception):ledger.settle('post-1',status=200)
    self.assertEqual(ledger.read()['counts']['post'],2)
 def test_lock_torn_scope(self):
    ctx,ledger=fresh()
    with (ledger.path/'mutation.lock').open('xb'):pass
    with self.assertRaises(FileExistsError):ledger.append('TEST')
    with self.assertRaises(Exception):ctx.scope(c.ROOT/'.local/rpf-65')
    with (ledger.path/'ledger.jsonl').open('ab') as f:f.write(b'{')
    with self.assertRaises(Exception):ledger.read()
 def test_input_prefix_guard(self):
    ctx,ledger=fresh();broker=config.BrokerLedger(ledger,ctx.contract()['experiment']['run_id']);r=broker.reserve({'messages':[],'model':c.MODEL},[]);broker.received(r,{'id':str(uuid.uuid4()),'model':c.MODEL,'usage':dict(prompt_tokens=10,completion_tokens=1,total_tokens=11)})
    with self.assertRaises(Exception):broker.reserve({'messages':[],'model':'changed'},[])
    for malformed in ({'messages':[]},{'messages':[],'model':c.MODEL,'temperature':1},{'messages':[{'role':'user','content':'replaced'}],'model':'changed'}):
        with self.subTest(malformed=malformed):
            with self.assertRaises(Exception):broker.reserve(malformed,[])
 def test_explorer_arguments_and_replay(self):
    data={'model':c.MODEL,'id':str(uuid.uuid4()),'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','tool_calls':[{'id':'x','type':'function','function':{'name':'select_experiment','arguments':'{"candidate_id":"normal","extra":1}'}}]}}]}
    with self.assertRaises(Exception):explorer.parse_selection(data,set())
    data['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{"candidate_id":"normal"}'
    with self.assertRaises(Exception):explorer.parse_selection(data,{'x'})
 def test_write_after_unknown_rejected_before_io(self):
    ctx,_=fresh();ct=ctx.contract();j=type('J',(),{'add':lambda *a,**k:None})();backend=config.ConfigLiveMemoryBackend();host=config.Host(ct,config.ProviderLedger.fixture_only('synthetic'),backend,j);host.tool_trace=[{},{},{}];host.activated=True
    with self.assertRaises(Exception):host._tool(dict(call_id='fake',name='update_config_v2',arguments={}))
    self.assertEqual(backend.version,0)
if __name__=='__main__':unittest.main()
