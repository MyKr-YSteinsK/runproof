"""Pure synthetic ABI, source, WAL, domain oracle and semantic attack controls."""
import copy,hashlib,os,subprocess,sys,unittest,uuid
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_port_context as c,pge_portability_config as config,pge_portability_order as order,pge_portability_session as session,pge_portability_verify as v
from runtime.runproof_runtime.effectwitness.pge_domain_port import classify,select
from runtime.runproof_runtime.effectwitness.contracts import ENV_REVISION,READER_ID
from runtime.runproof_runtime.effectwitness.config_live_contracts import TOOL_ARGUMENT_KEYS

def registry():return [{'type':'function','function':{'name':n,'description':c.TOOL_HELP[n],'parameters':{'type':'object','properties':{k:{'type':'integer' if k=='expected_version' else 'string'} for k in TOOL_ARGUMENT_KEYS[n]},'required':list(TOOL_ARGUMENT_KEYS[n]),'additionalProperties':False},'strict':True}} for n in c.TOOLS]
def drive(host,ct,pid):
 pin=c.pinned_sdk_fields();ready={'framework':'pydantic-ai-slim','version':'2.57.0','openai_version':'3.35.1','pid':pid,'python_executable_sha256':pin['python_executable_sha256'],'sdk_source_sha256':c.SDK_CORE_SHA256,'openai_source_sha256':pin['openai_core_sha256'],'sdk_site_root_binding_sha256':pin['sdk_site_root_binding_sha256'],'python_runtime_mapping_sha256':pin['python_runtime_mapping_sha256']};host._ready(ready);messages=[{'role':'system','content':ct['execution']['agent_instructions']},{'role':'user','content':ct['execution']['task_prompt']}]
 for _ in range(5 if ct['experiment']['fault_plan']['enabled'] else 4):
  data=host._completion({'model':'rpf53-fixture-only','messages':copy.deepcopy(messages),'tools':registry(),'tool_choice':'auto','parallel_tool_calls':False,'max_tokens':256});msg=data['choices'][0]['message'];messages.append(msg)
  for call in msg.get('tool_calls',[]):
   result=host._tool({'call_id':call['id'],'name':call['function']['name'],'arguments':c.strict_json(call['function']['arguments'].encode())});messages.append({'role':'tool','tool_call_id':call['id'],'content':c.canonical(result).decode()})
 report={'framework':'pydantic-ai-slim','version':'2.57.0','openai_version':'3.35.1','python_executable_sha256':pin['python_executable_sha256'],'sdk_source_sha256':c.SDK_CORE_SHA256,'openai_source_sha256':pin['openai_core_sha256'],'status':'COMPLETED','pid':pid,'guard_denials':[],'provider_key_present':False,'business_key_present':False,'final_text_persisted':False,'tool_calls':len(host.tool_trace),'tool_callbacks':len(host.tool_trace),'requests':len(host.provider_responses),'input_tokens':0,'output_tokens':0}
 return {'popen_pid':pid,'ready':ready,'report':report,'returncode':0,'stderr_bytes':0}
class FakeHttp(config.Http):
 def request(self,kind,*,reconcile=False):
  method,path,body=config._http_contract(self.effect,kind);c.require(method!='POST' or not self.stop_writes,'WRITE_AFTER_UNKNOWN');kw={'domain':c.DOMAINS[1],'run_id':self.contracts['experiment']['run_id'],'http_seq':len(self.observations)+1,'operation':kind,'method':method};ticket=self.total.reserve('http',**kw);post=self.total.reserve('post',**kw) if method=='POST' else None;self.journal.add('HTTP_RESERVED',**{k:kw[k] for k in ('http_seq','operation','method')})
  def item(version):return {**{k:self.effect[k] for k in ('app','env','key')},'version':version,'value':'rpf53-v'+str(version),'description':None,'updatedAt':'2026-10-22T00:00:00Z'}
  def history(version):
   row=item(version);row['createdAt']=row.pop('updatedAt');row.update(action='UPSERT',operator=None,reason=None);return row
  absent=kind=='initial_current' or kind=='inspect_config' and len(self.observations)==2;data=[] if kind=='initial_history' else None if absent else [history(2),history(1)] if kind.endswith('history') else [item(2)] if kind=='final_list' else item(1 if kind=='create_config_v1' else 2);status=404 if absent else 200;response={'code':4041 if absent else 0,'message':'synthetic','data':data,'traceId':None};o={'seq':len(self.observations)+1,'kind':kind,'method':method,'path':path,'request':body,'status':status,'content_type':'application/json','response':response,'response_body_sha256':c.digest(response),'elapsed_ms':0,'transport_error':None};self.observations.append(o);self.total.settle(ticket,status=status,response_sha256=o['response_body_sha256'],transport_error=None)
  if post:self.total.settle(post,status=status,unknown=False)
  self.journal.add('HTTP_COMPLETED',http_seq=o['seq'],status=status,response_sha256=o['response_body_sha256']);return o

