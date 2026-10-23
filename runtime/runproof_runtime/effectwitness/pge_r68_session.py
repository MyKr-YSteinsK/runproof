"""Sole typed SharedSession; verify and clean round one before feedback or round two."""
import secrets,os,shutil,subprocess,ast
from . import pge_r68_context as c
from .pge_r68_budget import Ledger
from .pge_r68_driver import Driver,Port,require_admission
from .pge_r68_explorer import choose,feedback
from .pge_r68_order_port import OrderPort
from .pge_r68_config_port import ConfigPort
REGISTRY={c.DOMAINS[0]:ConfigPort,c.DOMAINS[1]:OrderPort}
class SharedSession:
 def __init__(self,ctx,l):c.require(isinstance(l,Ledger) and l.ctx is ctx and l.path==ctx.scope(ctx.root/'wal.jsonl'),'SINGLE_LEDGER');self.ctx=ctx;self.l=l;self.rows=[]
 def execute(self,domain,ct,port,*,fixture=False,key=None):
  if not fixture:require_admission(self.ctx,self.l)
  c.require(domain in REGISTRY and type(port) is REGISTRY[domain] and ct['experiment']['domain']==domain and ct['experiment']['round']==len(self.rows)+1,'TYPED_DISPATCH');self.ctx.validate(ct);name='runtime/runproof_runtime/effectwitness/'+port.__class__.__module__.split('.')[-1]+'.py';self.l.append('PORT_ENTERED',domain=domain,round=ct['experiment']['round'],port_module=name,port_source_sha256=self.ctx.public()['sources'][name]['raw'],contract_sha256=c.digest(ct));driver=Driver(self.ctx,self.l,ct,fixture=fixture,key=key);prepared=False
  try:
   port.prepare(self.ctx,ct,self.l);prepared=True;sdk=driver.run(port);business=port.finish()
  except BaseException:
   if prepared:
    try:self.ctx.once(self.ctx.folder(ct)/'failure-business-readback.json',port.finish())
    except Exception:pass
   raise
  finally:
   driver.key=None
   if prepared or hasattr(port,'proc'):cleanup=port.cleanup()
  evidence=dict(contract=ct,trace=port.trace,fault=port.fault,sdk=sdk,business=business,cleanup=cleanup);from .pge_r68_verify import verify_domain
  verify_domain(self.ctx.public(),ct,evidence);return evidence
 def run(self,*,candidates=None,key=None):
  fixture=self.ctx.public()['source_kind']==c.SYNTHETIC;c.require((candidates is not None)==fixture,'SOURCE_MODE');ticket=self.l.reserve('session')
  for index,domain in enumerate(c.DOMAINS,1):
   choice=choose(self.ctx,self.l,index,self.rows,fixture=candidates[index-1] if fixture else None,key=key);ct=self.ctx.contract(index,choice['candidate_id']);trial=self.l.reserve('trial',domain=domain,round=index);e=self.execute(domain,ct,REGISTRY[domain](),fixture=fixture,key=key);self.l.settle(trial,status='VERIFIED');seq=len(self.l.frames);self.l.append('DOMAIN_VERIFIED',domain=domain,round=index,evidence_sha256=c.digest(e),contract_sha256=c.digest(ct),oracle=e['business']['oracle']);fb=feedback(ct,e,choice,seq);self.l.append('FEEDBACK_FROZEN',domain=domain,round=index,feedback=fb,feedback_sha256=c.digest(fb));self.rows.append(dict(choice=choice,evidence=e,feedback=fb))
  self.l.settle(ticket,status='COMPLETED');self.l.append('SESSION_COMPLETE',rounds=2);self.l.read();from .pge_r68_verify import seal,verify
  witness=seal(dict(context=self.ctx.public(),frames=self.l.frames,rounds=self.rows,admission=c.strict((self.ctx.root/'paid-gate.json').read_bytes()) if not fixture else None,boundaries=c.BOUNDARIES));verify(witness);return witness

def copy_jar(ctx):
 _,old=c.helpers();target=ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar');target.parent.mkdir();c.require(c.sha(old.SOURCE_JAR.read_bytes())==c.SOURCE_JAR_SHA256 and old.SOURCE_JAR.stat().st_size==c.SOURCE_JAR_BYTES,'JAR_SOURCE_PIN')
 with old.SOURCE_JAR.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
 c.require(c.sha(target.read_bytes())==c.SOURCE_JAR_SHA256,'JAR_COPY')
