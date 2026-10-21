"""RPF-60 real HTTP transport tests; Provider and business disabled."""
import json,threading,time,unittest,uuid,http.client
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import lab_cross_domain_contracts as c
from runtime.runproof_runtime.effectwitness.lab_cross_domain_projection import CrossDomainStore,reviewed,SCHEMA
from runtime.runproof_runtime.effectwitness.lab_gateway import Gateway
from runtime.runproof_runtime.effectwitness.lab_store import LabError

class GatewayTests(unittest.TestCase):
 def setUp(self):
  self.root=c.WORK/'tests'/('http-'+uuid.uuid4().hex);self.entered=threading.Event();self.release=threading.Event();self.calls=0
  def runner():
   self.calls+=1;self.entered.set();self.release.wait(5);self.store.checkpoint()
   with self.store.lock:self.store.state['status']='INCONCLUSIVE';self.store._save()
  self.store=CrossDomainStore(enabled=True,root=self.root,runner=runner)
  self.fake=type('OldFrozenStore',(),{'cross_domain':self.store})();self.server=Gateway(0,'t'*32,'http://127.0.0.1:4185',self.fake)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.gate=patch.object(self.store,'_gate',return_value={});self.gate.start()
  self.base='/effectwitness-api/cross-domain';self.rid=str(uuid.uuid4());self.body={'mode':'RPF60_CONTROLLED_LIVE','request_id':self.rid,'nonce':self.store.nonce,'confirm_cost_and_simulation':True}
 def tearDown(self):
  self.release.set();self.store.close();self.gate.stop();self.server.shutdown();self.server.server_close();self.thread.join()
 def call(self,path,method='GET',body=None,headers=None):
  h={'Authorization':'Bearer '+'t'*32,'Origin':'http://127.0.0.1:4185','Content-Type':'application/json'}
  if headers:h.update(headers)
  raw=json.dumps(body).encode() if body is not None else None
  conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
  conn.request(method,self.base+path,raw,h);r=conn.getresponse();data=r.read();code=r.status;conn.close()
  return code,json.loads(data)
 def test_real_http_auth_origin_size_type_and_paths(self):
  self.assertEqual(self.call('/capabilities')[0],200)
  for headers,code in [({'Authorization':''},401),({'Origin':'https://evil.example'},403),({'Sec-Fetch-Site':'cross-site'},403),({'Host':'evil.example'},403)]:
   self.assertEqual(self.call('/sessions','POST',self.body,headers)[0],code)
  self.assertEqual(self.call('/sessions','POST',self.body,{'Content-Type':'text/plain'})[0],415)
  self.assertEqual(self.call('/sessions','POST',{'x':'x'*1200})[0],413)
  self.assertEqual(self.call('/sessions/not-valid')[0],404)
  self.assertEqual(self.call('/unknown')[0],404)
  self.assertEqual(self.call('/sessions','POST',self.body|{'path':'arbitrary'})[0],400)
  self.assertEqual(self.call('/sessions','POST',self.body|{'nonce':'wrong'})[0],403)
  self.assertEqual(self.call('/sessions','POST',self.body|{'confirm_cost_and_simulation':False})[0],400)
  self.assertEqual(self.calls,0)
 def test_one_reservation_request_recovery_cancel_restart(self):
  code,s=self.call('/sessions','POST',self.body);self.assertEqual(code,202);self.assertTrue(self.entered.wait(3));sid=s['session_id']
  self.assertEqual(self.call('/sessions','POST',self.body)[1]['session_id'],sid)
  self.assertEqual(self.call('/requests/'+self.rid)[1]['session_id'],sid)
  self.assertEqual(self.call('/sessions','POST',self.body|{'nonce':'different'})[0],409)
  self.assertEqual(self.call('/sessions','POST',self.body|{'request_id':str(uuid.uuid4())})[0],409)
  self.assertEqual(self.call('/sessions/'+sid+'/witness')[0],409)
  cancelled=self.call('/sessions/'+sid+'/cancel','POST',{})[1];self.assertTrue(cancelled['cancel_requested']);self.assertEqual(cancelled['status'],'CANCEL_REQUESTED')
  self.release.set();self.store.thread.join(5);self.assertEqual(self.store.get(sid)['status'],'CANCELLED');self.assertEqual(self.calls,1)
  self.store.close();restored=CrossDomainStore(enabled=True,root=self.root)
  try:self.assertEqual(restored.get(sid)['status'],'CANCELLED');self.assertEqual(restored.capabilities()['remaining_sessions'],0)
  finally:restored.close()
 def test_restart_unresolved_and_second_process_lock(self):
  with self.assertRaises(LabError):CrossDomainStore(root=self.root)
  code,s=self.call('/sessions','POST',self.body);self.release.set();self.store.thread.join(5)
  with self.store.lock:self.store.state['status']='RUNNING';self.store._save()
  self.store.close();restored=CrossDomainStore(root=self.root)
  try:self.assertEqual(restored.get(s['session_id'])['status'],'RECONCILE_REQUIRED');self.assertEqual(restored.capabilities()['remaining_sessions'],0)
  finally:restored.close()
 def test_reviewed_anchor_projection_and_unavailable_gate(self):
  x=reviewed();self.assertEqual(x['source'],'REVIEWED');self.assertEqual(x['session_id'],'rpf59-session-966ab13e1fdf471d')
  self.assertEqual(x['witness']['sha256'],'0bb359ca78c7c0415afef30ff959d41112da3f5155e5ae18e68be28735f9996a')
  self.assertEqual(self.call('/reviewed/rpf-59')[0],200)
  self.assertFalse(x['rows'][1]['fault']['triggered'])
  with patch.object(self.store,'_gate',side_effect=LabError(409,'SOURCE_DRIFT')):
   self.assertFalse(self.call('/capabilities')[1]['enabled']);self.assertEqual(self.call('/sessions','POST',self.body)[0],409)
  self.assertEqual(self.calls,0)
if __name__=='__main__':unittest.main()
