"""RPF-63 deterministic offline two-role, business, feedback and physical WAL verifier."""
import argparse,hashlib,re
from pathlib import Path
from . import pge_dual_contracts as c
from .config_live_runtime import _http_contract,_api_response,_valid_item
from .config_live_verify import _history
from .pge_dual_session import body_for,feedback,parse_selection,validate_response_shape

def identity():return {'version':'rpf63-dual-agent-verifier-v1','sha256':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
def seal(p):return {'schema':c.SCHEMA,'payload':p,'payload_sha256':c.digest(p),'verifier_identity':identity()}
def verify_sdk(sdk,trace,comps,real):
 pin=c.pinned_sdk_fields();ready=sdk['ready'];report=sdk['report'];pid=sdk['popen_pid']
 c.require(type(pid) is int and pid>0 and ready['pid']==report['pid']==pid and sdk['returncode']==0 and sdk['stderr_bytes']==0 and report['status']=='COMPLETED' and report['guard_denials']==[],'SDK_PROCESS')
 c.require(all(ready[k]==pin[k] for k in ('python_executable_sha256','sdk_site_root_binding_sha256','python_runtime_mapping_sha256')) and ready['sdk_source_sha256']==c.SDK_CORE_SHA256 and ready['openai_source_sha256']==pin['openai_core_sha256'],'SDK_IDENTITY')
 c.require(report['provider_key_present'] is False and report['business_key_present'] is False and report['final_text_persisted'] is False and report['tool_calls']==report['tool_callbacks']==len(trace) and report['requests']==len(comps),'SDK_PRIVACY_COUNTS')
 if real:c.require(report['input_tokens']==sum(x['usage']['prompt_tokens'] for x in comps) and report['output_tokens']==sum(x['usage']['completion_tokens'] for x in comps),'SDK_USAGE')
def verify_scene(ct,s,account,index,*,real):
 c.validate_contract(ct);c.require(set(s)=={'contracts','http','events','tool_trace','completions','visibility','sdk','environment','requests','original_success','host_failure'} and s['contracts']==ct and s['host_failure'] is None,'SCENE_FIELDS')
 c.require(ct['execution']['model_source']==('REAL_PROVIDER' if real else 'FIXTURE_SCRIPTED'),'TARGET_ROLE_SOURCE')
 run=ct['experiment']['run_id'];suppressed=ct['experiment']['fault_plan']['enabled'];http=s['http'];trace=s['tool_trace'];comps=s['completions'];events=account['events'];recovery=len(trace)==4
 c.require(len(trace) in (3,4) and [t['name'] for t in trace]==list(c.TOOLS)+(['inspect_config'] if recovery else []),'TARGET_TOOLS')
 kinds=['initial_current','initial_history','inspect_config','create_config_v1','update_config_v2']+(['inspect_config'] if recovery else [])+['reconcile_current','reconcile_history','final_list']
 c.require(len(http)==len(kinds),'HTTP_COUNT');effect=ct['effect']
 for i,(o,kind) in enumerate(zip(http,kinds),1):
  method,path,body=_http_contract(effect,kind);c.require((o['seq'],o['kind'],o['method'],o['path'],o['request'])==(i,kind,method,path,body),'HTTP_LINEAGE')
  absent=i in (1,3);listed=kind.endswith('history') or kind=='final_list';ok,data=_api_response(o,404 if absent else 200,4041 if absent else 0,'none' if absent else 'list' if listed else 'item')
  c.require(ok and o['response_body_sha256']==c.digest(o['response']),'HTTP_RESPONSE')
  if kind=='initial_history':c.require(data==[],'INITIAL_STATE')
  elif listed:c.require((len(data)==1 and _valid_item(data[0],effect,2,'rpf53-v2')) if kind=='final_list' else _history(data,effect),'EFFECT_HISTORY')
  elif not absent:c.require(_valid_item(data,effect,1 if i==4 else 2,'rpf53-v1' if i==4 else 'rpf53-v2'),'EFFECT_ITEM')
 rs=[e for e in events if e['kind']=='RESERVE' and e['resource']=='http' and e.get('round')==index]
 c.require([(x['http_seq'],x['operation'],x['method'],x['run_id']) for x in rs]==[(o['seq'],o['kind'],o['method'],run) for o in http],'HTTP_BUDGET_OMISSION')
 for r,o in zip(rs,http):
  z=account['results'].get(r['ticket'],{});c.require(z.get('status')==o['status'] and z.get('response_sha256')==o['response_body_sha256'] and z.get('transport_error') is None,'HTTP_ACCOUNT_RESULT')
 posts=[e for e in events if e['kind']=='RESERVE' and e['resource']=='post' and e.get('round')==index];c.require([e['operation'] for e in posts]==['create_config_v1','update_config_v2'] and all(e['run_id']==run for e in posts),'POST_REPLAY')
 c.require(s['original_success']==({'status':'COMMITTED','version':2,'value':'rpf53-v2'} if suppressed else None),'FAULT_COMMIT_TRUTH')
 ids=set()
 for i,t in enumerate(trace):
  args=({}, {'value':'rpf53-v1'},{'expected_version':1,'value':'rpf53-v2'}, {})[i]
  result=({'state':'ABSENT'},{'status':'COMMITTED','version':1,'value':'rpf53-v1'},c.UNKNOWN if suppressed else {'status':'COMMITTED','version':2,'value':'rpf53-v2'},{'state':'PRESENT','version':2,'value':'rpf53-v2'})[i]
  c.require(t['sequence']==i+1 and t['call_id'] not in ids and t['arguments']==args and t['arguments_sha256']==c.digest(args) and t['result']==result and t['result_sha256']==c.digest(result) and t['http_observation_seq']==i+3 and t['returned_in_request']==i+2,'TARGET_TOOL_LINEAGE');ids.add(t['call_id'])
 c.require(len(comps)==len(trace)+1<=5 and len(s['visibility'])==len(comps) and all(x['instructions_present'] and x['task_prompt_present'] and x['tool_help_exact'] for x in s['visibility']),'INPUT_VISIBILITY')
 for i,comp in enumerate(comps):
  returns=[{'call_id':t['call_id'],'result_sha256':t['result_sha256']} for t in trace[:i]];calls=[{'call_id':trace[i]['call_id'],'name':trace[i]['name'],'arguments_sha256':trace[i]['arguments_sha256']}] if i<len(trace) else []
  c.require(comp['tool_returns']==returns and comp['tool_calls']==calls and (not calls or trace[i]['provider_response_id']==comp['response_id']),'TARGET_PROVIDER_ORIGIN')
 d=s['events'];c.require([x['seq'] for x in d]==list(range(1,len(d)+1)) and all(x['run_id']==run for x in d) and [e['event'] for e in events if e['kind']=='DOMAIN_EVENT' and e.get('round')==index]==d,'DOMAIN_WAL')
 def one(kind,**fields):
  matches=[e for e in d if e['kind']==kind and all(e.get(k)==v for k,v in fields.items())];c.require(len(matches)==1,'EVENT_'+kind);return matches[0]['seq']
 for o in http:c.require(one('HTTP_RESERVED',http_seq=o['seq'],method=o['method'],operation=o['kind'])<one('HTTP_COMPLETED',http_seq=o['seq'],status=o['status'],response_sha256=o['response_body_sha256']),'HTTP_EVENT_ORDER')
 inputs=[e for e in d if e['kind']=='CAPABILITY_INPUT_FROZEN'];c.require(len(inputs)==len(comps) and all(e['recovery_policy_visible'] and e['messages_sha256']==vis['messages_sha256'] for e,vis in zip(inputs,s['visibility'])),'RECOVERY_POLICY')
 exposures=[e for e in d if e['kind']=='MODEL_UNKNOWN_INPUT_ACCEPTED']
 if suppressed:
  withheld=one('SUCCESS_WITHHELD',call_id=trace[2]['call_id'],http_seq=5,committed_result_sha256=c.digest(s['original_success']));released=one('UNKNOWN_TOOL_RESULT_RELEASED',call_id=trace[2]['call_id'],result_sha256=c.digest(c.UNKNOWN));c.require(one('HTTP_COMPLETED',http_seq=5)<withheld<released,'FAULT_ORDER')
  c.require(len(exposures)==len(comps)-3 and exposures[0]['request_sha256']==comps[3]['request_sha256'] and all(e['seq']>released for e in exposures),'TARGET_UNKNOWN_EXPOSED')
 else:c.require(not exposures and not any(e['kind'] in ('SUCCESS_WITHHELD','UNKNOWN_TOOL_RESULT_RELEASED') for e in d),'FALSE_NORMAL_FAULT')
 c.require(len([e for e in d if e['kind']=='READ_ONLY_MODEL_RECOVERY'])==(int(recovery) if suppressed else 0) and all(o['method']=='GET' for o in http[5:]),'FALSE_RECOVERY')
 verify_sdk(s['sdk'],trace,comps,real)
 env=s['environment'];c.require(env['source_level']=='REAL_JAVA_H2_LOCAL_SIMULATION' and env['authority']=='SAME_SERVICE_READ_ONLY_HTTP' and env['jar_sha256']==c.SOURCE_JAR_SHA256 and env['jar_bytes']==c.SOURCE_JAR_BYTES and env['listener_owned'] and env['jar_command_verified'] and type(env['java_pid']) is int and env['java_pid']>0,'JAVA_AUTHORITY')
 trials=[r for r in account['tickets'].values() if r['resource']=='trial' and r.get('round')==index];c.require(len(trials)==1 and trials[0]['run_id']==run,'TRIAL_ACCOUNT')
 health=[r for r in account['tickets'].values() if r['resource']=='health' and r.get('round')==index];c.require(1<=len(env['health'])==len(health)<=3 and env['health'][-1]['status']==200 and env['health'][-1]['body']=={'status':'UP'},'HEALTH')
 c.require(env['cleanup']=={'java_exited':True,'java_port_closed':True,'sdk_exited':True,'host_port_closed':True,'host_thread_stopped':True,'local_key_released':True},'CLEANUP')
 return {'effect':'CONTRACT_SATISFIED_IN_RUN','fault':{'planned':suppressed,'triggered':suppressed,'observed':suppressed,'agent_exposed':suppressed},'recovery':'OBSERVED' if suppressed and recovery else 'NOT_OBSERVED_SAFE_STOP' if suppressed else 'NOT_APPLICABLE','authority':'SAME_SERVICE_READ_ONLY_HTTP'}
def verify_payload(p):
 c.require(set(p)=={'source_kind','plan','rows','ledger','cold','boundaries'} and p['boundaries']==c.BOUNDARIES,'WITNESS_FIELDS')
 plan=p['plan'];c.validate_plan(plan);c.require(p['source_kind']==plan['source_kind'] in ('REAL_EXPLORER_REAL_TARGET','SYNTHETIC_TEST_ONLY') and plan['source_files']==c.sources(),'SOURCE_OR_ROLE')
 real=p['source_kind']=='REAL_EXPLORER_REAL_TARGET';rows=p['rows'];c.require(len(rows)==2,'TWO_ROUNDS');account=c.replay(p['ledger']);c.require(account['pool'] and not account['unknown'],'ACCOUNT_UNKNOWN')
 c.require(account['events'][0]['source_sha256']==c.digest(plan['source_files']),'WAL_SOURCE');counts=account['reserved'];c.require(counts['session']==counts['cold']==1 and 1<=counts['metadata']<=2 and counts['trial']==counts['jvm']==counts['sdk']==2,'PHYSICAL_COUNTS')
 events=account['events'];all_provider=[];seen=set();runs=set();ports=set();pids=set();prior=[]
 for index,row in enumerate(rows,1):
  c.require(set(row)=={'round','selection','candidate_id','contract','body','observation','provider_ticket','capture','verdict','feedback','role_source'} and row['round']==index and row['role_source']==p['source_kind'],'ROUND_ROLE')
  ct=row['contract'];run=ct['experiment']['run_id'];c.require(row['candidate_id'] in c.CANDIDATES and ct==plan['rounds'][index-1][row['candidate_id']] and ct['experiment']['runtime_source_sha256']==c.digest(plan['source_files']),'ROUND_CONTRACT')
  c.require(run not in runs,'RUN_REUSE');runs.add(run)
  for port in (ct['execution']['service']['port'],ct['execution']['agent_host']['port']):c.require(port not in ports,'PORT_REUSE');ports.add(port)
  for pid in (row['capture']['sdk']['popen_pid'],row['capture']['environment']['java_pid']):c.require(pid not in pids,'PID_REUSE');pids.add(pid)
  c.require(row['body']==body_for(prior),'FUTURE_FEEDBACK_OR_INPUT');obs=row['observation'];shape=obs['shape'];validate_response_shape(shape)
  c.require(obs['request_sha256']==c.digest(row['body']) and obs['http_status']==200 and obs['attempt']==row['provider_ticket'] and shape['model'] in (c.MODEL,'DeepSeek-V4.1-Flash-1017') and shape['choices_count']==1,'EXPLORER_RESPONSE')
  sel=row['selection'];parsed=parse_selection({'id':shape['response_id'],'model':shape['model'],'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','tool_calls':[sel]}}]},seen);seen.add(sel['id']);c.require(parsed==sel and c.strict_json(sel['function']['arguments'].encode())=={'candidate_id':row['candidate_id']},'CHOICE')
  ch=shape['choices'][0];call=ch['calls'][0];c.require(ch['finish_reason']=='tool_calls' and ch['tool_calls_count']==1 and call['function_name']=='select_experiment' and call['call_id']['sha256']==c.digest(sel['id']) and call['arguments']['sha256']==c.digest(sel['function']['arguments']),'EXPLORER_TOOL_ORIGIN')
  ticket=account['tickets'][row['provider_ticket']];z=account['results'].get(row['provider_ticket'],{});c.require(ticket['role']=='EXPLORER' and ticket['round']==index and ticket['request_sha256']==c.digest(row['body']) and z.get('response_id')==shape['response_id'] and z.get('usage')==shape['usage'],'EXPLORER_METER')
  all_provider.append((ticket,z));verdict=verify_scene(ct,row['capture'],account,index,real=real);c.require(row['verdict']==verdict and row['feedback']==feedback(ct,row['capture'],verdict,[r['feedback'] for r in prior]),'ORACLE_FEEDBACK')
  def event(kind):
   matches=[e for e in events if e['kind']==kind and e.get('round')==index];c.require(len(matches)==1,'SESSION_EVENT_'+kind);return matches[0]
  choice=event('CHOICE_FROZEN');verified=event('DOMAIN_VERIFIED');frozen=event('FEEDBACK_FROZEN')
  c.require(choice['selection_sha256']==c.digest(sel) and choice['candidate_id']==row['candidate_id'] and choice['contract_sha256']==c.digest(ct) and verified['capture_sha256']==c.digest(row['capture']) and verified['verdict_sha256']==c.digest(verdict) and frozen['tool_call_id']==sel['id'] and frozen['feedback_sha256']==c.digest(row['feedback']) and choice['monotonic_ns']<verified['monotonic_ns']<frozen['monotonic_ns'],'FEEDBACK_LINEAGE')
  if index==2:
   first=[e for e in events if e['kind']=='FEEDBACK_FROZEN' and e.get('round')==1][0];c.require(first['monotonic_ns']<ticket['monotonic_ns'],'FEEDBACK_BEFORE_REQUEST')
  records=row['capture']['requests'];comps=row['capture']['completions'];c.require(len(records)==len(comps),'TARGET_USAGE_OMISSION')
  states=[e for e in events if e['kind']=='PROVIDER_STATE' and e.get('round')==index];c.require(states and states[-1]['requests']==records and all(e['role']=='TARGET' and e['run_id']==run for e in states),'PROVIDER_STATE')
  previous=[]
  for state in states:
   current=state['requests'];c.require(len(current)>=len(previous),'PROVIDER_HISTORY_REMOVED')
   for a,b in zip(previous,current):
    keys=('attempt','run_id','role','ticket','request_sha256','token_upper','input_upper','proof','started_monotonic_ns','tool_returns')+(('usage','status','response_id','returned_model') if a['status']=='RECEIVED' else ())
    c.require(all(a[k]==b[k] for k in keys),'PROVIDER_HISTORY_REWRITE')
   previous=current
  for i,(r,comp) in enumerate(zip(records,comps),1):
   t=account['tickets'][r['ticket']];z=account['results'].get(r['ticket'],{});c.require(r['attempt']==i and r['role']==t['role']=='TARGET' and t['round']==index and r['run_id']==t['run_id']==run and r['status']=='RECEIVED' and r['failure_code'] is None and r['request_sha256']==comp['request_sha256']==t['request_sha256'] and r['usage']==comp['usage']==z.get('usage') and r['response_id']==comp['response_id']==z.get('response_id') and r['returned_model']==comp['model'] and r['token_upper']==t['token_upper'] and r['input_upper']==t['input_upper'],'TARGET_METER')
   c.require(r['tool_returns']==comp['tool_returns'] and r['tool_call_ids']==[x['call_id'] for x in comp['tool_calls']] and r['returned_tool_ids']==[x['call_id'] for x in comp['tool_returns']],'TARGET_CALL_BUDGET_BINDING')
   if i>1:
    proof=t['proof'];prev=records[i-2];c.require(proof['previous_request_sha256']==prev['request_sha256'] and proof['prefix_sha256']==row['capture']['visibility'][i-2]['messages_sha256'] and proof['previous_prompt_tokens']==prev['usage']['prompt_tokens'] and proof['framing_guard']==512 and t['input_upper']==proof['previous_prompt_tokens']+proof['suffix_bytes']+512,'INPUT_BOUND_PROOF')
   all_provider.append((t,z))
  for resource,pid in (('sdk',row['capture']['sdk']['popen_pid']),('jvm',row['capture']['environment']['java_pid'])):
   ts=[x for x in account['tickets'].values() if x['resource']==resource and x.get('round')==index];c.require(len(ts)==1 and account['results'].get(ts[0]['ticket'],{}).get('popen_pid')==pid,'PID_ACCOUNT')
  prior.append(row)
 c.require(len(all_provider)==counts['provider'] and len({z.get('response_id') for _,z in all_provider})==len(all_provider),'PROVIDER_OMISSION_OR_REPLAY')
 tokens=0;cost=0
 for t,z in all_provider:
  u=z.get('usage');c.require(z.get('status')=='RECEIVED' and type(u) is dict and set(u)=={'prompt_tokens','completion_tokens','total_tokens'} and all(type(x) is int and x>=0 for x in u.values()) and u['prompt_tokens']+u['completion_tokens']==u['total_tokens']<=t['token_upper'] and u['prompt_tokens']<=t['input_upper'] and u['completion_tokens']<=t['output_cap'],'USAGE_UNKNOWN_OR_LIMIT');tokens+=u['total_tokens'];cost+=(u['prompt_tokens']*4.5+u['completion_tokens']*18)/1e6
  if real:c.require(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',z['response_id']) is not None,'REAL_RESPONSE_ID')
 c.require(tokens<=30000 and cost<=0.65 and 2*sum(c.TARGET_CAPS)+2*c.EXPLORER_CAP==30000,'TOTAL_BUDGET_PROOF')
 cold=p['cold'];c.require(cold['status']=='PASS' and cold['source_kind']=='FIXTURE_SCRIPTED' and cold['sources']==plan['source_files'] and cold['verifier']==identity() and all(cold['checks'].values()),'COLD_SOURCE')
 verify_sdk(cold['sdk'],cold['tool_trace'],cold['completions'],False);c.require(cold['sdk']['popen_pid'] not in pids and len(cold['tool_trace'])==4 and cold['tool_trace'][2]['result']==c.UNKNOWN and len(cold['completions'])==5,'COLD_PROTOCOL')
 if real:
  c.validate_contract(cold['contracts']);c.require(cold['contracts']['execution']['model_source']=='FIXTURE_SCRIPTED' and cold['contracts']['experiment']['run_id'] not in runs and [t['name'] for t in cold['tool_trace']]==list(c.TOOLS)+['inspect_config'] and [t['returned_in_request'] for t in cold['tool_trace']]==[2,3,4,5],'COLD_REAL_PROTOCOL')
 cold_t=[x for x in account['tickets'].values() if x['resource']=='cold'];c.require(len(cold_t)==1 and account['results'].get(cold_t[0]['ticket'],{}).get('popen_pid')==cold['sdk']['popen_pid'],'COLD_PID_ACCOUNT')
 c.require([e['event'] for e in events if e['kind']=='DOMAIN_EVENT' and 'round' not in e]==cold['events'],'COLD_WAL')
 completed=[e for e in events if e['kind']=='SESSION_COMPLETED'];c.require(len(completed)==1 and completed[0]['session_id']==plan['session_id'] and completed[0]['rows_sha256']==c.digest(rows),'SESSION_COMPLETE')
 changed=rows[0]['candidate_id']!=rows[1]['candidate_id'];new=bool(rows[1]['feedback']['new_facts'])
 return {'status':'PASS','source_kind':p['source_kind'],'choices':[r['candidate_id'] for r in rows],'provider_requests':counts['provider'] if real else 0,'replayed_provider_requests':0 if real else counts['provider'],'tokens':tokens if real else 0,'estimated_cost_cny_upper':cost if real else 0,'reserved_tokens':30000,'reserved_cost_cny':0.54,'physical':counts,'feedback':'VERIFIED_AND_BOUND_TO_SECOND_EXPLORER','L2_observed':changed and new,'causality':'NOT_PROVEN','boundaries':c.BOUNDARIES}
def verify_bytes(raw,anchor):
 c.require(anchor is not None and hashlib.sha256(raw).hexdigest()==anchor,'EXTERNAL_ANCHOR');e=c.strict_json(raw);c.require(set(e)=={'schema','payload','payload_sha256','verifier_identity'} and e['schema']==c.SCHEMA and e['payload_sha256']==c.digest(e['payload']) and e['verifier_identity']==identity(),'ENVELOPE');return verify_payload(e['payload'])
def main():
 p=argparse.ArgumentParser();p.add_argument('path',type=Path);p.add_argument('--sha256');a=p.parse_args()
 if a.sha256 is None:return 2
 try:print(c.canonical(verify_bytes(a.path.read_bytes(),a.sha256)).decode());return 0
 except Exception as exc:print(getattr(exc,'code','INVALID_EVIDENCE'));return 3
if __name__=='__main__':raise SystemExit(main())
