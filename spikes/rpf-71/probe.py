"""Explicit zero-Provider runner and raw-anchored compatibility/component CLI."""
import argparse
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_r71_contracts as c,pge_r71_owner_source as s
from runtime.runproof_runtime.effectwitness import pge_r71_session as session,pge_r71_verify as verifier
from runtime.runproof_runtime.effectwitness import pge_r71_budget_policy as policy

def component_context():
    return s.Context(s.OwnerScope('rpf71-'+'a'*16),s.SourceCapsule.observe(),(29001,29002,29003))

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('normal','fault','normal-corrective','fault-corrective','verify','component','verify-component'))
    p.add_argument('--path');p.add_argument('--sha256');args=p.parse_args()
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
    if args.mode=='component':
        ctx=component_context();obj=policy.provider_component(ctx);folder=ROOT/'.local/rpf-71/component';folder.mkdir(exist_ok=True)
        path=folder/('provider-budget-model-'+s.identity()['lf_digest'][:12]+'.json')
        with path.open('xb') as f:f.write(c.canonical(obj))
        print(c.canonical(dict(status='SYNTHETIC_COMPONENT_PASS',path=path.relative_to(ROOT).as_posix(),sha256=c.digest(obj))).decode());return 0
    fault=args.mode.startswith('fault');row=session.run_session(fault,corrective=args.mode.endswith('corrective'))
    manifest=session.manifest(row);verifier.verify(manifest);path=ROOT/'.local/rpf-71'/(args.mode+'-manifest.json')
    with path.open('xb') as f:f.write(c.canonical(manifest))
    print(c.canonical(dict(status='LOCAL_COMPATIBILITY_PASS',path=path.relative_to(ROOT).as_posix(),sha256=c.digest(manifest),run_id=row['context']['session_id'])).decode());return 0

if __name__=='__main__':raise SystemExit(main())
