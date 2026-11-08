#!/usr/bin/env python3
"""Bounded same-run Router ledger projection; never executes Router or tests."""
import argparse
import ast
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).absolute().parents[1]
PINS = {
    'ci/run-runtime-contract-tests.py': 'ccf8d56b32aedb9ea7e5b5f3a4d4f07ae8b9ce51',
    'ci/runtime-contract-test-matrix.json': 'ed827c3dc354c18c9d4b7bc63384805e50e97785',
    'ci/verify-runtime-coverage-handoff.py': '80e0220af74711cde4f91cfbd3c6102fe52b13c2',
    'spikes/rpf-82/rev-2/classification-ledger.json': '51fefc01b4c4d3b465f7b7584b8384e1b9994c78',
}
ROUTES = {'PORTABLE', 'WINDOWS_NATIVE', 'DEDICATED_RUNNER',
          'LEGACY_SDK_PRECONDITION', 'FROZEN_PRIVATE_ARTIFACT', 'LEGACY_OWNER_ROOT'}
ACTUAL = {'PASS', 'FAIL', 'ERROR', 'SKIP', 'NOT_RUN', 'UNAVAILABLE'}
INPUT_LIMIT = 8 * 1024 * 1024
OUTPUT_LIMIT = 64 * 1024


class Invalid(Exception):
    """Only fixed program-owned codes may leave the CLI."""


def need(value, code):
    if not value:
        raise Invalid(code)


def strict(raw):
    def pairs(items):
        d = {}
        for k, v in items:
            need(k not in d, 'DUPLICATE_KEY')
            d[k] = v
        return d
    def constant(_):
        raise Invalid('NONFINITE_JSON')
    try:
        value = json.loads(raw.decode('utf-8', errors='strict'),
                           object_pairs_hook=pairs, parse_constant=constant)
        def check(v):
            if isinstance(v, str):
                v.encode('utf-8', errors='strict')
            elif type(v) is float:
                need(math.isfinite(v), 'NONFINITE_JSON')
            elif type(v) is dict:
                for k, x in v.items():
                    check(k)
                    check(x)
            elif type(v) is list:
                for x in v:
                    check(x)
        check(value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise Invalid('INVALID_JSON') from None


def safe_path(path):
    """Reject aliases and reparse components before opening any supplied file."""
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts and str(p) == str(path), 'PATH_ALIAS')
    for q in (p, *p.parents):
        try:
            s = q.lstat()
        except FileNotFoundError:
            continue
        need(not stat.S_ISLNK(s.st_mode)
             and not getattr(s, 'st_file_attributes', 0) & 1024, 'PATH_REPARSE')
        if q == p and stat.S_ISREG(s.st_mode):
            need(s.st_nlink == 1, 'PATH_HARDLINK')
    need(str(p.resolve()) == str(p), 'PATH_ALIAS')
    return p


def bounded_read(path, limit):
    p = safe_path(path)
    s = p.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_size <= limit, 'INPUT_TYPE_OR_SIZE')
    # Recheck the opened descriptor, including replacement/hardlink races.
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(p, flags)
    with os.fdopen(fd, 'rb') as f:
        actual = os.fstat(f.fileno())
        need((actual.st_dev, actual.st_ino) == (s.st_dev, s.st_ino)
             and actual.st_nlink == 1 and stat.S_ISREG(actual.st_mode), 'INPUT_REPLACED')
        raw = f.read(limit + 1)
    need(len(raw) <= limit, 'INPUT_TYPE_OR_SIZE')
    return raw


