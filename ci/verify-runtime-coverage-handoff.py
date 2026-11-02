"""Verify RPF84 receipts before diagnostic continuation; never waive coverage.

Only stdlib, Git metadata and explicitly bounded current-source/receipt reads.
Local synthetic fixtures are labelled and cannot be admitted in GitHub Actions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / '.local/rpf-85-coverage-handoff'
RUNNER = ROOT / 'ci/run-runtime-contract-tests.py'
MATRIX = ROOT / 'ci/runtime-contract-test-matrix.json'
BASELINE = ROOT / 'spikes/rpf-82/rev-2/classification-ledger.json'
MAX_JSON = 8 * 1024 * 1024
MAX_LOG = 2 * 1024 * 1024
RUNNER_BLOB = '88396fa78d73ba091e91992d4d51263063a95aa7'
MATRIX_BLOB = 'ed827c3dc354c18c9d4b7bc63384805e50e97785'


class Invalid(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Invalid(code)


def strict(raw):
    need(isinstance(raw, bytes) and 0 < len(raw) <= MAX_JSON, 'JSON_SIZE')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(Invalid('NONFINITE_JSON')))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def lf(path):
    return digest(path.read_bytes().replace(b'\r\n', b'\n'))


def git(*args):
    p = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, timeout=10)
    need(p.returncode == 0, 'GIT_PRECONDITION')
    return p.stdout


def nonlink(path):
    for item in (path, *path.parents):
        need(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(), 'REPARSE')
        if item.exists():
            need(not bool(getattr(item.lstat(), 'st_file_attributes', 0) & 1024), 'REPARSE')


def scoped(path, *, run_id, attempt, kind, synthetic=False):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'PATH_LEXICAL')
    ci = os.environ.get('GITHUB_ACTIONS') == 'true'
    need(re.fullmatch(r'[A-Za-z0-9-]+', run_id) is not None
         and re.fullmatch(r'[0-9]+', attempt) is not None, 'RUN_IDENTITY')
    if ci:
        need(not synthetic and run_id.isdecimal() and run_id.isascii(), 'SYNTHETIC_CI_FORBIDDEN')
        need(os.environ.get('GITHUB_WORKSPACE') == str(ROOT)
             and os.environ.get('GITHUB_RUN_ID') == run_id
             and os.environ.get('GITHUB_RUN_ATTEMPT') == attempt, 'CI_IDENTITY')
        expected = (ROOT / 'ci-results' / f'rpf84-{run_id}-{attempt}' / 'ledger.json'
                    if kind == 'ledger' else ROOT / 'ci-results' / f'rpf85-coverage-{run_id}-{attempt}.json')
        need(path == expected, 'CI_PATH_IDENTITY')
    else:
        need(path != OWNER and path.is_relative_to(OWNER), 'LOCAL_OWNER_SCOPE')
    # Scope is checked lexically before any target metadata or file IO.
    nonlink(path)
    need(path.resolve().is_relative_to((ROOT / 'ci-results' if ci else OWNER).resolve()), 'PATH_ESCAPE')
    return path


def read_bound(path, root, *, limit=MAX_JSON):
    need(path.is_relative_to(root) and '..' not in path.parts, 'EVIDENCE_SCOPE')
    nonlink(path)
    need(path.resolve().is_relative_to(root.resolve()), 'EVIDENCE_ESCAPE')
    with path.open('rb') as source:
        raw = source.read(limit + 1)
    need(len(raw) <= limit, 'EVIDENCE_SIZE')
    return raw


def sources():
    # Import only the pinned stdlib supervisor, never a Runtime test module.
    for path, pin in ((RUNNER, RUNNER_BLOB), (MATRIX, MATRIX_BLOB)):
        need(git('rev-parse', 'HEAD:' + path.relative_to(ROOT).as_posix()).decode().strip() == pin, 'GIT_SOURCE_BINDING')
        raw = git('cat-file', 'blob', pin)
        need(raw.replace(b'\r\n', b'\n') == path.read_bytes().replace(b'\r\n', b'\n'), 'PINNED_SOURCE_DRIFT')
    spec = importlib.util.spec_from_file_location('rpf85_pinned_router', RUNNER)
    router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    files = git('ls-files', '--', 'runtime/tests/test_*.py').decode('utf8').splitlines()
    need(not git('diff', 'HEAD', '--name-only', '--', *files).strip(), 'TEST_TREE_DRIFT')
    matrix = router.validate_matrix(router.strict(MATRIX.read_bytes()), files)
    required = router.required_inventory(files)
    return router, matrix, required


RECEIPT_KEYS = {'exit', 'timeout', 'truncated', 'stdout_sha256', 'bytes',
                'monotonic_start_ns', 'monotonic_end_ns', 'child_pid',
                'runner_sha256', 'timeout_limit_seconds', 'child_exited',
                'drain_joined', 'descendant_cleanup'}


def invocation(folder, root, declared, runner_sha, anchors):
    raw = read_bound(folder / 'launch-receipt.json', root)
    value = strict(raw)
    need(value == declared and set(value) == RECEIPT_KEYS, 'RECEIPT_BINDING')
    need(type(value['exit']) is int and value['exit'] == 0, 'CHILD_EXIT')
    need(value['timeout'] is False and value['truncated'] is False
         and value['child_exited'] is True and value['drain_joined'] is True, 'CHILD_UNSETTLED')
    for key in ('monotonic_start_ns', 'monotonic_end_ns', 'child_pid', 'bytes'):
        need(type(value[key]) is int and value[key] >= (1 if key != 'bytes' else 0), 'RECEIPT_NUMBER')
    need(value['monotonic_end_ns'] >= value['monotonic_start_ns'], 'CHILD_CLOCK')
    duration = (value['monotonic_end_ns'] - value['monotonic_start_ns']) / 1e9
    budget = value['timeout_limit_seconds']
    need(type(budget) in (int, float) and math.isfinite(budget) and 0 < budget <= 300
         and duration <= budget + 5.1, 'CHILD_BUDGET')
    need(value['runner_sha256'] == runner_sha, 'RUNNER_SOURCE')
    log = read_bound(folder / 'output.log', root, limit=MAX_LOG)
    need(value['bytes'] == len(log) and value['stdout_sha256'] == digest(log), 'OUTPUT_BINDING')
    anchors[folder.name + '/launch-receipt.json'] = digest(raw)
    anchors[folder.name + '/output.log'] = digest(log)
    result_raw = read_bound(folder / 'result.json', root)
    anchors[folder.name + '/result.json'] = digest(result_raw)
    return strict(result_raw), value


def native_events(selected, report, raw):
    """Independent reconstruction from native Result events, not row labels."""
    lines = raw.splitlines()
    need(len(lines) <= 20000, 'PROGRESS_SIZE')
    events = [strict(line) for line in lines]
    states, fixtures = {}, {}
    for e in events:
        need(type(e) is dict and set(e) == {'id', 'actual'}, 'PROGRESS_SCHEMA')
        tid, actual = e['id'], e['actual']
        need(type(tid) is str and actual in {'STARTED', 'PASS', 'FAIL', 'ERROR', 'SKIP'}, 'PROGRESS_STATUS')
        if tid in selected:
            if actual == 'STARTED':
                need(tid not in states, 'DUPLICATE_START')
            else:
                need(states.get(tid) == 'STARTED', 'UNOBSERVED_TERMINAL')
            states[tid] = actual
        else:
            match = re.fullmatch(r'setUp(Class|Module) \(([A-Za-z0-9_.]+)\)', tid)
            need(match is not None and actual == 'SKIP' and tid not in fixtures, 'FIXTURE_EVENT')
            matching = [x for x in selected if x.startswith(match.group(2) + '.')]
            need(bool(matching), 'UNRELATED_FIXTURE')
            fixtures[tid] = matching
    skipped = [x for ids in fixtures.values() for x in ids]
    need(len(skipped) == len(set(skipped)) and set(skipped) == set(report['fixture_skips']), 'FIXTURE_SKIP_BINDING')
    need(type(report['tests_run']) is int and report['tests_run'] == len(states), 'TESTS_RUN_BINDING')
    observed = {}
    for tid in selected:
        if tid in skipped:
            need(tid not in states, 'FIXTURE_STARTED_CONFLICT')
            observed[tid] = ('SKIP', False)
        else:
            need(states.get(tid) in {'PASS', 'SKIP'}, 'PORTABLE_NOT_PASSED')
            observed[tid] = (states[tid], True)
    need(report['results'] == [dict(id=x, actual=observed[x][0]) for x in selected], 'RESULT_EVENT_BINDING')
    return observed, events


def assess(ledger_path, runner_exit, run_id, attempt, commit, *, synthetic=False):
    ledger_path = scoped(ledger_path, run_id=run_id, attempt=attempt, kind='ledger', synthetic=synthetic)
    need(re.fullmatch(r'[0-9a-f]{40}', commit) is not None and git('rev-parse', 'HEAD').decode().strip() == commit, 'COMMIT_IDENTITY')
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        need(os.environ.get('GITHUB_SHA') == commit, 'CI_COMMIT')
    root = ledger_path.parent
    raw = read_bound(ledger_path, root)
    ledger = strict(raw)
    router, matrix, required = sources()
    expected_top = {'schema', 'modules', 'coverage_policy', 'overall', 'portable', 'required_modules',
                    'required_methods', 'baseline_sha256', 'lane_limit_seconds', 'coverage_verified',
                    'discovered', 'unique_dispositions', 'counts', 'routes', 'lane_finished_monotonic'}
    need(type(ledger) is dict and set(ledger) == expected_top, 'LEDGER_SCHEMA')
    need(ledger['schema'] == 'rpf84-runtime-ledger-v1' and ledger['coverage_policy'] == 'ALL_DISCOVERED_REQUIRED', 'COVERAGE_POLICY')
    need(ledger['required_modules'] == 57 and ledger['required_methods'] == 1232
         and ledger['discovered'] == ledger['unique_dispositions'] == 1232
         and ledger['coverage_verified'] is True, 'REQUIRED_IDENTITY')
    need(ledger['baseline_sha256'] == lf(BASELINE) and ledger['lane_limit_seconds'] == 1500, 'BASELINE_BINDING')
    need(type(ledger['modules']) is list and len(ledger['modules']) == 57, 'MODULE_COUNT')
    need(all(type(m) is dict for m in ledger['modules']), 'MODULE_SCHEMA')
    need([m.get('path') for m in ledger['modules']] == [m['path'] for m in matrix['modules']], 'MODULE_IDENTITY')
    runner_sha, matrix_sha = lf(RUNNER), lf(MATRIX)
    anchors = {}
    all_rows, clocks = [], []
    for module, declaration in zip(ledger['modules'], matrix['modules']):
        path = declaration['path']
        expected = router.classify(declaration, required[path])
        portable = [r['id'] for r in expected if r['route'] == 'PORTABLE']
        module_keys = {'path', 'source_sha256', 'rows', 'invocations', 'inventory_verified', 'runner_sha256', 'matrix_sha256'}
        need(set(module) == module_keys | ({'tests_run', 'fixture_skips'} if portable else set()), 'MODULE_SCHEMA')
        need(module['inventory_verified'] is True and module['source_sha256'] == declaration['source_sha256']
             and module['runner_sha256'] == runner_sha and module['matrix_sha256'] == matrix_sha, 'MODULE_PROVENANCE')
        need(type(module['invocations']) is list and len(module['invocations']) == (2 if portable else 1), 'INVOCATION_COUNT')
        stem = Path(path).stem
        inventory, rec = invocation(root / (stem + '-inventory'), root, module['invocations'][0], runner_sha, anchors)
        clocks.append(rec)
        need(type(inventory) is dict and set(inventory) == {'ids'} and inventory['ids'] == required[path], 'DYNAMIC_IDENTITY')
        observed = {}
        if portable:
            folder = root / (stem + '-execution')
            result, rec = invocation(folder, root, module['invocations'][1], runner_sha, anchors)
            clocks.append(rec)
            selection_raw = read_bound(root / (stem + '-selection.json'), root)
            child_selection_raw = read_bound(folder / 'selection.json', root)
            need(selection_raw == child_selection_raw
                 and strict(selection_raw) == {'inventory': required[path], 'selected': portable}, 'SELECTION_BINDING')
            anchors[stem + '-selection.json'] = digest(selection_raw)
            progress = read_bound(folder / 'progress.jsonl', root)
            anchors[stem + '-execution/progress.jsonl'] = digest(progress)
            need(type(result) is dict and set(result) == {'ids', 'results', 'tests_run', 'successful', 'fixture_skips'}
                 and result['ids'] == portable and result['successful'] is True, 'EXECUTION_REPORT')
            observed, events = native_events(portable, result, progress)
            router.reconcile(portable, result, rec['exit'], events)  # second, pinned implementation
            need(module['tests_run'] == result['tests_run'] and module['fixture_skips'] == result['fixture_skips'], 'MODULE_SETTLEMENT')
        need(type(module['rows']) is list and len(module['rows']) == len(expected), 'METHOD_COUNT')
        for row, old in zip(module['rows'], expected):
            need(type(row) is dict and set(row) == set(old), 'ROW_SCHEMA')
            need(all(row[k] == old[k] for k in ('id', 'route', 'reason')) and row['required'] is True, 'METHOD_ROUTE_IDENTITY')
            if row['route'] == 'PORTABLE':
                actual, executed = observed[row['id']]
                need(row['actual'] == actual and row['executed'] is executed, 'ROW_EXECUTION')
            else:
                need(row['actual'] == 'UNAVAILABLE' and row['executed'] is False, 'UNAVAILABLE_RELABELED')
            all_rows.append(row)
    need(len(all_rows) == len({x['id'] for x in all_rows}) == 1232, 'UNIQUE_REQUIRED_IDS')
    need(all(a['monotonic_end_ns'] <= b['monotonic_start_ns'] for a, b in zip(clocks, clocks[1:])), 'CHILD_CHRONOLOGY')
    finish = ledger['lane_finished_monotonic']
    need(type(finish) in (int, float) and math.isfinite(finish)
         and clocks[-1]['monotonic_end_ns'] / 1e9 <= finish
         and finish - clocks[0]['monotonic_start_ns'] / 1e9 <= 1505.1, 'LANE_CLOCK')
    counts = dict(Counter(x['actual'] for x in all_rows))
    routes = {route: dict(Counter(x['actual'] for x in all_rows if x['route'] == route)) for route in sorted(router.ROUTES)}
    need(type(ledger['counts']) is dict and all(type(n) is int for n in ledger['counts'].values())
         and type(ledger['routes']) is dict and all(type(c) is dict and all(type(n) is int for n in c.values())
                                                 for c in ledger['routes'].values()), 'AGGREGATE_TYPES')
    need(ledger['counts'] == counts and ledger['routes'] == routes, 'AGGREGATE_MISMATCH')
    unavailable = counts.get('UNAVAILABLE', 0)
    need(ledger['portable'] == 'PASS' and ledger['overall'] == ('REQUIRED_COVERAGE_UNAVAILABLE' if unavailable else 'PASS'), 'LANE_STATUS')
    need(type(runner_exit) is int and runner_exit == (1 if unavailable else 0), 'RUNNER_EXIT_MISMATCH')
    anchors['ledger.json'] = digest(raw)
    return dict(schema='rpf85-coverage-handoff-v1', run_id=run_id, attempt=attempt, commit=commit,
                router_exit=runner_exit, router_ledger_sha256=digest(raw), counts=counts, routes=routes,
                portable_status='PASS', all_required_status='UNAVAILABLE' if unavailable else 'PASS',
                diagnostic_continuation='CONTINUE_DIAGNOSTIC_ONLY', release_eligible=False,
                release_executed=False, deployment_authorized=False, unavailable_required_count=unavailable,
                reason='RELEASE_BLOCKED_BY_REQUIRED_COVERAGE' if unavailable else 'COVERAGE_ONLY_NOT_RELEASE_AUTHORITY',
                evidence_kind='SYNTHETIC_OFFLINE_TEST' if synthetic else 'ROUTER_PROCESS_RECEIPTS',
                source_validation=dict(modules=57, required_methods=1232, runner_lf_sha256=runner_sha,
                                       matrix_lf_sha256=matrix_sha, baseline_lf_sha256=lf(BASELINE),
                                       verifier_lf_sha256=lf(Path(__file__))),
                evidence_manifest_sha256=digest(json.dumps(anchors, sort_keys=True, separators=(',', ':')).encode()),
                bounded_summary='Portable evidence verified; required gaps retain the global blocker. NO_RELEASE/NO_DEPLOY.')


def enforce(status_path, ledger_path, run_id, attempt, commit, *, synthetic=False):
    status_path = scoped(status_path, run_id=run_id, attempt=attempt, kind='status', synthetic=synthetic)
    status = strict(read_bound(status_path, status_path.parent))
    need(type(status) is dict and type(status.get('router_exit')) is int, 'STATUS_SCHEMA')
    expected = assess(ledger_path, status['router_exit'], run_id, attempt, commit, synthetic=synthetic)
    need(status == expected, 'STATUS_REVALIDATION')
    return (0 if status['all_required_status'] == 'PASS' else 1), status


def summary(text):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return
    raw = os.environ.get('GITHUB_STEP_SUMMARY', '')
    temp = os.environ.get('RUNNER_TEMP', '')
    need(bool(raw) and bool(temp), 'SUMMARY_CONTEXT')
    path, base = Path(raw), Path(temp)
    need(path.is_absolute() and path.is_relative_to(base) and '..' not in path.parts
         and path.name.startswith('step_summary_'), 'SUMMARY_SCOPE')
    nonlink(path)
    with path.open('a', encoding='utf8') as out:
        out.write('\n### RPF-85 Required Runtime coverage\n\n' + text + '\n\nNO_RELEASE/NO_DEPLOY.\n')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('assess', 'enforce'):
        parser = sub.add_parser(command)
        parser.add_argument('--ledger', type=Path, required=True)
        parser.add_argument('--run-id', required=True)
        parser.add_argument('--attempt', required=True)
        parser.add_argument('--commit', required=True)
        parser.add_argument('--synthetic', action='store_true')
        if command == 'assess':
            parser.add_argument('--runner-exit', type=int, required=True)
            parser.add_argument('--output', type=Path, required=True)
        else:
            parser.add_argument('--status', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.command == 'assess':
            output = scoped(a.output, run_id=a.run_id, attempt=a.attempt, kind='status', synthetic=a.synthetic)
            need(not os.path.lexists(output), 'OUTPUT_OCCUPIED')
            result = assess(a.ledger, a.runner_exit, a.run_id, a.attempt, a.commit, synthetic=a.synthetic)
            with output.open('x', encoding='utf8') as out:
                json.dump(result, out, indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
            print('CONTINUE_DIAGNOSTIC_ONLY; ALL_REQUIRED=' + result['all_required_status'])
            return 0
        code, result = enforce(a.status, a.ledger, a.run_id, a.attempt, a.commit, synthetic=a.synthetic)
        text = result['reason'] + '; unavailable_required=' + str(result['unavailable_required_count'])
        summary(text)
        print(text + '; NO_RELEASE/NO_DEPLOY')
        return code
    except (Invalid, OSError, ValueError, TypeError, KeyError, IndexError, RecursionError,
            subprocess.SubprocessError) as exc:
        # No free exception/path/traceback text is exported to public CI.
        code = str(exc) if isinstance(exc, Invalid) else type(exc).__name__
        print('INVALID_COVERAGE_EVIDENCE:' + code, file=sys.stderr)
        if a.command == 'enforce':
            try:
                summary('RELEASE_BLOCKED_BY_REQUIRED_COVERAGE; evidence INVALID')
            except (Invalid, OSError):
                pass  # The process still fails closed with exit 2.
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
