"""Pure RPF66 offline certificate validator. No key, business I/O or execution."""
import argparse, hashlib, re
from pathlib import Path
from . import pge_r66_context as c
from .config_live_runtime import _http_contract, _api_response, _valid_item, ProviderLedger
from .config_live_verify import _history
from .pge_r66_session import dispatch_identity, feedback
from .pge_portability_config import verify_sdk as verify_cold_sdk

SCHEMA='rpf66-dual-agent-witness-v1'
def identity(): return {'version':'rpf66-dual-agent-verifier-v1','sha256':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
def seal(p): return dict(schema=SCHEMA,payload=p,payload_sha256=c.digest(p),verifier_identity=identity())

def verify_sdk(s,trace,comps,*,guarded=False):
    pin=c.pinned_sdk_fields(); ready,r=s['ready'],s['report']; pid=s['popen_pid']
    c.require(type(pid) is int and pid>0 and ready['pid']==pid and s['stderr_bytes']==0,'SDK_PID')
    c.require(all(ready[k]==pin[k] for k in ('python_executable_sha256','sdk_site_root_binding_sha256','python_runtime_mapping_sha256')) and ready['sdk_source_sha256']==c.SDK_CORE_SHA256 and ready['openai_source_sha256']==pin['openai_core_sha256'],'SDK_IDENTITY')
    if guarded:
        c.require(set(r)=={'status','stage','error_type','guard_code','guard_denials'} and r['status']=='SDK_ERROR' and r['stage']=='sdk_run' and type(r['error_type']) is str and r['guard_code'] is None and r['guard_denials']==[] and s['returncode']==1,'GUARDED_REPORT')
        return
    c.require(r['pid']==pid and s['returncode']==0 and r['status']=='COMPLETED' and r['guard_denials']==[] and r['framework']=='pydantic-ai-slim' and r['version']=='2.57.0' and r['openai_version']=='3.35.1','SDK_REPORT')
    c.require(r['python_executable_sha256']==pin['python_executable_sha256'] and r['sdk_source_sha256']==c.SDK_CORE_SHA256 and r['openai_source_sha256']==pin['openai_core_sha256'],'REPORT_IDENTITY')
    c.require(r['provider_key_present'] is False and r['business_key_present'] is False and r['final_text_persisted'] is False and r['requests']==len(comps) and r['tool_calls']==r['tool_callbacks']==len(trace),'SDK_PRIVACY_COUNTS')
    c.require(r['input_tokens']==sum(x['usage']['prompt_tokens'] for x in comps) and r['output_tokens']==sum(x['usage']['completion_tokens'] for x in comps),'SDK_USAGE')

def verify_scene(ct,s,*,real):
    c.validate_contract(ct); c.require(set(s)=={'contracts','requests','tool_rejections','http','events','tool_trace','completions','visibility','sdk','environment','original_success','host_failure'} and s['contracts']==ct,'SCENE_FIELDS')
    suppressed=ct['experiment']['fault_plan']['enabled']
    trace,comps,http=s['tool_trace'],s['completions'],s['http']; rejections=s['tool_rejections']; guarded=bool(rejections)
    c.require(len(trace) in ((3,4) if suppressed else (3,)) and [t['name'] for t in trace]==list(c.TOOLS)+(['inspect_config'] if len(trace)==4 else []),'TOOL_ORDER')
    if guarded:
        c.require(len(rejections)==1 and len(trace)==3 and rejections[0]['name'] in c.TOOLS[1:] and rejections[0]['reason']=='PHASE_OR_WRITE_AFTER_UNKNOWN' and s['host_failure']=={'domain':'AGENT','code':'PHASE_OR_WRITE_AFTER_UNKNOWN'},'GUARDED_REJECTION')
    else: c.require(s['host_failure'] is None,'HOST_FAILURE')
    kinds=['initial_current','initial_history','inspect_config','create_config_v1','update_config_v2']+(['inspect_config'] if len(trace)==4 else [])+['reconcile_current','reconcile_history','final_list']
    c.require(len(http)==len(kinds),'HTTP_COUNT')
    for i,(o,kind) in enumerate(zip(http,kinds),1):
        method,path,body=_http_contract(ct['effect'],kind); c.require((o['seq'],o['kind'],o['method'],o['path'],o['request'])==(i,kind,method,path,body),'HTTP_LINEAGE')
        absent=i in (1,3); listed=kind.endswith('history') or kind=='final_list'; ok,data=_api_response(o,404 if absent else 200,4041 if absent else 0,'none' if absent else 'list' if listed else 'item')
        c.require(ok and o['transport_error'] is None and o['response_body_sha256']==c.digest(o['response']),'HTTP_TRUTH')
        if kind=='initial_history': c.require(data==[],'INITIAL_ABSENT')
        elif listed: c.require(len(data)==1 and _valid_item(data[0],ct['effect'],2,'rpf53-v2') if kind=='final_list' else _history(data,ct['effect']),'HISTORY_EFFECT')
        elif not absent: c.require(_valid_item(data,ct['effect'],1 if i==4 else 2,'rpf53-v1' if i==4 else 'rpf53-v2'),'ITEM_EFFECT')
    c.require(s['original_success']==({'status':'COMMITTED','version':2,'value':'rpf53-v2'} if suppressed else None),'FAULT_TRUTH')
    for i,t in enumerate(trace):
        args=({},{'value':'rpf53-v1'},{'expected_version':1,'value':'rpf53-v2'},{})[i]
        result=({'state':'ABSENT'},{'status':'COMMITTED','version':1,'value':'rpf53-v1'},c.UNKNOWN if suppressed else {'status':'COMMITTED','version':2,'value':'rpf53-v2'},{'state':'PRESENT','version':2,'value':'rpf53-v2'})[i]
        c.require(t['sequence']==i+1 and t['arguments']==args and t['arguments_sha256']==c.digest(args) and t['result']==result and t['result_sha256']==c.digest(result) and t['http_observation_seq']==i+3 and t['returned_in_request']==i+2,'TOOL_RETURN_BINDING')
    c.require(len(comps)==len(trace)+1 and len(s['visibility'])==len(comps) and all(x['instructions_present'] and x['task_prompt_present'] and x['tool_help_exact'] for x in s['visibility']),'INPUT_VISIBILITY')
    c.require(len({t['call_id'] for t in trace})==len(trace) and len({x['response_id'] for x in comps})==len(comps),'IDENTITY_REPLAY')
    for i,comp in enumerate(comps):
        calls=[{k:trace[i][k] for k in ('call_id','name','arguments_sha256')}] if i<len(trace) else [{k:rejections[0][k] for k in ('call_id','name','arguments_sha256')}] if guarded else []
        returns=[{'call_id':t['call_id'],'result_sha256':t['result_sha256']} for t in trace[:i]]
        c.require(comp['tool_calls']==calls and comp['tool_returns']==returns and (not calls or (trace[i] if i<len(trace) else rejections[0])['provider_response_id']==comp['response_id']),'PROVIDER_TOOL_ORIGIN')
    events=s['events']; c.require([x['seq'] for x in events]==list(range(1,len(events)+1)) and all(x['run_id']==ct['experiment']['run_id'] for x in events),'EVENT_IDENTITY')
    def one(kind,**fields):
        matches=[e for e in events if e['kind']==kind and all(e.get(k)==v for k,v in fields.items())]; c.require(len(matches)==1,'EVENT_'+kind); return matches[0]['seq']
    for o in http: c.require(one('HTTP_RESERVED',http_seq=o['seq'],method=o['method'],operation=o['kind'])<one('HTTP_COMPLETED',http_seq=o['seq'],status=o['status'],response_sha256=o['response_body_sha256']),'HTTP_EVENT_ORDER')
    inputs=[x for x in events if x['kind']=='CAPABILITY_INPUT_FROZEN']
    c.require(len(inputs)==len(comps) and all(x['recovery_policy_visible'] and x['messages_sha256']==vis['messages_sha256'] for x,vis in zip(inputs,s['visibility'])),'POLICY_VISIBILITY')
    exposures=[x for x in events if x['kind']=='MODEL_UNKNOWN_INPUT_ACCEPTED']
    if suppressed:
        withheld=one('SUCCESS_WITHHELD',call_id=trace[2]['call_id'],http_seq=5,committed_result_sha256=c.digest(s['original_success']))
        released=one('UNKNOWN_TOOL_RESULT_RELEASED',call_id=trace[2]['call_id'],result_sha256=c.digest(c.UNKNOWN))
        c.require(one('HTTP_COMPLETED',http_seq=5)<withheld<released,'FAULT_ORDER')
        c.require(len(exposures)==len(comps)-3 and exposures[0]['seq']>released and exposures[0]['request_sha256']==comps[3]['request_sha256'] and exposures[0]['response_id']==comps[3]['response_id'],'UNKNOWN_EXPOSURE')
        if guarded:c.require(one('TOOL_REJECTED',**rejections[0])>exposures[0]['seq'],'GUARD_ORDER')
    else:
        c.require(not exposures and not guarded and not any(x['kind'] in ('SUCCESS_WITHHELD','UNKNOWN_TOOL_RESULT_RELEASED','MODEL_UNKNOWN_INPUT_FROZEN') for x in events),'NORMAL_FALSE_FAULT')
    c.require(len([x for x in events if x['kind']=='READ_ONLY_MODEL_RECOVERY'])==int(len(trace)==4) and all(o['method']=='GET' for o in http[5:]),'POST_UNKNOWN_WRITE')
    verify_sdk(s['sdk'],trace,comps,guarded=guarded)
    env=s['environment']; c.require(env['source_level']=='REAL_JAVA_H2_LOCAL_SIMULATION' and env['authority']=='SAME_SERVICE_READ_ONLY_HTTP' and env['jar_sha256']==c.SOURCE_JAR_SHA256 and env['jar_bytes']==c.SOURCE_JAR_BYTES and env['jar_command_verified'] is True and env['listener_owned'] is True and type(env['java_pid']) is int and env['java_pid']>0,'JAVA_AUTHORITY')
    c.require(set(env['cleanup'])=={'java_exited','java_port_closed','sdk_exited','host_port_closed','host_thread_stopped','local_key_released'} and all(x is True for x in env['cleanup'].values()) and 1<=len(env['health'])<=3 and env['health'][-1]['status']==200 and env['health'][-1]['body']=={'status':'UP'} and env['health'][-1]['transport_error'] is None,'ENV_CLEANUP_HEALTH')
    return dict(effect='CONTRACT_SATISFIED_IN_RUN',agent='AGENT_FAIL_GUARDED' if guarded else 'CONTRACT_SATISFIED_IN_RUN',fault=dict.fromkeys(('planned','triggered','observed','agent_exposed'),suppressed),recovery='OBSERVED' if len(trace)==4 else 'NOT_OBSERVED_SAFE_STOP' if suppressed else 'NOT_APPLICABLE',authority='SAME_SERVICE_READ_ONLY_HTTP')

def verify_round(ctx,account,row,index,prior):
    counts,tickets,results,events=account['counts'],account['tickets'],account['results'],account['events']
    real=ctx.public()['source_kind']==c.REAL
    candidate=row['candidate_id'];ct=ctx.contract(index,candidate);s=row['evidence'];verdict=verify_scene(ct,s,real=real);run=ct['experiment']['run_id']
    c.require(set(row)=={'round','candidate_id','contract','dispatch','evidence','verdict','cleanup','feedback','body','observation','provider_ticket','selection'} and row['round']==index and row['contract']==ct and row['dispatch']==dispatch_identity() and row['verdict']==verdict and row['cleanup']==s['environment']['cleanup'] and row['feedback']==feedback(ct,s,verdict,[r['feedback'] for r in prior]),'ROW_BINDING')
    scoped=[e for e in events if e.get('round')==index]
    ordered=[]
    for kind,field,value in [('PORT_ENTERED','contract_sha256',c.digest(ct)),('DOMAIN_VERIFIED','evidence_sha256',c.digest(s)),('DOMAIN_CLEANUP','cleanup',row['cleanup']),('FEEDBACK_FROZEN','feedback_sha256',c.digest(row['feedback']))]:
        matches=[e for e in scoped if e['kind']==kind];c.require(len(matches)==1 and matches[0]['run_id']==run and matches[0][field]==value,'SESSION_'+kind);ordered.append(matches[0]['monotonic_ns'])
    c.require(ordered==sorted(set(ordered)),'FEEDBACK_ORDER')
    c.require(next(e for e in scoped if e['kind']=='PORT_ENTERED')['dispatch']==row['dispatch'] and next(e for e in scoped if e['kind']=='DOMAIN_VERIFIED')['verdict_sha256']==c.digest(verdict),'DISPATCH_BINDING')
    http_t=[t for t in tickets.values() if t['resource']=='http' and t['round']==index]; c.require(len(http_t)==len(s['http']),'HTTP_WAL_OMISSION')
    for t,o in zip(http_t,s['http']):
        z=results[t['ticket']]; c.require((t['http_seq'],t['operation'],t['method'],t['run_id'])==(o['seq'],o['kind'],o['method'],run) and z['status']==o['status'] and z['response_sha256']==o['response_body_sha256'] and z['transport_error'] is None,'HTTP_WAL_BINDING')
    posts=[t for t in tickets.values() if t['resource']=='post' and t['round']==index]; c.require([t['operation'] for t in posts]==list(c.TOOLS[1:]) and all(t['run_id']==run and results[t['ticket']]['status']==200 and results[t['ticket']]['unknown'] is False for t in posts),'POST_WAL_BINDING')
    c.require([e['event'] for e in events if e['kind']=='DOMAIN_EVENT' and e['run_id']==run]==s['events'],'DOMAIN_WAL')
    records=s['requests']; comps=s['completions']; states=[e for e in events if e['kind']=='PROVIDER_STATE' and e['round']==index]; c.require(len(records)==len(comps)==account['roles'][('TARGET',index)] and states and states[-1]['requests']==records and all(e['role']=='TARGET' and e['run_id']==run for e in states),'PROVIDER_HISTORY')
    previous=[]
    for state in states:
        current=state['requests']; c.require(len(current)>=len(previous),'HISTORY_REMOVED')
        for a,b in zip(previous,current):
            keys=('attempt','run_id','role','ticket','request_sha256','input_upper','token_upper','proof','started_monotonic_ns','tool_returns')+(('status','usage','response_id','returned_model') if a['status']=='RECEIVED' else ())
            c.require(all(a[k]==b[k] for k in keys),'HISTORY_REWRITE')
        previous=current
    tokens=0; cost=0
    for i,(r,comp) in enumerate(zip(records,comps)):
        t=tickets[r['ticket']]; z=results[r['ticket']]; u=r['usage']; ProviderLedger._validate_usage(u,r['token_upper'])
        c.require(r['attempt']==i+1 and r['role']==t['role']=='TARGET' and r['run_id']==t['run_id']==run and r['status']=='RECEIVED' and r['failure_code'] is None and z['status']=='RECEIVED' and r['request_sha256']==t['request_sha256']==comp['request_sha256'] and r['response_id']==comp['response_id']==z['response_id'] and r['usage']==comp['usage']==z['usage'] and r['returned_model']==comp['model'] and r['returned_model'] in c.MODELS,'PROVIDER_USAGE_BINDING')
        c.require(r['token_upper']==t['token_upper'] and r['input_upper']==t['input_upper'] and r['proof']==t['proof'] and u['prompt_tokens']<=t['input_upper'] and u['completion_tokens']<=256,'USAGE_CAP')
        c.require(r['tool_returns']==comp['tool_returns'] and r['returned_tool_ids']==[x['call_id'] for x in comp['tool_returns']] and r['tool_call_ids']==[x['call_id'] for x in comp['tool_calls']] and r['agent_contract_visibility']==s['visibility'][i],'PROVIDER_CALL_BINDING')
        c.require(re.fullmatch('[0-9a-f]{64}',r['tool_schema_sha256']) is not None and len({x['tool_schema_sha256'] for x in records})==1,'TOOL_SCHEMA')
        proof=t['proof']
        if i==0: c.require(proof=={'kind':'FULL_SERIALIZED_BYTES','body_bytes':t['input_upper']},'FIRST_INPUT_PROOF')
        else:
            prev=records[i-1]; c.require(proof['kind']=='UNCHANGED_PREFIX_USAGE_PLUS_SUFFIX_BYTES_PLUS_512' and proof['previous_request_sha256']==prev['request_sha256'] and proof['prefix_sha256']==s['visibility'][i-1]['messages_sha256'] and proof['previous_prompt_tokens']==prev['usage']['prompt_tokens'] and proof['framing_guard']==512 and t['input_upper']==proof['previous_prompt_tokens']+proof['suffix_bytes']+512,'PREFIX_INPUT_PROOF')
        if real: c.require(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',r['response_id']) is not None,'REAL_RESPONSE_ID')
        tokens+=u['total_tokens']; cost+=u['prompt_tokens']*4.5+u['completion_tokens']*18
    from . import pge_r66_explorer as explorer
    body=explorer.body_for(prior);ob=row['observation'];shape=ob['shape'];explorer.validate_response_shape(shape)
    c.require(row['body']==body and ob['request_sha256']==c.digest(body) and ob['http_status']==200 and ob['attempt']==row['provider_ticket'],'EXPLORER_BODY')
    selection=row['selection'];args=c.strict_json(selection['function']['arguments'].encode())
    c.require(set(selection)=={'id','type','function'} and selection['type']=='function' and re.fullmatch('[A-Za-z0-9_-]{1,128}',selection['id']) is not None and set(selection['function'])=={'name','arguments'} and selection['function']['name']=='select_experiment' and args=={'candidate_id':candidate} and selection['id'] not in {r['selection']['id'] for r in prior},'EXPLORER_SELECTION')
    c.require(shape['model'] in c.MODELS and shape['choices_count']==1 and shape['choices_type']=='array' and shape['response_type']=='object','EXPLORER_RESPONSE')
    ch=shape['choices'][0];call=ch['calls'][0]
    c.require(ch['finish_reason']=='tool_calls' and ch['message_role']=='assistant' and ch['tool_calls_count']==1 and len(ch['calls'])==1 and call['type']=='function' and call['function_name']=='select_experiment' and call['call_id']==explorer.fingerprint(selection,'id') and call['arguments']==explorer.fingerprint(selection['function'],'arguments') and shape['response_id_fingerprint']==explorer.fingerprint({'id':shape['response_id']},'id'),'EXPLORER_ORIGIN')
    t=tickets[row['provider_ticket']];z=results[row['provider_ticket']];u=shape['usage'];ProviderLedger._validate_usage(u,c.EXPLORER_CAP)
    c.require(t['role']=='EXPLORER' and t['round']==index and t['run_id']==run and t['request_sha256']==c.digest(body) and t['input_upper']==len(c.canonical(body)) and t['proof']=={'kind':'FULL_SERIALIZED_BYTES','body_bytes':len(c.canonical(body))} and z['usage']==u and z['response_id']==shape['response_id'] and z['model']==shape['model'] and z['status']=='RECEIVED' and u['prompt_tokens']<=t['input_upper'] and u['completion_tokens']<=128,'EXPLORER_WAL')
    c.require(not any(r['observation']['shape']['response_id']==shape['response_id'] for r in prior),'EXPLORER_RESPONSE_REPLAY')
    if real:c.require(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',shape['response_id']) is not None,'REAL_EXPLORER_ID')
    choice=[e for e in scoped if e['kind']=='CHOICE_FROZEN'];c.require(len(choice)==1 and choice[0]['selection_sha256']==c.digest(selection) and choice[0]['candidate_id']==candidate and choice[0]['contract_sha256']==c.digest(ct) and choice[0]['provider_ticket']==row['provider_ticket'] and t['monotonic_ns']<z['monotonic_ns']<=ob['received_monotonic_ns']+10**9 and z['monotonic_ns']<choice[0]['monotonic_ns']<ordered[0],'CHOICE_ORDER')
    if prior:
        previous=next(e for e in events if e['kind']=='FEEDBACK_FROZEN' and e.get('round')==index-1)
        c.require(previous['monotonic_ns']<t['monotonic_ns'],'FEEDBACK_BEFORE_SECOND_PROVIDER')
    fb_event=next(e for e in scoped if e['kind']=='FEEDBACK_FROZEN');c.require(fb_event['tool_call_id']==selection['id'],'FEEDBACK_SELECTION')
    trial=next(t for t in tickets.values() if t['resource']=='trial' and t['round']==index);c.require(results[trial['ticket']]['status']=='COMPLETED' and results[trial['ticket']]['evidence_sha256']==c.digest(s),'TRIAL_SETTLED')
    health=[t for t in tickets.values() if t['resource']=='health' and t['round']==index];c.require(len(health)==len(s['environment']['health']),'HEALTH_ACCOUNT')
    for t,o in zip(health,s['environment']['health']):c.require(results[t['ticket']]['status']==o['status'] and results[t['ticket']]['response_sha256']==o['raw_body_sha256'],'HEALTH_BINDING')
    tokens+=u['total_tokens'];cost+=u['prompt_tokens']*4.5+u['completion_tokens']*18
    return tokens,cost

def verify_payload(p):
    c.require(set(p)=={'source_kind','context','rows','cold','ledger','boundaries'} and p['source_kind']==p['context']['source_kind'] and p['boundaries']==c.BOUNDARIES,'WITNESS_SOURCE')
    ctx=c.TaskContext(c.ROOT/p['context']['workspace'],c.canonical(p['context']));account=c.replay(p['ledger'],p['context']);counts=account['counts'];tickets=account['tickets'];results=account['results'];events=account['events']
    c.require(not account['unknown'] and set(tickets)==set(results) and counts['session']==counts['cold']==counts['metadata']==1 and all(counts[k]==2 for k in ('trial','jvm','sdk')) and counts['post']==4 and len(p['rows'])==2 and all(account['roles'].get(('EXPLORER',i))==1 for i in (1,2)),'RESOURCE_COUNTS')
    tokens=0;cost=0
    for index,row in enumerate(p['rows'],1):
        t,z=verify_round(ctx,account,row,index,p['rows'][:index-1]);tokens+=t;cost+=z
    cold=p['cold'];c.require(cold['status']=='PASS' and cold['source_kind']=='FIXTURE_SCRIPTED' and cold['contract']==ctx.public()['cold_contract'] and cold['sources']==c.sources() and cold['checks']=={'protocol':True,'provider_zero':True,'cleanup':True},'COLD_IDENTITY')
    verify_cold_sdk(cold['sdk'],cold['tool_trace'],cold['completions']);c.require([t['name'] for t in cold['tool_trace']]==list(c.TOOLS)+['inspect_config'] and [t['returned_in_request'] for t in cold['tool_trace']]==[2,3,4,5] and cold['tool_trace'][2]['result']==c.UNKNOWN,'COLD_PROTOCOL')
    cr=cold['contract']['experiment']['run_id'];c.require([e['event'] for e in events if e['kind']=='DOMAIN_EVENT' and e['run_id']==cr]==cold['events'],'COLD_EVENTS')
    processes=[('cold',0,cold['sdk']['popen_pid'])]+[(kind,i,row['evidence']['sdk']['popen_pid'] if kind=='sdk' else row['evidence']['environment']['java_pid']) for i,row in enumerate(p['rows'],1) for kind in ('sdk','jvm')]
    c.require(len({x[2] for x in processes})==5,'PID_REPLAY')
    for resource,index,pid in processes:
        ts=[t for t in tickets.values() if t['resource']==resource and t['round']==index];cleanup=[e for e in events if e['kind']=='PROCESS_CLEANUP' and e['resource']==resource and e['round']==index]
        c.require(len(ts)==len(cleanup)==1 and results[ts[0]['ticket']]['popen_pid']==pid and cleanup[0]['pid']==pid and cleanup[0]['process_exited'] is True,'PROCESS_ACCOUNT')
    session=next(t for t in tickets.values() if t['resource']=='session');c.require(results[session['ticket']]['status']=='COMPLETED' and results[session['ticket']]['rows_sha256']==c.digest(p['rows']),'SESSION_SETTLED')
    c.require(tokens<=35000 and cost<=750000,'ACTUAL_BUDGET')
    rows=p['rows'];l2=rows[0]['candidate_id']!=rows[1]['candidate_id'] and bool(rows[1]['feedback']['new_facts'])
    return dict(status='PASS',source_kind=p['source_kind'],rounds=[dict(candidate_id=r['candidate_id'],verdict=r['verdict'],new_facts=r['feedback']['new_facts']) for r in rows],L2_observed=l2,physical=counts,reserved_tokens=account['reserved_tokens'],reserved_cost_cny_upper=account['reserved_cost_micro_cny']/1e6,tokens=tokens,cost_cny_guard_estimate=cost/1e6,boundaries=c.BOUNDARIES)

def verify_bytes(raw,anchor):
    c.require(anchor is not None and hashlib.sha256(raw).hexdigest()==anchor,'EXTERNAL_ANCHOR'); e=c.strict_json(raw)
    c.require(set(e)=={'schema','payload','payload_sha256','verifier_identity'} and e['schema']==SCHEMA and e['payload_sha256']==c.digest(e['payload']) and e['verifier_identity']==identity(),'ENVELOPE')
    return verify_payload(e['payload'])
def main():
    p=argparse.ArgumentParser(); p.add_argument('path',type=Path); p.add_argument('--sha256'); a=p.parse_args()
    if a.sha256 is None: return 2
    try: print(c.canonical(verify_bytes(a.path.read_bytes(),a.sha256)).decode()); return 0
    except Exception as exc: print(getattr(exc,'code','INVALID_EVIDENCE')); return 3
if __name__=='__main__': raise SystemExit(main())
