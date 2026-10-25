"""Immutable budget decisions derived only from the native physical WAL."""
from dataclasses import dataclass
from . import pge_r72r2_contracts as c
from . import pge_r68_context as n

VERSION = 'rpf72r2-budget-policy-v1'
TAG = 'RPF72R2_BUDGET'
AUTH = 'RPF72R2_AUTHORIZATION'
STATUSES = dict(session=('COMPLETED',), trial=('VERIFIED',), sdk=('COMPLETED',), host=('CLOSED',),
                jvm=('CLOSED',), sqlite_setup=('CREATED',), sqlite_refund=('COMMITTED','UNKNOWN'),
                config_post=('COMMITTED','UNKNOWN'), config_http=('RECEIVED',),
                config_health=('READ_ONLY',), authority_read=('READ_ONLY',), explorer_calls=('SELECTED',))

def specification(ctx):
    slots = [n.slot_scope(domain,i,role,ordinal) for i,domain in enumerate(c.DOMAINS,1)
             for role in ('EXPLORER','TARGET') for ordinal in range(1,len(n.CAPS['EXPLORER' if role=='EXPLORER' else domain])+1)]
    return dict(schema=VERSION, owner=ctx.owner.public(), source_capsule_sha256=ctx.source.raw_sha256,
                source_lf_digest=ctx.source.public()['lf_digest'], source_raw_digest=ctx.source.public()['raw_digest'],
                source_kind=c.KIND, native_budget_version=n.BUDGET_VERSION, slots=slots,
                native_limits=n.LIMITS, actual_provider_limit=0, actual_key_lookup=0,
                actual_usage=0, admission=False, refundable=False, independent_balance=False,
                reachable_tokens=n.REACHABLE_TOKENS, global_tokens=n.GLOBAL_TOKENS, max_slot=n.MAX_SLOT,
                component_provider_limit=11, child_cumulative={d:sum(n.CAPS[d]) for d in c.DOMAINS},
                historical_price_reference=dict(source='pge_r68_contracts.PRICE', raw_sha256=c.digest(n.PRICE),
                    input_half_micro_cny=9, output_half_micro_cny=36, maximum_micro_cny=15000000,
                    invoice='NOT_QUERIED', refreshed=False), sdk_pin=n.pinned_sdk_fields(),
                unknown='STOP_WRITES_IN_DOMAIN_UNTIL_VERIFIED;UNSETTLED_NATIVE_UNKNOWN_GLOBAL_STOP',
                journal='ONE_NATIVE_PHYSICAL_WAL', issuer=False)

@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    frozen: bytes

    @classmethod
    def create(cls, ctx):
        return cls(c.canonical(specification(ctx)))

    def public(self):
        c.require(type(self.frozen) is bytes, 'POLICY_BYTES')
        return c.strict(self.frozen)

    @property
    def raw_sha256(self):
        return c.sha(self.frozen)

    def check(self, ctx):
        c.equal(self.public(),specification(ctx),'POLICY_IDENTITY')
        c.require(self.frozen==c.canonical(self.public()),'POLICY_CANONICAL')

def state_projection(state):
    return {k:state[k] for k in ('counts','tickets','results','unknown','blocked','reserved_tokens','reserved_cost_micro_cny')}

