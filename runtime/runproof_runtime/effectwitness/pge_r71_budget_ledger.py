"""Policy proxy. Only native Ledger persists; no independent balance or WAL."""
from . import pge_r71_contracts as c
from . import pge_r71_owner_source as source
from . import pge_r71_budget_policy as p
from .pge_r68_budget import Ledger as NativeLedger

class BudgetLedger:
    def __init__(self,ctx,*,create=False,policy=None):
        c.require(type(ctx) is source.Context,'BUDGET_CONTEXT')
        self.ctx=ctx
        self.policy=policy if policy is not None else p.BudgetPolicy.create(ctx)
        c.require(type(self.policy) is p.BudgetPolicy,'TYPED_BUDGET_POLICY')
        self.policy.check(ctx)
        c.require(ctx._writer_owner is None,'ONE_BUDGET_WRITER')
        ctx._writer_owner=self
        with ctx.writer(self):self._native=NativeLedger(ctx,create=create)
        self.path=self._native.path
        self.read()

    @property
    def frames(self):return self._native.frames

    def read(self):
        state=self._native.read()
        p.audit(self.frames,self.ctx,self.policy)
        return state

    def append(self,kind,**data):
        c.require(kind not in ('RESERVE','RESULT'),'USE_POLICY_RESERVE_SETTLE')
        with self.ctx.writer(self):self._native.append(kind,**data)

    def receipt(self,*args,**kw):
        self.read()
        with self.ctx.writer(self):self._native.receipt(*args,**kw)

    def _perform(self,action,resource,ticket,parameters):
        self.ctx.check()
        state=self.read()
        request=dict(action=action,resource=resource,ticket=ticket,parameters=parameters)
        self.append('INTENT',audit_type=p.TAG,status='CHECK',request=request,
                    policy_sha256=self.policy.raw_sha256,source_capsule_sha256=self.ctx.source.raw_sha256)
        try:decision=p.decide(self.policy,self.ctx,state,state['events'],action,resource,ticket,parameters)
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            self.append('INTENT',audit_type=p.TAG,status='REJECTED',request_sha256=c.digest(request),reason=str(exc))
            raise
        self.append('INTENT',audit_type=p.TAG,status='GRANTED',decision=decision)
        with self.ctx.writer(self):
            if action=='RESERVE':actual_ticket=self._native.reserve(resource,**parameters);c.require(actual_ticket==ticket,'NATIVE_TICKET_PARITY')
            else:self._native.settle(ticket,**parameters)
        actual=self.frames[-1]
        self.append('INTENT',audit_type=p.TAG,status='CONFIRMED' if action=='RESERVE' else 'SETTLED',
                    decision_sha256=c.digest(decision),native_seq=actual['seq'],native_event_sha256=c.digest(actual['event']))
        return ticket

    def reserve(self,resource,**data):
        state=self.read()
        c.require(type(resource) is str and resource in state['counts'],'RESOURCE_ALLOWLIST')
        return self._perform('RESERVE',resource,resource+'-'+str(state['counts'][resource]+1),data)

    def settle(self,ticket,**data):
        state=self.read()
        c.require(type(ticket) is str and ticket in state['tickets'],'BUDGET_SETTLEMENT_TICKET')
        return self._perform('SETTLE',state['tickets'][ticket]['resource'],ticket,data)
