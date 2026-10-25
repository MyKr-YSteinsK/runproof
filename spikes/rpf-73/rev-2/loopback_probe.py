"""Read-only tracing of original test plus two explicitly independent contrasts."""
import argparse,http.client,io,os,socket,sys,threading,time,unittest
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from . import environment_contract as e
TARGET='runtime.tests.test_effectwitness_target_agent.TargetAgentTests.test_real_loopback_host_rejects_unauthenticated_tool_without_effect'
def destination():return Path(os.environ['RPF73R2_ENV_RECEIPT']).parent
def original():
 actual=e.observe_actual();events=[];lock=threading.Lock();started=time.monotonic();origin=sys.gettrace();thread_origin=threading.gettrace()
 def trace(frame,event,arg):
  module=frame.f_globals.get('__name__','');name=frame.f_code.co_name
  selected=(module=='http.client' and name in ('request','getresponse','read','close','_send_request','_read_status')) or (module=='runtime.runproof_runtime.effectwitness.target_driver' and name in ('run','do_POST')) or (module=='http.server' and name in ('send_response','end_headers','finish','handle_one_request'))
  if selected and event in ('call','return','exception'):
   row=dict(event=event,module=module,function=name,line=frame.f_lineno,thread_id=threading.get_ident(),elapsed=time.monotonic()-started)
   obj=frame.f_locals.get('self');server=getattr(obj,'server',None)
   if server is not None:row['port']=server.server_port
   if module=='http.client' and name in ('request','getresponse','close') and obj is not None:row['port']=getattr(obj,'port',None);row['host_is_loopback']=getattr(obj,'host',None)=='127.0.0.1'
   if event=='exception':row.update(error_type=type(arg[1]).__name__,winerror=getattr(arg[1],'winerror',None),errno=getattr(arg[1],'errno',None))
   if module=='http.server' and name=='send_response' and event=='call':row['status']=frame.f_locals.get('code')
   if module=='runtime.runproof_runtime.effectwitness.target_driver' and name=='run' and event=='return' and type(arg) is dict:row['failure_code']=(arg.get('failure') or {}).get('code')
   with lock:events.append(row)
  return trace
 try:
  sys.settrace(trace);threading.settrace(trace)
  suite=unittest.TestLoader().loadTestsFromName(TARGET);result=unittest.TextTestRunner(verbosity=2).run(suite)
 finally:sys.settrace(origin);threading.settrace(thread_origin)
 ports=sorted({r['port'] for r in events if type(r.get('port')) is int});cleanup=[]
 for port in ports:
  with socket.socket() as sock:sock.settimeout(.2);cleanup.append(dict(port=port,port_closed=sock.connect_ex(('127.0.0.1',port))!=0))
 report=dict(status='PASS' if result.wasSuccessful() else 'FAIL',test_id=TARGET,tests_run=result.testsRun,error_count=len(result.errors),failure_count=len(result.failures),actual_environment=actual,events=events,ports=cleanup,source_unchanged_instrumentation='sys/threading.settrace reads metadata only; no patched socket/http/test/Host, observer timing effect remains possible',win10053='REPRODUCED' if any(x.get('winerror')==10053 for x in events) else 'NOT_REPRODUCED_IN_THIS_ATTEMPT',cause='NOT_PROVEN',factory_child_starts=0)
 e.write_once(destination()/'loopback-original.json',report);print(e.canonical(dict(loopback_status=report['status'],win10053=report['win10053'],events=len(events),ports=cleanup)).decode());return 0 if result.wasSuccessful() else 1
def control(mode):
 e.require(mode in ('immediate','drain'),'CONTROL_MODE');actual=e.observe_actual();events=[];lock=threading.Lock();start=time.monotonic()
 def log(stage,**fields):
  with lock:events.append(dict(stage=stage,elapsed=time.monotonic()-start,**fields))
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   log('SERVER_REQUEST',port=self.server.server_port)
   if mode=='drain':size=int(self.headers.get('Content-Length','0'));raw=self.rfile.read(size);log('SERVER_BODY_DRAINED',bytes=len(raw))
   raw=b'{"error":"CONTROL_AUTH_REJECTED"}';self.send_response(400);self.send_header('Content-Length',str(len(raw)));self.end_headers();log('SERVER_HEADERS_SENT',status=400);self.wfile.write(raw);log('SERVER_BODY_SENT',bytes=len(raw))
  def finish(self):
   try:return super().finish()
   finally:log('SERVER_FINISH')
 server=HTTPServer(('127.0.0.1',0),Handler);port=server.server_port;thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.1});thread.start();connection=http.client.HTTPConnection('127.0.0.1',port,timeout=5);phase='request';error=None;status=None
 try:
  log('CLIENT_REQUEST');connection.request('POST','/tool',b'{}',{'Content-Type':'application/json'});phase='getresponse';log('CLIENT_GETRESPONSE');response=connection.getresponse();status=response.status;phase='read';log('CLIENT_READ',status=status);raw=response.read();log('CLIENT_BODY_READ',bytes=len(raw))
 except (OSError,http.client.HTTPException) as exc:error=dict(stage=phase,error_type=type(exc).__name__,winerror=getattr(exc,'winerror',None),errno=getattr(exc,'errno',None));log('CLIENT_EXCEPTION',**error)
 finally:
  connection.close();log('CLIENT_CLOSE');server.shutdown();server.server_close();thread.join(timeout=5)
 with socket.socket() as sock:sock.settimeout(.2);closed=sock.connect_ex(('127.0.0.1',port))!=0
 e.require(closed and not thread.is_alive(),'CONTROL_CLEANUP')
 report=dict(status='DIAGNOSTIC_COMPLETE',mode=mode,actual_environment=actual,events=events,client_status=status,exception=error,port=port,port_closed=closed,thread_gone=not thread.is_alive(),scope='INDEPENDENT_CONTRAST_NOT_OLD_HOST_PROOF',cause='NOT_PROVEN',factory_child_starts=0)
 e.write_once(destination()/'loopback-control.json',report);print(e.canonical(report).decode());return 0
def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True);sub.add_parser('original');control_parser=sub.add_parser('control');control_parser.add_argument('--mode',choices=('immediate','drain'),required=True);a=p.parse_args();return original() if a.action=='original' else control(a.mode)
if __name__=='__main__':raise SystemExit(main())
