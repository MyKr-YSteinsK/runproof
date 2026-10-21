"""Static DomainPort ABI and common, domain-scoped evidence projection."""
from typing import Protocol
from .pge_port_context import ABI,DOMAINS,require,digest
class DomainPort(Protocol):
 def validate_contract(self,context,contract): ...
 def execute(self,context,contract,ledger): ...
 def verify(self,context,contract,evidence): ...
 def cleanup(self,context,contract,evidence): ...
def select(domain):
 from .pge_portability_order import OrderPort
 from .pge_portability_config import ConfigPort
 require(domain in DOMAINS,'STATIC_PORT_ALLOWLIST')
 return {DOMAINS[0]:OrderPort,DOMAINS[1]:ConfigPort}[domain]()
def classify(effect,fault,*,authority=True,unknown=False,reconciled=False):
 require(set(fault)=={'planned','triggered','observed','agent_exposed'} and all(type(x) is bool for x in fault.values()),'FAULT_FIELDS')
 require((not fault['triggered'] or fault['planned']) and (not fault['observed'] or fault['triggered']) and (not fault['agent_exposed'] or fault['observed']),'FALSE_FAULT')
 require(effect in ('CONTRACT_SATISFIED_IN_RUN','VIOLATION_CONFIRMED','INCONCLUSIVE'),'EFFECT_ENUM')
 state='AUTHORITY_UNAVAILABLE' if not authority else 'VIOLATION_CONFIRMED' if effect=='VIOLATION_CONFIRMED' else 'UNKNOWN_OUTCOME' if unknown else 'INCONCLUSIVE' if effect=='INCONCLUSIVE' else 'FAULT_NOT_TRIGGERED' if fault['planned'] and not fault['triggered'] else 'NORMAL'
 return {'state':state,'effect':effect if authority else 'INCONCLUSIVE','fault':fault,'write_ack':'UNKNOWN_OUTCOME' if unknown else 'CONFIRMED','reconciled':bool(reconciled)}
def projection(domain,source,authority,outcome,facts):
 require(domain in DOMAINS and source in ('DETERMINISTIC','FIXTURE_SCRIPTED','SYNTHETIC_TEST_ONLY'),'SOURCE_LEVEL')
 require(type(facts) is list and all(type(x) is str and x.startswith(domain+'/') for x in facts),'DOMAIN_FACT_SCOPE')
 return {'abi':ABI,'domain':domain,'source_kind':source,'authority':authority,'outcome':outcome,'verified_facts':facts,'facts_sha256':digest(facts)}