def authorization(events, resource, parameters, *, settlement=False):
    active = {}
    for e in events:
        if e.get('audit_type') != AUTH:
            continue
        key=e['operation_sha256']
        if e['status']=='GRANTED':active[key]=e['operation']
        elif e['status'] in ('COMPLETED','REJECTED'):active.pop(key,None)
    phases=dict(session=('session',),trial=('trial',),sdk=('driver',),host=('driver',),
                jvm=('cleanup',) if settlement else ('prepare',),sqlite_setup=('prepare',),
                sqlite_refund=('business',),config_post=('business',),
                config_http=('business','authority','prepare'),config_health=('prepare',),
                authority_read=('authority',),explorer_calls=('select',))
    c.require(resource in phases,'RESOURCE_ALLOWLIST')
    candidates=[]
    for key,op in active.items():
        if op['phase'] not in phases[resource]:continue
        if resource in ('sqlite_setup','sqlite_refund') and op['domain']!=c.DOMAINS[1]:continue
        if resource in ('jvm','config_post','config_http','config_health') and op['domain']!=c.DOMAINS[0]:continue
        if 'domain' in parameters and parameters['domain']!=op['domain']:continue
        if 'round' in parameters and parameters['round']!=op['round']:continue
        if resource=='sqlite_refund' and op['tool']!='refund_order':continue
        if resource=='sqlite_refund' and 'arguments_sha256' in parameters and parameters['arguments_sha256']!=c.digest(op['arguments']):continue
        if resource=='authority_read' and parameters.get('phase',op['tool'])!=op['tool']:continue
        if resource=='config_post' and (op['tool'] not in ('create_config_v1','update_config_v2') or parameters.get('operation')!=op['tool']):continue
        if resource=='config_http' and parameters.get('method')=='POST' and (op['phase']!='business' or parameters.get('operation')!=op['tool']):continue
        candidates.append((key,op))
    c.require(bool(candidates),'CURRENT_OWNER_OPERATION_REQUIRED')
    return candidates[-1]

def decide(policy, ctx, state, events, action, resource, ticket, parameters):
    policy.check(ctx)
    return _decide(policy, ctx, state, events, action, resource, ticket, parameters)

def _decide(policy, ctx, state, events, action, resource, ticket, parameters):
    c.require(type(parameters) is dict and resource in STATUSES and action in ('RESERVE','SETTLE'),'BUDGET_REQUEST')
    c.require(type(ticket) is str and type(resource) is str,'BUDGET_REQUEST_TYPES')
    c.require(resource!='provider','ZERO_PROVIDER')
    if action=='RESERVE':
        allowed=dict(session=set(),trial={'domain','round'},sdk={'domain','round'},host={'domain','round'},
                     jvm={'domain','round'},sqlite_setup=set(),sqlite_refund={'domain','round','arguments_sha256'},
                     config_post={'domain','round','operation'},config_http={'domain','round','method','operation'},
                     config_health=set(),authority_read={'domain','round','phase'},explorer_calls={'domain','round'})
        c.require(set(parameters)<=allowed[resource],'BUDGET_PARAMETER_FIELDS')
        if 'domain' in parameters:c.require(type(parameters['domain']) is str and parameters['domain'] in c.DOMAINS,'BUDGET_DOMAIN_TYPE')
        if 'round' in parameters:c.require(type(parameters['round']) is int and parameters['round'] in (1,2),'BUDGET_ROUND_TYPE')
        if 'domain' in parameters and 'round' in parameters:c.require(parameters['round']==c.DOMAINS.index(parameters['domain'])+1,'BUDGET_DOMAIN_ROUND')
        for name in ('arguments_sha256','operation','method','phase'):
            if name in parameters:c.require(type(parameters[name]) is str,'BUDGET_PARAMETER_TYPE')
        c.require(ticket==resource+'-'+str(state['counts'][resource]+1),'BUDGET_TICKET_SEQUENCE')
        safe=resource=='authority_read' or resource=='config_http' and parameters.get('method')=='GET'
        c.require(not (state['unknown'] or state['blocked']) or safe,'BUDGET_UNKNOWN_GLOBAL_STOP')
        pending=any(k not in state['results'] and value['resource'] in ('provider','sqlite_refund','config_post') for k,value in state['tickets'].items())
        c.require(not pending or safe,'BUDGET_UNSETTLED_STOP')
        c.require(type(state['counts'][resource]) is int and state['counts'][resource]<n.LIMITS[resource],'BUDGET_RESOURCE_LIMIT')
        key,op=authorization(events,resource,parameters)
        unknown_domains={e['domain'] for e in events if e['kind']=='TOOL_RETURN' and e['row']['result'].get('status')=='UNKNOWN_OUTCOME'}
        write=resource in ('sqlite_refund','config_post','sqlite_setup','jvm','sdk','host','trial') or resource=='config_http' and parameters.get('method')=='POST'
        c.require(not (write and op['domain'] in unknown_domains),'BUDGET_DOMAIN_UNKNOWN_STOP')
        if resource=='config_http':
            read_names=('initial_current','initial_history','inspect_config','reconcile_current','reconcile_history','final_list')
            c.require(parameters.get('method')=='GET' and parameters.get('operation') in read_names or
                      parameters.get('method')=='POST' and parameters.get('operation') in ('create_config_v1','update_config_v2'),'HTTP_METHOD_OPERATION')
    else:
        c.require(ticket in state['tickets'] and ticket not in state['results'] and state['tickets'][ticket]['resource']==resource,'BUDGET_SETTLEMENT_TICKET')
        c.require(parameters.get('status') in STATUSES[resource],'BUDGET_SETTLEMENT_STATUS')
        native=state['tickets'][ticket]
        key,op=authorization(events,resource,native,settlement=True)
    c.require(op['owner']==ctx.owner.public() and op['source_capsule_sha256']==ctx.source.raw_sha256,'BUDGET_OWNER_SOURCE')
    return dict(schema=VERSION,action=action,resource=resource,ticket=ticket,policy_sha256=policy.raw_sha256,
                source_capsule_sha256=ctx.source.raw_sha256,owner=ctx.owner.public(),
                operation_sha256=key,domain=op['domain'],role=op['role'],round=op['round'],
                run_id=op['run_id'],environment_id=op['environment_id'],
                parameters_sha256=c.digest(parameters),prior_state_sha256=c.digest(state_projection(state)))

