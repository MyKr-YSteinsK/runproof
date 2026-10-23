"""RPF68 config capability: unchanged bounded HTTP/business methods, owned Java/H2."""
import secrets,time,subprocess
from . import pge_r68_context as c
from .pge_r68_driver import Port
from .config_live_runtime import ConfigLiveHttp,ConfigLiveBusiness,_http_contract,_api_response,_valid_item
from .config_live_verify import _history
class Http(ConfigLiveHttp):
 def __init__(self,ct,key,ledger):
  self.contracts=ct;self.effect=ct['effect'];self.port=ct['execution']['service_port'];self._api_key=key;self.deadline=time.monotonic()+1200;self.observations=[];self.post_count=0;self.stop_writes=False;self.ledger=ledger
 def request(self,kind,*,reconcile=False):
  method,_,_= _http_contract(self.effect,kind);post=None;t=self.ledger.reserve('config_http',domain=c.DOMAINS[0],round=1,method=method,operation=kind)
  if method=='POST':post=self.ledger.reserve('config_post',domain=c.DOMAINS[0],round=1,operation=kind)
  result=super().request(kind,reconcile=reconcile);self.ledger.settle(t,status='RECEIVED',observation=result)
  if post:self.ledger.settle(post,status='COMMITTED' if result['status']==200 and not result['transport_error'] else 'UNKNOWN',observation_sha256=c.digest(result))
  return result
class ConfigPort(Port):
 domain=c.DOMAINS[0]
 def prepare(self,ctx,ct,ledger):
  self.prepare_common(ctx,ct,ledger);self.proc=None;self.log=None;self.client=None;self.java_ticket=None;self.environment={};self.folder=ctx.folder(ct);self.folder.mkdir(parents=True);temp=ctx.scope(self.folder/'java-tmp');temp.mkdir();_,self.old=c.helpers();self.jp=ct['execution']['service_port'];jar=ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar');c.require(c.sha(jar.read_bytes())==c.SOURCE_JAR_SHA256 and jar.stat().st_size==c.SOURCE_JAR_BYTES,'JAR_PIN');c.require(self.old._port_closed(self.jp),'JAVA_PORT')
  key=secrets.token_urlsafe(32);self.client=Http(ct,key,ledger);self.business_api=ConfigLiveBusiness(ct,self.client)
  args=[str(self.old.JAVA),'-Djava.io.tmpdir='+str(temp),'-jar',str(jar),'--spring.profiles.active=local','--server.address=127.0.0.1','--server.port='+str(self.jp),'--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}','--security.api-keys[0].app='+ct['effect']['app'],'--security.api-keys[0].env='+ct['effect']['env']]
  self.java_ticket=ledger.reserve('jvm',domain=self.domain,round=1);self.proc=subprocess.Popen(args,cwd=self.folder,env=self.old._java_env(temp,key),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);self.log=self.old._RedactedJavaLog(self.proc,key.encode());key=None;ledger.append('PROCESS_START',domain=self.domain,round=1,resource='jvm',pid=self.proc.pid,jar_sha256=c.SOURCE_JAR_SHA256)
  self.environment=dict(jar_sha256=c.SOURCE_JAR_SHA256,jar_bytes=c.SOURCE_JAR_BYTES,pid=self.proc.pid,java_identity=self.old._java_identity(),command_verified=self.old._argv_jar_path_matches(self.old._split_windows_command_line(self.old._actual_process_command_line(self.proc.pid)),jar,ctx.root))
  until=time.monotonic()+150
  while time.monotonic()<until and self.proc.poll() is None and not self.log.overflow and not self.old._listener_owned(self.proc.pid,self.jp):time.sleep(.25)
  health=[]
  for _ in range(3):
   t=ledger.reserve('config_health');x=self.old._health_get(self.jp,timeout=5);health.append(dict(status=x['status'],up=type(x['body']) is dict and x['body'].get('status')=='UP'));ledger.settle(t,status='READ_ONLY',health=health[-1])
   if health[-1]['up'] and health[-1]['status']==200:break
  self.environment.update(health=health,listener_owned=self.old._listener_owned(self.proc.pid,self.jp));c.require(health[-1]['up'] and self.environment['command_verified'] and self.environment['listener_owned'] and not self.old._external_connections(self.proc.pid),'JAVA_READY_OWNERSHIP');self.before=self.authority('BEFORE')
 def authority(self,phase):
  t=self.ledger.reserve('authority_read',domain=self.domain,round=1,phase=phase)
  if phase=='BEFORE':c.require(self.client.initial_state_valid(),'CONFIG_INITIAL');out=self.client.observations[-2:]
  else:self.client.stop_writes=True;out=self.client.final_readback(reconcile=True)+[self.client.request('final_list')]
  self.ledger.settle(t,status='READ_ONLY',observations=out,connection='SAME_SERVICE_GET_ONLY');return out
 def business(self,name,args):
  result=self.business_api.invoke(name,args)
  if name=='update_config_v2' and result.get('status')=='COMMITTED' and self.ct['experiment']['fault_enabled']:
   self.client.stop_writes=True;self.fault.update(triggered=True,observed=True,agent_exposed=True);return dict(status='UNKNOWN_OUTCOME',reason='LOCAL_SUCCESS_DELIVERY_SUPPRESSED',write_policy='STOP_WRITES_READ_ONLY_RECONCILE')
  return result
 def finish(self):
  self.after=self.authority('FINAL');e=self.ct['effect'];ok,item=_api_response(self.after[0],200,0,'item');okh,history=_api_response(self.after[1],200,0,'list');okl,listed=_api_response(self.after[2],200,0,'list');c.require(ok and _valid_item(item,e,2,'rpf53-v2') and okh and _history(history,e) and okl and len(listed)==1 and _valid_item(listed[0],e,2,'rpf53-v2'),'CONFIG_ORACLE');return dict(before=self.before,after=self.after,http=self.client.observations,oracle=dict(contract_outcome='CONTRACT_SATISFIED_IN_RUN'),environment=self.environment,backend='REAL_JAVA_H2_HTTP')
 def cleanup(self):
  if self.client:self.client.stop_writes=True;self.client._api_key=None
  if self.proc:
   if self.proc.poll() is None:self.proc.terminate()
   try:self.proc.wait(timeout=20)
   except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=10)
   closed=self.old._port_closed(self.jp);result=dict(process_gone=self.proc.poll() is not None,port_closed=closed,key_reference_released=True);self.ledger.append('PROCESS_CLEANUP',domain=self.domain,round=1,resource='jvm',pid=self.proc.pid,**result)
   if self.log:
    info=self.log.close(self.folder/'java-redacted.log');c.require(not info['overflow'] and not self.log.thread.is_alive(),'JAVA_LOG_CLEANUP')
   if self.proc.stdout:self.proc.stdout.close()
   if self.java_ticket:self.ledger.settle(self.java_ticket,status='CLOSED',cleanup=result)
   c.require(all(result.values()),'JAVA_CLEANUP');return result
  return dict(process_gone=True,port_closed=True,key_reference_released=True)
