"""One bounded Provider meter and SDK host for both typed Target capabilities."""
import copy,http.client,os,re,secrets,socket,subprocess,threading
from http.server import HTTPServer,BaseHTTPRequestHandler
from . import pge_r68_context as c
class Port:
 def prepare_common(self,ctx,ct,ledger):
  ctx.validate(ct);c.require(ct['experiment']['domain']==self.domain,'PORT_DOMAIN');self.ctx=ctx;self.ct=ct;self.ledger=ledger;self.trace=[];self.pending=None;self.cold=False;self.fault=dict.fromkeys(('planned','triggered','observed','agent_exposed'),False);self.fault['planned']=ct['experiment']['fault_enabled']
 def expected(self):return list(c.TOOLS[self.domain][:2]) if self.domain==c.DOMAINS[1] else list(c.TOOLS[self.domain])
 def allowed(self,name,args):
  c.require(args==c.args_for(self.ct,name),'TOOL_ARGUMENTS');c.require(all(type(args[k]) is type(v) for k,v in c.args_for(self.ct,name).items()),'TOOL_ARGUMENT_TYPE');names=[t['name'] for t in self.trace];expected=self.expected()
  if len(names)<len(expected):c.require(name==expected[len(names)],'TOOL_ORDER')
  else:c.require(self.ct['experiment']['fault_enabled'] and len(names)==len(expected) and name==c.TOOLS[self.domain][0 if self.domain==c.DOMAINS[0] else 2],'STOP_WRITES_READ_ONLY')
 def register(self,proof):
  call=proof['call'];c.require(self.pending is None,'PENDING_TOOL')
  if call:self.allowed(call['name'],call['arguments']);self.pending=dict(response_id=proof['response_id'],**call);self.ledger.append('INTENT',domain=self.domain,round=self.ct['experiment']['round'],cold=self.cold,**self.pending)
  else:c.require(len(self.trace)>=len(self.expected()) and proof['finish_reason']=='stop','PREMATURE_STOP')
 def invoke(self,value):
  c.require(self.pending is not None and value=={k:self.pending[k] for k in ('call_id','name','arguments')},'TOOL_LINEAGE');self.allowed(value['name'],value['arguments']);result=self.business(value['name'],value['arguments']);row=dict(**self.pending,result=result,result_sha256=c.digest(result));self.trace.append(row);self.pending=None;self.ledger.append('TOOL_RETURN',domain=self.domain,round=self.ct['experiment']['round'],cold=self.cold,row=row)
  if result.get('status')=='UNKNOWN_OUTCOME':self.ledger.append('FAULT',domain=self.domain,round=self.ct['experiment']['round'],cold=self.cold,fault=self.fault)
  return result

def shape(data):
 m={};calls=[];choices=data.get('choices') if type(data) is dict else None
 if type(choices) is list and len(choices)==1 and type(choices[0]) is dict:
  m=choices[0].get('message');m=m if type(m) is dict else {};calls=m.get('tool_calls')
 u=data.get('usage') if type(data) is dict else None
 def length(v):return len(v.encode()) if type(v) is str else None
 return dict(schema='rpf68-shape-v1',response_type=type(data).__name__,choice_count=len(choices) if type(choices) is list else None,finish_reason=choices[0].get('finish_reason') if type(choices) is list and len(choices)==1 and type(choices[0]) is dict and choices[0].get('finish_reason') in ('stop','tool_calls','length','content_filter') else 'OTHER',tool_container=type(calls).__name__,tool_count=len(calls) if type(calls) is list else None,content_type=type(m.get('content')).__name__,content_bytes=length(m.get('content')),reasoning_nonempty=bool(m.get('reasoning_content')),refusal_nonempty=bool(m.get('refusal')),usage_confidence='UNTRUSTED_OBSERVED_HINT',usage={k:u.get(k) if type(u) is dict and type(u.get(k)) is int and 0<=u[k]<=1000000 else None for k in ('prompt_tokens','completion_tokens','total_tokens')})
