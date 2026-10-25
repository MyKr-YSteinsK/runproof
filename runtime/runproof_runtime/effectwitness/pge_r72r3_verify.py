"""Strict raw-anchored local manifest verifier; never a historical Issuer."""
import argparse
from pathlib import Path
from . import pge_r72r3_contracts as c
from . import pge_r72r3_owner_source as s
from . import pge_r68_context as n
from . import pge_r68_explorer as explorer
from .pge_r68_budget import replay
from .pge_r72r3_capability import Gate
from .effect_oracle import evaluate_order_effect

def verify_domain(ctx, ct, e):
    c.equal(e['contract'], ct, 'DOMAIN_CONTRACT')
    c.require(all(type(v) is bool and v for v in e['cleanup'].values()) and
              all(type(v) is bool and v for v in e['sdk']['cleanup'].values()), 'DOMAIN_CLEANUP')
    domain, lost = ct['experiment']['domain'], ct['experiment']['fault_enabled']
    c.equal(e['fault'], dict.fromkeys(('planned','triggered','observed','agent_exposed'), lost), 'FAULT_FOUR_STATES')
    trace = e['trace']
    names = list(n.TOOLS[domain][:3 if domain == c.DOMAINS[0] else 2])
    c.equal([z['name'] for z in trace], names + ([n.TOOLS[domain][0 if domain == c.DOMAINS[0] else 2]] if lost else []), 'TOOL_ORDER')
    for row in trace:
        c.equal(row['arguments'], n.args_for(ct, row['name']), 'TRACE_ARGUMENTS')
        c.require(row['result_sha256'] == c.digest(row['result']), 'TOOL_RESULT_HASH')
    if domain == c.DOMAINS[0]:
        from .pge_r68_verify import verify_domain as native_config_verify
        native_config_verify(ctx.public(), ct, e)
    else:
        b = e['business']
        c.equal(b['oracle'], evaluate_order_effect(ct['effect'], ct['experiment']['environment_id'], b['before']['data'], b['after']['data']), 'ORDER_ORACLE')
        c.require(b['oracle']['contract_outcome'] == 'CONTRACT_SATISFIED_IN_RUN', 'ORDER_OUTCOME')
        for snap in (b['before'], b['after']):
            data = snap['data']
            c.require(snap['sha256'] == c.digest(data) and data['environment']['owner'] == c.OWNER and
                      data['environment']['run_id'] == ct['experiment']['run_id'] and
                      data['environment']['environment_id'] == ct['experiment']['environment_id'] and
                      data['environment']['reset_generation'] == 0 and data['source_id'] == ct['effect']['authority_id'], 'ORDER_AUTHORITY')
        c.require(len(b['after']['data']['receipts']) == 1 and b['after']['data']['receipts'][0]['amount_minor'] == 2500, 'SINGLE_REFUND')
    sdk = e['sdk']
    ready, pin = sdk['ready'], ct['execution']['sdk']
    c.require(ready['python_executable_sha256']==pin['python_executable_sha256'] and
              ready['sdk_site_root_binding_sha256']==pin['sdk_site_root_binding_sha256'] and
              ready['python_runtime_mapping_sha256']==pin['python_runtime_mapping_sha256'] and
              ready['sdk_source_sha256']=='70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa' and
              ready['openai_source_sha256']==pin['openai_core_sha256'] and ready['version']=='2.57.0' and
              ready['openai_version']=='3.35.1' and not sdk['report']['business_key_present'] and
              not sdk['report']['denied_files'] and sdk['report']['final_text_persisted'] is False, 'SDK_PIN_GUARD')
    c.require(sdk['child_sha256'] == ctx.public()['sources']['runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py']['raw'] and
              sdk['pid'] == sdk['ready']['pid'] == sdk['report']['pid'] and sdk['report']['status'] == 'COMPLETED' and
              not sdk['report']['guard_denials'] and sdk['report']['provider_key_present'] is False, 'SDK_IDENTITY')
    c.require(len(sdk['requests']) == len(trace)+1 and sdk['report']['requests'] == len(sdk['requests']) and
              sdk['report']['tool_calls'] == sdk['report']['tool_callbacks'] == len(trace), 'SDK_COUNTS')
    for j, row in enumerate(sdk['requests']):
        q, r = row['request'], row['response']
        c.require(n.validate_slot(q, domain, ct['experiment']['round'], 'TARGET'), 'SDK_SLOT')
        c.require(q['ordinal'] == j+1 and q['tool_returns'] == [dict(call_id=t['call_id'], result_sha256=t['result_sha256']) for t in trace[:j]], 'TOOL_REINJECTION')
        u = r['usage']
        c.require(all(type(x) is int and x >= 0 for x in u.values()) and u['total_tokens'] == u['prompt_tokens']+u['completion_tokens'] and
                  u['prompt_tokens'] <= q['input_upper'] and u['completion_tokens'] <= q['output_cap'], 'SYNTHETIC_USAGE')
        if j:
            c.require(q['previous_prompt'] == sdk['requests'][j-1]['response']['usage']['prompt_tokens'] and
                      q['input_upper'] == q['previous_prompt']+q['suffix_bytes']+512 and q['framing_guard'] == 512, 'SUFFIX_BOUND')
        else:
            c.require(q['input_upper'] == q['canonical_bytes'] and q['previous_prompt'] is None, 'INITIAL_BOUND')
        if j < len(trace):
            c.require(r['call']=={k:trace[j][k] for k in ('call_id','name','arguments')} and
                      r['response_id']==trace[j]['response_id'] and r['finish_reason']=='tool_calls', 'TARGET_RESPONSE_LINEAGE')
        else:
            c.require(r['call'] is None and r['finish_reason']=='stop','FINAL_STOP')
    c.require(sdk['report']['input_tokens'] == sum(x['response']['usage']['prompt_tokens'] for x in sdk['requests']) and
              sdk['report']['output_tokens'] == sum(x['response']['usage']['completion_tokens'] for x in sdk['requests']), 'SDK_USAGE_SUM')

