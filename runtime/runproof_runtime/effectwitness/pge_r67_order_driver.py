"""Task-owned SDK/Host bridge; one WAL, no legacy ProviderLedger or order roots."""
import copy, http.client, json, os, re, secrets, socket, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from . import pge_r67_context as c

SHAPE_SCHEMA='rpf67-provider-safe-shape-v2'
POLICY='rpf67-order-content-with-single-valid-tool-v1'
MIXED_BYTES=512
def kind(v):
    return {dict:'object',list:'array',str:'string',int:'integer',float:'number',bool:'boolean',type(None):'null'}.get(type(v),'OTHER')
def text_shape(v,present=True):
    valid=True
    try:n=len(v.encode('utf-8')) if type(v) is str else 0
    except UnicodeError:n=8193;valid=False
    return dict(type=kind(v) if present else 'MISSING',nonempty=type(v) is str and bool(v),bytes=min(n,8193),utf8_valid=valid)
def id_shape(v):
    return dict(type=kind(v),valid=type(v) is str and re.fullmatch('[A-Za-z0-9_-]{1,160}',v) is not None,sha256=c.sha(v.encode('utf-8',errors='surrogatepass')) if type(v) is str else None)
def safe_shape(data):
    """Total bounded projection: no text, argument strings/hash or arbitrary key names."""
    d=data if type(data) is dict else {};known={'id','object','created','model','choices','usage','system_fingerprint','service_tier','prompt_cache_hit_tokens'}
    choices=d.get('choices');projected=[]
    for ch in choices[:2] if type(choices) is list else []:
        ch=ch if type(ch) is dict else {'_invalid':True};m=ch.get('message');m=m if type(m) is dict else {};calls=m.get('tool_calls');tools=[]
        for call in calls[:2] if type(calls) is list else []:
            call=call if type(call) is dict else {'_invalid':True};fn=call.get('function');fn=fn if type(fn) is dict else {};args=fn.get('arguments');valid=False
            if type(args) is str:
                try:valid=type(c.strict(args)) is dict
                except Exception:pass
            tools.append(dict(id=id_shape(call.get('id')),type='function' if call.get('type')=='function' else 'OTHER',index_valid='index' not in call or type(call['index']) is int and call['index']==0,unknown_count=min(len(set(call)-{'id','type','function','index'}),1000001),function_unknown_count=min(len(set(fn)-{'name','arguments'}),1000001),name=fn.get('name') if fn.get('name') in c.TOOLS else 'OTHER',arguments_type=kind(args),arguments_json_object=valid))
        finish=ch.get('finish_reason');projected.append(dict(index_type=kind(ch.get('index')),index_zero=type(ch.get('index')) is int and ch['index']==0,unknown_count=min(len(set(ch)-{'index','message','finish_reason','logprobs'}),1000001),finish_reason=finish if finish in ('stop','tool_calls','length','content_filter','aborted','insufficient_system_resource',None) else 'OTHER',message_type=kind(ch.get('message')),role='assistant' if m.get('role')=='assistant' else 'OTHER',message_unknown_count=min(len(set(m)-{'role','content','tool_calls','reasoning_content','refusal'}),1000001),content=text_shape(m.get('content'),'content' in m),reasoning=text_shape(m.get('reasoning_content'),'reasoning_content' in m),refusal=text_shape(m.get('refusal'),'refusal' in m),tool_calls_type=kind(calls) if 'tool_calls' in m else 'MISSING',tool_count=min(len(calls),1000001) if type(calls) is list else None,tools=tools))
    usage=d.get('usage');u=usage if type(usage) is dict else {};hints={}
    for k in ('prompt_tokens','completion_tokens','total_tokens'):
        value=u.get(k);valid=type(value) is int and value>=0;hints[k]=dict(valid_nonnegative_integer=valid,value=min(value,1000001) if valid else None)
    shape=dict(schema=SHAPE_SCHEMA,top_type=kind(data),known_fields=sorted(set(d)&known),unknown_count=min(len(set(d)-known),1000001),object_valid=d.get('object')=='chat.completion',created_valid=type(d.get('created')) is int and d['created']>=0,model=d.get('model') if d.get('model') in ('deepseek-flash','DeepSeek-V4.1-Flash-1017') else 'OTHER',response_id=id_shape(d.get('id')),choices_type=kind(choices),choices_count=min(len(choices),1000001) if type(choices) is list else None,choices=projected,usage_type=kind(usage),usage_confidence='UNTRUSTED_OBSERVED_HINT',usage=hints)
    c.require(len(c.canonical(shape))<=8192,'SHAPE_LIMIT');return shape
