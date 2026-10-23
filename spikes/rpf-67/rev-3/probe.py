"""RPF67 rev3 sole task entry; all free modes avoid credential lookup."""
import argparse,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_r67_context as c
from runtime.runproof_runtime.effectwitness import pge_r67_session as s
from runtime.runproof_runtime.effectwitness import pge_r67_order_verify as v
def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('init','diagnose-http','metadata','cold','admit','live','verify'));parser.add_argument('--phase',choices=('baseline','post'),default='baseline');parser.add_argument('--witness');parser.add_argument('--sha256');args=parser.parse_args()
    try:
        if args.mode=='diagnose-http':
            root=ROOT/'.local/rpf-67-rev-3';owner=dict(owner='rpf-67-rev-3',base='7858badb829265b738fc7ccf2de31711df51d9c8',created_by='spikes/rpf-67/rev-3/probe.py',credential_lookup=False)
            path=root/'owner.json'
            if path.exists():c.require(c.strict(path.read_bytes())==owner,'OWNER_IDENTITY')
            else:
                with path.open('xb') as f:f.write(c.canonical(owner));f.flush();__import__('os').fsync(f.fileno())
            sys.argv=[str(root/'http_diagnostic.py'),args.phase];runpy.run_path(str(root/'http_diagnostic.py'),run_name='__main__');result=dict(phase=args.phase)
        elif args.mode=='verify':return v.main([args.witness]+(['--sha256',args.sha256] if args.sha256 else []))
        elif args.mode=='init':result={'context_sha256':c.digest(s.initialize().public())}
        else:
            ctx=s.load();ledger=c.Ledger(ctx)
            if args.mode in ('metadata','cold'):s.freeze_check(ctx)
            result={'metadata':lambda:c.metadata(ctx,ledger),'cold':lambda:s.cold(ctx,ledger),'admit':lambda:s.admit(ctx,ledger),'live':lambda:s.live(ctx,ledger)}[args.mode]()
        print(c.canonical(dict(mode=args.mode,status='PASS',result_sha256=c.digest(result))).decode());return 0
    except Exception as error:print('BLOCKED:'+type(error).__name__+(':'+str(error) if type(error) is ValueError else ''));return 3
if __name__=='__main__':raise SystemExit(main())
