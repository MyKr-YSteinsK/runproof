"""RPF-63 offline four-path protocol and reanchored semantic attacks."""
import copy,hashlib,os,subprocess,sys,unittest,uuid
from runtime.runproof_runtime.effectwitness import pge_dual_contracts as c,pge_dual_config_port as b,pge_dual_session as session,pge_dual_verify as v
def registry():
    from runtime.runproof_runtime.effectwitness.config_live_contracts import TOOL_ARGUMENT_KEYS
    return [{'type':'function','function':{'name':n,'description':c.TOOL_HELP[n],'parameters':{'type':'object','properties':{k:{'type':'integer' if k=='expected_version' else 'string'} for k in TOOL_ARGUMENT_KEYS[n]},'required':list(TOOL_ARGUMENT_KEYS[n]),'additionalProperties':False},'strict':True}} for n in c.TOOLS]
class FakeHttp(b.BusinessHttp):
    def request(self,kind,*,reconcile=False):
        method,path,body=b._http_contract(self.effect,kind);c.require(method!='POST' or not self.stop_writes,'WRITE_AFTER_UNKNOWN')
        ticket=self.total.reserve('http',run_id=self.contracts['experiment']['run_id'],http_seq=len(self.observations)+1,operation=kind,method=method)
        if method=='POST':self.total.reserve('post',operation=kind,run_id=self.contracts['experiment']['run_id'])
        self.journal.add('HTTP_RESERVED',http_seq=len(self.observations)+1,method=method,operation=kind)
        def item(version):return {**{k:self.effect[k] for k in ('app','env','key')},'version':version,'value':'rpf53-v'+str(version),'description':None,'updatedAt':'2026-10-21T00:00:00Z'}
        initial=kind in ('initial_current','initial_history') or (kind=='inspect_config' and len(self.observations)==2)
        def history(version):
            row=item(version);row['createdAt']=row.pop('updatedAt');row.update(action='UPSERT',operator=None,reason=None);return row
        data=[] if kind=='initial_history' else None if initial else [history(2),history(1)] if kind.endswith('history') else [item(2)] if kind=='final_list' else item(1 if kind=='create_config_v1' else 2)
        status=404 if initial and kind!='initial_history' else 200;response={'code':4041 if status==404 else 0,'message':'synthetic','data':data,'traceId':None}
        o={'seq':len(self.observations)+1,'kind':kind,'method':method,'path':path,'request':body,'status':status,'content_type':'application/json','response':response,'response_body_sha256':c.digest(response),'elapsed_ms':0,'transport_error':None}
        self.observations.append(o);self.total.settle(ticket,status=status,response_sha256=o['response_body_sha256'],transport_error=None);self.journal.add('HTTP_COMPLETED',http_seq=o['seq'],status=status,response_sha256=o['response_body_sha256']);return o

