"""RPF65 context-injected configuration port; real Host and one shared supervisor."""
import copy, hashlib, secrets, time
from . import pge_r65_context as c
from .pge_domain_port import DomainPort
from .config_live_runtime import ConfigLiveHost, ConfigLiveHttp, ConfigLiveBusiness, ConfigLiveMemoryBackend, ProviderLedger, LiveRuntimeRejected, _http_contract, _api_response, _valid_item
from .config_live_verify import _history

class Journal:
 def __init__(self,ledger,run):self.ledger,self.run,self.events=ledger,run,[]
 def add(self,kind,**data):
  e={'seq':len(self.events)+1,'kind':kind,'run_id':self.run,'monotonic_ns':time.monotonic_ns(),**data}
  self.ledger.append('DOMAIN_EVENT',domain=c.DOMAIN,run_id=self.run,event=e);self.events.append(e);return e

class Http(ConfigLiveHttp):
 def __init__(self,ctx,ct,key,journal,ledger):
  self.contracts,self.effect,self.port=ct,ct['effect'],ct['execution']['service']['port'];self._api_key=key;self.deadline=time.monotonic()+600;self.observations=[];self.post_count=0;self.stop_writes=False;self.ctx,self.journal,self.total=ctx,journal,ledger
 def request(self,kind,*,reconcile=False):
  method,_,_=_http_contract(self.effect,kind);c.require(method!='POST' or not self.stop_writes,'WRITE_AFTER_UNKNOWN');data={'domain':c.DOMAIN,'run_id':self.contracts['experiment']['run_id'],'http_seq':len(self.observations)+1,'operation':kind,'method':method};ticket=self.total.reserve('http',**data);post=self.total.reserve('post',**data) if method=='POST' else None
  self.journal.add('HTTP_RESERVED',**{k:data[k] for k in ('http_seq','operation','method')});o=super().request(kind,reconcile=reconcile);self.total.settle(ticket,status=o['status'],response_sha256=o['response_body_sha256'],transport_error=o['transport_error'])
  if post:self.total.settle(post,status=o['status'],unknown=o['status']!=200 or o['transport_error'] is not None)
  self.journal.add('HTTP_COMPLETED',http_seq=o['seq'],status=o['status'],response_sha256=o['response_body_sha256']);return o

class BrokerLedger:
    """Ephemeral SDK index; every state is fsynced in the one session WAL."""
    def __init__(self,total,run_id):self.total,self.run_id,self.data,self.previous_body=total,run_id,{'requests':[]},None
    def checkpoint(self):self.total.append('PROVIDER_STATE',role='TARGET',run_id=self.run_id,requests=self.data['requests'])
    def reserve(self,body,returns):
        records=self.data['requests'];c.require(all(r['status']=='RECEIVED' for r in records) and len(records)<6,'UNKNOWN_USAGE_OR_TARGET_LIMIT')
        messages=body['messages'];prior=self.previous_body
        if prior is None:input_upper=len(c.canonical(body));proof={'kind':'FULL_SERIALIZED_BYTES','body_bytes':input_upper}
        else:
            pm=prior['messages'];c.require(messages[:len(pm)]==pm and all(body[k]==prior[k] for k in body if k!='messages'),'INPUT_PREFIX_CHANGED')
            extra=len(c.canonical(messages[len(pm):]));input_upper=records[-1]['usage']['prompt_tokens']+extra+512
            proof={'kind':'UNCHANGED_PREFIX_USAGE_PLUS_SUFFIX_BYTES_PLUS_512','previous_request_sha256':c.digest(prior),'prefix_sha256':c.digest(pm),'suffix_bytes':extra,'previous_prompt_tokens':records[-1]['usage']['prompt_tokens'],'framing_guard':512}
        cap=c.CAPS[len(records)];c.require(input_upper+256<=cap,'REQUEST_INPUT_BOUND')
        ticket=self.total.reserve('provider',role='TARGET',run_id=self.run_id,request_sha256=c.digest(body),token_upper=cap,input_upper=input_upper,output_cap=256,proof=proof,cost_micro_cny_upper=input_upper*4.5+256*18)
        record={'attempt':len(records)+1,'run_id':self.run_id,'role':'TARGET','ticket':ticket,'request_sha256':c.digest(body),'token_upper':cap,'input_upper':input_upper,'proof':proof,'status':'RESERVED_USAGE_UNKNOWN','usage':None,'response_id':None,'returned_model':None,'tool_returns':returns,'failure_code':None,'started_monotonic_ns':time.monotonic_ns()}
        records.append(record);self.previous_body=copy.deepcopy(body);self.checkpoint();return record
    def received(self,record,data):
        u={k:data['usage'].get(k) for k in ('prompt_tokens','completion_tokens','total_tokens')};ProviderLedger._validate_usage(u,record['token_upper'])
        c.require(u['prompt_tokens']<=record['input_upper'] and u['completion_tokens']<=256,'REPORTED_USAGE_BOUND')
        c.require(data['model'] in c.MODELS,'MODEL')
        record.update(status='RECEIVED',usage=u,response_id=data['id'],returned_model=data['model']);self.checkpoint();self.total.settle(record['ticket'],usage=u,response_id=data['id'],status='RECEIVED')
    def fail_unknown(self,record,code):
        record['failure_code']=code;self.checkpoint();self.total.settle(record['ticket'],status='UNKNOWN',unknown=True)

