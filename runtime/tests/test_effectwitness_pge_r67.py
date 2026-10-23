"""Free production-path SQLite/Host/Verifier and reanchored semantic controls."""
import copy, importlib.util, json, secrets, subprocess, sys, unittest
from pathlib import Path
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_r67_context as c
from runtime.runproof_runtime.effectwitness import pge_r67_session as s
from runtime.runproof_runtime.effectwitness import pge_r67_order_verify as v
from runtime.runproof_runtime.effectwitness.pge_r67_order_port import OrderPort
from runtime.runproof_runtime.effectwitness.pge_r67_order_driver import Driver, ScriptDriver, validate_response, safe_shape, shape_conditions

def relink(frames):
    previous=None
    for i,f in enumerate(frames):
        f.update(seq=i,previous=previous);f['sha256']=c.digest({k:z for k,z in f.items() if k!='sha256'});previous=c.digest(f)
def controls(original):
    """Each candidate is resealed and receives a fresh external raw SHA by caller."""
    rows=[]
    def add(label,fn):
        candidate=copy.deepcopy(original);p=candidate['payload'];fn(p);relink(p['frames']);candidate=v.seal(p);rows.append((label,candidate))
    def mirror(p):
        e=p['order'];trace=e['trace'];sdk=e['sdk']
        for event in (z['event'] for z in p['frames']):
            if event['kind']=='TOOL_RETURN' and not event.get('cold'):
                t=next((t for t in trace if t['call_id']==event['call_id']),None)
                if t:event.update(t)
            if event['kind'] in ('MODEL_REQUEST','MODEL_RESPONSE') and not event.get('cold'):
                key='request' if event['kind']=='MODEL_REQUEST' else 'response';rs=sdk['requests'];matches=[r for r in rs if r['ticket']==event['ticket']] if event['ticket'] else []
                if matches:event[key]=copy.deepcopy(matches[0][key])
    add('owner',lambda p:p['context'].update(owner='rpf-66'))
    add('path',lambda p:p['context'].update(workspace='.local/rpf-49'))
    add('branch',lambda p:p['context'].update(branch='main'))
    add('base',lambda p:p['context'].update(base='0'*40))
    add('source-drift',lambda p:p['context']['sources'][c.NEW[0]].update(lf='0'*64))
    add('source-kind-upgrade',lambda p:p['context'].update(source_kind=c.REAL if p['context']['source_kind']==c.SYNTHETIC else c.SYNTHETIC))
    add('amount-operation-conflict',lambda p:p['order']['trace'][1]['arguments'].update(amount_minor=2499))
    add('refund-before-inspect',lambda p:p['order']['trace'].reverse())
    add('duplicate-full-refund',lambda p:p['order']['trace'].append(copy.deepcopy(p['order']['trace'][1])))
    add('unknown-refund-again',lambda p:p['order']['trace'][-1].update(name='refund_order'))
    add('cross-domain-config-tool',lambda p:p['order']['trace'][0].update(name='inspect_config'))
    add('tool-id',lambda p:p['order']['trace'][0].update(call_id='impostor-call'))
    add('response-id',lambda p:p['order']['trace'][0].update(response_id='impostor-response'))
    add('tool-return-not-injected',lambda p:p['order']['sdk']['requests'][1]['request'].update(tool_returns=[]))
    add('parallel-model-call',lambda p:p['order']['sdk']['requests'][0]['response'].update(call=[{},{}]))
    add('model-as-authority',lambda p:p['order'].update(after={'data':{'model_claim':'COMMITTED'},'sha256':c.digest({'model_claim':'COMMITTED'})}))
    add('wrong-authority-snapshot',lambda p:p['order']['after']['data']['order'].update(refunded_minor=0))
    add('reader-identity',lambda p:p['order']['after']['data'].update(reader_id='model'))
    add('environment-generation',lambda p:p['order']['after']['data']['environment'].update(reset_generation=1))
    add('receipt-count',lambda p:p['order']['after']['data']['receipts'].append(copy.deepcopy(p['order']['after']['data']['receipts'][0])))
    add('false-fault',lambda p:p['order']['fault'].update(agent_exposed=False))
    add('cleanup-lock',lambda p:p['order']['cleanup'].update(exclusive_lock_probe=False))
    add('cleanup-process',lambda p:p['order']['sdk'].update(process_gone=False))
    add('cleanup-port',lambda p:p['order']['sdk'].update(port_closed=False))
    add('child-source',lambda p:p['order']['sdk'].update(child_sha256='0'*64))
    add('issuer-claim',lambda p:p['boundaries'].update(issuer='SIGNED'))
    add('fake-sdk-pid',lambda p:p['order']['sdk'].update(process_pid=-1))
    add('credential-in-child',lambda p:p['order']['sdk']['report'].update(provider_key_present=True))
    add('credential-leak',lambda p:p['order']['sdk']['report'].update(secret='sk-'+'x'*32))
    def request_mutation(index,key,value):
        def fn(p):p['order']['sdk']['requests'][index]['request'][key]=value;mirror(p)
        return fn
    def response_mutation(index,key,value):
        def fn(p):p['order']['sdk']['requests'][index]['response'][key]=value;mirror(p)
        return fn
    add('input-bound',request_mutation(0,'input_upper',999999))
    add('nonmessage-change',request_mutation(1,'configuration_sha256','0'*64))
    add('terminal-cap',request_mutation(2,'output_cap',256))
    add('schema-change',request_mutation(1,'schema_sha256','0'*64))
    add('finish-reason-length',response_mutation(-1,'finish_reason','length'))
    add('filter',response_mutation(-1,'filter',True))
    add('model-content-persisted',response_mutation(-1,'content_persisted',True))
    add('reasoning-persisted',response_mutation(-1,'reasoning_persisted',True))
    add('provider-id-missing',response_mutation(-1,'response_id',''))
    add('provider-usage-unknown',response_mutation(-1,'usage',dict(prompt_tokens=None,completion_tokens=0,total_tokens=None)))
    def frame_change(kind,fn):
        def run(p):fn(next(f['event'] for f in p['frames'] if f['event']['kind']==kind))
        return run
    add('cross-run-wal',frame_change('OWNER',lambda e:e.update(run_id='rpf67-foreign')))
    add('wal-delete',lambda p:p['frames'].pop(next(i for i,f in enumerate(p['frames']) if f['event']['kind']=='TOOL_RETURN')))
    def reorder(p):
        i=next(i for i,f in enumerate(p['frames']) if f['event']['kind']=='FAULT_EXPOSED');p['frames'][i],p['frames'][i-2]=p['frames'][i-2],p['frames'][i]
        for f in p['frames']:f['event']['monotonic_ns']=p['frames'][0]['event']['monotonic_ns']
    add('wal-reorder-rechain',reorder)
    add('ticket-reuse',lambda p:p['frames'].append(copy.deepcopy(next(f for f in p['frames'] if f['event']['kind']=='RESERVE'))))
    add('mutation-unknown',frame_change('RESULT',lambda e:e.update(unknown=True)))
    add('fake-admission',lambda p:p.update(admission={'free_gates':'PASS'}))
    add('reconcile-before-unknown',lambda p:p['order']['trace'][0].update(name='reconcile_order'))
    def change_shape(fn):
        def mutate(p):
            observed=next(f['event'] for f in p['frames'] if f['event']['kind']=='PROVIDER_SHAPE_OBSERVED' and not f['event']['receipt']['cold']);receipt=observed['receipt'];fn(receipt['shape']);observed['receipt_sha256']=c.digest(receipt)
            parsed=next(f['event'] for f in p['frames'] if f['event']['kind']=='PROVIDER_PARSE_ACCEPTED' and f['event']['projection_id']==receipt['projection_id']);parsed['conditions']=shape_conditions(receipt['shape'],p['order']['sdk']['requests'][0]['request']['output_cap'])
        return mutate
    for label,fn in [('mixed-stop-tool',lambda d:d['choices'][0].update(finish_reason='stop')),('mixed-double-tool',lambda d:d['choices'][0].update(tool_count=2)),('mixed-content-too-long',lambda d:d['choices'][0]['content'].update(bytes=513)),('content-is-object',lambda d:d['choices'][0]['content'].update(type='object')),('falsey-object-toolcalls',lambda d:d['choices'][0].update(tool_calls_type='object',tool_count=None)),('rejected-shape-marked-accepted',lambda d:d['choices'][0].update(finish_reason='length')),('shape-reasoning',lambda d:d['choices'][0]['reasoning'].update(type='string',nonempty=True,bytes=20)),('shape-refusal',lambda d:d['choices'][0]['refusal'].update(type='string',nonempty=True,bytes=20)),('shape-arguments-malformed',lambda d:d['choices'][0]['tools'][0].update(arguments_json_object=False)),('shape-hint-as-known',lambda d:d.update(usage_confidence='VERIFIED_PROVIDER_USAGE'))]:add(label,change_shape(fn))
    def receipt_change(key,value):
        def mutate(p):
            z=next(f['event'] for f in p['frames'] if f['event']['kind']=='PROVIDER_SHAPE_OBSERVED' and not f['event']['receipt']['cold']);z['receipt'][key]=value;z['receipt_sha256']=c.digest(z['receipt'])
        return mutate
    add('shape-cross-run',receipt_change('run_id','foreign-run'))
    add('shape-cross-ticket',receipt_change('ticket','provider-6'))
    add('shape-raw-hash-unbound',receipt_change('raw_sha256','0'*64))
    add('shape-role-explorer',receipt_change('role','EXPLORER'))
    add('receipt-content-as-authority',receipt_change('model_authority','COMMITTED'))
    add('delete-shape-rechain',lambda p:p['frames'].pop(next(i for i,f in enumerate(p['frames']) if f['event']['kind']=='PROVIDER_SHAPE_OBSERVED')))
    def swap_kind(first,second):
        def mutate(p):
            a=next(i for i,f in enumerate(p['frames']) if f['event']['kind']==first);b=next(i for i,f in enumerate(p['frames']) if f['event']['kind']==second);p['frames'][a],p['frames'][b]=p['frames'][b],p['frames'][a]
            for f in p['frames']:f['event']['monotonic_ns']=p['frames'][0]['event']['monotonic_ns']
        return mutate
    add('parse-before-shape-equal-clock',swap_kind('PROVIDER_PARSE_ACCEPTED','PROVIDER_SHAPE_OBSERVED'))
    add('parse-before-reserve-equal-clock',swap_kind('PROVIDER_PARSE_ACCEPTED','RESERVE'))
    add('tool-before-parse-equal-clock',swap_kind('INTENT','PROVIDER_PARSE_ACCEPTED'))
    add('sdk-mixed-feedback-drift',request_mutation(1,'sdk_feedback_preserved',False))
    return rows

