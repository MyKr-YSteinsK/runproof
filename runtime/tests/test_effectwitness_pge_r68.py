"""Real Java/H2 and SQLite with fixed SDK fixture models; semantic reanchored attacks."""
import copy,secrets,sys,subprocess,unittest,ast,importlib.util
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_r68_context as c,pge_r68_session as s,pge_r68_verify as v
from runtime.runproof_runtime.effectwitness.pge_r68_budget import Ledger
from runtime.runproof_runtime.effectwitness.pge_r68_driver import parse,shape

def relink(frames):
 previous=None
 for i,f in enumerate(frames):f.update(seq=i,previous=previous);f['sha256']=c.digest({k:x for k,x in f.items() if k!='sha256'});previous=c.digest(f)

def synchronize(p):
 # Re-anchor dependent envelope, WAL and domain receipts, retaining semantic attacks.
 events=[f['event'] for f in p['frames']]
 for index,row in enumerate(p['rounds'],1):
  if 'evidence' not in row:continue
  e=row['evidence'];ct=e['contract']
  for event in events:
   if event.get('round')!=index:continue
   if event['kind']=='CHOICE':event.update(choice=copy.deepcopy(row['choice']),choice_sha256=c.digest(row['choice']))
   if event['kind']=='DOMAIN_VERIFIED':event.update(evidence_sha256=c.digest(e),contract_sha256=c.digest(ct),oracle=e['business']['oracle'])
  row['feedback']['source_evidence_sha256']=c.digest(e)
  for event in events:
   if event['kind']=='FEEDBACK_FROZEN' and event.get('round')==index:event.update(feedback=copy.deepcopy(row['feedback']),feedback_sha256=c.digest(row['feedback']))
  req=[z for z in events if z['kind']=='MODEL_REQUEST' and z.get('role')=='TARGET' and not z.get('cold') and z.get('round')==index];res=[z for z in events if z['kind']=='MODEL_RESPONSE' and z.get('role')=='TARGET' and not z.get('cold') and z.get('round')==index]
  for target,q,r in zip(e['sdk']['requests'],req,res):
   q['request']=copy.deepcopy(target['request']);r['response']=copy.deepcopy(target['response'])
   if q['ticket']:
    next(z for z in events if z['kind']=='RESERVE' and z['ticket']==q['ticket'])['request']=copy.deepcopy(q['request']);next(z for z in events if z['kind']=='RESULT' and z['ticket']==q['ticket'])['response']=copy.deepcopy(r['response'])
  for event,t in zip([z for z in events if z['kind']=='TOOL_RETURN' and z.get('round')==index and not z.get('cold')][-len(e['trace']):],e['trace']):event['row']=copy.deepcopy(t)
 for event in events:
  if event['kind']=='SHAPE':event['receipt_sha256']=c.digest(event['receipt'])
 relink(p['frames'])