def fake_order(self,ctx,ct,ledger):
 f,x=ct['effect'],ct['experiment'];setup=ledger.reserve('sqlite_setup',domain=c.DOMAINS[0],run_id=x['run_id']);ledger.settle(setup,status='CREATED');env={'owner':x['owner'],'run_id':x['run_id'],'environment_id':x['environment_id'],'environment_revision':ENV_REVISION,'reset_generation':0};initial={'order_id':f['order_id'],'paid_minor':2500,'refunded_minor':0,'currency':'CNY','status':'PAID','revision':0};before={'reader_id':READER_ID,'reader_version':'1','source_id':f['authority_id'],'environment':env,'order':initial,'receipts':[]};receipt={k:f[k] for k in ('order_id','operation_id','amount_minor','currency')};receipt.update(receipt_id='receipt-'+c.digest({'environment':x['environment_id'],'operation_id':f['operation_id']})[:24],status='COMMITTED',committed_revision=1);after=copy.deepcopy(before);after['order'].update(refunded_minor=2500,status='REFUNDED',revision=1);after['receipts']=[receipt];args={k:f[k] for k in ('order_id','operation_id','amount_minor')};ticket=ledger.reserve('sqlite_refund',domain=c.DOMAINS[0],run_id=x['run_id'],arguments_sha256=c.digest(args));ledger.settle(ticket,status='COMMITTED',receipt_id=receipt['receipt_id']);result={k:receipt[k] for k in ('status','operation_id','receipt_id','committed_revision')}
 return {'backend':'SYNTHETIC_TEST_ONLY','source_kind':'SYNTHETIC_TEST_ONLY','executor_pid':123,'before':{'data':before,'sha256':c.digest(before)},'after':{'data':after,'sha256':c.digest(after)},'inspect':{'order_id':f['order_id'],'status':'PAID','revision':0},'tool_call':{'name':'refund_order','arguments':args,'result':result},'fault':dict.fromkeys(('planned','triggered','observed','agent_exposed'),False),'database_sha256':'a'*64,'cleanup':{'connections_closed':True,'exclusive_lock_probe':True,'database_retained_for_evidence':True}}
def fake_config(self,ctx,ct,ledger):
 run=ct['experiment']['run_id'];jvm=ledger.reserve('jvm',domain=c.DOMAINS[1],run_id=run);ledger.settle(jvm,popen_pid=456,status='STARTED');health=ledger.reserve('health',domain=c.DOMAINS[1],run_id=run);ledger.settle(health,status=200,response_sha256=c.digest({'status':'UP'}));sdk_t=ledger.reserve('sdk',domain=c.DOMAINS[1],run_id=run);j=config.Journal(ledger,run);http=FakeHttp(ctx,ct,'synthetic-key',j,ledger);http.initial_state_valid();host=config.Host(ct,config.ConfigLiveBusiness(ct,http),j);sdk=drive(host,ct,789);ledger.settle(sdk_t,popen_pid=789,status='COMPLETED');http.stop_writes=True;http.final_readback(reconcile=True);http.request('final_list')
 return {'backend':'SYNTHETIC_TEST_ONLY','source_kind':'SYNTHETIC_TEST_ONLY','http':http.observations,'events':j.events,'tool_trace':host.tool_trace,'completions':host.provider_responses,'visibility':host.visible_contract_checks,'sdk':sdk,'environment':{'jar_sha256':c.SOURCE_JAR_SHA256,'jar_bytes':c.SOURCE_JAR_BYTES,'java_pid':456,'listener_owned':True,'jar_command_verified':True,'health':[{'status':200,'body':{'status':'UP'}}],'cleanup':{'java_exited':True,'java_port_closed':True,'sdk_exited':True,'host_port_closed':True,'local_key_released':True}},'original_success':host.original_success,'host_failure':None}