def synthetic(candidates=None):
 ctx=c.make(synthetic=True);ctx.root.mkdir(parents=True);copy_jar(ctx);l=Ledger(ctx,create=True);w=SharedSession(ctx,l).run(candidates=candidates or (c.CANDIDATES[0][1],c.CANDIDATES[1][1]));ctx.once(ctx.root/'synthetic-witness.json',w);return w
class ColdPort(Port):
 def __init__(self,ctx,ct,l):self.domain=ct['experiment']['domain'];self.prepare_common(ctx,ct,l);self.cold=True
 def business(self,name,args):
  if self.domain==c.DOMAINS[0]:return dict(state='ABSENT') if name=='inspect_config' else dict(status='COMMITTED',version=1 if name=='create_config_v1' else 2,value='rpf53-v1' if name=='create_config_v1' else 'rpf53-v2')
  if name=='inspect_order':return dict(order_id=args['order_id'],status='PAID',revision=0)
  return dict(status='COMMITTED',operation_id=args['operation_id'],receipt_id='receipt-'+'a'*24,committed_revision=1)
def load():
 p=c.strict((c.ROOT/'.local/rpf-68/context.json').read_bytes());return c.Context(c.ROOT/p['workspace'],c.canonical(p))
def freeze_check(ctx):
 f=c.strict((ctx.root/'source-freeze.json').read_bytes());g=c.strict((ctx.root/'free-gates.json').read_bytes());c.require(f['sources']==ctx.public()['sources']==c.sources() and g['source_digest']==ctx.public()['source_digest'] and g['status']=='PASS' and g['full']['exit']==0 and g['full']['errors']==g['full']['failures']==0 and g['synthetic_controls']>=90 and all(x['exit']==0 for x in g['anchors']) and len(g['anchors'])==21,'FREE_GATES');c.require(all(c.sha(ctx.scope(c.ROOT/name).read_bytes())==h for name,h in f['helpers'].items()),'FROZEN_HELPER_DRIFT');return f,g
def initialize():
 root=c.ROOT/'.local/rpf-68';c.require(not (root/'context.json').exists() and c.strict((root/'g0.json').read_bytes())['status']=='PASS','INIT_ONCE');ctx=c.make();freeze_check(ctx);ctx.once(root/'context.json',ctx.public());Ledger(ctx,create=True);copy_jar(ctx);return ctx

def metadata(ctx,l):
 from .pge_r67_context import metadata as fixed_sdk_metadata
 result=fixed_sdk_metadata(ctx,l);_,old=c.helpers();ctx.once(ctx.root/'java-identity.json',old._java_identity());return result

def cold(ctx,l):
 result=[]
 for index in (1,2):
  ct=ctx.contract(index,c.CANDIDATES[index-1][0]);port=ColdPort(ctx,ct,l);sdk=Driver(ctx,l,ct,fixture=True,cold=True).run(port);result.append(sdk)
 c.require(l.read()['counts']['provider']==0,'COLD_PROVIDER_ZERO');ctx.once(ctx.root/'cold.json',result);return result

def admit(ctx,l):
 freeze,gates=freeze_check(ctx);a=l.read();cold=c.strict((ctx.root/'cold.json').read_bytes());c.require(a['counts']['metadata']==1 and a['counts']['cold']==2 and a['counts']['provider']==a['counts']['session']==0 and set(a['tickets'])==set(a['results']) and not a['unknown'] and all(all(x['cleanup'].values()) for x in cold),'ADMISSION_RESOURCES');c.require(c.strict((ctx.root/'price.json').read_bytes())==c.PRICE,'OFFICIAL_PRICE');gate=dict(context_sha256=c.digest(ctx.public()),sources=ctx.public()['sources'],freeze_sha256=c.digest(freeze),free_sha256=c.digest(gates),price=c.PRICE,cold_sha256=c.digest(cold));ctx.once(ctx.root/'paid-gate.json',gate);l.append('ADMISSION',gate_sha256=c.digest(gate));return gate

def live(ctx,l):
 freeze_check(ctx);a=l.read();gate=c.strict((ctx.root/'paid-gate.json').read_bytes());c.require(gate['context_sha256']==c.digest(ctx.public()) and a['counts']['provider']==a['counts']['session']==0 and not a['unknown'] and not a['blocked'] and subprocess.check_output(['git','rev-parse','HEAD'],cwd=c.ROOT,text=True).strip()==c.BASE and subprocess.check_output(['git','branch','--show-current'],cwd=c.ROOT,text=True).strip()==c.BRANCH,'FRESH_LIVE');key=os.environ.get('DEEPSEEK_API_KEY');c.require(bool(key),'KEY_UNAVAILABLE')
 try:w=SharedSession(ctx,l).run(key=key);ctx.once(ctx.root/'accepted-witness.json',w);return w
 finally:key=None