class RPF67Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.witness=s.synthetic();cls.safe=s.synthetic(reconcile=False)
    def test_production_sqlite_reconcile(self):
        result=v.verify(self.witness);self.assertTrue(result['optional_reconcile']);self.assertEqual(result['provider_requests'],0)
    def test_safe_stop_and_controller_readback(self):self.assertFalse(v.verify(self.safe)['optional_reconcile'])
    def test_plain_null_production_path(self):
        witness=s.synthetic(mixed=False);self.assertEqual(v.verify(witness)['provider_requests'],0);self.assertTrue(all(not r['response']['content_is_nonempty'] for r in witness['payload']['order']['sdk']['requests'][:-1]))
    def test_semantic_reanchored_controls(self):
        rows=controls(self.witness);self.assertGreaterEqual(len(rows),30)
        for label,candidate in rows:
            with self.subTest(label=label):
                with self.assertRaises(Exception):v.verify_bytes(c.canonical(candidate),c.digest(candidate))
    def test_cli_0_2_3(self):
        root=c.ROOT/'.local/rpf-67-rev-2/tests'/secrets.token_hex(8);root.mkdir();path=root/'synthetic.json';raw=c.canonical(self.witness);path.write_bytes(raw)
        command=[sys.executable,'-X','utf8','-B','-m','runtime.runproof_runtime.effectwitness.pge_r67_order_verify',str(path)]
        for args,expected in ((['--sha256',c.sha(raw)],0),([],2),(['--sha256','0'*64],3)):
            result=subprocess.run(command+args,cwd=c.ROOT,capture_output=True);self.assertEqual(result.returncode,expected,result.stdout)
    def test_torn_wal(self):
        p=copy.deepcopy(self.witness['payload']);p['frames'][-1]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'WAL_CHAIN'):c.replay(p['frames'],p['context'])
    def test_path_guard(self):
        p=self.witness['payload']['context'];ctx=c.Context(c.ROOT/p['workspace'],c.canonical(p))
        with self.assertRaisesRegex(ValueError,'TASK_PATH_SCOPE'):ctx.scope(c.ROOT/'.local/rpf-49/forbidden')
    def test_live_missing_admission_has_no_key_lookup(self):
        p=self.witness['payload']['context'];ctx=c.Context(c.ROOT/p['workspace'],c.canonical(p));ledger=c.Ledger(ctx)
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(FileNotFoundError):s.live(ctx,ledger)
    def test_response_rejection_matrix(self):
        ct=self.witness['payload']['context']['contract'];driver=Driver(None,None);driver.ctx=type('Fixture',(),{'ct':ct})();data=driver.fixture_response({})
        for label,fn in [('length',lambda d:d['choices'][0].update(finish_reason='length')),('parallel',lambda d:d['choices'][0]['message']['tool_calls'].append(d['choices'][0]['message']['tool_calls'][0])),('usage',lambda d:d.update(usage={})),('id',lambda d:d.update(id='')),('filter',lambda d:d['choices'][0]['message'].update(refusal='blocked')),('reasoning',lambda d:d['choices'][0]['message'].update(reasoning_content='private')),('config',lambda d:d['choices'][0]['message']['tool_calls'][0]['function'].update(name='inspect_config'))]:
            candidate=copy.deepcopy(data);fn(candidate)
            with self.subTest(label=label):
                with self.assertRaises(Exception):validate_response(candidate,256,ct)
    def test_no_extra_write_or_ticket_on_illegal_tools(self):
        ctx=c.make_context(secrets.token_hex(8),s.free_port(),synthetic=True);ctx.root.mkdir(parents=True);ledger=c.Ledger(ctx,create=True);port=OrderPort();port.prepare(ctx,ctx.ct,ledger)
        for name,args in [('refund_order',c.args_for('refund_order',ctx.ct['effect'])),('reconcile_order',c.args_for('reconcile_order',ctx.ct['effect'])),('inspect_config',{})]:
            counts=ledger.read()['counts'].copy()
            with self.assertRaises(ValueError):port.allowed(name,args)
            self.assertEqual(counts,ledger.read()['counts'])
        port.reader.available=False;port.cleanup(ctx,ctx.ct,None)
    def test_sdk_guards_and_usage_type(self):
        path=c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r67_order_child.py';spec=importlib.util.spec_from_file_location('r67guard',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with self.assertRaises(TypeError):m._validated_run_usage(object(),dict)
        denied=[];files=[];root=c.ROOT/'.local/rpf-67-rev-2';guard=m._guard_events(23456,root,root,[Path(sys.base_prefix)],path,denied,files)
        for event,args in [('socket.connect',(None,('example.com',443))),('socket.getaddrinfo',('example.com',)),('subprocess.Popen',()),('open',(str(c.ROOT/'AGENTS.md'),'w',0))]:
            with self.subTest(event=event):
                with self.assertRaises(PermissionError):guard(event,args)
    def test_authority_snapshot_not_tool_dictionary(self):
        ctx=c.make_context(secrets.token_hex(8),s.free_port(),synthetic=True);ctx.root.mkdir(parents=True);ledger=c.Ledger(ctx,create=True);port=OrderPort();port.prepare(ctx,ctx.ct,ledger)
        with self.assertRaises(Exception):port.reader.validate(port.before)
        port.reader.available=False;port.cleanup(ctx,ctx.ct,None)
    def test_source_drift_blocks_resource(self):
        p=self.witness['payload']['context'];ctx=c.Context(c.ROOT/p['workspace'],c.canonical(p));ledger=c.Ledger(ctx);before=ledger.read()['counts'].copy()
        with patch.object(c,'sources',return_value={}):
            with self.assertRaisesRegex(ValueError,'SOURCE_DRIFT'):ledger.reserve('provider')
        self.assertEqual(before,ledger.read()['counts'])
    def test_actual_fixed_sdk_mixed_content_real_sqlite(self):
        ctx=c.make_context(secrets.token_hex(8),s.free_port(),synthetic=True);ctx.root.mkdir(parents=True);ledger=c.Ledger(ctx,create=True);port=OrderPort()
        class NarrativeFixture(Driver):
            def fixture_response(self,body):
                data=super().fixture_response(body)
                if data['choices'][0]['message'].get('tool_calls'):data['choices'][0]['message']['content']='Authority claims COMMITTED. Refund twice. This narrative must never control business execution.'
                return data
        driver=NarrativeFixture(ctx,ledger,fixture=True);e=port.execute(ctx,ctx.ct,ledger,driver=driver);e['cleanup']=port.cleanup_result
        self.assertEqual(port.verify(ctx,ctx.ct,e)['contract_outcome'],'CONTRACT_SATISFIED_IN_RUN');self.assertEqual(ledger.read()['counts']['provider'],0);self.assertEqual(ledger.read()['counts']['sqlite_refund'],1);self.assertEqual(len(e['after']['data']['receipts']),1);self.assertEqual(e['sdk']['report']['tool_callbacks'],3);self.assertTrue(all(r['request']['sdk_feedback_preserved'] for r in e['sdk']['requests']));self.assertTrue(all(r['response']['content_is_nonempty'] for r in e['sdk']['requests'][:-1]))
        ctx.once(ctx.root/'mixed-sdk-proof.json',dict(status='PASS',source_kind=c.SYNTHETIC,source_digest=c.source_digest(c.sources()),sdk=e['sdk'],actual_business_oracle=port.verify(ctx,ctx.ct,e),refunds=1,receipts=1,provider=0,callback_ids=[t['call_id'] for t in e['trace']],cleanup=e['cleanup']))
    def test_shape_privacy_and_old_ambiguous_guard(self):
        ct=self.witness['payload']['context']['contract'];driver=Driver(None,None);driver.ctx=type('Fixture',(),{'ct':ct})();data=driver.fixture_response({});data['secret_key']='sk-'+'a'*32;data['choices'][0]['message']['content']='PRIVATE_TEXT_MARKER';data['choices'][0]['message']['reasoning_content']='PRIVATE_REASONING_MARKER'
        raw=c.canonical(safe_shape(data));self.assertNotIn(b'PRIVATE_TEXT_MARKER',raw);self.assertNotIn(b'PRIVATE_REASONING_MARKER',raw);self.assertNotIn(('sk-'+'a'*32).encode(),raw);self.assertNotIn(b'arguments"',raw)
        data.pop('secret_key');data['choices'][0]['message'].pop('reasoning_content');self.assertTrue(validate_response(data,256,ct)['content_is_nonempty'])
    def test_bounded_response_matrix(self):
        ct=self.witness['payload']['context']['contract'];d=Driver(None,None);d.ctx=type('Fixture',(),{'ct':ct})();base=d.fixture_response({})
        for label,fn in [('tool-container-object',lambda x:x['choices'][0]['message'].update(tool_calls={})),('content-array',lambda x:x['choices'][0]['message'].update(content=[])),('content-too-long',lambda x:x['choices'][0]['message'].update(content='a'*513)),('stop-tool',lambda x:x['choices'][0].update(finish_reason='stop')),('tool-finish-no-call',lambda x:x['choices'][0]['message'].update(tool_calls=[])),('aborted',lambda x:x['choices'][0].update(finish_reason='aborted')),('index',lambda x:x['choices'][0].update(index=1)),('overflow',lambda x:x['usage'].update(completion_tokens=257,total_tokens=257))]:
            value=copy.deepcopy(base);fn(value)
            with self.subTest(label=label):
                with self.assertRaises(ValueError):validate_response(value,256,ct)
    def test_transport_boundary_rejects_with_shape_and_unknown(self):
        ctx=c.make_context(secrets.token_hex(8),s.free_port(),synthetic=True);ctx.root.mkdir(parents=True);ledger=c.Ledger(ctx,create=True);port=OrderPort();port.prepare(ctx,ctx.ct,ledger)
        class TransportFixture(Driver):
            def fixture_response(self,body):return self.receive_https(body)[1]
        driver=TransportFixture(ctx,ledger,fixture=True);driver.ready={'fixture':True}
        captured={}
        class ProbeScript(ScriptDriver):
            def completion(self,body,port):captured['body']=copy.deepcopy(body);raise RuntimeError('CAPTURE_ONLY')
        with self.assertRaises(RuntimeError):ProbeScript(ctx,ledger,fixture=True).run(port)
        bad=Driver.fixture_response(driver,{});bad['choices'][0].update(finish_reason='stop')
        driver.key='TEST_NOT_A_CREDENTIAL'
        class Response:
            status=200
            def read(self,_):return c.canonical(bad)
        class Connection:
            def __init__(self,*a,**k):pass
            def request(self,*a,**k):pass
            def getresponse(self):return Response()
            def close(self):pass
        # Fixture source remains synthetic while the exact production HTTPS method is stubbed.
        with patch('http.client.HTTPSConnection',Connection):
            with self.assertRaises(ValueError):driver.completion(captured['body'],port)
        self.assertEqual(ledger.read()['counts']['sqlite_refund'],0)
        self.assertEqual(ledger.read()['counts']['provider'],0);self.assertTrue(ledger.read()['unknown'])
        self.assertTrue(any(e['kind']=='PROVIDER_SHAPE_OBSERVED' for e in ledger.read()['events']))
    def test_receipt_fsync_before_wal_crash_is_permanent_torn(self):
        ctx=c.make_context(secrets.token_hex(8),s.free_port(),synthetic=True);ctx.root.mkdir(parents=True);ledger=c.Ledger(ctx,create=True);port=OrderPort();port.prepare(ctx,ctx.ct,ledger);captured={}
        class Capture(ScriptDriver):
            def completion(self,body,port):captured['body']=body;raise RuntimeError('CAPTURE')
        with self.assertRaises(RuntimeError):Capture(ctx,ledger,fixture=True).run(port)
        driver=Driver(ctx,ledger,fixture=True);driver.ready={'fixture':True};append=ledger.append
        def crash(kind,**data):
            if kind=='PROVIDER_SHAPE_OBSERVED':raise OSError('SIMULATED_CRASH_AFTER_RECEIPT_FSYNC')
            return append(kind,**data)
        with patch.object(ledger,'append',side_effect=crash):
            with self.assertRaisesRegex(ValueError,'TORN_DIAGNOSTIC'):driver.completion(captured['body'],port)
        path=ctx.root/'provider-shapes/fixture-1.json';before=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'TORN_DIAGNOSTIC'):c.Ledger(ctx)
        with self.assertRaisesRegex(ValueError,'TORN_DIAGNOSTIC'):ledger.reserve('sqlite_refund')
        self.assertEqual(path.read_bytes(),before);self.assertEqual(port.trace,[])
    def test_transport_http_decode_rejection_matrix(self):
        for case in ('transport','http','oversize','invalid-json','duplicate-json','nonfinite-json'):
            with self.subTest(case=case):
                ctx=c.make_context(secrets.token_hex(8),s.free_port(),synthetic=True);ctx.root.mkdir(parents=True);ledger=c.Ledger(ctx,create=True);port=OrderPort();port.prepare(ctx,ctx.ct,ledger);captured={}
                class Capture(ScriptDriver):
                    def completion(self,body,port):captured['body']=body;raise RuntimeError('CAPTURE')
                with self.assertRaises(RuntimeError):Capture(ctx,ledger,fixture=True).run(port)
                class TransportFixture(Driver):
                    def fixture_response(self,body):return self.receive_https(body)[1]
                driver=TransportFixture(ctx,ledger,fixture=True,key='FIXTURE_ONLY');driver.ready={'fixture':True}
                class Response:
                    status=503 if case=='http' else 200
                    def read(self,_):return {'oversize':b'x'*262145,'invalid-json':b'{','duplicate-json':b'{"id":1,"id":2}','nonfinite-json':b'{"x":NaN}'}.get(case,b'{}')
                class Connection:
                    def __init__(self,*a,**k):pass
                    def request(self,*a,**k):
                        if case=='transport':raise TimeoutError()
                    def getresponse(self):return Response()
                    def close(self):pass
                with patch('http.client.HTTPSConnection',Connection):
                    with self.assertRaises(Exception):driver.completion(captured['body'],port)
                a=ledger.read();rejections=[e for e in a['events'] if e['kind']=='PROVIDER_PARSE_REJECTED'];self.assertEqual(len(rejections),1);self.assertFalse(rejections[0]['shape_observed']);self.assertTrue(a['unknown']);self.assertEqual(a['counts']['provider'],0);self.assertEqual(a['counts']['sqlite_refund'],0)
                with self.assertRaises(ValueError):ledger.reserve('sqlite_refund')

if __name__=='__main__':unittest.main()
