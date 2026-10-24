"""Pure ABI controls; dynamic parity is the separately bounded probe."""
import copy,unittest
from runtime.runproof_runtime.effectwitness import pge_r69_abi as a,pge_r69_capsule as c,pge_r69_budget as b,pge_r69_guard_audit as g,pge_r69_compat as compat
def attacks():
 original=c.create('config-java-http','EXPLORER','r69-'+'a'*16).public();rows=[]
 def add(label,fn,code):
  p=copy.deepcopy(original);fn(p);rows.append((label,p,code))
 for k,v,code in [('schema','other','SOURCE_KIND_VERSION'),('source_kind','REAL_EXPLORER_REAL_TARGET_CROSS_DOMAIN','SOURCE_KIND_VERSION'),('owner_id','rpf-68','OWNER_SCOPE'),('run_id','old','OWNER_RUN'),('environment_id','old','OWNER_SCOPE'),('reset_generation',1,'OWNER_SCOPE'),('domain','external','DOMAIN_ALLOWLIST'),('role','ROOT','ROLE_ALLOWLIST'),('workspace','.local/rpf-68-rev-3','OWNER_SCOPE'),('oracle_identity','MODEL','ORACLE_IDENTITY'),('native_legacy_verifier_version','fake','CERTIFICATE_AUTHORITY'),('original_certificate_raw_sha256','0'*64,'CERTIFICATE_AUTHORITY'),('observed_vs_declared','REAL','CERTIFICATE_AUTHORITY'),('allowed_tool_names',['refund_order'],'CAPABILITIES')]:add(k,lambda p,k=k,v=v:p.update({k:v}),code)
 for k,v in [('base','0'*40),('branch','main'),('source_digest','0'*64),('native_source_digest','0'*64)]:add('identity-'+k,lambda p,k=k,v=v:p['identity'].update({k:v}),'SOURCE_IDENTITY')
 for key in ('raw','lf'):add('source-'+key,lambda p,k=key:p['identity']['source_map'][c.NEW[0]].update({k:'0'*64}),'SOURCE_IDENTITY')
 for k,v in [('can_issue_verdict',True),('can_sign',True),('can_release',True),('network',['example.com']),('provider_key',True),('process_spawn',True),('write',['refund_once']),('read',['arbitrary_file']),('oracle_readback',False)]:add('cap-'+k,lambda p,k=k,v=v:p['capabilities'].update({k:v}),'CAPABILITIES')
 for k,v in [('version','old'),('reachable_tokens',600001),('global_tokens',600001),('max_slot',160001),('provider_calls_limit',12),('sdk_cumulative',{'config-java-http':35000,'order-sqlite':35000}),('refundable',True),('real_provider_allowed',True),('caps',{'EXPLORER':[160000]}),('currency_guard',{})]:add('budget-'+k,lambda p,k=k,v=v:p['budget_policy'].update({k:v}),'BUDGET_POLICY')
 for k,v in [('child_raw','0'*64),('guard_raw','0'*64),('network','ANY'),('file','ANY'),('provider_key',True),('process',True),('sdk',{})]:add('guard-'+k,lambda p,k=k,v=v:p['guard_policy'].update({k:v}),'GUARD_IDENTITY')
 add('role-upgrade',lambda p:p.update(role='TARGET'),'CAPABILITIES')
 add('float-slot',lambda p:p['budget_policy']['caps']['EXPLORER'].__setitem__(0,32000.0),'BUDGET_POLICY')
 add('numeric-false',lambda p:p['capabilities'].update(can_release=0),'CAPABILITIES')
 add('missing-field',lambda p:p.pop('domain'),'CAPSULE_FIELDS');add('unknown-field',lambda p:p.update(extra=True),'CAPSULE_FIELDS')
 return rows
