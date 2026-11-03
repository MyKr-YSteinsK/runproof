"""RPF89 B-path admission precondition diagnostic, NOT an activated assessor.

No historical module imports, receipt reads, SQL, native methods, or promotion.
The frozen RPF87 schema lacks an assessor-completion observation required by
Plan 3.1. This candidate refuses assess/enforce rather than assume a timestamp.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE='0530d2c019e0fd812658b28f61688b21d4fc5753'
PINS={
 'ci/reconcile-rpf86-required-coverage.py':'1d8d502e0a8db08e56763272565386dc246469b0',
 'ci/run-rpf88-r72-owner-scope.py':'6ca463addf0b861dfe1be854ea305d5f5b369c9c',
 'ci/verify-runtime-coverage-handoff.py':'0e22b02048497b21d698dfe6cd958a437583c94d',
 'ci/run-runtime-contract-tests.py':'88396fa78d73ba091e91992d4d51263063a95aa7',
 'ci/runtime-contract-test-matrix.json':'ed827c3dc354c18c9d4b7bc63384805e50e97785',
 '.github/workflows/release-gate.yml':'0cfc1a8ec53899eb6e9fe6aee46396ffa8af506b'}
class Invalid(ValueError):pass
def need(ok,code):
    if not ok:raise Invalid(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def strict(b):
    need(type(b) is bytes and 0<len(b)<=8*1024*1024,'JSON_SIZE')
    def pairs(xs):
        d={}
        for k,v in xs:need(k not in d,'JSON_DUPLICATE');d[k]=v
        return d
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Invalid('JSON_NONFINITE')))
def git(*args):
    p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,timeout=15)
    need(p.returncode==0,'GIT_SOURCE');return p.stdout
def pinned(path,pin):
    raw=(ROOT/path).read_bytes();old=git('cat-file','blob',pin)
    need(git('rev-parse','HEAD:'+path).decode().strip()==pin and raw.replace(b'\r\n',b'\n')==old.replace(b'\r\n',b'\n'),'PIN_DRIFT')
    return raw
def return_fields(raw,function):
    tree=ast.parse(raw);fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==function)
    last=next(x for x in reversed(fn.body) if isinstance(x,ast.Return))
    need(isinstance(last.value,ast.Call) and isinstance(last.value.func,ast.Name) and last.value.func.id=='dict','RETURN_SHAPE')
    return [k.arg for k in last.value.keywords]
def completion_evidence(raw):
    """Static schema observation, never pretends to observe a historical run."""
    keys=return_fields(raw,'reconcile');proof=return_fields(raw,'pilot_receipts')
    need(set(proof)=={'native_receipt_sha256','journal_sha256','independent_receipt_sha256','manifest_sha256','wal_files'},'PROOF_SCHEMA_DRIFT')
    own_clock=any(k and re.search('monotonic|completed|finished|receipt',k) for k in keys)
    return dict(return_fields=keys,pilot_proof_fields=proof,own_completion_clock_declared=own_clock,
        observation='PINNED_SOURCE_SCHEMA_ONLY',actual_run_evidence_read=False,
        timestamp_inference_from_step_order=False)
def model_observations(r87_completion,r88_start):
    """Two synthetic schedules, same serialized schema: no timing claim."""
    need(type(r87_completion) is int and type(r88_start) is int,'MODEL_TIME_TYPE')
    return dict(r87_result_schema='rpf87-required-coverage-reconciliation-v1',r88_native_start=r88_start)
def audit():
    src={p:pinned(p,h) for p,h in PINS.items()};clock=completion_evidence(src['ci/reconcile-rpf86-required-coverage.py'])
    need(not clock['own_completion_clock_declared'],'SCHEMA_CHANGED_REQUIRES_REVIEW')
    tree=ast.parse(src['ci/run-rpf88-r72-owner-scope.py']);names=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NAMES' for t in n.targets)))
    excluded=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='EXCLUDED' for t in n.targets)))
    pins=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PINS' for t in n.targets)))
    target='runtime/tests/test_effectwitness_pge_r72.py';raw=pinned(target,pins[target]['blob']);cl=next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='BudgetTests')
    methods={n.name:sha(ast.dump(n,include_attributes=False).encode()) for n in cl.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
    need(len(methods)==25 and len(names)==18 and len(excluded)==7 and set(names).isdisjoint(excluded) and set(names)|set(excluded)==set(methods),'INVENTORY')
    row=next(x for x in strict(src['ci/runtime-contract-test-matrix.json'])['modules'] if x['path']==target)
    routes={x['selector']:x['route'] for x in row['rules']}
    need(all(routes['BudgetTests.'+n]=='DEDICATED_RUNNER' for n in names),'ROUTE')
    workflow=src['.github/workflows/release-gate.yml'].decode()
    need(workflow.index('Reconcile admitted RPF-86 required methods')<workflow.index('Run RPF-88 R72 fresh-owner cohort pilot'),'WORKFLOW_SEQUENCE')
    return dict(status='UNAVAILABLE',decision='B_UNACTIVATED',reason='RPF87_COMPLETION_OBSERVATION_UNAVAILABLE',
        source={p:dict(blob=PINS[p],raw_sha256=sha(b),lf_sha256=sha(b.replace(b'\r\n',b'\n'))) for p,b in src.items()},
        clock=clock,workflow_step_order='SOURCE_FACT; NOT_USED_AS_NATIVE_COMPLETION_RECEIPT',
        selected=['runtime.tests.test_effectwitness_pge_r72.BudgetTests.'+n for n in names],excluded=list(excluded),method_ast=methods,
        native_RPF88_revalidation='NOT_RUN',RPF87_recomputation='NOT_RUN',new_admissions=0,
        baseline_counts_reverified=False,release_eligible=False,release_executed=False,deployment_authorized=False)
def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['diagnose','assess','enforce'])
    # These parameters are parsed for fail-closed compatibility, NEVER opened.
    for k in ('rpf87','rpf88','output','run-id','attempt','commit','fixture-root'):ap.add_argument('--'+k)
    ap.add_argument('--synthetic',action='store_true');a=ap.parse_args(argv)
    if a.command!='diagnose':
        print('UNAVAILABLE:RPF87_COMPLETION_OBSERVATION_UNAVAILABLE; B_UNACTIVATED; NO_RELEASE/NO_DEPLOY',file=sys.stderr);return 2
    try:print(json.dumps(audit(),sort_keys=True));return 2
    except (Invalid,KeyError,ValueError,OSError,StopIteration):
        print('INVALID_GATE_INPUT:SOURCE_AUDIT; NO_RELEASE/NO_DEPLOY',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
