"""RPF66 synthetic state machine and independently reanchored semantic attacks."""
import copy, hashlib, inspect, os, subprocess, sys, unittest, uuid
from pathlib import Path
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_r66_context as c, pge_r66_target_config as config, pge_r66_session as session, pge_r66_verify as v
from runtime.runproof_runtime.effectwitness.config_live_contracts import TOOL_ARGUMENT_KEYS

def registry():
    return [{'type':'function','function':{'name':n,'description':c.TOOL_HELP[n],'parameters':{'type':'object','properties':{k:{'type':'integer' if k=='expected_version' else 'string'} for k in TOOL_ARGUMENT_KEYS[n]},'required':list(TOOL_ARGUMENT_KEYS[n]),'additionalProperties':False},'strict':True}} for n in c.TOOLS]

def drive(host,ct,pid,*,cold=False,bad_final=False):
    pin=c.pinned_sdk_fields(); ready=dict(framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=pid,python_executable_sha256=pin['python_executable_sha256'],sdk_source_sha256=c.SDK_CORE_SHA256,openai_source_sha256=pin['openai_core_sha256'],sdk_site_root_binding_sha256=pin['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=pin['python_runtime_mapping_sha256'])
    host._ready(ready); messages=[{'role':'system','content':ct['execution']['agent_instructions']},{'role':'user','content':ct['execution']['task_prompt']}]
    def response(body):
        data=host._fixture_response(body); data['id']=str(uuid.uuid4()); data['model']=c.MODEL; data['usage']=dict(prompt_tokens=500,completion_tokens=50,total_tokens=550)
        if bad_final and data['choices'][0]['finish_reason']=='stop':data['choices'][0]['finish_reason']='length'
        return data
    with patch.object(config.ConfigLiveHost,'_provider_request',autospec=True,side_effect=lambda self,body:response(body)):
        for _ in range(5):
            data=host._completion(dict(model='rpf53-fixture-only' if cold else c.MODEL,messages=copy.deepcopy(messages),tools=registry(),tool_choice='auto',parallel_tool_calls=False,max_tokens=512))
            msg=data['choices'][0]['message']; messages.append(msg)
            if not msg.get('tool_calls'):break
            for call in msg.get('tool_calls',[]):
                result=host._tool(dict(call_id=call['id'],name=call['function']['name'],arguments=c.strict_json(call['function']['arguments'].encode())))
                messages.append(dict(role='tool',tool_call_id=call['id'],content=c.canonical(result).decode()))
    r=dict(status='COMPLETED',framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=pid,python_executable_sha256=pin['python_executable_sha256'],sdk_source_sha256=c.SDK_CORE_SHA256,openai_source_sha256=pin['openai_core_sha256'],guard_denials=[],provider_key_present=False,business_key_present=False,final_text_persisted=False,tool_calls=len(host.tool_trace),tool_callbacks=len(host.tool_trace),requests=len(host.provider_responses),input_tokens=0 if cold else 500*len(host.provider_responses),output_tokens=0 if cold else 50*len(host.provider_responses))
    return dict(child_script=c.child_identity(),child_script_argv_verified=True,popen_pid=pid,ready=ready,report=r,returncode=0,stderr_bytes=0)

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
    return dict(body=explorer.body_receipt(body,rows),observation=observation,provider_ticket=ticket,selection=selection)
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
 attacks={
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
 'future_feedback':lambda p:p['rows'][1]['body'].update(prior_feedback_sha256='0'*64),
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

 def shape_attack(p,mutate):
    event=next(f['event'] for f in p['ledger'] if f['event']['kind']=='PROVIDER_SHAPE_OBSERVED');old=event['receipt_sha256'];mutate(event['receipt']);new=c.digest(event['receipt']);event['receipt_sha256']=new
    for frame in p['ledger']:
        e=frame['event']
        if e.get('receipt_sha256')==old:e['receipt_sha256']=new
        for record in e.get('requests',[]):
            if record.get('shape_sha256')==old:record['shape_sha256']=new
    for row in p['rows']:
        for record in row['evidence']['requests']:
            if record.get('shape_sha256')==old:record['shape_sha256']=new
    rechain(p)
 def missing_shape(p):
    i=next(i for i,f in enumerate(p['ledger']) if f['event']['kind']=='PROVIDER_SHAPE_OBSERVED');p['ledger'].pop(i);rechain(p)
 def rejected(p):
    e=next(f['event'] for f in p['ledger'] if f['event']['kind']=='PROVIDER_PARSE_ACCEPTED');e.update(kind='PROVIDER_PARSE_REJECTED',code='PROVIDER_CHOICE',stage='STRICT_RESPONSE_VALIDATION');rechain(p)
 def historical_shape(p):
    event=next(f['event'] for f in p['ledger'] if f['event']['kind']=='PROVIDER_STATE' and any(r['status']=='RECEIVED' and 'shape_sha256' in r for r in f['event']['requests']));next(r for r in event['requests'] if r['status']=='RECEIVED')['shape_sha256']='0'*64;rechain(p)
 def lost_selection(p):
    e=next(f['event'] for f in p['ledger'] if f['event']['kind']=='CHOICE_FROZEN');e['receipt']['selection'].pop('id');e['receipt_sha256']=c.digest(e['receipt']);rechain(p)
 def shape_reversed(p):
    frames=p['ledger'];a=next(i for i,f in enumerate(frames) if f['event']['kind']=='PROVIDER_SHAPE_OBSERVED');b=next(i for i,f in enumerate(frames) if f['event']['kind']=='PROVIDER_PARSE_ACCEPTED')
    stamp=frames[a]['event']['monotonic_ns']
    for f in frames[a:b+1]:f['event']['monotonic_ns']=stamp
    frames[a],frames[b]=frames[b],frames[a];rechain(p)
 def parse_replay(p):
    frames=p['ledger'];i=next(i for i,f in enumerate(frames) if f['event']['kind']=='PROVIDER_PARSE_ACCEPTED');frames.insert(i+1,copy.deepcopy(frames[i]));rechain(p)
 def clock_reverse(p):
    p['ledger'][2]['event']['monotonic_ns']=p['ledger'][1]['event']['monotonic_ns']-1;rechain(p)
 def cross_ticket(p):
    e=next(f['event'] for f in p['ledger'] if f['event']['kind']=='PROVIDER_PARSE_ACCEPTED');e['provider_ticket']='provider-1';rechain(p)
 def selection_late(p):
    frames=p['ledger'];a=next(i for i,f in enumerate(frames) if f['event']['kind']=='CHOICE_FROZEN');b=next(i for i,f in enumerate(frames) if f['event']['kind']=='RESERVE' and f['event']['resource']=='jvm');frames[a],frames[b]=frames[b],frames[a];rechain(p)
 attacks.update({
  'shape_unknown_choice_keys':lambda p:shape_attack(p,lambda r:r['shape']['choices'][0]['fields'].update(unknown_count=1)),
  'shape_length_rejected':lambda p:shape_attack(p,lambda r:r['shape']['choices'][0].update(finish_reason='length')),
  'shape_forced_stop':lambda p:shape_attack(p,lambda r:r['shape']['choices'][0].update(finish_reason='stop')),
  'shape_index_false':lambda p:shape_attack(p,lambda r:r['shape']['choices'][0].update(index_zero=False)),
  'shape_cross_role':lambda p:shape_attack(p,lambda r:r.update(role='EXPLORER')),
  'shape_usage_hint_promoted':lambda p:shape_attack(p,lambda r:r['shape']['usage'].update(confidence='TRUSTED_SETTLED')),
  'shape_request_scope':lambda p:shape_attack(p,lambda r:r.update(request_sha256='0'*64)),
  'shape_absent':missing_shape,'shape_rejected_as_success':rejected,'original_selection_id_absent':lost_selection,
  'partial_as_success':lambda p:p.update(rows=p['rows'][:1]),'provider_shape_history_rewrite':historical_shape,
  'equal_clock_shape_parse_reordered':shape_reversed,'accepted_parse_replayed':parse_replay,
  'raw_clock_decreasing':clock_reverse,'accepted_parse_cross_ticket':cross_ticket,'selection_after_jvm':selection_late,
 })
 def binding_attack(p,key,value,stage=False):
    event=next(f['event'] for f in p['ledger'] if f['event']['kind']=='RESERVE' and f['event'].get('role')=='TARGET')
    target=event['binding']['stage'] if stage else event['binding'];target[key]=value;rechain(p)
 attacks.update({
  'v5_sdk_cap':lambda p:binding_attack(p,'sdk_requested_max_tokens',256),
  'v5_nonterminal_512':lambda p:binding_attack(p,'outbound_max_tokens',512),
  'v5_sdk_hash_type':lambda p:binding_attack(p,'sdk_request_sha256','invalid'),
  'v5_outbound_hash':lambda p:binding_attack(p,'outbound_request_sha256','0'*64),
  'v5_config_drift':lambda p:binding_attack(p,'sdk_config_sha256','0'*64),
  'v5_message_drift':lambda p:binding_attack(p,'sdk_messages_sha256','0'*64),
  'v5_early_terminal':lambda p:binding_attack(p,'terminal',True,True),
  'v5_sixth_request':lambda p:binding_attack(p,'attempt',6,True),
  'v5_missing_tools':lambda p:binding_attack(p,'completed_tools',[{'name':'update_config_v2'}],True),
  'v5_cross_run':lambda p:binding_attack(p,'run_id','another-run',True),
  'v5_foreign_candidate':lambda p:binding_attack(p,'candidate_id','uncontrolled',True),
  'v5_stage_cap':lambda p:binding_attack(p,'outbound_max_tokens',128,True),
  'v5_child_source':lambda p:p['rows'][0]['evidence']['sdk']['child_script'].update(lf_sha256='0'*64),
  'v5_child_argv':lambda p:p['rows'][0]['evidence']['sdk'].update(child_script_argv_verified=False),
 })
 return attacks

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
 def test_actual_execute_failure_keeps_selection_and_reconcile(self):
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
         t=ledger.reserve('sdk',domain=c.DOMAIN,run_id=ct['experiment']['run_id'])
         try:result=drive(host,ct,789+ct['experiment']['round'],bad_final=True)
         except config.LiveRuntimeRejected as exc:
             host.failure={'domain':'PROVIDER','code':exc.code};result={'child_script':c.child_identity(),'child_script_argv_verified':True,'popen_pid':789+ct['experiment']['round'],'ready':host.runtime,'report':{'status':'SDK_ERROR','stage':'sdk_run','error_type':'ModelHTTPError','guard_code':None,'guard_denials':[]},'returncode':1,'stderr_bytes':0}
         ledger.settle(t,popen_pid=789+ct['experiment']['round'],status='COMPLETED');ledger.append('PROCESS_CLEANUP',resource='sdk',pid=789+ct['experiment']['round'],process_exited=True);return result
     # Only external boundaries are synthetic; Session/Port/factory/Host/Broker
     # and real ConfigLiveBusiness/Oracle implementations execute unchanged.
     with patch.object(c,'helpers',return_value=(None,Old())),patch.object(config,'Http',FakeHttp),patch('subprocess.Popen',Proc),patch.object(config,'run_sdk',sdk_stub),patch('socket.socket') as network:
         with self.assertRaises(Exception):session.Session().execute(ctx,ledger,config.ConfigPort('synthetic-only-no-credential'),choose=synthetic_choice((c.CANDIDATES[1],c.CANDIDATES[0])))
         network.assert_not_called()
     scene=c.strict_json((ctx.folder(ct)/'scene-capture.json').read_bytes());receipt=c.strict_json((ctx.root/'session-receipt.json').read_bytes())
     self.assertEqual(receipt['status'],'NOT_COMPLETE');self.assertEqual(receipt['completed_rounds'],0);self.assertEqual(len(receipt['selections']),1);self.assertEqual(receipt['selections'][0]['selection']['id'],'select_round_1')
     self.assertTrue((ctx.root/'explorer-selections/selection-1.json').exists());self.assertTrue(ledger.read()['unknown']);self.assertEqual([o['kind'] for o in scene['http'][-3:]],['reconcile_current','reconcile_history','final_list']);self.assertTrue(all(scene['environment']['cleanup'].values()))
     self.assertFalse(any(e['kind'] in ('DOMAIN_VERIFIED','FEEDBACK_FROZEN') for e in ledger.read()['events']))
 def test_unknown_blocks_both_roles_and_writes(self):
    ctx,ledger=fresh();broker=config.BrokerLedger(ledger,ctx.contract()['experiment']['run_id']);body={'messages':[],'max_tokens':256,'thinking':{'type':'disabled'}};sdk={**body,'max_tokens':512};st=c.stage_for(ctx.contract(),1,[],[],stop_writes=False);record=broker.reserve(body,[],sdk_body=sdk,stage=st);broker.fail_unknown(record,'SYNTHETIC_UNKNOWN')
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
    with self.assertRaises(Exception):ctx.scope(c.ROOT/'.local/rpf-66')
    with (ledger.path/'ledger.jsonl').open('ab') as f:f.write(b'{')
    with self.assertRaises(Exception):ledger.read()
 def test_input_prefix_guard(self):
    ctx,ledger=fresh();broker=config.BrokerLedger(ledger,ctx.contract()['experiment']['run_id']);body={'messages':[],'model':c.MODEL,'max_tokens':256,'thinking':{'type':'disabled'}};sdk={**body,'max_tokens':512};st=c.stage_for(ctx.contract(),1,[],[],stop_writes=False);r=broker.reserve(body,[],sdk_body=sdk,stage=st);broker.received(r,{'id':str(uuid.uuid4()),'model':c.MODEL,'usage':dict(prompt_tokens=10,completion_tokens=1,total_tokens=11)})
    with self.assertRaises(Exception):broker.reserve({'messages':[],'model':'changed','max_tokens':256},[],sdk_body=sdk,stage=st)
    for malformed in ({'messages':[]},{'messages':[],'model':c.MODEL,'temperature':1},{'messages':[{'role':'user','content':'replaced'}],'model':'changed'}):
        with self.subTest(malformed=malformed):
            with self.assertRaises(Exception):broker.reserve(malformed,[],sdk_body=sdk,stage=st)
 def test_explorer_arguments_and_replay(self):
    data={'model':c.MODEL,'id':str(uuid.uuid4()),'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','tool_calls':[{'id':'x','type':'function','function':{'name':'select_experiment','arguments':'{"candidate_id":"normal","extra":1}'}}]}}]}
    with self.assertRaises(Exception):explorer.parse_selection(data,set())
    data['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{"candidate_id":"normal"}'
    with self.assertRaises(Exception):explorer.parse_selection(data,{'x'})
 def test_write_after_unknown_rejected_before_io(self):
    ctx,_=fresh();ct=ctx.contract();j=type('J',(),{'add':lambda *a,**k:None})();backend=config.ConfigLiveMemoryBackend();host=config.Host(ct,config.ProviderLedger.fixture_only('synthetic'),backend,j);host.tool_trace=[{},{},{}];host.activated=True
    with self.assertRaises(Exception):host._tool(dict(call_id='fake',name='update_config_v2',arguments={}))
    self.assertEqual(backend.version,0)

def minimal_response(*,tool=False):
 msg={'role':'assistant','content':None}
 if tool:msg['tool_calls']=[{'id':'call_'+uuid.uuid4().hex,'type':'function','function':{'name':'inspect_config','arguments':'{}'}}]
 return {'id':str(uuid.uuid4()),'object':'chat.completion','created':1,'model':c.MODEL,'choices':[{'index':0,'message':msg,'finish_reason':'tool_calls' if tool else 'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}

def ready_host(host,pid=789):
 pin=c.pinned_sdk_fields();host._ready(dict(framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=pid,python_executable_sha256=pin['python_executable_sha256'],sdk_source_sha256=c.SDK_CORE_SHA256,openai_source_sha256=pin['openai_core_sha256'],sdk_site_root_binding_sha256=pin['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=pin['python_runtime_mapping_sha256']))

def completion_body(ct):return dict(model=c.MODEL,messages=[{'role':'system','content':ct['execution']['agent_instructions']},{'role':'user','content':ct['execution']['task_prompt']}],tools=registry(),tool_choice='auto',parallel_tool_calls=False,max_tokens=512)

def response_cases():
 def changed(fn,tool=False):
  value=minimal_response(tool=tool);fn(value);return value
 return {
 'finish_length':changed(lambda d:d['choices'][0].update(finish_reason='length')),
 'finish_content_filter':changed(lambda d:d['choices'][0].update(finish_reason='content_filter')),
 'finish_null':changed(lambda d:d['choices'][0].update(finish_reason=None)),
 'finish_other':changed(lambda d:d['choices'][0].update(finish_reason='private-value')),
 'missing_index':changed(lambda d:d['choices'][0].pop('index')),
 'index_nonzero':changed(lambda d:d['choices'][0].update(index=1)),
 'index_boolean':changed(lambda d:d['choices'][0].update(index=False)),
 'choice_scalar':changed(lambda d:d.update(choices=[1])),
 'choice_unknown_field':changed(lambda d:d['choices'][0].update(new_field='private-value')),
 'choices_empty':changed(lambda d:d.update(choices=[])),
 'choices_double':changed(lambda d:d['choices'].append(copy.deepcopy(d['choices'][0]))),
 'message_scalar':changed(lambda d:d['choices'][0].update(message='private-value')),
 'message_role':changed(lambda d:d['choices'][0]['message'].update(role='user')),
 'tools_scalar':changed(lambda d:d['choices'][0]['message'].update(tool_calls='private-value')),
 'tools_falsey_object':changed(lambda d:d['choices'][0]['message'].update(tool_calls={})),
 'tools_double':changed(lambda d:d['choices'][0]['message']['tool_calls'].append(copy.deepcopy(d['choices'][0]['message']['tool_calls'][0])),True),
 'tool_index_invalid':changed(lambda d:d['choices'][0]['message']['tool_calls'][0].update(index=1),True),
 'tool_unallowed':changed(lambda d:d['choices'][0]['message']['tool_calls'][0]['function'].update(name='delete_everything'),True),
 'tool_arguments':changed(lambda d:d['choices'][0]['message']['tool_calls'][0]['function'].update(arguments='{"extra":1}'),True),
 'response_id_invalid':changed(lambda d:d.update(id='private id / invalid')),
 'model_unallowed':changed(lambda d:d.update(model='private-model')),
 'usage_missing':changed(lambda d:d['usage'].pop('total_tokens')),
 'usage_negative':changed(lambda d:d['usage'].update(prompt_tokens=-1)),
 'usage_sum':changed(lambda d:d['usage'].update(total_tokens=999)),
 'usage_output_cap':changed(lambda d:d['usage'].update(completion_tokens=257,total_tokens=267)),
 'usage_input_cap':changed(lambda d:d['usage'].update(prompt_tokens=9000,total_tokens=9002)),
 'http200_error_object':{'error':{'message':'private-value'}},
 }

class R66ShapeTests(unittest.TestCase):
 def exercise(self,value,*,expect_ok=False,transport=None):
  ctx,ledger=fresh();ct=ctx.contract();client,broker,host,j=config.assemble_host(ctx,ct,ledger,api_key='synthetic-only');ready_host(host);body=completion_body(ct)
  from runtime.runproof_runtime.effectwitness import config_live_runtime as base
  class Reply:
   status=200 if transport!='http500' else 500
   def read(self,n):return (b'x'*262145 if transport=='oversize' else b'not-json' if transport=='non_json' else c.canonical(value))[:n]
   def getheader(self,*a):return 'application/json'
  class Connection:
   calls=0
   def request(self,*a,**kw):
    Connection.calls+=1
    if transport=='timeout':raise TimeoutError()
   def getresponse(self):return Reply()
   def close(self):pass
  with patch.object(base.http.client,'HTTPSConnection',return_value=Connection()),patch.object(base.ssl,'create_default_context',return_value=None):
   if expect_ok:host._completion(body)
   else:
    with self.assertRaises(Exception):host._completion(body)
  self.assertEqual(Connection.calls,1)
  account=ledger.read();events=account['events'];shape=next(e for e in events if e['kind']=='PROVIDER_SHAPE_OBSERVED');record=broker.data['requests'][0]
  self.assertEqual(shape['provider_ticket'],record['ticket']);self.assertEqual(shape['receipt']['request_sha256'],record['request_sha256']);self.assertTrue((ctx.root/'provider-shapes'/(record['ticket']+'.json')).exists())
  if expect_ok:
   self.assertEqual(record['status'],'RECEIVED');self.assertFalse(ledger.read()['unknown']);self.assertEqual(shape['receipt']['conditions'],[])
  else:
   self.assertEqual(record['status'],'UNKNOWN');self.assertTrue(ledger.read()['unknown']);self.assertIsNone(record['usage'])
   rejected=next(e for e in events if e['kind']=='PROVIDER_PARSE_REJECTED');settled=next(e for e in events if e['kind']=='RESULT');v.wal_order(account,shape,rejected,settled)
   with self.assertRaises(Exception):ledger.reserve('sdk',run_id=ct['experiment']['run_id'])
  return ctx,ledger,host,shape['receipt']
 def test_actual_transport_parser_positive_stop_and_tool(self):
  for tool in (False,True):
   with self.subTest(tool=tool):self.exercise(minimal_response(tool=tool),expect_ok=True)
 def test_actual_transport_parser_negative_matrix(self):
  for name,value in response_cases().items():
   with self.subTest(name=name):
    _,_,_,receipt=self.exercise(value)
    if name=='finish_length':self.assertIn('CHOICE_FINISH_REASON',receipt['conditions']);self.assertEqual(receipt['shape']['choices'][0]['finish_reason'],'length')
    if name=='missing_index':self.assertIn('CHOICE_REQUIRED_FIELDS',receipt['conditions'])
    if name=='choice_unknown_field':self.assertIn('CHOICE_UNKNOWN_FIELDS',receipt['conditions'])
 def test_transport_size_json_timeout_status(self):
  for kind in ('oversize','non_json','timeout','http500'):
   with self.subTest(kind=kind):
    _,_,_,receipt=self.exercise(minimal_response(),transport=kind);self.assertEqual(receipt['conditions'],['NOT_OBSERVED']);self.assertEqual(receipt['stage'],'TRANSPORT_OR_DECODE_NOT_OBSERVED')
 def test_privacy_canary_never_persisted_or_reversibly_encoded(self):
  import base64
  canary='sk-'+uuid.uuid4().hex+uuid.uuid4().hex;value=minimal_response();value['choices'][0]['message'].update(content=canary,reasoning_content=canary);value['choices'][0][canary]=canary
  ctx,ledger,host,receipt=self.exercise(value);raw=(ledger.path/'ledger.jsonl').read_bytes()+(ctx.root/'provider-shapes/provider-1.json').read_bytes()
  for needle in (canary.encode(),base64.b64encode(canary.encode()),canary.encode().hex().encode()):self.assertNotIn(needle,raw)
  self.assertLessEqual(len(c.canonical(receipt['shape'])),config.SHAPE_MAX_BYTES)
 def test_response_and_tool_id_reuse_is_unknown(self):
  for duplicate_tool in (False,True):
   ctx,ledger=fresh();ct=ctx.contract();_,broker,host,_=config.assemble_host(ctx,ct,ledger,api_key='synthetic-only');ready_host(host);first=minimal_response(tool=True);second=copy.deepcopy(first)
   if duplicate_tool:second['id']=str(uuid.uuid4())
   host.business=config.ConfigLiveMemoryBackend();body=completion_body(ct)
   with patch.object(config.ConfigLiveHost,'_provider_request',autospec=True,side_effect=[first,second]):
    host._completion(body);call=first['choices'][0]['message']['tool_calls'][0]
    result=host._tool(dict(call_id=call['id'],name='inspect_config',arguments={}))
    body['messages'] += [first['choices'][0]['message'],dict(role='tool',tool_call_id=call['id'],content=c.canonical(result).decode())]
    with self.assertRaises(Exception):host._completion(body)
   self.assertTrue(ledger.read()['unknown']);self.assertEqual(broker.data['requests'][-1]['status'],'UNKNOWN')
 def test_shape_width_is_bounded(self):
  value=minimal_response();value['choices']=[value['choices'][0]]*100;value['usage']['prompt_tokens']=10**100;shape=config.safe_shape(value);self.assertEqual(len(shape['choices']),2);self.assertLess(len(c.canonical(shape)),8192);self.assertIsNone(shape['usage']['fields']['prompt_tokens']['value'])

class R66ClockTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  with patch('time.monotonic_ns',return_value=10**12):cls.payload=synthetic_payload()
 def test_equal_clock_full_session_keeps_raw_clock(self):
  p=copy.deepcopy(self.payload);self.assertEqual({f['event']['monotonic_ns'] for f in p['ledger']},{10**12});self.assertEqual(v.verify_payload(p)['status'],'PASS')
 def test_equal_clock_actual_rejected_transport(self):
  with patch('time.monotonic_ns',return_value=10**12):
   ctx,ledger,host,receipt=R66ShapeTests().exercise(response_cases()['tool_unallowed'])
  account=ledger.read();selected=[f for f in ledger.frames if f['event']['kind'] in ('PROVIDER_SHAPE_OBSERVED','PROVIDER_PARSE_REJECTED','RESULT')]
  self.assertEqual([f['seq'] for f in selected],sorted({f['seq'] for f in selected}));self.assertEqual({f['event']['monotonic_ns'] for f in selected},{10**12})
 def test_strictly_increasing_clock_uses_same_wal_order(self):
  p=copy.deepcopy(self.payload)
  for i,f in enumerate(p['ledger']):f['event']['monotonic_ns']+=i
  # Domain event mirrors retain their original raw clocks; order helper is tested
  # against replayed physical frames, independently of scene reanchoring.
  rechain(p);a=c.replay(p['ledger'],p['context']);v.wal_order(a,a['events'][0],a['events'][-1])
 def test_equal_clock_reverse_rechain_rejected(self):
  p=copy.deepcopy(self.payload);mutations()['equal_clock_shape_parse_reordered'](p)
  with self.assertRaises(Exception):v.verify_payload(p)
 def test_missing_replayed_cross_ticket_and_clock_reverse(self):
  for name in ('shape_absent','accepted_parse_replayed','accepted_parse_cross_ticket','raw_clock_decreasing','selection_after_jvm'):
   with self.subTest(name=name):
    p=copy.deepcopy(self.payload);mutations()[name](p)
    with self.assertRaises(Exception):v.verify_payload(p)
 def test_detached_or_duplicate_event_identity_rejected(self):
  a=c.replay(self.payload['ledger'],self.payload['context']);first,last=a['events'][0],a['events'][-1]
  for other in (copy.deepcopy(first),last):
   with self.assertRaises(Exception):v.wal_order(a,other,last)

if __name__=='__main__':unittest.main()


class R66V5Tests(unittest.TestCase):
 def test_parser_differential_and_terminal_range(self):
  from runtime.runproof_runtime.effectwitness import pge_r66_response_v5 as parser
  from runtime.runproof_runtime.effectwitness.config_live_runtime import _validate_provider_response as original
  ctx,ledger=fresh();ct=ctx.contract();body=completion_body(ct);_,broker,host,_=config.assemble_host(ctx,ct,ledger,api_key='synthetic');ready_host(host)
  req=copy.deepcopy(body);req.update(max_tokens=256,thinking={'type':'disabled'});st=host.request_policy(body,[])
  rec=broker.reserve(req,[],sdk_body=body,stage=st)
  values=[minimal_response(),minimal_response(tool=True)]+list(response_cases().values())
  for output in (0,128,256):
   value=minimal_response();value['usage'].update(completion_tokens=output,total_tokens=10+output);values.append(value)
  def outcome(fn,value):
   try:return ('PASS',fn(value),value)
   except Exception as exc:return (getattr(exc,'code',type(exc).__name__),value)
  for value in values:
   with self.subTest(value=c.digest(value)):
    self.assertEqual(outcome(original,copy.deepcopy(value)),outcome(lambda d:parser.validate(d,authorization=rec,account=ledger.read()),copy.deepcopy(value)))
  terminal=copy.deepcopy(rec);terminal.update(attempt=5,output_cap=512)
  trace=[dict(call_id='id'+str(i),name=name,result_sha256='0'*64) for i,name in enumerate(list(c.TOOLS)+['inspect_config'])]
  terminal['binding']['stage']=c.stage_for(ct,5,trace,[dict(call_id=x['call_id'],result_sha256=x['result_sha256']) for x in trace],stop_writes=True)
  terminal['binding']['outbound_max_tokens']=512
  account=copy.deepcopy(ledger.read());account['tickets'][terminal['ticket']].update({k:terminal[k] for k in ('request_sha256','binding','input_upper','output_cap','token_upper')})
  for output in (257,300,512,513):
   value=minimal_response();value['usage'].update(completion_tokens=output,total_tokens=10+output)
   if output<=512:self.assertEqual(parser.validate(copy.deepcopy(value),authorization=terminal,account=account)[0]['usage'],value['usage'])
   else:
    with self.assertRaises(Exception):parser.validate(value,authorization=terminal,account=account)
   with self.assertRaises(Exception):parser.validate(copy.deepcopy(value),authorization=rec,account=ledger.read())
  for finish in ('length','content_filter','aborted',None):
   for output in (128,256,300,512):
    value=minimal_response();value['choices'][0]['finish_reason']=finish;value['usage'].update(completion_tokens=output,total_tokens=10+output)
    with self.assertRaises(Exception):parser.validate(value,authorization=terminal,account=account)
 def test_child_exact_diff_and_guards(self):
  import runpy
  old=(c.ROOT/'runtime/runproof_runtime/effectwitness/config_live_external.py').read_bytes()
  new=(c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r66_sdk_child_v5.py').read_bytes()
  self.assertEqual(new,old.replace(b'model_settings={"max_tokens": 256,',b'model_settings={"max_tokens": 512,'))
  ctx,_=fresh();mod=runpy.run_path(str(c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r66_sdk_child_v5.py'))
  denied=[];guard=mod['_guard_events'](45002,ctx.root,ctx.root/'sdk',[],c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r66_sdk_child_v5.py',denied,[])
  for event,args in [('socket.connect',(None,('127.0.0.1',45003))),('socket.getaddrinfo',('invalid.example',)),('open',(str(ctx.root.parent/'outside'),'r',0)),('subprocess.Popen',('x',)),('socket.bind',(None,('127.0.0.1',0)))]:
   with self.subTest(event=event):
    with self.assertRaises(PermissionError):guard(event,args)
 def test_real_child_wire_usage_300_and_512(self):
  from runtime.runproof_runtime.effectwitness import config_live_runtime as base
  import importlib.util
  fixed=Path(os.environ.get('RPF66_FIXED_SDK_PUBLIC_ROOT',str(c.ROOT)))
  source=fixed/'spikes/rpf-55/probe.py'
  self.assertEqual(hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),c.sources()['spikes/rpf-55/probe.py'])
  other=fixed/'spikes/rpf-53/probe.py';self.assertEqual(hashlib.sha256(other.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),c.sources()['spikes/rpf-53/probe.py'])
  spec=importlib.util.spec_from_file_location('rpf66_free_fixed_sdk_helpers',source);helpers=importlib.util.module_from_spec(spec);before_path=list(sys.path)
  try:spec.loader.exec_module(helpers)
  finally:sys.path[:]=before_path
  for candidate,output in zip(c.CANDIDATES,(300,512)):
   ctx,ledger=fresh();ct=ctx.contract(1,candidate);run=ct['experiment']['run_id'];journal=config.Journal(ledger,run);client=FakeHttp(ctx,ct,'synthetic',journal,ledger);client.initial_state_valid()
   broker=config.BrokerLedger(ledger,run);host=config.Host(ct,broker,config.ConfigLiveBusiness(ct,client),journal,api_key='synthetic');folder=ctx.folder(ct);folder.mkdir(parents=True);seen=[]
   class Reply:
    status=200
    def getheader(self,*a):return 'application/json'
    def read(self,n):return self.raw[:n]
   class Connection:
    def request(self,method,path,raw,headers):
     body=c.strict_json(raw);record=broker.data['requests'][-1];self.reply=Reply();self.reply.raw=b''
     selfcheck=hashlib.sha256(raw).hexdigest();assert selfcheck==record['request_sha256']==record['binding']['outbound_request_sha256'];assert ledger.read()['tickets'][record['ticket']]['request_sha256']==selfcheck
     seen.append((body['max_tokens'],record['binding']['sdk_requested_max_tokens']))
     data=host._fixture_response(body);data['id']=str(uuid.uuid4());data['model']=c.MODEL
     count=output if data['choices'][0]['finish_reason']=='stop' else 30
     data['usage']=dict(prompt_tokens=500,completion_tokens=count,total_tokens=500+count);self.reply.raw=c.canonical(data)
    def getresponse(self):return self.reply
    def close(self):pass
   with patch.object(c,'helpers',return_value=(helpers,helpers.old)),patch.object(base.http.client,'HTTPSConnection',side_effect=lambda *a,**k:Connection()),patch.object(base.ssl,'create_default_context',return_value=None):
    result=config.run_sdk(ctx,ct,ledger,c.pinned_sdk_fields(),folder,host)
   self.assertEqual(seen,[(256,512)]*(3 if candidate==c.CANDIDATES[0] else 4)+[(512,512)])
   v.verify_sdk(result,host.tool_trace,host.provider_responses);self.assertEqual(host.provider_responses[-1]['usage']['completion_tokens'],output)
   self.assertEqual(broker.data['requests'][-1]['output_cap'],512);self.assertFalse(ledger.read()['unknown'])
   ledger.read();self.assertTrue(all(r['status']=='RECEIVED' for r in broker.data['requests']))
   with self.assertRaises(Exception):host.request_policy(completion_body(ct),[dict(call_id=x['call_id'],result_sha256=x['result_sha256']) for x in host.tool_trace])
 def test_pre_send_input_bound_and_sixth_slot(self):
  ctx,ledger=fresh();ct=ctx.contract();_,broker,host,_=config.assemble_host(ctx,ct,ledger,api_key='synthetic');ready_host(host);body=completion_body(ct);body['messages'][1]['content']+='x'*4000
  with patch.object(config.ConfigLiveHost,'_provider_request') as wire:
   with self.assertRaises(Exception):host._completion(body)
   wire.assert_not_called()
  self.assertEqual(ledger.read()['counts']['provider'],0)
  with self.assertRaises(Exception):c.stage_for(ct,6,[],[],stop_writes=True)
