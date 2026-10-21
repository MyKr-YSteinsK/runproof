"""RPF-62 config capability bridge. Reuses frozen SDK/HTTP transport, not old runners."""
from __future__ import annotations
import ast
import copy
import hashlib
import importlib.util
import os
import secrets
import shutil
import subprocess
import time
from . import pge_target_capability as c
from .config_live_runtime import (ConfigLiveHost,ConfigLiveBusiness,ConfigLiveMemoryBackend,ConfigLiveHttp,ProviderLedger,LiveRuntimeRejected,_api_response,_valid_item,_http_contract)
spec=importlib.util.spec_from_file_location('rpf62_fixed_helpers',c.ROOT/'spikes/rpf-55/probe.py')
h55=importlib.util.module_from_spec(spec);spec.loader.exec_module(h55);old=h55.old
JAR=c.WORK/'jar/config-center-server-1.0.0.jar'
class Journal:
    def __init__(self,ledger,run_id):self.ledger,self.run_id,self.events=ledger,run_id,[]
    def add(self,kind,**data):
        e={'seq':len(self.events)+1,'run_id':self.run_id,'kind':kind,'monotonic_ns':time.monotonic_ns(),**data}
        if self.ledger:self.ledger.append('DOMAIN_EVENT',event=e)
        self.events.append(e);return e
class BrokerLedger:
    """Memory is an index only; every transition fsyncs in the single task WAL."""
    def __init__(self,ledger,run_id):self.total,self.run_id=ledger,run_id;self.data={'requests':[]}
    def checkpoint(self):self.total.append('PROVIDER_STATE',run_id=self.run_id,requests=self.data['requests'])
    def reserve(self,body,returns):
        records=self.data['requests'];c.require(all(r['status']=='RECEIVED' for r in records),'UNKNOWN_USAGE_STOP')
        used=sum(r['usage']['total_tokens'] for r in records)
        upper=len(c.canonical(body))+256
        c.require(upper<=12000-used,'REQUEST_TOKEN_UPPER_BOUND')
        ticket=self.total.reserve('provider',run_id=self.run_id,request_sha256=c.digest(body),token_upper=upper)
        record={'attempt':len(records)+1,'run_id':self.run_id,'ticket':ticket,'request_sha256':c.digest(body),'token_upper':upper,
            'status':'RESERVED_USAGE_UNKNOWN','usage':None,'response_id':None,'returned_model':None,'tool_returns':returns,
            'failure_code':None,'started_monotonic_ns':time.monotonic_ns()}
        records.append(record);self.checkpoint();return record
    def received(self,record,data):
        u={k:data['usage'].get(k) for k in ('prompt_tokens','completion_tokens','total_tokens')}
        ProviderLedger._validate_usage(u,record['token_upper']);c.require(u['completion_tokens']<=256,'OUTPUT_LIMIT')
        c.require(sum(r['usage']['total_tokens'] for r in self.data['requests'] if r['usage'])+u['total_tokens']<=12000,'TOKEN_LIMIT')
        record.update(status='RECEIVED',usage=u,response_id=data['id'],returned_model=data['model']);self.checkpoint()
        self.total.settle(record['ticket'],usage=u,response_id=data['id'],status='RECEIVED')
    def fail_unknown(self,record,code):record['failure_code']=code;self.checkpoint()
class BusinessHttp(ConfigLiveHttp):
    def __init__(self,contracts,key,journal,total,deadline):
        c.validate_contract(contracts);self.contracts,self.effect,self.port=contracts,contracts['effect'],contracts['execution']['service']['port']
        self._api_key,self.journal,self.total,self.deadline=key,journal,total,deadline
        self.observations,self.post_count,self.stop_writes=[],0,False
    def request(self,kind,*,reconcile=False):
        method,_,_= _http_contract(self.effect,kind)
        c.require(method!='POST' or not self.stop_writes,'WRITE_AFTER_UNKNOWN')
        ticket=self.total.reserve('http',run_id=self.contracts['experiment']['run_id'],http_seq=len(self.observations)+1,operation=kind,method=method)
        if method=='POST':self.total.reserve('post',operation=kind,run_id=self.contracts['experiment']['run_id'])
        self.journal.add('HTTP_RESERVED',http_seq=len(self.observations)+1,method=method,operation=kind)
        result=super().request(kind,reconcile=reconcile)
        self.total.settle(ticket,status=result['status'],response_sha256=result['response_body_sha256'],transport_error=result['transport_error'])
        self.journal.add('HTTP_COMPLETED',http_seq=result['seq'],status=result['status'],response_sha256=result['response_body_sha256'])
        return result