class _NoIO:
    def __init__(self, ctx):
        self.ctx = ctx

def verify_processes(result, events):
    starts = [e for e in events if e['kind']=='PROCESS_START']
    closed = [e for e in events if e['kind']=='PROCESS_CLEANUP']
    expected = [('sdk',r['evidence']['sdk']['pid']) for r in result['rounds']]
    expected.append(('jvm',result['rounds'][0]['evidence']['business']['environment']['pid']))
    c.require(len(starts)==len(closed)==3 and sorted((e['resource'],e['pid']) for e in starts)==sorted(expected) and
              sorted((e['resource'],e['pid']) for e in closed)==sorted(expected), 'PROCESS_WAL_IDENTITY')
    c.require(sorted((e['resource'],e['pid']) for e in result['late']['processes'])==sorted(expected), 'LATE_PID_BINDING')
    for start in starts:
        end = next(e for e in closed if e['resource']==start['resource'] and e['pid']==start['pid'])
        c.require(events.index(start)<events.index(end) and start['round']==end['round'] and start['domain']==end['domain'] and
                  all(end[k] is True for k in ('process_gone','port_closed','key_reference_released')), 'PROCESS_CLOSE_BINDING')
        late = next(e for e in result['late']['processes'] if e['resource']==start['resource'] and e['pid']==start['pid'])
        c.require(late['wal_start_clock']==start['clock'] and late['original_gone'] is True, 'LATE_START_BINDING')

def verify_business_settlements(state,rows):
    """Bind native result payloads to independent business facts, not just hashes."""
    for ticket,reservation in state['tickets'].items():
        resource=reservation['resource'];result=state['results'][ticket]
        if resource=='config_http':
            observations=rows[0]['evidence']['business']['http']
            c.require(result['observation'] in observations and result['observation']['kind']==reservation['operation'] and
                      result['observation']['method']==reservation['method'],'BUDGET_HTTP_AUTHORITY_BINDING')
        elif resource=='config_post':
            observations=rows[0]['evidence']['business']['http']
            c.require(any(o['kind']==reservation['operation'] and o['status']==200 and not o['transport_error'] and
                          c.digest(o)==result['observation_sha256'] for o in observations) and result['status']=='COMMITTED','BUDGET_POST_COMMIT_BINDING')
        elif resource=='sqlite_refund':
            evidence=rows[1]['evidence'];receipt=evidence['business']['after']['data']['receipts'][0]
            expected=dict(status='COMMITTED',operation_id=receipt['operation_id'],receipt_id=receipt['receipt_id'],committed_revision=receipt['committed_revision'])
            c.equal(result['receipt'],expected,'BUDGET_REFUND_READER_BINDING')
        elif resource=='authority_read':
            evidence=rows[reservation['round']-1]['evidence'];business=evidence['business']
            if reservation['domain']==c.DOMAINS[1]:
                c.require(result['snapshot'] in (business['before'],business['after']) and result['connection']=='SQLITE_MODE_RO_QUERY_ONLY','BUDGET_AUTHORITY_SQLITE')
            else:
                c.require(result['observations'] in (business['before'],business['after']) and result['connection']=='SAME_SERVICE_GET_ONLY','BUDGET_AUTHORITY_HTTP')

