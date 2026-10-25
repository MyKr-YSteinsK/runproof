"""Immutable arithmetic reference, never a provider wallet or reservation."""
from dataclasses import dataclass
from . import pge_r73_contracts as c
CAPS={'EXPLORER':(32000,),'config-java-http':(10000,30000,50000,70000,90000),'order-sqlite':(10000,30000,50000,70000)}
@dataclass(frozen=True,slots=True)
class BudgetView:
 domain:str
 def public(self):
  c.require(self.domain in c.DOMAINS,'BUDGET_DOMAIN')
  return dict(version='rpf73-readonly-budget-v1',domain=self.domain,cumulative=sum(CAPS[self.domain]),slots=list(CAPS[self.domain]),all_slots=11,reachable=474000,global_cap=600000,max_slot=160000,provider_reserved=0,actual_provider_usage=0)
 def check(self,value):c.equal(value,self.public(),'BUDGET_VIEW_BINDING')
 def request(self,n,upper,output=None):
  c.require(type(n) is int and type(upper) is int,'BUDGET_INTEGER')
  cap=512 if n>=(4 if self.domain==c.DOMAINS[0] else 3) else 256
  output=cap if output is None else output
  c.require(type(output) is int and 1<=n<=len(CAPS[self.domain]) and output==cap and 0<upper<=262144 and upper+512<=CAPS[self.domain][n-1],'REQUEST_SLOT_BOUND')
  return dict(ordinal=n,input_upper=upper,output_cap=output,sdk_output_cap=512,conservative_output_guard=512,slot_cap=CAPS[self.domain][n-1])
