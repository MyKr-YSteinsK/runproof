"""Execution gate, carried in the single native WAL as tagged INTENT events."""
from dataclasses import dataclass
from . import pge_r72r3_contracts as c
from . import pge_r72r3_owner_source as s
from . import pge_r68_context as n

@dataclass(frozen=True, slots=True)
class AuthorizedOperation:
    frozen: bytes

    def public(self):
        c.require(type(self.frozen) is bytes, 'OPERATION_BYTES')
        value = c.strict(self.frozen)
        c.require(self.frozen == c.canonical(value), 'OPERATION_CANONICAL')
        return value

class Gate:
    def __init__(self, ctx, ct, ledger):
        c.require(type(ctx) is s.Context and ledger.ctx is ctx, 'GATE_CONTEXT')
        self.ctx, self.ct, self.ledger = ctx, ct, ledger
        self.writes, self.unknown, self.closed, self.prepared = set(), False, False, False
        self.active = None
        self.used_ids = set()

    def operation(self, phase, *, role='CONTROLLER', tool=None, args=None, response_id=None, call_id=None):
        e = self.ct['experiment']
        return AuthorizedOperation(c.canonical(dict(schema=c.VERSION, source_kind=c.KIND,
            owner=self.ctx.owner.public(), source_capsule=self.ctx.source.public(),
            source_capsule_sha256=self.ctx.source.raw_sha256, domain=e['domain'], role=role,
            round=e['round'], run_id=e['run_id'], environment_id=e['environment_id'],
            phase=phase, tool=tool or phase, arguments={} if args is None else args,
            arguments_sha256=c.digest({} if args is None else args), response_id=response_id,
            call_id=call_id, issuer=False, provider_calls=0)))

    def audit(self, status, operation, **data):
        self.ledger.append('INTENT', audit_type='RPF72R3_AUTHORIZATION', status=status,
                           operation=operation, operation_sha256=c.digest(operation), **data)

    def authorize(self, operation, phase, *, role='CONTROLLER', tool=None, args=None,
                  response_id=None, call_id=None):
        args = {} if args is None else args
        c.require(type(operation) is AuthorizedOperation, 'TYPED_OPERATION')
        value = operation.public()
        self.audit('CHECK', value)
        try:
            c.require(type(self.ctx) is s.Context and type(self.ctx.owner) is s.OwnerScope and
                      type(self.ctx.source) is s.SourceCapsule, 'TYPED_OWNER_SOURCE')
            self.ctx.validate(self.ct)
            c.require(phase in c.PHASES and role in c.ROLES and
                      self.ct['experiment']['domain'] in c.DOMAINS, 'OPERATION_ALLOWLIST')
            expected = self.operation(phase, role=role, tool=tool, args=args,
                                      response_id=response_id, call_id=call_id).public()
            c.equal(value, expected, 'OPERATION_IDENTITY')
            c.require(not self.closed, 'GATE_CLOSED')
            if phase == 'prepare':
                c.require(role == 'CONTROLLER' and not self.prepared, 'PREPARE_ONCE')
            elif phase in ('session', 'trial', 'driver'):
                c.require(role == 'CONTROLLER' and (phase != 'driver' or self.prepared), 'CONTROLLER_RESOURCE_SCOPE')
            elif phase == 'select':
                c.require(role == 'EXPLORER' and tool == 'select_experiment' and
                          args['candidate_id'] in n.CANDIDATES[self.ct['experiment']['round']-1], 'EXPLORER_READ_ONLY')
            else:
                c.require(self.prepared, 'PREPARE_REQUIRED')
            if phase in ('allowed', 'invoke', 'business'):
                c.require(role == 'TARGET' and tool in n.TOOLS[self.ct['experiment']['domain']], 'TARGET_DOMAIN_TOOL')
                c.equal(args, n.args_for(self.ct, tool), 'TOOL_ARGUMENTS')
                if tool in ('create_config_v1', 'update_config_v2', 'refund_order'):
                    c.require(not self.unknown and tool not in self.writes, 'UNKNOWN_OR_WRITE_ONCE')
                if phase in ('invoke', 'business'):
                    c.require(type(response_id) is str and bool(response_id) and type(call_id) is str and bool(call_id), 'RESPONSE_LINEAGE')
                if phase == 'invoke':
                    c.require((response_id, call_id) not in self.used_ids, 'OPERATION_REPLAY')
            if phase == 'authority':
                c.require(role == 'CONTROLLER' and tool in ('BEFORE', 'FINAL', 'AGENT_RECONCILE') and args == {}, 'INDEPENDENT_AUTHORITY')
            if phase == 'cleanup':
                c.require(role == 'CONTROLLER', 'CLEANUP_OWNER')
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            self.audit('REJECTED', value, reason=str(exc))
            raise
        self.audit('GRANTED', value)
        return operation

    def complete(self, operation, result):
        self.audit('COMPLETED', operation.public(), result_sha256=c.digest(result))

    def enter(self, phase, **kw):
        op = self.operation(phase, **kw)
        return self.authorize(op, phase, **kw)

    def begin_business(self, name, args):
        c.require(type(self.active) is AuthorizedOperation, 'NO_ACTIVE_OPERATION')
        value = self.active.public()
        op = self.enter('business', role='TARGET', tool=name, args=args,
                        response_id=value['response_id'], call_id=value['call_id'])
        if name in ('create_config_v1', 'update_config_v2', 'refund_order'):
            self.writes.add(name)
        return op
