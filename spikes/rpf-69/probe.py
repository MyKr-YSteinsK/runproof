"""Explicit zero-Provider compatibility entry; never reads model credentials."""
import sys,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_r69_abi as a,pge_r69_compat as c,pge_r69_guard_audit as guard
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['run','guard','verify']);p.add_argument('--path');p.add_argument('--sha256');x=p.parse_args()
 if x.mode=='verify':return c.cli([x.path]+(['--sha256',x.sha256] if x.sha256 else []))
 if x.mode=='guard':print(a.canonical(guard.audit()).decode());return 0
 rows=[c.run_session(False),c.run_session(True)];m=c.manifest(rows);c.verify(m)
 with (ROOT/'.local/rpf-69/compatibility-manifest.json').open('xb') as f:f.write(a.canonical(m))
 print(a.canonical(dict(status='COMPATIBILITY_PASS',provider=0,sessions=2)).decode());return 0
if __name__=='__main__':raise SystemExit(main())