class CapabilityHost(ConfigLiveHost):
    def __init__(self,contracts,ledger,business,journal,*,fixture=False,api_key=None):
        c.validate_contract(contracts);c.require(fixture==(contracts['execution']['model_source']=='FIXTURE_SCRIPTED'),'HOST_ROLE')
        self.contracts,self.ledger,self.business,self.journal=contracts,ledger,business,journal
        self.fixture,self.api_key,self.expected_tool_schema_sha256,self.fixture_failure_code=fixture,api_key,None,None
        self.tool_schema_sha256=self.tool_schema_summary=self.tool_definitions=self.runtime=self.failure=None
        self.intents,self.tool_returns={},{};self.tool_trace,self.tool_rejections,self.visible_contract_checks,self.provider_responses=[],[],[],[]
        self._server=self._thread=None;self.fixture_index=0;self.request_started=time.monotonic();self.activated=False;self.original_success=None
        journal.add('PRE_REGISTERED',capability_sha256=c.digest(contracts['capability']))
    def start(self,bind_port=None):return super().start(bind_port or self.contracts['execution']['agent_host']['port'])
    def _tool(self,body):
        c.require(type(body) is dict and body.get('name') in c.TOOLS,'TOOL_CAPABILITY')
        phase=len(self.tool_trace);expected=list(c.TOOLS)+['inspect_config']
        c.require(phase<len(expected) and body['name']==expected[phase],'TOOL_PHASE_OR_WRITE_AFTER_UNKNOWN')
        self.journal.add('TOOL_RESERVED',call_id=body.get('call_id'),name=body['name'])
        result=super()._tool(body);item=self.tool_trace[-1]
        self.journal.add('TOOL_RESULT_READY',call_id=item['call_id'],name=item['name'],result_sha256=c.digest(result))
        if body['name']=='update_config_v2':
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
    def _completion(self,body):
        # Parent contract visibility remains checked by the frozen transport.
        visible=c.RECOVERY_INSTRUCTIONS in str(body.get('messages'))
        c.require(visible,'CAPABILITY_RECOVERY_POLICY_VISIBLE')
        self.journal.add('CAPABILITY_INPUT_FROZEN',messages_sha256=c.digest(body.get('messages')),recovery_policy_visible=visible)
        if self.activated:self.journal.add('MODEL_UNKNOWN_INPUT_FROZEN',messages_sha256=c.digest(body.get('messages')))
        result=super()._completion(body)
        if self.activated:
            self.journal.add('MODEL_UNKNOWN_INPUT_ACCEPTED',request_sha256=self.provider_responses[-1]['request_sha256'],response_id=self.provider_responses[-1]['response_id'])
        return result
    def _fixture_response(self,request):
        if self.fixture_index!=3:return super()._fixture_response(request)
        data=super()._fixture_response(request)
        data['choices'][0].update(finish_reason='tool_calls',message={'role':'assistant','content':None,'tool_calls':[{'id':'call_rpf62_fixture_reconcile','type':'function','function':{'name':'inspect_config','arguments':'{}'}}]})
        return data
class ConfigTargetDriver:
    def run(self,capability,context):
        c.validate_capability(capability)
        c.require(set(context)=={'contracts','host','ledger','sdk','folder','fixture'} and type(context['host']) is CapabilityHost and context['contracts']['capability']==capability,'STATIC_DRIVER_CONTEXT')
        return run_sdk(**context)
