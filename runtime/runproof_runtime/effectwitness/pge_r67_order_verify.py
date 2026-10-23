"""Deterministic offline Order Witness verifier. No SDK, key or network access."""
import argparse, re
from pathlib import Path
from . import pge_r67_context as c
from .effect_oracle import evaluate_order_effect
from .contracts import ENV_REVISION, READER_ID
from .pge_r67_order_driver import shape_conditions,validate_shape,POLICY

VERSION='rpf67-order-witness-verifier-v3'
def identity():
    raw=Path(__file__).read_bytes();return dict(version=VERSION,raw=c.sha(raw),lf=c.sha(raw.replace(b'\r\n',b'\n')))
def seal(payload):return dict(schema='rpf67-order-witness-v3',verifier=identity(),payload=payload,payload_sha256=c.digest(payload))
def verify(value):
    c.require(re.search(r'sk-[A-Za-z0-9_-]{16,}|C:[/\\]+Users[/\\]+|Bearer [A-Za-z0-9_-]{16,}',c.canonical(value).decode()) is None,'CREDENTIAL_OR_PRIVATE_PATH')
    c.require(type(value) is dict and set(value)=={'schema','verifier','payload','payload_sha256'} and value['schema']=='rpf67-order-witness-v3' and value['verifier']==identity() and value['payload_sha256']==c.digest(value['payload']),'ENVELOPE_VERIFIER')
    p=value['payload'];c.require(set(p)=={'context','frames','order','outcome','admission','boundaries'},'PAYLOAD_FIELDS')
    ctx=p['context'];ct=ctx['contract'];suffix=ct['experiment']['run_id'].removeprefix('rpf67r3-order-');synthetic=ctx['source_kind']==c.SYNTHETIC
    c.require(ctx==c.public(suffix,ct['execution']['port'],synthetic),'CONTEXT_SOURCE_IDENTITY');c.validate_contract(ct)
    c.require(p['boundaries']==c.BOUNDARIES,'BOUNDARIES')
    a=c.replay(p['frames'],ctx);c.require(not a['unknown'] and set(a['tickets'])==set(a['results']),'UNSETTLED_OR_UNKNOWN')
    events=a['events'];allowed={'OWNER','RESERVE','RESULT','INTENT','TOOL_RETURN','FAULT_EXPOSED','MODEL_REQUEST','MODEL_RESPONSE','PROCESS_START','SDK_READY','PROCESS_CLEANUP','ADMISSION','SOURCE_FREEZE','VERDICT','PROVIDER_SHAPE_OBSERVED','PROVIDER_PARSE_ACCEPTED','PROVIDER_PARSE_REJECTED'}
    c.require(all(e['kind'] in allowed for e in events),'WAL_EVENT_KIND')
    e=p['order'];c.require(set(e)=={'source_kind','backend','before','committed','after','trace','fault','sdk','database_sha256','cleanup'},'ORDER_FIELDS')
    c.require(e['source_kind']==ctx['source_kind'] and e['backend']=='REAL_LOCAL_SQLITE','ORDER_SOURCE')
    f,x=ct['effect'],ct['experiment'];authority=[]
    for event in events:
        if event['kind']=='RESULT' and a['tickets'][event['ticket']]['resource']=='authority':
            c.require(event['status']=='READ_ONLY' and event['connection']=='SQLITE_MODE_RO_QUERY_ONLY','READER_CONNECTION');authority.append(event)
            snapshot=event['snapshot'];data=snapshot['data']
            c.require(set(snapshot)=={'data','sha256'} and snapshot['sha256']==c.digest(data) and set(data)=={'reader_id','reader_version','source_id','environment','order','receipts'},'AUTHORITY_SNAPSHOT')
            c.require(data['reader_id']==READER_ID and data['reader_version']=='1' and data['source_id']==f['authority_id'] and data['environment']==dict(owner='rpf-67-rev-3',run_id=x['run_id'],environment_id=x['environment_id'],environment_revision=ENV_REVISION,reset_generation=0),'READER_IDENTITY_GENERATION')
    c.require([z['phase'] for z in authority] in (['BEFORE','AFTER_COMMIT_BEFORE_UNKNOWN','CONTROLLER_FINAL_RECONCILE'],['BEFORE','AFTER_COMMIT_BEFORE_UNKNOWN','OPTIONAL_AGENT_RECONCILE','CONTROLLER_FINAL_RECONCILE']),'AUTHORITY_PHASES')
    c.require(e['before']==authority[0]['snapshot'] and e['committed']==authority[1]['snapshot'] and e['after']==authority[-1]['snapshot'],'AUTHORITY_BINDING')
    outcome=evaluate_order_effect(f,x['environment_id'],e['before']['data'],e['after']['data']);c.require(outcome['contract_outcome']=='CONTRACT_SATISFIED_IN_RUN' and p['outcome']==outcome and e['committed']['data']==e['after']['data'],'ORDER_ORACLE')
    c.require(e['fault']==dict.fromkeys(('planned','triggered','observed','agent_exposed'),True),'FAULT_FOUR_STATES')
    trace=e['trace'];c.require([t['name'] for t in trace] in (list(c.TOOLS[:2]),list(c.TOOLS)) and len({t['call_id'] for t in trace})==len(trace),'TOOL_ORDER_OR_DUPLICATE')
    intents=[v for v in events if v['kind']=='INTENT' and not v.get('cold')];returns=[v for v in events if v['kind']=='TOOL_RETURN' and not v.get('cold')]
    # Cold uses distinct event kinds through the memory port; never counts as business truth.
    c.require(len(intents)==len(returns)==len(trace),'TOOL_EVENT_COUNT')
    for i,t in enumerate(trace):
        c.require(set(t)=={'response_id','call_id','name','arguments','result','result_sha256'} and re.fullmatch('[A-Za-z0-9_-]{1,160}',t['call_id']) and t['arguments']==c.args_for(t['name'],f) and t['result_sha256']==c.digest(t['result']),'TOOL_TRACE')
        c.require({k:intents[i][k] for k in ('response_id','call_id','name','arguments')}=={k:t[k] for k in ('response_id','call_id','name','arguments')} and all(returns[i][k]==v for k,v in t.items()) and events.index(intents[i])<events.index(returns[i]),'INTENT_RETURN_LINEAGE')
        response=next(z for z in events if z['kind']=='MODEL_RESPONSE' and not z['cold'] and z['response']['response_id']==t['response_id']);c.require(events.index(response)<events.index(intents[i]),'NO_TOOL_BEFORE_ACCEPTED_RESPONSE')
    c.require(trace[0]['result']==dict(order_id=f['order_id'],status='PAID',revision=0),'INSPECT_PRECONDITION')
    c.require(trace[1]['result']==dict(status='UNKNOWN_OUTCOME',operation_id=f['operation_id'],reason='CONTROLLED_POST_COMMIT_RESPONSE_LOSS',write_policy='STOP_WRITES_READ_ONLY_RECONCILE'),'UNKNOWN_DELIVERY')
    receipt=e['after']['data']['receipts'][0]
    if len(trace)==3:c.require(trace[2]['result']==dict(status='COMMITTED',receipt=receipt,readonly=True),'RECONCILE_READ_ONLY')
    write=a['results']['sqlite_refund-1'];c.require(write['status']=='COMMITTED' and write['receipt']==dict(status='COMMITTED',operation_id=f['operation_id'],receipt_id=receipt['receipt_id'],committed_revision=1) and a['tickets']['sqlite_refund-1']['arguments_sha256']==c.digest(trace[1]['arguments']) and a['tickets']['sqlite_refund-1']['call_id']==trace[1]['call_id'],'MUTATION_RECEIPT_TICKET')
    exposed=[v for v in events if v['kind']=='FAULT_EXPOSED'];c.require(len(exposed)==1 and exposed[0]['fault']==e['fault'] and events.index(write)<events.index(authority[1])<events.index(returns[1])<events.index(exposed[0])<events.index(authority[-1]),'COMMIT_UNKNOWN_CAUSAL_WAL_ORDER')
    sdk=e['sdk'];c.require(not sdk['report'].get('provider_key_present') and not sdk['report'].get('business_key_present'),'CREDENTIAL_REDACTION');requests=sdk['requests'];c.require(len(requests)==len(trace)+1 and len(requests)<=6,'REQUEST_TRACE_COUNT')
    modelrequests=[v for v in events if v['kind']=='MODEL_REQUEST' and not v.get('cold')];modelresponses=[v for v in events if v['kind']=='MODEL_RESPONSE' and not v.get('cold')]
    c.require(len(modelrequests)==len(modelresponses)==len(requests),'MODEL_EVENT_COUNT')
    seen=set();configuration=None;schema=None
    for i,row in enumerate(requests):
        q,r=row['request'],row['response'];c.require(set(row)=={'request','response','ticket','fixture'} and row['fixture'] is synthetic,'PROVIDER_SOURCE')
        transaction=a['transactions'][('fixture-' if synthetic else 'provider-')+str(i+1)];receipt=transaction['shape'];parsed=transaction['parsed'];c.require(receipt is not None and parsed is not None and parsed['kind']=='PROVIDER_PARSE_ACCEPTED' and parsed['proof_sha256']==c.digest(r),'SHAPE_PARSE_PROOF')
        shape=receipt['shape'];flags=validate_shape(shape,q['output_cap']);c.require(all(flags.values()) and parsed['conditions']==flags and parsed['usage']==r['usage'] and receipt['raw_sha256']==r['raw_sha256'],'SHAPE_PARSE_CONDITIONS')
        choice=shape['choices'][0];c.require(shape['response_id']['sha256']==c.sha(r['response_id'].encode()) and choice['finish_reason']==r['finish_reason'] and choice['content']['nonempty'] is r['content_is_nonempty'] and choice['content']['bytes']==r['content_bytes'] and r['policy']==POLICY and q['sdk_feedback_preserved'] is True,'SHAPE_RESPONSE_BINDING')
        if r['call']:c.require(choice['tools'][0]['id']['sha256']==c.sha(r['call']['call_id'].encode()) and choice['tools'][0]['name']==r['call']['name'],'SHAPE_TOOL_BINDING')
        c.require({k:z['value'] for k,z in shape['usage'].items()}==r['usage'],'SHAPE_USAGE_BINDING')
        c.require(set(q)=={'sdk_request_sha256','request_sha256','configuration_sha256','messages_sha256','input_upper','output_cap','stage','tool_returns','schema_sha256','canonical_bytes','sdk_feedback_preserved'} and all(re.fullmatch('[0-9a-f]{64}',q[k]) for k in ('sdk_request_sha256','request_sha256','configuration_sha256','messages_sha256','schema_sha256')),'REQUEST_BINDING')
        c.require(configuration is None or configuration==q['configuration_sha256'],'NONMESSAGE_DRIFT');configuration=q['configuration_sha256'];c.require(schema is None or schema==q['schema_sha256'],'SCHEMA_DRIFT');schema=q['schema_sha256']
        c.require(q['stage']==('PRE_COMMIT' if i<2 else 'POST_COMMIT_READ_ONLY') and q['output_cap']==(256 if i<2 else 512) and type(q['input_upper']) is int and q['input_upper']>0 and q['input_upper']+q['output_cap']<=c.CAPS[i],'STAGE_CAP_INPUT')
        if i==0:c.require(q['input_upper']==q['canonical_bytes'],'FIRST_CANONICAL_BYTES')
        c.require(q['tool_returns']==[dict(call_id=t['call_id'],result_sha256=t['result_sha256']) for t in trace[:i]],'TOOL_RETURN_REINJECTION')
        c.require(set(r)=={'response_id','model','finish_reason','call','usage','content_bytes','content_is_nonempty','policy','raw_sha256','reasoning_persisted','content_persisted','filter'} and r['response_id'] not in seen and re.fullmatch('[A-Za-z0-9_-]{1,160}',r['response_id']) and r['model'] in ct['execution']['models'] and r['reasoning_persisted'] is False and r['content_persisted'] is False and r['filter'] is False,'RESPONSE_PROOF');seen.add(r['response_id'])
        u=r['usage'];c.require(set(u)=={'prompt_tokens','completion_tokens','total_tokens'} and all(type(v) is int and v>=0 for v in u.values()) and u['total_tokens']==u['prompt_tokens']+u['completion_tokens'] and u['prompt_tokens']<=q['input_upper'] and u['completion_tokens']<=q['output_cap'],'KNOWN_USAGE_BOUND')
        if i<len(trace):c.require(r['finish_reason']=='tool_calls' and r['call']=={k:trace[i][k] for k in ('call_id','name','arguments')} and r['response_id']==trace[i]['response_id'],'RESPONSE_CALL_LINEAGE')
        else:c.require(r['finish_reason']=='stop' and r['call'] is None,'LEGAL_STOP')
        c.require(modelrequests[i]['request']==q and modelresponses[i]['response']==r and modelrequests[i]['fixture'] is synthetic and modelresponses[i]['fixture'] is synthetic and modelrequests[i]['ticket']==modelresponses[i]['ticket']==row['ticket'] and events.index(modelrequests[i])<events.index(modelresponses[i]),'MODEL_WAL_BINDING')
        if i:c.require(events.index(returns[i-1])<events.index(modelrequests[i]),'RETURN_BEFORE_NEXT_REQUEST')
        if not synthetic:
            t=a['tickets'][row['ticket']];s=a['results'][row['ticket']];c.require(t['role']=='TARGET' and t['request_sha256']==q['request_sha256'] and all(t[k]==q[k] for k in ('input_upper','output_cap','stage')) and s['status']=='RECEIVED' and s['usage']==u and s['response_id']==r['response_id'] and s['request_sha256']==q['request_sha256'],'PROVIDER_SETTLEMENT')
    c.require(e['cleanup']==dict(connections_closed=True,exclusive_lock_probe=True,database_retained_for_evidence=True) and re.fullmatch('[0-9a-f]{64}',e['database_sha256']) and sdk['process_gone'] is True and sdk['port_closed'] is True and sdk['fixture'] is synthetic and sdk['cold'] is False,'CLEANUP_OR_SOURCE')
    c.require(sdk['child_sha256']==ctx['sources']['runtime/runproof_runtime/effectwitness/pge_r67_order_child.py']['raw'],'CHILD_SOURCE')
    if synthetic:
        c.require(a['counts']['provider']==0 and p['admission'] is None and sdk['process_pid'] is None,'SYNTHETIC_NO_PAID_OR_PID')
    else:
        c.require(all(a['counts'][r]==1 for r in ('metadata','cold','session','trial','sdk','host','sqlite_setup','sqlite_refund')) and a['counts']['provider']==len(requests),'REAL_RESOURCE_COUNTS')
        gate=p['admission'];c.require(type(gate) is dict and gate['context_sha256']==c.digest(ctx) and gate['sources']==ctx['sources'] and gate['price']==c.PRICE and gate['free_gates']=='PASS' and gate['metadata']=='PASS' and gate['cold']=='PASS','PAID_ADMISSION')
        starts=[z for z in events if z['kind']=='PROCESS_START'];ready=[z for z in events if z['kind']=='SDK_READY'];cleanup=[z for z in events if z['kind']=='PROCESS_CLEANUP']
        c.require(len(starts)==len(ready)==len(cleanup)==2 and [z['cold'] for z in starts]==[True,False] and len({z['pid'] for z in starts})==2,'SDK_LIFECYCLE')
        for st,rd,cl in zip(starts,ready,cleanup):
            v=rd['ready'];pin=c.pin();c.require(type(st['pid']) is int and st['pid']>0 and st['parent_pid']>0 and st['pid']==v['pid']==cl['pid'] and st['python_sha256']==v['python_executable_sha256']==pin['python_executable_sha256'] and st['child_sha256']==sdk['child_sha256'] and v['version']=='2.57.0' and v['openai_version']=='3.35.1' and v['sdk_source_sha256']=='70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa' and v['openai_source_sha256']==pin['openai_core_sha256'] and v['sdk_site_root_binding_sha256']==pin['sdk_site_root_binding_sha256'] and v['python_runtime_mapping_sha256']==pin['python_runtime_mapping_sha256'],'SDK_PID_OR_PIN')
            c.require(cl['process_gone'] and cl['thread_gone'] and cl['port_closed'] and cl['key_reference_released'] and events.index(st)<events.index(rd)<events.index(cl),'PROCESS_CLEANUP')
        c.require(events.index(ready[-1])<events.index(modelrequests[0])<events.index(modelresponses[-1])<events.index(cleanup[-1]),'SDK_PROVIDER_ORDER')
        cold_transactions=[t for t in a['transactions'].values() if t['request']['cold']];c.require(len(cold_transactions)==4 and all(t['response'] is not None and t['parsed']['kind']=='PROVIDER_PARSE_ACCEPTED' and all(shape_conditions(t['shape']['shape'],t['request']['request']['output_cap']).values()) for t in cold_transactions),'COLD_SHAPE_PROTOCOL')
        report=sdk['report'];c.require(sdk['ready']==ready[-1]['ready'] and sdk['process_pid']==starts[-1]['pid']==report['pid'] and report['status']=='COMPLETED' and report['requests']==len(requests) and report['tool_calls']==report['tool_callbacks']==len(trace) and report['input_tokens']==sum(r['response']['usage']['prompt_tokens'] for r in requests) and report['output_tokens']==sum(r['response']['usage']['completion_tokens'] for r in requests),'SDK_REPORT')
        c.require(report['final_text_persisted'] is False and report['provider_key_present'] is False and report['business_key_present'] is False and not report['guard_denials'] and not report['denied_files'],'CREDENTIAL_REDACTION')
        admissions=[z for z in events if z['kind']=='ADMISSION'];c.require(len(admissions)==1 and admissions[0]['gate_sha256']==c.digest(gate) and events.index(admissions[0])<events.index(modelrequests[0]),'ADMISSION_BEFORE_NETWORK')
    return dict(status='PASS',source_kind=ctx['source_kind'],outcome=outcome['contract_outcome'],provider_requests=a['counts']['provider'],reserved_tokens=a['reserved_tokens'],reserved_cost_micro_cny=a['reserved_cost_micro_cny'],known_tokens=sum(r['response']['usage']['total_tokens'] for r in requests),optional_reconcile=len(trace)==3,boundaries=c.BOUNDARIES)
def verify_bytes(raw,expected):
    c.require(expected is not None and re.fullmatch('[0-9a-f]{64}',expected),'EXTERNAL_RAW_ANCHOR_REQUIRED');c.require(c.sha(raw)==expected,'EXTERNAL_RAW_SHA');return verify(c.strict(raw))
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('witness');p.add_argument('--sha256');a=p.parse_args(argv)
    if not a.sha256:print('EXTERNAL_RAW_ANCHOR_REQUIRED');return 2
    try:result=verify_bytes(Path(a.witness).read_bytes(),a.sha256);print(c.canonical(result).decode());return 0
    except Exception as error:print('REJECTED:'+type(error).__name__+(':'+str(error) if type(error) is ValueError else ''));return 3
if __name__=='__main__':raise SystemExit(main())
