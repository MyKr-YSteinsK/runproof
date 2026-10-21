"""Pure synthetic RPF-62 protocol, accounting, unknown and rehashed tamper controls."""
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from runtime.runproof_runtime.effectwitness import pge_target_capability as c,pge_target_config_spike as b,pge_target_capability_verify as v
def registry():
    from runtime.runproof_runtime.effectwitness.config_live_contracts import TOOL_ARGUMENT_KEYS
    return [{'type':'function','function':{'name':n,'description':c.TOOL_HELP[n],'parameters':{'type':'object','properties':{k:{'type':'integer' if k=='expected_version' else 'string'} for k in TOOL_ARGUMENT_KEYS[n]},'required':list(TOOL_ARGUMENT_KEYS[n]),'additionalProperties':False},'strict':True}} for n in c.TOOLS]
class FakeHttp(b.BusinessHttp):
    def request(self,kind,*,reconcile=False):
        method,path,body=b._http_contract(self.effect,kind);c.require(method!='POST' or not self.stop_writes,'WRITE_AFTER_UNKNOWN')
        ticket=self.total.reserve('http',run_id=self.contracts['experiment']['run_id'],http_seq=len(self.observations)+1,operation=kind,method=method)
        if method=='POST':self.total.reserve('post',operation=kind,run_id=self.contracts['experiment']['run_id'])
        self.journal.add('HTTP_RESERVED',http_seq=len(self.observations)+1,method=method,operation=kind)
        def item(version):return {**{k:self.effect[k] for k in ('app','env','key')},'version':version,'value':'rpf53-v'+str(version),'description':None,'updatedAt':'2026-10-21T00:00:00Z'}
        initial=kind in ('initial_current','initial_history') or (kind=='inspect_config' and len(self.observations)==2)
        def history(version):
            row=item(version);row['createdAt']=row.pop('updatedAt');row.update(action='UPSERT',operator=None,reason=None);return row
        data=[] if kind=='initial_history' else None if initial else [history(2),history(1)] if kind.endswith('history') else [item(2)] if kind=='final_list' else item(1 if kind=='create_config_v1' else 2)
        status=404 if initial and kind!='initial_history' else 200;response={'code':4041 if status==404 else 0,'message':'synthetic','data':data,'traceId':None}
        o={'seq':len(self.observations)+1,'kind':kind,'method':method,'path':path,'request':body,'status':status,'content_type':'application/json','response':response,'response_body_sha256':c.digest(response),'elapsed_ms':0,'transport_error':None}
        self.observations.append(o);self.total.settle(ticket,status=status,response_sha256=o['response_body_sha256'],transport_error=None);self.journal.add('HTTP_COMPLETED',http_seq=o['seq'],status=status,response_sha256=o['response_body_sha256']);return o