class Host(ConfigLiveHost):
    def __init__(self,contracts,ledger,business,journal,*,fixture=False,api_key=None):
        c.validate_contract(contracts);c.require(fixture==(contracts['execution']['model_source']=='FIXTURE_SCRIPTED'),'HOST_ROLE')
        self.contracts,self.ledger,self.business,self.journal=contracts,ledger,business,journal
        self.fixture,self.api_key,self.expected_tool_schema_sha256,self.fixture_failure_code=fixture,api_key,None,None
        self.tool_schema_sha256=self.tool_schema_summary=self.tool_definitions=self.runtime=self.failure=None
        self.intents,self.tool_returns={},{};self.tool_trace,self.tool_rejections,self.visible_contract_checks,self.provider_responses=[],[],[],[]
        self._server=self._thread=None;self.fixture_index=0;self.request_started=time.monotonic();self.activated=False;self.original_success=None
    def start(self,bind_port=None):return super().start(bind_port or self.contracts['execution']['agent_host']['port'])
    def _tool(self,body):
        c.require(type(body) is dict and body.get('name') in c.TOOLS,'TOOL_CAPABILITY')
        phase=len(self.tool_trace);expected=list(c.TOOLS)+['inspect_config']

        if not (phase<len(expected) and body['name']==expected[phase]):
            self.tool_rejections.append({'call_id':body.get('call_id'),'name':body['name'],'arguments_sha256':c.digest(body.get('arguments')),'provider_response_id':self.intents.get(body.get('call_id'),{}).get('response_id'),'reason':'PHASE_OR_WRITE_AFTER_UNKNOWN'});self.journal.add('TOOL_REJECTED',**self.tool_rejections[-1]);raise LiveRuntimeRejected('PHASE_OR_WRITE_AFTER_UNKNOWN','AGENT')
        self.journal.add('TOOL_RESERVED',call_id=body.get('call_id'),name=body['name'])
        result=super()._tool(body);item=self.tool_trace[-1]
        self.journal.add('TOOL_RESULT_READY',call_id=item['call_id'],name=item['name'],result_sha256=c.digest(result))
        if body['name']=='update_config_v2' and self.contracts['experiment']['fault_plan']['enabled']:
            c.require(not self.activated and result=={'status':'COMMITTED','version':2,'value':'rpf53-v2'},'SUPPRESSION_PRECONDITION')
            if isinstance(self.business,ConfigLiveBusiness):
                observation=self.business.client.observations[-1];ok,data=_api_response(observation,200,0,'item')
                c.require(ok and observation['kind']=='update_config_v2' and _valid_item(data,self.contracts['effect'],2,'rpf53-v2'),'COMMITTED_HTTP_REQUIRED')
                self.business.client.stop_writes=True
            self.activated=True;self.original_success=copy.deepcopy(result)
            item.update(result=copy.deepcopy(c.UNKNOWN),result_sha256=c.digest(c.UNKNOWN))
            self.journal.add('SUCCESS_WITHHELD',call_id=item['call_id'],http_seq=item['http_observation_seq'],committed_result_sha256=c.digest(result))
            self.journal.add('UNKNOWN_TOOL_RESULT_RELEASED',call_id=item['call_id'],result_sha256=item['result_sha256'])
            return item['result']
        self.journal.add('READ_ONLY_MODEL_RECOVERY' if self.activated else 'SUCCESS_RELEASED',call_id=item['call_id'],http_seq=item['http_observation_seq'])
        return result
    def _ready(self,body):
        c.require(not hasattr(self,'expected_pid') or body.get('pid')==self.expected_pid,'CHILD_PID_BINDING');return super()._ready(body)
    def _completion(self,body):
        if isinstance(self.business,ConfigLiveBusiness):c.require(not self.business.client.stop_writes or self.activated,'BUSINESS_UNKNOWN_STOP_MODEL')
        # Parent contract visibility remains checked by the frozen transport.
        visible=c.RECOVERY in str(body.get('messages'))
        c.require(visible,'CAPABILITY_RECOVERY_POLICY_VISIBLE')
        self.journal.add('CAPABILITY_INPUT_FROZEN',messages_sha256=c.digest(body.get('messages')),recovery_policy_visible=visible)
        if self.activated:self.journal.add('MODEL_UNKNOWN_INPUT_FROZEN',messages_sha256=c.digest(body.get('messages')))
        result=super()._completion(body)
        if self.activated:
            self.journal.add('MODEL_UNKNOWN_INPUT_ACCEPTED',request_sha256=self.provider_responses[-1]['request_sha256'],response_id=self.provider_responses[-1]['response_id'])
        return result
    def _provider_request(self,body):
        data=super()._provider_request(body)
        calls=data.get('choices',[{}])[0].get('message',{}).get('tool_calls',[])
        c.require(calls is None or type(calls) is list and len(calls)<=1,'MULTIPLE_TARGET_TOOLS_REJECTED')
        return data
    def _fixture_response(self,request):
        if self.fixture_index!=3 or not self.contracts['experiment']['fault_plan']['enabled']:return super()._fixture_response(request)
        data=super()._fixture_response(request)
        data['choices'][0].update(finish_reason='tool_calls',message={'role':'assistant','content':None,'tool_calls':[{'id':'call_rpf65_fixture_reconcile','type':'function','function':{'name':'inspect_config','arguments':'{}'}}]})
        return data