def git(*args):
    p = subprocess.run(['git', 'rev-parse', *args], cwd=ROOT,
                       capture_output=True, timeout=10, check=False)
    need(p.returncode == 0 and len(p.stdout) <= 8192, 'GIT_IDENTITY')
    return p.stdout.decode('ascii', errors='strict').strip().splitlines()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def context():
    """Read four public pinned files; derive inventory without importing Router."""
    actual = git(*['HEAD:' + f for f in PINS])
    need(actual == list(PINS.values()), 'SOURCE_GIT_DRIFT')
    sources = {}
    for f, pin in PINS.items():
        raw = bounded_read(ROOT / f, INPUT_LIMIT)
        lf = raw.replace(b'\r\n', b'\n')
        need(pin in {blob(raw), blob(lf)}, 'SOURCE_WORKTREE_DRIFT')
        sources[f] = lf
    matrix = strict(sources['ci/runtime-contract-test-matrix.json'])
    baseline = strict(sources['spikes/rpf-82/rev-2/classification-ledger.json'])
    inventory = {m['path']: [r['id'] for r in m['rows']] for m in baseline['modules']}
    expected = {}
    for m in matrix['modules']:
        rows = []
        for tid in inventory[m['path']]:
            local = tid[len(Path(m['path']).stem) + 1:]
            matches = [r for r in m['rules'] if local == r['selector'] or local.startswith(r['selector'] + '.')]
            need(len(matches) <= 1, 'SOURCE_ROUTING')
            rows.append((tid, matches[0]['route'] if matches else 'PORTABLE'))
        expected[m['path']] = (m['source_sha256'], rows)
    need(len(expected) == 57 and sum(len(x[1]) for x in expected.values()) == 1232,
         'SOURCE_INVENTORY')
    # Only constant Invalid/require codes in pinned Router are eligible for exact attribution.
    codes = set()
    for n in ast.walk(ast.parse(sources['ci/run-runtime-contract-tests.py'])):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            i = 1 if n.func.id == 'require' else 0 if n.func.id == 'Invalid' else -1
            if i >= 0 and len(n.args) > i and isinstance(n.args[i], ast.Constant):
                v = n.args[i].value
                if isinstance(v, str) and re.fullmatch('[A-Z][A-Z0-9_]{0,79}', v):
                    codes.add(v)
    return dict(expected=expected, hashes={f: sha(b) for f, b in sources.items()}, codes=codes)


def integer(v, low=0, high=2**63-1):
    return type(v) is int and low <= v <= high


def number(v, low, high):
    return type(v) in (int, float) and math.isfinite(v) and low <= v <= high


def receipt(r, ctx):
    need(type(r) is dict and set(r) == {
        'exit', 'timeout', 'truncated', 'stdout_sha256', 'bytes', 'monotonic_start_ns',
        'monotonic_end_ns', 'child_pid', 'runner_sha256', 'timeout_limit_seconds',
        'child_exited', 'drain_joined', 'descendant_cleanup'}, 'RECEIPT_SCHEMA')
    need(integer(r['exit'], -2**31, 2**31-1) and integer(r['bytes'])
         and integer(r['child_pid'], 1) and integer(r['monotonic_start_ns'], 1)
         and integer(r['monotonic_end_ns'], r['monotonic_start_ns'])
         and number(r['timeout_limit_seconds'], 0.000000001, 300), 'RECEIPT_NUMBERS')
    need(all(type(r[k]) is bool for k in ('timeout', 'truncated', 'child_exited', 'drain_joined')),
         'RECEIPT_BOOL')
    need(r['runner_sha256'] == ctx['hashes']['ci/run-runtime-contract-tests.py']
         and type(r['stdout_sha256']) is str and re.fullmatch('[0-9a-f]{64}', r['stdout_sha256'])
         and r['descendant_cleanup'] == 'UNAVAILABLE: exact Popen handle only', 'RECEIPT_SOURCE')
    duration = (r['monotonic_end_ns'] - r['monotonic_start_ns']) / 1e9
    need(duration <= 1520, 'RECEIPT_DURATION')
    out = {k: r[k] for k in ('exit', 'timeout', 'truncated', 'child_exited', 'drain_joined', 'timeout_limit_seconds')}
    out['monotonic_duration_seconds'] = duration
    return out


def error_code(value, ctx):
    need(type(value) is str and len(value) <= 8192, 'ERROR_FIELD')
    if value.startswith('Invalid:') and value[8:] in ctx['codes']:
        return value[8:], True
    if re.fullmatch(r'(?:OSError|FileNotFoundError|PermissionError|IsADirectoryError|NotADirectoryError|ValueError|KeyError|TypeError|UnicodeDecodeError|JSONDecodeError):INVALID_CHILD_SETTLEMENT', value):
        return 'INVALID_CHILD_SETTLEMENT', True
    return 'UNRECOGNIZED_ERROR_REDACTED', False