def parse(data,cap,allowed):
 c.require(type(data) is dict and {'id','object','created','model','choices','usage'}<=set(data)<={'id','object','created','model','choices','usage','system_fingerprint','service_tier','prompt_cache_hit_tokens'},'RESPONSE_FIELDS');c.require(type(data['id']) is str and re.fullmatch('[A-Za-z0-9_-]{1,160}',data['id']) and data['object']=='chat.completion' and type(data['created']) is int and data['created']>=0 and data['model'] in ('deepseek-flash','DeepSeek-V4.1-Flash-1017'),'RESPONSE_IDENTITY');ch=data['choices'];c.require(type(ch) is list and len(ch)==1,'ONE_CHOICE');ch=ch[0];c.require(set(ch)<={'index','message','finish_reason','logprobs'} and type(ch['index']) is int and ch['index']==0 and ch['finish_reason'] in ('tool_calls','stop'),'FINISH_REASON');m=ch['message'];c.require(type(m) is dict and set(m)<={'role','content','tool_calls','reasoning_content','refusal'} and m['role']=='assistant' and not m.get('reasoning_content') and not m.get('refusal'),'PRIVATE_PROTOCOL');content=m.get('content');c.require(content is None or type(content) is str and len(content.encode())<=512,'CONTENT_BOUND');calls=m.get('tool_calls');calls=[] if calls is None else calls;c.require(type(calls) is list and len(calls)<=1 and bool(calls)==(ch['finish_reason']=='tool_calls'),'SINGLE_TOOL');call=None
 if calls:
  z=copy.deepcopy(calls[0]);ix=z.pop('index',0);c.require(type(ix) is int and ix==0 and set(z)=={'id','type','function'} and z['type']=='function' and re.fullmatch('[A-Za-z0-9_-]{1,160}',z['id']),'TOOL_ID');f=z['function'];c.require(set(f)=={'name','arguments'} and f['name'] in allowed and type(f['arguments']) is str and len(f['arguments'].encode())<=8192,'DOMAIN_TOOL');args=c.strict(f['arguments']);c.require(type(args) is dict,'ARGUMENTS_OBJECT');call=dict(call_id=z['id'],name=f['name'],arguments=args)
 u={k:data['usage'][k] for k in ('prompt_tokens','completion_tokens','total_tokens')};c.require(all(type(v) is int and v>=0 for v in u.values()) and u['total_tokens']==u['prompt_tokens']+u['completion_tokens'] and u['completion_tokens']<=cap,'USAGE');return dict(response_id=data['id'],model=data['model'],call=call,finish_reason=ch['finish_reason'],usage=u,content_bytes=len((content or '').encode()),raw_sha256=c.digest(data))