def run_sdk(ctx,ct,ledger,sdk,folder,host,*,cold=False):
 h,old=c.helpers();scratch=ctx.scope(folder/'sdk-scratch');scratch.mkdir();direct=h.resolve_direct_python(sdk);supervisor=c.ProcessSupervisor(ctx,ledger,ct,'cold' if cold else 'sdk');result=None
 try:
  host.start(ct['execution']['agent_host']['port']);cfg={'port':host.port,'token':host.token,'write_root':str(scratch),'sdk_readonly_path':str(old.SDK_SITE.resolve()),'sdk_site_root_binding_sha256':sdk['sdk_site_root_binding_sha256'],'python_runtime_mapping_sha256':sdk['python_runtime_mapping_sha256'],'instructions':ct['execution']['agent_instructions'],'task_prompt':ct['execution']['task_prompt'],'model':'rpf53-fixture-only' if cold else c.MODEL,'max_runtime_seconds':180,'fixture':cold}
  proc=supervisor.start([str(direct),'-I','-B',str(c.ROOT/'runtime/runproof_runtime/effectwitness/config_live_external.py')],old._sdk_env(scratch),scratch,stdio=True);host.expected_pid=proc.pid;stdout,stderr=proc.communicate(c.canonical(cfg),timeout=180)
  parsed=c.strict_json(stdout);allowed={'status','framework','version','openai_version','pid','python_executable_sha256','usage_type','usage_fields','requests','input_tokens','output_tokens','tool_calls','tool_callbacks','sdk_source_sha256','openai_source_sha256','final_output_sha256','final_text_persisted','guard_denials','provider_key_present','business_key_present','stage','error_type','guard_code','denied_files'};c.require(type(parsed) is dict and set(parsed)<=allowed,'SDK_REPORT_FIELDS');report={k:v for k,v in parsed.items() if k!='denied_files'}
  result={'popen_pid':proc.pid,'ready':host.runtime,'report':report,'returncode':proc.returncode,'stderr_bytes':len(stderr)};ctx.once(folder/'sdk-received-before-cleanup.json',{'sdk':result,'tool_trace':host.tool_trace,'completions':host.provider_responses,'events':host.journal.events});supervisor.received(status=report['status'],report_sha256=c.digest(report));return result
 except Exception as exc:
  ctx.once(folder/'sdk-failure.json',{'error_type':type(exc).__name__,'code':getattr(exc,'code','SDK_UNAVAILABLE'),'ready':host.runtime});raise
 finally:
  supervisor.close();thread=host._thread;host.close();cleanup={'sdk_exited':supervisor.cleanup['process_exited'],'host_thread_stopped':thread is None or not thread.is_alive(),'host_port_closed':old._port_closed(ct['execution']['agent_host']['port'])};ctx.once(folder/'sdk-cleanup.json',cleanup);c.require(all(cleanup.values()),'SDK_CLEANUP')

