"""Task-owned SDK/Host bridge; one WAL, no legacy ProviderLedger or order roots."""
import copy, http.client, json, os, re, secrets, socket, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from . import pge_r67_context as c

def validate_response(data,cap,ct):
    c.require(type(data) is dict and {'id','object','created','model','choices','usage'}<=set(data)<= {'id','object','created','model','choices','usage','system_fingerprint','service_tier','prompt_cache_hit_tokens'},'RESPONSE_FIELDS')
    c.require(type(data['id']) is str and re.fullmatch('[A-Za-z0-9_-]{1,160}',data['id']) and data['object']=='chat.completion' and type(data['created']) is int and data['created']>=0 and data['model'] in ct['execution']['models'],'RESPONSE_IDENTITY')
    choices=data['choices'];c.require(type(choices) is list and len(choices)==1,'PARALLEL_CHOICES');choice=choices[0]
    c.require(type(choice) is dict and {'index','message','finish_reason'}<=set(choice)<={'index','message','finish_reason','logprobs'} and type(choice['index']) is int and choice['index']==0 and choice['finish_reason'] in ('tool_calls','stop'),'FINISH_REASON')
    m=choice['message'];c.require(type(m) is dict and set(m)<={'role','content','tool_calls','reasoning_content','refusal'} and m.get('role')=='assistant' and not m.get('refusal') and not m.get('reasoning_content'),'MESSAGE_OR_FILTER')
    calls=m.get('tool_calls') or [];c.require(type(calls) is list and len(calls)<=1,'PARALLEL_TOOLS')
    c.require(bool(calls)==(choice['finish_reason']=='tool_calls') and (not calls or m.get('content') in (None,'')),'FINISH_SHAPE')
    call=None
    if calls:
        v=copy.deepcopy(calls[0]);idx=v.pop('index',0);c.require(type(idx) is int and idx==0 and set(v)=={'id','type','function'} and v['type']=='function' and type(v['id']) is str and re.fullmatch('[A-Za-z0-9_-]{1,160}',v['id']),'TOOL_ENVELOPE')
        fn=v['function'];c.require(type(fn) is dict and set(fn)=={'name','arguments'} and fn['name'] in c.TOOLS and type(fn['arguments']) is str,'TOOL_FUNCTION')
        args=c.strict(fn['arguments']);c.require(args==c.args_for(fn['name'],ct['effect']),'TOOL_ARGUMENTS');call=dict(call_id=v['id'],name=fn['name'],arguments=args)
    u=data['usage'];c.require(type(u) is dict and {'prompt_tokens','completion_tokens','total_tokens'}<=set(u),'USAGE_FIELDS')
    usage={k:u[k] for k in ('prompt_tokens','completion_tokens','total_tokens')}
    c.require(all(type(v) is int and v>=0 for v in usage.values()) and usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'] and usage['completion_tokens']<=cap,'USAGE_BOUND')
    c.require(cap==256 or choice['finish_reason'] in ('stop','tool_calls'),'READ_ONLY_FINAL_STAGE')
    content=m.get('content');c.require(content is None or type(content) is str,'CONTENT_TYPE')
    return dict(response_id=data['id'],model=data['model'],finish_reason=choice['finish_reason'],call=call,usage=usage,content_sha256=c.sha((content or '').encode()),content_bytes=len((content or '').encode()),raw_sha256=c.digest(data),reasoning_persisted=False,content_persisted=False,filter=False)

class Driver:
    def __init__(self,ctx,ledger,*,fixture=False,key=None,reconcile=True,cold=False):
        self.ctx=ctx;self.ledger=ledger;self.fixture=fixture;self.key=key;self.reconcile=reconcile;self.cold=cold;self.ready=None;self.pid=None;self.requests=[];self.prior_messages=None;self.configuration=None;self.failure=None;self.child=None;self.cleaned=False;self.port_closed=False
    def fixture_response(self,body):
        n=len(self.requests);names=list(c.TOOLS) if self.reconcile else list(c.TOOLS[:2]);call=None
        if n<len(names):
            name=names[n];call={'id':'fixture-call-'+str(n+1),'type':'function','function':{'name':name,'arguments':c.canonical(c.args_for(name,self.ctx.ct['effect'])).decode()}}
        return dict(id='fixture-response-'+str(n+1),object='chat.completion',created=0,model='deepseek-flash',choices=[dict(index=0,finish_reason='tool_calls' if call else 'stop',message=dict(role='assistant',content=None if call else 'Stopped safely.',**({'tool_calls':[call]} if call else {})))],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0))
    def validate_request(self,body,port):
        c.require(type(body) is dict and set(body)<={'model','messages','tools','tool_choice','parallel_tool_calls','max_tokens','max_completion_tokens','stream','temperature','thinking'},'REQUEST_FIELDS')
        c.require(body.get('model')=='deepseek-flash' and body.get('stream') is False and body.get('tool_choice','auto')=='auto' and body.get('parallel_tool_calls') is False,'REQUEST_CONFIG')
        fields=set(body)&{'max_tokens','max_completion_tokens'};c.require(len(fields)==1 and body[next(iter(fields))]==512,'SDK_CAP')
        tools=body.get('tools');c.require(type(tools) is list and len(tools)==3 and [t['function']['name'] for t in tools]==list(c.TOOLS),'SDK_REGISTRATION')
        for t in tools:
            fn=t['function'];s=fn['parameters'];args=c.args_for(fn['name'],self.ctx.ct['effect']);c.require(s['type']=='object' and s.get('additionalProperties') is False and set(s.get('properties',{}))==set(args) and set(s.get('required',[]))==set(args),'SDK_SCHEMA')
            for k,v in args.items():c.require(s['properties'][k].get('type')==('integer' if type(v) is int else 'string'),'SDK_SCHEMA_TYPE')
        config={k:v for k,v in body.items() if k not in ('messages','max_tokens','max_completion_tokens')}
        c.require(self.configuration is None or config==self.configuration,'NONMESSAGE_DRIFT');self.configuration=copy.deepcopy(config)
        messages=body['messages'];c.require(type(messages) is list and len(messages)>=2,'MESSAGES')
        c.require(messages[0]=={'role':'system','content':c.INSTRUCTIONS} and messages[1]=={'role':'user','content':c.canonical(self.ctx.ct['effect']).decode()},'INITIAL_PROMPT')
        if self.prior_messages is not None:c.require(messages[:len(self.prior_messages)]==self.prior_messages,'PREFIX_DRIFT')
        calls=[t for m in messages if m.get('role')=='assistant' for t in m.get('tool_calls',[])];returns=[m for m in messages if m.get('role')=='tool']
        c.require(len(calls)==len(returns)==len(port.trace),'TOOL_RETURN_COUNT')
        line=[]
        for original,returned,trace in zip(calls,returns,port.trace):
            c.require(original['id']==returned['tool_call_id']==trace['call_id'] and original['function']['name']==trace['name'] and c.strict(original['function']['arguments'])==trace['arguments'],'TOOL_RETURN_ID')
            value=c.strict(returned['content']);c.require(value==trace['result'],'TOOL_RETURN_CONTENT');line.append(dict(call_id=trace['call_id'],result_sha256=c.digest(value)))
        cap=512 if port.fault['agent_exposed'] else 256
        out=copy.deepcopy(body);out.pop('max_completion_tokens',None);out['max_tokens']=cap;out['thinking']={'type':'disabled'}
        current=copy.deepcopy(messages);suffix=messages[len(self.prior_messages):] if self.prior_messages is not None else messages
        upper=len(c.canonical(out)) if not self.requests else self.requests[-1]['response']['usage']['prompt_tokens']+len(c.canonical(suffix))+512
        request=dict(sdk_request_sha256=c.digest(body),request_sha256=c.digest(out),configuration_sha256=c.digest(config),messages_sha256=c.digest(messages),input_upper=upper,output_cap=cap,stage='POST_COMMIT_READ_ONLY' if cap==512 else 'PRE_COMMIT',tool_returns=line,schema_sha256=c.digest(tools),canonical_bytes=len(c.canonical(out)))
        c.require(len(self.requests)<6 and upper+cap<=c.CAPS[len(self.requests)],'INPUT_BOUND')
        self.prior_messages=current;return out,request
    def completion(self,body,port):
        c.require(self.ready is not None and port.pending is None and self.failure is None,'SDK_READY_OR_PENDING')
        out,request=self.validate_request(body,port);ticket=None
        if not self.fixture:
            ticket=self.ledger.reserve('provider',role='TARGET',token_upper=c.CAPS[len(self.requests)],cost_micro_cny_upper=request['input_upper']*4.5+request['output_cap']*18,**{k:request[k] for k in ('request_sha256','input_upper','output_cap','stage')})
        self.ledger.append('MODEL_REQUEST',fixture=self.fixture,ticket=ticket,request=request,cold=self.cold)
        try:
            if self.fixture:data=self.fixture_response(out)
            else:
                c.require(type(self.key) is str and bool(self.key),'KEY_UNAVAILABLE')
                conn=http.client.HTTPSConnection('api.deepseek.com',timeout=60)
                try:
                    conn.request('POST','/chat/completions',body=c.canonical(out),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
                    response=conn.getresponse();c.require(response.status==200,'PROVIDER_HTTP_STATUS');raw=response.read(262145);c.require(len(raw)<=262144,'RESPONSE_SIZE');data=c.strict(raw)
                finally:conn.close()
            proof=validate_response(data,request['output_cap'],self.ctx.ct);u=proof['usage'];c.require(u['prompt_tokens']<=request['input_upper'],'INPUT_USAGE_BOUND');port.register(proof['response_id'],proof['call'])
            if ticket:self.ledger.settle(ticket,status='KNOWN',usage=u,response_id=proof['response_id'],request_sha256=request['request_sha256'])
            self.ledger.append('MODEL_RESPONSE',fixture=self.fixture,ticket=ticket,response=proof,cold=self.cold);self.requests.append(dict(request=request,response=proof,ticket=ticket,fixture=self.fixture));return data
        except BaseException:
            if ticket and ticket not in self.ledger.read()['results']:self.ledger.settle(ticket,status='UNKNOWN',unknown=True)
            raise
    def accept_ready(self,value):
        p=c.pin();c.require(self.ready is None and value==dict(framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=self.pid,python_executable_sha256=p['python_executable_sha256'],sdk_source_sha256='70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa',openai_source_sha256=p['openai_core_sha256'],sdk_site_root_binding_sha256=p['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=p['python_runtime_mapping_sha256']),'SDK_READY_IDENTITY');self.ready=value;self.ledger.append('SDK_READY',ready=value,cold=self.cold)
    def run(self,port):
        self.ctx.check();h,old=c.sdk_helpers();pin=c.pin();direct=h.resolve_direct_python(pin);folder=self.ctx.scope(self.ctx.root/('cold-scratch' if self.cold else 'sdk-scratch'));folder.mkdir()
        token=secrets.token_hex(32);driver=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                try:
                    c.require(driver.failure is None and self.headers.get('Authorization')=='Bearer '+token and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and self.headers.get('Origin') is None,'HOST_AUTH')
                    n=int(self.headers.get('Content-Length','0'));c.require(0<n<=262144,'HOST_SIZE');value=c.strict(self.rfile.read(n))
                    if self.path=='/ready':driver.accept_ready(value);result={'ready':True}
                    elif self.path=='/tool':c.require(driver.ready is not None,'SDK_NOT_READY');result=port.invoke(value)
                    else:c.require(self.path=='/v1/chat/completions','HOST_ROUTE');result=driver.completion(value,port)
                    raw=c.canonical(result);self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except BaseException as error:
                    driver.failure=type(error).__name__+':'+(str(error) if type(error) is ValueError and re.fullmatch('[A-Z0-9_]+',str(error)) else 'REDACTED');self.send_response(409);self.end_headers()
        resource='cold' if self.cold else 'sdk';ticket=self.ledger.reserve(resource);host_ticket=None
        if not self.cold:host_ticket=self.ledger.reserve('host')
        server=None;thread=None;start=time.monotonic();report=None
        try:
            server=HTTPServer(('127.0.0.1',self.ctx.ct['execution']['port']),Handler);server.timeout=1
            thread=threading.Thread(target=server.serve_forever,name='rpf67-host',daemon=True);thread.start()
            cfg=dict(port=server.server_port,token=token,write_root=str(folder),sdk_readonly_path=str(old.SDK_SITE.resolve()),sdk_site_root_binding_sha256=pin['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=pin['python_runtime_mapping_sha256'],instructions=c.INSTRUCTIONS,task_prompt=c.canonical(self.ctx.ct['effect']).decode())
            script=c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r67_order_child.py'
            self.child=subprocess.Popen([str(direct),'-I','-B','-X','utf8',str(script)],cwd=folder,env=old._sdk_env(folder),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.pid=self.child.pid;self.ledger.append('PROCESS_START',pid=self.pid,parent_pid=os.getpid(),resource=resource,python_sha256=pin['python_executable_sha256'],child_sha256=c.sha(script.read_bytes()),cold=self.cold)
            stdout,stderr=self.child.communicate(c.canonical(cfg),timeout=max(1,1200-(time.monotonic()-start)))
            report=c.strict(stdout);self.ctx.once(folder/'child-report.json',report)
            c.require(self.child.returncode==0 and not stderr and self.failure is None and report['status']=='COMPLETED','SDK_PROCESS_REPORT')
            c.require(report['pid']==self.pid and report['tool_callbacks']==report['tool_calls']==len(port.trace) and report['requests']==len(self.requests) and report['input_tokens']==sum(r['response']['usage']['prompt_tokens'] for r in self.requests) and report['output_tokens']==sum(r['response']['usage']['completion_tokens'] for r in self.requests),'SDK_USAGE')
            c.require(not report['provider_key_present'] and not report['business_key_present'] and not report['guard_denials'] and not report['denied_files'] and report['final_text_persisted'] is False,'CREDENTIAL_OR_GUARD')
            self.ledger.settle(ticket,status='PASS',pid=self.pid)
            if host_ticket:self.ledger.settle(host_ticket,status='PASS')
        finally:
            self.key=None
            if self.child is not None:
                if self.child.poll() is None:self.child.terminate();self.child.wait(timeout=15)
                self.cleaned=self.child.poll() is not None
            if server:server.shutdown();server.server_close()
            if thread:thread.join(timeout=5)
            s=socket.socket();s.settimeout(.2);self.port_closed=s.connect_ex(('127.0.0.1',self.ctx.ct['execution']['port']))!=0;s.close()
            self.ledger.append('PROCESS_CLEANUP',pid=self.pid,process_gone=self.cleaned,thread_gone=thread is None or not thread.is_alive(),port_closed=self.port_closed,key_reference_released=self.key is None,cold=self.cold)
        c.require(self.cleaned and self.port_closed,'CLEANUP_INCOMPLETE')
        return dict(ready=self.ready,report=report,requests=self.requests,child_sha256=c.sha((c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r67_order_child.py').read_bytes()),process_pid=self.pid,process_gone=self.cleaned,port_closed=self.port_closed,fixture=self.fixture,cold=self.cold)

class ScriptDriver(Driver):
    """Free model simulation calls the same production validator and transaction path."""
    def run(self,port):
        c.require(self.fixture and self.ctx.public()['source_kind']==c.SYNTHETIC,'SYNTHETIC_ONLY')
        self.ready={'fixture':True};messages=[dict(role='system',content=c.INSTRUCTIONS),dict(role='user',content=c.canonical(self.ctx.ct['effect']).decode())]
        tools=[]
        for name in c.TOOLS:
            args=c.args_for(name,self.ctx.ct['effect']);tools.append(dict(type='function',function=dict(name=name,description=name,parameters=dict(type='object',properties={k:dict(type='integer' if type(v) is int else 'string') for k,v in args.items()},required=list(args),additionalProperties=False))))
        while True:
            data=self.completion(dict(model='deepseek-flash',stream=False,parallel_tool_calls=False,max_completion_tokens=512,tools=tools,messages=messages),port)
            m=data['choices'][0]['message'];messages.append(m)
            if not m.get('tool_calls'):break
            call=port.pending;result=port.invoke({k:call[k] for k in ('call_id','name','arguments')});messages.append(dict(role='tool',tool_call_id=call['call_id'],content=c.canonical(result).decode()))
        return dict(ready={'fixture':True},report={'status':'SYNTHETIC_TEST_ONLY'},requests=self.requests,fixture=True,cold=False,process_pid=None,process_gone=True,port_closed=True,child_sha256=c.sha((c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r67_order_child.py').read_bytes()))
