"""Context-injected Java/HTTP port; pinned SDK is always scripted and Provider-denied."""
import copy,hashlib,secrets,time
from . import pge_port_context as c
from .pge_domain_port import classify,projection
from .config_live_runtime import ConfigLiveHost,ConfigLiveHttp,ConfigLiveBusiness,ConfigLiveMemoryBackend,ProviderLedger,_http_contract,_api_response,_valid_item
from .config_live_verify import _history
class Journal:
 def __init__(self,ledger,run):self.ledger,self.run,self.events=ledger,run,[]
 def add(self,kind,**data):
  e={'seq':len(self.events)+1,'kind':kind,'run_id':self.run,'monotonic_ns':time.monotonic_ns(),**data}
  self.ledger.append('DOMAIN_EVENT',domain=c.DOMAINS[1],run_id=self.run,event=e);self.events.append(e);return e
class Http(ConfigLiveHttp):
 def __init__(self,ctx,ct,key,journal,ledger):
  self.contracts,self.effect,self.port=ct,ct['effect'],ct['execution']['service']['port'];self._api_key=key;self.deadline=time.monotonic()+600;self.observations=[];self.post_count=0;self.stop_writes=False;self.ctx,self.journal,self.total=ctx,journal,ledger
 def request(self,kind,*,reconcile=False):
  method,_,_=_http_contract(self.effect,kind);c.require(method!='POST' or not self.stop_writes,'WRITE_AFTER_UNKNOWN');data={'domain':c.DOMAINS[1],'run_id':self.contracts['experiment']['run_id'],'http_seq':len(self.observations)+1,'operation':kind,'method':method};ticket=self.total.reserve('http',**data);post=self.total.reserve('post',**data) if method=='POST' else None
  self.journal.add('HTTP_RESERVED',**{k:data[k] for k in ('http_seq','operation','method')});o=super().request(kind,reconcile=reconcile);self.total.settle(ticket,status=o['status'],response_sha256=o['response_body_sha256'],transport_error=o['transport_error'])
  if post:self.total.settle(post,status=o['status'],unknown=o['status']!=200 or o['transport_error'] is not None)
  self.journal.add('HTTP_COMPLETED',http_seq=o['seq'],status=o['status'],response_sha256=o['response_body_sha256']);return o
class Host(ConfigLiveHost):
 def __init__(self,ct,business,journal):
  c.validate_contract(ct);self.contracts,self.business,self.journal=ct,business,journal;self.ledger=ProviderLedger.fixture_only(ct['experiment']['run_id']);self.fixture,self.api_key=True,None
  self.expected_tool_schema_sha256=self.fixture_failure_code=self.tool_schema_sha256=self.tool_schema_summary=self.tool_definitions=self.runtime=self.failure=None
  self.intents,self.tool_returns={},{};self.tool_trace,self.tool_rejections,self.visible_contract_checks,self.provider_responses=[],[],[],[];self._server=self._thread=None;self.fixture_index=0;self.request_started=time.monotonic();self.activated=False;self.original_success=None
 def _provider_request(self,body):c.require(False,'PROVIDER_FORBIDDEN')
 def _completion(self,body):
  c.require(self.fixture is True and self.api_key is None and c.RECOVERY in str(body.get('messages')),'FIXTURE_ONLY');return super()._completion(body)
 def _tool(self,body):
  phase=len(self.tool_trace);expected=list(c.TOOLS)+['inspect_config'];c.require(phase<len(expected) and body.get('name')==expected[phase],'TOOL_PHASE_OR_REPEAT_WRITE');result=super()._tool(body);item=self.tool_trace[-1]
  if body['name']=='update_config_v2' and self.contracts['experiment']['fault_plan']['enabled']:
   c.require(result=={'status':'COMMITTED','version':2,'value':'rpf53-v2'},'SUPPRESSION_PRECONDITION')
   if isinstance(self.business,ConfigLiveBusiness):
    o=self.business.client.observations[-1];ok,data=_api_response(o,200,0,'item');c.require(ok and _valid_item(data,self.contracts['effect'],2,'rpf53-v2'),'HTTP_COMMIT');self.business.client.stop_writes=True
   self.original_success=copy.deepcopy(result);self.activated=True;item.update(result=copy.deepcopy(c.UNKNOWN),result_sha256=c.digest(c.UNKNOWN));self.journal.add('SUCCESS_WITHHELD',call_id=item['call_id'],http_seq=item['http_observation_seq']);return item['result']
  if self.activated:self.journal.add('SCRIPTED_READ_ONLY_RECOVERY',call_id=item['call_id'])
  return result
 def _fixture_response(self,request):
  reconcile=self.fixture_index==3 and self.contracts['experiment']['fault_plan']['enabled'];data=super()._fixture_response(request)
  if reconcile:data['choices'][0].update(finish_reason='tool_calls',message={'role':'assistant','content':None,'tool_calls':[{'id':'call_rpf64_scripted_reconcile','type':'function','function':{'name':'inspect_config','arguments':'{}'}}]})
  return data