def controls(original):
 rows=[]
 def add(label,fn,*,sync=True):
  candidate=copy.deepcopy(original);p=candidate['payload'];fn(p)
  if sync:synchronize(p)
  else:
   if label in ('wal-parse-before-shape','wal-double-resource'):
    for frame in p['frames']:frame['event']['clock']=p['frames'][0]['event']['clock']
   relink(p['frames'])
  rows.append((label,v.seal(p)))
 def context(key,value):return lambda p:p['context'].update({key:value})
 for key,value in [('owner','rpf-66'),('abi','rpf66-config-pge-session-v5'),('base','0'*40),('branch','main'),('source_kind',c.REAL if original['payload']['context']['source_kind']==c.SYNTHETIC else c.SYNTHETIC),('workspace','.local/rpf-67-rev-4'),('session_id','rpf68-'+'0'*16),('source_digest','0'*64)]:add('context-'+key,context(key,value))
 add('source-current-raw',lambda p:p['context']['sources'][c.NEW[0]].update(raw='0'*64))
 add('source-lf-history-relabel',lambda p:p['context']['sources'][c.NEW[0]].update(lf='0'*64))
 for key,value in [('provider',12),('sqlite_refund',2),('config_post',3),('jvm',2),('trial',3),('sdk',3),('cold',3),('authority_read',9)]:add('pool-'+key,lambda p,k=key,z=value:p['context']['limits'].update({k:z}))
 for key,value in [('causality','PROVEN'),('issuer','ESTABLISHED'),('L2',True),('release','AUTHORIZED')]:add('boundary-'+key,lambda p,k=key,z=value:p['boundaries'].update({k:z}))
 add('swap-domains',lambda p:p['rounds'].reverse(),sync=False)
 add('config-tag-as-order',lambda p:p['rounds'][0]['choice'].update(domain=c.DOMAINS[1]))
 add('second-round-as-first',lambda p:p['rounds'][1]['choice'].update(round=1))
 add('order-candidate-in-config',lambda p:p['rounds'][0]['choice'].update(candidate_id=c.CANDIDATES[1][0]))
 add('config-candidate-in-order',lambda p:p['rounds'][1]['choice'].update(candidate_id=c.CANDIDATES[0][0]))
 add('feedback-foreign-facts',lambda p:p['rounds'][0]['feedback'].update(facts=['refunded2500']))
 add('feedback-unverified-verdict',lambda p:p['rounds'][0]['feedback'].update(verdict='MODEL_SAYS_COMMITTED'))
 add('feedback-source-contract',lambda p:p['rounds'][0]['feedback'].update(source_contract_sha256='0'*64))
 add('feedback-source-event',lambda p:p['rounds'][0]['feedback'].update(source_event_seq=0))
 add('feedback-choice-id',lambda p:p['rounds'][0]['feedback'].update(choice_tool_call_id='foreign-id'))
 add('feedback-domain-upgrade',lambda p:p['rounds'][0]['feedback'].update(domain=c.DOMAINS[1]))
 add('explorer2-feedback-sha',lambda p:p['rounds'][1]['choice']['request'].update(prior_feedback_sha256='0'*64))
 add('explorer2-tool-id',lambda p:p['rounds'][1]['choice']['request'].update(prior_tool_call_id='foreign-tool'))
 add('explorer2-messages-hash',lambda p:p['rounds'][1]['choice']['request'].update(messages_sha256='0'*64))
 add('explorer2-input-truncated',lambda p:p['rounds'][1]['choice']['request'].update(input_upper=1))
 add('original-selection-id',lambda p:p['rounds'][1]['choice']['selection'].update(id=p['rounds'][0]['choice']['selection']['id']))
 add('choice-response-role',lambda p:p['rounds'][0]['choice']['response']['call'].update(name='refund_order'))
 add('config-as-order-backend',lambda p:p['rounds'][0]['evidence']['business'].update(backend='REAL_LOCAL_SQLITE'))
 add('order-as-config-backend',lambda p:p['rounds'][1]['evidence']['business'].update(backend='REAL_JAVA_H2_HTTP'))
 for index in (0,1):
  for k in ('planned','triggered','observed','agent_exposed'):add('fault-'+str(index)+'-'+k,lambda p,i=index,key=k:p['rounds'][i]['evidence']['fault'].update({key:not p['rounds'][i]['evidence']['fault'][key]}))
  for k,value in [('status','SDK_ERROR'),('requests',99),('tool_callbacks',99),('input_tokens',99999),('output_tokens',99999),('provider_key_present',True),('business_key_present',True),('guard_denials',['DENIED']),('final_text_persisted',True)]:add('sdk-'+str(index)+'-'+k,lambda p,i=index,key=k,z=value:p['rounds'][i]['evidence']['sdk']['report'].update({key:z}))
  add('sdk-'+str(index)+'-child-source',lambda p,i=index:p['rounds'][i]['evidence']['sdk'].update(child_sha256='0'*64))
  add('sdk-'+str(index)+'-python-pin',lambda p,i=index:p['rounds'][i]['evidence']['sdk']['ready'].update(python_executable_sha256='0'*64))
  add('sdk-'+str(index)+'-openai-pin',lambda p,i=index:p['rounds'][i]['evidence']['sdk']['ready'].update(openai_source_sha256='0'*64))
  for key in ('process_gone','thread_gone','port_closed','key_reference_released'):add('sdk-'+str(index)+'-cleanup-'+key,lambda p,i=index,k=key:p['rounds'][i]['evidence']['sdk']['cleanup'].update({k:False}))
 for key,value in [('input_upper',99999),('previous_prompt',None),('suffix_bytes',1),('framing_guard',0),('output_cap',256),('slot_cap',4800),('ordinal',6),('tool_returns',[]),('canonical_bytes',1),('configuration_sha256','0'*64),('schema_sha256','0'*64)]:add('order-terminal-'+key,lambda p,k=key,z=value:p['rounds'][1]['evidence']['sdk']['requests'][-1]['request'].update({k:z}))
 for label,fn in [('length',lambda p:p.update(finish_reason='length')),('unknown-usage',lambda p:p['usage'].update(prompt_tokens=None)),('usage-overflow',lambda p:p['usage'].update(completion_tokens=99999)),('reused-id',lambda p:p.update(response_id='fixture-explorer-response-1')),('wrong-model',lambda p:p.update(model='unknown-model')),('extra-tool-at-stop',lambda p:p.update(call=dict(call_id='extra',name='refund_order',arguments={})))]:add('order-response-'+label,lambda p,f=fn:f(p['rounds'][1]['evidence']['sdk']['requests'][-1]['response']))
 for key,value in [('command_verified',False),('listener_owned',False),('jar_sha256','0'*64),('jar_bytes',1)]:add('java-'+key,lambda p,k=key,z=value:p['rounds'][0]['evidence']['business']['environment'].update({k:z}))
 add('config-missing-history',lambda p:p['rounds'][0]['evidence']['business']['after'][1]['response'].update(data=[]))
 add('config-wrong-effect',lambda p:p['rounds'][0]['evidence']['contract']['effect'].update(required_value='unauthorized'))
 add('order-wrong-amount',lambda p:p['rounds'][1]['evidence']['contract']['effect'].update(amount_minor=2499))
 add('order-wrong-operation',lambda p:p['rounds'][1]['evidence']['trace'][1]['arguments'].update(operation_id='foreign'))
 add('order-double-refund',lambda p:p['rounds'][1]['evidence']['trace'].append(copy.deepcopy(p['rounds'][1]['evidence']['trace'][1])))
 add('order-missing-receipt',lambda p:p['rounds'][1]['evidence']['business']['after']['data'].update(receipts=[]))
 add('order-forged-reader',lambda p:p['rounds'][1]['evidence']['business']['after']['data'].update(reader_id='tool-dict'))
 add('order-cross-owner',lambda p:p['rounds'][1]['evidence']['business']['after']['data']['environment'].update(owner='rpf-67-rev-4'))
 add('order-foreign-authority',lambda p:p['rounds'][1]['evidence']['business']['after']['data'].update(source_id='foreign'))
 add('oracle-model-authority',lambda p:p['rounds'][0]['evidence']['business']['oracle'].update(contract_outcome='MODEL_CONFIRMED'))
 def event(kind,fn):return lambda p:fn(next(f['event'] for f in p['frames'] if f['event']['kind']==kind))
 add('wal-session-foreign',event('OWNER',lambda e:e.update(session_id='foreign')),sync=False)
 add('wal-explorer-role-as-target',event('MODEL_REQUEST',lambda e:e.update(role='TARGET')),sync=False)
 add('wal-first-domain-as-second',event('MODEL_REQUEST',lambda e:e.update(domain=c.DOMAINS[1])),sync=False)
 add('wal-delete-first-domain-verified',lambda p:p['frames'].pop(next(i for i,f in enumerate(p['frames']) if f['event']['kind']=='DOMAIN_VERIFIED')),sync=False)
 add('wal-double-resource',lambda p:p['frames'].append(copy.deepcopy(next(f for f in p['frames'] if f['event']['kind']=='RESERVE'))),sync=False)
 add('wal-parse-before-shape',lambda p:p['frames'].insert(1,p['frames'].pop(next(i for i,f in enumerate(p['frames']) if f['event']['kind']=='PARSED'))),sync=False)
 for domain,index,ordinal,value in [(c.DOMAINS[0],0,3,2400),(c.DOMAINS[0],0,4,2800),(c.DOMAINS[1],1,2,4600),(c.DOMAINS[1],1,3,4300)]:add('v2-cap-'+domain+'-'+str(ordinal+1),lambda p,i=index,n=ordinal,z=value:p['rounds'][i]['evidence']['sdk']['requests'][n]['request'].update(slot_cap=z))
 for key,value in [('version','rpf68-slot-budget-v1'),('role','EXPLORER'),('domain',c.DOMAINS[0]),('round',1),('ordinal',3),('reachable_tokens',35000),('global_tokens',40000)]:
  def scope_attack(p,k=key,z=value):
   q=p['rounds'][1]['evidence']['sdk']['requests'][-1]['request'];q['slot_scope'][k]=z;q['slot_contract_sha256']=c.digest(q['slot_scope'])
  add('v2-reanchored-scope-'+key,scope_attack)
 for key,value in [('slot_contract_sha256','0'*64),('output_cap',128),('stage','PRE_COMMIT'),('input_upper',True),('previous_prompt',99999),('request_sha256','not-a-sha'),('framing_guard',511),('tool_returns',[])]:add('v2-proof-'+key,lambda p,k=key,z=value:p['rounds'][0]['evidence']['sdk']['requests'][-1]['request'].update({k:z}))
 for key,value in [('reachable_tokens',30400),('global_tokens',35001),('budget_version','rpf68-slot-budget-v1')]:add('v2-context-'+key,context(key,value))
 return rows