def project(v, ctx):
    top = {'schema', 'modules', 'coverage_policy', 'overall', 'portable', 'required_modules',
           'required_methods', 'baseline_sha256', 'lane_limit_seconds', 'coverage_verified',
           'discovered', 'unique_dispositions', 'counts', 'routes', 'lane_finished_monotonic'}
    need(type(v) is dict and set(v) == top, 'LEDGER_SCHEMA')
    need(v['schema'] == 'rpf84-runtime-ledger-v1' and v['coverage_policy'] == 'ALL_DISCOVERED_REQUIRED'
         and type(v['required_modules']) is int and v['required_modules'] == 57
         and type(v['required_methods']) is int and v['required_methods'] == 1232
         and v['baseline_sha256'] == ctx['hashes']['spikes/rpf-82/rev-2/classification-ledger.json']
         and type(v['lane_limit_seconds']) is int and v['lane_limit_seconds'] == 1500, 'LEDGER_IDENTITY')
    need(type(v['modules']) is list and len(v['modules']) == 57, 'MODULE_COUNT')
    rows, errors, failures, badmodules, unresolved = [], [], [], [], set()
    discovered = 0
    any_error = False
    for m, (path, (source, expected)) in zip(v['modules'], ctx['expected'].items()):
        required = {'path', 'source_sha256', 'rows', 'invocations', 'inventory_verified', 'runner_sha256', 'matrix_sha256'}
        need(type(m) is dict and required <= set(m) <= required | {'error', 'progress_error', 'tests_run', 'fixture_skips'}, 'MODULE_SCHEMA')
        need(m['path'] == path and m['source_sha256'] == source
             and m['runner_sha256'] == ctx['hashes']['ci/run-runtime-contract-tests.py']
             and m['matrix_sha256'] == ctx['hashes']['ci/runtime-contract-test-matrix.json'], 'MODULE_SOURCE')
        need(type(m['inventory_verified']) is bool and type(m['rows']) is list
             and len(m['rows']) == len(expected), 'MODULE_ROWS')
        if m['inventory_verified']:
            discovered += len(expected)
        need(type(m['invocations']) is list and len(m['invocations']) <= 2, 'INVOCATIONS')
        receipts = [receipt(r, ctx) for r in m['invocations']]
        if any(r['timeout'] or r['truncated'] for r in receipts):
            need('error' in m, 'UNSETTLED_RECEIPT_WITHOUT_ERROR')
        if m['inventory_verified']:
            need(bool(receipts) and receipts[0]['exit'] == 0 and not receipts[0]['timeout']
                 and not receipts[0]['truncated'], 'INVENTORY_RECEIPT')
        selected = []
        for r, (tid, route) in zip(m['rows'], expected):
            need(type(r) is dict and set(r) == {'id', 'route', 'required', 'reason', 'executed', 'actual'}, 'ROW_SCHEMA')
            need(r['id'] == tid and r['route'] == route and r['required'] is True
                 and type(r['executed']) is bool and type(r['reason']) is str
                 and len(r['reason']) <= 8192 and type(r['actual']) is str and r['actual'] in ACTUAL, 'ROW_IDENTITY')
            if route != 'PORTABLE':
                need(r['actual'] == 'UNAVAILABLE' and r['executed'] is False, 'NONPORTABLE_PROMOTION')
            else:
                selected.append(tid)
                need(r['actual'] != 'UNAVAILABLE', 'PORTABLE_UNAVAILABLE')
                need(r['actual'] not in {'PASS', 'FAIL'} or r['executed'], 'UNEXECUTED_RESULT')
                need(r['actual'] != 'NOT_RUN' or not r['executed'], 'EXECUTED_NOT_RUN')
                if r['actual'] in {'PASS', 'FAIL', 'ERROR', 'SKIP'}:
                    need(m['inventory_verified'] and len(receipts) == 2, 'MISSING_EXECUTION_RECEIPT')
                item = dict(id=tid, module=path, route=route, executed=r['executed'])
                if r['actual'] == 'ERROR':
                    errors.append(item)
                elif r['actual'] == 'FAIL':
                    failures.append(item)
            rows.append(r)
        if 'tests_run' in m or 'fixture_skips' in m:
            need('tests_run' in m and 'fixture_skips' in m and integer(m['tests_run'], 0, len(selected))
                 and type(m['fixture_skips']) is list and len(set(m['fixture_skips'])) == len(m['fixture_skips'])
                 and set(m['fixture_skips']) <= set(selected), 'RESULT_SUMMARY')
            need(set(m['fixture_skips']) <= {r['id'] for r in m['rows'] if r['actual'] == 'SKIP'},
                 'FALSE_FIXTURE_SKIP')
        codes, confirmed = [], False
        if 'error' in m:
            code, confirmed = error_code(m['error'], ctx)
            codes.append(code)
            any_error = True
        if 'progress_error' in m:
            need(type(m['progress_error']) is str, 'PROGRESS_FIELD')
            codes.append('INVALID_PARTIAL_PROGRESS' if m['progress_error'] == 'INVALID_PARTIAL_PROGRESS' else 'UNRECOGNIZED_PROGRESS_REDACTED')
        bad = [r for r in m['rows'] if r['route'] == 'PORTABLE' and r['actual'] not in {'PASS', 'SKIP'}]
        if codes or bad or any(r['exit'] != 0 or r['timeout'] or r['truncated'] or not r['child_exited'] or not r['drain_joined'] for r in receipts):
            if not confirmed:
                unresolved.add('NO_RELIABLE_MODULE_ERROR_CODE')
            badmodules.append(dict(module=path, error_codes=codes, invocations=receipts,
                                   exact_cause_confirmed=confirmed,
                                   cause_scope='ROUTER_PROTOCOL_ONLY' if confirmed else 'UNRESOLVED'))
    need(len(rows) == len({r['id'] for r in rows}) == 1232, 'ID_INVENTORY')
    counts = dict(Counter(r['actual'] for r in rows))
    routes = {k: dict(Counter(r['actual'] for r in rows if r['route'] == k)) for k in sorted(ROUTES)}
    def counts_valid(obj, expected):
        return type(obj) is dict and set(obj) == set(expected) and all(type(x) is int and x > 0 for x in obj.values()) and obj == expected
    need(counts_valid(v['counts'], counts) and type(v['routes']) is dict and set(v['routes']) == ROUTES
         and all(counts_valid(v['routes'][k], routes[k]) for k in ROUTES), 'AGGREGATES')
    verified = discovered == 1232
    need(type(v['coverage_verified']) is bool and v['coverage_verified'] == verified
         and type(v['discovered']) is int and v['discovered'] == discovered
         and type(v['unique_dispositions']) is int and v['unique_dispositions'] == 1232
         and number(v['lane_finished_monotonic'], 0.000000001, 1e15), 'COVERAGE_SETTLEMENT')
    failed = any_error or bool(errors or failures) or not verified
    complete = all(r['actual'] in {'PASS', 'SKIP'} for r in rows if r['route'] == 'PORTABLE')
    portable = 'FAIL' if failed else 'PASS' if complete else 'NOT_RUN'
    overall = 'FAIL' if failed else 'REQUIRED_COVERAGE_UNAVAILABLE'
    need(v['portable'] == portable and v['overall'] == overall, 'FALSE_GREEN')
    if errors:
        unresolved.add('METHOD_EXCEPTION_DETAIL_NOT_IN_LEDGER')
    return dict(overall=overall, portable=portable, counts=counts, routes=routes,
                error_methods=errors, failed_methods=failures, failure_modules=badmodules,
                unresolved_cause_codes=sorted(unresolved),
                validation_status='VALIDATED_FAILURE' if failed or not complete else 'VALIDATED_NO_PORTABLE_ERROR')


