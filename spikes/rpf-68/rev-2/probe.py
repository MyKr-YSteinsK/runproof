"""Explicit RPF68/rev2 entry; no default network or paid operation."""
import sys,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_r68_context as c,pge_r68_session as s,pge_r68_verify as v
from runtime.runproof_runtime.effectwitness.pge_r68_budget import Ledger

def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('init','preflight','free','max-envelope','metadata','cold','admit','live','verify'));p.add_argument('--witness');p.add_argument('--sha256');a=p.parse_args()
 try:
  if a.mode=='verify':return v.main([a.witness]+(['--sha256',a.sha256] if a.sha256 else []))
  if a.mode=='free':result=s.synthetic()
  elif a.mode=='max-envelope':
   result=s.max_envelope()
   if result['status']!='PASS':print(c.canonical(dict(status='FAIL',mode=a.mode,result_sha256=c.digest(result),provider=0)).decode());return 3
  elif a.mode in ('init','preflight'):result=s.initialize().public()
  else:
   ctx=s.load();s.freeze_check(ctx);l=Ledger(ctx);result={'metadata':lambda:s.metadata(ctx,l),'cold':lambda:s.cold(ctx,l),'admit':lambda:s.admit(ctx,l),'live':lambda:s.live(ctx,l)}[a.mode]()
  print(c.canonical(dict(status='PASS',mode=a.mode,result_sha256=c.digest(result))).decode());return 0
 except Exception as e:print('STOP:'+type(e).__name__+(':'+str(e) if type(e) is ValueError else ''));return 3
if __name__=='__main__':raise SystemExit(main())
