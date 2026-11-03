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
        report['cache_policy']=dict(policy='FRESH_OWNER_PREFIX',prefix_relative=(work.parent/'pycache').relative_to(r.ROOT).as_posix(),
            dont_write_bytecode=True,source_pins=r.CACHE_SOURCES,global_loader_patch=False)
        receipt=dict(mode='native',exit=0,timeout=False,truncated=False,child_exited=True,drain_joined=True,pid=123,harness_lf_sha256=self.source['harness_lf_sha256'])
        receipt['journal']=dict(schema=r.JOURNAL_SCHEMA,status='COMPLETE',zero_denials_proven=True,methods=dict.fromkeys(r.IDS,'PASS'),
            denial_events=[],terminal={'status':'PASS','error':None},pid=123,source_sha256=self.source['harness_lf_sha256'])
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

    def durable(self):
        cls=type(self)
        if not hasattr(cls,'durable_receipt'):
            cls.durable_folder=self.folder('durable-exit')
            cls.durable_receipt=r.launch('durable-deny-crash',cls.durable_folder,deadline=time.monotonic()+20,timeout=20)
        return cls.durable_folder,copy.deepcopy(cls.durable_receipt)

    def test_durable_denial_survives_actual_child_exit(self):
        folder,receipt=self.durable();self.assertEqual(receipt['exit'],7)
        j=receipt['journal'];self.assertEqual(j['status'],'INCOMPLETE_EXIT');self.assertFalse(j['terminal_present'])
        self.assertFalse(j['zero_denials_proven']);self.assertEqual(len(j['denial_events']),1)
        e=j['denial_events'][0];self.assertEqual(e['reason'],'READ_SCOPE_DENIED')
        self.assertEqual(e['caller']['function'],'durable_control');self.assertEqual(e['phase'],'method')
        self.assertTrue(receipt['child_exited']);self.assertTrue(receipt['drain_joined'])
        self.assertFalse((folder/'child-result.json').exists())
        self.assertEqual(j,r.read_journal(folder/'denial-journal.jsonl',receipt['harness_lf_sha256'],receipt['pid'],['synthetic.durable_control'],self.source['attribution_sources']))

    def test_durable_start_timeout_never_proves_zero_denials(self):
        folder=self.folder('durable-timeout');rec=r.launch('durable-timeout',folder,deadline=time.monotonic()+20,timeout=2)
        self.assertTrue(rec['timeout']);self.assertTrue(rec['child_exited']);self.assertTrue(rec['drain_joined'])
        j=rec['journal'];self.assertEqual(j['status'],'INCOMPLETE_TIMEOUT')
        self.assertEqual(j['latest_method'],'synthetic.durable_control');self.assertFalse(j['terminal_present']);self.assertFalse(j['zero_denials_proven'])

    def test_durable_torn_duplicate_pid_source_caller_and_raw_path_rejected(self):
        folder,receipt=self.durable();raw=(folder/'denial-journal.jsonl').read_bytes();base=[r.strict(x) for x in raw.splitlines()]
        def encode(frames):
            previous=None;lines=[]
            for f in frames:
                f['previous_raw_sha256']=previous
                line=json.dumps(f,sort_keys=True,separators=(',',':')).encode()+b'\n';lines.append(line);previous=r.sha(line)
            return b''.join(lines)
        changes=[lambda fs:fs[-1].update(seq=fs[-2]['seq']),lambda fs:fs[-1].update(pid=999),
            lambda fs:fs[-1].update(source_sha256='0'*64),lambda fs:fs[-1]['data'].update(raw_path='synthetic-forbidden-field'),
            lambda fs:fs[-1]['data']['caller_chain'][0].update(function='<anonymous>'),
            lambda fs:fs[-1]['data']['caller_chain'][0].update(line=999999)]
        variants=[raw[:-5]]
        for change in changes:
            frames=copy.deepcopy(base);change(frames);variants.append(encode(frames))
        for value in variants:
            path=self.folder('journal-corrupt');path.write_bytes(value)
            j=r.read_journal(path,receipt['harness_lf_sha256'],receipt['pid'],['synthetic.durable_control'],self.source['attribution_sources'])
            self.assertEqual(j['status'],'TORN_OR_MISSING');self.assertFalse(j['zero_denials_proven']);self.assertGreaterEqual(j['valid_prefix_frames'],1)

    def test_journal_write_all_audit_fsync_failure_and_thread_rejection(self):
        import threading
        path=self.folder('partial-journal');source=self.source['harness_lf_sha256'];ids=['synthetic.durable_control']
        original=r.os.write;calls=[];audit_events=[];active=[False]
        def observe(event,args):
            if active[0]:audit_events.append(event)
        sys.addaudithook(observe)
        def short(fd,data):calls.append(len(data));return original(fd,data[:7])
        with patch.object(r.os,'write',short):
            j=r.Journal(path,source,ids);active[0]=True
            try:j.emit('METHOD_START',{'id':ids[0]})
            finally:active[0]=False
        self.assertGreater(len(calls),2);self.assertEqual(audit_events,[])
        errors=[]
        def other():
            try:j.emit('METHOD_STOP',{'id':ids[0],'actual':'PASS'})
            except r.Invalid as exc:errors.append(str(exc))
        t=threading.Thread(target=other);t.start();t.join();self.assertEqual(errors,['JOURNAL_THREAD']);self.assertTrue(j.failed)
        with self.assertRaises(r.Invalid):j.emit('TERMINAL',{'status':'PASS','error':None})
        j.close()
        with patch.object(r.os,'fsync',side_effect=OSError('synthetic fsync failure')):
            with self.assertRaisesRegex(r.Invalid,'JOURNAL_IO'):r.Journal(self.folder('fsync-failure'),source,ids)

    def test_durable_real_denial_overflow_is_not_admissible(self):
        folder=self.folder('durable-overflow');folder.mkdir();sandbox=folder/'sandbox';sandbox.mkdir()
        target=folder/'new-fixture';target.write_bytes(b'new fixture');source=self.source['harness_lf_sha256'];ids=['synthetic.durable_control']
        j=r.Journal(folder/'journal.jsonl',source,ids);g=r.Guard(sandbox,journal=j);g.method_start(ids[0])
        for _ in range(17):
            g.context('Guard.check',target)
            with self.assertRaises(PermissionError):g.check(target)
        j.close();result=r.read_journal(folder/'journal.jsonl',source,os.getpid(),ids,self.source['attribution_sources'])
        self.assertEqual(result['status'],'TORN_OR_MISSING');self.assertEqual(len(result['denial_events']),16)
        self.assertFalse(result['zero_denials_proven']);self.assertTrue(g.truncated)

    def test_native_suite_does_not_install_global_trace(self):
        def fixture():pass
        suite=unittest.TestSuite([unittest.FunctionTestCase(fixture)]);g=r.Guard(self.folder('no-trace'));before=sys.gettrace()
        with patch.object(r.sys,'settrace',side_effect=AssertionError('global trace forbidden')):
            result=r.run_suite(suite,g)
        self.assertTrue(result.wasSuccessful());self.assertIs(sys.gettrace(),before)

    def test_actual_independent_performance_microprobe_is_observation_only(self):
        folder=self.folder('performance');rec=r.launch('performance',folder,deadline=time.monotonic()+20,timeout=20)
        self.assertEqual(rec['exit'],0);p=r.strict((folder/'performance.json').read_bytes())
        self.assertEqual(p['status'],'OBSERVED_NO_SPEED_THRESHOLD');self.assertGreater(p['base_trace_callbacks'],0)
        self.assertEqual([x['mode'] for x in p['samples']],['base_global_trace','candidate_no_trace'])
        self.assertEqual([len(x['samples_ns']) for x in p['samples']],[7,7])
        self.assertEqual(p['samples'][0]['checksum'],p['samples'][1]['checksum'])

    def test_exact_lexical_cache_classification_never_grants_target_io(self):
        candidates=r.cache_candidates()
        with patch.object(r.os,'stat',side_effect=AssertionError('target stat forbidden')),patch.object(r.os,'lstat',side_effect=AssertionError('target lstat forbidden')):
            for target,kind in candidates.items():
                self.assertEqual(r.classify_cache(target,candidates),kind)
                self.assertEqual(r.classify_cache(target.replace(sys.implementation.cache_tag,'wrong-tag'),candidates),'other_public')
                self.assertEqual(r.classify_cache(str(Path(target).with_name('unlisted.pyc')),candidates),'other_public')
                self.assertEqual(r.classify_cache(str(Path(target).with_name(Path(target).name.upper())),candidates),'other_public')
                self.assertEqual(r.classify_cache(str(Path(target).parent/'..'/Path(target).name),candidates),'other_public')

    def test_real_fresh_prefix_source_load_and_historical_cache_denial(self):
        folder=self.folder('cache-control');rec=r.launch('cache-controls',folder,deadline=time.monotonic()+20,timeout=20)
        self.assertEqual(rec['exit'],0);p=r.strict((folder/'cache-controls.json').read_bytes())
        self.assertEqual(p['loaded_source_files'],list(r.CACHE_SOURCES));self.assertEqual(p['historical_cache_reads_denied'],2)
        self.assertEqual(p['actual_cache_files_created'],0);self.assertFalse(p['global_loader_patch'])
        self.assertEqual(p['source_pins'],self.source['cache_sources'])

    def test_cache_source_pin_prefix_scope_and_journal_class_forgery_rejected(self):
        with patch.object(r,'CACHE_SOURCES',{next(iter(r.CACHE_SOURCES)):r.PINS[next(iter(r.PINS))]}):
            with self.assertRaisesRegex(r.Invalid,'CACHE_SOURCE_PIN'):r.identity()
        with self.assertRaises(r.Invalid):r.configure_cache(r.ROOT/'.local/rpf-63/no-access')
        work,report,rec=self.protocol()
        for change in (lambda p:p.update(prefix_relative='outside'),lambda p:p.update(dont_write_bytecode=False),lambda p:p.update(global_loader_patch=True)):
            p=copy.deepcopy(report);change(p['cache_policy'])
            with self.assertRaisesRegex(r.Invalid,'CACHE_POLICY_BINDING'):r.validate_native(p,rec,self.source,work)
        fg=self.false_green();g=fg['guard'];g['attribution_events'][0]['cache_probe']='forged-cache-tag'
        g['attribution_sha256']=r.sha(json.dumps(g['attribution_events'],sort_keys=True,separators=(',',':')).encode())
        with self.assertRaisesRegex(r.Invalid,'CACHE_CLASSIFICATION'):r.validate_attribution(g,self.source['attribution_sources'],fg['ids'])
        directory=self.folder('cache-reparse');directory.mkdir();target=self.folder('cache-target');target.mkdir();link=directory/'pycache'
        try:link.symlink_to(target,target_is_directory=True)
        except OSError:
            if os.name!='nt':raise
            import _winapi
            _winapi.CreateJunction(str(target),str(link))
        with self.assertRaisesRegex(r.Invalid,'REPARSE'):r.configure_cache(directory)
        work,p,rec=self.protocol()
        for change in (lambda x:x.pop('journal'),lambda x:x['journal'].update(status='INCOMPLETE_TIMEOUT'),
                       lambda x:x['journal'].update(denial_events=[{}]),lambda x:x['journal'].update(pid=999)):
            bad=copy.deepcopy(rec);change(bad)
            with self.assertRaisesRegex(r.Invalid,'JOURNAL_NATIVE_BINDING'):r.validate_native(p,bad,self.source,work)

    def test_hosted_public_projection_omits_paths_protocol_and_identity_values(self):
        marker='synthetic-private-canary'
        result=dict(status='FAIL',physical_owner=marker,error=marker,source_identity={'sdk_identity':marker},
            native_results=[{'id':x,'actual':'PASS'} for x in r.IDS],
            native_receipt={'pid':123,'exit':1,'stdout':marker,'stderr':marker,'path':marker,
                'journal':{'status':'COMPLETE','terminal':{'status':'FAIL','error':marker},'denial_events':[{'target_token':marker,'caller':marker}]}})
        projected=r.public_projection(result);self.assertNotIn(marker,json.dumps(projected))
        self.assertEqual(projected['journal_denial_count'],1);self.assertFalse(projected['journal_terminal_pass'])
        self.assertEqual(projected['status'],'FAIL');self.assertEqual(projected['formal_required_unavailable'],539)

if __name__=='__main__':unittest.main()
