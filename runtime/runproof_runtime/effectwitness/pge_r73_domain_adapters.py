"""Two explicit schemas and fictional ToolReturns; zero business backends."""
from dataclasses import dataclass
from . import pge_r73_contracts as c
from .pge_r73_budget_view import CAPS
TOOLS={c.DOMAINS[0]:('inspect_config','create_config_v1','update_config_v2'),c.DOMAINS[1]:('inspect_order','refund_order','reconcile_order')}
@dataclass(frozen=True,slots=True)
class DomainAdapter:
 domain:str
 def check(self):c.require(type(self) is DomainAdapter and self.domain in c.DOMAINS,'ADAPTER_IDENTITY')
 def instructions(self):return 'Component-only fictional ToolReturns. Use each registered tool in order, then stop. No real business effect or authority.'
 def prompt(self):return 'RPF73 controlled SDK component. Exercise all three registered tools once with the specified dummy values. '+c.canonical(self.arguments()).decode()+' Padding: '+'x'*7500
 def arguments(self):
  self.check()
  return ({'inspect_config':{},'create_config_v1':dict(value='rpf53-v1'),'update_config_v2':dict(expected_version=1,value='rpf53-v2')} if self.domain==c.DOMAINS[0] else {'inspect_order':dict(order_id='component-order'),'refund_order':dict(order_id='component-order',operation_id='component-op',amount_minor=2500),'reconcile_order':dict(operation_id='component-op')})
 def result(self,name,args):
  c.require(name in TOOLS[self.domain],'DOMAIN_TOOL');c.equal(args,self.arguments()[name],'TOOL_ARGUMENT_TYPE_VALUE')
  return dict(status='SIMULATED_ONLY',tool=name,business_effect=False,component='rpf73',value_sha256=c.digest(args))
 def registry(self,tools):
  self.check();c.require(type(tools) is list and [t['function']['name'] for t in tools]==list(TOOLS[self.domain]),'SDK_REGISTRY')
  for t in tools:
   f=t['function'];p=f['parameters'];a=self.arguments()[f['name']]
   c.require(t['type']=='function' and p['type']=='object' and p['additionalProperties'] is False and set(p['properties'])==set(p.get('required',[]))==set(a),'SDK_SCHEMA')
   for k,v in a.items():c.require(p['properties'][k]['type']==('integer' if type(v) is int else 'string'),'SDK_PROPERTY_TYPE')
 def response(self,run,n,upper,prior_total,pressure=False):
  c.require(type(n) is int and 1<=n<=4,'ADAPTER_REQUEST_COUNT');name=TOOLS[self.domain][n-1] if n<=3 else None
  prompt=max(1,upper-512);output=20
  if pressure and n==4:prompt=sum(CAPS[self.domain])+1-prior_total-output
  message=dict(role='assistant',content=None if name else 'Component complete.')
  if name:message['tool_calls']=[dict(id=run+'-call-'+str(n),type='function',function=dict(name=name,arguments=c.canonical(self.arguments()[name]).decode()))]
  return dict(id=run+'-response-'+str(n),object='chat.completion',created=0,model='deepseek-flash',choices=[dict(index=0,finish_reason='tool_calls' if name else 'stop',message=message)],usage=dict(prompt_tokens=prompt,completion_tokens=output,total_tokens=prompt+output))