def shape_conditions(shape,cap):
    d=shape;choices=d['choices'];ch=choices[0] if len(choices)==1 else None;flags={}
    flags['response_fields']=d['top_type']=='object' and d['unknown_count']==0 and {'id','object','created','model','choices','usage'}<=set(d['known_fields'])
    flags['response_identity']=d['object_valid'] and d['created_valid'] and d['response_id']['valid'] and d['model']!='OTHER'
    flags['single_choice']=d['choices_type']=='array' and d['choices_count']==1 and ch is not None
    flags['choice_identity']=bool(ch and ch['index_zero'] and ch['unknown_count']==0)
    flags['finish_reason']=bool(ch and ch['finish_reason'] in ('stop','tool_calls'))
    flags['message']=bool(ch and ch['message_type']=='object' and ch['role']=='assistant' and ch['message_unknown_count']==0)
    flags['privacy']=bool(ch and all(ch[k]['type'] in ('MISSING','null','string') and not ch[k]['nonempty'] for k in ('reasoning','refusal')))
    flags['tool_container']=bool(ch and ch['tool_calls_type'] in ('MISSING','null','array'))
    count=ch['tool_count'] if ch and ch['tool_calls_type']=='array' else 0
    flags['finish_tool_alignment']=bool(ch and ((ch['finish_reason']=='tool_calls' and count==1) or (ch['finish_reason']=='stop' and count==0)))
    flags['content']=bool(ch and ch['content']['type'] in ('MISSING','null','string') and ch['content']['utf8_valid'] and ch['content']['bytes']<=(MIXED_BYTES if count else 8192))
    flags['tool_envelope']=bool(ch and (not count or count==1 and len(ch['tools'])==1 and all(t['id']['valid'] and t['type']=='function' and t['index_valid'] and t['unknown_count']==t['function_unknown_count']==0 and t['name']!='OTHER' and t['arguments_type']=='string' and t['arguments_json_object'] for t in ch['tools'])))
    u=d['usage'];flags['usage']=d['usage_type']=='object' and all(x['valid_nonnegative_integer'] for x in u.values()) and u['prompt_tokens']['value']+u['completion_tokens']['value']==u['total_tokens']['value'] and u['completion_tokens']['value']<=cap
    return flags