def assemble_host(ctx, ct, ledger, *, api_key=None):
 """Production factory, also exercised without credentials/processes/network."""
 c.validate_contract(ct)
 c.require(ct==ctx.contract() and ledger.context is ctx,'FACTORY_CONTEXT_LEDGER')
 journal=Journal(ledger,ct['experiment']['run_id'])
 client=Http(ctx,ct,secrets.token_urlsafe(32),journal,ledger)
 broker=BrokerLedger(ledger,ct['experiment']['run_id'])
 business=ConfigLiveBusiness(ct,client)
 host=Host(ct,broker,business,journal,fixture=False,api_key=api_key)
 c.require(host.ledger is broker and broker.total is ledger and host.business is business and business.client is client and host.journal is journal and journal.ledger is ledger,'FACTORY_INJECTION')
 return client,broker,host,journal

class ConfigPort:
 def __init__(self,api_key=None): self.api_key=api_key
 def validate_contract(self,ctx,ct): c.validate_contract(ct); c.require(ct==ctx.contract() and ctx.public()['source_kind'] in (c.REAL,c.SYNTHETIC),'CONFIG_CONTEXT')
 def execute(self,ctx,ct,ledger):
  self.validate_contract(ctx,ct)
  client,broker,host,j=assemble_host(ctx,ct,ledger,api_key=self.api_key)
  folder=ctx.folder(ct); jp=ct['execution']['service']['port']
  supervisor=c.ProcessSupervisor(ctx,ledger,ct,'jvm')
  env={'source_level':'REAL_JAVA_H2_LOCAL_SIMULATION','authority':'SAME_SERVICE_READ_ONLY_HTTP','jar_sha256':c.SOURCE_JAR_SHA256,'jar_bytes':c.SOURCE_JAR_BYTES,'java_pid':None,'jar_command_verified':False,'listener_owned':False,'health':[]}
  log=sdk=old=None; initial_ok=False
  try:
   h,old=c.helpers();meta=c.strict_json((ctx.root/'preflight/metadata.json').read_bytes());c.require(meta['sources']==c.sources() and old._java_identity()==meta['java'],'PIN_DRIFT')
   folder.mkdir(parents=True,exist_ok=False);temp=folder/'java-tmp';temp.mkdir();jar=ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar');c.require(old._sha_file(jar)==c.SOURCE_JAR_SHA256 and jar.stat().st_size==c.SOURCE_JAR_BYTES,'JAR_PIN')
   c.require(old._port_closed(jp),'JAVA_PORT');args=[str(old.JAVA),f'-Djava.io.tmpdir={temp}','-jar',str(jar),'--spring.profiles.active=local','--server.address=127.0.0.1',f'--server.port={jp}','--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}','--security.api-keys[0].app='+ct['effect']['app'],'--security.api-keys[0].env='+ct['effect']['env']];proc=supervisor.start(args,old._java_env(temp,client._api_key),folder);env['java_pid']=proc.pid;supervisor.received(status='STARTED');log=old._RedactedJavaLog(proc,client._api_key.encode('ascii'));env['jar_command_verified']=old._argv_jar_path_matches(old._split_windows_command_line(old._actual_process_command_line(proc.pid)),jar,ctx.root);c.require(env['jar_command_verified'],'JAVA_ARGV')
   until=time.monotonic()+150
   while time.monotonic()<until and proc.poll() is None and not log.overflow and not old._listener_owned(proc.pid,jp):time.sleep(.25)
   for _ in range(3):
    ticket=ledger.reserve('health',domain=c.DOMAIN,run_id=ct['experiment']['run_id']);item=old._health_get(jp,timeout=5);ledger.settle(ticket,status=item['status'],response_sha256=c.digest(item['body']));env['health'].append(item)
    if item['status']==200 and type(item['body']) is dict and item['body'].get('status')=='UP':break
   env['health']=[{'status':x['status'],'body':{'status':'UP' if type(x['body']) is dict and x['body'].get('status')=='UP' else 'NOT_UP'},'raw_body_sha256':c.digest(x['body']),'transport_error':x['transport_error']} for x in env['health']];c.require(env['health'][-1]['body']=={'status':'UP'},'JAVA_READY');env['listener_owned']=old._listener_owned(proc.pid,jp);c.require(env['listener_owned'] and not old._external_connections(proc.pid) and client.initial_state_valid(),'JAVA_INITIAL')
   initial_ok=True
   sdk=run_sdk(ctx,ct,ledger,meta['sdk'],folder,host)
  finally:
   client.stop_writes=True
   try:
    if initial_ok:
     client.final_readback(reconcile=True);client.request('final_list');c.require(not old._external_connections(supervisor.proc.pid),'JAVA_NETWORK')
   finally:
    # A failure in receipt creation or readback must still close owned children.
    try:ctx.once(folder/'business-received-before-cleanup.json',{'http':client.observations,'tool_trace':host.tool_trace,'sdk':sdk,'host_failure':host.failure})
    finally:
     try:supervisor.close()
     finally:
      thread=host._thread
      try:host.close()
      finally:
       client._api_key=None;host.api_key=None;self.api_key=None
       if log:log.close(folder/'java-redacted.log')
       env['cleanup']={'java_exited':supervisor.cleanup is not None and supervisor.cleanup['process_exited'],'java_port_closed':old is not None and old._port_closed(jp),'sdk_exited':sdk is not None,'host_port_closed':old is not None and old._port_closed(ct['execution']['agent_host']['port']),'local_key_released':True,'host_thread_stopped':thread is None or not thread.is_alive()}
       ctx.once(folder/'environment-cleanup.json',env)
  scene={'contracts':ct,'requests':broker.data['requests'],'tool_rejections':host.tool_rejections,'http':client.observations,'events':j.events,'tool_trace':host.tool_trace,'completions':host.provider_responses,'visibility':host.visible_contract_checks,'sdk':sdk,'environment':env,'original_success':host.original_success,'host_failure':host.failure}
  ctx.once(folder/'scene-capture.json',scene)
  return scene
 def verify(self,ctx,ct,e):
  from .pge_r65_verify import verify_scene
  self.validate_contract(ctx,ct); return verify_scene(ct,e,real=ctx.public()['source_kind']==c.REAL)
 def cleanup(self,ctx,ct,e):
  _,old=c.helpers();c.require(old._port_closed(ct['execution']['service']['port']) and old._port_closed(ct['execution']['agent_host']['port']),'CONFIG_PORT_CLEANUP');return e['environment']['cleanup']