def synthetic_payload():
    folder=c.WORK/'tests'/uuid.uuid4().hex;folder.mkdir(parents=True);total=c.TaskLedger(folder/'account',create=True)
    total.reserve('metadata');total.reserve('cold');total.token_pool();ct=c.contract('62'+'a'*16,45001,46001,c.digest(c.sources()),fixture=True)
    total.reserve('trial',run_id=ct['experiment']['run_id']);total.reserve('jvm');total.reserve('health');total.reserve('sdk')
    journal=b.Journal(total,ct['experiment']['run_id']);client=FakeHttp(ct,'synthetic-key',journal,total,9999999999);client.initial_state_valid()
    host=b.CapabilityHost(ct,b.ProviderLedger.fixture_only(journal.run_id),b.ConfigLiveBusiness(ct,client),journal,fixture=True)
    pin=c.pinned_sdk_fields();ready={'framework':'pydantic-ai-slim','version':'2.57.0','openai_version':'3.35.1','pid':1234,'python_executable_sha256':pin['python_executable_sha256'],'sdk_source_sha256':c.SDK_CORE_SHA256,'openai_source_sha256':pin['openai_core_sha256'],'sdk_site_root_binding_sha256':pin['sdk_site_root_binding_sha256'],'python_runtime_mapping_sha256':pin['python_runtime_mapping_sha256']}
    host._ready(ready);messages=[{'role':'system','content':ct['execution']['agent_instructions']},{'role':'user','content':ct['execution']['task_prompt']}]
    for _ in range(5):
        body={'model':'rpf53-fixture-only','messages':copy.deepcopy(messages),'tools':registry(),'tool_choice':'auto','parallel_tool_calls':False,'max_tokens':256}
        data=host._completion(body);msg=data['choices'][0]['message'];messages.append(msg)
        for call in msg.get('tool_calls',[]):
            result=host._tool({'call_id':call['id'],'name':call['function']['name'],'arguments':c.strict_json(call['function']['arguments'].encode())});messages.append({'role':'tool','tool_call_id':call['id'],'content':c.canonical(result).decode()})
    client.final_readback(reconcile=True);client.request('final_list')
    report={'status':'COMPLETED','pid':1234,'guard_denials':[],'provider_key_present':False,'business_key_present':False,'final_text_persisted':False,'tool_calls':4,'tool_callbacks':4,'requests':5,'input_tokens':0,'output_tokens':0}
    sdk={'popen_pid':1234,'ready':ready,'report':report,'returncode':0,'stderr_bytes':0}
    env={'source_level':'REAL_JAVA_H2_LOCAL_SIMULATION','authority':'SAME_SERVICE_READ_ONLY_HTTP','java_pid':5678,'jar_sha256':c.SOURCE_JAR_SHA256,'jar_bytes':c.SOURCE_JAR_BYTES,'listener_owned':True,'jar_command_verified':True,'health':[{'status':200,'body':{'status':'UP'}}],'cleanup':dict.fromkeys(('java_exited','java_port_closed','sdk_exited','host_port_closed','host_thread_stopped','local_key_released'),True)}
    s={'contracts':ct,'http':client.observations,'events':journal.events,'tool_trace':host.tool_trace,'completions':host.provider_responses,'visibility':host.visible_contract_checks,'sdk':sdk,'environment':env,'requests':[],'original_success':host.original_success,'host_failure':None}
    cold={'status':'PASS','sources':c.sources(),'source_kind':'FIXTURE_SCRIPTED','sdk':copy.deepcopy(sdk),'checks':{'synthetic':True}}
    return {'source_kind':'SYNTHETIC_TEST_ONLY','sources':c.sources(),'contracts':ct,'capture':s,'ledger':total.frames,'cold':cold,'boundaries':c.BOUNDARIES}
def mutations():
    def omit_budget(p):
        frames=[f for f in p['ledger'] if not (f['event']['kind']=='RESERVE' and f['event'].get('ticket')=='http-1') and not (f['event']['kind']=='RESULT' and f['event'].get('ticket')=='http-1')]
        previous=None
        for i,f in enumerate(frames):
            f.update(seq=i,previous=previous);f['sha256']=c.digest({k:v for k,v in f.items() if k!='sha256'});previous=c.digest(f)
        p['ledger']=frames
    return {'role_upgrade':lambda p:p.update(source_kind='REAL_PROVIDER_TARGET'),'fake_fault':lambda p:p['capture'].update(original_success=None),
        'duplicate_post':lambda p:p['capture']['http'].append(copy.deepcopy(p['capture']['http'][4])),
        'missing_readback':lambda p:p['capture']['http'].pop(),
        'future_feedback':lambda p:p['capture']['tool_trace'][2].update(returned_in_request=2),
        'old_run':lambda p:p['capture']['events'][0].update(run_id='rpf57-old'),
        'budget_omission':omit_budget,
        'call_id':lambda p:p['capture']['completions'][1]['tool_returns'][0].update(call_id='fake'),
        'source':lambda p:p['sources'].update({c.NEW_FILES[0]:'0'*64}),
        'cleanup':lambda p:p['capture']['environment']['cleanup'].update(java_exited=False),
        'false_reconcile':lambda p:p['capture']['http'][-2].update(kind='update_config_v2'),
        'cold_pid':lambda p:p['cold']['sdk'].update(popen_pid=42),
        'false_ack':lambda p:p['capture']['tool_trace'][2].update(result={'status':'COMMITTED'}),
        'authority':lambda p:p['capture']['environment'].update(authority='AGENT_SELF_REPORT'),
        'runtime_callable':lambda p:p['contracts']['capability'].update(callable='os.system')}
