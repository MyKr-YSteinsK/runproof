"""RPF-59 independent deterministic verifier; no provider or business I/O."""
import argparse,hashlib
from pathlib import Path
from . import pge_select_contracts as c,pge_select_explorer as explorer
from .pge_select_session import validate_state,verify_chain,verify_task_records,dispatch_identity,domain_port
from .pge_select_feedback import visible
canonical,digest,require,strict_json=c.canonical,c.digest,c.require,c.strict_json
SCHEMA='rpf59-cross-domain-selection-evidence-v1'
REAL='REAL_EXPLORER_CONTROLLED_TARGETS'
CLAIM='REAL_EXPLORER_SHARED_SESSION_CONTROLLED_SELECTION_VERIFIED'
def identity():return {'version':'rpf59-selection-verifier-v1','sha256':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
def seal(p):return {'schema':SCHEMA,'payload':p,'payload_sha256':digest(p),'verifier_identity':identity()}
def domain_verdict(contract,evidence):return domain_port(contract['experiment']['domain']).verify(contract,evidence)

def validate_observation(selection,obs,body,seen):
    require(set(obs)=={'shape','attempt','request_sha256','http_status','received_monotonic_ns'} and obs['http_status']==200 and obs['request_sha256']==digest(body)
        and type(obs['received_monotonic_ns']) is int,'RESPONSE_OBSERVATION')
    shape=obs['shape'];explorer.validate_response_shape(shape)
    require(shape['response_type']=='object' and shape['choices_type']=='array' and shape['choices_count']==1 and len(shape['choices'])==1,'PROVIDER_CHOICES_SHAPE')
    choice=shape['choices'][0]
    require(choice['finish_reason']=='tool_calls' and choice['message_type']=='object' and choice['message_role']=='assistant'
        and choice['tool_calls_presence']=='PRESENT' and choice['tool_calls_type']=='array' and choice['tool_calls_count']==1 and len(choice['calls'])==1,'UNIQUE_TOOL_CALL_SHAPE')
    call=choice['calls'][0]
    data={'id':shape['response_id'],'model':shape['model'],'usage':shape['usage'],'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','tool_calls':[selection]}}]}
    require(explorer.parse_selection(data,seen)==selection,'SELECTION_PARSE')
    require(call=={'type':'function','function_name':'select_experiment','call_id':explorer.fingerprint(selection,'id'),
        'arguments':explorer.fingerprint(selection['function'],'arguments')} and shape['response_id_fingerprint']==explorer.fingerprint(data,'id'),'CALL_ID_OR_ARGUMENT_PROVENANCE')
    return data

def research(rows):
    domains=[r['contract']['experiment']['domain'] for r in rows];changed=domains[0]!=domains[1]
    return {'candidate_changed':rows[0]['candidate_id']!=rows[1]['candidate_id'],'domain_changed':changed,
        'TWO_DISTINCT_DOMAINS_IN_THIS_SESSION':'YES' if changed else 'NO','DISTINCT_DOMAINS_IN_SESSION':changed,
        'CROSS_DOMAIN_ADAPTIVE_SELECTION_OBSERVED':'YES_OBSERVATIONAL_ONLY' if changed else 'NO',
        'fact_novelty_domain_scoped':[len(r['feedback']['new_fact_ids']) for r in rows],
        'cross_domain_information_gain':'NOT_COMPARABLE','H1':'NOT_PROVEN','H3':'NOT_PROVEN','CAUSAL_ADVANTAGE':'NOT_PROVEN'}

