"""Fail-closed authorization around the existing single native WAL."""
from contextlib import contextmanager
from . import pge_r74r2_contracts as c
from . import pge_r68_contracts as native
from .pge_r68_budget import Ledger as NativeLedger
from .pge_r74r2_owner_source import Context
from .pge_r74r2_slot_contract import slot

VERSION = 'rpf74r2-budget-policy-v1'
TAG = 'RPF74R2_BUDGET'
AUTH = 'RPF74R2_AUTHORIZATION'
RESOURCE_PHASES = {
    'provider': ('model',),
    'session': ('session',), 'trial': ('trial',), 'sdk': ('driver',), 'host': ('driver',),
    'jvm': ('prepare', 'cleanup'), 'sqlite_setup': ('prepare',), 'sqlite_refund': ('business',),
    'config_post': ('business',), 'config_http': ('business', 'authority', 'prepare'),
    'config_health': ('prepare',), 'authority_read': ('authority', 'prepare', 'business'), 'explorer_calls': ('select',),
}
SAFE_READ = frozenset(('authority_read', 'config_health'))
STATUSES = dict(session=('COMPLETED','UNKNOWN'), trial=('VERIFIED','UNKNOWN'), sdk=('COMPLETED','UNKNOWN'),
                host=('CLOSED','UNKNOWN'), jvm=('CLOSED','UNKNOWN'), sqlite_setup=('CREATED','UNKNOWN'),
                sqlite_refund=('COMMITTED','UNKNOWN'), config_post=('COMMITTED','UNKNOWN'),
                config_http=('RECEIVED','UNKNOWN'), config_health=('READ_ONLY','UNKNOWN'),
                authority_read=('READ_ONLY','UNKNOWN'), explorer_calls=('SELECTED','UNKNOWN'),
                provider=('RECEIVED_SYNTHETIC','UNKNOWN'))

