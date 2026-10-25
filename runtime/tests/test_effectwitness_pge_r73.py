"""Pure ABI/admission/state tests. SDK execution belongs to bounded probe runs."""
from dataclasses import FrozenInstanceError
import copy
from pathlib import Path
import secrets
import subprocess
import unittest
from runtime.runproof_runtime.effectwitness import pge_r73_contracts as c
from runtime.runproof_runtime.effectwitness.pge_r73_launch_contract import LaunchRequest,LaunchReceipt,env_summary,lifecycle_action
from runtime.runproof_runtime.effectwitness.pge_r73_budget_view import BudgetView,CAPS
from runtime.runproof_runtime.effectwitness.pge_r73_domain_adapters import DomainAdapter,TOOLS
from runtime.runproof_runtime.effectwitness.pge_r73_launch_factory import LaunchFactory,ACTIVE
from runtime.runproof_runtime.effectwitness.pge_r73_sdk_harness import Harness
from runtime.runproof_runtime.effectwitness.pge_r73_verify import verify_bytes,MemoryJournal
from runtime.runproof_runtime.effectwitness.pge_r73_compat import parity

class FactoryContractTests(unittest.TestCase):
 def setUp(self):
  self.paths=dict(python=str(c.WORK/'unit-python.exe'),child=str(c.ROOT/c.CHILD),site=str(c.WORK/'unit-site'))
  self.request=LaunchRequest.build('config',25473,fixed=self.paths)
 def reject(self,mutate):
  v=self.request.public();mutate(v)
  with self.assertRaises((ValueError,TypeError,KeyError)):LaunchRequest(c.canonical(v)).check(self.paths)
 def test_canonical_owner_type_and_source_closure(self):
  self.assertEqual(self.request.check(self.paths)['owner'],'rpf-73');self.assertEqual(len(c.NEW),10);self.assertTrue(all(p in c.sources() for p in c.NEW))
 def test_request_and_receipt_immutable(self):
  with self.assertRaises(FrozenInstanceError):self.request.frozen=b'{}'
  receipt=LaunchReceipt(c.canonical({'example':1}));v=receipt.public();v['example']=2;self.assertEqual(receipt.public()['example'],1)
 def test_duplicate_and_nonfinite_json(self):
  for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
   with self.assertRaises(ValueError):c.strict(raw)
 def test_noncanonical_raw_rejected(self):
  with self.assertRaises(ValueError):LaunchRequest(self.request.frozen+b' ').public()
 def test_boolean_and_float_counts_rejected(self):
  for x in (True,1.0):self.reject(lambda v:v['cfg'].update(port=x))
 def test_extra_contract_fields_rejected(self):self.reject(lambda v:v.update(extension=True))
 def test_owner_source_cannot_be_aliased(self):self.reject(lambda v:v.update(owner='rpf-72-rev-3'))
 def test_round_bool_and_wrong_role(self):
  self.reject(lambda v:v.update(round=True));self.reject(lambda v:v.update(role='EXPLORER'))
 def test_nonwindows_contract_rejected(self):self.reject(lambda v:v.update(platform='POSIX'))
 def test_budget_constants_and_readonly_arithmetic(self):
  self.assertEqual([BudgetView(d).public()['cumulative'] for d in c.DOMAINS],[250000,160000]);self.assertEqual(2*sum(CAPS['EXPLORER'])+sum(CAPS[c.DOMAINS[0]])+sum(CAPS[c.DOMAINS[1]]),474000);self.assertEqual(BudgetView(c.DOMAINS[0]).public()['provider_reserved'],0)
 def test_budget_over_slot_bool_and_output_cap(self):
  for args in ((1,10000),(True,1),(1,1,True),(1,1,512),(6,1)):
   with self.assertRaises(ValueError):BudgetView(c.DOMAINS[0]).request(*args)
 def test_cumulative_limit_changed_and_bool_rejected(self):
  self.reject(lambda v:v['cfg'].update(total_token_limit=35000));self.reject(lambda v:v['cfg'].update(total_token_limit=True))
 def test_command_extra_flag_and_collision_rejected(self):
  self.reject(lambda v:v['argv'].append('-c'));self.reject(lambda v:v.update(command=v['command']+' '))
 def test_fake_binary_and_child_pin_rejected(self):
  self.reject(lambda v:v['argv'].__setitem__(0,'python'));self.reject(lambda v:v['pins'].update(child_sha256='0'*64))
 def test_cross_owner_and_old_certificate_cwd_rejected(self):
  self.reject(lambda v:v.update(cwd=str(c.ROOT/'.local/rpf-72-rev-3')));self.reject(lambda v:v['cfg'].update(write_root=str(c.ROOT/'docs')))
 def test_env_key_extra_and_type_rejected(self):
  self.reject(lambda v:v['env'].update(DEEPSEEK_API_KEY='dummy-unit-sentinel'));self.reject(lambda v:v['env'].update(PATH=[]))
 def test_env_relative_path_and_unknown_absolute_rejected(self):
  self.reject(lambda v:v['env'].update(PATH='.'));self.reject(lambda v:v['env'].update(PATH='C:\\untrusted'))
 def test_env_reanchored_foreign_home_rejected(self):
  def attack(v):v['env']['HOME']='C:\\foreign';v['env_summary']['sha256']=c.digest(v['env']);v['env_summary']['value_sha256']['HOME']=c.sha(v['env']['HOME'].encode())
  self.reject(attack)
 def test_frozen_env_summary_not_ambient(self):
  v=self.request.public();a=copy.deepcopy(v['env']);b=copy.deepcopy(a);b['SYSTEMROOT']=b['SYSTEMROOT'].swapcase();b['WINDIR']=b['WINDIR'].swapcase();self.assertNotEqual(c.digest(a),c.digest(b));self.assertEqual(env_summary(a,Path(v['cwd']))['sha256'],v['env_summary']['sha256']);env_summary(b,Path(v['cwd']))
 def test_cfg_raw_cannot_drift_or_be_noncanonical(self):self.reject(lambda v:v.update(cfg_raw=v['cfg_raw']+' '))
 def test_case_domain_and_cross_adapter_rejected(self):
  self.reject(lambda v:v.update(domain=c.DOMAINS[1]))
  with self.assertRaises(ValueError):Harness(self.request.public(),DomainAdapter(c.DOMAINS[1]),MemoryJournal())
 def test_domain_tools_and_argument_types(self):
  for d in c.DOMAINS:
   a=DomainAdapter(d)
   for name,args in a.arguments().items():self.assertIs(a.result(name,args)['business_effect'],False)
  with self.assertRaises(ValueError):DomainAdapter(c.DOMAINS[1]).result('refund_order',dict(order_id='component-order',operation_id='component-op',amount_minor=True))
 def test_missing_registry_or_cross_domain_tool_rejected(self):
  with self.assertRaises(ValueError):DomainAdapter(c.DOMAINS[0]).registry([])
  with self.assertRaises(ValueError):DomainAdapter(c.DOMAINS[0]).result('refund_order',{})
 def test_callback_requires_pending_and_cannot_repeat(self):
  h=Harness(self.request.public(),DomainAdapter(c.DOMAINS[0]),MemoryJournal());h.ready={}
  call=dict(call_id='unit-call',name='inspect_config',arguments={})
  with self.assertRaises(ValueError):h.callback(call,c.canonical(call))
  h.pending=call;h.callback(call,c.canonical(call));h.pending=call
  with self.assertRaises(ValueError):h.callback(call,c.canonical(call))
 def test_unknown_closed_and_error_stop_callbacks(self):
  for state in ('UNKNOWN','CLOSED','EXPECTED_REJECTION'):
   self.assertTrue(lifecycle_action(state,'OS_READBACK'))
   with self.assertRaises(ValueError):lifecycle_action(state,'CALLBACK')
 def test_no_frame_or_profile_dependency_shared_method(self):
  raw=(c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r73_launch_factory.py').read_text();self.assertNotIn('sys._getframe',raw);self.assertNotIn('sys.setprofile',raw);self.assertIsNone(ACTIVE.get());self.assertEqual(parity()['shared_factory_domains'],list(c.DOMAINS));self.assertTrue(callable(LaunchFactory.launch))
 def test_anchor_rejection_precedes_sdk_and_any_execution(self):
  with self.assertRaisesRegex(ValueError,'RAW_ANCHOR'):verify_bytes(b'{}','0'*64)
 def test_real_junction_and_owner_scope(self):
  root=c.scope(c.WORK/'tests'/secrets.token_hex(8));root.mkdir(parents=True);target=root/'target';target.mkdir();link=root/'link'
  result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True)
  self.assertEqual(result.returncode,0);self.assertTrue(link.is_junction())
  with self.assertRaisesRegex(ValueError,'OWNER_REPARSE'):c.scope(link/'child')
  # Deliberately retained current-task fixture, never follow it during inventory.
 def test_fictitious_returns_never_claim_authority(self):
  result=DomainAdapter(c.DOMAINS[0]).result('inspect_config',{});self.assertEqual(result['status'],'SIMULATED_ONLY');self.assertFalse(result['business_effect']);self.assertEqual(c.FLAGS['AUTHORITY_READBACK'],'NOT_RUN')
 def test_budget_view_closed_shape(self):
  value=BudgetView(c.DOMAINS[0]).public();value['reserve']=1
  with self.assertRaises(ValueError):BudgetView(c.DOMAINS[0]).check(value)

if __name__=='__main__':unittest.main()
