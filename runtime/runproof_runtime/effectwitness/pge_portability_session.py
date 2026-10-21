"""One concrete dispatch/verify/feedback/cleanup path for both static ports."""
import hashlib,inspect
from . import pge_port_context as c
from .pge_domain_port import select

def dispatch_identity(domain):
 port=select(domain)
 return {'abi':c.ABI,'shared_entry':'pge_portability_session.SharedSession.execute','shared_source_sha256':hashlib.sha256(inspect.getsource(SharedSession.execute).encode()).hexdigest(),'port_entry':type(port).__module__+'.'+type(port).__qualname__+'.execute','port_file_sha256':c.sources()[type(port).__module__.replace('.','/')+'.py'] if type(port).__module__.startswith('runtime.') else c.sources()['runtime/'+type(port).__module__.replace('.','/')+'.py']}
def feedback(context,ct,verdict,evidence):
 return {'schema':'rpf64-domain-feedback-v1','session_id':context.public()['session_id'],'domain':ct['experiment']['domain'],'run_id':ct['experiment']['run_id'],'authority':verdict['authority'],'outcome':verdict['outcome'],'verified_facts':verdict['verified_facts'],'evidence_sha256':c.digest(evidence),'verdict_sha256':c.digest(verdict),'cross_domain_information_gain':'NOT_COMPARABLE'}
class SharedSession:
 def __init__(self,context,ledger):self.context,self.ledger,self.rows=context,ledger,[]
 def execute(self,domain):
  ctx,total=self.context,self.ledger;index=len(self.rows);c.require(index<len(c.DOMAINS) and domain==c.DOMAINS[index],'SESSION_SEQUENCE');ct=ctx.contract(domain);port=select(domain);port.validate_contract(ctx,ct);run=ct['experiment']['run_id'];identity=dispatch_identity(domain)
  ticket=total.reserve('trial',domain=domain,run_id=run);specific=total.reserve(ct['execution']['resource'],domain=domain,run_id=run);total.append('PORT_ENTERED',domain=domain,run_id=run,dispatch=identity,contract_sha256=c.digest(ct),prior_feedback_sha256=[c.digest(r['feedback']) for r in self.rows])
  evidence=port.execute(ctx,ct,total);verdict=port.verify(ctx,ct,evidence);total.append('DOMAIN_VERIFIED',domain=domain,run_id=run,evidence_sha256=c.digest(evidence),verdict_sha256=c.digest(verdict));cleanup=port.cleanup(ctx,ct,evidence);c.require(all(cleanup.values()),'DOMAIN_CLEANUP');total.append('DOMAIN_CLEANUP',domain=domain,run_id=run,cleanup=cleanup)
  fb=feedback(ctx,ct,verdict,evidence);total.append('FEEDBACK_FROZEN',domain=domain,run_id=run,feedback_sha256=c.digest(fb));total.settle(specific,status='VERIFIED',evidence_sha256=c.digest(evidence));total.settle(ticket,status='VERIFIED',feedback_sha256=c.digest(fb))
  row={'domain':domain,'contract':ct,'dispatch':identity,'evidence':evidence,'verdict':verdict,'feedback':fb,'cleanup':cleanup};ctx.once(ctx.root/(domain+'-verified.json'),row);self.rows.append(row);return row
 def run(self):
  ctx,total=self.context,self.ledger;ticket=total.reserve('session',session_id=ctx.public()['session_id']);ctx.once(ctx.root/'session-started.json',ctx.public())
  try:
   for domain in c.DOMAINS:self.execute(domain)
   total.settle(ticket,status='COMPLETED',rows_sha256=c.digest(self.rows));return self.rows
  finally:ctx.once(ctx.root/'session-receipt.json',{'completed_domains':len(self.rows),'rows':self.rows,'ledger':total.frames,'context_sha256':c.digest(ctx.public())})