def envelope(run_id, attempt, commit, kind):
    return dict(schema='rpf90-router-failure-observation-v1', run_id=run_id, attempt=attempt,
                commit=commit, evidence_kind=kind, release_eligible=False, release_executed=False,
                deployment_authorized=False, coverage_promoted=False, authority='NO_RELEASE/NO_DEPLOY')


def exception_signatures(ledger, root):
    """Project only fixed exception classes from receipt-bound unittest output."""
    allowed = {'PermissionError', 'FileNotFoundError', 'OSError', 'ValueError',
               'TypeError', 'RuntimeError', 'AssertionError', 'ImportError',
               'ModuleNotFoundError', 'NotADirectoryError', 'IsADirectoryError'}
    output = []
    for module in ledger['modules']:
        targets = [r['id'] for r in module['rows'] if r['route'] == 'PORTABLE' and r['actual'] == 'ERROR']
        if not targets:
            continue
        if len(module['invocations']) != 2:
            output.extend({'id': tid, 'status': 'UNAVAILABLE'} for tid in targets)
            continue
        receipt = module['invocations'][1]
        path = root / (Path(module['path']).stem + '-execution') / 'output.log'
        try:
            raw = bounded_read(path, 2 * 1024 * 1024)
            need(len(raw) == receipt['bytes'] and sha(raw) == receipt['stdout_sha256']
                 and not receipt['truncated'], 'LOG_BINDING')
            text = raw.decode('utf-8', errors='replace')
            for tid in targets:
                prefix, method = tid.rsplit('.', 1)
                header = 'ERROR: ' + method + ' (' + prefix + ')'
                sections = text.split(header)
                if len(sections) != 2:
                    output.append({'id': tid, 'status': 'UNAVAILABLE'})
                    continue
                section = sections[1].split('\n======================================================================', 1)[0]
                found = re.findall(r'(?m)^(' + '|'.join(sorted(allowed)) + r')(?::|\s*$)', section)
                output.append({'id': tid, 'status': 'MATCHED', 'exception': found[-1]} if len(found) == 1
                              else {'id': tid, 'status': 'UNAVAILABLE'})
        except (Invalid, OSError, ValueError, TypeError, KeyError):
            output.extend({'id': tid, 'status': 'UNAVAILABLE'} for tid in targets)
    return output


