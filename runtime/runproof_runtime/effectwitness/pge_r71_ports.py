"""Narrow executed gates around the frozen native Port and business methods."""
from . import pge_r71_contracts as c
from . import pge_r71_owner_source as s
from .pge_r71_capability import Gate
from .pge_r68_driver import Port
from .pge_r68_config_port import ConfigPort as NativeConfig
from .pge_r68_order_port import OrderPort as NativeOrder, Bridge, Reader
from .orders import OrderSandbox, OrderAdapter

class Sandbox(OrderSandbox):
    def __init__(self, ctx, ct):
        ctx.validate(ct)
        self.contracts, self.owner, self.storage_task = Bridge(ctx, ct), c.OWNER, c.OWNER
        self.directory = ctx.scope(ctx.folder(ct) / 'business')
        self.path = ctx.scope(self.directory / 'orders.sqlite3')
        self.created, self.generation = False, 0

class Guarded:
    def __init__(self, gate):
        c.require(type(gate) is Gate, 'GATE_REQUIRED')
        self.gate = gate

    def prepare(self, ctx, ct, ledger, *, operation=None):
        from .pge_r71_budget_ledger import BudgetLedger
        c.require(type(ledger) is BudgetLedger and ctx._writer_owner is ledger, 'BUDGET_LEDGER_REQUIRED')
        ledger.policy.check(ctx)
        c.require(type(getattr(self, 'gate', None)) is Gate, 'GATE_REQUIRED')
        g = self.gate
        c.require(g.ctx is ctx and g.ledger is ledger and c.canonical(g.ct) == c.canonical(ct)
                  and ct['experiment']['domain'] == self.domain, 'PORT_GATE_BINDING')
        op = operation if operation is not None else g.operation('prepare')
        g.authorize(op, 'prepare')
        g.prepared = True
        # Dynamic dispatch of authority during native prepare also crosses this gate.
        super().prepare(ctx, ct, ledger)
        g.complete(op, dict(prepared=True, before_sha256=c.digest(self.before)))

    def allowed(self, name, args):
        self.gate.enter('allowed', role='TARGET', tool=name, args=args)
        return super().allowed(name, args)

    def invoke(self, value, *, operation=None):
        g = self.gate
        c.require(self.pending is not None and value == {k: self.pending[k] for k in ('call_id', 'name', 'arguments')}, 'TOOL_LINEAGE')
        op = operation if operation is not None else g.operation('invoke', role='TARGET', tool=value['name'], args=value['arguments'],
                     response_id=self.pending['response_id'], call_id=value['call_id'])
        g.authorize(op, 'invoke', role='TARGET', tool=value['name'], args=value['arguments'],
                    response_id=self.pending['response_id'], call_id=value['call_id'])
        g.active = op
        try:
            result = super().invoke(value)
            g.used_ids.add((op.public()['response_id'], value['call_id']))
            g.unknown |= result.get('status') == 'UNKNOWN_OUTCOME'
            g.complete(op, result)
            return result
        finally:
            g.active = None

    def business(self, name, args):
        op = self.gate.begin_business(name, args)
        result = super().business(name, args)
        self.gate.complete(op, result)
        return result

    def authority(self, phase):
        op = self.gate.enter('authority', tool=phase)
        result = super().authority(phase)
        self.gate.complete(op, result)
        return result

    def cleanup(self):
        op = self.gate.enter('cleanup')
        result = super().cleanup()
        self.gate.complete(op, result)
        self.gate.closed = True
        return result

class ConfigPort(Guarded, NativeConfig):
    pass

class OwnedOrder(NativeOrder):
    def prepare(self, ctx, ct, ledger):
        self.prepare_common(ctx, ct, ledger)
        self.sandbox = Sandbox(ctx, ct)
        self.reader, self.adapter = Reader(self.sandbox), OrderAdapter(self.sandbox)
        ticket = ledger.reserve('sqlite_setup')
        self.sandbox.initialize()
        ledger.settle(ticket, status='CREATED')
        self.before = self.authority('BEFORE')

class OrderPort(Guarded, OwnedOrder):
    pass

def adapter(ctx, ct, ledger):
    c.require(type(ctx) is s.Context and ct['experiment']['domain'] in c.DOMAINS, 'PORT_DOMAIN')
    gate = Gate(ctx, ct, ledger)
    return (ConfigPort if ct['experiment']['domain'] == c.DOMAINS[0] else OrderPort)(gate)
