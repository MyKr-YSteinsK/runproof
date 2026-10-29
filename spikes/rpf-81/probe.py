"""Bounded local host/sink orchestration and independent verification CLI."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime'))
from runproof_runtime.effectwitness import pge_r81_contracts as c
from runproof_runtime.effectwitness import pge_r81_loopback as loop
from runproof_runtime.effectwitness.pge_r81_oracle import inspect


def check_source(case_id):
    freeze=c.scope(c.WORK/'source-freeze.json')
    if freeze.exists():c.require(c.strict(freeze.read_bytes())['source_map']==c.source_map(),'SOURCE_DRIFT')
    else:c.require(c.spec(case_id)['stage']=='prefreeze','FORMAL_REQUIRES_FREEZE')


def snapshot(case_id):
    root=c.case_dir(case_id);receiver=c.scope(c.WORK/'receivers'/case_id);run=c.scope(c.WORK/'runs'/case_id)
    def js(p):
        p=c.scope(p);return c.strict(p.read_bytes()) if p.exists() else None
    def txt(p):
        p=c.scope(p);return p.read_text(encoding='utf8') if p.exists() else ''
    prior=c.scope(run/'pre-recovery.raw');received=c.scope(receiver/'received.raw')
    return dict(wal_raw=txt(root/'wal.jsonl'),journal_commits=[js(p) for p in sorted(c.scope(root/'commits').glob('*.json'))],before_recovery_hex=prior.read_bytes().hex() if prior.exists() else '',operations_raw=txt(root/'operations.jsonl'),calls_raw=txt(root/'calls.jsonl'),unknown_commit=js(root/'unknown-commit.json'),persist_failure=js(root/'persist-failure.json'),unknown_intent=js(root/'unknown-intent.json'),receiver_raw_hex=received.read_bytes().hex(),receiver_receipt=js(receiver/'receipt.json'),ready=js(receiver/'ready.json'),processes=js(run/'processes.json'),host_summaries=[js(run/('host-'+phase+'.json')) for phase in ('main','prepare','recover')])


def envelope(case_id,body,kind='LOCAL_LOOPBACK_ONLY'):
    return dict(abi='rpf81-bundle-v1',case_id=case_id,source=c.source_id(),kind=kind,fixture_sha256=c.digest(c.spec(case_id)),**body)


def proposal(case_id):
    spec=c.spec(case_id);c.require(not spec['localhost'],'PROPOSAL_SCOPE');frames=[]
    for kind in spec['proposal_kinds']:
        extra={}
        if kind=='OWNER':extra=dict(session_id='session-'+case_id,source_kind='FROZEN_UNSAFE_PROPOSAL',fixture_sha256=c.digest(spec))
        elif kind=='SLOT_RESERVED':extra=dict(ticket='ticket-1',domain='order',role='EXPLORER')
        elif kind=='UNKNOWN_OBSERVED':extra=dict(domain='config',role='TARGET',observed_mono=time.monotonic(),planned=True,triggered=True,observed=True,agent_exposed=False)
        elif kind=='SEND_BEGIN':extra=dict(ticket='ticket-1',payload_sha256=c.sha(spec['payload'].encode()),size=len(spec['payload'].encode()))
        elif kind=='SESSION_TERMINAL':extra=dict(status='TERMINATED')
        e=dict(kind=kind,owner=c.OWNER,abi=c.ABI,case_id=case_id,source=c.source_id(),**c.clock(),**extra)
        f=dict(seq=len(frames),previous=c.digest(frames[-1]) if frames else None,event=e);f['sha256']=c.digest(f);frames.append(f)
    return envelope(case_id,dict(wal_raw=''.join(c.canonical(f).decode()+'\n' for f in frames),journal_commits=[],before_recovery_hex='',operations_raw='',calls_raw='',unknown_commit=None,persist_failure=None,unknown_intent=None,receiver_raw_hex='',receiver_receipt=None,ready=None,processes=[],host_summaries=[]),'FROZEN_UNSAFE_PROPOSAL')


def run_case(case_id):
    check_source(case_id);spec=c.spec(case_id);run=c.scope(c.WORK/'runs'/case_id);run.mkdir(parents=True,exist_ok=False)
    if not spec['localhost']:
        value=proposal(case_id);c.once(run/'bundle.json',value);return dict(status='PROPOSAL_PREPARED_NOT_VERIFIED',case_id=case_id)
    processes=[];active=[]
    def launch(role,phase=None,port=None):
        log=c.scope(c.WORK/'stdout-stderr'/(case_id+'-'+role+('-'+phase if phase else '')));log.mkdir(parents=True,exist_ok=False)
        args=[sys.executable,'-X','utf8','-B','spikes/rpf-81/probe.py',role,'--case',case_id]
        if phase:args+=['--phase',phase,'--port',str(port)]
        out=(log/'stdout').open('wb');err=(log/'stderr').open('wb');start=c.clock();p=subprocess.Popen(args,stdout=out,stderr=err);active.append(p)
        return p,out,err,log,start,args
    def finish(job,expected):
        p,out,err,log,start,args=job
        try:code=p.wait(timeout=180)
        except subprocess.TimeoutExpired:
            if p.poll() is None:p.kill()
            code=p.wait();raise ValueError('OWNED_CHILD_TIMEOUT')
        finally:out.close();err.close()
        record=dict(role=args[5],phase=args[args.index('--phase')+1] if '--phase' in args else None,pid=p.pid,parent_pid=os.getpid(),invocation_prefix=['python','-X','utf8'],argv=args[3:],actual_argv_sha256=c.digest(args),start=start,end=c.clock(),exit=code,stdout_sha256=c.sha((log/'stdout').read_bytes()),stderr_sha256=c.sha((log/'stderr').read_bytes()))
        c.once(log/'receipt.json',record);processes.append(record);c.require(code==expected,'CHILD_EXIT:'+str(code)+':'+(log/'stderr').read_text()[-300:]);return record
    try:
        sink=launch('receiver');folder=c.scope(c.WORK/'receivers'/case_id);loop.wait_file(folder/'ready.json',process=sink[0]);ready=c.strict((folder/'ready.json').read_bytes());c.require(ready['pid']==sink[0].pid,'RECEIVER_PID')
        if spec['scenario']=='connect-fail':finish(sink,0)
        if spec['scenario']=='recovery':
            finish(launch('host','prepare',ready['port']),23)
            with (run/'pre-recovery.raw').open('xb') as f:f.write((c.case_dir(case_id)/'wal.jsonl').read_bytes());f.flush();os.fsync(f.fileno())
            finish(launch('host','recover',ready['port']),0)
        else:finish(launch('host','main',ready['port']),0)
        if sink[0].poll() is None:
            c.once(folder/'stop.json',dict(**c.clock()));finish(sink,0)
        elif spec['scenario']!='connect-fail':finish(sink,0)
        c.once(run/'processes.json',processes);value=envelope(case_id,snapshot(case_id));c.once(run/'bundle.json',value)
        return dict(status='PHYSICAL_PREPARED_NOT_VERIFIED',case_id=case_id,processes=len(processes),source=c.source_id())
    finally:
        for p in active:
            if p.poll() is None:p.kill();p.wait(timeout=5)


def rechain(raw):
    frames=[c.strict(x) for x in raw.splitlines()];prev=None
    for i,f in enumerate(frames):f['seq']=i;f['previous']=prev;f['sha256']=c.digest({k:z for k,z in f.items() if k!='sha256'});prev=c.digest(f)
    return ''.join(c.canonical(x).decode()+'\n' for x in frames)


def mutate(bundle,index):
    v=copy.deepcopy(bundle);frames=[c.strict(x) for x in v['wal_raw'].splitlines()]
    if index==0:frames[1]['seq']=True
    elif index==1:frames[1]['previous']='f'*64
    elif index==2:frames[0]['event']['owner']='wrong-owner'
    elif index==3:frames[0]['event']['source']='0'*64
    elif index==4:
        n=next(i for i,f in enumerate(frames) if f['event']['kind']=='UNKNOWN_OBSERVED');del frames[n]
    elif index==5:
        v['source']='f'*64;frames[0]['event']['owner']='forged-owner';frames[0]['event']['source']='f'*64
    else:raise ValueError('MUTATION_INDEX')
    text=''.join(c.canonical(f).decode()+'\n' for f in frames)
    v['wal_raw']=rechain(text) if index>=2 else text
    c.require(c.canonical(v)!=c.canonical(bundle),'TEST_INVALID_NO_OP');return v


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('run','host','receiver','verify','negative'));parser.add_argument('--case',required=True);parser.add_argument('--phase',choices=('main','prepare','recover'));parser.add_argument('--port',type=int);parser.add_argument('--file');parser.add_argument('--sha');args=parser.parse_args()
    try:
        check_source(args.case)
        if args.command=='run':value=run_case(args.case);code=0
        elif args.command=='receiver':value=loop.receiver(args.case);code=0
        elif args.command=='host':value=loop.host(args.case,args.phase,args.port);code=0
        elif args.command=='verify':
            if not args.file or not args.sha:value=dict(status='NOT_RUN',classification='ANCHOR_REQUIRED');code=2
            else:
                p=c.scope(args.file);c.require(p.suffix=='.json','FILE_TYPE');value=inspect(p.read_bytes(),args.sha,c.source_id(),c.spec(args.case),c.WORK);code=0 if value['status']=='CONFORMANT' else 4 if value['status']=='INCOMPLETE' else 3
        else:
            original=c.strict((c.WORK/'runs'/args.case/'bundle.json').read_bytes());folder=c.scope(c.WORK/'negative'/args.case);folder.mkdir(parents=True,exist_ok=False);items=[]
            for i in range(6):
                v=mutate(original,i);file=folder/(str(i)+'.json');c.once(file,v);items.append(dict(index=i,file=file.relative_to(c.ROOT).as_posix(),raw_sha256=c.sha(file.read_bytes())))
            c.require(len({x['raw_sha256'] for x in items})==6,'DUPLICATE_MUTATIONS');c.once(folder/'manifest.json',items);value=dict(status='PREPARED_NOT_CLI_PROVEN',count=6);code=0
    except (OSError,ValueError,KeyError,TypeError) as exc:code=3;value=dict(status='INVALID',classification=str(exc),error_type=type(exc).__name__)
    print(c.canonical(value).decode(),flush=True);return code


if __name__=='__main__':raise SystemExit(main())