def synthetic_payload(mode='suppressed'):
 ctx=c.make_context(uuid.uuid4().hex[:16],(8001,8002),(8003,8004),synthetic=True,mode=mode);ctx.root.mkdir(parents=True);ledger=c.Ledger(ctx,ctx.root/'account',create=True);meta=ledger.reserve('metadata');ledger.settle(meta,status='PASS');ct=ctx.public()['cold_contract'];cold_t=ledger.reserve('cold',domain=c.DOMAINS[1],run_id=ct['experiment']['run_id']);j=config.Journal(ledger,ct['experiment']['run_id']);host=config.Host(ct,config.ConfigLiveMemoryBackend(),j);sdk=drive(host,ct,987);ledger.settle(cold_t,popen_pid=987,status='COMPLETED');cold={'status':'PASS','source_kind':'FIXTURE_SCRIPTED','contract':ct,'sources':c.sources(),'verifier':v.identity(),'sdk':sdk,'tool_trace':host.tool_trace,'completions':host.provider_responses,'events':j.events,'checks':{'synthetic':True}}
 with patch.object(order.OrderPort,'execute',fake_order),patch.object(config.ConfigPort,'execute',fake_config),patch.object(order.OrderPort,'cleanup',lambda self,ctx,ct,e:e['cleanup']),patch.object(config.ConfigPort,'cleanup',lambda self,ctx,ct,e:e['environment']['cleanup']):rows=session.SharedSession(ctx,ledger).run()
 return {'source_kind':'SYNTHETIC_TEST_ONLY','context':ctx.public(),'rows':rows,'ledger':ledger.frames,'cold':cold,'boundaries':c.BOUNDARIES}
def rechain(p):
 previous=None
 for i,f in enumerate(p['ledger']):f.update(seq=i,previous=previous);f['sha256']=c.digest({k:v for k,v in f.items() if k!='sha256'});previous=c.digest(f)
def mutations():
 def authority(p,key,value):s=p['rows'][0]['evidence']['after'];s['data']['receipts'][0][key]=value;s['sha256']=c.digest(s['data'])
 def stale(p):s=p['rows'][0]['evidence']['after'];s['data']['order']['revision']=0;s['sha256']=c.digest(s['data'])
 def omit(p):p['ledger']=[f for f in p['ledger'] if f['event'].get('ticket')!='http-1'];rechain(p)
 def reverse(p):p['ledger'].reverse();rechain(p)
 def role(p):p['source_kind']='BOTH_REAL_CONTROLLED' if p['source_kind']=='SYNTHETIC_TEST_ONLY' else 'SYNTHETIC_TEST_ONLY'
 return {'role_upgrade_or_downgrade':role,'wrong_operation_receipt':lambda p:authority(p,'operation_id','old-operation'),'stale_revision':stale,'missing_authority':lambda p:p['rows'][0]['evidence']['after'].update(data={}),'wrong_owner':lambda p:p['context'].update(owner='rpf-63'),'run_reuse':lambda p:p['rows'][1].update(contract=copy.deepcopy(p['rows'][0]['contract'])),'negative_budget':lambda p:p['context']['limits'].update(http=-1),'wrong_port_source':lambda p:p['rows'][0]['dispatch'].update(port_file_sha256='0'*64),'unknown_sdk':lambda p:p['rows'][1]['evidence']['sdk']['report'].update(status='REPORT_UNAVAILABLE'),'cleanup_incomplete':lambda p:p['rows'][1]['cleanup'].update(java_exited=False),'false_fault':lambda p:p['rows'][0]['evidence']['fault'].update(triggered=True),'false_explorer':lambda p:p['boundaries'].update(explorer='REAL_PROVIDER'),'false_target':lambda p:p['rows'][1]['evidence'].update(source_kind='REAL_PROVIDER_TARGET'),'false_cross_domain_gain':lambda p:p['rows'][1]['feedback'].update(cross_domain_information_gain=1),'budget_omission':omit,'wal_reversed':reverse,'missing_readback':lambda p:p['rows'][1]['evidence']['http'].pop(),'tool_call_id':lambda p:p['rows'][1]['evidence']['completions'][1]['tool_returns'][0].update(call_id='fake'),'source_missing':lambda p:p['context']['sources'].pop(c.NEW_FILES[0]),'cold_pid':lambda p:p['cold']['sdk'].update(popen_pid=42),'duplicate_post':lambda p:p['rows'][1]['evidence']['http'].append(copy.deepcopy(p['rows'][1]['evidence']['http'][4])),'false_config_authority':lambda p:p['rows'][1]['verdict'].update(authority='EXTERNAL_DATABASE_AUDIT')}
