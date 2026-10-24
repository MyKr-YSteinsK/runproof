"""Budget execution, bypass and crash fixtures; no SDK/Java/network."""
import copy
import secrets
import unittest
from unittest.mock import patch
from runtime.runproof_runtime.effectwitness import pge_r71_contracts as c,pge_r71_owner_source as s,pge_r71_budget_policy as p,pge_r68_context as n
from runtime.runproof_runtime.effectwitness.pge_r71_budget_ledger import BudgetLedger,NativeLedger
from runtime.runproof_runtime.effectwitness.pge_r71_capability import Gate
from runtime.runproof_runtime.effectwitness.pge_r71_ports import adapter,OwnedOrder

def setup(index=2,fault=False):
    ctx=s.Context(s.OwnerScope('rpf71-'+secrets.token_hex(8)),s.SourceCapsule.observe(),(29001,29002,29003));ctx.root.mkdir(parents=True)
    ledger=BudgetLedger(ctx,create=True);ct=ctx.contract(index,n.CANDIDATES[index-1][int(fault)]);gate=Gate(ctx,ct,ledger)
    return ctx,ct,ledger,gate

class BudgetTests(unittest.TestCase):
    def test_immutable_policy_strict_identity(self):
        ctx,_,l,_=setup();value=l.policy.public();value['actual_provider_limit']=False
        with self.assertRaisesRegex(ValueError,'POLICY_IDENTITY'):p.BudgetPolicy(c.canonical(value)).check(ctx)

    def test_native_direct_reserve_denied_before_wal_write(self):
        ctx,_,l,_=setup();before=l.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'NATIVE_WAL_WRITE_REQUIRES_BUDGET_GATE'):NativeLedger(ctx).reserve('sqlite_setup')
        self.assertEqual(l.path.read_bytes(),before)

    def test_native_direct_settle_and_append_denied(self):
        ctx,_,l,_=setup()
        with self.assertRaisesRegex(ValueError,'NATIVE_WAL_WRITE_REQUIRES_BUDGET_GATE'):NativeLedger(ctx).settle('fake',status='COMMITTED')
        with self.assertRaisesRegex(ValueError,'USE_POLICY_RESERVE_SETTLE'):l.append('RESERVE',resource='sqlite_setup',ticket='sqlite_setup-1')

    def test_no_operation_no_sqlite_setup(self):
        ctx,_,l,_=setup()
        with self.assertRaisesRegex(ValueError,'CURRENT_OWNER_OPERATION_REQUIRED'):l.reserve('sqlite_setup')
        self.assertEqual(NativeLedger(ctx).read()['counts']['sqlite_setup'],0)

    def test_session_reserve_settle_native_parity(self):
        ctx,_,l,g=setup();op=g.enter('session');ticket=l.reserve('session');l.settle(ticket,status='COMPLETED');g.complete(op,{'done':True})
        state=l.read();self.assertEqual(state['counts']['session'],1);self.assertEqual(len(p.audit(l.frames,ctx,l.policy)['transactions']),2)

    def test_duplicate_settlement_is_not_reclaimed(self):
        _,_,l,g=setup();g.enter('session');ticket=l.reserve('session');l.settle(ticket,status='COMPLETED')
        with self.assertRaisesRegex(ValueError,'BUDGET_SETTLEMENT_TICKET'):l.settle(ticket,status='COMPLETED')

    def test_resource_limit_session_once(self):
        _,_,l,g=setup();g.enter('session');l.reserve('session')
        with self.assertRaisesRegex(ValueError,'BUDGET_RESOURCE_LIMIT'):l.reserve('session')

    def test_unknown_refund_stops_new_writes(self):
        ctx,ct,l,g=setup();g.prepared=True;args=n.args_for(ct,'refund_order');g.enter('business',role='TARGET',tool='refund_order',args=args,response_id='r',call_id='c')
        ticket=l.reserve('sqlite_refund',domain=n.DOMAINS[1],round=2);l.settle(ticket,status='UNKNOWN')
        with self.assertRaisesRegex(ValueError,'BUDGET_UNKNOWN_GLOBAL_STOP'):l.reserve('sqlite_refund',domain=n.DOMAINS[1],round=2)

    def test_unsettled_refund_stops_second_write(self):
        _,ct,l,g=setup();g.prepared=True;g.enter('business',role='TARGET',tool='refund_order',args=n.args_for(ct,'refund_order'),response_id='r',call_id='c');l.reserve('sqlite_refund')
        with self.assertRaisesRegex(ValueError,'BUDGET_RESOURCE_LIMIT|BUDGET_UNSETTLED_STOP'):l.reserve('sqlite_refund')

    def test_crash_check_before_reserve(self):
        ctx,_,l,g=setup();g.enter('session');l.append('INTENT',audit_type=p.TAG,status='CHECK',request=dict(action='RESERVE',resource='session',ticket='session-1',parameters={}),policy_sha256=l.policy.raw_sha256,source_capsule_sha256=ctx.source.raw_sha256)
        with self.assertRaisesRegex(ValueError,'ORPHAN_BUDGET_CHECK'):l.read()
        self.assertEqual(NativeLedger(ctx).read()['counts']['session'],0)

    def test_crash_native_reserve_before_confirmation(self):
        ctx,_,l,g=setup();g.enter('session')
        original=l.append
        def crash(kind,**data):
            if data.get('status')=='CONFIRMED':raise RuntimeError('CONTROLLED_CRASH')
            return original(kind,**data)
        with patch.object(l,'append',crash),self.assertRaisesRegex(RuntimeError,'CONTROLLED_CRASH'):l.reserve('session')
        self.assertEqual(NativeLedger(ctx).read()['counts']['session'],1)
        with self.assertRaisesRegex(ValueError,'ORPHAN_BUDGET_CHECK'):l.read()

    def test_valid_owner_missing_policy_does_not_enter_port(self):
        ctx,ct,l,g=setup();port=adapter(ctx,ct,l)
        with patch.object(OwnedOrder,'prepare') as native:
            with self.assertRaisesRegex(ValueError,'BUDGET_LEDGER_REQUIRED'):port.prepare(ctx,ct,NativeLedger(ctx))
            native.assert_not_called()

    def test_wrong_policy_does_not_enter_port(self):
        ctx,ct,l,g=setup();v=l.policy.public();v['global_tokens']=600001;l.policy=p.BudgetPolicy(c.canonical(v))
        with patch.object(OwnedOrder,'prepare') as native:
            with self.assertRaisesRegex(ValueError,'POLICY_IDENTITY'):adapter(ctx,ct,l).prepare(ctx,ct,l)
            native.assert_not_called()

    def test_component_eleven_slots_permanent_native_caps(self):
        ctx,_,_,_=setup();obj=p.provider_component(ctx);self.assertEqual(obj['reserved_tokens'],474000);self.assertEqual(obj['counts']['provider'],11);self.assertEqual(obj['provider_network_calls'],0)
        p.verify_component(obj,ctx)

    def test_component_rejects_slot_and_price_forgery(self):
        ctx,_,_,_=setup();obj=p.provider_component(ctx)
        for path in ('input_upper','output_cap','slot_cap','ordinal'):
            mutated=copy.deepcopy(obj);mutated['slots'][0][path]=True
            with self.assertRaisesRegex(ValueError,'COMPONENT_REFERENCE_PARITY'):p.verify_component(mutated,ctx)

    def test_junction_and_torn_receipt(self):
        import _winapi
        ctx,_,l,_=setup();target=ctx.root/'target';target.mkdir();link=ctx.root/'junction';_winapi.CreateJunction(str(target),str(link))
        with self.assertRaisesRegex(ValueError,'OWNER_LINK'):ctx.scope(link/'file')
        folder=ctx.root/'receipts';folder.mkdir();(folder/'orphan.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'TORN_RECEIPT'):l.read()

    def _order(self,fault):
        ctx,ct,l,_=setup(fault=fault);port=adapter(ctx,ct,l);port.prepare(ctx,ct,l)
        names=['inspect_order','refund_order']+(['reconcile_order'] if fault else [])
        try:
            for i,name in enumerate(names):
                proof=dict(response_id='unit-response-'+str(i),call=dict(call_id='unit-call-'+str(i),name=name,arguments=n.args_for(ct,name)))
                port.register(proof);result=port.invoke(proof['call'])
                if name=='refund_order':self.assertEqual(result['status'],'UNKNOWN_OUTCOME' if fault else 'COMMITTED')
            out=port.finish();self.assertEqual(len(out['after']['data']['receipts']),1)
            self.assertEqual(out['after']['data']['receipts'][0]['amount_minor'],2500)
        finally:self.assertTrue(all(port.cleanup().values()))
        self.assertEqual(l.read()['counts']['sqlite_refund'],1)
        self.assertEqual(p.audit(l.frames,ctx,l.policy)['status'],'PASS')

    def test_real_sqlite_normal_gate_and_policy(self):self._order(False)
    def test_real_sqlite_unknown_readonly_gate_and_policy(self):self._order(True)

    def test_boolean_round_and_unknown_parameter_rejected(self):
        for parameters,reason in ((dict(domain=n.DOMAINS[1],round=True),'BUDGET_ROUND_TYPE'),(dict(extra=1),'BUDGET_PARAMETER_FIELDS')):
            _,_,l,g=setup();g.enter('trial')
            with self.assertRaisesRegex(ValueError,reason):l.reserve('trial',**parameters)
