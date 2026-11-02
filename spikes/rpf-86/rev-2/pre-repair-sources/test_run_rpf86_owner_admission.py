"""Harness controls only; never execute the five native methods in this suite."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import uuid

spec=importlib.util.spec_from_file_location('owner_admission',Path(__file__).with_name('run-rpf86-owner-admission.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class OwnerAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('GITHUB_ACTIONS')=='true':
            cls.root=r.ROOT/'ci-results'/('rpf86-unit-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']+'-'+uuid.uuid4().hex)
        else:cls.root=r.LOCAL/('unit-'+uuid.uuid4().hex)
        r.owned(cls.root).mkdir(parents=True,exist_ok=False)
        cls.source=r.identity()
    def folder(self,label):return self.root/(label+'-'+uuid.uuid4().hex)
    def protocol(self):
        work=self.folder('protocol')/'work'
        events=[{'id':tid,'actual':state} for tid in r.IDS for state in ('STARTED','PASS')]
        report=dict(schema='rpf86-native-v1',ids=r.IDS,results=[dict(id=x,actual='PASS') for x in r.IDS],tests_run=5,
            source_identity=self.source,source_unchanged=True,physical_owner=work.relative_to(r.ROOT).as_posix(),
            logical_owner='rpf-63',logical_identity_changed=False,marker='TEST_HARNESS_OWNER_SUBSTITUTION',
            patch_points=['pge_dual_contracts.WORK'],patch_restored=True,status='PASS',error=None,
            guard={'denied':{}},source_level='SYNTHETIC_OFFLINE_TEST',events=events,pid=123,
            actual_provider_calls=0,actual_sdk_calls=0,actual_java_processes=0,actual_business_writes=0,
            manifest=[{'path':'synthetic-only-not-executed','bytes':1,'sha256':'0'*64}])
        receipt=dict(mode='native',exit=0,timeout=False,truncated=False,child_exited=True,drain_joined=True,pid=123,harness_lf_sha256=self.source['harness_lf_sha256'])
        return work,report,receipt
    def test_original_source_and_assertions_pinned(self):
        self.assertEqual(len(r.NAMES),5);self.assertEqual(len(set(r.IDS)),5)
        self.assertTrue(all(x>0 for x in self.source['assertion_counts'].values()))
        self.assertFalse(any(x==r.MODULE or x.startswith(r.MODULE+'.') for x in sys.modules))
    def test_protocol_control_not_native_pass_and_false_greens_reject(self):
        work,base,receipt=self.protocol();r.validate_native(base,receipt,self.source,work)
        mutations=[lambda x:x['results'].pop(),lambda x:x['results'][0].update(actual='SKIP'),
            lambda x:x['results'].__setitem__(1,copy.deepcopy(x['results'][0])),
            lambda x:x.update(source_identity={}),lambda x:x.update(physical_owner='wrong'),
            lambda x:x.update(logical_owner='rpf-86'),lambda x:x.update(patch_restored=False),
            lambda x:x['guard'].update(denied={'OLD_ROOT_ACCESS_DENIED':1}),
            lambda x:x['events'].pop(),lambda x:x['events'].insert(1,copy.deepcopy(x['events'][0])),
            lambda x:x.update(source_unchanged=False),lambda x:x['source_identity']['assertion_counts'].update(test_four_paths=0)]
        for change in mutations:
            report=copy.deepcopy(base);change(report)
            with self.assertRaises(r.Invalid):r.validate_native(report,receipt,self.source,work)
    def test_unsettled_child_never_passes(self):
        work,report,base=self.protocol()
        for key,value in [('exit',1),('timeout',True),('truncated',True),('child_exited',False),('drain_joined',False),('pid',999)]:
            receipt=dict(base,**{key:value})
            with self.assertRaises(r.Invalid):r.validate_native(report,receipt,self.source,work)
    def test_actual_protected_open_mkdir_stat_socket_and_subprocess_denied(self):
        folder=self.folder('guard');receipt=r.launch('controls',folder,deadline=time.monotonic()+20,timeout=20)
        self.assertEqual(receipt['exit'],0)
        report=r.strict((folder/'control-result.json').read_bytes())
        self.assertEqual(report['rejected'],['old-open','old-mkdir','old-stat','outside-write','socket','process'])
        self.assertEqual(report['old_root_delegations'],0)
        self.assertFalse((r.ROOT/report['canary_relative']).exists())
    def test_real_child_crash_exit_missing_timeout_and_truncation(self):
        for mode in ('crash','exit1','missing','timeout','overflow'):
            folder=self.folder(mode);rec=r.launch(mode,folder,deadline=time.monotonic()+15,timeout=.4 if mode=='timeout' else 10)
            self.assertTrue(rec['child_exited']);self.assertTrue(rec['drain_joined'])
            if mode=='crash':self.assertEqual(rec['exit'],7)
            if mode=='exit1':self.assertEqual(rec['exit'],1)
            if mode=='timeout':self.assertTrue(rec['timeout'])
            if mode=='overflow':self.assertTrue(rec['truncated'])
            self.assertFalse((folder/'child-result.json').exists())
    def test_owner_escape_casefold_reparse_and_ci_identity(self):
        for path in (r.ROOT/'.local/rpf-63/no-io',r.ROOT/'ci-results/rpf84-no',r.ROOT/'docs/no',self.root/'..'/'escape',
                     r.ROOT/'.LOCAL/RPF-86-OWNER-ADMISSION/case'):
            with self.assertRaises(r.Invalid):r.owned(path)
        target=self.folder('target');target.mkdir();link=self.folder('link')
        try:link.symlink_to(target,target_is_directory=True)
        except OSError:
            if os.name!='nt':raise
            import _winapi
            _winapi.CreateJunction(str(target),str(link))
        with self.assertRaisesRegex(r.Invalid,'REPARSE'):r.owned(link/'child')
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_WORKSPACE':str(r.ROOT),'GITHUB_RUN_ID':'1','GITHUB_RUN_ATTEMPT':'1'}):
            with self.assertRaisesRegex(r.Invalid,'CI_OWNER'):r.owned(r.ROOT/'ci-results/rpf86-1-2')
    def test_exclusive_result_and_expired_budget(self):
        folder=self.folder('exclusive');folder.mkdir();r.write(folder/'result.json',{'fixture':'protocol-only'})
        with self.assertRaises(FileExistsError):r.write(folder/'result.json',{})
        absent=self.folder('expired')
        with self.assertRaisesRegex(r.Invalid,'TOTAL_DEADLINE'):r.launch('missing',absent,deadline=time.monotonic()-1)
        self.assertFalse(absent.exists())
    def test_json_duplicate_nonfinite(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.assertRaises(r.Invalid):r.strict(raw)

if __name__=='__main__':unittest.main()
