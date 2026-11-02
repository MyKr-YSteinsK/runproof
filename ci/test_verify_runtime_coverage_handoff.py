"""Synthetic, task-owned receipt controls; never a claim of Runtime execution."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

SPEC = importlib.util.spec_from_file_location('coverage_handoff', Path(__file__).with_name('verify-runtime-coverage-handoff.py'))
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as out:
        out.write(value if isinstance(value, bytes) else json.dumps(value, indent=2).encode())


def overwrite(path, value):
    # Deliberate corruption of a new negative fixture, never sealed evidence.
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value, indent=2).encode())


def fixture(root):
    router, matrix, required = v.sources()
    baseline = v.strict(v.BASELINE.read_bytes())
    skipped = {r['id'] for m in baseline['modules'] for r in m['rows'] if r['actual'] == 'SKIP'}
    assert len(skipped) == 5
    ledger = dict(schema='rpf84-runtime-ledger-v1', modules=[], coverage_policy='ALL_DISCOVERED_REQUIRED',
                  overall='REQUIRED_COVERAGE_UNAVAILABLE', portable='PASS', required_modules=57,
                  required_methods=1232, baseline_sha256=v.lf(v.BASELINE), lane_limit_seconds=1500,
                  coverage_verified=True, discovered=1232, unique_dispositions=1232)
    clock = 1_000_000_000
    def invocation(folder, result):
        nonlocal clock
        log = b'RPF85 SYNTHETIC OFFLINE RECEIPT; NOT A RUNTIME RUN\n'
        rec = dict(exit=0, timeout=False, truncated=False, stdout_sha256=v.digest(log), bytes=len(log),
                   monotonic_start_ns=clock, monotonic_end_ns=clock+1000, child_pid=1000+clock//10000,
                   runner_sha256=v.lf(v.RUNNER), timeout_limit_seconds=300, child_exited=True,
                   drain_joined=True, descendant_cleanup='UNAVAILABLE: exact Popen handle only')
        clock += 10000
        write(folder/'launch-receipt.json', rec);write(folder/'output.log', log);write(folder/'result.json', result)
        return rec
    for declaration in matrix['modules']:
        path = declaration['path'];stem = Path(path).stem
        rows = router.classify(declaration, required[path])
        selected = [r['id'] for r in rows if r['route'] == 'PORTABLE']
        rec = invocation(root/(stem+'-inventory'), {'ids': required[path]})
        module = dict(path=path, source_sha256=declaration['source_sha256'], rows=rows,
                      invocations=[rec], inventory_verified=True, runner_sha256=v.lf(v.RUNNER), matrix_sha256=v.lf(v.MATRIX))
        for row in rows:
            row.update(actual=('SKIP' if row['id'] in skipped else 'PASS') if row['route']=='PORTABLE' else 'UNAVAILABLE',
                       executed=row['route']=='PORTABLE' and row['id'] not in skipped)
        if selected:
            events=[];fixture_ids=[]
            skip_classes={tid.rsplit('.',1)[0] for tid in selected if tid in skipped}
            for cls in sorted(skip_classes):
                ids=[x for x in selected if x.startswith(cls+'.')]
                assert set(ids) <= skipped
                fixture_ids.extend(ids);events.append(dict(id='setUpClass ('+cls+')',actual='SKIP'))
            for tid in selected:
                if tid not in fixture_ids:
                    events += [dict(id=tid,actual='STARTED'),dict(id=tid,actual='PASS')]
            result = dict(ids=selected, results=[dict(id=x,actual='SKIP' if x in skipped else 'PASS') for x in selected],
                          tests_run=len(selected)-len(fixture_ids), successful=True, fixture_skips=fixture_ids)
            execution=root/(stem+'-execution')
            module['invocations'].append(invocation(execution,result))
            selection=dict(inventory=required[path],selected=selected)
            write(root/(stem+'-selection.json'),selection);write(execution/'selection.json',selection)
            write(execution/'progress.jsonl',b''.join(json.dumps(e).encode()+b'\n' for e in events))
            module.update(tests_run=result['tests_run'],fixture_skips=fixture_ids)
        ledger['modules'].append(module)
    rows=[r for m in ledger['modules'] for r in m['rows']]
    ledger['counts']=dict(v.Counter(r['actual'] for r in rows))
    ledger['routes']={route:dict(v.Counter(r['actual'] for r in rows if r['route']==route)) for route in sorted(router.ROUTES)}
    ledger['lane_finished_monotonic']=clock/1e9+1
    write(root/'ledger.json',ledger)


class CoverageHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=v.OWNER/('unit-'+uuid.uuid4().hex)
        cls.root.mkdir(parents=True,exist_ok=False)
        cls.template=cls.root/'template';cls.template.mkdir()
        fixture(cls.template)
        cls.commit=v.git('rev-parse','HEAD').decode().strip()

    def fresh(self):
        root=self.root/('case-'+uuid.uuid4().hex);root.mkdir()
        for path in self.template.rglob('*'):
            target=root/path.relative_to(self.template)
            if path.is_dir():target.mkdir()
            else:write(target,path.read_bytes())
        return root

    def assess(self, root, code=1):
        return v.assess(root/'ledger.json',code,'local','1',self.commit,synthetic=True)

    def test_synthetic_positive_continues_but_barrier_rejects(self):
        root=self.fresh();status=self.assess(root)
        self.assertEqual(status['counts'],{'PASS':688,'SKIP':5,'UNAVAILABLE':539})
        self.assertEqual(status['diagnostic_continuation'],'CONTINUE_DIAGNOSTIC_ONLY')
        self.assertEqual(status['evidence_kind'],'SYNTHETIC_OFFLINE_TEST')
        self.assertFalse(status['release_eligible']);self.assertFalse(status['release_executed']);self.assertFalse(status['deployment_authorized'])
        write(root/'status.json',status)
        code,again=v.enforce(root/'status.json',root/'ledger.json','local','1',self.commit,synthetic=True)
        self.assertEqual(code,1);self.assertEqual(again['reason'],'RELEASE_BLOCKED_BY_REQUIRED_COVERAGE')

    def test_json_duplicate_nonfinite_oversize_and_truncation(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}',b'{',b' '* (v.MAX_JSON+1)):
            with self.subTest(kind=raw[:24]),self.assertRaises((v.Invalid,ValueError)):
                v.strict(raw)
        root=self.fresh();overwrite(root/'ledger.json',b'x'*(v.MAX_JSON+1))
        with self.assertRaisesRegex(v.Invalid,'EVIDENCE_SIZE'):self.assess(root)

    def test_missing_ledger_escape_and_reparse(self):
        with self.assertRaises(OSError):self.assess(self.root/'absent')
        for path in (v.ROOT/'docs/reviews/forbidden.json',v.ROOT/'.local/other/ledger.json',self.root/'..'/'escape'):
            with self.assertRaises(v.Invalid):v.scoped(path,run_id='local',attempt='1',kind='ledger',synthetic=True)
        root=self.fresh();link=self.root/('link-'+uuid.uuid4().hex)
        try:link.symlink_to(root,target_is_directory=True)
        except OSError:
            if os.name!='nt':raise
            import _winapi
            _winapi.CreateJunction(str(root),str(link))
        with self.assertRaisesRegex(v.Invalid,'REPARSE'):self.assess(link)

    def test_identity_coverage_routes_and_fake_green_reject(self):
        mutations={
            'missing-module':lambda x:x['modules'].pop(),
            'duplicate-module':lambda x:x['modules'].__setitem__(1,copy.deepcopy(x['modules'][0])),
            'reduced-required':lambda x:x.update(required_methods=693),
            'fake-coverage':lambda x:x.update(coverage_verified=False),
            'overall-pass':lambda x:x.update(overall='PASS'),
            'portable-failure':lambda x:x.update(portable='FAIL'),
            'source-drift':lambda x:x['modules'][0].update(source_sha256='0'*64),
            'matrix-drift':lambda x:x['modules'][0].update(matrix_sha256='0'*64),
            'duplicate-method':lambda x:x['modules'][0]['rows'].__setitem__(1,copy.deepcopy(x['modules'][0]['rows'][0])),
            'missing-method':lambda x:x['modules'][0]['rows'].pop(),
            'fake-pass':lambda x:x['modules'][0]['rows'][0].update(executed=False),
            'portable-not-run':lambda x:x['modules'][0]['rows'][0].update(actual='NOT_RUN'),
            'required-false':lambda x:x['modules'][0]['rows'][0].update(required=False),
            'inventory-not-verified':lambda x:x['modules'][0].update(inventory_verified=False),
            'unavailable-skip':lambda x:next(r for m in x['modules'] for r in m['rows'] if r['route']!='PORTABLE').update(actual='SKIP'),
            'unavailable-pass':lambda x:next(r for m in x['modules'] for r in m['rows'] if r['route']!='PORTABLE').update(actual='PASS',executed=True),
        }
        for name,mutate in mutations.items():
            with self.subTest(name=name):
                root=self.fresh();ledger=v.strict((root/'ledger.json').read_bytes());mutate(ledger);overwrite(root/'ledger.json',ledger)
                with self.assertRaises(v.Invalid):self.assess(root)
        with self.assertRaisesRegex(v.Invalid,'RUNNER_EXIT_MISMATCH'):self.assess(self.fresh(),0)

    def test_real_receipt_timeout_exit_truncation_and_missing_final_reject(self):
        for key,value in (('timeout',True),('truncated',True),('exit',1),('child_exited',False),('drain_joined',False),('runner_sha256','0'*64)):
            with self.subTest(field=key):
                root=self.fresh();ledger=v.strict((root/'ledger.json').read_bytes());m=next(x for x in ledger['modules'] if len(x['invocations'])==2)
                folder=root/(Path(m['path']).stem+'-execution');rec=m['invocations'][1];rec[key]=value
                overwrite(folder/'launch-receipt.json',rec);overwrite(root/'ledger.json',ledger)
                with self.assertRaises(v.Invalid):self.assess(root)
        root=self.fresh();m=next(x for x in v.strict((root/'ledger.json').read_bytes())['modules'] if len(x['invocations'])==2)
        # Only a newly generated synthetic fixture is removed for this negative.
        (root/(Path(m['path']).stem+'-execution')/'result.json').unlink()
        with self.assertRaises(OSError):self.assess(root)

    def test_native_skip_and_partial_progress_cannot_be_invented(self):
        for kind in ('missing-progress','duplicate-start','class-skip-to-pass','partial','bad-log'):
            with self.subTest(kind=kind):
                root=self.fresh();ledger=v.strict((root/'ledger.json').read_bytes())
                m=next(x for x in ledger['modules'] if len(x['invocations'])==2 and (x['fixture_skips'] if kind=='class-skip-to-pass' else x['tests_run']>0))
                folder=root/(Path(m['path']).stem+'-execution');progress=folder/'progress.jsonl';raw=progress.read_bytes()
                if kind=='missing-progress':overwrite(progress,b'')
                elif kind=='duplicate-start':overwrite(progress,raw.splitlines()[0]+b'\n'+raw)
                elif kind=='partial':overwrite(progress,raw.splitlines()[0]+b'\n')
                elif kind=='bad-log':overwrite(folder/'output.log',b'forged log')
                else:
                    result=v.strict((folder/'result.json').read_bytes());result['fixture_skips']=[];result['results']=[dict(id=x,actual='PASS') for x in result['ids']];result['tests_run']=len(result['ids']);overwrite(folder/'result.json',result)
                with self.assertRaises(v.Invalid):self.assess(root)

    def test_enforce_revalidates_status_and_original_ledger(self):
        for kind in ('status-forgery','missing-status','ledger-changed','source-changed'):
            with self.subTest(kind=kind):
                root=self.fresh();status=self.assess(root)
                if kind=='status-forgery':status.update(all_required_status='PASS',release_eligible=True)
                if kind!='missing-status':write(root/'status.json',status)
                if kind=='ledger-changed':
                    ledger=v.strict((root/'ledger.json').read_bytes());ledger['counts']['PASS']+=1;overwrite(root/'ledger.json',ledger)
                if kind=='source-changed':
                    with patch.object(v,'lf',return_value='0'*64):
                        with self.assertRaises(v.Invalid):v.enforce(root/'status.json',root/'ledger.json','local','1',self.commit,synthetic=True)
                else:
                    with self.assertRaises((v.Invalid,OSError)):v.enforce(root/'status.json',root/'ledger.json','local','1',self.commit,synthetic=True)

    def test_ci_identity_and_synthetic_cannot_cross_boundary(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_WORKSPACE':str(v.ROOT),'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}):
            with self.assertRaisesRegex(v.Invalid,'SYNTHETIC_CI_FORBIDDEN'):
                v.scoped(self.template/'ledger.json',run_id='123',attempt='1',kind='ledger',synthetic=True)
            with self.assertRaisesRegex(v.Invalid,'CI_PATH_IDENTITY'):
                v.scoped(v.ROOT/'ci-results/rpf84-123-2/ledger.json',run_id='123',attempt='1',kind='ledger')

    def test_false_coverage_flag_cannot_replace_actual_dynamic_ids(self):
        for kind in ('missing','duplicate','new'):
            root=self.fresh();ledger=v.strict((root/'ledger.json').read_bytes());module=ledger['modules'][0]
            path=root/(Path(module['path']).stem+'-inventory')/'result.json'
            result=v.strict(path.read_bytes())
            if kind=='missing':result['ids'].pop()
            elif kind=='duplicate':result['ids'][1]=result['ids'][0]
            else:result['ids'][0]=result['ids'][0].rsplit('.',1)[0]+'.test_new'
            overwrite(path,result)
            self.assertTrue(ledger['coverage_verified'])
            with self.assertRaisesRegex(v.Invalid,'DYNAMIC_IDENTITY'):self.assess(root)

    def test_summary_appends_separate_blocker_and_rejects_escape(self):
        root=self.root/('summary-'+uuid.uuid4().hex);root.mkdir()
        path=root/'_runner_file_commands/step_summary_synthetic'
        original=b'RPF-12 original synthetic summary\n'
        write(path,original)
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','RUNNER_TEMP':str(root),'GITHUB_STEP_SUMMARY':str(path)}):
            v.summary('RELEASE_BLOCKED_BY_REQUIRED_COVERAGE; unavailable_required=539')
        text=path.read_bytes();self.assertTrue(text.startswith(original))
        self.assertIn(b'NO_RELEASE/NO_DEPLOY',text)
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','RUNNER_TEMP':str(root),'GITHUB_STEP_SUMMARY':str(v.ROOT/'outside.txt')}):
            with self.assertRaisesRegex(v.Invalid,'SUMMARY_SCOPE'):v.summary('blocked')

    def test_cli_actual_assess_zero_enforce_one_invalid_two_and_no_overwrite(self):
        root=self.fresh();base=[sys.executable,'-B',str(Path(v.__file__))]
        identity=['--ledger',str(root/'ledger.json'),'--run-id','local','--attempt','1','--commit',self.commit,'--synthetic']
        a=subprocess.run(base+['assess',*identity,'--runner-exit','1','--output',str(root/'status.json')],capture_output=True,timeout=60)
        b=subprocess.run(base+['enforce',*identity,'--status',str(root/'status.json')],capture_output=True,timeout=60)
        c=subprocess.run(base+['assess',*identity,'--runner-exit','1','--output',str(root/'status.json')],capture_output=True,timeout=60)
        self.assertEqual((a.returncode,b.returncode,c.returncode),(0,1,2))
        self.assertIn(b'CONTINUE_DIAGNOSTIC_ONLY',a.stdout)
        self.assertIn(b'RELEASE_BLOCKED_BY_REQUIRED_COVERAGE',b.stdout)
        write(root/'cli-receipt.json',dict(assess_exit=a.returncode,enforce_exit=b.returncode,occupied_exit=c.returncode,
              assess_stdout_sha256=v.digest(a.stdout),enforce_stdout_sha256=v.digest(b.stdout),
              synthetic_only=True,status_sha256=v.digest((root/'status.json').read_bytes())))


if __name__=='__main__':
    unittest.main()