def audit(frames, ctx, policy):
    """Independent forward fold; native replay remains the persistence authority."""
    from .pge_r68_budget import replay
    native=replay(frames,ctx.public())
    policy.check(ctx)
    state=dict(counts=dict.fromkeys(n.LIMITS,0),tickets={},results={},unknown=False,blocked=False,reserved_tokens=0,reserved_cost_micro_cny=0)
    events=[f['event'] for f in frames];covered=set();transactions=[]
    for i,e in enumerate(events):
        if e.get('audit_type')==TAG:
            c.require(e['status'] in ('CHECK','GRANTED','CONFIRMED','SETTLED'),'BUDGET_EVENT_STATUS')
            if e['status']=='CHECK':
                c.require(i+3<len(events),'ORPHAN_BUDGET_CHECK')
                g,actual,done=events[i+1:i+4]
                request=e['request'];action=request['action'];resource=request['resource'];ticket=request['ticket'];parameters=request['parameters']
                expected=_decide(policy,ctx,state,events[:i],action,resource,ticket,parameters)
                c.require(g.get('audit_type')==TAG and g.get('status')=='GRANTED','ORPHAN_BUDGET_GRANT')
                c.equal(g['decision'],expected,'BUDGET_DECISION_BINDING')
                c.require(e['policy_sha256']==policy.raw_sha256 and e['source_capsule_sha256']==ctx.source.raw_sha256,'BUDGET_CHECK_IDENTITY')
                c.require(actual['kind']==('RESERVE' if action=='RESERVE' else 'RESULT') and actual['ticket']==ticket,'POLICY_NATIVE_ORDER')
                actual_data={k:v for k,v in actual.items() if k not in ('kind','clock','session_id','ticket','resource')}
                c.equal(actual_data,parameters,'POLICY_NATIVE_PARAMETERS')
                c.require(action!='RESERVE' or actual['resource']==resource,'POLICY_NATIVE_RESOURCE')
                c.require(done.get('audit_type')==TAG and done.get('status')==('CONFIRMED' if action=='RESERVE' else 'SETTLED') and
                          done['decision_sha256']==c.digest(expected) and done['native_seq']==i+2 and done['native_event_sha256']==c.digest(actual),'POLICY_NATIVE_CONFIRMATION')
                covered.update((i,i+1,i+2,i+3));transactions.append(expected)
            else:c.require(i in covered,'ORPHAN_POLICY_EVENT')
        elif e['kind'] in ('RESERVE','RESULT'):
            c.require(i in covered,'NATIVE_BUDGET_BYPASS')
            if e['kind']=='RESERVE':state['counts'][e['resource']]+=1;state['tickets'][e['ticket']]=e
            else:state['results'][e['ticket']]=e;state['unknown']|=e.get('status')=='UNKNOWN'
        elif e.get('audit_type'):
            c.require(e['audit_type'] in (AUTH,'RPF72R2_SDK_CONTRACT'),'UNSUPPORTED_AUDIT_TYPE')
            if e['audit_type']=='RPF72R2_SDK_CONTRACT':
                c.require(e['status'] in ('CONFIG_VALIDATED','SERIALIZED_INPUT','RESULT_BOUND') and
                          e['domain'] in c.DOMAINS and type(e['round']) is int and
                          e['round']==c.DOMAINS.index(e['domain'])+1,'SDK_CONTRACT_AUDIT_SCOPE')
    c.equal(state_projection(state),state_projection(native),'POLICY_NATIVE_REPLAY_PARITY')
    return dict(status='PASS',transactions=transactions,projection=state_projection(state),physical_wal='NATIVE_ONLY')

