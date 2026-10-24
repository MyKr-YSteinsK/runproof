"""Two-domain task-owned execution with real local effects and scripted models."""
import ctypes
import datetime
import secrets
import shutil
import socket
import time
from . import pge_r70_contracts as c
from . import pge_r70_owner_source as s
from . import pge_r68_context as n
from . import pge_r68_explorer as explorer
from .pge_r68_budget import Ledger
from .pge_r68_driver import Driver
from .pge_r70_capability import Gate
from .pge_r70_ports import adapter

def late(ctx):
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.restype = ctypes.c_void_p
    class FT(ctypes.Structure):
        _fields_ = [('lo', ctypes.c_uint32), ('hi', ctypes.c_uint32)]
    rows = []
    for e in Ledger(ctx).read()['events']:
        if e['kind'] != 'PROCESS_START':
            continue
        h = api.OpenProcess(0x1000, False, e['pid'])
        if not h:
            gone = ctypes.get_last_error() == 87
            status, created = 'NOT_PRESENT' if gone else 'UNAVAILABLE', None
        else:
            try:
                code, f = ctypes.c_uint32(), [FT() for _ in range(4)]
                ok = api.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
                okt = api.GetProcessTimes(ctypes.c_void_p(h), *[ctypes.byref(z) for z in f])
                created = ((f[0].hi << 32) + f[0].lo) / 1e7 - 11644473600 if okt else None
                expected = e.get('started_unix_ns', 0) / 1e9 or time.time() + (e['clock'] - time.monotonic_ns()) / 1e9
                gone = bool(ok and code.value != 259 or created is not None and created > expected + 5)
                status = 'EXITED_OR_REUSED' if gone else 'PRESENT_OR_UNAVAILABLE'
            finally:
                api.CloseHandle(ctypes.c_void_p(h))
        rows.append(dict(pid=e['pid'], resource=e['resource'], original_gone=gone,
                         status=status, observed_creation_unix=created, wal_start_clock=e['clock']))
    ports = []
    for port in ctx.public()['ports']:
        with socket.socket() as sock:
            sock.settimeout(.2)
            closed = sock.connect_ex(('127.0.0.1', port)) != 0
        ports.append(dict(port=port, closed=closed))
    return dict(status='PASS' if all(z['original_gone'] for z in rows) and all(z['closed'] for z in ports) else 'UNAVAILABLE',
                processes=rows, ports=ports, queried_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())

def run_session(fault, *, corrective=False):
    c.require(type(fault) is bool, 'SCENARIO')
    task = s.ROOT / '.local/rpf-70'
    c.require(type(corrective) is bool, 'CORRECTIVE_FLAG')
    claim = ('fault' if fault else 'normal') + ('-corrective-attempt.json' if corrective else '-attempt.json')
    with (task / claim).open('xb') as f:
        f.write(c.canonical(dict(source_kind=c.KIND, provider=0)))
    owner, source = s.OwnerScope('rpf70-' + secrets.token_hex(8)), s.SourceCapsule.observe()
    ports = []
    while len(ports) < 3:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        if port not in ports:
            ports.append(port)
    ctx = s.Context(owner, source, ports)
    ctx.root.mkdir(parents=True)
    ctx.once(ctx.root / 'context.json', ctx.public())
    ledger = Ledger(ctx, create=True)
    _, old = n.helpers()
    jar = ctx.scope(ctx.root / 'jar/config-center-server-1.0.0.jar')
    jar.parent.mkdir()
    c.require(c.sha(old.SOURCE_JAR.read_bytes()) == n.SOURCE_JAR_SHA256, 'JAR_PIN')
    with old.SOURCE_JAR.open('rb') as src, jar.open('xb') as dst:
        shutil.copyfileobj(src, dst)
    start, rows = time.monotonic(), []
    session_ticket = ledger.reserve('session')
    for i, domain in enumerate(c.DOMAINS, 1):
        c.require(time.monotonic() - start < 1200, 'SESSION_DEADLINE')
        candidate = n.CANDIDATES[i-1][int(fault)]
        ct = ctx.contract(i, candidate)
        selection_gate = Gate(ctx, ct, ledger)
        selection = selection_gate.enter('select', role='EXPLORER', tool='select_experiment', args=dict(candidate_id=candidate))
        choice = explorer.choose(ctx, ledger, i, rows, fixture=candidate)
        selection_gate.complete(selection, choice)
        port = adapter(ctx, ct, ledger)
        trial = ledger.reserve('trial', domain=domain, round=i)
        ledger.append('PORT_ENTERED', domain=domain, round=i, port_class=type(port).__module__ + '.' + type(port).__qualname__,
                      port_source_sha256=source.public()['source_map']['runtime/runproof_runtime/effectwitness/pge_r70_ports.py']['raw'])
        prepared = False
        try:
            port.prepare(ctx, ct, ledger)
            prepared = True
            sdk = Driver(ctx, ledger, ct, fixture=True).run(port)
            business = port.finish()
        finally:
            if prepared or hasattr(port, 'proc') or hasattr(port, 'reader'):
                cleanup = port.cleanup()
        evidence = dict(contract=ct, trace=port.trace, fault=port.fault, sdk=sdk, business=business, cleanup=cleanup)
        from .pge_r70_verify import verify_domain
        verify_domain(ctx, ct, evidence)
        ledger.settle(trial, status='VERIFIED')
        seq = len(ledger.frames)
        ledger.append('DOMAIN_VERIFIED', domain=domain, round=i, evidence_sha256=c.digest(evidence),
                      contract_sha256=c.digest(ct), oracle=business['oracle'])
        feedback = explorer.feedback(ct, evidence, choice, seq)
        ledger.append('FEEDBACK_FROZEN', domain=domain, round=i, feedback=feedback, feedback_sha256=c.digest(feedback))
        rows.append(dict(choice=choice, evidence=evidence, feedback=feedback))
    ledger.settle(session_ticket, status='COMPLETED')
    ledger.append('SESSION_COMPLETE', rounds=2)
    state = ledger.read()
    os_late = late(ctx)
    c.require(os_late['status'] == 'PASS' and not state['unknown'] and not state['blocked'] and
              set(state['tickets']) == set(state['results']) and state['counts']['provider'] == 0, 'FINAL_SETTLEMENT_CLEANUP')
    result = dict(schema='rpf70-session-v1', source_kind=c.KIND, model_source='SCRIPTED_PROVIDER', owner=owner.public(),
                  source=source.public(), source_capsule_sha256=source.raw_sha256, context=ctx.public(),
                  context_sha256=c.digest(ctx.public()), frames=ledger.frames,
                  wal_raw_sha256=c.sha(ledger.path.read_bytes()), rounds=rows, counts=state['counts'],
                  provider_calls=0, provider_usage=0, key_lookup=0, usage_confidence='SYNTHETIC_ONLY',
                  flags=c.FLAGS, status='LOCAL_COMPATIBILITY_PASS', late=os_late, elapsed_seconds=time.monotonic()-start)
    ctx.once(ctx.root / 'session-result.json', result)
    return result

def manifest(row):
    return dict(schema='rpf70-owner-source-manifest-v1', source_kind=c.KIND, identity=s.identity(),
                session=row, flags=c.FLAGS, issuer=False)
