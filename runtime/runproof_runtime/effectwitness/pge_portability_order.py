"""Order adapter composes the unchanged SQLite transaction and authenticated RO Reader."""
import hashlib,os,secrets,sqlite3
from contextlib import closing
from . import pge_port_context as c
from .pge_domain_port import classify,projection
from .orders import OrderSandbox,OrderAdapter,AuthorityReader
from .contracts import ENV_REVISION,READER_ID
from .effect_oracle import evaluate_order_effect
class Bridge:
 def __init__(self,ct):self.ct=ct
 @property
 def execution(self):return self.ct['execution']
 @property
 def effect(self):return self.ct['effect']
 @property
 def experiment(self):return self.ct['experiment']
 def validate(self):c.validate_contract(self.ct)
class Sandbox(OrderSandbox):
 def __init__(self,ctx,ct):
  self.contracts=Bridge(ct);self.owner=ctx.public()['owner'];self.storage_task=self.owner;self.directory=ctx.folder(ct)/'sqlite';self.path=ctx.scope(self.directory/'orders.sqlite3');self.created=False;self.generation=0
class Reader(AuthorityReader):
 def __init__(self,ctx,sandbox):self.path=ctx.scope(sandbox.path);self.contracts=sandbox.contracts;self._seal=secrets.token_bytes(32);self.available=True
class OrderPort:
 def validate_contract(self,ctx,ct):c.validate_contract(ct);c.require(ct==ctx.contract(c.DOMAINS[0]),'ORDER_CONTEXT')
 def execute(self,ctx,ct,ledger):
  self.validate_contract(ctx,ct);sandbox=Sandbox(ctx,ct);run=ct['experiment']['run_id'];folder=ctx.folder(ct);folder.mkdir(parents=True,exist_ok=False)
  init=ledger.reserve('sqlite_setup',domain=c.DOMAINS[0],run_id=run);sandbox.initialize();ledger.settle(init,status='CREATED')
  reader=Reader(ctx,sandbox);adapter=OrderAdapter(sandbox);before=reader.read();reader.validate(before);inspect=adapter.invoke('inspect_order',{'order_id':ct['effect']['order_id']});args={k:ct['effect'][k] for k in ('order_id','operation_id','amount_minor')}
  ticket=ledger.reserve('sqlite_refund',domain=c.DOMAINS[0],run_id=run,arguments_sha256=c.digest(args))
  try:
   result=adapter.invoke('refund_order',args);c.require(result['status']=='COMMITTED','ORDER_UNKNOWN_STOP');ledger.settle(ticket,status='COMMITTED',receipt_id=result['receipt_id']);after=reader.read();reader.validate(after)
   evidence={'backend':'REAL_LOCAL_SQLITE','source_kind':'DETERMINISTIC','executor_pid':os.getpid(),'before':before.public(),'after':after.public(),'inspect':inspect,'tool_call':{'name':'refund_order','arguments':args,'result':result},'fault':dict.fromkeys(('planned','triggered','observed','agent_exposed'),False),'database_sha256':hashlib.sha256(sandbox.path.read_bytes()).hexdigest(),'cleanup':{}}
   ctx.once(folder/'received-before-cleanup.json',evidence)
  except Exception:
   ctx.once(folder/'failure-before-cleanup.json',{'phase':'REFUND_OR_READBACK','write_ticket':ticket,'before':before.public()});raise
  finally:reader.available=False
  evidence['cleanup']=self.cleanup(ctx,ct,evidence);return evidence
 def verify(self,ctx,ct,e):
  self.validate_contract(ctx,ct);synthetic=ctx.public()['source_kind']=='SYNTHETIC_TEST_ONLY';c.require(e['source_kind']==('SYNTHETIC_TEST_ONLY' if synthetic else 'DETERMINISTIC') and e['backend']==('SYNTHETIC_TEST_ONLY' if synthetic else 'REAL_LOCAL_SQLITE'),'ORDER_SOURCE')
  c.require(set(e)=={'backend','source_kind','executor_pid','before','after','inspect','tool_call','fault','database_sha256','cleanup'},'ORDER_EVIDENCE_FIELDS')
  f,x=ct['effect'],ct['experiment']
  for snapshot in (e['before'],e['after']):
   data=snapshot['data'];c.require(set(snapshot)=={'data','sha256'} and set(data)=={'reader_id','reader_version','source_id','environment','order','receipts'},'ORDER_AUTHORITY_FIELDS');c.require(snapshot['sha256']==c.digest(data) and data['reader_id']==READER_ID and data['reader_version']=='1' and data['source_id']==f['authority_id'] and data['environment']=={'owner':x['owner'],'run_id':x['run_id'],'environment_id':x['environment_id'],'environment_revision':ENV_REVISION,'reset_generation':0},'ORDER_AUTHORITY_IDENTITY')
  verdict=evaluate_order_effect(f,x['environment_id'],e['before']['data'],e['after']['data']);c.require(verdict['contract_outcome']=='CONTRACT_SATISFIED_IN_RUN','ORDER_ORACLE')
  receipt=e['after']['data']['receipts'][0];c.require(e['inspect']=={'order_id':f['order_id'],'status':'PAID','revision':0} and e['tool_call']=={'name':'refund_order','arguments':{k:f[k] for k in ('order_id','operation_id','amount_minor')},'result':{'status':'COMMITTED','operation_id':f['operation_id'],'receipt_id':receipt['receipt_id'],'committed_revision':1}},'ORDER_OPERATION_RECEIPT')
  c.require(e['fault']==dict.fromkeys(('planned','triggered','observed','agent_exposed'),False) and e['cleanup']=={'connections_closed':True,'exclusive_lock_probe':True,'database_retained_for_evidence':True},'ORDER_CLEANUP_OR_FAULT')
  return projection(c.DOMAINS[0],e['source_kind'],f['authority'],classify(verdict['contract_outcome'],e['fault']),[c.DOMAINS[0]+'/full-refund-one-receipt'])
 def cleanup(self,ctx,ct,e):
  path=ctx.scope(ctx.folder(ct)/'sqlite/orders.sqlite3');c.require(path.is_file(),'ORDER_DATABASE_MISSING')
  with closing(sqlite3.connect(path,timeout=1)) as db:db.execute('BEGIN EXCLUSIVE');db.rollback()
  return {'connections_closed':True,'exclusive_lock_probe':True,'database_retained_for_evidence':True}
