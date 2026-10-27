"""One N or F session, with two domains and one native WAL."""
import secrets
import shutil
import socket
from . import pge_r74_contracts as c
from . import pge_r68_contracts as native
from .pge_r74_owner_source import Context, OwnerScope, SourceCapsule
from .pge_r74_budget_gate import BudgetLedger
from .pge_r74_domain_ports import ConfigPort, OrderPort
from .pge_r74_launch_contract import LaunchRequest
from .pge_r74_launch_factory import LaunchFactory

JAR = c.ROOT / '.local/rpf-51-rev4/upstream-config-center/config-center-server/target/config-center-server-1.0.0.jar'

def allocate_ports():
    ports = []
    while len(ports) < 3:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        if port not in ports:
            ports.append(port)
    return ports

def choose(ctx, ledger, ct, feedback=None):
    domain, index = ct['experiment']['domain'], ct['experiment']['round']
    if index == 2:
        c.require(type(feedback) is dict and feedback['domain'] == c.DOMAINS[0], 'FEEDBACK_SCOPE')
    else:
        c.require(feedback is None, 'FIRST_ROUND_FEEDBACK')
    request = dict(domain=domain, round=index, candidates=list(native.CANDIDATES[index-1]),
                   feedback=feedback, feedback_sha256=c.digest(feedback) if feedback is not None else None,
                   source='SCRIPTED_EXPLORER')
    with ledger.authorized('select', domain=domain, tool='select_experiment'):
        ticket = ledger.reserve('explorer_calls', domain=domain, round=index)
        proof = ledger.claim_slot(ct, 'EXPLORER', request, len(c.canonical(request)), 128)
        choice = dict(domain=domain, round=index, candidate_id=ct['experiment']['candidate_id'],
                      input=request, input_sha256=c.digest(request), proof=proof, source='SCRIPTED_EXPLORER')
        ledger.append('MODEL_RESPONSE', domain=domain, round=index, role='EXPLORER', ticket=None,
                      response=choice, usage_type='SYNTHETIC_VALIDATED_USAGE')
        ledger.settle(ticket, status='SELECTED')
    ledger.append('CHOICE', domain=domain, round=index, choice=choice, choice_sha256=c.digest(choice))
    return choice

def run(scenario):
    c.require(scenario in c.SCENARIOS, 'SCENARIO')
    frozen=c.strict((c.WORK/'source-freeze.json').read_bytes())
    source=SourceCapsule.observe()
    c.require(frozen['identity']==source.public() and frozen['source_sha256']==source.raw_sha256, 'SOURCE_FROZEN')
    marker = c.WORK / ('claim-' + scenario + '.json')
    if scenario == 'F':
        n_result = c.strict((c.WORK/'N-result.json').read_bytes())
        c.require(n_result['status'] == 'VERIFIED' and n_result['scenario'] == 'N', 'N_MUST_VERIFY_FIRST')
    run_id = 'rpf74-' + secrets.token_hex(8)
    owner = OwnerScope(run_id)
    owner.path(owner.root)
    with marker.open('xb') as f:
        f.write(c.canonical({'scenario':scenario,'run_id':run_id,'source_sha256':source.raw_sha256}))
        f.flush(); __import__('os').fsync(f.fileno())
    ctx = Context(owner, source, allocate_ports(), scenario)
    ctx.root.mkdir(parents=True, exist_ok=False)
    ctx.once(ctx.root/'context.json', ctx.public())
    ledger = BudgetLedger(ctx, create=True)
    factory = LaunchFactory()
    port = None; rows = []; feedback = None; session_ticket = None; trial_ticket = None
    try:
        with ledger.authorized('session', domain=c.DOMAINS[0], tool='session'):
            session_ticket = ledger.reserve('session')
        jar = ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar')
        jar.parent.mkdir()
        c.require(JAR.is_file() and not JAR.is_symlink() and c.sha(JAR.read_bytes()) == native.SOURCE_JAR_SHA256
                  and JAR.stat().st_size == native.SOURCE_JAR_BYTES, 'JAR_PIN')
        with JAR.open('rb') as src, jar.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        c.require(c.sha(jar.read_bytes()) == native.SOURCE_JAR_SHA256, 'JAR_COPY')
        for index in (1,2):
            ct = ctx.public()['rounds'][index-1]
            domain = ct['experiment']['domain']
            choice = choose(ctx, ledger, ct, feedback)
            with ledger.authorized('trial', domain=domain, tool='trial'):
                trial_ticket = ledger.reserve('trial', domain=domain, round=index)
            port = ConfigPort() if index == 1 else OrderPort()
            port.prepare(ctx, ct, ledger)
            ledger.append('PORT_ENTERED', domain=domain, round=index, factory='RPF74_V2')
            request = LaunchRequest.build(ctx, ct)
            sdk = factory.launch(ctx, ct, ledger, port, request)
            effect = port.finish()
            business_calls = port.r74_calls
            cleanup = port.cleanup(); port = None
            c.require(all(cleanup.values()), 'DOMAIN_CLEANUP')
            with ledger.authorized('trial', domain=domain, tool='trial'):
                ledger.settle(trial_ticket, status='VERIFIED')
            trial_ticket = None
            ledger.append('DOMAIN_VERIFIED', domain=domain, round=index, effect_sha256=c.digest(effect),
                          sdk_receipt_sha256=c.digest(sdk))
            verified_seq = ledger.frames[-1]['seq']
            feedback = dict(domain=domain, round=index, verdict='CONTRACT_SATISFIED_IN_RUN',
                source_effect_sha256=c.digest(effect), source_contract_sha256=c.digest(ct),
                verified_seq=verified_seq, candidate_id=choice['candidate_id'])
            ledger.append('FEEDBACK_FROZEN', domain=domain, round=index, feedback=feedback,
                          feedback_sha256=c.digest(feedback))
            rows.append(dict(contract=ct, choice=choice, sdk=sdk, business_calls=business_calls,
                             effect=effect, cleanup=cleanup, feedback=feedback))
        with ledger.authorized('session', domain=c.DOMAINS[0], tool='session'):
            ledger.settle(session_ticket, status='COMPLETED')
        session_ticket = None
        ledger.append('SESSION_COMPLETE', scenario=scenario, domains=2)
        state = ledger.read()
        manifest = dict(schema='rpf74-local-integration-manifest-v1', owner=c.OWNER, abi=c.ABI,
            source_kind=c.SOURCE_KIND, scenario=scenario, context=ctx.public(), source=source.public(),
            source_sha256=source.raw_sha256, policy=ledger.policy, policy_sha256=ledger.policy_sha256,
            domains=rows, wal=ledger.frames, wal_sha256=c.sha(ledger.path.read_bytes()),
            budget_projection={k:state[k] for k in ('counts','unknown','blocked','reserved_tokens')},
            model_source='SCRIPTED_PROVIDER', provider_calls=0, child_attestation=False, issuer=False)
        ctx.once(ctx.root/'manifest.json', manifest)
        return ctx.root/'manifest.json'
    except BaseException:
        if port is not None:
            try: port.cleanup()
            except BaseException: pass
        raise