def https(body,key):
 conn=http.client.HTTPSConnection('api.deepseek.com',timeout=60)
 try:
  conn.request('POST','/chat/completions',body=c.canonical(body),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'});r=conn.getresponse();c.require(r.status==200,'PROVIDER_HTTP');raw=r.read(262145);c.require(len(raw)<=262144,'RESPONSE_SIZE');return raw,c.strict(raw)
 finally:conn.close()
def require_admission(ctx,l):
 c.require(ctx.public()['source_kind']==c.REAL,'REAL_ADMISSION_REQUIRED')
 from .pge_r68_session import freeze_check
 freeze_check(ctx);gate=c.strict((ctx.root/'paid-gate.json').read_bytes());state=l.read();c.require(gate['context_sha256']==c.digest(ctx.public()) and any(e['kind']=='ADMISSION' and e['gate_sha256']==c.digest(gate) for e in state['events']) and not state['unknown'] and not state['blocked'],'REAL_ADMISSION_REQUIRED')

def exchange(ctx,l,ct,role,ordinal,body,proof,*,fixture=None,key=None,cold=False):
 if fixture is None:require_admission(ctx,l);c.require(type(key) is str and bool(key),'KEY_UNAVAILABLE')
 domain=ct['experiment']['domain'];index=ct['experiment']['round'];scope=dict(domain=domain,round=index,role=role,cold=cold);receiptid=('cold-' if cold else '')+str(index)+'-'+role.lower()+'-'+str(ordinal)
 if proof['input_upper']+proof['output_cap']>proof['slot_cap']:
  l.receipt('PRE_SEND_REJECTED',receiptid+'-reject',dict(scope=scope,request=proof,reason='INPUT_BOUND',provider_reserved=False,network_sent=False),**scope);raise ValueError('PLATFORM_PRE_SEND_BUDGET')
 ticket=None
 if fixture is None:ticket=l.reserve('provider',**scope,request=proof)
 l.append('MODEL_REQUEST',**scope,ticket=ticket,request=proof)
 try:
  raw,data=(c.canonical(fixture),fixture) if fixture is not None else https(body,key)
  l.receipt('SHAPE',receiptid,dict(request_sha256=proof['request_sha256'],raw_sha256=c.sha(raw),shape=shape(data)),**scope)
  p=parse(data,proof['output_cap'],('select_experiment',) if role=='EXPLORER' else c.TOOLS[domain]);p['raw_sha256']=c.sha(raw);c.require(p['usage']['prompt_tokens']<=proof['input_upper'],'INPUT_USAGE')
  ids=[e['response']['response_id'] for e in l.read()['events'] if e['kind']=='MODEL_RESPONSE'];toolids=[e['response']['call']['call_id'] for e in l.read()['events'] if e['kind']=='MODEL_RESPONSE' and e['response']['call']];c.require(p['response_id'] not in ids and (not p['call'] or p['call']['call_id'] not in toolids),'GLOBAL_ID_REPLAY')
  l.append('PARSED',**scope,receipt_id=receiptid,proof_sha256=c.digest(p),usage_confidence='VERIFIED_PROVIDER_USAGE')
  if ticket:l.settle(ticket,status='RECEIVED',response=p)
  l.append('MODEL_RESPONSE',**scope,ticket=ticket,response=p);return data,p
 except BaseException:
  if ticket and ticket not in l.read()['results']:l.settle(ticket,status='UNKNOWN')
  raise

def fixture_response(ct,n,call,*,prefix='fixture'):
 tool=None
 if call:tool=dict(id=prefix+'-call-'+str(n),type='function',function=dict(name=call,arguments=c.canonical(c.args_for(ct,call)).decode()))
 return dict(id=prefix+'-response-'+str(n),object='chat.completion',created=0,model='deepseek-flash',choices=[dict(index=0,finish_reason='tool_calls' if tool else 'stop',message=dict(role='assistant',content=None if tool else 'Stopped safely.',**({'tool_calls':[tool]} if tool else {})))],usage=dict(prompt_tokens=400+n*30,completion_tokens=20,total_tokens=420+n*30))
class Driver:
 def __init__(self,ctx,l,ct,*,fixture=False,key=None,cold=False):self.ctx=ctx;self.l=l;self.ct=ct;self.fixture=fixture;self.key=key;self.cold=cold;self.rows=[];self.prior=None;self.config=None;self.expected=None;self.failure=None;self.ready=None;self.pid=None
 def completion(self,body,port):
  c.require(self.failure is None and self.ready is not None and port.pending is None,'HOST_STOP');c.require(set(body)<={'model','messages','tools','tool_choice','parallel_tool_calls','max_tokens','max_completion_tokens','stream','temperature','thinking'} and body['model']=='deepseek-flash' and body['stream'] is False and body['parallel_tool_calls'] is False and body.get('tool_choice','auto')=='auto','SDK_CONFIG');caps=set(body)&{'max_tokens','max_completion_tokens'};c.require(len(caps)==1 and body[next(iter(caps))]==512,'SDK_CAP');tools=body['tools'];domain=self.ct['experiment']['domain'];c.require([t['function']['name'] for t in tools]==list(c.TOOLS[domain]),'SDK_REGISTRY')
  for t in tools:
   schema=t['function']['parameters'];args=c.args_for(self.ct,t['function']['name']);c.require(schema['type']=='object' and schema['additionalProperties'] is False and set(schema['properties'])==set(schema.get('required',[]))==set(args) and all(schema['properties'][k]['type']==('integer' if type(v) is int else 'string') for k,v in args.items()),'SDK_SCHEMA')
  config={k:v for k,v in body.items() if k not in ('messages','max_tokens','max_completion_tokens')};c.require(self.config is None or config==self.config,'CONFIG_DRIFT');self.config=copy.deepcopy(config);messages=body['messages'];c.require(messages[:2]==[dict(role='system',content=c.INSTRUCTIONS[domain]),dict(role='user',content=c.prompt(self.ct))],'INITIAL_PROMPT');suffix=messages if self.prior is None else messages[len(self.prior):];c.require(self.prior is None or messages[:len(self.prior)]==self.prior,'PREFIX_DRIFT')
  if self.expected is not None:c.require([m for m in suffix if m.get('role')=='assistant'][0].get('content')==self.expected.get('content'),'NARRATIVE_REINJECTION')
  calls=[z for m in messages if m.get('role')=='assistant' for z in m.get('tool_calls',[])];returns=[m for m in messages if m.get('role')=='tool'];c.require(len(calls)==len(returns)==len(port.trace),'RETURN_COUNT')
  for a,b,t in zip(calls,returns,port.trace):c.require(a['id']==b['tool_call_id']==t['call_id'] and a['function']['name']==t['name'] and c.strict(a['function']['arguments'])==t['arguments'] and b['content'].encode()==c.canonical(t['result']),'ORIGINAL_TOOL_RETURN')
  n=len(self.rows)+1;cap=512 if len(port.trace)>=len(port.expected()) else 256;cap=512 if domain==c.DOMAINS[1] and len(port.trace)>=2 else cap;slots=c.CAPS[domain];c.require(n<=len(slots),'NORMAL_PROTOCOL_EXHAUSTED');out=copy.deepcopy(body);out.pop('max_completion_tokens',None);out.update(max_tokens=cap,thinking=dict(type='disabled'));previous=self.rows[-1]['response']['usage']['prompt_tokens'] if self.rows else None;sb=len(c.canonical(suffix)) if self.rows else 0;upper=len(c.canonical(out)) if previous is None else previous+sb+512
  q=dict(ordinal=n,request_sha256=c.digest(out),sdk_request_sha256=c.digest(body),configuration_sha256=c.digest(config),messages_sha256=c.digest(messages),schema_sha256=c.digest(tools),canonical_bytes=len(c.canonical(out)),previous_prompt=previous,suffix_bytes=sb,framing_guard=512 if previous is not None else 0,input_upper=upper,output_cap=cap,slot_cap=slots[n-1],tool_returns=[dict(call_id=t['call_id'],result_sha256=t['result_sha256']) for t in port.trace],stage='POST_RECONCILE_TERMINAL' if domain==c.DOMAINS[1] and len(port.trace)==3 else 'READ_ONLY' if cap==512 else 'PRE_COMMIT')
  scripted=None
  if self.fixture:
   seq=port.expected()+([c.TOOLS[domain][0 if domain==c.DOMAINS[0] else 2]] if self.ct['experiment']['fault_enabled'] else []);scripted=fixture_response(self.ct,n,seq[n-1] if n<=len(seq) else None,prefix=('cold' if self.cold else 'fixture')+'-'+str(self.ct['experiment']['round']))
  data,p=exchange(self.ctx,self.l,self.ct,'TARGET',n,out,q,fixture=scripted,key=self.key,cold=self.cold);port.register(p);self.rows.append(dict(request=q,response=p));self.prior=copy.deepcopy(messages);self.expected=copy.deepcopy(data['choices'][0]['message']);return data
 def run(self,port):
  ctx,l,ct=self.ctx,self.l,self.ct;h,old=c.helpers();pin=ct['execution']['sdk'];direct=h.resolve_direct_python(pin);folder=ctx.scope(ctx.root/('cold-'+str(ct['experiment']['round']) if self.cold else 'runs/'+ct['experiment']['run_id']+'/sdk'));folder.mkdir(parents=True);token=secrets.token_hex(32);driver=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*_):pass
   def do_POST(self):
    try:
     self.connection.settimeout(5);c.require(driver.failure is None and self.headers.get('Authorization')=='Bearer '+token and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and self.headers.get('Origin') is None and self.headers.get('Transfer-Encoding') is None,'HOST_AUTH');n=int(self.headers.get('Content-Length','0'));c.require(0<n<=262144,'HOST_SIZE');raw=self.rfile.read(n);c.require(len(raw)==n,'HOST_SHORT');v=c.strict(raw)
     if self.path=='/ready':
      expected=dict(framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=driver.pid,python_executable_sha256=pin['python_executable_sha256'],sdk_source_sha256='70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa',openai_source_sha256=pin['openai_core_sha256'],sdk_site_root_binding_sha256=pin['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=pin['python_runtime_mapping_sha256']);c.require(driver.ready is None and v==expected,'SDK_PIN');driver.ready=v;result={'ready':True}
     elif self.path=='/tool':result=port.invoke(v)
     else:c.require(self.path=='/v1/chat/completions','HOST_ROUTE');result=driver.completion(v,port)
     raw=c.canonical(result);self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    except BaseException as error:
     driver.failure=str(error) if type(error) is ValueError and re.fullmatch('[A-Z0-9_]+',str(error)) else 'PLATFORM_ERROR'
     if not (folder/'host-failure.json').exists():ctx.once(folder/'host-failure.json',dict(error_type=type(error).__name__,code=driver.failure,stage='LOOPBACK_HANDLER'))
     self.send_response(409);self.end_headers()
  resource='cold' if self.cold else 'sdk';ticket=l.reserve(resource,domain=port.domain,round=ct['experiment']['round']);hostticket=None if self.cold else l.reserve('host',domain=port.domain,round=ct['experiment']['round']);server=thread=proc=None;report=None
  try:
   server=HTTPServer(('127.0.0.1',ct['execution']['host_port']),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();cfg=dict(port=server.server_port,token=token,write_root=str(folder),sdk_readonly_path=str(old.SDK_SITE.resolve()),sdk_site_root_binding_sha256=pin['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=pin['python_runtime_mapping_sha256'],instructions=c.INSTRUCTIONS[port.domain],task_prompt=c.prompt(ct),domain=port.domain);script=c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py';proc=subprocess.Popen([str(direct),'-I','-B','-X','utf8',str(script)],cwd=folder,env=old._sdk_env(folder),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.pid=proc.pid;l.append('PROCESS_START',domain=port.domain,round=ct['experiment']['round'],resource=resource,pid=self.pid,child_sha256=c.sha(script.read_bytes()),cold=self.cold);stdout,stderr=proc.communicate(c.canonical(cfg),timeout=1200);report=c.strict(stdout);report.pop('final_output_sha256',None);ctx.once(folder/'report.json',report);c.require(proc.returncode==0 and not stderr and not self.failure and report['status']=='COMPLETED','SDK_PROCESS_REPORT');c.require(report['pid']==self.pid and report['requests']==len(self.rows) and report['tool_calls']==report['tool_callbacks']==len(port.trace) and report['input_tokens']==sum(r['response']['usage']['prompt_tokens'] for r in self.rows) and report['output_tokens']==sum(r['response']['usage']['completion_tokens'] for r in self.rows),'SDK_USAGE');c.require(not report['provider_key_present'] and not report['business_key_present'] and not report['guard_denials'] and not report['denied_files'],'SDK_GUARD');l.settle(ticket,status='COMPLETED')
   if hostticket:l.settle(hostticket,status='CLOSED')
  finally:
   self.key=None
   if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=15)
   if server:server.shutdown();server.server_close()
   if thread:thread.join(timeout=5)
   with socket.socket() as sock:sock.settimeout(.2);closed=sock.connect_ex(('127.0.0.1',ct['execution']['host_port']))!=0
   cleanup=dict(process_gone=proc is None or proc.poll() is not None,thread_gone=thread is None or not thread.is_alive(),port_closed=closed,key_reference_released=True);l.append('PROCESS_CLEANUP',domain=port.domain,round=ct['experiment']['round'],resource=resource,pid=self.pid,cold=self.cold,**cleanup);c.require(all(cleanup.values()),'SDK_CLEANUP')
  return dict(ready=self.ready,report=report,pid=self.pid,requests=self.rows,cleanup=cleanup,child_sha256=c.sha(script.read_bytes()))
