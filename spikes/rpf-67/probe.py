"""RPF67 bounded order Target entry point; free modes never read a Provider key."""
import argparse, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_r67_context as c
from runtime.runproof_runtime.effectwitness import pge_r67_session as s
from runtime.runproof_runtime.effectwitness import pge_r67_order_verify as v

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('init','metadata','cold','admit','live','verify'));p.add_argument('--witness');p.add_argument('--sha256');a=p.parse_args()
    try:
        if a.mode=='verify':return v.main([a.witness]+(['--sha256',a.sha256] if a.sha256 else []))
        if a.mode=='init':ctx=s.initialize();result={'context_sha256':c.digest(ctx.public())}
        else:
            ctx=s.load();ledger=c.Ledger(ctx)
            if a.mode in ('metadata','cold'):s.freeze_check(ctx)
            result={'metadata':lambda:c.metadata(ctx,ledger),'cold':lambda:s.cold(ctx,ledger),'admit':lambda:s.admit(ctx,ledger),'live':lambda:s.live(ctx,ledger)}[a.mode]()
        print(c.canonical(dict(mode=a.mode,status='PASS',result_sha256=c.digest(result))).decode());return 0
    except Exception as e:print('BLOCKED:'+type(e).__name__+(':'+str(e) if type(e) is ValueError else ''));return 3
if __name__=='__main__':raise SystemExit(main())
