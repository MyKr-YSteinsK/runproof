"""RPF-74 rev-2 ABI entry point under the rev-3 continuation Plan."""
import argparse
import json
import sys
from pathlib import Path
from runtime.runproof_runtime.effectwitness import pge_r74r2_contracts as c


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('--manifest', required=True)
    verify.add_argument('--sha256')
    run = sub.add_parser('run')
    run.add_argument('scenario', choices=['N', 'F'])
    sub.add_parser('status')
    sub.add_parser('freeze')
    sub.add_parser('history')
    sub.add_parser('full-runtime')
    negative = sub.add_parser('negative')
    negative.add_argument('--manifest', required=True)
    negative.add_argument('--sha256', required=True)
    plus = sub.add_parser('usage-counterexample')
    plus.add_argument('--manifest', required=True)
    plus.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if args.command == 'status':
        print(json.dumps({'status': 'DEVELOPMENT_DRAFT', 'source_frozen': (c.WORK/'source-freeze.json').exists()}))
        return 0
    if args.command in ('freeze', 'history', 'full-runtime'):
        import importlib
        runner = importlib.import_module('spikes.rpf-74.rev-2.runner')
        if args.command == 'freeze':
            result = runner.source_freeze()
            print(json.dumps({'status':'FROZEN','source_sha256':result['source_sha256']}))
            return 0
        if args.command == 'full-runtime':
            result=runner.full_runtime()
            print(json.dumps({'status':result['status'],'summary':result['summary']}))
            return 0 if result['status']=='PASS' else 3
        result = runner.history()
        print(json.dumps({'status':result['status'], 'commands':len(result['results'])}))
        return 0 if result['status']=='PASS' else 3
    if args.command in ('negative','usage-counterexample'):
        import importlib
        runner=importlib.import_module('spikes.rpf-74.rev-2.runner')
        path=Path(args.manifest)
        result=(runner.negative(path,args.sha256) if args.command=='negative'
                else runner.usage_counterexample(path,args.sha256))
        print(json.dumps({k:v for k,v in result.items() if k!='cases'}))
        return 0 if result['status']=='PASS' else 3
    if args.command == 'verify':
        if args.sha256 is None:
            print(json.dumps({'status': 'MISSING_ANCHOR'}))
            return 2
        from runtime.runproof_runtime.effectwitness.pge_r74r2_verify import verify
        try:
            result = verify(args.manifest, args.sha256)
            print(json.dumps({'status': 'PASS', 'result': result}))
            return 0
        except (ValueError, KeyError, TypeError, OSError) as exc:
            print(json.dumps({'status': 'FAIL', 'reason': str(exc)}))
            return 3
    from runtime.runproof_runtime.effectwitness.pge_r74r2_session import run
    from runtime.runproof_runtime.effectwitness.pge_r74r2_verify import verify
    import importlib
    runner=importlib.import_module('spikes.rpf-74.rev-2.runner')
    path=run(args.scenario); anchor=c.sha(path.read_bytes())
    result=verify(path,anchor)
    runner.once(c.WORK/(args.scenario+'-result.json'),
                {'status':'VERIFIED','scenario':args.scenario,'manifest':path.relative_to(c.ROOT).as_posix(),
                 'sha256':anchor,'verification':result})
    print(json.dumps({'status':'VERIFIED','manifest':str(path),'sha256':anchor}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