def controls(payload,folder):
    folder.mkdir(parents=True,exist_ok=False)
    def cli(raw,anchor):
        path=folder/'input.json';path.write_bytes(raw);args=[sys.executable,'-X','utf8','-B','-m','runtime.runproof_runtime.effectwitness.pge_target_capability_verify',str(path)]
        if anchor is not None:args+=['--sha256',anchor]
        env={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH') if k in os.environ};return subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30).returncode
    raw=c.canonical(v.seal(payload));codes=[cli(raw,hashlib.sha256(raw).hexdigest()),cli(raw,None),cli(raw,'0'*64)];c.require(codes==[0,2,3],'CLI_CODES')
    results={}
    for name,mutate in mutations().items():
        p=copy.deepcopy(payload);mutate(p);raw=c.canonical(v.seal(p));results[name]=cli(raw,hashlib.sha256(raw).hexdigest())
    c.require(set(results.values())=={3},'TAMPER_ACCEPTED');return {'correct_missing_wrong':codes,'rehashed_semantic_controls':results}
class CapabilityTests(unittest.TestCase):
    def test_synthetic_full_chain(self):self.assertEqual(v.verify_payload(synthetic_payload())['model_read_only_recovery'],'OBSERVED')
    def test_fifteen_rehashed_semantic_controls(self):
        p=synthetic_payload()
        for name,mutate in mutations().items():
            with self.subTest(name=name):
                bad=copy.deepcopy(p);mutate(bad);raw=c.canonical(v.seal(bad))
                with self.assertRaises(Exception):v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    def test_capability_static_and_no_role_authority_escalation(self):
        cap=c.capability(c.pinned_sdk_fields(),'a'*64)
        for key,val in (('provider_role','EXPLORER'),('driver_kind','os.system'),('resource_budgets',{})):
            bad=copy.deepcopy(cap);bad[key]=val
            with self.assertRaises(Exception):c.validate_capability(bad)
    def test_unknown_provider_no_more_requests(self):
        folder=c.WORK/'tests'/uuid.uuid4().hex;folder.mkdir(parents=True);total=c.TaskLedger(folder/'account',create=True);total.token_pool();broker=b.BrokerLedger(total,'rpf62-test')
        broker.reserve({'messages':[]},[])
        with self.assertRaises(Exception):broker.reserve({'messages':[]},[])
        self.assertEqual(total.read()['reserved']['provider'],1)
    def test_no_refund_restart_duplicate_pool_and_torn_wal(self):
        folder=c.WORK/'tests'/uuid.uuid4().hex;folder.mkdir(parents=True);total=c.TaskLedger(folder/'account',create=True);total.token_pool();total.reserve('trial')
        second=c.TaskLedger(total.path)
        with self.assertRaises(Exception):second.reserve('trial')
        with self.assertRaises(Exception):second.token_pool()
        (total.path/'frame-9999.json').write_bytes(b'{')
        with self.assertRaises(Exception):second.read()
    def test_scope_lock_and_body_budget(self):
        with self.assertRaises(Exception):c.scoped(c.ROOT/'outside')
        folder=c.WORK/'tests'/uuid.uuid4().hex;folder.mkdir(parents=True);total=c.TaskLedger(folder/'account',create=True);total.token_pool();(total.path/'mutation.lock').touch()
        with self.assertRaises(Exception):total.reserve('provider')
if __name__=='__main__':unittest.main()