def provider_component(ctx):
    """Deterministic native replay fixture; no Ledger, SDK, key or network calls."""
    from .pge_r68_budget import replay
    value=ctx.public()
    value['source_kind']='SYNTHETIC_BUDGET_COMPONENT_ONLY'
    value['workspace']='.local/rpf-72-rev-2/component'
    frames=[]
    def emit(kind,**data):
        event=dict(kind=kind,session_id=value['session_id'],clock=len(frames),**data)
        f=dict(seq=len(frames),previous=c.digest(frames[-1]) if frames else None,event=event)
        f['sha256']=c.digest(f);frames.append(f)
    emit('OWNER',context_sha256=c.digest(value))
    slots=[];count=0
    for i,domain in enumerate(c.DOMAINS,1):
        if i==2:emit('FEEDBACK_FROZEN',round=1,component_fixture_only=True)
        for role in ('EXPLORER','TARGET'):
            for ordinal in range(1,len(n.CAPS['EXPLORER' if role=='EXPLORER' else domain])+1):
                scope=n.slot_scope(domain,i,role,ordinal)
                q=dict(ordinal=ordinal,slot_scope=scope,slot_contract_sha256=c.digest(scope),slot_cap=scope['slot_cap'],
                       output_cap=scope['output_cap'],input_upper=scope['slot_cap']-scope['output_cap'],request_sha256='a'*64)
                if role=='TARGET':q['stage']='POST_RECONCILE_TERMINAL' if i==2 and ordinal==4 else 'READ_ONLY' if ordinal>=(4 if i==1 else 3) else 'PRE_COMMIT'
                c.require(n.validate_slot(q,domain,i,role),'COMPONENT_NATIVE_SLOT')
                count+=1;ticket='provider-'+str(count)
                emit('RESERVE',resource='provider',ticket=ticket,role=role,domain=domain,round=i,request=q)
                emit('RESULT',ticket=ticket,status='SIMULATED_ONLY_NO_CALL')
                slots.append(q)
    state=replay(frames,value)
    c.require(count==11 and state['reserved_tokens']==n.REACHABLE_TOKENS==474000 and n.GLOBAL_TOKENS==600000 and n.MAX_SLOT==160000,'COMPONENT_CAP_PARITY')
    c.require(state['reserved_cost_micro_cny']<=15000000 and sum(n.CAPS[c.DOMAINS[0]])==250000 and sum(n.CAPS[c.DOMAINS[1]])==160000,'COMPONENT_GUARDS')
    return dict(schema='rpf72r2-provider-budget-component-v1',source_kind='SYNTHETIC_BUDGET_COMPONENT_ONLY',
                context=value,slots=slots,frames=frames,counts=state['counts'],reserved_tokens=state['reserved_tokens'],
                simulated_cost_micro_cny=state['reserved_cost_micro_cny'],historical_price_reference=True,
                child_cumulative={d:sum(n.CAPS[d]) for d in c.DOMAINS},provider_network_calls=0,key_lookup=0,real_usage=0)

def verify_component(obj,ctx):
    c.equal(obj,provider_component(ctx),'COMPONENT_REFERENCE_PARITY')
    return dict(status='SYNTHETIC_COMPONENT_PASS',provider_network_calls=0)
