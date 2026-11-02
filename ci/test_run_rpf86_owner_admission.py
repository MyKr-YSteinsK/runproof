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
        else:cls.root=r.local_task()/('unit-'+uuid.uuid4().hex)
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
            guard={'denied':{},'certificate':self.source['certificate'],'observed':{'certificate_read_granted':1},
                'attribution_schema':'rpf86-denial-events-v1','attribution_events':[],
                'attribution_total':0,'attribution_truncated':False,'attribution_sources':self.source['attribution_sources'],
                'attribution_sha256':r.sha(b'[]')},source_level='SYNTHETIC_OFFLINE_TEST',events=events,pid=123,
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

    def test_exact_certificate_original_helper_and_real_denials(self):
        folder=self.folder('certificate');receipt=r.launch('certificate-controls',folder,deadline=time.monotonic()+20,timeout=20)
        self.assertEqual(receipt['exit'],0)
        report=r.strict((folder/'certificate-controls.json').read_bytes())
        self.assertEqual(report['rejected'],['directory','sibling','other-json','write','truncate-audit','case-alias'])
        self.assertTrue(report['original_helper_called']);self.assertFalse(report['certificate_values_exported'])
        self.assertGreater(report['guard']['observed']['certificate_read_granted'],0)
        self.assertEqual(report['guard']['certificate'],self.source['certificate'])
        self.assertEqual(report['guard']['denied'],{'READ_SCOPE_DENIED':3,'CERTIFICATE_WRITE_DENIED':2,'CERTIFICATE_CASE_ALIAS_DENIED':1})

    def test_certificate_hash_source_and_unobserved_read_fail_closed(self):
        with self.assertRaisesRegex(r.Invalid,'CERTIFICATE_HASH'):r.certificate_bytes(b'not a historical certificate')
        with patch.object(r,'CERT_BLOB','0'*40):
            with self.assertRaisesRegex(r.Invalid,'CERTIFICATE_TRACKED_IDENTITY'):r.certificate_identity()
        with patch.object(r,'HELPER_BLOB',r.PINS[next(iter(r.PINS))]):
            with self.assertRaisesRegex(r.Invalid,'HELPER_PIN'):r.identity()
        work,base,receipt=self.protocol()
        for change in (lambda x:x['guard'].update(certificate={}),lambda x:x['guard'].update(observed={})):
            report=copy.deepcopy(base);change(report)
            with self.assertRaisesRegex(r.Invalid,'CERTIFICATE_READ_UNOBSERVED'):r.validate_native(report,receipt,self.source,work)

    def test_certificate_reparse_rejected_before_read(self):
        target=self.folder('synthetic-bytes');target.write_bytes(b'not certificate content')
        link=self.folder('synthetic-link')
        try:link.symlink_to(target)
        except OSError:
            # A real junction exercises the same ancestor check on Windows.
            if os.name!='nt':raise
            directory=self.folder('synthetic-directory');directory.mkdir()
            import _winapi
            _winapi.CreateJunction(str(directory),str(link))
        with patch.object(r,'CERT_PATH',link):
            with self.assertRaisesRegex(r.Invalid,'REPARSE'):r.certificate_identity()

    def test_real_log_byte_drift_rejected(self):
        path=self.folder('log');path.write_bytes(b'actual local log\n')
        raw=path.read_bytes();receipt={'bytes':len(raw),'stdout_sha256':r.sha(raw)}
        r.validate_log(raw,receipt)
        path.write_bytes(raw.replace(b'local',b'LOCAL'))
        with self.assertRaisesRegex(r.Invalid,'LOG_BINDING'):r.validate_log(path.read_bytes(),receipt)

    def false_green(self):
        cls=type(self)
        if not hasattr(cls,'false_green_report'):
            folder=self.folder('false-green')
            receipt=r.launch('false-green',folder,deadline=time.monotonic()+20,timeout=20)
            self.assertEqual(receipt['exit'],0)
            cls.false_green_report=r.strict((folder/'sandbox/false-green.json').read_bytes())
        return copy.deepcopy(cls.false_green_report)

    def test_real_broad_assertion_permission_error_is_never_admitted(self):
        report=self.false_green();self.assertEqual(report['native_method_status'],'PASS')
        self.assertEqual(report['admission_status'],'FAIL');self.assertEqual(report['delegated_target_io'],0)
        event=report['guard']['attribution_events'][0]
        self.assertEqual(event['phase'],'method');self.assertEqual(event['event_kind'],'Guard.check')
        self.assertEqual(event['caller']['function'],'test_guard_false_green')
        self.assertTrue(event['permission_error_observed_in_method']);self.assertTrue(event['continued_after_broad_context'])
        self.assertEqual(event['method_later_status'],'PASS')
        self.assertEqual(event['assertRaises_broad_exception_risk'],'SUSPECTED')
        work,native,receipt=self.protocol();native['guard']=report['guard']
        with self.assertRaises(r.Invalid):r.validate_native(native,receipt,self.source,work)

    def test_attribution_missing_binding_spoof_tamper_duplicate_and_stale_source(self):
        report=self.false_green();base=report['guard'];sources=self.source['attribution_sources'];ids=report['ids']
        r.validate_attribution(base,sources,ids)
        changes=[lambda g:g['attribution_events'][0].update(method_id=None),
            lambda g:g['attribution_events'][0].update(phase='fabricated'),
            lambda g:g['attribution_events'][0]['caller_chain'][0].update(path='unapproved.py'),
            lambda g:g['attribution_events'][0]['caller_chain'][0].update(line=999999),
            lambda g:g['attribution_events'][0]['caller_chain'][0].update(function='spoofed'),
            lambda g:g['attribution_events'][0]['caller_chain'][0].update(source_sha256='0'*64),
            lambda g:g['attribution_events'].append(copy.deepcopy(g['attribution_events'][0])),
            lambda g:g.update(attribution_sources={}),lambda g:g.update(attribution_total=0)]
        for change in changes:
            g=copy.deepcopy(base);change(g)
            g['attribution_sha256']=r.sha(json.dumps(g['attribution_events'],sort_keys=True,separators=(',',':')).encode())
            with self.assertRaises(r.Invalid):r.validate_attribution(g,sources,ids)
        g=copy.deepcopy(base);g['attribution_events'][0]['intent']='write'
        with self.assertRaisesRegex(r.Invalid,'ATTRIBUTION_EVENT_HASH'):r.validate_attribution(g,sources,ids)

    def test_real_denial_precedes_io_and_event_overflow_fails_closed(self):
        fixture=self.folder('new-owned-synthetic');fixture.write_bytes(b'new fixture only')
        guard=r.Guard(self.folder('isolated'))
        def forbidden_metadata(*a,**kw):raise AssertionError('metadata delegated')
        with patch.object(guard,'raw_lstat',forbidden_metadata):
            for _ in range(r.ATTRIBUTION_LIMIT+1):
                guard.context('Guard.check',fixture)
                with self.assertRaises(PermissionError):guard.check(fixture)
        projection=guard.projection();self.assertEqual(len(projection['attribution_events']),16)
        self.assertEqual(projection['attribution_total'],17);self.assertTrue(projection['attribution_truncated'])
        with self.assertRaisesRegex(r.Invalid,'ATTRIBUTION_TRUNCATED'):r.validate_attribution(projection,guard.sources,[])

    def test_actual_child_report_byte_and_receipt_binding(self):
        folder=self.folder('report-binding');folder.mkdir();r.write(folder/'child-result.json',{'kind':'synthetic-control'})
        raw=(folder/'child-result.json').read_bytes();receipt={'child_result_raw_sha256':r.sha(raw)}
        self.assertEqual(r.read_child_report(folder,receipt),{'kind':'synthetic-control'})
        (folder/'child-result.json').write_bytes(raw+b' ')
        with self.assertRaisesRegex(r.Invalid,'CHILD_REPORT_BINDING'):r.read_child_report(folder,receipt)
        with self.assertRaisesRegex(r.Invalid,'CHILD_REPORT_BINDING'):r.read_child_report(folder,{})

if __name__=='__main__':unittest.main()
