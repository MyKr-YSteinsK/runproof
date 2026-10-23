"""Free production-path SQLite/Host/Verifier and reanchored semantic controls."""
import copy, importlib.util, json, secrets, subprocess, sys, unittest
from pathlib import Path
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_r67_context as c
from runtime.runproof_runtime.effectwitness import pge_r67_session as s
from runtime.runproof_runtime.effectwitness import pge_r67_order_verify as v
from runtime.runproof_runtime.effectwitness.pge_r67_order_port import OrderPort
from runtime.runproof_runtime.effectwitness.pge_r67_order_driver import Driver, ScriptDriver, validate_response

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
    return rows

class RPF67Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.witness=s.synthetic();cls.safe=s.synthetic(reconcile=False)
    def test_production_sqlite_reconcile(self):
        result=v.verify(self.witness);self.assertTrue(result['optional_reconcile']);self.assertEqual(result['provider_requests'],0)
    def test_safe_stop_and_controller_readback(self):self.assertFalse(v.verify(self.safe)['optional_reconcile'])
    def test_semantic_reanchored_controls(self):
        rows=controls(self.witness);self.assertGreaterEqual(len(rows),30)
        for label,candidate in rows:
            with self.subTest(label=label):
                with self.assertRaises(Exception):v.verify_bytes(c.canonical(candidate),c.digest(candidate))
    def test_cli_0_2_3(self):
        root=c.ROOT/'.local/rpf-67/tests'/secrets.token_hex(8);root.mkdir();path=root/'synthetic.json';raw=c.canonical(self.witness);path.write_bytes(raw)
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
        denied=[];files=[];root=c.ROOT/'.local/rpf-67';guard=m._guard_events(23456,root,root,[Path(sys.base_prefix)],path,denied,files)
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

if __name__=='__main__':unittest.main()
