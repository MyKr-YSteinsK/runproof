"""Owned loopback wire protocol and fsynced component lifecycle journal."""
import copy
from http.server import BaseHTTPRequestHandler,HTTPServer
import os
import re
import socket
import threading
from . import pge_r73_contracts as c
from .pge_r73_budget_view import BudgetView
from .pge_r73_domain_adapters import DomainAdapter,TOOLS

class Journal:
 def __init__(self,folder):self.path=c.scope(folder/'component.wal');self.frames=[];self.lock=threading.Lock()
 def append(self,kind,**fields):
  with self.lock:
   frame=dict(seq=len(self.frames)+1,previous=self.frames[-1]['sha256'] if self.frames else '0'*64,event=dict(kind=kind,**fields));frame['sha256']=c.digest(frame)
   with self.path.open('ab') as out:out.write(c.canonical(frame)+b'\n');out.flush();os.fsync(out.fileno())
   self.frames.append(frame)
 def raw_sha(self):return c.sha(self.path.read_bytes())

def ready_identity(pid):
 return dict(framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=pid,python_executable_sha256=c.PIN['python_executable_sha256'],sdk_source_sha256=c.PIN['sdk_source_sha256'],openai_source_sha256=c.PIN['openai_source_sha256'],sdk_site_root_binding_sha256=c.PIN['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=c.PIN['python_runtime_mapping_sha256'])

class Harness:
 def __init__(self,value,adapter,journal):
  c.require(type(adapter) is DomainAdapter and adapter.domain==value['domain'],'ADAPTER_BINDING')
  self.v=value;self.adapter=adapter;self.journal=journal;self.rows=[];self.callbacks=[];self.ready=None;self.pid=None;self.pending=None;self.failure=None;self.prior=None;self.configuration=None;self.server=None;self.thread=None
 def completion(self,body,raw):
  c.require(self.ready is not None and self.failure is None and self.pending is None,'HOST_STATE')
  allowed={'model','messages','tools','tool_choice','parallel_tool_calls','max_tokens','max_completion_tokens','stream','temperature','thinking'}
  c.require(type(body) is dict and set(body)<=allowed and body['model']=='deepseek-flash' and body['stream'] is False and body['parallel_tool_calls'] is False and body.get('tool_choice','auto')=='auto','SDK_BODY_POLICY')
  caps=set(body)&{'max_tokens','max_completion_tokens'};c.require(len(caps)==1 and type(body[next(iter(caps))]) is int and body[next(iter(caps))]==512,'SDK_OUTPUT_CAP')
  self.adapter.registry(body['tools']);messages=body['messages'];c.require(type(messages) is list and messages[:2]==[dict(role='system',content=self.adapter.instructions()),dict(role='user',content=self.adapter.prompt())],'SDK_INITIAL_PROMPT')
  configuration={k:v for k,v in body.items() if k not in ('messages','max_tokens','max_completion_tokens')}
  if self.configuration is not None:c.equal(configuration,self.configuration,'SDK_CONFIGURATION_DRIFT')
  self.configuration=copy.deepcopy(configuration)
  if self.prior is not None:c.equal(messages[:len(self.prior)],self.prior,'SDK_PREFIX_DRIFT')
  calls=[z for m in messages if m.get('role')=='assistant' for z in m.get('tool_calls',[])];returns=[m for m in messages if m.get('role')=='tool']
  c.require(len(calls)==len(returns)==len(self.callbacks),'SDK_RETURN_COUNT')
  for call,returned,callback in zip(calls,returns,self.callbacks):
   c.require(call['id']==returned['tool_call_id']==callback['call']['call_id'] and call['function']['name']==callback['call']['name'],'SDK_CALLBACK_LINEAGE')
   c.equal(c.strict(call['function']['arguments']),callback['call']['arguments'],'SDK_ARGUMENT_REINJECTION')
   c.require(type(returned['content']) is str and returned['content'].encode()==c.canonical(callback['result']),'SDK_RETURN_BYTES')
  n=len(self.rows)+1;suffix=messages if self.prior is None else messages[len(self.prior):]
  upper=len(c.canonical(body)) if not self.rows else self.rows[-1]['response']['usage']['prompt_tokens']+len(c.canonical(suffix))+512
  proof=BudgetView(self.v['domain']).request(n,upper)
  total=sum(r['response']['usage']['total_tokens'] for r in self.rows)
  response=self.adapter.response(self.v['run_id'],n,upper,total,self.v['pressure'])
  if not self.v['pressure'] or n<4:c.require(response['usage']['prompt_tokens']<=upper,'SYNTHETIC_HINT_INPUT_BOUND')
  call=response['choices'][0]['message'].get('tool_calls',[])
  if call:self.pending=dict(call_id=call[0]['id'],name=call[0]['function']['name'],arguments=c.strict(call[0]['function']['arguments']))
  else:c.require(len(self.callbacks)==3 and response['choices'][0]['finish_reason']=='stop','SDK_TERMINAL_STOP')
  row=dict(body=body,body_raw=raw.decode('utf-8'),body_raw_sha256=c.sha(raw),proof=proof,response=response,response_sha256=c.digest(response),tool_return_sha256=[c.digest(x['result']) for x in self.callbacks])
  self.rows.append(row);self.prior=copy.deepcopy(messages)
  self.journal.append('MODEL_EXCHANGE',ordinal=n,request_raw_sha256=row['body_raw_sha256'],request_sha256=c.digest(body),response_sha256=row['response_sha256'],usage_type='SYNTHETIC_VALIDATED_USAGE',proof=proof)
  return response
 def callback(self,value,raw):
  c.require(self.failure is None and self.ready is not None and self.pending is not None,'CALLBACK_STATE')
  c.equal(value,self.pending,'CALLBACK_PENDING_LINEAGE');c.require(len(self.callbacks)<3,'CALLBACK_LIMIT')
  c.require(value['call_id'] not in [x['call']['call_id'] for x in self.callbacks],'DUPLICATE_CALL_ID')
  result=self.adapter.result(value['name'],value['arguments']);row=dict(call=value,raw_sha256=c.sha(raw),result=result,result_sha256=c.digest(result));self.callbacks.append(row);self.pending=None
  self.journal.append('TOOL_RETURN',index=len(self.callbacks),call=value,request_raw_sha256=row['raw_sha256'],result_sha256=row['result_sha256'],business_effect=False)
  return result
 def start(self):
  host=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    try:
     self.connection.settimeout(5)
     c.require(host.failure is None and self.headers.get('Authorization')=='Bearer '+host.v['cfg']['token'] and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and self.headers.get('Origin') is None and self.headers.get('Transfer-Encoding') is None,'HOST_AUTH_ORIGIN')
     length=int(self.headers.get('Content-Length','0'));c.require(0<length<=262144,'HOST_BODY_SIZE');raw=self.rfile.read(length);c.require(len(raw)==length,'HOST_SHORT_READ');value=c.strict(raw)
     if self.path=='/ready':
      c.require(host.ready is None and type(host.pid) is int,'READY_ONCE');c.equal(value,ready_identity(host.pid),'ACTUAL_SDK_READY_PIN');host.ready=value;host.journal.append('READY',identity=value,raw_sha256=c.sha(raw));result={'ready':True}
     elif self.path=='/tool':result=host.callback(value,raw)
     else:c.require(self.path=='/v1/chat/completions','HOST_ROUTE');result=host.completion(value,raw)
     reply=c.canonical(result);self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(reply)));self.end_headers();self.wfile.write(reply)
    except BaseException as error:
     host.failure=str(error) if type(error) is ValueError and re.fullmatch('[A-Z0-9_]+',str(error)) else 'ADAPTER_ERROR'
     host.journal.append('ADAPTER_ERROR',code=host.failure,error_type=type(error).__name__)
     self.send_response(409);self.send_header('Content-Length','0');self.end_headers()
  self.server=HTTPServer(('127.0.0.1',self.v['cfg']['port']),Handler);self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.1},daemon=True);self.thread.start()
  self.journal.append('HOST_START',address='127.0.0.1',port=self.server.server_port)
 def close(self):
  if self.server:self.server.shutdown();self.server.server_close()
  if self.thread:self.thread.join(timeout=5)
  with socket.socket() as sock:sock.settimeout(.2);closed=sock.connect_ex(('127.0.0.1',self.v['cfg']['port']))!=0
  return dict(thread_gone=self.thread is None or not self.thread.is_alive(),port_closed=closed)