class ABITests(unittest.TestCase):
 def test_capsule_roundtrip(self):
  for d in ('config-java-http','order-sqlite'):
   for r in ('EXPLORER','TARGET'):
    x=c.create(d,r,'r69-'+'a'*16);self.assertEqual(a.CapabilityCapsule(x.frozen).raw_sha256,x.raw_sha256)
 def test_reanchored_attacks(self):
  rows=attacks();self.assertGreaterEqual(len(rows),45)
  for label,p,code in rows:
   with self.subTest(label=label),self.assertRaisesRegex(ValueError,'^'+code+'$'):a.CapabilityCapsule(a.canonical(p))
 def test_scope_refuses_old_and_foreign(self):
  x=c.OwnerScope('r69-'+'a'*16)
  for p in (c.ROOT/'.local/rpf-68-rev-3/file',c.ROOT/'AGENTS.md'):
   with self.assertRaisesRegex(ValueError,'OWNER_PATH'):x.path(p)
 def test_budget_parity(self):
  for d in ('config-java-http','order-sqlite'):
   for r in ('EXPLORER','TARGET'):
    caps=b.policy()['caps']['EXPLORER' if r=='EXPLORER' else d]
    for i,cap in enumerate(caps,1):
     out=128 if r=='EXPLORER' else 512 if i>=(4 if d=='config-java-http' else 3) else 256
     self.assertEqual(b.decide(d,r,i,cap-out,out)['slot_cap'],cap)
     with self.assertRaisesRegex(ValueError,'PRE_SEND_INPUT_BOUND'):b.decide(d,r,i,cap-out+1,out)
 def test_permanent_unknown_and_zero(self):
  for kw,code in [(dict(recycle=True),'PERMANENT_TICKET'),(dict(unknown=True,write=True),'UNKNOWN_STOP_WRITES'),(dict(provider=1),'ZERO_PROVIDER'),(dict(usage=1),'ZERO_PROVIDER'),(dict(finish='length'),'RESPONSE_POLICY'),(dict(refusal=True),'RESPONSE_POLICY')]:
   with self.assertRaisesRegex(ValueError,code):b.ledger_policy(**kw)
 def test_writes_and_readonly_reconcile(self):
  for d,names,name in [('config-java-http',['inspect_config','create_config_v1','update_config_v2'],'update_config_v2'),('order-sqlite',['inspect_order','refund_order'],'refund_order')]:
   with self.assertRaisesRegex(ValueError,'UNKNOWN_READ_ONLY'):b.write_policy(d,names,name,True)
 def test_guard_differential(self):self.assertEqual(g.audit()['r67_r68'],'byte-identical')
 def test_history_identity(self):
  for p,_,sha in compat.HISTORY:self.assertEqual(compat.historical_identity(p)['raw_sha256'],sha)
 def test_third_domain_adapter_rejected(self):
  with self.assertRaisesRegex(ValueError,'DOMAIN_ALLOWLIST'):compat.adapter('external')
 def test_owner_context_no_native_root(self):
  ctx=compat.Context(c.OwnerScope('r69-'+'b'*16),(29001,29002,29003));self.assertTrue(ctx.root.is_relative_to(c.ROOT/'.local/rpf-69'));self.assertEqual(ctx.public()['owner'],'rpf-69')

 def test_original_guard_denials(self):
  import importlib,sys
  for stem in ('pge_r67_order_child','pge_r68_sdk_child'):
   module=importlib.import_module('runtime.runproof_runtime.effectwitness.'+stem);root=c.ROOT/'.local/rpf-69';denied=[];files=[];hook=module._guard_events(23456,root,root,[__import__('pathlib').Path(sys.base_prefix)],c.ROOT/('runtime/runproof_runtime/effectwitness/'+stem+'.py'),denied,files)
   for event,args in [('socket.connect',(None,('example.com',443))),('socket.getaddrinfo',('example.com',)),('subprocess.Popen',()),('open',(str(c.ROOT/'AGENTS.md'),'w',0))]:
    with self.assertRaises(PermissionError):hook(event,args)