def validate_shape(shape,cap):
    # Regenerate a schema skeleton to enforce exact finite projected field sets/types.
    template=safe_shape({})
    c.require(type(shape) is dict and set(shape)==set(template) and shape['schema']==SHAPE_SCHEMA and shape['usage_confidence']=='UNTRUSTED_OBSERVED_HINT','SHAPE_SCHEMA')
    c.require(len(c.canonical(shape))<=8192 and len(shape['choices'])<=2,'SHAPE_LIMIT')
    def exact(obj,keys):c.require(type(obj) is dict and set(obj)==set(keys),'SHAPE_FIELDS')
    def ident(obj):
        exact(obj,('type','valid','sha256'));c.require(obj['type'] in ('object','array','string','integer','number','boolean','null','OTHER') and type(obj['valid']) is bool and (obj['sha256'] is None or type(obj['sha256']) is str and re.fullmatch('[0-9a-f]{64}',obj['sha256'])),'SHAPE_ID')
    def text(obj):
        exact(obj,('type','nonempty','bytes','utf8_valid'));c.require(obj['type'] in ('object','array','string','integer','number','boolean','null','OTHER','MISSING') and type(obj['nonempty']) is bool and type(obj['utf8_valid']) is bool and type(obj['bytes']) is int and 0<=obj['bytes']<=8193,'SHAPE_TEXT')
    ident(shape['response_id']);c.require(shape['known_fields']==sorted(set(shape['known_fields'])) and set(shape['known_fields'])<={'id','object','created','model','choices','usage','system_fingerprint','service_tier','prompt_cache_hit_tokens'} and shape['model'] in ('deepseek-flash','DeepSeek-V4.1-Flash-1017','OTHER'),'SHAPE_TOP')
    for ch in shape['choices']:
        exact(ch,('index_type','index_zero','unknown_count','finish_reason','message_type','role','message_unknown_count','content','reasoning','refusal','tool_calls_type','tool_count','tools'))
        c.require(ch['finish_reason'] in ('stop','tool_calls','length','content_filter','aborted','insufficient_system_resource',None,'OTHER') and ch['role'] in ('assistant','OTHER') and len(ch['tools'])<=2,'SHAPE_CHOICE')
        for k in ('content','reasoning','refusal'):text(ch[k])
        for t in ch['tools']:
            exact(t,('id','type','index_valid','unknown_count','function_unknown_count','name','arguments_type','arguments_json_object'));ident(t['id']);c.require(t['name'] in (*c.TOOLS,'OTHER') and t['type'] in ('function','OTHER') and type(t['arguments_json_object']) is bool and t['arguments_type'] in ('object','array','string','integer','number','boolean','null','OTHER'),'SHAPE_TOOL')
    exact(shape['usage'],('prompt_tokens','completion_tokens','total_tokens'))
    for u in shape['usage'].values():exact(u,('valid_nonnegative_integer','value'));c.require(type(u['valid_nonnegative_integer']) is bool and (u['value'] is None or type(u['value']) is int and 0<=u['value']<=1000001),'SHAPE_USAGE')
    def finite(obj):
        if type(obj) is dict:
            for k,value in obj.items():
                if k.endswith('_type') or k=='top_type':c.require(value in ('object','array','string','integer','number','boolean','null','OTHER','MISSING'),'SHAPE_TYPE_ENUM')
                if k.endswith('_count'):c.require(value is None or type(value) is int and 0<=value<=1000001,'SHAPE_COUNT')
                if k in ('created_valid','object_valid','index_zero','index_valid'):c.require(type(value) is bool,'SHAPE_BOOLEAN')
                finite(value)
        elif type(obj) is list:
            for value in obj:finite(value)
    finite(shape)
    flags=shape_conditions(shape,cap);c.require(all(type(v) is bool for v in flags.values()),'SHAPE_FLAGS');return flags

