"""RPF68 order capability: original SQL methods, new owner and independent RO Reader."""
import secrets,sqlite3
from contextlib import closing
from . import pge_r68_context as c
from .pge_r68_driver import Port
from .orders import OrderSandbox,AuthorityReader,OrderAdapter
from .effect_oracle import evaluate_order_effect
class Bridge:
 def __init__(self,ctx,ct):self.ctx=ctx;self.ct=ct
 @property
 def execution(self):return self.ct['execution']
 @property
 def effect(self):return self.ct['effect']
 @property
 def experiment(self):return self.ct['experiment']
 def validate(self):self.ctx.validate(self.ct)
class Sandbox(OrderSandbox):
 def __init__(self,ctx,ct):
  self.contracts=Bridge(ctx,ct);self.owner=c.OWNER;self.storage_task=c.OWNER;self.directory=ctx.scope(ctx.folder(ct)/'business');self.path=ctx.scope(self.directory/'orders.sqlite3');self.created=False;self.generation=0
class Reader(AuthorityReader):
 def __init__(self,sandbox):self.path=sandbox.path;self.contracts=sandbox.contracts;self._seal=secrets.token_bytes(32);self.available=True
class OrderPort(Port):
 domain=c.DOMAINS[1]
 def prepare(self,ctx,ct,ledger):
  self.prepare_common(ctx,ct,ledger);self.sandbox=Sandbox(ctx,ct);self.reader=Reader(self.sandbox);self.adapter=OrderAdapter(self.sandbox);t=ledger.reserve('sqlite_setup');self.sandbox.initialize();ledger.settle(t,status='CREATED');self.before=self.authority('BEFORE')
 def authority(self,phase):
  t=self.ledger.reserve('authority_read',domain=self.domain,round=2,phase=phase);s=self.reader.read();self.reader.validate(s);p=s.public();self.ledger.settle(t,status='READ_ONLY',snapshot=p,connection='SQLITE_MODE_RO_QUERY_ONLY');return p
 def business(self,name,args):
  if name=='refund_order':
   t=self.ledger.reserve('sqlite_refund',domain=self.domain,round=2,arguments_sha256=c.digest(args));result=self.adapter.invoke(name,args);c.require(result['status']=='COMMITTED','REFUND_COMMIT');self.ledger.settle(t,status='COMMITTED',receipt=result)
   if self.ct['experiment']['fault_enabled']:self.fault.update(triggered=True,observed=True,agent_exposed=True);return dict(status='UNKNOWN_OUTCOME',operation_id=args['operation_id'],reason='CONTROLLED_POST_COMMIT_RESPONSE_LOSS',write_policy='STOP_WRITES_READ_ONLY_RECONCILE')
   return result
  if name=='reconcile_order':return dict(status='COMMITTED',receipt=self.authority('AGENT_RECONCILE')['data']['receipts'][0],readonly=True)
  return self.adapter.invoke(name,args)
 def finish(self):
  self.after=self.authority('FINAL');outcome=evaluate_order_effect(self.ct['effect'],self.ct['experiment']['environment_id'],self.before['data'],self.after['data']);c.require(outcome['contract_outcome']=='CONTRACT_SATISFIED_IN_RUN','ORDER_ORACLE');return dict(before=self.before,after=self.after,oracle=outcome,backend='REAL_LOCAL_SQLITE',database_sha256=c.sha(self.sandbox.path.read_bytes()))
 def cleanup(self):
  self.reader.available=False
  with closing(sqlite3.connect(self.sandbox.path,timeout=1)) as db:db.execute('BEGIN EXCLUSIVE');db.rollback()
  return dict(database_retained=True,connections_closed=True,exclusive_lock_probe=True)
