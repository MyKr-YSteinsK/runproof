"""RPF-82: isolated unittest inventory, explicit prerequisites, fail-closed accounting.

The supervisor never imports runtime/tests. Non-portable obligations remain required.
Only this versioned runner's owned output tree may receive temporary test files.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
from collections import Counter
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
MATRIX = ROOT / 'ci/runtime-contract-test-matrix.json'
OWNER = ROOT / '.local/rpf-82-rev-3-classifier-closure'
ROUTES = {'PORTABLE', 'WINDOWS_NATIVE', 'DEDICATED_RUNNER',
          'LEGACY_SDK_PRECONDITION', 'FROZEN_PRIVATE_ARTIFACT', 'LEGACY_OWNER_ROOT'}
LIMIT = 2 * 1024 * 1024
TIMEOUT = 300  # RPF60 semantic matrix exceeded 120s locally; suite deadline remains 1800s.
KNOWN = {
    'test_effectwitness_config_live.ConfigLiveContractsTests.test_denied_file_diagnostic_keeps_only_a_bounded_safe_basename',
    'test_effectwitness_config_target.ConfigTargetVerifierBoundaryTests.test_sdk_child_guard_allows_reads_from_resolved_base_python_runtime',
}


class Invalid(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Invalid(reason)


def strict(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'DUPLICATE_JSON_KEY')
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(Invalid('NONFINITE_JSON')))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_sha(path):
    return sha(path.read_bytes().replace(b'\r\n', b'\n'))


def owned(path):
    path = Path(path).absolute()
    allowed = (OWNER, ROOT / 'ci-results')
    require(any(path.is_relative_to(p) for p in allowed), 'OUTPUT_SCOPE')
    for p in (path, *path.parents):
        require(not p.is_symlink() and not getattr(p, 'is_junction', lambda: False)(), 'OUTPUT_REPARSE')
    require(any(path.resolve().is_relative_to(p.resolve()) for p in allowed), 'OUTPUT_ESCAPE')
    return path


def tracked_modules():
    p = subprocess.run(['git', 'ls-files', '--', 'runtime/tests/test_*.py'],
                       cwd=ROOT, capture_output=True, text=True, check=True)
    return p.stdout.splitlines()


def validate_matrix(value, files):
    require(type(value) is dict and set(value) == {'schema', 'required_coverage', 'modules', 'helper_registry'}, 'MATRIX_SCHEMA')
    require(value['schema'] == 'rpf82-test-matrix-v2' and value['required_coverage'] == 'ALL_DISCOVERED', 'COVERAGE_POLICY')
    require(type(value['modules']) is list, 'MODULES_TYPE')
    paths = [m.get('path') for m in value['modules'] if type(m) is dict]
    require(len(paths) == len(value['modules']) and len(set(paths)) == len(paths), 'DUPLICATE_MODULE')
    require(set(paths) == set(files), 'MODULE_INVENTORY_MISMATCH')
    for m in value['modules']:
        require(set(m) == {'path', 'source_sha256', 'default', 'rules'}, 'MODULE_SCHEMA')
        require(re.fullmatch(r'runtime/tests/test_[a-zA-Z0-9_]+\.py', m['path']) is not None, 'MODULE_PATH')
        require(source_sha(ROOT / m['path']) == m['source_sha256'], 'SOURCE_DRIFT')
        require(m['default'] == 'PORTABLE' and type(m['rules']) is list, 'DEFAULT_ROUTE')
        for rule in m['rules']:
            require(type(rule) is dict and set(rule) == {'selector', 'route', 'reason', 'evidence'}, 'RULE_SCHEMA')
            require(rule['route'] in ROUTES - {'PORTABLE'} and type(rule['reason']) is str and bool(rule['reason']), 'ROUTE')
            require(re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?', rule['selector']) is not None, 'SELECTOR')
            e = rule['evidence']
            require(type(e) is dict and set(e) == {'line', 'marker'}, 'EVIDENCE_SCHEMA')
            lines = (ROOT / m['path']).read_text(encoding='utf-8').splitlines()
            require(type(e['line']) is int and 1 <= e['line'] <= len(lines)
                    and type(e['marker']) is str and len(e['marker']) > 3
                    and e['marker'] in lines[e['line'] - 1], 'PREREQUISITE_EVIDENCE')
    validate_helper_registry(value)
    return value


def callable_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = callable_name(node.value)
        return (parent or '<expr>') + '.' + node.attr
    return ''


def helper_closure(source, class_name, owner_calls, approved_calls):
    """Bounded static closure; never import/execute historical helpers.

    Every external callable in a portable closure is explicitly source-reviewed.
    Known owner constructors terminate the proof as unavailable before execution.
    """
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name]
    require(len(classes) == 1, 'HELPER_CLASS')
    methods = {n.name:n for n in classes[0].body if isinstance(n, ast.FunctionDef)}
    require(len(methods) == sum(isinstance(n, ast.FunctionDef) for n in classes[0].body), 'DUPLICATE_HELPER')
    def visit(name, chain):
        require(name in methods, 'UNKNOWN_HELPER:' + name)
        require(name not in chain and len(chain) < 32, 'AMBIGUOUS_HELPER_CYCLE')
        node = methods[name]
        calls = [callable_name(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)]
        roots = [x for x in calls if x in owner_calls]
        # Generic hidden-root mutation counterexample, not a two-ID string patch.
        old_root = any(isinstance(n, ast.Name) and n.id == 'WORK' or
                       isinstance(n, ast.Constant) and isinstance(n.value, str) and '.local/' in n.value
                       for n in ast.walk(node))
        if old_root and any(x.rsplit('.',1)[-1] in {'mkdir','write_bytes','write_text','open'} for x in calls):
            roots.append('HIDDEN_OWNER_ROOT_MUTATION')
        if roots:
            return dict(owner_bound=True, chain=[*chain,name,roots[0]])
        traces=[]
        for call in calls:
            if call.startswith('self.assert'):
                continue
            if call.startswith('self.'):
                traces.append(visit(call[5:], [*chain,name]))
            else:
                require(call in approved_calls, 'UNVERIFIED_HELPER_CALL:' + call)
        return next((x for x in traces if x['owner_bound']), dict(owner_bound=False, chain=[*chain,name]))
    return {name:visit(name,[]) for name in methods if name.startswith('test_')}


def validate_helper_registry(matrix):
    reg = matrix['helper_registry']
    require(type(reg) is dict and set(reg) == {'path','class','owner_calls','approved_calls','method_ids','dependencies'}, 'HELPER_REGISTRY_SCHEMA')
    require(reg['path'] == 'runtime/tests/test_effectwitness_pge_r81.py' and reg['class'] == 'ConformanceTests', 'HELPER_REGISTRY_SCOPE')
    for key in ('owner_calls','approved_calls','method_ids'):
        require(type(reg[key]) is list and all(type(x) is str for x in reg[key])
                and len(set(reg[key])) == len(reg[key]), 'HELPER_REGISTRY_LIST')
    require(set(reg['owner_calls']) == {'Host','Journal','c.case_dir'}
            and not set(reg['owner_calls']) & set(reg['approved_calls']), 'OWNER_PREREQUISITE_MASK')
    require(type(reg['dependencies']) is list
            and {d.get('path') for d in reg['dependencies'] if type(d) is dict} == {
                'runtime/runproof_runtime/effectwitness/pge_r81_'+x+'.py'
                for x in ('contracts','journal','barrier')}
            and len(reg['dependencies']) == 3, 'HELPER_DEPENDENCY_SET')
    for dep in reg['dependencies']:
        require(type(dep) is dict and set(dep) == {'path','sha256'}, 'HELPER_DEPENDENCY_SCHEMA')
        require(re.fullmatch(r'runtime/runproof_runtime/effectwitness/pge_r81_[a-z_]+\.py',dep['path']) is not None, 'HELPER_DEPENDENCY_SCOPE')
        require(source_sha(ROOT / dep['path']) == dep['sha256'], 'HELPER_DEPENDENCY_DRIFT')
    closure=helper_closure((ROOT/reg['path']).read_text(encoding='utf-8'),reg['class'],reg['owner_calls'],reg['approved_calls'])
    require(set(closure) == set(reg['method_ids']), 'UNREGISTERED_HELPER_METHOD')
    module=next(x for x in matrix['modules'] if x['path']==reg['path'])
    rows=classify(module,[Path(reg['path']).stem+'.'+reg['class']+'.'+n for n in closure])
    for row in rows:
        bound=closure[row['id'].rsplit('.',1)[-1]]['owner_bound']
        require(bound == (row['route'] in {'DEDICATED_RUNNER','LEGACY_OWNER_ROOT'}), 'HELPER_ROUTE_MISMATCH')
    return closure


def classify(module, ids):
    require(bool(ids) and len(set(ids)) == len(ids), 'EMPTY_OR_DUPLICATE_TEST_IDS')
    prefix = Path(module['path']).stem + '.'
    rows, used = [], set()
    for tid in ids:
        require(type(tid) is str and tid.startswith(prefix), 'UNKNOWN_TEST_ID')
        local = tid[len(prefix):]
        require(re.fullmatch(r'[A-Za-z0-9_]+\.test_[A-Za-z0-9_]+', local) is not None, 'TEST_ID_SHAPE')
        matches = [(i, r) for i, r in enumerate(module['rules'])
                   if local == r['selector'] or local.startswith(r['selector'] + '.')]
        require(len(matches) <= 1, 'ROUTING_OVERLAP')
        rule = matches[0][1] if matches else None
        if matches:
            used.add(matches[0][0])
        route = rule['route'] if rule else 'PORTABLE'
        require(tid not in KNOWN or route == 'PORTABLE', 'KNOWN_FAILURE_HIDDEN')
        rows.append(dict(id=tid, route=route, required=True,
                         reason=rule['reason'] if rule else 'No declared OS/SDK/private-owner prerequisite; execute original assertions',
                         executed=False, actual='NOT_RUN'))
    require(used == set(range(len(module['rules']))), 'UNKNOWN_RULE_SELECTOR')
    return rows


def reconcile(expected, report, returncode):
    require(type(report) is dict and set(report) == {'ids', 'results', 'tests_run', 'successful', 'fixture_skips'}, 'CHILD_REPORT_SCHEMA')
    require(report['ids'] == expected and len(set(report['ids'])) == len(expected), 'CHANGED_OR_DUPLICATE_IDS')
    rows = report['results']
    require(type(rows) is list and len(rows) == len(expected), 'MISSING_RESULTS')
    require([r.get('id') for r in rows] == expected, 'RESULT_ID_MISMATCH')
    require(all(set(r) == {'id', 'actual'} and r['actual'] in {'PASS', 'FAIL', 'ERROR', 'SKIP'} for r in rows), 'RESULT_STATUS')
    success = all(r['actual'] in {'PASS', 'SKIP'} for r in rows)
    require(type(report['successful']) is bool and report['successful'] == success, 'FALSE_PASS')
    require(type(report['tests_run']) is int and 0 <= report['tests_run'] <= len(expected), 'TESTS_RUN_COUNT')
    skips = report['fixture_skips']
    require(type(skips) is list and len(set(skips)) == len(skips)
            and set(skips) <= {r['id'] for r in rows if r['actual'] == 'SKIP'}, 'FIXTURE_SKIPS')
    require(not success or report['tests_run'] + len(skips) == len(expected), 'UNEXECUTED_PASS')
    require(returncode == (0 if success else 1), 'CHILD_EXIT_DISAGREES')
    return rows


def child_environment(folder):
    env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'LANG', 'LC_ALL') if k in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', TMP=str(folder), TEMP=str(folder),
               TMPDIR=str(folder), HOME=str(folder), USERPROFILE=str(folder), RPF82_TEST_ROOT=str(folder))
    return env


def launch(args, folder, timeout=TIMEOUT):
    """Only own CLI and the current Python; bound logs and propagate timeout/crash."""
    folder = owned(folder)
    folder.mkdir(parents=True, exist_ok=False)
    argv = [sys.executable, '-B', str(SELF), *args]
    start = time.monotonic_ns()
    p = subprocess.Popen(argv, cwd=ROOT, env=child_environment(folder),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    chunks, count, overflow = [], 0, threading.Event()
    def drain():
        nonlocal count
        while True:
            b = p.stdout.read(65536)
            if not b:
                break
            count += len(b)
            if count > LIMIT:
                overflow.set()
                p.kill()
                break
            chunks.append(b)
    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    timed_out = False
    try:
        code = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        p.kill()
        code = p.wait()
    thread.join(timeout=5)
    if not thread.is_alive():
        p.stdout.close()
    raw = b''.join(chunks)
    with (folder / 'output.log').open('xb') as f:
        f.write(raw)
    receipt = dict(exit=code, timeout=timed_out, truncated=overflow.is_set() or thread.is_alive(),
                   stdout_sha256=sha(raw), bytes=count, monotonic_start_ns=start,
                   monotonic_end_ns=time.monotonic_ns(), child_pid=p.pid,
                   runner_sha256=source_sha(SELF))
    with (folder/'launch-receipt.json').open('x',encoding='utf-8') as f:
        json.dump(receipt,f,indent=2)
    return receipt


def guard(folder):
    """Fail on boundary violations, never turn exceptions into unavailable/PASS."""
    folder = owned(folder).resolve()
    private = (ROOT / '.local').resolve()
    forbidden = ROOT / 'docs' / 'reviews'
    def check(path, write=False):
        if isinstance(path, int) or path is None:
            return
        p = Path(os.fsdecode(path)).absolute()
        # Check lexical scope first, so a protected directory is never traversed.
        if p.is_relative_to(forbidden) or (p.is_relative_to(private) and not p.is_relative_to(folder)):
            raise PermissionError('RPF82_PROTECTED_PATH')
        if write and not p.is_relative_to(folder):
            raise PermissionError('RPF82_WRITE_SCOPE')
        if write and not p.resolve().is_relative_to(folder):
            raise PermissionError('RPF82_WRITE_ESCAPE')
    def audit(event, args):
        if event == 'open':
            path, mode, flags = args
            check(path, bool(isinstance(mode, str) and any(x in mode for x in 'wax+')
                             or isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)))
        elif event in {'os.listdir', 'os.scandir'}:
            check(args[0])
        elif event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime', 'os.truncate'}:
            check(args[0], True)
        elif event in {'os.rename', 'os.link', 'os.symlink'}:
            check(args[0], True)
            check(args[1], True)
        elif event == 'socket.connect':
            address = args[1]
            if not isinstance(address, tuple) or address[0] != '127.0.0.1':
                raise PermissionError('RPF82_EXTERNAL_NETWORK')
        elif event == 'socket.bind':
            if args[1][0] != '127.0.0.1':
                raise PermissionError('RPF82_NON_LOOPBACK_BIND')
        elif event == 'socket.getaddrinfo':
            if args[0] != '127.0.0.1':
                raise PermissionError('RPF82_DNS_SCOPE')
        elif event == 'subprocess.Popen':
            executable, argv = args[:2]
            # Windows exposes the serialized native command and executable=None.
            native_python = (os.name == 'nt' and executable is None and isinstance(argv, str)
                             and argv.startswith(subprocess.list2cmdline([sys.executable]) + ' '))
            vector_python = (executable is not None and isinstance(argv, (list, tuple))
                             and Path(executable).resolve() == Path(sys.executable).resolve())
            if not (native_python or vector_python):
                raise PermissionError('RPF82_PROCESS_SCOPE')
        elif event in {'os.system', 'os.posix_spawn', 'os.spawn', 'os.exec'}:
            raise PermissionError('RPF82_PROCESS_SCOPE')
    sys.addaudithook(audit)


R60_PATH = 'runtime/tests/test_effectwitness_lab_cross_domain.py'
R60_SHA = '6ee0cfd3620381c3d0415601d9d05e9cfe916803df29e78425081b16c364c08f'


def r60_owner(raw):
    """Versioned test-only adapter: same harness, current authorized owner."""
    return owned(raw)


@contextlib.contextmanager
def r60_harness(module, folder):
    # The inherited test file is immutable in rev3 and allows only rev2/CI roots.
    # Adapt that test-only owner validator, never the business Runtime or assertions.
    from unittest.mock import patch
    require(source_sha(ROOT / R60_PATH) == R60_SHA, 'R60_HARNESS_SOURCE')
    tree=ast.parse((ROOT/R60_PATH).read_text(encoding='utf-8'))
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
                and n.name=='test_competing_processes_share_provider_reservation')
    code=next(n.value.value for n in ast.walk(method) if isinstance(n,ast.Assign)
              and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str)
              and any(isinstance(x,ast.Name) and x.id=='code' for x in n.targets))
    original=subprocess.Popen
    def popen(argv, *args, **kwargs):
        if argv == [sys.executable,'-B','-c',code]:
            argv=[sys.executable,'-B',str(SELF),'--r60-race','--output',str(folder)]
        return original(argv,*args,**kwargs)
    with patch.object(module,'_test_owner',r60_owner), patch.object(subprocess,'Popen',popen):
        yield


def r60_race(folder):
    require(source_sha(ROOT/R60_PATH)==R60_SHA,'R60_HARNESS_SOURCE')
    guard(folder)
    sys.path.insert(0,str(ROOT))
    from runtime.runproof_runtime.effectwitness import lab_cross_domain as core,lab_cross_domain_contracts as c
    data=strict(sys.stdin.buffer.read())
    require(set(data)=={'path','plan','owner_root'} and r60_owner(data['owner_root'])==folder,'R60_RACE_OWNER')
    c.WORK=folder
    try:
        ledger=core.Ledger(owned(data['path']),data['plan'])
        ledger.reserve_request('EXPLORER',1,c.body_for(c.messages_for([])))
        print('RESERVED')
    except Exception:
        print('REJECTED')
    return 0


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


class Result(unittest.TextTestResult):
    progress_path = None
    def __init__(self, *args):
        super().__init__(*args)
        self.actual = {}
    def record(self, test, actual):
        self.actual[test.id()] = actual
        if self.progress_path:
            with self.progress_path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(dict(id=test.id(), actual=actual)) + '\n')
    def startTest(self, test):
        super().startTest(test)
        self.record(test, 'STARTED')
    def addSuccess(self, test):
        super().addSuccess(test)
        if self.actual.get(test.id()) == 'STARTED':
            self.record(test, 'PASS')
    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, 'FAIL')
    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, 'ERROR')
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, 'SKIP')
    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            self.record(test, 'FAIL' if issubclass(err[0], test.failureException) else 'ERROR')
    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, 'FAIL')  # Expected failure is not proof of a passing assertion.
    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, 'FAIL')


def child(module, mode, folder):
    folder = owned(folder)
    guard(folder)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'runtime/tests'))
    sys.path.insert(0, str(ROOT / 'runtime'))
    name = Path(module).stem
    imported = importlib.import_module(name)
    suite = unittest.defaultTestLoader.loadTestsFromModule(imported)
    require(not unittest.defaultTestLoader.errors, 'DISCOVERY_ERROR')
    tests = list(flatten(suite))
    ids = [t.id() for t in tests]
    require(len(set(ids)) == len(ids) and bool(ids), 'DISCOVERY_IDS')
    if mode == 'inventory':
        payload, code = {'ids': ids}, 0
    else:
        request = strict((folder / 'selection.json').read_bytes())
        require(type(request) is dict and set(request) == {'inventory', 'selected'}, 'SELECTION_SCHEMA')
        require(request['inventory'] == ids, 'DYNAMIC_INVENTORY_CHANGED')
        selection = request['selected']
        require(type(selection) is list and len(set(selection)) == len(selection) and set(selection) <= set(ids), 'SELECTION')
        chosen = [t for t in tests if t.id() in selection]
        require([t.id() for t in chosen] == selection, 'DISCOVERY_CHANGED')
        Result.progress_path = folder / 'progress.jsonl'
        harness=r60_harness(imported,folder) if module==R60_PATH else contextlib.nullcontext()
        with harness:
            result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(unittest.TestSuite(chosen))
        fixture_skips=[]
        for holder, _ in result.skipped:
            if holder.id() not in selection:
                # unittest's actual addSkip(setUpClass/setUpModule) event, not an invented prerequisite skip.
                fixture=re.fullmatch(r'setUp(Class|Module) \(([A-Za-z0-9_.]+)\)', holder.id())
                require(fixture is not None, 'UNKNOWN_FIXTURE_SKIP')
                for tid in selection:
                    if tid.startswith(fixture.group(2)+'.'):
                        fixture_skips.append(tid)
                        result.actual[tid]='SKIP'
        rows = [dict(id=tid, actual=result.actual.get(tid, 'ERROR')) for tid in selection]
        success = result.wasSuccessful() and all(r['actual'] in {'PASS', 'SKIP'} for r in rows)
        payload = dict(ids=selection, results=rows, tests_run=result.testsRun, successful=success, fixture_skips=fixture_skips)
        code = 0 if success else 1
    with (folder / 'result.json').open('x', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    return code


def run(matrix, output, only=None, execute=True):
    matrix = validate_matrix(matrix, tracked_modules())
    root = owned(output)
    root.mkdir(parents=True, exist_ok=False)
    ledger = dict(schema='rpf82-runtime-ledger-v1', modules=[],
                  coverage_policy='ALL_DISCOVERED_REQUIRED', overall='FAIL', portable='NOT_RUN')
    failure, uncovered = False, False
    deadline = time.monotonic() + 1800
    for m in matrix['modules']:
        stem = Path(m['path']).stem
        record = dict(path=m['path'], source_sha256=m['source_sha256'], rows=[], invocations=[],
                      runner_sha256=source_sha(SELF), matrix_sha256=source_sha(MATRIX))
        ledger['modules'].append(record)
        invdir = root / (stem + '-inventory')
        receipt = launch(['--child', m['path'], '--mode', 'inventory', '--output', str(invdir)], invdir)
        record['invocations'].append(receipt)
        try:
            require(not receipt['timeout'] and not receipt['truncated'] and receipt['exit'] == 0, 'INVENTORY_PROCESS')
            report = strict((invdir / 'result.json').read_bytes())
            require(set(report) == {'ids'}, 'INVENTORY_SCHEMA')
            rows = classify(m, report['ids'])
            record['rows'] = rows
            selected = []
            for row in rows:
                if row['route'] != 'PORTABLE':
                    row['actual'] = 'UNAVAILABLE'
                    uncovered = True
                elif execute and (only is None or m['path'] in only):
                    selected.append(row['id'])
            if selected:
                require(time.monotonic() < deadline, 'SUITE_DEADLINE')
                folder = root / (stem + '-execution')
                # launch owns mkdir. Selection is passed through an owned input file
                # in a separate directory, then copied by the child before test import.
                selection_path = root / (stem + '-selection.json')
                selection_path.write_text(json.dumps(dict(inventory=report['ids'], selected=selected)), encoding='utf-8')
                rec = launch(['--child', m['path'], '--mode', 'execute', '--output', str(folder),
                              '--selection', str(selection_path)], folder)
                record['invocations'].append(rec)
                require(not rec['timeout'] and not rec['truncated'], 'EXECUTION_PROCESS')
                observed = reconcile(selected, strict((folder / 'result.json').read_bytes()), rec['exit'])
                results = {r['id']: r['actual'] for r in observed}
                for row in rows:
                    if row['id'] in results:
                        row.update(executed=True, actual=results[row['id']])
                failure |= any(r['actual'] not in {'PASS', 'SKIP'} for r in observed)
        except (Invalid, OSError, ValueError, KeyError, TypeError) as exc:
            record['error'] = type(exc).__name__ + ':' + (str(exc) if isinstance(exc, Invalid) else 'INVALID_CHILD_SETTLEMENT')
            # Preserve real completed assertions even when the module never settled.
            progress = root / (stem + '-execution') / 'progress.jsonl'
            if progress.is_file():
                for raw in progress.read_text(encoding='utf-8').splitlines():
                    event = strict(raw)
                    for row in record['rows']:
                        if row['id'] == event.get('id'):
                            actual = event.get('actual')
                            row.update(executed=True, actual='ERROR' if actual == 'STARTED' else actual)
            failure = True
    rows = [row for m in ledger['modules'] for row in m['rows']]
    ledger['counts'] = dict(Counter(row['actual'] for row in rows))
    ledger['routes'] = {route: dict(Counter(row['actual'] for row in rows if row['route'] == route)) for route in sorted(ROUTES)}
    ledger['discovered'] = len(rows)
    complete_portable = all(row['actual'] in {'PASS', 'SKIP'} for row in rows if row['route'] == 'PORTABLE')
    ledger['portable'] = 'FAIL' if failure else 'PASS' if execute and complete_portable else 'NOT_RUN'
    ledger['overall'] = 'FAIL' if failure else 'REQUIRED_COVERAGE_UNAVAILABLE' if uncovered else 'PASS' if complete_portable else 'NOT_RUN'
    (root / 'ledger.json').write_text(json.dumps(ledger, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: ledger[k] for k in ('overall', 'portable', 'discovered', 'counts', 'routes')}))
    return (1 if ledger['overall'] != 'PASS' else 0), ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', type=Path, default=MATRIX)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inventory-only', action='store_true')
    parser.add_argument('--only', action='append')
    parser.add_argument('--child')
    parser.add_argument('--mode', choices=['inventory', 'execute'])
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--r60-race', action='store_true')
    parser.add_argument('--control', choices=['hook', 'sibling', 'crash', 'exit1', 'timeout', 'overflow', 'missing', 'premkdir'])
    args = parser.parse_args()
    try:
        if args.r60_race:
            return r60_race(owned(args.output))
        if args.control:
            folder=owned(args.output)
            if args.control == 'premkdir':
                guard(folder)
                denied=[]
                # Synthetic audit events only: never call mkdir/open on an old root.
                path=str(ROOT/'.local/rpf-81-durable-unknown-presend-loopback/sessions/synthetic-no-io')
                for event, values in [('os.mkdir',(path,511,-1)),('open',(path,'rb',0))]:
                    try:
                        sys.audit(event,*values)
                    except PermissionError as exc:
                        require(str(exc)=='RPF82_PROTECTED_PATH','PRE_IO_REASON')
                        denied.append(event)
                require(len(denied)==2,'PRE_IO_DENIAL')
                (folder/'result.json').write_text(json.dumps({'denied':denied,'old_root_syscalls':0}),encoding='utf-8')
                return 0
            if args.control == 'exit1':
                return 1
            if args.control == 'crash':
                return 7
            if args.control == 'timeout':
                time.sleep(10)
                return 0
            if args.control == 'overflow':
                sys.stdout.write('x' * (LIMIT + 1))
                return 0
            if args.control == 'missing':
                return 0
            if args.control == 'hook':
                sys.path.insert(0, str(ROOT / 'runtime'))
                spec=importlib.util.spec_from_file_location('rpf82_guard_control', ROOT/'spikes/rpf-75/probe.py')
                probe=importlib.util.module_from_spec(spec)
                spec.loader.exec_module(probe)
                rejected=[]
                for event in ('subprocess.Popen', 'socket.connect'):
                    try:
                        probe.offline_guard(event, ())
                    except Exception as exc:
                        require(str(exc) == 'OFFLINE_OPERATION_FORBIDDEN', 'GUARD_REASON')
                        rejected.append(event)
                require(len(rejected) == 2, 'GUARD_INACTIVE')
                try:
                    subprocess.run([sys.executable, '-B', '-c', 'pass'], check=True)
                except Exception as exc:
                    require(str(exc) == 'OFFLINE_OPERATION_FORBIDDEN', 'HOOK_REASON')
                else:
                    raise Invalid('HOOK_NOT_INSTALLED')
                payload={'guard_denied':rejected,'actual_subprocess_denied':True}
            else:
                import socket
                with socket.socket() as listener:
                    listener.bind(('127.0.0.1',0));listener.listen(1)
                    with socket.create_connection(listener.getsockname(), timeout=3) as client:
                        with listener.accept()[0] as peer:
                            client.sendall(b'rpf82');require(peer.recv(5) == b'rpf82','LOOPBACK_BYTES')
                p=subprocess.run([sys.executable,'-B','-c','pass'],cwd=ROOT,env=child_environment(folder),timeout=5)
                require(p.returncode == 0,'SIBLING_SUBPROCESS')
                payload={'loopback_bytes':5,'python_subprocess_exit':p.returncode}
            (folder/'result.json').write_text(json.dumps(payload),encoding='utf-8')
            print(json.dumps(payload))
            return 0
        if args.child:
            require(args.child in tracked_modules(), 'CHILD_MODULE')
            if args.selection:
                selection = owned(args.selection).read_bytes()
                (owned(args.output) / 'selection.json').write_bytes(selection)
            return child(args.child, args.mode, args.output)
        require(args.matrix.resolve() == MATRIX, 'MATRIX_PATH')
        if args.only:
            require(set(args.only) <= set(tracked_modules()), 'UNKNOWN_ONLY_MODULE')
        return run(strict(args.matrix.read_bytes()), args.output, args.only, not args.inventory_only)[0]
    except (Invalid, OSError, ValueError, KeyError, TypeError) as exc:
        print('INVALID_GATE_INPUT:' + (str(exc) if isinstance(exc, Invalid) else type(exc).__name__), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