def run_sdk(ctx,ct,ledger,sdk,folder,host,*,cold=False):
 h,old=c.helpers();scratch=ctx.scope(folder/'sdk-scratch');scratch.mkdir();direct=h.resolve_direct_python(sdk);supervisor=c.ProcessSupervisor(ctx,ledger,ct,'cold' if cold else 'sdk');result=None
 try:
  host.start(ct['execution']['agent_host']['port']);cfg={'port':host.port,'token':host.token,'write_root':str(scratch),'sdk_readonly_path':str(old.SDK_SITE.resolve()),'sdk_site_root_binding_sha256':sdk['sdk_site_root_binding_sha256'],'python_runtime_mapping_sha256':sdk['python_runtime_mapping_sha256'],'instructions':ct['execution']['agent_instructions'],'task_prompt':ct['execution']['task_prompt'],'model':'rpf53-fixture-only','max_runtime_seconds':120,'fixture':True}
  proc=supervisor.start([str(direct),'-I','-B',str(c.ROOT/'runtime/runproof_runtime/effectwitness/config_live_external.py')],old._sdk_env(scratch),scratch,stdio=True);stdout,stderr=proc.communicate(c.canonical(cfg),timeout=120)
  parsed=c.strict_json(stdout);allowed={'status','framework','version','openai_version','pid','python_executable_sha256','usage_type','usage_fields','requests','input_tokens','output_tokens','tool_calls','tool_callbacks','sdk_source_sha256','openai_source_sha256','final_output_sha256','final_text_persisted','guard_denials','provider_key_present','business_key_present','stage','error_type','guard_code','denied_files'};c.require(type(parsed) is dict and set(parsed)<=allowed,'SDK_REPORT_FIELDS');report={k:v for k,v in parsed.items() if k!='denied_files'}
  result={'popen_pid':proc.pid,'ready':host.runtime,'report':report,'returncode':proc.returncode,'stderr_bytes':len(stderr)};ctx.once(folder/'sdk-received-before-cleanup.json',{'sdk':result,'tool_trace':host.tool_trace,'completions':host.provider_responses,'events':host.journal.events});supervisor.received(status=report['status'],report_sha256=c.digest(report));return result
 finally:
  supervisor.close();thread=host._thread;host.close();cleanup={'sdk_exited':supervisor.cleanup['process_exited'],'host_thread_stopped':thread is None or not thread.is_alive(),'host_port_closed':old._port_closed(ct['execution']['agent_host']['port'])};ctx.once(folder/'sdk-cleanup.json',cleanup);c.require(all(cleanup.values()),'SDK_CLEANUP')
