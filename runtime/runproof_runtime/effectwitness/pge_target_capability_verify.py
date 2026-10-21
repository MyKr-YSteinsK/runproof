"""RPF-62 pure offline content/source/physical-account and domain verifier."""
import argparse
import hashlib
import re
from pathlib import Path
from . import pge_target_capability as c
from .config_live_runtime import _http_contract,_api_response,_valid_item
from .config_live_verify import _history
def identity():return {'version':'rpf62-target-capability-verifier-v1','sha256':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
def seal(payload):return {'schema':c.SCHEMA,'payload':payload,'payload_sha256':c.digest(payload),'verifier_identity':identity()}
def verify_payload(p):
    c.require(set(p)=={'source_kind','sources','contracts','capture','ledger','cold','boundaries'},'WITNESS_FIELDS')
    c.require(p['source_kind'] in ('REAL_PROVIDER_TARGET','SYNTHETIC_TEST_ONLY') and p['sources']==c.sources() and p['boundaries']==c.BOUNDARIES,'SOURCE_OR_CLAIM')
    contract=p['contracts'];c.validate_contract(contract);c.require(contract['experiment']['runtime_source_sha256']==c.digest(p['sources']),'SOURCE_MAP')
    real=p['source_kind']=='REAL_PROVIDER_TARGET'
    c.require(contract['execution']['model_source']==('REAL_PROVIDER' if real else 'FIXTURE_SCRIPTED'),'ROLE_DOWNGRADE_OR_UPGRADE')
    s=p['capture'];c.require(set(s)=={'contracts','http','events','tool_trace','completions','visibility','sdk','environment','requests','original_success','host_failure'} and s['contracts']==contract and s['host_failure'] is None,'CAPTURE_CONTRACT')
    account=c.replay(p['ledger']);events=account['events'];reserved=account['reserved'];c.require(account['token_pool_reserved'],'POOL')
    c.require(reserved['trial']==reserved['jvm']==reserved['sdk']==reserved['cold']==1 and 1<=reserved['metadata']<=2,'PHYSICAL_COUNTS')
    c.require(len([e for e in events if e['kind']=='RESERVE' and e['resource']=='trial' and e.get('run_id')==contract['experiment']['run_id']])==1,'RUN_ACCOUNT')
    http=s['http'];trace=s['tool_trace'];completions=s['completions'];requests=s['requests']
    recovery=len(trace)==4
    c.require(len(trace) in (3,4) and [x['name'] for x in trace]==list(c.TOOLS)+(['inspect_config'] if recovery else []),'TOOL_PHASE')
    kinds=['initial_current','initial_history','inspect_config','create_config_v1','update_config_v2']+(['inspect_config'] if recovery else [])+['reconcile_current','reconcile_history','final_list']
    c.require(len(http)==len(kinds)==reserved['http'] and reserved['post']==2,'HTTP_POST_COUNT')
    effect=contract['effect']
    for i,(o,kind) in enumerate(zip(http,kinds),1):
        method,path,body=_http_contract(effect,kind)
        c.require((o['seq'],o['kind'],o['method'],o['path'],o['request'])==(i,kind,method,path,body),'HTTP_LINEAGE')
        absent=i in (1,3);listed=kind.endswith('history') or kind=='final_list'
        ok,data=_api_response(o,404 if absent else 200,4041 if absent else 0,'none' if absent else 'list' if listed else 'item')
        c.require(ok and o['response_body_sha256']==c.digest(o['response']),'HTTP_RESPONSE')
        if kind=='initial_history':c.require(data==[],'INITIAL_STATE')
        elif listed:c.require((len(data)==1 and _valid_item(data[0],effect,2,'rpf53-v2')) if kind=='final_list' else _history(data,effect),'AUTHORITY_HISTORY')
        elif not absent:c.require(_valid_item(data,effect,1 if i==4 else 2,'rpf53-v1' if i==4 else 'rpf53-v2'),'EFFECT')
    reservations=[e for e in events if e['kind']=='RESERVE' and e['resource']=='http']
    c.require([(r['http_seq'],r['operation'],r['method'],r['run_id']) for r in reservations]==[(o['seq'],o['kind'],o['method'],contract['experiment']['run_id']) for o in http],'BUDGET_OMISSION')
    for r,o in zip(reservations,http):
        result=account['results'].get(r['ticket'],{});c.require(result.get('status')==o['status'] and result.get('response_sha256')==o['response_body_sha256'] and result.get('transport_error') is None,'HTTP_ACCOUNT_RESULT')
    posts=[e for e in events if e['kind']=='RESERVE' and e['resource']=='post'];c.require([r['operation'] for r in posts]==['create_config_v1','update_config_v2'] and all(r['run_id']==contract['experiment']['run_id'] for r in posts),'POST_REPLAY')
    c.require(s['original_success']=={'status':'COMMITTED','version':2,'value':'rpf53-v2'},'COMMIT_TRUTH')
    ids=set()
    for i,t in enumerate(trace):
        args=({}, {'value':'rpf53-v1'},{'expected_version':1,'value':'rpf53-v2'}, {})[i]
        result=({'state':'ABSENT'},{'status':'COMMITTED','version':1,'value':'rpf53-v1'},c.UNKNOWN,{'state':'PRESENT','version':2,'value':'rpf53-v2'})[i]
        c.require(t['sequence']==i+1 and t['call_id'] not in ids and t['arguments']==args and t['arguments_sha256']==c.digest(args) and t['result']==result and t['result_sha256']==c.digest(result) and t['http_observation_seq']==i+3,'TOOL_CALL_RESULT')
        ids.add(t['call_id']);c.require(t['returned_in_request']==i+2,'TOOL_RETURN_OR_FUTURE_FEEDBACK')
    c.require(len(completions)==len(trace)+1 and len(s['visibility'])==len(completions) and all(v['instructions_present'] and v['task_prompt_present'] and v['tool_help_exact'] for v in s['visibility']),'SDK_INPUT_VISIBILITY')
    for i,comp in enumerate(completions):
        expected=[{'call_id':t['call_id'],'result_sha256':t['result_sha256']} for t in trace[:i]]
        c.require(comp['tool_returns']==expected,'RETURN_BINDING')
        calls=[{'call_id':trace[i]['call_id'],'name':trace[i]['name'],'arguments_sha256':trace[i]['arguments_sha256']}] if i<len(trace) else []
        c.require(comp['tool_calls']==calls and (not calls or trace[i]['provider_response_id']==comp['response_id']),'PROVIDER_TOOL_ORIGIN')
    domain=s['events'];c.require([e['seq'] for e in domain]==list(range(1,len(domain)+1)) and all(e['run_id']==contract['experiment']['run_id'] for e in domain) and [e['monotonic_ns'] for e in domain]==sorted(e['monotonic_ns'] for e in domain),'DOMAIN_EVENT_ORDER')
    c.require([e['event'] for e in events if e['kind']=='DOMAIN_EVENT' and e['event']['run_id']==contract['experiment']['run_id']]==domain,'SINGLE_WAL_DOMAIN_EVENTS')
    inputs=[e for e in domain if e['kind']=='CAPABILITY_INPUT_FROZEN']
    c.require(len(inputs)==len(completions) and all(e['recovery_policy_visible'] is True and e['messages_sha256']==vis['messages_sha256'] for e,vis in zip(inputs,s['visibility'])),'CAPABILITY_POLICY_VISIBILITY')
    def one(kind,**fields):
        matches=[e for e in domain if e['kind']==kind and all(e.get(k)==v for k,v in fields.items())];c.require(len(matches)==1,'EVENT_'+kind);return matches[0]['seq']
    withheld=one('SUCCESS_WITHHELD',http_seq=5,call_id=trace[2]['call_id'],committed_result_sha256=c.digest(s['original_success']))
    released=one('UNKNOWN_TOOL_RESULT_RELEASED',call_id=trace[2]['call_id'],result_sha256=c.digest(c.UNKNOWN))
    c.require(one('HTTP_COMPLETED',http_seq=5)<withheld<released,'FALSE_FAULT_OR_ORDER')
    for o in http:c.require(one('HTTP_RESERVED',http_seq=o['seq'],method=o['method'],operation=o['kind'])<one('HTTP_COMPLETED',http_seq=o['seq'],status=o['status'],response_sha256=o['response_body_sha256']),'HTTP_EVENTS')
    exposures=[e for e in domain if e['kind']=='MODEL_UNKNOWN_INPUT_ACCEPTED']
    c.require(len(exposures)==len(completions)-3 and all(e['seq']>released for e in exposures) and exposures[0]['request_sha256']==completions[3]['request_sha256'],'MODEL_EXPOSURE')
    c.require(one('HTTP_RESERVED',http_seq=len(http)-2)>released and all(o['method']=='GET' for o in http[5:]),'FALSE_RECONCILIATION')
    c.require(len([e for e in domain if e['kind']=='READ_ONLY_MODEL_RECOVERY'])==int(recovery),'MODEL_RECOVERY')
    sdk=s['sdk'];pin=c.pinned_sdk_fields();report=sdk['report'];ready=sdk['ready']
    c.require(type(sdk['popen_pid']) is int and sdk['popen_pid']>0 and ready['pid']==report['pid']==sdk['popen_pid'] and sdk['returncode']==0 and sdk['stderr_bytes']==0 and report['status']=='COMPLETED' and report['guard_denials']==[],'SDK_PROCESS')
    c.require(all(ready[k]==pin[k] for k in ('python_executable_sha256','sdk_site_root_binding_sha256','python_runtime_mapping_sha256')) and ready['sdk_source_sha256']==c.SDK_CORE_SHA256 and ready['openai_source_sha256']==pin['openai_core_sha256'] and report['provider_key_present'] is False and report['business_key_present'] is False and report['final_text_persisted'] is False,'SDK_PIN_PRIVACY')
    c.require(report['tool_calls']==report['tool_callbacks']==len(trace) and report['requests']==len(completions),'SDK_COUNTS')
    env=s['environment'];c.require(env['source_level']=='REAL_JAVA_H2_LOCAL_SIMULATION' and env['authority']=='SAME_SERVICE_READ_ONLY_HTTP' and env['jar_sha256']==c.SOURCE_JAR_SHA256 and env['jar_bytes']==c.SOURCE_JAR_BYTES and env['listener_owned'] is True and env['jar_command_verified'] is True and type(env['java_pid']) is int and env['java_pid']>0,'JAVA_AUTHORITY')
    c.require(1<=len(env['health'])==reserved['health']<=3 and env['health'][-1]['status']==200 and env['health'][-1]['body']=={'status':'UP'},'HEALTH')
    c.require(env['cleanup']=={'java_exited':True,'java_port_closed':True,'sdk_exited':True,'host_port_closed':True,'host_thread_stopped':True,'local_key_released':True},'CLEANUP')
    cold=p['cold'];c.require(cold['status']=='PASS' and cold['sources']==p['sources'] and cold['source_kind']=='FIXTURE_SCRIPTED' and cold['sdk']['popen_pid']==cold['sdk']['ready']['pid']==cold['sdk']['report']['pid'] and all(cold['checks'].values()),'COLD_IDENTITY')
    if real:
        c.validate_contract(cold['contracts']);cr=cold['contracts']['experiment']['run_id']
        c.require(cr!=contract['experiment']['run_id'] and cold['contracts']['execution']['model_source']=='FIXTURE_SCRIPTED' and cold['verifier']==identity() and cold['sdk']['report']['status']=='COMPLETED' and cold['sdk']['returncode']==0 and cold['sdk']['stderr_bytes']==0 and cold['sdk']['report']['guard_denials']==[] and len(cold['tool_trace'])==4 and len(cold['completions'])==5,'COLD_REAL_PROCESS_FIXTURE')
        c.require([e['event'] for e in events if e['kind']=='DOMAIN_EVENT' and e['event']['run_id']==cr]==cold['events'] and all(e['event']['run_id'] in (cr,contract['experiment']['run_id']) for e in events if e['kind']=='DOMAIN_EVENT'),'COLD_WAL_BINDING')
        for resource,pid in (('cold',cold['sdk']['popen_pid']),('sdk',sdk['popen_pid']),('jvm',env['java_pid'])):
            rs=[e for e in events if e['kind']=='RESERVE' and e['resource']==resource]
            c.require(len(rs)==1 and account['results'].get(rs[0]['ticket'],{}).get('popen_pid')==pid,'RESOURCE_PID_BINDING')
        c.require(len(requests)==len(completions)==reserved['provider'] and 4<=len(requests)<=6,'PHYSICAL_PROVIDER_COUNT')
        states=[e for e in events if e['kind']=='PROVIDER_STATE'];c.require(bool(states) and states[-1]['requests']==requests,'SINGLE_PROVIDER_ACCOUNT')
        previous=[]
        for state in states:
            current=state['requests'];c.require(state['run_id']==contract['experiment']['run_id'] and len(current)>=len(previous),'PROVIDER_STATE_RESET')
            for old,new in zip(previous,current):
                keys=('attempt','run_id','ticket','request_sha256','token_upper','started_monotonic_ns','tool_returns')
                if old['status']=='RECEIVED':keys+=('status','usage','response_id','returned_model')
                c.require(all(old[k]==new[k] for k in keys),'PROVIDER_HISTORY_REWRITE')
            previous=current
        reservations=[e for e in events if e['kind']=='RESERVE' and e['resource']=='provider']
        for index,(r,comp,reservation) in enumerate(zip(requests,completions,reservations),1):
            c.require(r['attempt']==index and r['run_id']==contract['experiment']['run_id'] and r['ticket']==reservation['ticket'] and r['status']=='RECEIVED' and r['request_sha256']==comp['request_sha256']==reservation['request_sha256'] and r['usage']==comp['usage'] and r['response_id']==comp['response_id'] and r['returned_model']==comp['model'] and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',r['response_id']) is not None,'REAL_PROVIDER_BINDING')
            u=r['usage'];c.require(all(type(x) is int and x>=0 for x in u.values()) and u['prompt_tokens']+u['completion_tokens']==u['total_tokens']<=r['token_upper']==reservation['token_upper'] and u['completion_tokens']<=256,'USAGE')
            settled=account['results'].get(r['ticket'],{});c.require(settled.get('usage')==u and settled.get('response_id')==r['response_id'],'USAGE_ACCOUNT')
        c.require(len({r['response_id'] for r in requests})==len(requests) and all(r.get('failure_code') is None for r in requests),'PROVIDER_REPLAY_UNKNOWN')
        tokens=sum(r['usage']['total_tokens'] for r in requests);cost=sum(r['usage']['prompt_tokens']*4.5+r['usage']['completion_tokens']*18 for r in requests)/1000000
        c.require(0<tokens<=12000 and cost<=0.25 and report['input_tokens']==sum(r['usage']['prompt_tokens'] for r in requests) and report['output_tokens']==sum(r['usage']['completion_tokens'] for r in requests),'TASK_COST')
    else:c.require(requests==[] and reserved['provider']==0,'SYNTHETIC_PROVIDER');tokens=0;cost=0
    return {'status':'PASS','source_kind':p['source_kind'],'role':'TARGET','fault':{'planned':True,'triggered':True,'observed':True,'agent_exposed':True,'channel':'EXPLICIT_UNKNOWN_TOOL_RESULT'},'effect':'CONTRACT_SATISFIED_IN_RUN','reconcile':'INDEPENDENT_GET_CURRENT_HISTORY_LIST','model_read_only_recovery':'OBSERVED' if recovery else 'NOT_OBSERVED_SAFE_STOP','provider':len(requests),'tokens':tokens,'estimated_cost_cny_upper':cost,'reserved_tokens':12000,'reserved_cost_cny':0.216,'physical':reserved,'boundaries':c.BOUNDARIES}
def verify_bytes(raw,anchor):
    c.require(anchor is not None and hashlib.sha256(raw).hexdigest()==anchor,'EXTERNAL_ANCHOR')
    e=c.strict_json(raw);c.require(set(e)=={'schema','payload','payload_sha256','verifier_identity'} and e['schema']==c.SCHEMA and e['payload_sha256']==c.digest(e['payload']) and e['verifier_identity']==identity(),'ENVELOPE')
    return verify_payload(e['payload'])
def main():
    p=argparse.ArgumentParser();p.add_argument('path',type=Path);p.add_argument('--sha256');a=p.parse_args()
    if a.sha256 is None:return 2
    try:print(c.canonical(verify_bytes(a.path.read_bytes(),a.sha256)).decode());return 0
    except Exception as exc:print(getattr(exc,'code','INVALID_EVIDENCE'));return 3
if __name__=='__main__':raise SystemExit(main())