class BudgetLedger:
    def __init__(self, ctx, *, create=False):
        c.require(type(ctx) is Context and ctx._writer_owner is None, 'ONE_TYPED_WRITER')
        ctx.check()
        self.ctx, self.active = ctx, None
        self.writes, self.call_ids, self.unknown_domains = set(), set(), set()
        self.policy = {'schema': VERSION, 'owner': ctx.owner.public(), 'source': ctx.source.raw_sha256,
                       'source_kind': c.SOURCE_KIND, 'limits': native.LIMITS,
                       'caps': {k:list(v) for k,v in native.CAPS.items()}, 'one_native_wal': True,
                       'provider_calls': 0, 'refundable': False}
        self.policy_sha256 = c.digest(self.policy)
        ctx._writer_owner = self
        with self.writer():
            self._native = NativeLedger(ctx, create=create)
        self.path = self._native.path

    @contextmanager
    def writer(self):
        c.require(self.ctx._writer_owner is self, 'WRITER_IDENTITY')
        self.ctx._writer_depth += 1
        try:
            yield
        finally:
            self.ctx._writer_depth -= 1

    @property
    def frames(self):
        return self._native.frames

    def read(self):
        self.ctx.check()
        return self._native.read()

    def append(self, kind, **data):
        c.require(kind not in ('RESERVE', 'RESULT'), 'USE_GATED_OPERATIONS')
        with self.writer():
            self._native.append(kind, **data)

    @contextmanager
    def authorized(self, phase, *, domain, tool, args=None, response_id=None, call_id=None):
        self.ctx.check()
        c.require(self.active is None and domain in c.DOMAINS, 'ACTIVE_OPERATION')
        op = dict(owner=self.ctx.owner.public(), source=self.ctx.source.raw_sha256, domain=domain,
                  phase=phase, tool=tool, arguments={} if args is None else args,
                  response_id=response_id, call_id=call_id)
        self.append('INTENT', audit_type=AUTH, status='CHECK', operation=op, operation_sha256=c.digest(op))
        try:
            c.require(phase in {p for phases in RESOURCE_PHASES.values() for p in phases} | {'invoke'}, 'PHASE')
            if phase == 'business':
                ct = next(x for x in self.ctx.public()['rounds'] if x['experiment']['domain'] == domain)
                c.require(tool in native.TOOLS[domain] and op['arguments'] == native.args_for(ct, tool) and
                          all(type(op['arguments'][k]) is type(v) for k,v in native.args_for(ct, tool).items()) and
                          type(response_id) is str and bool(response_id) and type(call_id) is str and bool(call_id),
                          'BUSINESS_OPERATION_IDENTITY')
            elif phase == 'authority':
                c.require(tool in ('BEFORE','FINAL','AGENT_RECONCILE') and op['arguments'] == {}, 'AUTHORITY_ROLE')
            elif phase == 'model':
                c.require(tool == 'model' and op['arguments'] == {}, 'MODEL_OPERATION_IDENTITY')
            else:
                c.require(tool == ('select_experiment' if phase == 'select' else phase) and op['arguments'] == {},
                          'CONTROLLER_OPERATION_IDENTITY')
            self.active = op
            self.append('INTENT', audit_type=AUTH, status='GRANTED', operation=op, operation_sha256=c.digest(op))
            yield op
            self.append('INTENT', audit_type=AUTH, status='COMPLETED', operation_sha256=c.digest(op))
        except BaseException:
            self.append('INTENT', audit_type=AUTH, status='REJECTED', operation_sha256=c.digest(op))
            raise
        finally:
            self.active = None

    def check_tool(self, ct, name, args, response_id, call_id):
        self.ctx.validate(ct)
        domain = ct['experiment']['domain']
        c.require(name in native.TOOLS[domain] and type(args) is dict and args == native.args_for(ct, name),
                  'DOMAIN_TOOL_ARGUMENTS')
        c.require(all(type(args[k]) is type(v) for k,v in native.args_for(ct, name).items()), 'ARGUMENT_TYPES')
        c.require(type(response_id) is str and type(call_id) is str and response_id and call_id and
                  (response_id, call_id) not in self.call_ids, 'TOOL_LINEAGE_REPLAY')
        if name in c.WRITES:
            c.require(domain not in self.unknown_domains and (domain, name) not in self.writes, 'UNKNOWN_OR_WRITE_ONCE')

    def completed_tool(self, ct, name, response_id, call_id, *, unknown=False):
        domain = ct['experiment']['domain']
        self.call_ids.add((response_id, call_id))
        if name in c.WRITES:
            self.writes.add((domain, name))
        if unknown:
            self.unknown_domains.add(domain)

    def claim_slot(self, ct, role, request, input_upper, output_cap):
        self.ctx.validate(ct)
        domain, round_number = ct['experiment']['domain'], ct['experiment']['round']
        c.require(role in ('TARGET', 'EXPLORER') and type(input_upper) is int and input_upper > 0 and
                  type(output_cap) is int and 0 < output_cap <= 512 and
                  input_upper >= len(c.canonical(request)), 'SLOT_TYPES')
        state = self.read()
        rows = [e for e in state['events'] if e['kind'] == 'MODEL_REQUEST' and
                e.get('role') == role and e.get('domain') == domain]
        caps = native.CAPS['EXPLORER' if role == 'EXPLORER' else domain]
        ordinal = len(rows) + 1
        c.require(ordinal <= len(caps) and input_upper + output_cap <= caps[ordinal-1], 'SLOT_INPUT_BOUND')
        if round_number == 2:
            c.require(any(e['kind'] == 'FEEDBACK_FROZEN' and e.get('round') == 1 for e in state['events']),
                      'FEEDBACK_REQUIRED')
        all_rows = [e for e in state['events'] if e['kind'] == 'MODEL_REQUEST']
        total = sum(e['request']['slot_cap'] for e in all_rows) + caps[ordinal-1]
        c.require(len(all_rows) < 11 and total <= native.REACHABLE_TOKENS <= native.GLOBAL_TOKENS and
                  caps[ordinal-1] <= native.MAX_SLOT, 'SLOT_POOL')
        proof = slot(domain, round_number, role, ordinal, input_upper, c.digest(request))
        with self.authorized('model', domain=domain, tool='model'):
            ticket = self.reserve('provider', domain=domain, round=round_number, role=role, request=proof)
        proof['ticket'] = ticket
        self.append('MODEL_REQUEST', domain=domain, round=round_number, role=role, ticket=ticket, request=proof,
                    transport='FIXTURE_LOOPBACK', usage_type='SYNTHETIC_VALIDATED_USAGE')
        return proof

    def complete_slot(self, ct, role, proof, response, usage):
        domain, index = ct['experiment']['domain'], ct['experiment']['round']
        ticket = proof['ticket']
        state = self.read()
        reservation = state['tickets'].get(ticket)
        c.require(reservation is not None and ticket not in state['results'] and
                  all(reservation[k] == v for k, v in (('domain', domain), ('round', index), ('role', role))) and
                  reservation['request'] == {k:v for k,v in proof.items() if k != 'ticket'}, 'MODEL_TICKET_BINDING')
        c.require(type(usage) is dict and all(type(usage.get(k)) is int and usage[k] >= 0 for k in
                  ('prompt_tokens','completion_tokens','total_tokens')) and
                  usage['prompt_tokens'] + usage['completion_tokens'] == usage['total_tokens'] and
                  usage['prompt_tokens'] <= proof['input_upper'] and usage['completion_tokens'] <= proof['output_cap'],
                  'MODEL_USAGE_BOUND')
        c.require(role != 'TARGET' or response.get('usage') == usage, 'MODEL_RESPONSE_USAGE')
        self.append('MODEL_RESPONSE', domain=domain, round=index, role=role, ticket=ticket,
                    response=response, usage_type='SYNTHETIC_VALIDATED_USAGE')
        with self.authorized('model', domain=domain, tool='model'):
            self.settle(ticket, status='RECEIVED_SYNTHETIC', usage=usage,
                        transport='FIXTURE_LOOPBACK', usage_type='SYNTHETIC_VALIDATED_USAGE')

    def _perform(self, action, resource, ticket, data):
        state = self.read()
        op = self.active
        parameters = data if action == 'RESERVE' else state['tickets'][ticket]
        c.require(op is not None and resource in RESOURCE_PHASES and op['phase'] in RESOURCE_PHASES[resource],
                  'RESOURCE_AUTHORIZATION')
        if resource in ('jvm', 'config_post', 'config_http', 'config_health'):
            c.require(op['domain'] == c.DOMAINS[0], 'CONFIG_RESOURCE_DOMAIN')
        if resource in ('sqlite_setup', 'sqlite_refund'):
            c.require(op['domain'] == c.DOMAINS[1], 'ORDER_RESOURCE_DOMAIN')
        if 'domain' in parameters:
            c.require(parameters['domain'] == op['domain'], 'RESOURCE_DOMAIN')
        if resource == 'authority_read' and op['phase'] == 'business':
            c.require(op['tool'] == 'reconcile_order', 'RECONCILE_ONLY')
        if resource == 'config_post':
            c.require(op['tool'] in ('create_config_v1', 'update_config_v2') and
                      parameters.get('operation') == op['tool'], 'CONFIG_POST_AUTH')
        if resource == 'sqlite_refund':
            c.require(op['tool'] == 'refund_order' and parameters.get('arguments_sha256') == c.digest(op['arguments']),
                      'REFUND_AUTH')
        if resource == 'config_http' and parameters.get('method') == 'POST':
            c.require(op['phase'] == 'business' and parameters.get('operation') == op['tool'], 'CONFIG_HTTP_AUTH')
        safe = resource in SAFE_READ or resource == 'config_http' and parameters.get('method') == 'GET'
        if action == 'RESERVE':
            c.require(not (state['unknown'] or state['blocked']) or safe, 'UNKNOWN_GLOBAL_STOP')
        else:
            c.require(type(data.get('status')) is str and data['status'] in STATUSES[resource], 'SETTLEMENT_STATUS')
        request = dict(action=action, resource=resource, ticket=ticket, parameters=data,
                       operation_sha256=c.digest(op), policy_sha256=self.policy_sha256)
        self.append('INTENT', audit_type=TAG, status='CHECK', request=request)
        self.append('INTENT', audit_type=TAG, status='GRANTED', request_sha256=c.digest(request))
        with self.writer():
            if action == 'RESERVE':
                actual = self._native.reserve(resource, **data)
                c.require(actual == ticket, 'TICKET_PARITY')
            else:
                self._native.settle(ticket, **data)
        self.append('INTENT', audit_type=TAG, status='CONFIRMED' if action == 'RESERVE' else 'SETTLED',
                    request_sha256=c.digest(request), native_seq=self.frames[-1]['seq'])
        return ticket

    def reserve(self, resource, **data):
        state = self.read()
        c.require(resource in RESOURCE_PHASES and resource in state['counts'], 'RESOURCE_ALLOWLIST')
        return self._perform('RESERVE', resource, resource + '-' + str(state['counts'][resource] + 1), data)

    def settle(self, ticket, **data):
        state = self.read()
        c.require(type(ticket) is str and ticket in state['tickets'] and ticket not in state['results'], 'TICKET')
        return self._perform('SETTLE', state['tickets'][ticket]['resource'], ticket, data)