def verify_sdk(sdk,trace,comps):
 pin=c.pinned_sdk_fields();ready,report=sdk['ready'],sdk['report'];pid=sdk['popen_pid'];c.require(type(pid) is int and pid>0 and ready['pid']==report['pid']==pid and sdk['returncode']==sdk['stderr_bytes']==0 and report['status']=='COMPLETED' and report['guard_denials']==[],'SDK_PROCESS')
 c.require(all(ready[k]==pin[k] for k in ('python_executable_sha256','sdk_site_root_binding_sha256','python_runtime_mapping_sha256')) and ready['sdk_source_sha256']==c.SDK_CORE_SHA256 and ready['openai_source_sha256']==pin['openai_core_sha256'],'SDK_PIN')
 c.require(report['framework']=='pydantic-ai-slim' and report['version']=='2.57.0' and report['openai_version']=='3.35.1' and report['python_executable_sha256']==pin['python_executable_sha256'] and report['sdk_source_sha256']==c.SDK_CORE_SHA256 and report['openai_source_sha256']==pin['openai_core_sha256'],'SDK_REPORT_IDENTITY')
 c.require(report['provider_key_present'] is False and report['business_key_present'] is False and report['final_text_persisted'] is False and report['input_tokens']==report['output_tokens']==0 and report['requests']==len(comps) and report['tool_calls']==report['tool_callbacks']==len(trace),'SDK_ZERO_PROVIDER')
 c.require(all(x['model']=='rpf53-fixture-only' and x['usage']=={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0} for x in comps),'SCRIPTED_SOURCE')
