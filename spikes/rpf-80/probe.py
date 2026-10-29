"""Bounded offline fixtures, source binding, CLI. No legacy imports or I/O tools."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime'))
from runproof_runtime.effectwitness.pge_r80_oracle import inspect
from runproof_runtime.effectwitness.pge_r80_unknown_barrier import initial,step
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.local/rpf-80-unknown-provider-reservation-oracle'
SOURCES=('runtime/runproof_runtime/effectwitness/pge_r80_unknown_barrier.py','runtime/runproof_runtime/effectwitness/pge_r80_oracle.py','runtime/tests/test_effectwitness_pge_r80.py','spikes/rpf-80/probe.py','spikes/rpf-80/fixtures.json')


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(x):return hashlib.sha256(x).hexdigest()


def source_map():return {p:dict(raw_sha256=sha((ROOT/p).read_bytes()),lf_sha256=sha((ROOT/p).read_bytes().replace(b'\r\n',b'\n'))) for p in SOURCES}


def path(value):
    p=Path(value).absolute()
    if p.suffix!='.json' or not p.is_relative_to(WORK):raise ValueError('FILE_SCOPE')
    for q in (p,*p.parents):
        if q.is_symlink() or q.is_junction():raise ValueError('FILE_REPARSE')
        if q==ROOT:break
    if p.resolve()!=p:raise ValueError('FILE_CANONICAL')
    return p


def cases():return json.loads((ROOT/'spikes/rpf-80/fixtures.json').read_bytes())['cases']


def rechain(v):
    previous=None
    for i,f in enumerate(v['frames']):
        f['seq']=i;f['previous']=previous;f['sha256']=sha(canonical({k:z for k,z in f.items() if k!='sha256'}));previous=sha(canonical(f))
    return v


def mutation(v,index):
    if type(index) is not int or not 0<=index<8:raise ValueError('MUTATION_INDEX')
    x=copy.deepcopy(v);fs=x['frames'];u=next(i for i,f in enumerate(fs) if f['event']['kind']=='TOOL_RETURN');r=next(i for i,f in enumerate(fs) if i>u and f['event']['kind']=='RESERVE')
    if index==0:fs[1]['seq']=True
    elif index==1:fs[1]['previous']='f'*64
    elif index==2:fs[r]['event']['session_id']='session-forged';rechain(x)
    elif index==3:fs[r]['event']['domain']='other';rechain(x)
    elif index==4:fs[r]['event']['role']='ALIEN';rechain(x)
    elif index==5:del fs[u];rechain(x)
    elif index==6:
        fs[u],fs[r]=fs[r],fs[u]
        for i,f in enumerate(fs):f['event']['clock']=i
        rechain(x)
    elif index==7:fs.pop();rechain(x)
    else:raise ValueError('MUTATION_INDEX')
    if canonical(x)==canonical(v):raise ValueError('TEST_INVALID_NO_OP')
    return x


def compare(v,result):
    state=initial();rows=[]
    for seq,f in enumerate(v['frames']):
        state,d=step(state,f['event']);rows.append(dict(seq=seq,**d))
    denied={x['seq'] for x in rows if x['reason']=='SESSION_UNKNOWN_NO_NEW_PROVIDER'}
    expected={x['reserve_seq'] for x in result.get('violations',[])}
    if result['status']!='INVALID' and denied!=expected:raise ValueError('ADMISSION_ORACLE_DIVERGENCE')
    return rows


def main():
    a=argparse.ArgumentParser();a.add_argument('command',choices=('generate','verify'));a.add_argument('--file');a.add_argument('--sha');a.add_argument('--case');args=a.parse_args()
    try:
        freeze=json.loads((WORK/'source-freeze.json').read_bytes())
        if source_map()!=freeze['source_map']:raise ValueError('SOURCE_IDENTITY')
        roster={x['id']:x for x in cases()}
        if args.command=='generate':
            folder=WORK/'streams';folder.mkdir(exist_ok=False);summary=[]
            for case in roster.values():
                raw=case['raw'].encode();file=folder/(case['id']+'.json')
                with file.open('xb') as f:f.write(raw)
                result=inspect(raw,sha(raw),case['raw_sha256']);summary.append(dict(case_id=case['id'],oracle=result,admission=compare(json.loads(raw),result)))
            original=json.loads(roster['violation-config-target']['raw']);negative=[]
            for i in range(8):
                raw=canonical(mutation(original,i));file=folder/('mutation-'+str(i)+'.json')
                with file.open('xb') as f:f.write(raw)
                negative.append(dict(file=str(file.relative_to(ROOT)),raw_sha256=sha(raw),case_id='violation-config-target'))
            with (WORK/'generated.json').open('xb') as f:f.write(canonical(dict(results=summary,mutations=negative)))
            value=dict(status='GENERATED_NOT_CLI_PROVEN',cases=len(summary),mutations=8);code=0
        elif not args.file or not args.sha:code,value=2,dict(status='NOT_RUN',reason='ANCHOR_OR_FILE_REQUIRED')
        else:
            raw=path(args.file).read_bytes();case=roster.get(args.case)
            if case is None:raise ValueError('REGISTERED_CASE_ID')
            value=inspect(raw,args.sha,case['raw_sha256']);code=0 if value['status']=='NO_VIOLATION' else 4 if value['status']=='INCONCLUSIVE' else 3
    except (ValueError,OSError,KeyError,TypeError) as exc:code,value=3,dict(status='INVALID',reason=str(exc))
    print(canonical(value).decode());return code


if __name__=='__main__':raise SystemExit(main())
