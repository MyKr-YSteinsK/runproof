"""Focused owner/source, write-once, WAL and cleanup policy regressions."""
import copy
import importlib.util
import os
import secrets
import unittest
from pathlib import Path
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_r70_contracts as c, pge_r70_owner_source as s
from runtime.runproof_runtime.effectwitness import pge_r68_context as n
from runtime.runproof_runtime.effectwitness.pge_r70_capability import Gate, AuthorizedOperation
from runtime.runproof_runtime.effectwitness.pge_r70_ports import adapter, OrderPort
from runtime.runproof_runtime.effectwitness.pge_r68_budget import Ledger, replay

class Memory:
    def __init__(self, ctx):
        self.ctx, self.events = ctx, []
    def append(self, kind, **data):
        self.events.append(dict(kind=kind, **data))
    def reserve(self, resource, **data):
        ticket=resource+'-'+str(len(self.events))
        self.append('RESERVE',resource=resource,ticket=ticket,**data)
        return ticket
    def settle(self, ticket, **data):
        self.append('RESULT',ticket=ticket,**data)

def setup(index=2, fault=False):
    ctx = s.Context(s.OwnerScope('rpf70-'+secrets.token_hex(8)), s.SourceCapsule.observe(), (29001,29002,29003))
    ct = ctx.contract(index,n.CANDIDATES[index-1][int(fault)])
    ledger = Memory(ctx)
    return ctx, ct, ledger, Gate(ctx,ct,ledger)

