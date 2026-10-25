"""Explicit zero-Provider runner and raw-anchored compatibility/component CLI."""
import argparse
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_r72r3_contracts as c,pge_r72r3_owner_source as s
from runtime.runproof_runtime.effectwitness import pge_r72r3_session as session,pge_r72r3_verify as verifier
from runtime.runproof_runtime.effectwitness import pge_r72r3_budget_policy as policy

def component_context():
    return s.Context(s.OwnerScope('rpf72r3-'+'a'*16),s.SourceCapsule.observe(),(29001,29002,29003))

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('normal','fault','normal-corrective','fault-corrective','verify','component','verify-component','pressure','smoke','smoke-B','smoke-reject','verify-smoke'))
    p.add_argument('--domain',choices=c.DOMAINS);p.add_argument('--case',choices=('legal-high','limit-minus-one','limit-equal','limit-plus-one'));p.add_argument('--path');p.add_argument('--sha256');args=p.parse_args()
    if args.mode=='verify':return verifier.cli([args.path]+(['--sha256',args.sha256] if args.sha256 else []))
    if args.mode=='verify-component':
        if not args.sha256:print('EXTERNAL_RAW_ANCHOR_REQUIRED');return 2
        try:
            raw=Path(args.path).read_bytes();c.require(c.sha(raw)==args.sha256,'EXTERNAL_RAW_ANCHOR')
            print(c.canonical(policy.verify_component(c.strict(raw),component_context())).decode());return 0
        except (ValueError,KeyError,IndexError,TypeError,OSError) as exc:print('REJECTED:'+str(exc));return 3
    def network_guard(event,values):
        if event=='socket.connect' and type(values[1]) is tuple:c.require(values[1][0] in ('127.0.0.1','::1','localhost'),'NON_LOOPBACK_DENIED')
        elif event=='socket.getaddrinfo':c.require(values[0] in ('127.0.0.1','::1','localhost',None),'NON_LOOPBACK_DNS_DENIED')
    sys.addaudithook(network_guard)
    if args.mode=='verify-smoke':
        if not args.sha256:print('EXTERNAL_RAW_ANCHOR_REQUIRED');return 2
        from runtime.runproof_runtime.effectwitness.pge_r72r3_sdk_contract import verify_proof
        try:
            raw=Path(args.path).read_bytes();c.require(c.sha(raw)==args.sha256,'EXTERNAL_RAW_ANCHOR')
            obj=c.strict(raw);ctx=s.Context(s.OwnerScope(obj['owner']['run_id']),s.SourceCapsule(c.canonical(obj['source'])),obj['context']['ports'])
            from runtime.runproof_runtime.effectwitness.pge_r72r3_budget_policy import BudgetPolicy
            verify_proof(ctx,BudgetPolicy(c.canonical(obj['policy'])),obj['contract'],obj['sdk'],[f['event'] for f in obj['frames']])
            print('HISTORICAL_SMOKE_PASS');return 0
        except (ValueError,KeyError,TypeError,IndexError,OSError,StopIteration) as exc:print('REJECTED:'+str(exc));return 3
    if args.mode in ('smoke','smoke-B','smoke-reject'):
        import secrets,socket
        from runtime.runproof_runtime.effectwitness.pge_r72r3_sdk_contract import smoke
        ports=[]
        while len(ports)<3:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            if port not in ports:ports.append(port)
        ctx=s.Context(s.OwnerScope('rpf72r3-'+secrets.token_hex(8)),s.SourceCapsule.observe(),ports)
        obj=smoke(ctx,reject=args.mode=='smoke-reject',variant='B' if args.mode=='smoke-B' else 'A')
        print(c.canonical(dict(status=obj['status'],path=(ctx.root/'smoke-result.json').relative_to(ROOT).as_posix(),sha256=c.digest(obj))).decode());return 0 if obj['status']=='PASS' else 1
    if args.mode=='pressure':
        import secrets
        from runtime.runproof_runtime.effectwitness.pge_r72r3_sdk_contract import pressure
        ctx=s.Context(s.OwnerScope('rpf72r3-'+secrets.token_hex(8)),s.SourceCapsule.observe(),(29001,29002,29003))
        obj=pressure(ctx,args.domain,args.case)
        print(c.canonical(dict(status=obj['status'],path=(ctx.root/('pressure-'+args.case)/'result.json').relative_to(ROOT).as_posix(),sha256=c.digest(obj))).decode());return 0 if obj['status']=='PASS' else 1
    if args.mode=='component':
        ctx=component_context();obj=policy.provider_component(ctx);folder=ROOT/'.local/rpf-72-rev-3/component';folder.mkdir(exist_ok=True)
        path=folder/('provider-budget-model-'+s.identity()['lf_digest'][:12]+'.json')
        with path.open('xb') as f:f.write(c.canonical(obj))
        print(c.canonical(dict(status='SYNTHETIC_COMPONENT_PASS',path=path.relative_to(ROOT).as_posix(),sha256=c.digest(obj))).decode());return 0
    fault=args.mode.startswith('fault');row=session.run_session(fault,corrective=args.mode.endswith('corrective'))
    manifest=session.manifest(row);verifier.verify(manifest);path=ROOT/'.local/rpf-72-rev-3'/(args.mode+'-manifest.json')
    with path.open('xb') as f:f.write(c.canonical(manifest))
    print(c.canonical(dict(status='LOCAL_COMPATIBILITY_PASS',path=path.relative_to(ROOT).as_posix(),sha256=c.digest(manifest),run_id=row['context']['session_id'])).decode());return 0

if __name__=='__main__':raise SystemExit(main())