def sdk_identity_direct():
    """Reviewed metadata-only inspector copied for the new owner/cwd."""
    pinned=c.pinned_sdk_fields();direct=h55.resolve_direct_python(pinned)
    tree=ast.parse((c.ROOT/'spikes/rpf-53/probe.py').read_text(encoding='utf-8'))
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_sdk_identity')
    assignment=next(n for n in function.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='script' for t in n.targets))
    script=ast.literal_eval(assignment.value).replace('base=pathlib.Path(sys.prefix,"Lib","site-packages").resolve(strict=True)','base=pathlib.Path(sys.argv[1]).resolve(strict=True); sys.path.insert(0,str(base))').replace('venv_root=pathlib.Path(sys.prefix).resolve(strict=True)','venv_root=base.parent.parent')
    result=subprocess.run([str(direct),'-I','-B','-X','utf8','-c',script,str(old.SDK_SITE.resolve(strict=True)),str(direct.resolve(strict=True))],cwd=c.WORK/'diagnostics',env=old._sdk_env(c.WORK/'diagnostics'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    c.require(result.returncode==0 and not result.stderr,'DIRECT_RECORD_INSPECTION')
    value=c.strict_json(result.stdout);value['python_launcher_sha256']=old._sha_file(old.SDK_LAUNCHER);value.pop('base_executable_sha256',None)
    c.require(h55.identity_fields(value)==pinned and value['pydantic']['record_hashed_entries']==443 and value['openai']['record_hashed_entries']==1999,'SDK_PIN')
    return value
def run_sdk(contracts,host,ledger,sdk,folder,fixture):
    folder=c.scoped(folder);scratch=folder/'sdk-scratch';scratch.mkdir();direct=h55.resolve_direct_python(sdk)
    ticket=ledger.reserve('cold' if fixture else 'sdk',run_id=contracts['experiment']['run_id'])
    proc=None;thread=None
    try:
        host.start()
        cfg={'port':host.port,'token':host.token,'write_root':str(scratch),'sdk_readonly_path':str(old.SDK_SITE.resolve()),
            'sdk_site_root_binding_sha256':sdk['sdk_site_root_binding_sha256'],'python_runtime_mapping_sha256':sdk['python_runtime_mapping_sha256'],
            'instructions':contracts['execution']['agent_instructions'],'task_prompt':contracts['execution']['task_prompt'],'model':'rpf53-fixture-only' if fixture else c.MODEL,'max_runtime_seconds':180,'fixture':fixture}
        proc=subprocess.Popen([str(direct),'-I','-B',str(c.ROOT/'runtime/runproof_runtime/effectwitness/config_live_external.py')],cwd=scratch,env=old._sdk_env(scratch),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        c.once(folder/'sdk-started.json',{'popen_pid':proc.pid,'sources':c.sources()})
        stdout,stderr=proc.communicate(c.canonical(cfg),timeout=180)
        try:
            parsed=c.strict_json(stdout);allowed={'status','framework','version','openai_version','pid','python_executable_sha256','usage_type','usage_fields','requests','input_tokens','output_tokens','tool_calls','tool_callbacks','sdk_source_sha256','openai_source_sha256','final_output_sha256','final_text_persisted','guard_denials','provider_key_present','business_key_present','stage','error_type','guard_code','denied_files'}
            c.require(type(parsed) is dict and set(parsed)<=allowed,'REPORT_FIELDS');report={k:v for k,v in parsed.items() if k!='denied_files'}
        except Exception:report={'status':'REPORT_UNAVAILABLE','raw_sha256':hashlib.sha256(stdout).hexdigest()}
        result={'popen_pid':proc.pid,'ready':host.runtime,'report':report,'returncode':proc.returncode,'stderr_bytes':len(stderr)}
        c.once(folder/'sdk-received.json',{'sdk':result,'tool_trace':host.tool_trace,'completions':host.provider_responses,'events':host.journal.events})
        ledger.settle(ticket,popen_pid=proc.pid,status=report['status']);return result
    except Exception as exc:
        c.once(folder/'sdk-failure.json',{'error_type':type(exc).__name__,'winerror':getattr(exc,'winerror',None),'popen_pid':proc.pid if proc else None,'ready':host.runtime,'events':host.journal.events})
        raise
    finally:
        if proc is not None and proc.poll() is None:proc.kill();proc.communicate(timeout=10)
        thread=host._thread;host.close()
        cleanup={'sdk_exited':proc is not None and proc.poll() is not None,'host_thread_stopped':thread is None or not thread.is_alive(),'host_port_closed':old._port_closed(contracts['execution']['agent_host']['port'])}
        c.once(folder/'sdk-cleanup.json',cleanup);c.require(all(cleanup.values()),'SDK_CLEANUP')
def health_ready(proc,port,log,deadline,ledger):
    until=min(deadline,time.monotonic()+150)
    while time.monotonic()<until:
        if proc.poll() is not None or log.overflow:return []
        if old._listener_owned(proc.pid,port):break
        time.sleep(.25)
    health=[]
    for _ in range(3):
        ticket=ledger.reserve('health');item=old._health_get(port,timeout=min(5,max(.1,deadline-time.monotonic())))
        ledger.settle(ticket,status=item['status'],response_sha256=c.digest(item['body']))
        health.append(item)
        if item['status']==200 and item['transport_error'] is None and type(item['body']) is dict and item['body'].get('status')=='UP':return h55.health_projection(health)
    return []
def execute(contracts,sdk,total,key):
    c.validate_contract(contracts);folder=c.WORK/'scene';folder.mkdir();total.reserve('trial',run_id=contracts['experiment']['run_id'])
    c.once(folder/'started.json',{'contracts':contracts,'sources':c.sources()})
    journal=Journal(total,contracts['experiment']['run_id']);deadline=time.monotonic()+1200
    client=BusinessHttp(contracts,secrets.token_urlsafe(32),journal,total,deadline);broker=BrokerLedger(total,journal.run_id)
    host=CapabilityHost(contracts,broker,ConfigLiveBusiness(contracts,client),journal,api_key=key)
    port=contracts['execution']['service']['port'];temp=folder/'java-tmp';temp.mkdir()
    args=[str(old.JAVA),f'-Djava.io.tmpdir={temp}','-jar',str(JAR),'--spring.profiles.active=local','--server.address=127.0.0.1',f'--server.port={port}','--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}','--security.api-keys[0].app='+contracts['effect']['app'],'--security.api-keys[0].env='+contracts['effect']['env']]
    environment={'source_level':'REAL_JAVA_H2_LOCAL_SIMULATION','authority':'SAME_SERVICE_READ_ONLY_HTTP','java_pid':None,'jar_sha256':old._sha_file(JAR),'jar_bytes':JAR.stat().st_size,'listener_owned':False,'jar_command_verified':False,'health':[],'cleanup':{}}
    proc=log=sdk_result=None
    try:
        c.require(environment['jar_sha256']==c.SOURCE_JAR_SHA256 and old._port_closed(port),'JAVA_SOURCE_PORT')
        ticket=total.reserve('jvm');proc=subprocess.Popen(args,cwd=folder,env=old._java_env(temp,client._api_key),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
        environment['java_pid']=proc.pid;total.settle(ticket,popen_pid=proc.pid)
        log=old._RedactedJavaLog(proc,client._api_key.encode('ascii'));argv=old._split_windows_command_line(old._actual_process_command_line(proc.pid))
        environment['jar_command_verified']=old._argv_jar_path_matches(argv,JAR,c.WORK);c.require(environment['jar_command_verified'],'JAVA_ARGV')
        environment['health']=health_ready(proc,port,log,deadline,total);c.require(bool(environment['health']),'JAVA_READY')
        environment['listener_owned']=old._listener_owned(proc.pid,port);c.require(environment['listener_owned'] and not old._external_connections(proc.pid),'JAVA_NETWORK')
        c.require(client.initial_state_valid(),'INITIAL_STATE')
        sdk_result=ConfigTargetDriver().run(contracts['capability'],{'contracts':contracts,'host':host,'ledger':total,'sdk':sdk,'folder':folder,'fixture':False})
        client.stop_writes=True
        client.final_readback(reconcile=True);client.request('final_list')
        c.require(not old._external_connections(proc.pid),'JAVA_EXTERNAL')
    finally:
        thread=host._thread;host.close()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if log:log.close(folder/'java-redacted.log')
        client._api_key=None;host.api_key=None
        environment['cleanup']={'java_exited':proc is not None and proc.poll() is not None,'java_port_closed':old._port_closed(port),'sdk_exited':sdk_result is not None,'host_port_closed':old._port_closed(contracts['execution']['agent_host']['port']),'host_thread_stopped':thread is None or not thread.is_alive(),'local_key_released':True}
        c.once(folder/'capture.json',{'contracts':contracts,'http':client.observations,'events':journal.events,'tool_trace':host.tool_trace,'completions':host.provider_responses,'visibility':host.visible_contract_checks,'sdk':sdk_result,'environment':environment,'requests':broker.data['requests'],'original_success':host.original_success,'host_failure':host.failure})
    return c.strict_json((folder/'capture.json').read_bytes())