class ConfigPort:
 def validate_contract(self,ctx,ct):c.validate_contract(ct);c.require(ct==ctx.contract(c.DOMAINS[1]),'CONFIG_CONTEXT')
 def execute(self,ctx,ct,ledger):
  self.validate_contract(ctx,ct);h,old=c.helpers();meta=c.strict_json((ctx.root/'preflight/metadata.json').read_bytes());c.require(meta['sources']==c.sources() and old._java_identity()==meta['java'],'PIN_DRIFT');folder=ctx.folder(ct);folder.mkdir(parents=True,exist_ok=False);temp=folder/'java-tmp';temp.mkdir();jar=ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar');c.require(old._sha_file(jar)==c.SOURCE_JAR_SHA256 and jar.stat().st_size==c.SOURCE_JAR_BYTES,'JAR_PIN')
  j=Journal(ledger,ct['experiment']['run_id']);client=Http(ctx,ct,secrets.token_urlsafe(32),j,ledger);host=Host(ct,ConfigLiveBusiness(ct,client),j);jp=ct['execution']['service']['port'];supervisor=c.ProcessSupervisor(ctx,ledger,ct,'jvm');env={'jar_sha256':c.SOURCE_JAR_SHA256,'jar_bytes':c.SOURCE_JAR_BYTES,'java_pid':None,'jar_command_verified':False,'listener_owned':False,'health':[]};log=sdk=None
  try:
   c.require(old._port_closed(jp),'JAVA_PORT');args=[str(old.JAVA),f'-Djava.io.tmpdir={temp}','-jar',str(jar),'--spring.profiles.active=local','--server.address=127.0.0.1',f'--server.port={jp}','--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}','--security.api-keys[0].app='+ct['effect']['app'],'--security.api-keys[0].env='+ct['effect']['env']];proc=supervisor.start(args,old._java_env(temp,client._api_key),folder);env['java_pid']=proc.pid;supervisor.received(status='STARTED');log=old._RedactedJavaLog(proc,client._api_key.encode('ascii'));env['jar_command_verified']=old._argv_jar_path_matches(old._split_windows_command_line(old._actual_process_command_line(proc.pid)),jar,ctx.root);c.require(env['jar_command_verified'],'JAVA_ARGV')
   until=time.monotonic()+150
   while time.monotonic()<until and proc.poll() is None and not log.overflow and not old._listener_owned(proc.pid,jp):time.sleep(.25)
   for _ in range(3):
    ticket=ledger.reserve('health',domain=c.DOMAINS[1],run_id=ct['experiment']['run_id']);item=old._health_get(jp,timeout=5);ledger.settle(ticket,status=item['status'],response_sha256=c.digest(item['body']));env['health'].append(item)
    if item['status']==200 and type(item['body']) is dict and item['body'].get('status')=='UP':break
   env['health']=[{'status':x['status'],'body':{'status':'UP' if type(x['body']) is dict and x['body'].get('status')=='UP' else 'NOT_UP'},'raw_body_sha256':c.digest(x['body']),'transport_error':x['transport_error']} for x in env['health']];c.require(env['health'][-1]['body']=={'status':'UP'},'JAVA_READY');env['listener_owned']=old._listener_owned(proc.pid,jp);c.require(env['listener_owned'] and not old._external_connections(proc.pid) and client.initial_state_valid(),'JAVA_INITIAL')
   sdk=run_sdk(ctx,ct,ledger,meta['sdk'],folder,host);client.stop_writes=True;client.final_readback(reconcile=True);client.request('final_list');c.require(not old._external_connections(proc.pid),'JAVA_NETWORK')
  finally:
   ctx.once(folder/'business-received-before-cleanup.json',{'http':client.observations,'tool_trace':host.tool_trace,'sdk':sdk,'host_failure':host.failure});supervisor.close();host.close()
   if log:log.close(folder/'java-redacted.log')
   client._api_key=None;env['cleanup']={'java_exited':supervisor.cleanup['process_exited'],'java_port_closed':old._port_closed(jp),'sdk_exited':sdk is not None,'host_port_closed':old._port_closed(ct['execution']['agent_host']['port']),'local_key_released':True}
  return {'backend':'REAL_JAVA_H2_HTTP','source_kind':'FIXTURE_SCRIPTED','http':client.observations,'events':j.events,'tool_trace':host.tool_trace,'completions':host.provider_responses,'visibility':host.visible_contract_checks,'sdk':sdk,'environment':env,'original_success':host.original_success,'host_failure':host.failure}
 def verify(self,ctx,ct,e):
  self.validate_contract(ctx,ct);synthetic=ctx.public()['source_kind']=='SYNTHETIC_TEST_ONLY';c.require(e['source_kind']==('SYNTHETIC_TEST_ONLY' if synthetic else 'FIXTURE_SCRIPTED') and e['backend']==('SYNTHETIC_TEST_ONLY' if synthetic else 'REAL_JAVA_H2_HTTP') and e['host_failure'] is None,'CONFIG_SOURCE')
  c.require(set(e)=={'backend','source_kind','http','events','tool_trace','completions','visibility','sdk','environment','original_success','host_failure'},'CONFIG_EVIDENCE_FIELDS')
  trace,comps,http=e['tool_trace'],e['completions'],e['http'];suppressed=ct['experiment']['fault_plan']['enabled'];recovery=len(trace)==4;c.require([t['name'] for t in trace]==list(c.TOOLS)+(['inspect_config'] if recovery else []),'CONFIG_TOOLS');kinds=['initial_current','initial_history','inspect_config','create_config_v1','update_config_v2']+(['inspect_config'] if recovery else [])+['reconcile_current','reconcile_history','final_list'];c.require(len(http)==len(kinds),'HTTP_COUNT')
  for i,(o,kind) in enumerate(zip(http,kinds),1):
   method,path,body=_http_contract(ct['effect'],kind);c.require((o['seq'],o['kind'],o['method'],o['path'],o['request'])==(i,kind,method,path,body),'HTTP_LINEAGE');absent=i in (1,3);listed=kind.endswith('history') or kind=='final_list';ok,data=_api_response(o,404 if absent else 200,4041 if absent else 0,'none' if absent else 'list' if listed else 'item');c.require(ok and o['response_body_sha256']==c.digest(o['response']),'HTTP_AUTHORITY')
   if kind=='initial_history':c.require(data==[],'INITIAL_STATE')
   elif listed:c.require((len(data)==1 and _valid_item(data[0],ct['effect'],2,'rpf53-v2')) if kind=='final_list' else _history(data,ct['effect']),'CONFIG_HISTORY')
   elif not absent:c.require(_valid_item(data,ct['effect'],1 if i==4 else 2,'rpf53-v1' if i==4 else 'rpf53-v2'),'CONFIG_EFFECT')
  c.require(e['original_success']==({'status':'COMMITTED','version':2,'value':'rpf53-v2'} if suppressed else None),'FAULT_COMMIT')
  for i,t in enumerate(trace):
   args=({}, {'value':'rpf53-v1'},{'expected_version':1,'value':'rpf53-v2'}, {})[i];result=({'state':'ABSENT'},{'status':'COMMITTED','version':1,'value':'rpf53-v1'},c.UNKNOWN if suppressed else {'status':'COMMITTED','version':2,'value':'rpf53-v2'},{'state':'PRESENT','version':2,'value':'rpf53-v2'})[i];c.require(t['sequence']==i+1 and t['arguments']==args and t['arguments_sha256']==c.digest(args) and t['result']==result and t['result_sha256']==c.digest(result) and t['http_observation_seq']==i+3 and t['returned_in_request']==i+2,'CONFIG_TOOL_RETURN')
  c.require(len({t['call_id'] for t in trace})==len(trace) and len({x['response_id'] for x in comps})==len(comps),'SDK_LOCAL_ID_REPLAY')
  c.require(len(comps)==len(trace)+1 and len(e['visibility'])==len(comps) and all(x['instructions_present'] and x['task_prompt_present'] and x['tool_help_exact'] for x in e['visibility']),'CONFIG_VISIBILITY')
  for i,comp in enumerate(comps):
   calls=[{'call_id':trace[i]['call_id'],'name':trace[i]['name'],'arguments_sha256':trace[i]['arguments_sha256']}] if i<len(trace) else [];returns=[{'call_id':t['call_id'],'result_sha256':t['result_sha256']} for t in trace[:i]];c.require(comp['tool_calls']==calls and comp['tool_returns']==returns and (not calls or trace[i]['provider_response_id']==comp['response_id']),'SCRIPTED_TOOL_LINEAGE')
  verify_sdk(e['sdk'],trace,comps);env=e['environment'];c.require(env['jar_sha256']==c.SOURCE_JAR_SHA256 and env['jar_bytes']==c.SOURCE_JAR_BYTES and env['listener_owned'] and env['jar_command_verified'] and 1<=len(env['health'])<=3 and env['health'][-1]['body']=={'status':'UP'} and env['health'][-1]['status']==200 and env['health'][-1].get('transport_error') is None and all(env['cleanup'].values()),'CONFIG_ENV_CLEANUP')
  events=e['events'];withheld=[x for x in events if x['kind']=='SUCCESS_WITHHELD'];c.require(len(withheld)==int(suppressed),'FALSE_ACTIVATION')
  if suppressed:c.require(withheld[0]['call_id']==trace[2]['call_id'] and withheld[0]['http_seq']==5 and next(x['seq'] for x in events if x['kind']=='HTTP_COMPLETED' and x['http_seq']==5)<withheld[0]['seq'],'FAULT_POSTCOMMIT_ORDER')
  fault={'planned':ct['experiment']['fault_plan']['planned'],'triggered':suppressed,'observed':suppressed,'agent_exposed':suppressed};return projection(c.DOMAINS[1],e['source_kind'],ct['effect']['authority'],classify('CONTRACT_SATISFIED_IN_RUN',fault,unknown=suppressed,reconciled=True),[c.DOMAINS[1]+'/version2-history2-1',c.DOMAINS[1]+('/postcommit-unknown-scripted-readback' if suppressed else '/no-fault-observed')])
 def cleanup(self,ctx,ct,e):
  _,old=c.helpers();c.require(old._port_closed(ct['execution']['service']['port']) and old._port_closed(ct['execution']['agent_host']['port']),'CONFIG_PORT_CLEANUP');return e['environment']['cleanup']
