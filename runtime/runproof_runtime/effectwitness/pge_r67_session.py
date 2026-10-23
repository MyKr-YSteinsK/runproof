"""Single-domain controller. Synthetic, metadata, cold and paid entry points separate."""
import copy, os, secrets, socket, subprocess
from . import pge_r67_context as c
from .pge_r67_order_port import OrderPort
from .pge_r67_order_driver import Driver, ScriptDriver
from .pge_r67_order_verify import seal, verify

def free_port():
    s=socket.socket();s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close();return p
def execute(ctx,ledger,driver,*,admission=None):
    session=ledger.reserve('session');trial=ledger.reserve('trial');port=OrderPort()
    try:
        evidence=port.execute(ctx,ctx.ct,ledger,driver=driver);evidence['cleanup']=port.cleanup_result
        outcome=port.verify(ctx,ctx.ct,evidence);c.require(outcome['contract_outcome']=='CONTRACT_SATISFIED_IN_RUN','ORACLE_INCONCLUSIVE')
        ledger.settle(trial,status='CONTRACT_SATISFIED_IN_RUN');ledger.settle(session,status='COMPLETED');ledger.read()
        payload=dict(context=ctx.public(),frames=ledger.frames,order=evidence,outcome=outcome,admission=admission,boundaries=c.BOUNDARIES)
        witness=seal(payload);verify(witness);return witness
    except BaseException as error:
        # Never retry; preserve any partial DB, trace, outstanding or unknown ticket.
        driver.key=None
        if hasattr(port,'reader'):
            try:port.reader.available=True;port.read('FAILURE_READ_ONLY_RECONCILE');port.reader.available=False
            except Exception:pass
            finally:port.reader.available=False
        try:account=ledger.read();counts=account['counts'];unknown=account['unknown'];diagnostics=[e for e in account['events'] if e['kind'] in ('PROVIDER_SHAPE_OBSERVED','PROVIDER_PARSE_REJECTED')]
        except Exception:counts=None;unknown=True;diagnostics=[dict(state='TORN_DIAGNOSTIC',action='STOP_NO_RESEND_NO_RECEIPT_DELETE')]
        ctx.once(ctx.root/'failure.json',dict(error_type=type(error).__name__,code=str(error) if type(error) is ValueError else 'REDACTED',trace=getattr(port,'trace',[]),driver_failure=driver.failure,counts=counts,unknown=unknown,response_diagnostics=diagnostics))
        raise
def synthetic(*,reconcile=True,mixed=True):
    suffix=secrets.token_hex(8);ctx=c.make_context(suffix,free_port(),synthetic=True);ctx.root.mkdir(parents=True)
    ledger=c.Ledger(ctx,create=True);return execute(ctx,ledger,ScriptDriver(ctx,ledger,fixture=True,reconcile=reconcile,mixed=mixed))

class ColdPort(OrderPort):
    """Memory protocol fixture only: no OrderSandbox, AuthorityReader or DB write."""
    def __init__(self,ctx,ledger):
        self.ctx=ctx;self.ct=ctx.ct;self.ledger=ledger;self.trace=[];self.pending=None;self.responses=[];self.fault=dict.fromkeys(('planned','triggered','observed','agent_exposed'),False)
    def register(self,response_id,call):
        c.require(self.pending is None and response_id not in self.responses,'COLD_RESPONSE_REPLAY');self.responses.append(response_id)
        if call:self.allowed(call['name'],call['arguments']);self.pending=dict(response_id=response_id,**call)
        else:c.require(len(self.trace) in (2,3),'COLD_STOP')
    def invoke(self,value):
        c.require(self.pending is not None and value=={k:self.pending[k] for k in ('call_id','name','arguments')},'COLD_CALLBACK');self.allowed(value['name'],value['arguments'])
        name=value['name'];f=self.ct['effect']
        if name==c.TOOLS[0]:result=dict(order_id=f['order_id'],status='PAID',revision=0)
        elif name==c.TOOLS[1]:result=dict(status='UNKNOWN_OUTCOME',operation_id=f['operation_id'],write_policy='STOP_WRITES_READ_ONLY_RECONCILE');self.fault['agent_exposed']=True
        else:result=dict(status='COMMITTED',operation_id=f['operation_id'],readonly=True,fixture=True)
        t=dict(**self.pending,result=result,result_sha256=c.digest(result));self.trace.append(t);self.pending=None;return result