class OwnerSourceTests(unittest.TestCase):
    def test_strict_owner_and_paths(self):
        owner = s.OwnerScope('rpf70-'+'a'*16)
        for value in ('r69-'+'a'*16,'rpf70-../old','rpf70-'+'g'*16,42):
            with self.assertRaises(ValueError):
                s.OwnerScope(value)
        for path in (s.ROOT/'AGENTS.md',owner.root/'../escape'):
            with self.assertRaises(ValueError):
                owner.path(path)

    def test_observed_source_rejects_raw_lf_alias(self):
        for key in ('raw','lf','origin'):
            value=s.identity();value['source_map'][s.NEW[0]][key]='forged'
            with self.assertRaisesRegex(ValueError,'SOURCE_DECLARED_OBSERVED'):
                s.SourceCapsule(c.canonical(value)).check()

    def test_context_owner_cannot_alias(self):
        ctx,ct,ledger,gate=setup()
        ctx.root=s.ROOT/'.local/rpf-68-rev-3'
        with self.assertRaisesRegex(ValueError,'CONTEXT_OWNER'):
            gate.enter('prepare')
        self.assertEqual(ledger.events[-1]['status'],'REJECTED')

    def test_prepare_requires_real_gate(self):
        with self.assertRaisesRegex(ValueError,'GATE_REQUIRED'):
            OrderPort(None)

    def test_prepare_wrong_owner_rejected_before_native(self):
        ctx,ct,ledger,gate=setup();op=gate.operation('prepare').public();op['owner']['owner']='rpf-69'
        with patch('runtime.runproof_runtime.effectwitness.pge_r70_ports.OwnedOrder.prepare') as native:
            with self.assertRaisesRegex(ValueError,'OPERATION_IDENTITY'):
                OrderPort(gate).prepare(ctx,ct,ledger,operation=AuthorizedOperation(c.canonical(op)))
            native.assert_not_called()

    def test_direct_business_has_no_authority(self):
        ctx,ct,ledger,gate=setup()
        with self.assertRaisesRegex(ValueError,'NO_ACTIVE_OPERATION'):
            OrderPort(gate).business('refund_order',n.args_for(ct,'refund_order'))

    def test_explorer_and_cross_domain_cannot_write(self):
        ctx,ct,ledger,gate=setup();gate.prepared=True
        for role,tool in (('EXPLORER','refund_order'),('TARGET','update_config_v2')):
            with self.assertRaisesRegex(ValueError,'TARGET_DOMAIN_TOOL'):
                gate.enter('allowed',role=role,tool=tool,args={})

    def test_unknown_and_once_never_reopen(self):
        for unknown in (False,True):
            ctx,ct,ledger,gate=setup();gate.prepared=True;gate.unknown=unknown
            if not unknown:gate.writes.add('refund_order')
            with self.assertRaisesRegex(ValueError,'UNKNOWN_OR_WRITE_ONCE'):
                gate.enter('invoke',role='TARGET',tool='refund_order',args=n.args_for(ct,'refund_order'),response_id='r',call_id='c')

    def test_replay_and_lineage(self):
        ctx,ct,ledger,gate=setup();gate.prepared=True;gate.used_ids.add(('r','c'))
        with self.assertRaisesRegex(ValueError,'OPERATION_REPLAY'):
            gate.enter('invoke',role='TARGET',tool='inspect_order',args=n.args_for(ct,'inspect_order'),response_id='r',call_id='c')
        with self.assertRaisesRegex(ValueError,'RESPONSE_LINEAGE'):
            gate.enter('invoke',role='TARGET',tool='inspect_order',args=n.args_for(ct,'inspect_order'))

    def test_actual_sqlite_commit_and_readonly_oracle(self):
        # Local unit fixture, no SDK/JVM/full-session resources; every run is fresh.
        ctx,ct,ledger,gate=setup();ctx.root.mkdir(parents=True)
        port=OrderPort(gate);port.prepare(ctx,ct,ledger)
        for i,name in enumerate(('inspect_order','refund_order')):
            proof=dict(response_id='unit-response-'+str(i),call=dict(call_id='unit-call-'+str(i),name=name,arguments=n.args_for(ct,name)))
            port.register(proof);port.invoke(proof['call'])
        business=port.finish();self.assertEqual(len(business['after']['data']['receipts']),1)
        self.assertEqual(business['after']['data']['receipts'][0]['amount_minor'],2500)
        self.assertTrue(all(port.cleanup().values()));self.assertFalse(port.reader.available)

    def test_torn_wal_and_owner_tamper(self):
        ctx,ct,_,_=setup();ctx.root.mkdir(parents=True);ledger=Ledger(ctx,create=True)
        frames=copy.deepcopy(ledger.frames);frames[0]['event']['context_sha256']='0'*64
        frames[0]['sha256']=c.digest({k:v for k,v in frames[0].items() if k!='sha256'})
        with self.assertRaisesRegex(ValueError,'WAL_OWNER'):
            replay(frames,ctx.public())
        with ledger.path.open('ab') as f:f.write(b'{')
        with self.assertRaisesRegex(ValueError,'TORN_WAL'):
            ledger.read()

    def test_closed_cleanup_and_source_readback(self):
        ctx,ct,ledger,gate=setup();gate.prepared=True
        gate.enter('cleanup');gate.closed=True
        with self.assertRaisesRegex(ValueError,'GATE_CLOSED'):
            gate.enter('authority',tool='FINAL')

    def test_real_junction_rejected(self):
        import _winapi
        owner=s.OwnerScope('rpf70-'+secrets.token_hex(8));owner.root.mkdir(parents=True)
        target=owner.path(owner.root/'target');target.mkdir();link=owner.root/'junction'
        _winapi.CreateJunction(str(target),str(link))
        with self.assertRaisesRegex(ValueError,'OWNER_LINK'):
            owner.path(link/'file')

    def test_strict_types_and_no_issuer(self):
        ctx,ct,ledger,gate=setup();op=gate.operation('prepare').public();op['provider_calls']=False
        with self.assertRaisesRegex(ValueError,'OPERATION_IDENTITY'):
            gate.authorize(AuthorizedOperation(c.canonical(op)),'prepare')
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON_KEY'):
            c.strict('{"owner":1,"owner":2}')

    def test_process_wal_pid_reanchor_cannot_hide(self):
        from runtime.runproof_runtime.effectwitness.pge_r70_verify import verify_processes
        result=dict(rounds=[dict(evidence=dict(sdk=dict(pid=11),business=dict(environment=dict(pid=33)))),dict(evidence=dict(sdk=dict(pid=22)))],late=dict(processes=[]))
        events=[]
        for i,(resource,pid) in enumerate((('sdk',11),('sdk',22),('jvm',33))):
            start=dict(kind='PROCESS_START',resource=resource,pid=pid,round=1 if pid!=22 else 2,domain='unit',clock=i)
            events.extend([start,dict(start,kind='PROCESS_CLEANUP',process_gone=True,port_closed=True,key_reference_released=True)])
            result['late']['processes'].append(dict(resource=resource,pid=pid,wal_start_clock=i,original_gone=True))
        verify_processes(result,events)
        events[0]['pid']=1
        with self.assertRaisesRegex(ValueError,'PROCESS_WAL_IDENTITY'):
            verify_processes(result,events)
