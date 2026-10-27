"""Focused fail-closed tests; no real business, provider or SDK child."""
import secrets
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from runtime.runproof_runtime.effectwitness import pge_r74_contracts as c
from runtime.runproof_runtime.effectwitness import pge_r68_contracts as n
from runtime.runproof_runtime.effectwitness.pge_r74_owner_source import Context, OwnerScope, SourceCapsule
from runtime.runproof_runtime.effectwitness.pge_r74_budget_gate import BudgetLedger
from runtime.runproof_runtime.effectwitness.pge_r74_fault import Fault
from runtime.runproof_runtime.effectwitness.pge_r74_sdk_harness import Harness
from runtime.runproof_runtime.effectwitness.pge_r74_launch_contract import LaunchRequest

class R74ContractTests(unittest.TestCase):
    def context(self, scenario='N'):
        owner = OwnerScope('rpf74-'+secrets.token_hex(8))
        ctx = Context(owner, SourceCapsule.observe(), (31001,31002,31003), scenario)
        owner.root.mkdir(parents=True, exist_ok=False)
        return ctx

    def ledger(self):
        ctx = self.context()
        return ctx, BudgetLedger(ctx, create=True)

    def test_contract_identity(self):
        ctx=self.context(); self.assertEqual(ctx.public()['source_kind'], c.SOURCE_KIND)

    def test_owner_rejects_bad_id(self):
        with self.assertRaises(ValueError): OwnerScope('rpf73-old')

    def test_owner_rejects_parent_traversal(self):
        o=OwnerScope('rpf74-'+secrets.token_hex(8))
        with self.assertRaises(ValueError): o.path(o.root/'..'/'escape')

    def test_owner_rejects_other_task(self):
        o=OwnerScope('rpf74-'+secrets.token_hex(8))
        with self.assertRaises(ValueError): o.path(c.ROOT/'.local/rpf-73/wal.jsonl')

    def test_source_rejects_noncanonical(self):
        with self.assertRaises(ValueError): SourceCapsule(b'{ "x":1}').public()

    def test_source_rejects_duplicate_keys(self):
        with self.assertRaises(ValueError): c.strict(b'{"x":1,"x":2}')

    def test_context_rejects_duplicate_ports(self):
        with self.assertRaises(ValueError): Context(OwnerScope('rpf74-'+secrets.token_hex(8)),SourceCapsule.observe(),(1,1,1),'N')

    def test_context_rejects_unknown_scenario(self):
        with self.assertRaises(ValueError): Context(OwnerScope('rpf74-'+secrets.token_hex(8)),SourceCapsule.observe(),(31001,31002,31003),'X')

    def test_context_rejects_contract_edit(self):
        ctx=self.context(); ct=ctx.public()['rounds'][0];ct['effect']['required_version']=3
        with self.assertRaises(ValueError): ctx.validate(ct)

    def test_native_wal_rejects_ungated_writer(self):
        ctx,ledger=self.ledger()
        with self.assertRaises(ValueError): ledger._native.reserve('session')

    def test_ledger_rejects_second_writer(self):
        ctx,ledger=self.ledger()
        with self.assertRaises(ValueError): BudgetLedger(ctx)

    def test_ledger_rejects_no_active_operation(self):
        ctx,ledger=self.ledger()
        with self.assertRaises(ValueError): ledger.reserve('session')

    def test_provider_resource_forbidden(self):
        ctx,ledger=self.ledger()
        with ledger.authorized('session',domain=c.DOMAINS[0],tool='session'):
            with self.assertRaises(ValueError): ledger.reserve('provider')

    def test_wrong_domain_resource_rejected(self):
        ctx,ledger=self.ledger()
        with ledger.authorized('prepare',domain=c.DOMAINS[0],tool='prepare'):
            with self.assertRaises(ValueError): ledger.reserve('sqlite_setup')

    def test_wrong_phase_resource_rejected(self):
        ctx,ledger=self.ledger()
        with ledger.authorized('select',domain=c.DOMAINS[0],tool='select_experiment'):
            with self.assertRaises(ValueError): ledger.reserve('jvm',domain=c.DOMAINS[0],round=1)

    def test_ticket_replay_rejected(self):
        ctx,ledger=self.ledger()
        with ledger.authorized('session',domain=c.DOMAINS[0],tool='session'):
            ticket=ledger.reserve('session'); ledger.settle(ticket,status='COMPLETED')
            with self.assertRaises(ValueError): ledger.settle(ticket,status='COMPLETED')

    def test_invalid_settlement_rejected(self):
        ctx,ledger=self.ledger()
        with ledger.authorized('session',domain=c.DOMAINS[0],tool='session'):
            ticket=ledger.reserve('session')
            with self.assertRaises(ValueError): ledger.settle(ticket,status='FORGED')

    def test_bool_amount_rejected(self):
        ctx,ledger=self.ledger();ct=ctx.public()['rounds'][1];args=n.args_for(ct,'refund_order');args['amount_minor']=True
        with self.assertRaises(ValueError): ledger.check_tool(ct,'refund_order',args,'r','c')

    def test_wrong_domain_tool_rejected(self):
        ctx,ledger=self.ledger();ct=ctx.public()['rounds'][0]
        with self.assertRaises(ValueError): ledger.check_tool(ct,'refund_order',{},'r','c')

    def test_duplicate_call_rejected(self):
        ctx,ledger=self.ledger();ct=ctx.public()['rounds'][1];args=n.args_for(ct,'inspect_order')
        ledger.check_tool(ct,'inspect_order',args,'r','c');ledger.completed_tool(ct,'inspect_order','r','c')
        with self.assertRaises(ValueError): ledger.check_tool(ct,'inspect_order',args,'r','c')

    def test_write_once_rejected(self):
        ctx,ledger=self.ledger();ct=ctx.public()['rounds'][1];args=n.args_for(ct,'refund_order')
        ledger.completed_tool(ct,'refund_order','r','c')
        with self.assertRaises(ValueError): ledger.check_tool(ct,'refund_order',args,'r2','c2')

    def test_unknown_stops_write(self):
        ctx,ledger=self.ledger();ct=ctx.public()['rounds'][1];ledger.unknown_domains.add(c.DOMAINS[1])
        with self.assertRaises(ValueError): ledger.check_tool(ct,'refund_order',n.args_for(ct,'refund_order'),'r','c')

    def test_unknown_allows_readonly_reconcile(self):
        ctx,ledger=self.ledger();ct=ctx.public()['rounds'][1];ledger.unknown_domains.add(c.DOMAINS[1])
        ledger.check_tool(ct,'reconcile_order',n.args_for(ct,'reconcile_order'),'r','c')

    def test_fault_cannot_trigger_before_commit(self):
        f=Fault('F',c.DOMAINS[1])
        with self.assertRaises(ValueError): f.suppress('refund_order','x',{'status':'REJECTED'})

    def test_fault_cannot_observe_without_trigger(self):
        with self.assertRaises(ValueError): Fault('F',c.DOMAINS[1]).observe('x','RemoteDisconnected')

    def test_fault_cannot_expose_without_observation(self):
        f=Fault('F',c.DOMAINS[1]);f.suppress('refund_order','x',{'status':'COMMITTED'})
        with self.assertRaises(ValueError): f.expose('x',{'status':'UNKNOWN_OUTCOME'})

    def test_fault_state_order(self):
        f=Fault('F',c.DOMAINS[1]);f.suppress('refund_order','x',{'status':'COMMITTED'})
        f.observe('x','RemoteDisconnected');f.expose('x',{'status':'UNKNOWN_OUTCOME'})
        self.assertTrue(all(f.public()[k] for k in ('planned','triggered','observed','agent_exposed')))

    def test_normal_fault_never_suppresses(self):
        f=Fault('N',c.DOMAINS[1]);self.assertFalse(f.suppress('refund_order','x',{'status':'COMMITTED'}))

    def test_internal_http_response_really_drops(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
        owner=OwnerScope('rpf74-'+secrets.token_hex(8))
        ctx=Context(owner,SourceCapsule.observe(),(31001,31002,port),'F')
        owner.root.mkdir(parents=True,exist_ok=False)
        ledger=BudgetLedger(ctx,create=True);ct=ctx.public()['rounds'][1]
        class FixturePort:
            domain=c.DOMAINS[1]
            unknown=False
            def invoke_real(self, value): return {'status':'COMMITTED','fixture_only':True}
            def mark_unknown(self): self.unknown=True
        fixture=FixturePort();host=Harness(ctx,ct,ledger,fixture,{'cfg':{'port':port,'token':'fixture'}})
        call=dict(response_id='response-1',call_id='call-1',name='refund_order',arguments=n.args_for(ct,'refund_order'))
        host.pending=call;host.start()
        try:
            payload={k:call[k] for k in ('call_id','name','arguments')}
            result=host.callback(payload,c.canonical(payload))
            self.assertEqual(result['status'],'UNKNOWN_OUTCOME')
            self.assertTrue(fixture.unknown and host.fault.triggered and host.fault.observed)
            self.assertFalse(host.fault.agent_exposed)
        finally:
            self.assertTrue(all(host.close().values()))

    def test_slot_rejects_oversized_input(self):
        ctx,ledger=self.ledger();ct=ctx.public()['rounds'][0]
        with self.assertRaises(ValueError): ledger.claim_slot(ct,'TARGET',{},10000,512)

    def test_round_two_requires_feedback(self):
        ctx,ledger=self.ledger();ct=ctx.public()['rounds'][1]
        with self.assertRaises(ValueError): ledger.claim_slot(ct,'TARGET',{},1,512)

    def test_real_cli_admission_rejects_reanchored_wrong_owner(self):
        ctx=self.context();ct=ctx.public()['rounds'][1]
        launch=LaunchRequest.build(ctx,ct).public()
        bundle=dict(context=ctx.public(),domain=c.DOMAINS[1],launch=launch)
        path=ctx.root/'admission.json';path.write_bytes(c.canonical(bundle))
        def call():
            return subprocess.run([sys.executable,'-X','utf8','-B','-m','spikes.rpf-74.probe','admit',
                                   str(path),'--sha256',c.sha(path.read_bytes())],cwd=c.ROOT,
                                  capture_output=True,timeout=30).returncode
        self.assertEqual(call(),0)
        bundle['launch']['owner']='rpf-73';path.write_bytes(c.canonical(bundle))
        self.assertEqual(call(),3)

if __name__=='__main__': unittest.main()