def initialize():
    root=c.ROOT/'.local/rpf-67-rev-2';c.require(root.is_dir() and not (root/'context.json').exists(),'INIT_ONCE')
    c.require(subprocess.check_output(['git','branch','--show-current'],cwd=c.ROOT,text=True).strip()==c.BRANCH and subprocess.check_output(['git','rev-parse','HEAD'],cwd=c.ROOT,text=True).strip()==c.BASE,'INIT_GIT_IDENTITY')
    c.require(c.strict((root/'g0.json').read_bytes())['status']=='PASS','G0_REQUIRED')
    ctx=c.make_context(secrets.token_hex(8),free_port());ctx.once(root/'context.json',ctx.public());c.Ledger(ctx,create=True);return ctx
def load():
    p=c.strict((c.ROOT/'.local/rpf-67-rev-2/context.json').read_bytes());return c.Context(c.ROOT/p['workspace'],c.canonical(p))
def cold(ctx,ledger):
    c.require(ledger.read()['counts']['metadata']==1 and ledger.read()['results']['metadata-1']['status']=='PASS','METADATA_REQUIRED')
    port=ColdPort(ctx,ledger);driver=Driver(ctx,ledger,fixture=True,cold=True);result=driver.run(port)
    c.require(not (ctx.root/'business').exists() and ledger.read()['counts']['provider']==0,'COLD_ZERO_BUSINESS_OR_PROVIDER')
    ctx.once(ctx.root/'cold.json',result);return result
def freeze_check(ctx):
    freeze=c.strict((ctx.root/'source-freeze.json').read_bytes());free=c.strict((ctx.root/'free-gates.json').read_bytes())
    c.require(freeze['sources']==c.sources()==ctx.public()['sources'] and freeze['source_digest']==ctx.public()['source_digest'] and freeze['diff_check']=={'staged':0,'unstaged':0},'SOURCE_FREEZE')
    c.require(free['source_digest']==ctx.public()['source_digest'] and free['status']=='PASS' and free['full']['exit']==0 and free['full']['errors']==free['full']['failures']==0 and free['focused']['exit']==0 and len(free['anchors'])==21 and all(z['exit']==0 for z in free['anchors']) and free['semantic_controls']>=55 and free['mixed_sdk_e2e']['status']=='PASS' and free['mixed_sdk_e2e']['source_digest']==ctx.public()['source_digest'],'FREE_GATES')
    return freeze,free
def admit(ctx,ledger):
    ctx.check();freeze,free=freeze_check(ctx);a=ledger.read()
    c.require(a['counts']['metadata']==a['counts']['cold']==1 and all(a['counts'][r]==0 for r in ('provider','session','trial','sdk','host','sqlite_setup','sqlite_refund')) and not a['unknown'] and set(a['tickets'])==set(a['results']),'FRESH_RESOURCE_ADMISSION')
    cold_result=c.strict((ctx.root/'cold.json').read_bytes());c.require(cold_result['process_gone'] and cold_result['port_closed'] and cold_result['fixture'],'COLD_GATE')
    official=c.strict((ctx.root/'official-price-check.json').read_bytes());c.require(official==c.PRICE and sum(c.CAPS)*18<=450000,'OFFICIAL_PRICE_GUARD')
    gate=dict(context_sha256=c.digest(ctx.public()),sources=c.sources(),price=c.PRICE,free_gates='PASS',free_receipt_sha256=c.digest(free),freeze_sha256=c.digest(freeze),metadata='PASS',cold='PASS',cold_sha256=c.digest(cold_result),limits=c.LIMITS,caps=list(c.CAPS))
    ctx.once(ctx.root/'paid-gate.json',gate);ledger.append('ADMISSION',gate_sha256=c.digest(gate));return gate
def live(ctx,ledger):
    ctx.check();freeze_check(ctx);gate=c.strict((ctx.root/'paid-gate.json').read_bytes());a=ledger.read()
    c.require(gate['context_sha256']==c.digest(ctx.public()) and gate['sources']==c.sources() and any(e['kind']=='ADMISSION' and e['gate_sha256']==c.digest(gate) for e in a['events']) and a['counts']['provider']==a['counts']['session']==a['counts']['trial']==0 and not a['unknown'],'LIVE_ADMISSION')
    c.require(subprocess.check_output(['git','branch','--show-current'],cwd=c.ROOT,text=True).strip()==c.BRANCH and subprocess.check_output(['git','rev-parse','HEAD'],cwd=c.ROOT,text=True).strip()==c.BASE,'LIVE_GIT_IDENTITY')
    # First and sole credential lookup is below all admission checks.
    key=os.environ.get('DEEPSEEK_API_KEY');c.require(bool(key),'KEY_UNAVAILABLE');driver=Driver(ctx,ledger,key=key);key=None
    try:
        witness=execute(ctx,ledger,driver,admission=gate);ctx.once(ctx.root/'accepted-witness.json',witness);return witness
    finally:driver.key=None
