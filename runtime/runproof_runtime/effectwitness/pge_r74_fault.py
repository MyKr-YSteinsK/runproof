"""Post-commit response suppression state, scoped to one domain and call."""
from . import pge_r74_contracts as c

class Fault:
    def __init__(self, scenario, domain):
        c.require(scenario in c.SCENARIOS and domain in c.DOMAINS, 'FAULT_SCOPE')
        self.scenario, self.domain = scenario, domain
        self.planned = scenario == 'F'
        self.triggered = self.observed = self.agent_exposed = False
        self.call_id = self.committed_sha256 = self.transport_error = None

    def suppress(self, name, call_id, result):
        target = 'update_config_v2' if self.domain == c.DOMAINS[0] else 'refund_order'
        if not self.planned or name != target:
            return False
        c.require(not self.triggered and type(result) is dict and result.get('status') == 'COMMITTED',
                  'FAULT_REQUIRES_ACTUAL_COMMIT')
        self.triggered = True
        self.call_id, self.committed_sha256 = call_id, c.digest(result)
        return True

    def observe(self, call_id, error_type):
        c.require(self.triggered and not self.observed and call_id == self.call_id and
                  error_type in ('RemoteDisconnected', 'ConnectionResetError', 'ConnectionAbortedError'),
                  'FAULT_NOT_OBSERVED')
        self.observed, self.transport_error = True, error_type

    def expose(self, call_id, result):
        c.require(self.observed and call_id == self.call_id and result.get('status') == 'UNKNOWN_OUTCOME',
                  'FAULT_NOT_EXPOSED')
        self.agent_exposed = True

    def public(self):
        return dict(planned=self.planned, triggered=self.triggered, observed=self.observed,
                    agent_exposed=self.agent_exposed, call_id=self.call_id,
                    committed_sha256=self.committed_sha256, transport_error=self.transport_error,
                    channel='SAME_HOST_INTERNAL_HTTP' if self.planned else 'NONE')
