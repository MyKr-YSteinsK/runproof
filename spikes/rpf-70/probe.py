"""Explicit local fixture CLI; no Provider configuration or credentials."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_r70_contracts as c
from runtime.runproof_runtime.effectwitness import pge_r70_owner_source as s
from runtime.runproof_runtime.effectwitness import pge_r70_session as session
from runtime.runproof_runtime.effectwitness import pge_r70_verify as verifier

def pre_execution(value):
    """Call the real gated Port entry; intercept native effects only as a tripwire."""
    from unittest.mock import patch
    from runtime.runproof_runtime.effectwitness.pge_r70_capability import Gate, AuthorizedOperation
    from runtime.runproof_runtime.effectwitness.pge_r70_ports import adapter, NativeConfig, OwnedOrder
    ctx = s.Context(s.OwnerScope(value['session_id']), s.SourceCapsule.observe(), value['ports'])
    ct = ctx.contract(value['round'], value['candidate'])
    class Audit:
        def __init__(self):
            self.ctx, self.events = ctx, []
        def append(self, kind, **data):
            self.events.append(dict(kind=kind, **data))
    ledger = Audit()
    port = adapter(ctx, ct, ledger)
    entered = []
    def trap(*_a, **_kw):
        entered.append(True)
        raise RuntimeError('NATIVE_EFFECT_TRIPWIRE_ENTERED')
    op = AuthorizedOperation(c.canonical(value['operation']))
    try:
        with patch.object(NativeConfig, 'prepare', trap), patch.object(OwnedOrder, 'prepare', trap), patch.object(NativeConfig, 'business', trap), patch.object(OwnedOrder, 'business', trap):
            if value['stage'] == 'prepare':
                port.prepare(ctx, ct, ledger, operation=op)
            elif value['stage'] == 'invoke':
                port.prepare_common(ctx, ct, ledger)
                port.gate.prepared = True
                port.pending = value['pending']
                port.invoke({k:port.pending[k] for k in ('call_id','name','arguments')}, operation=op)
            else:
                c.require(False, 'PREEXEC_STAGE')
    except ValueError as exc:
        c.require(not entered and any(e.get('status')=='REJECTED' for e in ledger.events), 'TEST_INVALID_NO_GATE_REJECTION')
        print(c.canonical(dict(classification='REJECTED', reason=str(exc), native_effect_entries=0,
                               audit_sha256=c.digest(ledger.events), stage=value['stage'])).decode())
        return 3
    raise RuntimeError('TEST_INVALID_ACCEPTED_NEGATIVE')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=('normal','fault','normal-corrective','verify','pre-execution'))
    p.add_argument('--path')
    p.add_argument('--sha256')
    args = p.parse_args()
    if args.mode == 'verify':
        return verifier.cli([args.path] + (['--sha256', args.sha256] if args.sha256 else []))
    if args.mode == 'pre-execution':
        if not args.sha256:
            return 2
        raw = Path(args.path).read_bytes()
        c.require(c.sha(raw)==args.sha256,'EXTERNAL_RAW_ANCHOR')
        return pre_execution(c.strict(raw))
    def network_guard(event, values):
        if event == 'socket.connect':
            address = values[1]
            if type(address) is tuple:
                c.require(address[0] in ('127.0.0.1','::1','localhost'), 'NON_LOOPBACK_DENIED')
        elif event == 'socket.getaddrinfo':
            c.require(values[0] in ('127.0.0.1','::1','localhost',None), 'NON_LOOPBACK_DNS_DENIED')
    sys.addaudithook(network_guard)
    row = session.run_session(args.mode=='fault', corrective=args.mode=='normal-corrective')
    manifest = session.manifest(row)
    verifier.verify(manifest)
    path = s.ROOT / '.local/rpf-70' / (args.mode+'-manifest.json')
    with path.open('xb') as f:
        f.write(c.canonical(manifest))
    print(c.canonical(dict(status='LOCAL_COMPATIBILITY_PASS', path=path.relative_to(s.ROOT).as_posix(),
                           sha256=c.sha(path.read_bytes()), run_id=row['context']['session_id'])).decode())
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
