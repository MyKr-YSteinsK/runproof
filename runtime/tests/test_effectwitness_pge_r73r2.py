"""Pure runner boundaries and actual sanitized process observation; no Factory."""
import copy,importlib,json,os,secrets,subprocess,sys,unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
e=importlib.import_module('spikes.rpf-73.rev-2.environment_contract')
r=importlib.import_module('spikes.rpf-73.rev-2.runner')
class RunnerContractTests(unittest.TestCase):
 def setUp(self):
  descriptor=Path(os.environ['RPF73R2_ENV_RECEIPT']);self.expected=e.strict(descriptor.read_bytes());self.contract=e.SuiteEnvironmentContract(e.canonical(self.expected['contract']));self.value=self.contract.public();self.root=Path(self.value['owner_root'])
 def reject(self,fn):
  value=copy.deepcopy(self.value);fn(value)
  with self.assertRaises((ValueError,TypeError,KeyError)):e.SuiteEnvironmentContract(e.canonical(value)).check()
 def test_actual_process_env_matches_admission(self):
  value=e.observe_actual();self.assertEqual(value['env_sha256'],self.value['env_sha256']);self.assertEqual(value['pid'],os.getpid());self.assertFalse(value['credential_values_read'])
 def test_python_is_absolute_and_raw_pinned(self):
  self.assertTrue(Path(self.value['python']).is_absolute());self.assertEqual(e.sha(Path(sys.executable).read_bytes()),e.PYTHON_SHA)
 def test_unknown_python_directory_is_never_appended(self):
  self.assertEqual(self.value['runner_appended_paths'],[]);self.assertTrue(all(e.path_id(x) in e.trusted_paths()['TRUSTED_PATH_SHA256'] for x in self.value['env']['PATH'].split(';')))
 def test_host_path_filters_percent_relative_unc_and_unknown(self):
  path=self.value['env']['PATH'];filtered,dropped=e.filtered_path(path+';.;%JAVA_HOME%\\bin;\\\\server\\share;C:\\unknown')
  self.assertEqual(filtered,path);self.assertEqual(len(dropped),4)
 def test_host_path_type_and_no_trusted_entries(self):
  for value in (True,[],'.','%PATH%'):
   with self.assertRaises(ValueError):e.filtered_path(value)
 def test_mutable_public_view_does_not_change_contract(self):
  public=self.contract.public();public['env']['PATH']='.';self.assertNotEqual(public,self.contract.public())
 def test_contract_bytes_immutable(self):
  with self.assertRaises(FrozenInstanceError):self.contract.frozen=b'{}'
 def test_noncanonical_duplicate_nonfinite_rejected(self):
  with self.assertRaises(ValueError):e.SuiteEnvironmentContract(self.contract.frozen+b' ').public()
  for raw in (b'{"a":1,"a":2}',b'{"a":Infinity}'):
   with self.assertRaises(ValueError):e.strict(raw)
 def test_owner_and_abi_cannot_alias_rev1(self):
  self.reject(lambda x:x.update(owner='rpf-73'));self.reject(lambda x:x.update(abi='rpf73-launch-factory-v1'))
 def test_reference_root_is_bound_to_owned_task(self):self.reject(lambda x:x.update(reference_root='C:\\foreign'))
 def test_credential_key_injection_is_data_not_host_lookup(self):self.reject(lambda x:x['env'].update(DEEPSEEK_API_KEY='UNIT_DUMMY_NOT_CREDENTIAL'))
 def test_extra_os_vars_are_not_implicitly_inherited(self):self.reject(lambda x:x['env'].update(APPDATA='C:\\unapproved'))
 def test_empty_bool_env_rejected(self):
  self.reject(lambda x:x['env'].update(PATH=''));self.reject(lambda x:x['env'].update(PATH=True))
 def test_unknown_absolute_relative_and_unc_rejected(self):
  for path in ('C:\\unknown','.','\\\\server\\share'):self.reject(lambda x:x['env'].update(PATH=path))
 def test_percent_parent_quote_command_rejected(self):
  for path in ('%PATH%','C:\\Windows\\..\\unknown','"C:\\Windows"','C:\\Windows&echo'):self.reject(lambda x:x['env'].update(PATH=path))
 def test_system_root_and_comspec_pinned(self):
  self.reject(lambda x:x['env'].update(SYSTEMROOT='C:\\foreign'));self.reject(lambda x:x['env'].update(COMSPEC='cmd'))
 def test_scratch_and_receipt_path_cannot_escape(self):
  self.reject(lambda x:x['env'].update(HOME='C:\\foreign'));self.reject(lambda x:x.update(descriptor='C:\\foreign\\environment.json'))
 def test_hash_cannot_replace_actual_env(self):self.reject(lambda x:x.update(env_sha256='0'*64))
 def test_unknown_binary_and_wrong_hash_rejected(self):
  self.reject(lambda x:x.update(python='C:\\not-python.exe'));self.reject(lambda x:x.update(python_sha256='0'*64))
 def test_unapproved_flags_rejected(self):
  self.reject(lambda x:x['env'].update(PYTHONUTF8='0'));self.reject(lambda x:x['env'].update(PYTHONPATH='C:\\inject'))
 def test_full_command_is_exact_unfiltered(self):
  self.assertTrue(r.validate_command('full',r.FULL_ARGS))
  for args in (r.FULL_ARGS+['test_only'],['-m','unittest','discover','-s','runtime/tests','-p','test_effectwitness_pge_r73r2.py','-v']):
   with self.assertRaises(ValueError):r.validate_command('full',args)
 def test_failed_summary_still_present_never_pass(self):
  summary=e.parse_summary('Ran 665 tests in 1.001s\r\n\r\nFAILED (errors=8, skipped=2)\r\n');self.assertTrue(summary['unittest_final_summary_present']);self.assertFalse(summary['pass_summary']);self.assertEqual(summary['tests'],665)
 def test_truncated_stdout_has_no_final_summary(self):self.assertFalse(e.parse_summary('test_a ... ok\n')['unittest_final_summary_present'])
 def test_raw_output_and_failure_reclassification_rejected(self):
  raw=b'Ran 1 test in 0.001s\nFAILED (errors=1)\n';receipt=dict(log_sha256=e.sha(raw),summary=e.parse_summary(raw.decode()),status='PASS',exit=1)
  with self.assertRaisesRegex(ValueError,'FAILURE_NOT_PASS'):e.verify_receipt(receipt,raw)
  receipt['status']='FAIL'
  with self.assertRaisesRegex(ValueError,'STDOUT_RAW_HASH'):e.verify_receipt(receipt,raw+b' ')
 def test_original_factory_identity_preserved(self):self.assertEqual(e.source_identity()['old_factory_source_sha256'],e.OLD_SOURCE)
 def test_actual_junction_and_duplicate_claim_refused(self):
  root=e.owned(self.root/'tests'/secrets.token_hex(8),self.root);root.mkdir(parents=True);target=root/'target';target.mkdir();link=root/'link';result=subprocess.run([self.value['env']['COMSPEC'],'/c','mklink','/J',str(link),str(target)],capture_output=True);self.assertEqual(result.returncode,0)
  with self.assertRaisesRegex(ValueError,'OWNER_REPARSE'):e.owned(link/'child',self.root)
  p=root/'once.json';e.write_once(p,{'claimed':True})
  with self.assertRaises(FileExistsError):e.write_once(p,{'claimed':False})
if __name__=='__main__':unittest.main()
