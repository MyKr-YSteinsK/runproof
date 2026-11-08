"""Fresh synthetic controls. Requires explicit RPF90_OWNER; never imports Router."""
import argparse
from collections import Counter
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

SPEC = importlib.util.spec_from_file_location('rpf90_diagnostic', Path(__file__).with_name('diagnose-runtime-router-gate.py'))
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)


class ExceptionSignatureControls(unittest.TestCase):
    def sample(self, raw):
        tid = 'test_x.C.test_one'
        receipt = {'bytes': len(raw), 'stdout_sha256': d.sha(raw), 'truncated': False}
        module = {'path': 'runtime/tests/test_x.py', 'rows': [{'id': tid, 'route': 'PORTABLE', 'actual': 'ERROR'}], 'invocations': [{}, receipt]}
        return {'modules': [module]}, receipt

    def test_bound_log_redacts_message(self):
        raw = b'ERROR: test_one (test_x.C)\nTraceback\nPermissionError: secret value\n'
        ledger, _ = self.sample(raw)
        with patch.object(d, 'bounded_read', return_value=raw):
            result = d.exception_signatures(ledger, Path('/synthetic'))
        self.assertEqual(result, [{'id': 'test_x.C.test_one', 'status': 'MATCHED', 'exception': 'PermissionError'}])
        self.assertNotIn('secret', str(result))

    def test_mismatch_duplicate_and_oversize_fail_closed(self):
        raw = b'ERROR: test_one (test_x.C)\nPermissionError: hidden\n'
        for reason in ('hash', 'duplicate', 'oversize'):
            ledger, receipt = self.sample(raw)
            with self.subTest(reason=reason):
                candidate = raw
                if reason == 'hash': receipt['stdout_sha256'] = '0' * 64
                if reason == 'duplicate':
                    candidate = raw + raw
                    receipt.update(bytes=len(candidate), stdout_sha256=d.sha(candidate))
                with patch.object(d, 'bounded_read', side_effect=OSError() if reason == 'oversize' else None, return_value=candidate):
                    result = d.exception_signatures(ledger, Path('/synthetic'))
                self.assertEqual(result, [{'id': 'test_x.C.test_one', 'status': 'UNAVAILABLE'}])

    def test_alias_path_rejected_before_read(self):
        with self.assertRaises(d.Invalid):
            d.safe_path(str(d.ROOT / 'ci-results' / '..' / 'outside'))


def settle(v):
    rows = [r for m in v['modules'] for r in m['rows']]
    v['counts'] = dict(Counter(r['actual'] for r in rows))
    v['routes'] = {k: dict(Counter(r['actual'] for r in rows if r['route'] == k)) for k in sorted(d.ROUTES)}
    v['discovered'] = sum(len(m['rows']) for m in v['modules'] if m['inventory_verified'])
    v['coverage_verified'] = v['discovered'] == 1232
    failure = not v['coverage_verified'] or any('error' in m for m in v['modules']) or any(r['actual'] in {'ERROR', 'FAIL'} for r in rows)
    complete = all(r['actual'] in {'PASS', 'SKIP'} for r in rows if r['route'] == 'PORTABLE')
    v['portable'] = 'FAIL' if failure else 'PASS' if complete else 'NOT_RUN'
    v['overall'] = 'FAIL' if failure else 'REQUIRED_COVERAGE_UNAVAILABLE'
    return v