def replay_scene(ct,total,index):
 account=session.RoundAccount(total,index);run=ct['experiment']['run_id'];account.reserve('trial',run_id=run)
 jvm=account.reserve('jvm',run_id=run);account.settle(jvm,popen_pid=5000+index);health=account.reserve('health');account.settle(health,status=200,response_sha256=c.digest({'status':'UP'}));sdk_ticket=account.reserve('sdk',run_id=run)
 journal=b.Journal(account,run);client=FakeHttp(ct,'synthetic-key',journal,account,9999999999);client.initial_state_valid()
 # Exercise the exact Host protocol with fixture completions, then meter replayed shapes separately.
 class ReplayHost(b.CapabilityHost):
  def _fixture_response(self,request):
   data=super()._fixture_response(request);data['id']='synthetic-response-'+str(index)+'-'+str(self.fixture_index);return data
 host=ReplayHost(ct,b.ProviderLedger.fixture_only(run),b.ConfigLiveBusiness(ct,client),journal,fixture=True)
 pin=c.pinned_sdk_fields();pid=6000+index;ready={'framework':'pydantic-ai-slim','version':'2.57.0','openai_version':'3.35.1','pid':pid,'python_executable_sha256':pin['python_executable_sha256'],'sdk_source_sha256':c.SDK_CORE_SHA256,'openai_source_sha256':pin['openai_core_sha256'],'sdk_site_root_binding_sha256':pin['sdk_site_root_binding_sha256'],'python_runtime_mapping_sha256':pin['python_runtime_mapping_sha256']}
 host._ready(ready);messages=[{'role':'system','content':ct['execution']['agent_instructions']},{'role':'user','content':ct['execution']['task_prompt']}];broker=b.BrokerLedger(account,run)
 count=5 if ct['experiment']['fault_plan']['enabled'] else 4
 for n in range(count):
  body={'model':'rpf53-fixture-only','messages':copy.deepcopy(messages),'tools':registry(),'tool_choice':'auto','parallel_tool_calls':False,'max_tokens':256,'thinking':{'type':'disabled'}}
  data=host._completion(body);comp=host.provider_responses[-1];record=broker.reserve(body,comp['tool_returns']);record['agent_contract_visibility']=host.visible_contract_checks[-1];broker.checkpoint()
  rid=data['id'];record['tool_call_ids']=[x['call_id'] for x in comp['tool_calls']];record['returned_tool_ids']=[x['call_id'] for x in comp['tool_returns']];record['tool_schema_sha256']=host.tool_schema_sha256
  data['usage']={'prompt_tokens':500,'completion_tokens':50,'total_tokens':550};comp['usage']=data['usage'];comp['model']=c.MODEL;broker.received(record,{'usage':data['usage'],'id':rid,'model':c.MODEL});broker.checkpoint()
  msg=data['choices'][0]['message'];messages.append(msg)
  for call in msg.get('tool_calls',[]):
   result=host._tool({'call_id':call['id'],'name':call['function']['name'],'arguments':c.strict_json(call['function']['arguments'].encode())});messages.append({'role':'tool','tool_call_id':call['id'],'content':c.canonical(result).decode()})
 client.stop_writes=True;client.final_readback(reconcile=True);client.request('final_list')
 report={'status':'COMPLETED','pid':pid,'guard_denials':[],'provider_key_present':False,'business_key_present':False,'final_text_persisted':False,'tool_calls':len(host.tool_trace),'tool_callbacks':len(host.tool_trace),'requests':count,'input_tokens':500*count,'output_tokens':50*count}
 sdk={'popen_pid':pid,'ready':ready,'report':report,'returncode':0,'stderr_bytes':0};account.settle(sdk_ticket,popen_pid=pid,status='COMPLETED')
 env={'source_level':'REAL_JAVA_H2_LOCAL_SIMULATION','authority':'SAME_SERVICE_READ_ONLY_HTTP','java_pid':5000+index,'jar_sha256':c.SOURCE_JAR_SHA256,'jar_bytes':c.SOURCE_JAR_BYTES,'listener_owned':True,'jar_command_verified':True,'health':[{'status':200,'body':{'status':'UP'}}],'cleanup':dict.fromkeys(('java_exited','java_port_closed','sdk_exited','host_port_closed','host_thread_stopped','local_key_released'),True)}
 return {'contracts':ct,'http':client.observations,'events':journal.events,'tool_trace':host.tool_trace,'completions':host.provider_responses,'visibility':host.visible_contract_checks,'sdk':sdk,'environment':env,'requests':broker.data['requests'],'original_success':host.original_success,'host_failure':None}