class R68Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.lost=s.synthetic();cls.normal=s.synthetic(candidates=(c.CANDIDATES[0][0],c.CANDIDATES[1][0]));cls.mixed=[s.synthetic(candidates=(c.CANDIDATES[0][i],c.CANDIDATES[1][1-i])) for i in (0,1)]
 def test_four_real_business_candidates_with_fixed_sdk(self):
  for w in (self.lost,self.normal,*self.mixed):
   r=v.verify(w);self.assertEqual(r['provider'],0);self.assertTrue(r['cross_domain_feedback']);self.assertEqual(len(w['payload']['rounds']),2)
 def test_semantic_reanchored_controls(self):
  rows=controls(self.lost);self.assertGreaterEqual(len(rows),138)
  for label,obj in rows:
   with self.subTest(label=label):
    with self.assertRaises(Exception):v.verify(obj)
 def test_original_guards_preserved_and_negative(self):
  path=c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py';original=c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r67_order_child.py';a=path.read_text();b=original.read_text();self.assertEqual(a[a.index('def _is_link'):a.index('def main():')],b[b.index('def _is_link'):b.index('def main():')]);spec=importlib.util.spec_from_file_location('r68_guard',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);root=c.ROOT/'.local/rpf-68-rev-2';deny=[];files=[];guard=m._guard_events(23456,root,root,[__import__('pathlib').Path(sys.base_prefix)],path,deny,files)
  for event,args in [('socket.connect',(None,('example.com',443))),('socket.getaddrinfo',('example.com',)),('subprocess.Popen',()),('open',(str(c.ROOT/'AGENTS.md'),'w',0))]:
   with self.assertRaises(PermissionError):guard(event,args)
 def test_foreign_path_and_context(self):
  p=self.lost['payload']['context'];ctx=c.Context(c.ROOT/p['workspace'],c.canonical(p))
  with self.assertRaisesRegex(ValueError,'TASK_PATH_SCOPE'):ctx.scope(c.ROOT/'.local/rpf-66/private')
  with self.assertRaises(ValueError):s.SharedSession(ctx,object())
 def test_strict_provider_nonempty_content_and_rejection(self):
  from runtime.runproof_runtime.effectwitness.pge_r68_driver import fixture_response
  ct=self.lost['payload']['rounds'][1]['evidence']['contract'];base=fixture_response(ct,1,'inspect_order');base['choices'][0]['message']['content']='Narrative is never authority.';self.assertIsNotNone(parse(base,256,c.TOOLS[c.DOMAINS[1]])['call'])
  for fn in [lambda d:d['choices'][0].update(finish_reason='length'),lambda d:d['choices'][0]['message'].update(reasoning_content='x'),lambda d:d['choices'][0]['message'].update(refusal='x'),lambda d:d['choices'][0]['message'].update(tool_calls={}),lambda d:d['choices'][0]['message']['tool_calls'].append(copy.deepcopy(d['choices'][0]['message']['tool_calls'][0])),lambda d:d['usage'].update(total_tokens=0)]:
   x=copy.deepcopy(base);fn(x)
   with self.assertRaises(Exception):parse(x,256,c.TOOLS[c.DOMAINS[1]])

 def refusal_context(self):
  ctx=c.make(synthetic=True);ctx.root.mkdir(parents=True);l=Ledger(ctx,create=True);scope=dict(domain=c.DOMAINS[0],round=1,role='EXPLORER',cold=False);q=dict(ordinal=1,request_sha256='a'*64,input_upper=5000,canonical_bytes=5000,previous_prompt=None,output_cap=128,slot_cap=2500);q['slot_scope']=c.slot_scope(c.DOMAINS[0],1,'EXPLORER',1);q['slot_contract_sha256']=c.digest(q['slot_scope']);return ctx,l,scope,dict(scope=scope,request=q,reason='INPUT_BOUND',provider_reserved=False,network_sent=False)
 def test_presend_durable_refusal_reanchored(self):
  ctx,l,scope,r=self.refusal_context();l.receipt('PRE_SEND_REJECTED','initial-reject',r,**scope);a=l.read();self.assertTrue(a['blocked']);self.assertFalse(a['unknown']);self.assertEqual(a['counts']['provider'],0)
  with self.assertRaisesRegex(ValueError,'STOP_WRITES_PROVIDER'):l.reserve('sqlite_refund')
  for key,value in [('ordinal',2),('slot_cap',5000),('input_upper',1),('canonical_bytes',1)]:
   frames=copy.deepcopy(l.frames);e=frames[-1]['event'];e['receipt']['request'][key]=value;e['receipt_sha256']=c.digest(e['receipt']);relink(frames)
   with self.subTest(key=key):
    with self.assertRaises(ValueError):__import__('runtime.runproof_runtime.effectwitness.pge_r68_budget',fromlist=['replay']).replay(frames,ctx.public())
 def test_receipt_before_wal_crash_is_permanent(self):
  ctx,l,scope,r=self.refusal_context();original=l.append
  def crash(kind,**data):
   if kind=='PRE_SEND_REJECTED':raise OSError('SIMULATED_CRASH')
   return original(kind,**data)
  with patch.object(l,'append',side_effect=crash):
   with self.assertRaises(OSError):l.receipt('PRE_SEND_REJECTED','orphan',r,**scope)
  with self.assertRaisesRegex(ValueError,'TORN_RECEIPT'):Ledger(ctx)
  self.assertTrue((ctx.root/'receipts/orphan.json').exists())
 def test_wal_receipt_missing_is_permanent(self):
  ctx,l,scope,r=self.refusal_context();l.receipt('PRE_SEND_REJECTED','initial-reject',r,**scope);original=c.Path.glob
  def missing(path,pattern):return iter(()) if path==ctx.root/'receipts' else original(path,pattern)
  with patch.object(c.Path,'glob',missing):
   with self.assertRaisesRegex(ValueError,'TORN_RECEIPT'):Ledger(ctx)
  self.assertTrue((ctx.root/'receipts/initial-reject.json').exists())

 def test_no_direct_provider_or_business_without_admission(self):
  from runtime.runproof_runtime.effectwitness.pge_r68_driver import exchange
  ctx=c.make(synthetic=True);ctx.root.mkdir(parents=True);l=Ledger(ctx,create=True);ct=ctx.contract(1,c.CANDIDATES[0][0])
  with patch('runtime.runproof_runtime.effectwitness.pge_r68_driver.https') as network:
   with self.assertRaisesRegex(ValueError,'REAL_ADMISSION_REQUIRED'):exchange(ctx,l,ct,'TARGET',1,{}, {},key='not-a-secret')
   with self.assertRaisesRegex(ValueError,'REAL_ADMISSION_REQUIRED'):s.SharedSession(ctx,l).execute(c.DOMAINS[0],ct,s.ConfigPort())
   network.assert_not_called()
  self.assertEqual(l.read()['counts']['provider'],0);self.assertFalse(l.read()['unknown']);self.assertFalse(any(f['event']['kind']=='PORT_ENTERED' for f in l.frames))

 def test_v2_reachable_table_and_identity(self):
  self.assertEqual(c.REACHABLE_TOKENS,34100);self.assertEqual(c.GLOBAL_TOKENS,35000);self.assertEqual(c.OWNER,'rpf-68-rev-2');self.assertEqual(c.ABI,'rpf68-shared-real-cross-domain-v2');self.assertIn('spikes/rpf-68/rev-2/probe.py',c.NEW)
 def test_v2_production_slot_boundaries(self):
  from runtime.runproof_runtime.effectwitness.pge_r68_driver import validate_request
  rows=[(i+1,row['evidence']['contract'],q['request']) for i,row in enumerate(self.lost['payload']['rounds']) for q in row['evidence']['sdk']['requests']]
  for index,ct,base in rows:
   for delta in (-1,0,1):
    q=copy.deepcopy(base);q['input_upper']=q['slot_cap']-q['output_cap']+delta
    with self.subTest(domain=ct['experiment']['domain'],ordinal=q['ordinal'],delta=delta):self.assertEqual(validate_request(ct,'TARGET',q),delta<=0)
  for row in self.lost['payload']['rounds']:
   ct=row['evidence']['contract']
   for delta in (-1,0,1):
    q=copy.deepcopy(row['choice']['request']);q['input_upper']=2500-128+delta;self.assertEqual(validate_request(ct,'EXPLORER',q),delta<=0)
 def test_v2_legacy_counterexample_arithmetic_is_not_worst_case(self):
  self.assertEqual(490+1192+512+512,2706);self.assertGreater(2706,2400);self.assertLessEqual(2706,c.CAPS[c.DOMAINS[0]][3]);self.assertEqual(sum(c.CAPS[c.DOMAINS[0]]),16700)