def controls(payload,folder):
 folder.mkdir(parents=True,exist_ok=False)
 def cli(raw,anchor):
  path=folder/'input.json';path.write_bytes(raw);args=[sys.executable,'-X','utf8','-B','-m','runtime.runproof_runtime.effectwitness.pge_portability_verify',str(path)]
  if anchor is not None:args+=['--sha256',anchor]
  env={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH') if k in os.environ};return subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30).returncode
 raw=c.canonical(v.seal(payload));codes=[cli(raw,hashlib.sha256(raw).hexdigest()),cli(raw,None),cli(raw,'0'*64)];c.require(codes==[0,2,3],'CLI_CODES');result={}
 for name,mutate in mutations().items():
  p=copy.deepcopy(payload);mutate(p);raw=c.canonical(v.seal(p));result[name]=cli(raw,hashlib.sha256(raw).hexdigest())
 c.require(set(result.values())=={3},'TAMPER_ACCEPTED');return {'correct_missing_wrong':codes,'rehashed_semantic_controls':result}
class PortabilityTests(unittest.TestCase):
 def test_shared_entry_three_config_modes(self):
  for mode in ('normal','inhibited','suppressed'):
   with self.subTest(mode=mode):self.assertEqual(v.verify_payload(synthetic_payload(mode))['status'],'PASS')
 def test_twenty_two_reanchored_semantic_attacks(self):
  p=synthetic_payload()
  for name,mutate in mutations().items():
   with self.subTest(name=name):
    bad=copy.deepcopy(p);mutate(bad);raw=c.canonical(v.seal(bad))
    with self.assertRaises(Exception):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
 def test_taxonomy_matrix(self):
  no=dict.fromkeys(('planned','triggered','observed','agent_exposed'),False);satisfied='CONTRACT_SATISFIED_IN_RUN'
  self.assertEqual(classify(satisfied,no)['state'],'NORMAL');self.assertEqual(classify(satisfied,no,authority=False)['state'],'AUTHORITY_UNAVAILABLE');self.assertEqual(classify('INCONCLUSIVE',no)['state'],'INCONCLUSIVE');self.assertEqual(classify('VIOLATION_CONFIRMED',no)['state'],'VIOLATION_CONFIRMED');self.assertEqual(classify(satisfied,no|{'planned':True})['state'],'FAULT_NOT_TRIGGERED');self.assertEqual(classify(satisfied,dict.fromkeys(no,True),unknown=True,reconciled=True)['state'],'UNKNOWN_OUTCOME')
  with self.assertRaises(Exception):classify(satisfied,no|{'triggered':True})
 def test_immutable_context_and_scope(self):
  ctx=c.make_context(uuid.uuid4().hex[:16],(8001,8002),(8003,8004),synthetic=True);p=ctx.public();p['limits']['provider']=99;self.assertEqual(ctx.public()['limits']['provider'],0)
  with self.assertRaises(Exception):ctx.root=c.ROOT
  with self.assertRaises(Exception):ctx.scope(c.ROOT/'outside')
  with self.assertRaises(Exception):c.TaskContext(ctx.root,bytearray(ctx.frozen))
  with patch.object(type(ctx.root),'is_symlink',return_value=True):
   with self.assertRaises(Exception):ctx.scope(ctx.root/'scope-probe')
  with self.assertRaises(Exception):select('os.system')
 def test_duplicate_refund_unknown_write_restart_torn_wal(self):
  ctx=c.make_context(uuid.uuid4().hex[:16],(8001,8002),(8003,8004),synthetic=True);ctx.root.mkdir(parents=True);ledger=c.Ledger(ctx,ctx.root/'account',create=True);ticket=ledger.reserve('sqlite_refund');ledger.settle(ticket,status='COMMITTED')
  with self.assertRaises(Exception):ledger.reserve('sqlite_refund')
  with self.assertRaises(Exception):ledger.reserve('provider')
  ticket=ledger.reserve('post',method='POST');ledger.settle(ticket,status=None,unknown=True);second=c.Ledger(ctx,ledger.path)
  with self.assertRaises(Exception):second.reserve('post',method='POST')
  self.assertTrue(second.reserve('http',method='GET'))
  with (ledger.path/'ledger.jsonl').open('ab') as f:f.write(b'{')
  with self.assertRaises(Exception):second.read()
 def test_host_provider_denial_and_repeat_write(self):
  ct=c.contract(c.DOMAINS[1],'a'*16,'b'*64);host=config.Host(ct,config.ConfigLiveMemoryBackend(),type('J',(),{'add':lambda *a,**k:None})())
  with self.assertRaises(Exception):host._provider_request({})
  host.tool_trace=[{}, {}, {}];host.activated=True
  with self.assertRaises(Exception):host._tool({'name':'update_config_v2'})
if __name__=='__main__':unittest.main()