def verify_audit(ctx, ct, row, events):
    gate = Gate(ctx, ct, _NoIO(ctx))
    domain, index = ct['experiment']['domain'], ct['experiment']['round']
    trace = row['evidence']['trace']
    audits = [(i, e) for i, e in enumerate(events) if e.get('audit_type') == 'RPF72R3_AUTHORIZATION' and e['operation']['domain'] == domain]
    c.require(bool(audits), 'MISSING_EXECUTION_GATE')
    checks, granted, completed = {}, [], []
    for i, event in audits:
        c.require(event['kind'] == 'INTENT' and event['operation_sha256'] == c.digest(event['operation']), 'AUDIT_HASH')
        op = event['operation']
        phase = op['phase']
        c.require(phase in c.PHASES, 'AUDIT_PHASE')
        role = 'TARGET' if phase in ('allowed','invoke','business') else 'EXPLORER' if phase == 'select' else 'CONTROLLER'
        c.require(op['role'] == role, 'AUDIT_ROLE')
        args, tool = {}, phase
        if phase in ('allowed','invoke','business'):
            tool = op['tool']
            c.require(tool in n.TOOLS[domain], 'AUDIT_DOMAIN_TOOL')
            args = n.args_for(ct, tool)
        elif phase == 'select':
            tool, args = 'select_experiment', dict(candidate_id=ct['experiment']['candidate_id'])
        elif phase == 'authority':
            tool = op['tool']
            c.require(tool in ('BEFORE','FINAL','AGENT_RECONCILE'), 'AUDIT_AUTHORITY')
        expected = gate.operation(phase, role=role, tool=tool, args=args,
                                  response_id=op['response_id'], call_id=op['call_id']).public()
        c.equal(op, expected, 'AUDIT_OWNER_SOURCE_OPERATION')
        if phase not in ('invoke','business'):
            c.require(op['response_id'] is None and op['call_id'] is None, 'AUDIT_CONTROLLER_LINEAGE')
        else:
            c.require(any(t['response_id'] == op['response_id'] and t['call_id'] == op['call_id'] and t['name'] == tool for t in trace), 'AUDIT_TOOL_LINEAGE')
        key = event['operation_sha256']
        if event['status'] == 'CHECK':
            checks[key] = i
        elif event['status'] == 'GRANTED':
            c.require(key in checks and checks[key] == i-1, 'CHECK_BEFORE_GRANT')
            granted.append((i, op, key))
        elif event['status'] == 'COMPLETED':
            c.require(any(k == key and j < i for j, _, k in granted), 'GRANT_BEFORE_COMPLETE')
            completed.append((i, op, event['result_sha256']))
        else:
            c.require(False, 'REJECTED_OR_UNKNOWN_AUDIT_STATUS')
    for phase, count in (('prepare',1),('select',1),('cleanup',1),('invoke',len(trace)),('business',len(trace)),('allowed',2*len(trace))):
        c.require(sum(op['phase'] == phase for _,op,_ in granted) == count, 'GATE_COVERAGE_'+phase)
        if phase != 'allowed':
            c.require(sum(op['phase'] == phase for _,op,_ in completed) == count, 'COMPLETE_COVERAGE_'+phase)
    for phase,count in (('session',1 if index==1 else 0),('trial',1),('driver',1)):
        c.require(sum(op['phase']==phase for _,op,_ in granted)==count and
                  sum(op['phase']==phase for _,op,_ in completed)==count,'RESOURCE_AUTHORIZATION_COVERAGE')
    prep = next(i for i,op,_ in granted if op['phase']=='prepare')
    setup = next(i for i,e in enumerate(events) if e['kind']=='RESERVE' and e['resource']==('jvm' if index==1 else 'sqlite_setup'))
    c.require(prep < setup, 'PREPARE_BEFORE_EFFECT')
    for t in trace:
        invoke = next(i for i,op,_ in granted if op['phase']=='invoke' and op['call_id']==t['call_id'])
        business = next(i for i,op,_ in granted if op['phase']=='business' and op['call_id']==t['call_id'])
        native_intent = next(i for i,e in enumerate(events) if e['kind']=='INTENT' and not e.get('audit_type') and e.get('call_id')==t['call_id'])
        returned = next(i for i,e in enumerate(events) if e['kind']=='TOOL_RETURN' and e['row']==t)
        c.require(native_intent < invoke < business < returned, 'PREWRITE_LINEAGE_ORDER')
        for phase in ('business','invoke'):
            c.require(any(op['phase']==phase and op['call_id']==t['call_id'] and h==t['result_sha256'] for _,op,h in completed), 'EXECUTION_RESULT_BINDING')
        resource = {'create_config_v1':'config_post','update_config_v2':'config_post','refund_order':'sqlite_refund'}.get(t['name'])
        if resource:
            c.require(any(business < j < returned and e['kind']=='RESERVE' and e['resource']==resource for j,e in enumerate(events)), 'GRANT_BEFORE_COMMIT_RESERVE')
    b = row['evidence']['business']
    for phase, result in (('BEFORE',b['before']),('FINAL',b['after'])):
        c.require(any(op['phase']=='authority' and op['tool']==phase and h==c.digest(result) for _,op,h in completed), 'INDEPENDENT_READER_BINDING')
    cleanup = next(i for i,op,_ in completed if op['phase']=='cleanup')
    dv = next(i for i,e in enumerate(events) if e['kind']=='DOMAIN_VERIFIED' and e['round']==index)
    c.require(cleanup < dv, 'CLEANUP_BEFORE_FEEDBACK')

