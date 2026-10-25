"""RPF73 bounded real child entrypoint and raw-anchored offline component CLI."""
import argparse
from pathlib import Path
import socket
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_r73_contracts as c
from runtime.runproof_runtime.effectwitness.pge_r73_launch_contract import LaunchRequest,CASES
from runtime.runproof_runtime.effectwitness.pge_r73_domain_adapters import DomainAdapter
from runtime.runproof_runtime.effectwitness.pge_r73_verify import verify_bytes
def main():
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
 run=sub.add_parser('run');run.add_argument('--case',choices=tuple(CASES),required=True)
 verify=sub.add_parser('verify');verify.add_argument('--manifest',required=True);verify.add_argument('--sha')
 args=parser.parse_args()
 if args.command=='verify':
  if args.sha is None:print(c.canonical(dict(status='UNANCHORED')).decode());return 2
  try:
   p=Path(args.manifest);p=p if p.is_absolute() else ROOT/p;c.scope(p)
   print(c.canonical(verify_bytes(p.read_bytes(),args.sha)).decode());return 0
  except (ValueError,TypeError,KeyError,UnicodeError,OverflowError,OSError) as error:
   code=str(error) if type(error) is ValueError else type(error).__name__;print(c.canonical(dict(status='REJECTED',reason=code)).decode());return 3
 from runtime.runproof_runtime.effectwitness.pge_r73_launch_factory import LaunchFactory
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 request=LaunchRequest.build(args.case,port)
 marker=LaunchFactory().launch(request,DomainAdapter(CASES[args.case]))
 if args.case!='development':verify_bytes((ROOT/marker['path']).read_bytes(),marker['sha256'])
 print(c.canonical(marker).decode());return 0
if __name__=='__main__':raise SystemExit(main())