def verify_payload(p):
    require(set(p)=={'source_kind','claim','plan','rows','ledger_chain','cold_fixture','task_intents','boundaries','research'}
        and p['source_kind'] in (REAL,'SYNTHETIC_TEST_ONLY') and p['boundaries']==c.BOUNDARIES,'PAYLOAD_SOURCE_OR_BOUNDARIES')
    real=p['source_kind']==REAL;plan=p['plan'];c.validate_plan(plan)
    require(plan['source_files']==c.sources() and p['claim']==(CLAIM if real else 'SYNTHETIC_TEST_ONLY'),'SOURCE_OR_CLAIM')
    s=verify_chain(p['ledger_chain'],plan);counts=validate_state(s,plan);events=s['events'];reservations=s['reservations']
    require(len(p['rows'])==2 and all(r['status']=='DONE' for r in reservations),'INCOMPLETE_OR_UNKNOWN')
    from .pge_select_config_port import validate_cold_capture
    validate_cold_capture(p['cold_fixture'])
    require(p['cold_fixture']['source_kind']==('REAL_SDK_COLD_FIXTURE' if real else 'SYNTHETIC_TEST_ONLY'),'COLD_REAL_SOURCE')
    task=verify_task_records(p['task_intents']);cold=[r for r in task if r['kind']=='COLD' and r['status']=='PASS'];sessions=[r for r in task if r['kind']=='SESSION']
    metadata=[r for r in task if r['kind']=='METADATA' and r['status']=='PASS' and r['source_sha256']==digest(c.sources())]
    require(len(cold)==len(sessions)==1 and bool(metadata) and cold[0]['source_sha256']==sessions[0]['source_sha256']==digest(c.sources())
        and cold[0]['ordinal']==p['cold_fixture']['attempt'] and cold[0]['detail']=={'capture_sha256':digest(p['cold_fixture'])}
        and sessions[0]['status']=='PASS' and sessions[0]['data']=={'plan_sha256':digest(plan),'cold_capture_sha256':digest(p['cold_fixture'])}
        and sessions[0]['detail']=={'ledger_chain_sha256':digest(p['ledger_chain']),'rows_sha256':digest(p['rows'])},'TASK_COLD_SESSION_SOURCE')
    def one(kind,**fields):
        matches=[e for e in events if e['kind']==kind and all(e['data'].get(k)==v for k,v in fields.items())]
        require(len(matches)==1,'EVENT_BINDING_'+kind);return matches[0]
    expected={};prior=[];seen=set();previous_end=0;usage=[];actual={'sqlite_trial':0,'jvm':0,'sdk':0,'business_http':0,'post':0,'health':0}
    for index,row in enumerate(p['rows'],1):
        require(set(row)=={'round','candidate_id','contract','body','observation','selection','provider_reservation','trial_reservation','evidence','feedback','input'}
            and row['round']==index and row['candidate_id'] in c.CANDIDATES,'ROW_FIELDS')
        candidate=row['candidate_id'];domain=c.domain_for(candidate);contract=row['contract'];evidence=row['evidence']
        require(contract==plan['rounds'][index-1]['candidates'][candidate] and row['body']==explorer.body_for(explorer.messages_for(prior))
            and row['input']==visible([r['feedback'] for r in prior]),'FROZEN_INPUT_OR_SLOT')
        data=validate_observation(row['selection'],row['observation'],row['body'],seen);seen.add(row['selection']['id'])
        require(strict_json(row['selection']['function']['arguments'].encode())=={'candidate_id':candidate},'CHOICE_CONTRACT_SPLICE')
        verdict=domain_verdict(contract,evidence)
        from .pge_select_feedback import project
        require(row['feedback']==project(contract,evidence,[r['feedback'] for r in prior]),'FEEDBACK_AUTHORITY_SPLICE')
        expected_source=('REAL_LOCAL_SQLITE_DETERMINISTIC' if domain==c.DOMAINS[0] else 'REAL_LOCAL_SDK_FIXTURE_JAVA_HTTP') if real else 'SYNTHETIC_TEST_ONLY'
        require(evidence['source_kind']==expected_source,'SOURCE_PROMOTION')
        expected[(index,'explorer','provider')]=({'provider':1,'token_reserve':3000,'cost_micro_cny':54000},
            {'request_sha256':digest(row['body']),'usage':data['usage'],'response_id':data['id'],'returned_model':data['model']})
        expected[(index,domain,'trial')]=({'trial':1,'order_trial' if domain==c.DOMAINS[0] else 'config_trial':1},
            {'evidence_sha256':digest(evidence),'feedback_sha256':digest(row['feedback'])})
        request=one('PROVIDER_REQUEST_FROZEN',round=index,reservation_id=row['provider_reservation'],request_sha256=digest(row['body']))
        choice=one('CHOICE_FROZEN',round=index,selection_sha256=digest(row['selection']),candidate_id=candidate,contract_sha256=digest(contract))
        dispatch=one('SHARED_PORT_DISPATCH',round=index,domain=domain,contract_sha256=digest(contract));runtime=dispatch['data']['runtime_identity']
        if real:require(runtime==dispatch_identity(domain_port(domain).execute),'ACTUAL_CALLABLE')
        entered=one('DOMAIN_CALL_ENTERED',round=index,domain=domain,runtime_identity=runtime)
        returned=one('DOMAIN_CALL_RETURNED',round=index,domain=domain,runtime_identity=runtime,evidence_sha256=digest(evidence))
        verified=one('DOMAIN_VERIFIED',round=index,domain=domain,verdict_sha256=digest(verdict))
        feedback=one('FEEDBACK_FROZEN',round=index,domain=domain,feedback_sha256=digest(row['feedback']),tool_call_id=row['selection']['id'])
        provider=reservations[row['provider_reservation']-1];trial=reservations[row['trial_reservation']-1]
        require((provider['round'],provider['domain'],provider['label'])==(index,'explorer','provider') and (trial['round'],trial['domain'],trial['label'])==(index,domain,'trial'),'LEDGER_ID_SPLICE')
        pstart=one('RESOURCE_RESERVED',id=provider['id']);pend=one('RESOURCE_SETTLED',id=provider['id']);tstart=one('RESOURCE_RESERVED',id=trial['id']);tend=one('RESOURCE_SETTLED',id=trial['id'])
        require(previous_end<pstart['seq']<request['seq']<pend['seq']<choice['seq']<tstart['seq']<dispatch['seq']<entered['seq']<returned['seq']<verified['seq']<feedback['seq']<tend['seq'],'ROUND_FEEDBACK_ORDER')
        require(request['monotonic_ns']<row['observation']['received_monotonic_ns']<pend['monotonic_ns'],'PROVIDER_OBSERVATION_TIME')
        previous_end=tend['seq'];usage.append(data['usage'])
        if domain==c.DOMAINS[0]:
            actual['sqlite_trial']+=1;receipt=evidence['after']['data']['receipts'][0]
            expected[(index,domain,'refund_order')]=({'sqlite_mutation':1},{'receipt_id':receipt['receipt_id'],'status':'COMMITTED'})
            order_events=[e for e in events if e['kind']=='ORDER_PORT_EVENT' and e['data']['round']==index]
            require([{'kind':e['data']['port_kind'],'monotonic_ns':e['monotonic_ns'],'data':{k:v for k,v in e['data'].items() if k not in ('round','port_kind')}} for e in order_events]==evidence['timeline'],'ORDER_EVENT_LINEAGE')
        else:
            scene=evidence['scene'];actual['jvm']+=1;actual['sdk']+=1;actual['business_http']+=len(scene['http']);actual['post']+=sum(o['method']=='POST' for o in scene['http']);actual['health']+=len(scene['environment']['health'])
            expected[(index,domain,'java')]=({'jvm':1},{'pid':scene['environment']['java_pid']})
            expected[(index,domain,'sdk')]=({'sdk':1},{'pid':scene['sdk']['popen_pid'],'report_sha256':digest(scene['sdk']['report'])})
            for i in range(3):
                rr=next(r for r in reservations if r['round']==index and r['label']==f'health:{i}')
                detail=rr['detail']
                require((set(detail)=={'health_sha256'} and type(detail['health_sha256']) is str and len(detail['health_sha256'])==64)
                    if i<len(scene['environment']['health']) else detail=={'status':'UNUSED_RESERVED_NO_IO'},'HEALTH_ACTUAL_UNUSED')
                expected[(index,domain,f'health:{i}')]=({'health':1},detail)
            for obs in scene['http']:expected[(index,domain,'http:'+obs['kind'])]=({'business_http':1,**({'post':1} if obs['method']=='POST' else {})},{'http_seq':obs['seq'],'observation_sha256':digest(obs)})
            require([e['data']['event'] for e in events if e['kind']=='CONFIG_TOOL_EVENT' and e['data']['round']==index]==scene['events'],'CONFIG_EVENT_LINEAGE')
        for r in reservations:
            if r['round']==index and r['domain']==domain and r['label']!='trial':
                require(entered['seq']<one('RESOURCE_RESERVED',id=r['id'])['seq']<one('RESOURCE_SETTLED',id=r['id'])['seq']<returned['seq'],'RESOURCE_OUTSIDE_CALL')
        prior.append(row)
    require({(r['round'],r['domain'],r['label']):(r['units'],r['detail']) for r in reservations}==expected,'BUDGET_SPLIT_EXTRA_OR_MISSING')
    for r in reservations:
        a=one('RESOURCE_RESERVED',id=r['id']);b=one('RESOURCE_SETTLED',id=r['id'])
        require(a['seq']<b['seq'] and a['data']=={k:r[k] for k in ('id','round','domain','label','units')} and b['data']=={'id':r['id'],'status':'DONE','detail_sha256':digest(r['detail'])},'RESOURCE_EVENT_DETAIL')
    cardinal={'RESOURCE_RESERVED':len(reservations),'RESOURCE_SETTLED':len(reservations)}
    cardinal.update({k:2 for k in ('PROVIDER_REQUEST_FROZEN','CHOICE_FROZEN','SHARED_PORT_DISPATCH','DOMAIN_CALL_ENTERED','DOMAIN_CALL_RETURNED','DOMAIN_VERIFIED','FEEDBACK_FROZEN')})
    require(all(sum(e['kind']==k for e in events)==n for k,n in cardinal.items()) and all(e['kind'] in (*cardinal,'ORDER_PORT_EVENT','CONFIG_TOOL_EVENT') for e in events),'EXTRA_EVENTS')
    require(p['research']==research(p['rows']),'RESEARCH_OVERCLAIM')
    actual.update(provider=2,tokens=sum(u['total_tokens'] for u in usage),estimated_cost_cny_upper=sum(u['prompt_tokens']*4.5+u['completion_tokens']*18 for u in usage)/10**6)
    require(actual['tokens']<=6000 and actual['estimated_cost_cny_upper']<=.15,'ACTUAL_PROVIDER_BUDGET')
    return {'status':'PASS','source_kind':p['source_kind'],'claim':p['claim'],'actual':actual,'reserved_budget':counts,'research':p['research'],'boundaries':c.BOUNDARIES}

def verify_bytes(raw,anchor):
    require(anchor is not None,'EXTERNAL_ANCHOR_REQUIRED');require(hashlib.sha256(raw).hexdigest()==anchor,'EXTERNAL_ANCHOR_MISMATCH')
    envelope=strict_json(raw);require(set(envelope)=={'schema','payload','payload_sha256','verifier_identity'} and envelope['schema']==SCHEMA
        and envelope['payload_sha256']==digest(envelope['payload']) and envelope['verifier_identity']==identity(),'ENVELOPE_IDENTITY')
    return verify_payload(envelope['payload'])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('path',type=Path);parser.add_argument('--sha256');args=parser.parse_args()
    if args.sha256 is None:return 2
    try:print(canonical(verify_bytes(args.path.read_bytes(),args.sha256)).decode());return 0
    except Exception as exc:print(getattr(exc,'code','INVALID_EVIDENCE'));return 3
if __name__=='__main__':raise SystemExit(main())