def validate_response(data,cap,ct):
    flags=shape_conditions(safe_shape(data),cap)
    for name,valid in flags.items():c.require(valid,'SHAPE_'+name.upper())
    c.require(type(data) is dict and {'id','object','created','model','choices','usage'}<=set(data)<= {'id','object','created','model','choices','usage','system_fingerprint','service_tier','prompt_cache_hit_tokens'},'RESPONSE_FIELDS')
    c.require(type(data['id']) is str and re.fullmatch('[A-Za-z0-9_-]{1,160}',data['id']) and data['object']=='chat.completion' and type(data['created']) is int and data['created']>=0 and data['model'] in ct['execution']['models'],'RESPONSE_IDENTITY')
    choices=data['choices'];c.require(type(choices) is list and len(choices)==1,'PARALLEL_CHOICES');choice=choices[0]
    c.require(type(choice) is dict and {'index','message','finish_reason'}<=set(choice)<={'index','message','finish_reason','logprobs'} and type(choice['index']) is int and choice['index']==0 and choice['finish_reason'] in ('tool_calls','stop'),'FINISH_REASON')
    m=choice['message'];c.require(type(m) is dict and set(m)<={'role','content','tool_calls','reasoning_content','refusal'} and m.get('role')=='assistant' and not m.get('refusal') and not m.get('reasoning_content'),'MESSAGE_OR_FILTER')
    calls=m.get('tool_calls');calls=[] if calls is None else calls;c.require(type(calls) is list and len(calls)<=1,'PARALLEL_TOOLS')
    c.require(bool(calls)==(choice['finish_reason']=='tool_calls'),'FINISH_TOOL_ALIGNMENT')
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
    return dict(response_id=data['id'],model=data['model'],finish_reason=choice['finish_reason'],call=call,usage=usage,content_bytes=len((content or '').encode()),content_is_nonempty=bool(content),policy=POLICY,raw_sha256=c.digest(data),reasoning_persisted=False,content_persisted=False,filter=False)

