"""Pure legacy-policy equivalence; simulation reservations are not Provider usage."""
from . import pge_r69_abi as a,pge_r68_contracts as native
def policy():return dict(version=native.BUDGET_VERSION,caps={k:list(v) for k,v in native.CAPS.items()},reachable_tokens=native.REACHABLE_TOKENS,global_tokens=native.GLOBAL_TOKENS,max_slot=native.MAX_SLOT,provider_calls_limit=native.LIMITS['provider'],sdk_cumulative={d:sum(native.CAPS[d]) for d in native.DOMAINS},currency_guard=native.PRICE,refundable=False,real_provider_allowed=False)
def decide(domain,role,ordinal,input_upper,output_cap):
 a.typed(domain,role);a.require(type(ordinal) is int and type(input_upper) is int and type(output_cap) is int,'BUDGET_INTEGER');i=native.DOMAINS.index(domain)+1;q=native.slot_scope(domain,i,role,ordinal);a.require(input_upper>0 and output_cap==q['output_cap'],'BUDGET_OUTPUT');a.require(input_upper+output_cap<=q['slot_cap'],'PRE_SEND_INPUT_BOUND');return q
def ledger_policy(*,unknown=False,write=False,recycle=False,provider=0,usage=0,finish='stop',refusal=False):
 a.require(type(provider) is int and type(usage) is int and provider==usage==0,'ZERO_PROVIDER');a.require(not recycle,'PERMANENT_TICKET');a.require(not (unknown and write),'UNKNOWN_STOP_WRITES');a.require(finish in ('stop','tool_calls') and refusal is False,'RESPONSE_POLICY');return True
def write_policy(domain,names,name,unknown=False):
 a.typed(domain,'TARGET');a.require(name in native.TOOLS[domain],'DOMAIN_TOOL');a.require(not unknown or name in (native.TOOLS[domain][0] if domain==native.DOMAINS[0] else native.TOOLS[domain][2],),'UNKNOWN_READ_ONLY')
 expected=list(native.TOOLS[domain][:(3 if domain==native.DOMAINS[0] else 2)]);a.require(names==expected[:len(names)] and (len(names)<len(expected) and name==expected[len(names)] or len(names)==len(expected) and unknown and name==(native.TOOLS[domain][0] if domain==native.DOMAINS[0] else native.TOOLS[domain][2])),'STOP_WRITES_READ_ONLY');return True
