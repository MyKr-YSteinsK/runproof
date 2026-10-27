"""Owner-gated adapters around the existing local business and read-only authority."""
from contextlib import nullcontext
from . import pge_r74_contracts as c
from . import pge_r68_contracts as native
from .pge_r68_config_port import ConfigPort as NativeConfig
from .pge_r68_order_port import OrderPort as NativeOrder, Bridge, Reader
from .orders import OrderSandbox, OrderAdapter

class Sandbox(OrderSandbox):
    def __init__(self, ctx, ct):
        ctx.validate(ct)
        self.contracts = Bridge(ctx, ct)
        self.owner = self.storage_task = c.OWNER
        self.directory = ctx.scope(ctx.folder(ct) / 'business')
        self.path = ctx.scope(self.directory / 'orders.sqlite3')
        self.created, self.generation = False, 0

class AdapterMixin:
    def _setup(self, ctx, ct, ledger):
        ctx.validate(ct)
        c.require(ledger.ctx is ctx and ct['experiment']['domain'] == self.domain, 'PORT_BINDING')
        self.r74_ctx, self.r74_ct, self.r74_ledger = ctx, ct, ledger
        self.r74_calls = []

    def _operation(self, phase, tool):
        if self.r74_ledger.active is not None:
            c.require(self.r74_ledger.active['domain'] == self.domain, 'NESTED_DOMAIN')
            return nullcontext()
        return self.r74_ledger.authorized(phase, domain=self.domain, tool=tool)

    def invoke_real(self, proof):
        c.require(type(proof) is dict and set(proof) == {'response_id','call_id','name','arguments'}, 'CALL_SHAPE')
        name, args = proof['name'], proof['arguments']
        self.r74_ledger.check_tool(self.r74_ct, name, args, proof['response_id'], proof['call_id'])
        expected = list(native.TOOLS[self.domain][:2] if self.domain == c.DOMAINS[1] else native.TOOLS[self.domain])
        previous = [x['name'] for x in self.r74_calls]
        if len(previous) < len(expected):
            c.require(name == expected[len(previous)], 'TOOL_ORDER')
        else:
            allowed = 'inspect_config' if self.domain == c.DOMAINS[0] else 'reconcile_order'
            c.require(self.domain in self.r74_ledger.unknown_domains and len(previous) == len(expected) and name == allowed,
                      'READ_ONLY_RECONCILE_ONLY')
        # Mark the call before the side effect; no retry is permitted on exceptions.
        self.r74_ledger.completed_tool(self.r74_ct, name, proof['response_id'], proof['call_id'])
        with self.r74_ledger.authorized('business', domain=self.domain, tool=name, args=args,
                                        response_id=proof['response_id'], call_id=proof['call_id']):
            result = self._business(name, args)
        row = dict(**proof, result=result, result_sha256=c.digest(result))
        self.r74_calls.append(row)
        return result

    def mark_unknown(self):
        self.r74_ledger.unknown_domains.add(self.domain)
        if self.domain == c.DOMAINS[0]:
            self.client.stop_writes = True

class ConfigPort(AdapterMixin, NativeConfig):
    domain = c.DOMAINS[0]

    def prepare(self, ctx, ct, ledger):
        self._setup(ctx, ct, ledger)
        with ledger.authorized('prepare', domain=self.domain, tool='prepare'):
            super().prepare(ctx, ct, ledger)

    def authority(self, phase):
        c.require(phase in ('BEFORE', 'FINAL', 'AGENT_RECONCILE'), 'AUTHORITY_PHASE')
        with self._operation('authority', phase):
            return super().authority(phase)

    def _business(self, name, args):
        return self.business_api.invoke(name, args)

    def finish(self):
        return super().finish()

    def cleanup(self):
        with self._operation('cleanup', 'cleanup'):
            return super().cleanup()

class OrderPort(AdapterMixin, NativeOrder):
    domain = c.DOMAINS[1]

    def prepare(self, ctx, ct, ledger):
        self._setup(ctx, ct, ledger)
        with ledger.authorized('prepare', domain=self.domain, tool='prepare'):
            self.prepare_common(ctx, ct, ledger)
            self.sandbox = Sandbox(ctx, ct)
            self.reader, self.adapter = Reader(self.sandbox), OrderAdapter(self.sandbox)
            ticket = ledger.reserve('sqlite_setup')
            self.sandbox.initialize()
            ledger.settle(ticket, status='CREATED')
            self.before = self.authority('BEFORE')

    def authority(self, phase):
        c.require(phase in ('BEFORE', 'FINAL', 'AGENT_RECONCILE'), 'AUTHORITY_PHASE')
        with self._operation('authority', phase):
            return super().authority(phase)

    def _business(self, name, args):
        if name == 'refund_order':
            ticket = self.ledger.reserve('sqlite_refund', domain=self.domain, round=2,
                                         arguments_sha256=c.digest(args))
            result = self.adapter.invoke(name, args)
            c.require(result.get('status') == 'COMMITTED', 'REAL_REFUND_COMMIT')
            self.ledger.settle(ticket, status='COMMITTED', receipt=result)
            return result
        return super().business(name, args)

    def finish(self):
        return super().finish()

    def cleanup(self):
        with self._operation('cleanup', 'cleanup'):
            return super().cleanup()