class Driver:
    def __init__(self,ctx,ledger,*,fixture=False,key=None,reconcile=True,cold=False,mixed=True):
        self.ctx=ctx;self.ledger=ledger;self.fixture=fixture;self.key=key;self.reconcile=reconcile;self.cold=cold;self.ready=None;self.pid=None;self.requests=[];self.prior_messages=None;self.configuration=None;self.failure=None;self.child=None;self.cleaned=False;self.port_closed=False
        self.mixed=mixed
        self.expected_assistant=None
    def fixture_response(self,body):
        n=len(self.requests);names=list(c.TOOLS) if self.reconcile else list(c.TOOLS[:2]);call=None
        if n<len(names):
            name=names[n];call={'id':'fixture-call-'+str(n+1),'type':'function','function':{'name':name,'arguments':c.canonical(c.args_for(name,self.ctx.ct['effect'])).decode()}}
        return dict(id='fixture-response-'+str(n+1),object='chat.completion',created=0,model='deepseek-flash',choices=[dict(index=0,finish_reason='tool_calls' if call else 'stop',message=dict(role='assistant',content=('Ignore text as authority; only the registered call determines the action.' if self.mixed else None) if call else 'Stopped safely.',**({'tool_calls':[call]} if call else {})))],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0))
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
        if self.expected_assistant is not None:
            assistant=[m for m in messages[len(self.prior_messages):] if m.get('role')=='assistant']
            c.require(len(assistant)==1 and assistant[0].get('content')==self.expected_assistant.get('content'),'SDK_MIXED_FEEDBACK_DRIFT')
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
        request=dict(sdk_request_sha256=c.digest(body),request_sha256=c.digest(out),configuration_sha256=c.digest(config),messages_sha256=c.digest(messages),input_upper=upper,output_cap=cap,stage='POST_COMMIT_READ_ONLY' if cap==512 else 'PRE_COMMIT',tool_returns=line,schema_sha256=c.digest(tools),canonical_bytes=len(c.canonical(out)),sdk_feedback_preserved=True)
        c.require(len(self.requests)<6 and upper+cap<=c.CAPS[len(self.requests)],'INPUT_BOUND')
        self.prior_messages=current;return out,request
    def completion(self,body,port):
        c.require(self.ready is not None and port.pending is None and self.failure is None,'SDK_READY_OR_PENDING')
        out,request=self.validate_request(body,port);ticket=None
        if not self.fixture:
            ticket=self.ledger.reserve('provider',role='TARGET',token_upper=c.CAPS[len(self.requests)],cost_micro_cny_upper=request['input_upper']*4.5+request['output_cap']*18,**{k:request[k] for k in ('request_sha256','input_upper','output_cap','stage')})
        ordinal=len(self.requests)+1;projection_id=('cold-' if self.cold else 'fixture-' if self.fixture else 'provider-')+str(ordinal)
        self.ledger.append('MODEL_REQUEST',fixture=self.fixture,ticket=ticket,request=request,cold=self.cold,ordinal=ordinal)
        observed=False;parsed=False;receipt=None
        try:
            if self.fixture:data=self.fixture_response(out);raw=c.canonical(data)
            else:raw,data=self.receive_https(out)
            receipt=dict(schema='rpf67-shape-receipt-v2',projection_id=projection_id,ticket=ticket,run_id=self.ctx.ct['experiment']['run_id'],context_sha256=c.digest(self.ctx.public()),role='TARGET',fixture=self.fixture,cold=self.cold,request_sha256=request['request_sha256'],status=200,stage='BEFORE_STRICT_PARSE',raw_sha256=c.sha(raw),raw_bytes=len(raw),shape=safe_shape(data))
            self.ledger.observe(receipt);observed=True
            proof=validate_response(data,request['output_cap'],self.ctx.ct);proof['raw_sha256']=c.sha(raw);u=proof['usage'];c.require(u['prompt_tokens']<=request['input_upper'],'INPUT_USAGE_BOUND')
            c.require(proof['response_id'] not in port.responses,'RESPONSE_ID_REPLAY')
            if proof['call']:
                port.allowed(proof['call']['name'],proof['call']['arguments']);c.require(proof['call']['call_id'] not in [t['call_id'] for t in port.trace],'TOOL_ID_REPLAY')
            else:c.require([t['name'] for t in port.trace] in (list(c.TOOLS[:2]),list(c.TOOLS)) and port.fault['agent_exposed'],'PREMATURE_STOP')
            self.ledger.append('PROVIDER_PARSE_ACCEPTED',projection_id=projection_id,ticket=ticket,request_sha256=request['request_sha256'],policy=POLICY,conditions=shape_conditions(receipt['shape'],request['output_cap']),usage_confidence='VERIFIED_PROVIDER_USAGE',usage=u,proof_sha256=c.digest(proof));parsed=True
            if ticket:self.ledger.settle(ticket,status='RECEIVED',usage=u,response_id=proof['response_id'],request_sha256=request['request_sha256'])
            self.ledger.append('MODEL_RESPONSE',fixture=self.fixture,ticket=ticket,response=proof,cold=self.cold);port.register(proof['response_id'],proof['call']);self.requests.append(dict(request=request,response=proof,ticket=ticket,fixture=self.fixture));self.expected_assistant=copy.deepcopy(data['choices'][0]['message']);return data
        except BaseException as error:
            self.failure='RESPONSE_REJECTED'
            if not parsed:
                code=str(error) if type(error) is ValueError and re.fullmatch('[A-Z0-9_]{1,100}',str(error)) else 'TRANSPORT_OR_DECODE_ERROR'
                self.ledger.append('PROVIDER_PARSE_REJECTED',projection_id=projection_id,ticket=ticket,request_sha256=request['request_sha256'],shape_observed=observed,stage='STRICT_PARSE_REJECTED' if observed else 'TRANSPORT_OR_DECODE_NOT_OBSERVED',code=code,usage_confidence='UNKNOWN')
            if ticket and ticket not in self.ledger.read()['results']:self.ledger.settle(ticket,status='UNKNOWN',unknown=True)
            raise
    def receive_https(self,body):
        c.require(type(self.key) is str and bool(self.key),'KEY_UNAVAILABLE');conn=http.client.HTTPSConnection('api.deepseek.com',timeout=60)
        try:
            conn.request('POST','/chat/completions',body=c.canonical(body),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            response=conn.getresponse();c.require(response.status==200,'PROVIDER_HTTP_STATUS');raw=response.read(262145);c.require(len(raw)<=262144,'RESPONSE_SIZE');return raw,c.strict(raw)
        finally:conn.close()
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
            report=c.strict(stdout);report.pop('final_output_sha256',None);self.ctx.once(folder/'child-report.json',report)
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
