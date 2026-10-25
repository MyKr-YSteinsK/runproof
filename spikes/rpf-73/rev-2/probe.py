"""Actual child environment, exact inventory and fail-closed process controls."""
import argparse,collections,copy,json,os,sys,unittest
from pathlib import Path
from . import environment_contract as e
def validate_case(case):
 kind=case['kind'];value=case['value']
 if kind=='contract':return e.SuiteEnvironmentContract(e.canonical(value)).check()
 if kind=='receipt':return e.verify_receipt(value,case['raw'].encode())
 if kind=='claim':e.require(not e.owned(Path(value)).exists(),'DUPLICATE_CLAIM');return True
 if kind=='source':
  raw=e.owned(Path(value['path'])).read_bytes();e.require(e.sha(raw)==value['raw'] and e.sha(raw.replace(b'\r\n',b'\n'))==value['lf'],'SOURCE_RAW_LF');return True
 if kind=='command':
  from .runner import validate_command
  return validate_command(value['mode'],value['args'])
 raise ValueError('UNKNOWN_CASE')
def inventory():
 actual=e.observe_actual();loader=unittest.TestLoader();suite=loader.discover('runtime/tests',pattern='test_*.py')
 def flatten(value):
  for item in value:
   if isinstance(item,unittest.TestSuite):yield from flatten(item)
   else:yield item
 ids=[test.id() for test in flatten(suite)];e.require(len(ids)==len(set(ids)) and not loader.errors,'DISCOVERY_ERRORS')
 classes=[]
 for name in ('test_docker_integration.DockerIntegrationTests','test_rpf05_runtime.Rpf05RuntimeTests'):
  methods=[x for x in ids if x.startswith(name+'.')];e.require(bool(methods),'DOCKER_CLASS_INVENTORY');classes.append(dict(class_id=name,test_ids=methods))
 value=dict(status='PASS',actual_environment=actual,discovered=len(ids),test_ids=ids,allowed_unavailable_classes=classes,expected_actual_with_class_skips=len(ids)-sum(len(x['test_ids']) for x in classes),module_counts=dict(collections.Counter(x.split('.')[0] for x in ids)),loader_errors=loader.errors)
 e.write_once(Path(os.environ['RPF73R2_ENV_RECEIPT']).parent/'inventory.json',value);print(e.canonical(dict(status='PASS',discovered=len(ids),expected_actual=value['expected_actual_with_class_skips'])).decode());return 0
def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True);sub.add_parser('observe');sub.add_parser('inventory');v=sub.add_parser('validate');v.add_argument('--case',required=True);a=p.parse_args()
 if a.action=='observe':print(e.canonical(e.observe_actual()).decode());return 0
 if a.action=='inventory':return inventory()
 try:
  path=e.owned(Path(a.case));case=e.strict(path.read_bytes());validate_case(case);print(e.canonical(dict(status='ACCEPTED')).decode());return 0
 except (ValueError,TypeError,KeyError,OSError,UnicodeError) as error:
  print(e.canonical(dict(status='REJECTED',reason=str(error) if type(error) is ValueError else type(error).__name__)).decode());return 3
if __name__=='__main__':raise SystemExit(main())