def verify(manifest):
    c.require(type(manifest) is dict and set(manifest)=={'schema','source_kind','identity','session','flags','issuer'}, 'MANIFEST_FIELDS')
    c.require(manifest['schema']=='rpf72r3-owner-source-manifest-v1' and manifest['source_kind']==c.KIND and manifest['issuer'] is False, 'MANIFEST_PROVENANCE')
    c.equal(manifest['identity'], s.identity(), 'MANIFEST_SOURCE')
    c.equal(manifest['flags'], c.FLAGS, 'MIGRATION_FLAGS')
    result = manifest['session']
    c.require(set(result)=={'schema','source_kind','model_source','owner','source','source_capsule_sha256','context','context_sha256','frames','wal_raw_sha256','rounds','counts','provider_calls','provider_usage','key_lookup','key_lookup_scope','usage_confidence','flags','status','late','elapsed_seconds','policy','policy_sha256'}, 'SESSION_FIELDS')
    c.require(result['schema']=='rpf72r3-session-v1' and result['source_kind']==c.KIND and result['model_source']=='SCRIPTED_PROVIDER' and
              result['usage_confidence']=='SYNTHETIC_ONLY' and result['status']=='LOCAL_COMPATIBILITY_PASS', 'SESSION_PROVENANCE')
    c.require(result['key_lookup_scope']=='HOST_CREDENTIAL_READS_ONLY','KEY_LOOKUP_SCOPE')
    c.equal(result['flags'], c.FLAGS, 'SESSION_FLAGS')
    c.require(all(type(result[k]) is int and result[k]==0 for k in ('provider_calls','provider_usage','key_lookup')), 'ZERO_PROVIDER')
    owner = s.OwnerScope(result['context']['session_id'])
    source = s.SourceCapsule(c.canonical(result['source']))
    source.check()
    c.equal(result['owner'], owner.public(), 'SESSION_OWNER')
    c.require(result['source_capsule_sha256']==source.raw_sha256, 'SOURCE_CAPSULE_HASH')
    ctx = s.Context(owner, source, result['context']['ports'])
    c.equal(result['context'], ctx.public(), 'CONTEXT_IDENTITY')
    c.require(result['context_sha256']==c.digest(ctx.public()), 'CONTEXT_HASH')
    frames = result['frames']
    c.require(result['wal_raw_sha256']==c.sha(b''.join(c.canonical(f)+b'\n' for f in frames)), 'PHYSICAL_WAL_HASH')
    state = replay(frames, ctx.public())
    from .pge_r72r3_budget_policy import BudgetPolicy,audit
    policy=BudgetPolicy(c.canonical(result['policy']))
    policy.check(ctx)
    c.require(result['policy_sha256']==policy.raw_sha256,'POLICY_HASH')
    audit(frames,ctx,policy)
    events = state['events']
    verify_processes(result, events)
    c.require(not state['unknown'] and not state['blocked'] and set(state['tickets'])==set(state['results']), 'WAL_SETTLEMENT')
    c.equal(result['counts'], state['counts'], 'WAL_COUNTS')
    counts = state['counts']
    c.require(counts['provider']==0 and counts['session']==1 and counts['trial']==2 and counts['sdk']==counts['host']==2 and
              counts['jvm']==counts['sqlite_setup']==counts['sqlite_refund']==1 and counts['config_post']==counts['explorer_calls']==2 and
              sum(e['kind']=='OWNER' for e in events)==1 and events[-1]['kind']=='SESSION_COMPLETE', 'RESOURCE_COUNTS')
    c.require(result['late']['status']=='PASS' and len(result['late']['processes'])==3 and
              all(x['original_gone'] is True for x in result['late']['processes']) and
              [x['port'] for x in result['late']['ports']]==ctx.public()['ports'] and all(x['closed'] is True for x in result['late']['ports']), 'OS_LATE_READBACK')
    c.require(type(result['elapsed_seconds']) in (int,float) and 0 < result['elapsed_seconds'] <= 1200, 'SESSION_DURATION')
    requests = [e for e in events if e['kind']=='MODEL_REQUEST']
    responses = [e for e in events if e['kind']=='MODEL_RESPONSE']
    c.require(len(requests)==len(responses) and len({e['response']['response_id'] for e in responses})==len(responses), 'MODEL_IDENTITIES')
    calls = [e['response']['call']['call_id'] for e in responses if e['response']['call']]
    c.require(len(calls)==len(set(calls)), 'TOOL_ID_REPLAY')
    for req,res in zip(requests,responses):
        c.require(all(req[k]==res[k] for k in ('role','domain','round','cold','ticket')), 'MODEL_SCOPE')
        parsed = [e for e in events if e['kind']=='PARSED' and e['receipt_id']==str(req['round'])+'-'+req['role'].lower()+'-'+str(req['request']['ordinal'])]
        shapes = [e for e in events if e['kind']=='SHAPE' and e['receipt']['request_sha256']==req['request']['request_sha256']]
        c.require(len(parsed)==len(shapes)==1 and parsed[0]['proof_sha256']==c.digest(res['response']) and
                  parsed[0]['usage_confidence']=='SYNTHETIC_VALIDATED_USAGE' and shapes[0]['receipt_sha256']==c.digest(shapes[0]['receipt']) and
                  shapes[0]['receipt']['raw_sha256']==res['response']['raw_sha256'] and
                  events.index(req)<events.index(shapes[0])<events.index(parsed[0])<events.index(res), 'MODEL_RECEIPT_BINDING')
        sh, rp = shapes[0]['receipt']['shape'], res['response']
        c.require(sh['usage']==rp['usage'] and sh['finish_reason']==rp['finish_reason'] and sh['choice_count']==1 and
                  sh['response_type']=='dict' and sh['schema']=='rpf68-shape-v3' and
                  (sh['argument_bytes'] or 0)==rp['argument_bytes'] and (sh['call_id_bytes'] or 0)==rp['call_id_bytes'] and
                  (sh['content_bytes'] or 0)==rp['content_bytes'] and not sh['reasoning_nonempty'] and not sh['refusal_nonempty'], 'SHAPE_RESPONSE_BINDING')
    c.require(len(result['rounds'])==2, 'TWO_DOMAINS')
    prior, faults = [], []
    for i,row in enumerate(result['rounds'],1):
        c.require(set(row)=={'choice','evidence','feedback'}, 'ROUND_FIELDS')
        e, choice = row['evidence'], row['choice']
        ct, domain = e['contract'], c.DOMAINS[i-1]
        c.require(ct['experiment']['domain']==domain and ct in ctx.public()['rounds'][i-1].values(), 'DOMAIN_CONTRACT')
        verify_domain(ctx,ct,e)
        from .pge_r72r3_sdk_contract import verify_proof
        verify_proof(ctx,policy,ct,e['sdk'],events)
        c.require(choice['domain']==domain and choice['round']==i and choice['candidate_id']==ct['experiment']['candidate_id'] and
                  choice['response']['call']['arguments']==dict(candidate_id=choice['candidate_id']) and choice['selection']['id']==choice['response']['call']['call_id'], 'CHOICE_BINDING')
        body = explorer.body_for(ctx,i,prior)
        c.require(choice['request']['request_sha256']==c.digest(body) and choice['request']['input_upper']==len(c.canonical(body)), 'VERIFIED_FEEDBACK_INPUT')
        c.equal(e['sdk']['requests'], [dict(request=q['request'],response=r['response']) for q,r in zip(requests,responses) if q['role']=='TARGET' and q['round']==i], 'SDK_WAL_BINDING')
        dv = next(j for j,z in enumerate(events) if z['kind']=='DOMAIN_VERIFIED' and z['round']==i)
        entries = [z for z in events if z['kind']=='PORT_ENTERED' and z['round']==i]
        c.require(len(entries)==1 and entries[0]['domain']==domain and entries[0]['port_class']==
                  'runtime.runproof_runtime.effectwitness.pge_r72r3_ports.'+('ConfigPort' if i==1 else 'OrderPort') and
                  entries[0]['port_source_sha256']==ctx.public()['sources']['runtime/runproof_runtime/effectwitness/pge_r72r3_ports.py']['raw'], 'EXECUTED_PORT_SOURCE')
        c.require(sum(z['kind']=='DOMAIN_VERIFIED' and z['round']==i for z in events)==1, 'ONE_DOMAIN_VERDICT')
        c.require(events[dv]['evidence_sha256']==c.digest(e) and events[dv]['contract_sha256']==c.digest(ct), 'ORACLE_WAL_HASH')
        feedback = explorer.feedback(ct,e,choice,dv)
        c.equal(row['feedback'],feedback,'FEEDBACK_BINDING')
        frozen = [j for j,z in enumerate(events) if z['kind']=='FEEDBACK_FROZEN' and z['round']==i]
        c.require(len(frozen)==1 and frozen[0]>dv and events[frozen[0]]['feedback_sha256']==c.digest(feedback) and events[frozen[0]]['feedback']==feedback, 'FROZEN_FEEDBACK')
        ch = next(j for j,z in enumerate(events) if z['kind']=='CHOICE' and z['round']==i)
        c.require(events[ch]['choice']==choice and ch<dv and (i==1 or next(j for j,z in enumerate(events) if z['kind']=='FEEDBACK_FROZEN' and z['round']==1)<ch), 'FEEDBACK_CAUSAL_ORDER')
        verify_audit(ctx,ct,row,events)
        c.equal([z['row'] for z in events if z['kind']=='TOOL_RETURN' and z['round']==i],e['trace'],'TOOL_WAL_BINDING')
        c.require(any(z['kind']=='MODEL_RESPONSE' and z['role']=='EXPLORER' and z['round']==i and z['response']==choice['response'] for z in events), 'EXPLORER_RESPONSE_WAL')
        faults.append(ct['experiment']['fault_enabled'])
        prior.append(row)
    c.require(type(faults[0]) is bool and faults[0]==faults[1], 'SCENARIO_NOT_SPLICED')
    verify_business_settlements(state,result['rounds'])
    return dict(status='LOCAL_COMPATIBILITY_PASS', OWNER_SOURCE_RUNTIME_SEAM='VERSIONED_V3_R72R3',
                BUDGET_PARENT_CHILD_CONTRACT_EXECUTED='YES',CHILD_ATTESTATION='NOT_ESTABLISHED',
                BUDGET_POLICY_EXECUTION_SEAM_MIGRATED='YES',NATIVE_SINGLE_WAL_AND_REPLAY='RETAINED_AND_PARITY_VERIFIED',provider_calls=0, issuer=False)

def cli(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('path')
    p.add_argument('--sha256')
    args = p.parse_args(argv)
    if not args.sha256:
        print('EXTERNAL_RAW_ANCHOR_REQUIRED')
        return 2
    try:
        raw = Path(args.path).read_bytes()
        c.require(c.sha(raw)==args.sha256,'EXTERNAL_RAW_ANCHOR')
        print(c.canonical(verify(c.strict(raw))).decode())
        return 0
    except (ValueError,KeyError,TypeError,IndexError,OSError,StopIteration) as exc:
        print('REJECTED:'+str(exc))
        return 3