def synthetic_payload(choices=(c.CANDIDATES[1],c.CANDIDATES[0])):
 folder=c.WORK/'tests'/uuid.uuid4().hex;folder.mkdir(parents=True);total=c.TaskLedger(folder/'account',create=True);meta=total.reserve('metadata');total.settle(meta,status='PASS');total.token_pool();cold_ticket=total.reserve('cold',run_id='synthetic-cold');total.settle(cold_ticket,popen_pid=7000,status='COMPLETED');total.reserve('session')
 rounds=[]
 for index in (1,2):
  suffix='63'+uuid.uuid4().hex[:16];rounds.append({candidate:c.contract(suffix,8000+index*2,8001+index*2,c.digest(c.sources()),candidate,fixture=True) for candidate in c.CANDIDATES})
 plan=c.plan('rpf63-session-'+uuid.uuid4().hex[:16],rounds,synthetic=True);rows=[]
 for index,candidate in enumerate(choices,1):
  ct=rounds[index-1][candidate];body=session.body_for(rows);meter=session.ExplorerMeter(total,index,ct['experiment']['run_id']);ticket=meter.reserve_request('EXPLORER',index,body)
  selection={'id':'synthetic-selection-'+str(index),'type':'function','function':{'name':'select_experiment','arguments':c.canonical({'candidate_id':candidate}).decode()}}
  data={'id':'synthetic-explorer-'+str(index),'model':c.MODEL,'usage':{'prompt_tokens':200,'completion_tokens':30,'total_tokens':230},'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[selection]}}]};meter.received(ticket,data)
  obs={'shape':session.safe_response_shape(data),'attempt':ticket,'request_sha256':c.digest(body),'http_status':200,'received_monotonic_ns':0}
  total.append('CHOICE_FROZEN',round=index,selection_sha256=c.digest(selection),candidate_id=candidate,contract_sha256=c.digest(ct),provider_ticket=ticket)
  capture=replay_scene(ct,total,index);verdict=v.verify_scene(ct,capture,c.replay(total.frames),index,real=False)
  total.append('DOMAIN_VERIFIED',round=index,run_id=ct['experiment']['run_id'],capture_sha256=c.digest(capture),verdict_sha256=c.digest(verdict));fb=session.feedback(ct,capture,verdict,[r['feedback'] for r in rows]);total.append('FEEDBACK_FROZEN',round=index,tool_call_id=selection['id'],feedback_sha256=c.digest(fb))
  rows.append({'round':index,'selection':selection,'candidate_id':candidate,'contract':ct,'body':body,'observation':obs,'provider_ticket':ticket,'capture':capture,'verdict':verdict,'feedback':fb,'role_source':'SYNTHETIC_TEST_ONLY'})
 total.append('SESSION_COMPLETED',session_id=plan['session_id'],rows_sha256=c.digest(rows))
 cold={'status':'PASS','source_kind':'FIXTURE_SCRIPTED','sources':c.sources(),'verifier':v.identity(),'checks':{'synthetic':True},'sdk':copy.deepcopy(rows[0]['capture']['sdk']),'tool_trace':copy.deepcopy(next(r['capture']['tool_trace'] for r in rows if len(r['capture']['tool_trace'])==4)) if c.CANDIDATES[1] in choices else [None,None,{'result':c.UNKNOWN},None],'completions':[{}]*5,'events':[]}
 cold['sdk']['popen_pid']=cold['sdk']['ready']['pid']=cold['sdk']['report']['pid']=7000;cold['sdk']['report'].update(tool_calls=4,tool_callbacks=4,requests=5)
 return {'source_kind':'SYNTHETIC_TEST_ONLY','plan':plan,'rows':rows,'ledger':total.frames,'cold':cold,'boundaries':c.BOUNDARIES}
def rechain(p):
 previous=None
 for i,f in enumerate(p['ledger']):f.update(seq=i,previous=previous);f['sha256']=c.digest({k:v for k,v in f.items() if k!='sha256'});previous=c.digest(f)
def mutations():
 def omit(p):
  p['ledger']=[f for f in p['ledger'] if f['event'].get('ticket')!='http-1'];rechain(p)
 def role(p):p['source_kind']='REAL_EXPLORER_REAL_TARGET' if p['source_kind']=='SYNTHETIC_TEST_ONLY' else 'SYNTHETIC_TEST_ONLY'
 return {'role_upgrade_or_downgrade':role,'target_impersonation':lambda p:p['rows'][0]['capture']['completions'][0]['tool_calls'][0].update(name='select_experiment'),'tool_call':lambda p:p['rows'][0]['capture']['tool_trace'][0].update(call_id='wrong'),'usage_omission':lambda p:p['rows'][0]['capture']['requests'].pop(),'duplicate_post':lambda p:p['rows'][0]['capture']['http'].append(copy.deepcopy(p['rows'][0]['capture']['http'][4])),'wrong_domain':lambda p:p['rows'][0]['contract']['experiment'].update(domain='order-refund'),'cross_round':lambda p:p['rows'][1].update(capture=copy.deepcopy(p['rows'][0]['capture'])),'fake_fault':lambda p:p['rows'][0]['verdict']['fault'].update(triggered=not p['rows'][0]['verdict']['fault']['triggered']),'old_run':lambda p:p['rows'][0]['capture']['events'][0].update(run_id='rpf57-old'),'future_feedback':lambda p:p['rows'][0].update(body=copy.deepcopy(p['rows'][1]['body'])),'unknown_usage':lambda p:p['rows'][0]['capture']['requests'][0].update(status='RESERVED_USAGE_UNKNOWN'),'cleanup':lambda p:p['rows'][0]['capture']['environment']['cleanup'].update(java_exited=False),'source':lambda p:p['plan']['source_files'].update({c.NEW_FILES[0]:'0'*64}),'price':lambda p:p['plan']['price'].update(input_cny_per_million_bound=0),'wal_reverse':lambda p:p['ledger'].reverse(),'budget_omission':omit,'feedback_call_id':lambda p:p['rows'][1]['body']['messages'][-1].update(tool_call_id='fake'),'false_reconcile':lambda p:p['rows'][0]['capture']['http'][-2].update(kind='update_config_v2'),'cold_pid':lambda p:p['cold']['sdk'].update(popen_pid=42),'authority':lambda p:p['rows'][0]['capture']['environment'].update(authority='MODEL_SELF_REPORT'),'missing_readback':lambda p:p['rows'][0]['capture']['http'].pop()}
def controls(payload,folder):
 folder.mkdir(parents=True,exist_ok=False)
 def cli(raw,anchor):
  path=folder/'input.json';path.write_bytes(raw);args=[sys.executable,'-X','utf8','-B','-m','runtime.runproof_runtime.effectwitness.pge_dual_verify',str(path)]
  if anchor is not None:args+=['--sha256',anchor]
  env={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH') if k in os.environ};return subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30).returncode
 raw=c.canonical(v.seal(payload));codes=[cli(raw,hashlib.sha256(raw).hexdigest()),cli(raw,None),cli(raw,'0'*64)];c.require(codes==[0,2,3],'CLI_CODES');results={}
 for name,mutate in mutations().items():
  p=copy.deepcopy(payload);mutate(p);raw=c.canonical(v.seal(p));results[name]=cli(raw,hashlib.sha256(raw).hexdigest())
 c.require(set(results.values())=={3},'TAMPER_ACCEPTED');return {'correct_missing_wrong':codes,'rehashed_semantic_controls':results}
class DualTests(unittest.TestCase):
 def test_four_paths(self):
  for a in c.CANDIDATES:
   for b0 in c.CANDIDATES:
    with self.subTest(choices=(a,b0)):self.assertEqual(v.verify_payload(synthetic_payload((a,b0)))['status'],'PASS')
 def test_twenty_one_reanchored_attacks(self):
  p=synthetic_payload()
  for name,mutation in mutations().items():
   with self.subTest(name=name):
    bad=copy.deepcopy(p);mutation(bad);raw=c.canonical(v.seal(bad))
    with self.assertRaises(Exception):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
 def test_unknown_usage_and_restart(self):
  folder=c.WORK/'tests'/uuid.uuid4().hex;folder.mkdir(parents=True);t=c.TaskLedger(folder/'account',create=True);t.token_pool();a=session.RoundAccount(t,1);b0=b.BrokerLedger(a,'synthetic-test');b0.reserve({'messages':[]},[])
  with self.assertRaises(Exception):b0.reserve({'messages':[]},[])
  second=c.TaskLedger(t.path)
  with self.assertRaises(Exception):session.ExplorerMeter(second,2,'synthetic2').reserve_request('EXPLORER',2,session.body_for([]))
  with self.assertRaises(Exception):second.token_pool()
  with (t.path/'ledger.jsonl').open('ab') as f:f.write(b'{')
  with self.assertRaises(Exception):second.read()
 def test_scope_lock_budget_and_invalid_selection(self):
  with self.assertRaises(Exception):c.scoped(c.ROOT/'outside')
  folder=c.WORK/'tests'/uuid.uuid4().hex;folder.mkdir(parents=True);t=c.TaskLedger(folder/'account',create=True);(t.path/'mutation.lock').touch()
  with self.assertRaises(Exception):t.reserve('cold')
  with self.assertRaises(Exception):session.parse_selection({'id':'x','model':c.MODEL,'choices':[{'finish_reason':'stop','message':{'role':'assistant','tool_calls':[]}}]},set())
  self.assertEqual(2*sum(c.TARGET_CAPS)+2*c.EXPLORER_CAP,30000)
 def test_host_blocks_write_after_unknown(self):
  ct=c.contract('63'+'a'*16,9001,9002,c.digest(c.sources()),c.CANDIDATES[1],fixture=True);j=b.Journal(None,ct['experiment']['run_id']);host=b.CapabilityHost(ct,b.ProviderLedger.fixture_only(j.run_id),b.ConfigLiveMemoryBackend(),j,fixture=True)
  host.tool_trace=[{'name':n} for n in c.TOOLS];host.activated=True
  with self.assertRaises(Exception):host._tool({'call_id':'malicious-repeat','name':'update_config_v2','arguments':{'expected_version':1,'value':'rpf53-v2'}})
  self.assertEqual(j.events[-1]['kind'],'TOOL_REJECTED');self.assertEqual(len(host.tool_trace),3)
 def test_unknown_mutation_stops_writes_but_allows_readback(self):
  folder=c.WORK/'tests'/uuid.uuid4().hex;folder.mkdir(parents=True);t=c.TaskLedger(folder/'account',create=True);t.token_pool();ticket=t.reserve('post',operation='update_config_v2');t.settle(ticket,status=None,unknown=True)
  with self.assertRaises(Exception):t.reserve('post',operation='update_config_v2')
  with self.assertRaises(Exception):session.ExplorerMeter(t,1,'synthetic').reserve_request('EXPLORER',1,session.body_for([]))
  self.assertTrue(t.reserve('http',method='GET',operation='reconcile_current'))
if __name__=='__main__':unittest.main()