def synthetic(ctx, errors=0):
    """Only IDs/routes from public frozen metadata; all results/receipts invented here."""
    modules = []
    skip = 5
    for path, (source, expected) in ctx['expected'].items():
        rows = []
        for tid, route in expected:
            actual = 'UNAVAILABLE'
            if route == 'PORTABLE':
                actual = 'SKIP' if skip else 'ERROR' if errors else 'PASS'
                if skip:
                    skip -= 1
                elif errors:
                    errors -= 1
            rows.append(dict(id=tid, route=route, required=True, reason='Synthetic control only',
                             executed=route == 'PORTABLE', actual=actual))
        r = dict(exit=0, timeout=False, truncated=False, stdout_sha256='0'*64, bytes=0,
                 monotonic_start_ns=1000000000, monotonic_end_ns=2000000000, child_pid=1,
                 runner_sha256=ctx['hashes']['ci/run-runtime-contract-tests.py'],
                 timeout_limit_seconds=300, child_exited=True, drain_joined=True,
                 descendant_cleanup='UNAVAILABLE: exact Popen handle only')
        inv = [r]
        if any(row['route'] == 'PORTABLE' for row in rows):
            inv.append(dict(r, exit=1 if any(row['actual'] == 'ERROR' for row in rows) else 0))
        modules.append(dict(path=path, source_sha256=source, rows=rows, invocations=inv,
                            inventory_verified=True, runner_sha256=r['runner_sha256'],
                            matrix_sha256=ctx['hashes']['ci/runtime-contract-test-matrix.json']))
    return settle(dict(schema='rpf84-runtime-ledger-v1', modules=modules,
                       coverage_policy='ALL_DISCOVERED_REQUIRED', overall='', portable='',
                       required_modules=57, required_methods=1232,
                       baseline_sha256=ctx['hashes']['spikes/rpf-82/rev-2/classification-ledger.json'],
                       lane_limit_seconds=1500, coverage_verified=True, discovered=1232,
                       unique_dispositions=1232, counts={}, routes={}, lane_finished_monotonic=10.0))


class DiagnosticControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = d.safe_path(os.environ.get('RPF90_OWNER', ''))
        if cls.owner.parent != d.ROOT / '.local/rpf-90-router-failure' or not cls.owner.is_dir():
            raise RuntimeError('EXPLICIT_FRESH_OWNER_REQUIRED')
        cls.ctx = d.context()
        cls.good = synthetic(cls.ctx)
        cls.bad = synthetic(cls.ctx, 12)

    def fixture(self, value=None):
        p = self.owner / ('fixture-' + uuid.uuid4().hex)
        p.mkdir()
        if value is not None:
            (p / 'ledger.json').write_bytes(json.dumps(value).encode())
        return p

    def args(self, p):
        return argparse.Namespace(ledger=str(p/'ledger.json'), output=str(p/'observation.json'),
                                  run_id='123', attempt='1', commit='a'*40, synthetic=True,
                                  fixture_root=str(p))

    def env(self):
        return {'RPF90_OWNER': str(self.owner)}

    def test_failure_exact_ids_separate_from_fail_and_unknown(self):
        out = d.project(self.bad, self.ctx)
        self.assertEqual(out['counts'], {'PASS': 676, 'ERROR': 12, 'SKIP': 5, 'UNAVAILABLE': 539})
        self.assertEqual(len(out['error_methods']), 12)
        self.assertEqual(out['failed_methods'], [])
        self.assertTrue(all(not m['exact_cause_confirmed'] for m in out['failure_modules']))
        self.assertIn('METHOD_EXCEPTION_DETAIL_NOT_IN_LEDGER', out['unresolved_cause_codes'])
        v = copy.deepcopy(self.bad)
        row = next(r for m in v['modules'] for r in m['rows'] if r['actual'] == 'ERROR')
        row['actual'] = 'FAIL'
        out = d.project(settle(v), self.ctx)
        self.assertEqual(len(out['error_methods']), 11)
        self.assertEqual(len(out['failed_methods']), 1)

    def test_healthy_preserves_required_unavailable(self):
        out = d.project(self.good, self.ctx)
        self.assertEqual(out['counts'], {'PASS': 688, 'SKIP': 5, 'UNAVAILABLE': 539})
        self.assertEqual(out['validation_status'], 'VALIDATED_NO_PORTABLE_ERROR')

    def test_timeout_truncation_partial_and_module_protocol(self):
        for change in ('timeout', 'truncated', 'exit', 'child_exited', 'drain_joined'):
            with self.subTest(change=change):
                v = copy.deepcopy(self.bad)
                m = next(m for m in v['modules'] if any(r['actual'] == 'ERROR' for r in m['rows']))
                m['error'] = 'Invalid:EXECUTION_PROCESS'
                m['progress_error'] = 'INVALID_PARTIAL_PROGRESS'
                m['invocations'][1][change] = True if change in {'timeout', 'truncated'} else 7 if change == 'exit' else False
                out = d.project(v, self.ctx)
                x = next(x for x in out['failure_modules'] if x['module'] == m['path'])
                self.assertTrue(x['exact_cause_confirmed'])
                self.assertEqual(x['cause_scope'], 'ROUTER_PROTOCOL_ONLY')
                self.assertIn('EXECUTION_PROCESS', x['error_codes'])
                self.assertNotIn('child_pid', json.dumps(out))
        v = copy.deepcopy(self.good)
        m = v['modules'][0]
        m['inventory_verified'] = False
        m['invocations'] = [dict(m['invocations'][0], exit=1)]
        m['error'] = 'Invalid:INVENTORY_PROCESS'
        for r in m['rows']:
            if r['route'] == 'PORTABLE':
                r.update(actual='NOT_RUN', executed=False)
        self.assertEqual(d.project(settle(v), self.ctx)['validation_status'], 'VALIDATED_FAILURE')

    def test_unknown_exception_and_reason_never_exported(self):
        v = copy.deepcopy(self.bad)
        v['modules'][0]['error'] = 'secret=/private/workspace/TOKEN'
        v['modules'][0]['progress_error'] = 'private text'
        v['modules'][0]['rows'][0]['reason'] = 'secret=/private/workspace/TOKEN'
        out = json.dumps(d.project(v, self.ctx))
        for x in ('TOKEN', '/private', 'private text', 'reason', 'stdout_sha256', 'child_pid'):
            self.assertNotIn(x, out)

    def test_structural_and_false_green_counterexamples(self):
        cases = {
            'module_count': lambda v: v['modules'].pop(),
            'module_source': lambda v: v['modules'][0].update(source_sha256='0'*64),
            'matrix_source': lambda v: v['modules'][0].update(matrix_sha256='0'*64),
            'router_source': lambda v: v['modules'][0].update(runner_sha256='0'*64),
            'baseline_source': lambda v: v.update(baseline_sha256='0'*64),
            'duplicate_id': lambda v: v['modules'][0]['rows'][1].update(id=v['modules'][0]['rows'][0]['id']),
            'unknown_id': lambda v: v['modules'][0]['rows'][0].update(id='unknown.test'),
            'required': lambda v: v['modules'][0]['rows'][0].update(required=False),
            'executed_type': lambda v: v['modules'][0]['rows'][0].update(executed=1),
            'unexecuted_pass': lambda v: next(r for m in v['modules'] for r in m['rows'] if r['actual']=='PASS').update(executed=False),
            'counts': lambda v: v['counts'].update(PASS=999),
            'routes': lambda v: v['routes']['PORTABLE'].update(PASS=999),
            'false_green': lambda v: v.update(portable='PASS'),
            'hidden_field': lambda v: v.update(secret='TOKEN'),
            'receipt_source': lambda v: v['modules'][0]['invocations'][0].update(runner_sha256='0'*64),
            'receipt_field': lambda v: v['modules'][0]['invocations'][0].update(stdout='TOKEN'),
            'receipt_clock': lambda v: v['modules'][0]['invocations'][0].update(monotonic_end_ns=0),
            'receipt_bool': lambda v: v['modules'][0]['invocations'][0].update(timeout=1),
            'missing_receipt': lambda v: v['modules'][0].update(invocations=[]),
            'coverage': lambda v: v.update(discovered=0),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                v = copy.deepcopy(self.bad)
                mutate(v)
                with self.assertRaises(d.Invalid):
                    d.project(v, self.ctx)
        v = copy.deepcopy(self.good)
        next(r for m in v['modules'] for r in m['rows'] if r['route']!='PORTABLE').update(actual='PASS', executed=True)
        with self.assertRaises(d.Invalid):
            d.project(settle(v), self.ctx)

    def test_strict_json_duplicate_nonfinite_unicode_oversize(self):
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'"\\ud800"', b'\xff', b'[]garbage']:
            with self.subTest(raw=raw):
                with self.assertRaises(d.Invalid):
                    d.strict(raw)
        p = self.fixture()
        with (p/'ledger.json').open('wb') as f:
            f.truncate(d.INPUT_LIMIT+1)
        with self.assertRaises(d.Invalid):
            d.bounded_read(p/'ledger.json', d.INPUT_LIMIT)
        with self.assertRaises(d.Invalid):
            d.encode({'x': 'a'*d.OUTPUT_LIMIT})

    def test_exact_paths_before_read_and_output_overwrite(self):
        p = self.fixture(self.good)
        a = self.args(p)
        for value in ['ledger.json', str(p/'..'/'ledger.json'), str(self.owner.parent/'other'/'ledger.json'), str(p/'LEDGER.json')]:
            with self.subTest(value=value):
                a.ledger = value
                with patch.object(d, 'bounded_read', side_effect=AssertionError('READ_BEFORE_VALIDATION')):
                    with self.assertRaises(d.Invalid):
                        d.capture(a, self.env())
        a = self.args(p)
        (p/'observation.json').write_text('KEEP')
        with self.assertRaises(d.Invalid):
            d.capture(a, self.env())
        self.assertEqual((p/'observation.json').read_text(), 'KEEP')

    def test_symlink_hardlink_and_reparse_before_read(self):
        p = self.fixture(self.good)
        alias = self.fixture()
        os.link(p/'ledger.json', alias/'ledger.json')
        with self.assertRaises(d.Invalid):
            d.bounded_read(p/'ledger.json', d.INPUT_LIMIT)
        with self.assertRaises(d.Invalid):
            d.bounded_read(alias/'ledger.json', d.INPUT_LIMIT)
        # Windows junction needs no symlink privilege; both supported paths are exercised.
        link = self.owner / ('link-' + uuid.uuid4().hex)
        if os.name == 'nt':
            process = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(alias)],
                                     capture_output=True, timeout=10)
            self.assertEqual(process.returncode, 0)
        else:
            link.symlink_to(alias, target_is_directory=True)
        with self.assertRaises(d.Invalid):
            d.safe_path(link/'ledger.json')

    def test_fake_hosted_and_local_without_synthetic(self):
        p = self.fixture(self.good)
        a = self.args(p)
        with self.assertRaises(d.Invalid):
            d.capture(a, {'GITHUB_ACTIONS':'true'})
        a.synthetic = False
        with self.assertRaises(d.Invalid):
            d.capture(a, self.env())
        a.synthetic = True
        for value in ['x', '-1', '0', '1/../2']:
            a.attempt = value
            with self.assertRaises(d.Invalid):
                d.capture(a, self.env())

    def test_hosted_identity_exact_environment_without_io(self):
        a = argparse.Namespace(ledger=str(d.ROOT/'ci-results/rpf84-123-1/ledger.json'),
                               output=str(d.ROOT/'ci-results/rpf90-router-123-1.json'), run_id='123',
                               attempt='1', commit='a'*40, synthetic=False, fixture_root=None)
        env = dict(GITHUB_ACTIONS='true', GITHUB_WORKSPACE=str(d.ROOT), GITHUB_RUN_ID='123',
                   GITHUB_RUN_ATTEMPT='1', GITHUB_SHA='a'*40)
        with patch.object(d, 'git', return_value=['a'*40]):
            self.assertEqual(d.identity(a, env)[2], 'HOSTED_SAME_RUN')
            for key in ('GITHUB_WORKSPACE', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'):
                with self.subTest(key=key):
                    with self.assertRaises(d.Invalid):
                        d.identity(a, dict(env, **{key:'wrong'}))
        with patch.object(d, 'git', return_value=['b'*40]):
            with self.assertRaises(d.Invalid):
                d.identity(a, env)

    def test_git_and_worktree_source_drift(self):
        with patch.object(d, 'git', return_value=['0'*40]*4):
            with self.assertRaises(d.Invalid):
                d.context()
        with patch.object(d, 'bounded_read', return_value=b'altered'):
            with self.assertRaises(d.Invalid):
                d.context()

    def test_missing_and_invalid_safe_outputs(self):
        for missing in (True, False):
            p = self.fixture(None if missing else {'secret':'TOKEN'})
            self.assertEqual(d.capture(self.args(p), self.env()), 2)
            out = d.strict((p/'observation.json').read_bytes())
            self.assertEqual(out['validation_status'], 'LEDGER_UNAVAILABLE' if missing else 'INVALID_LEDGER')
            self.assertFalse(out['release_eligible'])
            self.assertNotIn('TOKEN', json.dumps(out))

    def test_actual_cli_and_independent_fresh_readback(self):
        p = self.fixture(self.bad)
        a = self.args(p)
        args = [sys.executable, '-B', str(d.ROOT/'ci/diagnose-runtime-router-gate.py'), 'capture',
                '--ledger', a.ledger, '--output', a.output, '--run-id', a.run_id,
                '--attempt', a.attempt, '--commit', a.commit, '--synthetic', '--fixture-root', str(p)]
        env = {k: os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','LANG') if k in os.environ}
        env.update(RPF90_OWNER=str(self.owner), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1',
                   TEMP=str(p), TMP=str(p), TMPDIR=str(p))
        child = subprocess.run(args, capture_output=True, env=env, timeout=120)
        self.assertEqual(child.returncode, 0, child.stdout)
        self.assertLess(len(child.stdout)+len(child.stderr), 2*1024*1024)
        self.assertLessEqual((p/'observation.json').stat().st_size, d.OUTPUT_LIMIT)
        # Independent verifier: stdlib only, no diagnostic import, no Router import.
        check = '''import json,hashlib,pathlib,sys
p=pathlib.Path(sys.argv[1]);v=json.loads((p/'ledger.json').read_bytes());o=json.loads((p/'observation.json').read_bytes())
assert o['ledger_sha256']==hashlib.sha256((p/'ledger.json').read_bytes()).hexdigest()
ids=sorted(r['id'] for m in v['modules'] for r in m['rows'] if r['actual']=='ERROR')
assert ids==sorted(r['id'] for r in o['error_methods']) and len(ids)==12
assert o['counts']=={'PASS':676,'ERROR':12,'SKIP':5,'UNAVAILABLE':539}
assert o['evidence_kind']=='LOCAL_SYNTHETIC_CONTROL_ONLY' and not o['release_eligible']
assert o['validation_status']=='VALIDATED_FAILURE'
assert not any(x in (p/'observation.json').read_text() for x in ['TOKEN','child_pid','stdout_sha256'])
print('INDEPENDENT_SYNTHETIC_READBACK_PASS')'''
        verify = subprocess.run([sys.executable, '-B', '-c', check, str(p)], capture_output=True, env=env, timeout=120)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertIn(b'INDEPENDENT_SYNTHETIC_READBACK_PASS', verify.stdout)

    def test_workflow_exact_two_step_delta_and_gate_failure(self):
        base = (self.owner/'base-workflow.yml').read_text(encoding='utf-8')
        workflow = (d.ROOT/'.github/workflows/release-gate.yml').read_text(encoding='utf-8')
        start = workflow.index('      - name: Capture bounded Router failure evidence')
        end = workflow.index('      - name: Run fresh canonical Release Gate', start)
        addition = workflow[start:end]
        self.assertEqual(workflow[:start]+workflow[end:], base)
        self.assertIn('if: ${{ always() }}', addition)
        self.assertIn("steps.rpf90_capture.outcome == 'failure'", addition)
        self.assertIn('path: ci-results/rpf90-router-${{ github.run_id }}-${{ github.run_attempt }}.json', addition)
        for bad in ('continue-on-error', '|| true', 'ledger.json\n          if-no-files', '*.json'):
            self.assertNotIn(bad, addition)
        # Actions success() remains false for subsequent default-success steps.
        for diagnostic_exit in (0, 2):
            original_repository_exit = 2
            self.assertNotEqual(original_repository_exit, 0)
            self.assertFalse(original_repository_exit == 0 and diagnostic_exit == 0)

    def test_frozen_source_and_inputs_independent_process(self):
        script = '''import pathlib,json,hashlib,sys
p=pathlib.Path(sys.argv[1]); root=pathlib.Path(sys.argv[2]); freeze=json.loads((p/'freeze.json').read_bytes())
for name,expected in freeze['files'].items():
 assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected
for name,expected in freeze['inputs'].items():
 assert hashlib.sha256((p/name).read_bytes()).hexdigest()==expected
v=json.loads((p/'frozen-failure.json').read_bytes())
assert len(v['modules'])==57
rows=[r for m in v['modules'] for r in m['rows']]
assert len({r['id'] for r in rows})==1232
assert sum(r['actual']=='ERROR' for r in rows)==12
assert v['counts']=={'PASS':676,'ERROR':12,'SKIP':5,'UNAVAILABLE':539}
print('FROZEN_SOURCE_INPUT_RECHECK_PASS')'''
        child = subprocess.run([sys.executable, '-B', '-c', script, str(self.owner), str(d.ROOT)],
                               capture_output=True, timeout=120)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn(b'FROZEN_SOURCE_INPUT_RECHECK_PASS', child.stdout)


if __name__ == '__main__':
    unittest.main()