def identity(args, env):
    need(re.fullmatch('[0-9]+', args.run_id or '') is not None
         and re.fullmatch('[1-9][0-9]*', args.attempt or '') is not None
         and re.fullmatch('[0-9a-f]{40}', args.commit or '') is not None
         and len(args.run_id) <= 24 and len(args.attempt) <= 8, 'RUN_IDENTITY')
    if env.get('GITHUB_ACTIONS') == 'true':
        need(not args.synthetic and args.fixture_root is None, 'HOSTED_SYNTHETIC_FORBIDDEN')
        need(env.get('GITHUB_WORKSPACE') == str(ROOT)
             and env.get('GITHUB_RUN_ID') == args.run_id and env.get('GITHUB_RUN_ATTEMPT') == args.attempt
             and env.get('GITHUB_SHA') == args.commit, 'HOSTED_IDENTITY')
        need(git('HEAD') == [args.commit], 'HEAD_IDENTITY')
        parent = ROOT / 'ci-results'
        ledger = parent / ('rpf84-' + args.run_id + '-' + args.attempt) / 'ledger.json'
        output = parent / ('rpf90-router-' + args.run_id + '-' + args.attempt + '.json')
        kind = 'HOSTED_SAME_RUN'
    else:
        need(args.synthetic and args.fixture_root is not None, 'LOCAL_SYNTHETIC_REQUIRED')
        owner = safe_path(env.get('RPF90_OWNER', ''))
        need(owner.parent == ROOT / '.local/rpf-90-router-failure'
             and re.fullmatch('[0-9a-f]{32}', owner.name) is not None and owner.is_dir(), 'LOCAL_OWNER')
        parent = safe_path(args.fixture_root)
        need(parent.is_relative_to(owner) and parent != owner and parent.is_dir(), 'FIXTURE_ROOT')
        ledger, output = parent / 'ledger.json', parent / 'observation.json'
        kind = 'LOCAL_SYNTHETIC_CONTROL_ONLY'
    need(args.ledger == str(ledger) and args.output == str(output), 'EXACT_PATH')
    safe_path(ledger)
    safe_path(output)
    need(not os.path.lexists(output), 'OUTPUT_EXISTS')
    return ledger, output, kind


def encode(value):
    raw = (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2) + '\n').encode()
    need(len(raw) <= OUTPUT_LIMIT, 'PROJECTION_TOO_LARGE')
    return raw


def capture(args, env=None):
    env = os.environ if env is None else env
    # Path/identity failures deliberately produce no file: no trusted destination exists yet.
    ledger, output, kind = identity(args, env)
    out = envelope(args.run_id, args.attempt, args.commit, kind)
    code = 0
    try:
        ctx = context()
        out['source_blobs'] = dict(PINS)
        raw = bounded_read(ledger, INPUT_LIMIT)
        out['ledger_sha256'] = sha(raw)
        ledger_data = strict(raw)
        out.update(project(ledger_data, ctx))
        out['portable_exception_signatures'] = exception_signatures(ledger_data, ledger.parent)
        encoded = encode(out)
    except FileNotFoundError:
        code = 2
        out = dict(envelope(args.run_id, args.attempt, args.commit, kind),
                   validation_status='LEDGER_UNAVAILABLE', error_code='INPUT_MISSING')
        encoded = encode(out)
    except (Invalid, OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        code = 2
        # Invalid codes originate only in this module; never forward OS/parser exception text.
        out = dict(envelope(args.run_id, args.attempt, args.commit, kind),
                   validation_status='INVALID_LEDGER', error_code=str(exc) if type(exc) is Invalid else 'INPUT_INVALID')
        encoded = encode(out)
    safe_path(output)
    with output.open('xb') as f:
        f.write(encoded)
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps({'validation_status': out['validation_status'], 'exit': code}))
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['capture'])
    for name in ('ledger', 'output', 'run-id', 'attempt', 'commit'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--fixture-root')
    args = parser.parse_args()
    try:
        return capture(args)
    except (Invalid, OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.SubprocessError):
        print('{"validation_status":"INVALID_LEDGER","error_code":"UNTRUSTED_INVOCATION"}')
        return 2


if __name__ == '__main__':
    sys.exit(main())
