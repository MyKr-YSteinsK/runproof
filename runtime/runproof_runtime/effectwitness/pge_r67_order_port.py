"""Versioned OrderPort: unchanged business methods, new owner/path constructors."""
import hashlib, secrets, sqlite3
from contextlib import closing
from . import pge_r67_context as c
from .orders import OrderSandbox, OrderAdapter, AuthorityReader
from .contracts import ENV_REVISION, READER_ID
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
    # No legacy constructor or owned_path/storage_task dispatch is called.
    def __init__(self,ctx,ct):
        self.contracts=Bridge(ct);self.owner='rpf-67-rev-3';self.storage_task='rpf-67-rev-3';self.directory=ctx.scope(ctx.root/'business');self.path=ctx.scope(self.directory/'orders.sqlite3');self.created=False;self.generation=0
class Reader(AuthorityReader):
    def __init__(self,ctx,sandbox):
        self.path=ctx.scope(sandbox.path);self.contracts=sandbox.contracts;self._seal=secrets.token_bytes(32);self.available=True
class OrderPort:
    def validate_contract(self,ctx,ct):c.validate_contract(ct);c.require(ct==ctx.ct,'ORDER_CONTEXT')
    def prepare(self,ctx,ct,ledger):
        self.validate_contract(ctx,ct);self.ctx=ctx;self.ct=ct;self.ledger=ledger;self.trace=[];self.pending=None;self.responses=[]
        self.sandbox=Sandbox(ctx,ct);self.reader=Reader(ctx,self.sandbox);self.adapter=OrderAdapter(self.sandbox)
        self.fault=dict.fromkeys(('planned','triggered','observed','agent_exposed'),False);self.fault['planned']=True
        ticket=ledger.reserve('sqlite_setup');self.sandbox.initialize();ledger.settle(ticket,status='CREATED')
        self.before=self.read('BEFORE');self.committed=None;self.after=None
    def read(self,phase):
        ticket=self.ledger.reserve('authority',phase=phase);s=self.reader.read();self.reader.validate(s);value=s.public();self.ledger.settle(ticket,status='READ_ONLY',phase=phase,snapshot=value,connection='SQLITE_MODE_RO_QUERY_ONLY');return value
    def allowed(self,name,args):
        c.require(name in c.TOOLS and args==c.args_for(name,self.ct['effect']),'TOOL_ARGUMENTS')
        if name==c.TOOLS[1]:c.require(type(args['amount_minor']) is int,'AMOUNT_TYPE')
        names=[t['name'] for t in self.trace]
        c.require((not names and name==c.TOOLS[0]) or (names==[c.TOOLS[0]] and name==c.TOOLS[1]) or (names==list(c.TOOLS[:2]) and name==c.TOOLS[2] and self.fault['agent_exposed']),'TOOL_ORDER_OR_UNKNOWN_STOP')
    def register(self,response_id,call):
        c.require(self.pending is None and response_id not in self.responses,'RESPONSE_ID_REPLAY');self.responses.append(response_id)
        if call:
            self.allowed(call['name'],call['arguments']);c.require(call['call_id'] not in [t['call_id'] for t in self.trace],'TOOL_ID_REPLAY');self.pending=dict(response_id=response_id,**call);self.ledger.append('INTENT',**self.pending)
        else:c.require([t['name'] for t in self.trace] in (list(c.TOOLS[:2]),list(c.TOOLS)) and self.fault['agent_exposed'],'PREMATURE_STOP')
    def invoke(self,value):
        c.require(self.pending is not None and value=={k:self.pending[k] for k in ('call_id','name','arguments')},'MODEL_TOOL_LINEAGE')
        name,args=value['name'],value['arguments'];self.allowed(name,args)
        if name==c.TOOLS[0]:result=self.adapter.invoke(name,args)
        elif name==c.TOOLS[1]:
            ticket=self.ledger.reserve('sqlite_refund',arguments_sha256=c.digest(args),call_id=value['call_id'])
            try:
                actual=self.adapter.invoke(name,args);c.require(actual['status']=='COMMITTED','BUSINESS_COMMIT')
                self.ledger.settle(ticket,status='COMMITTED',receipt=actual);self.committed=self.read('AFTER_COMMIT_BEFORE_UNKNOWN')
                c.require(evaluate_order_effect(self.ct['effect'],self.ct['experiment']['environment_id'],self.before['data'],self.committed['data'])['contract_outcome']=='CONTRACT_SATISFIED_IN_RUN','COMMIT_READBACK')
                self.fault.update(triggered=True,observed=True)
                result=dict(status='UNKNOWN_OUTCOME',operation_id=args['operation_id'],reason='CONTROLLED_POST_COMMIT_RESPONSE_LOSS',write_policy='STOP_WRITES_READ_ONLY_RECONCILE')
            except BaseException:
                if ticket not in self.ledger.read()['results']:self.ledger.settle(ticket,status='UNKNOWN',unknown=True)
                raise
        else:
            data=self.read('OPTIONAL_AGENT_RECONCILE')['data'];receipt=data['receipts'];c.require(len(receipt)==1 and receipt[0]['operation_id']==args['operation_id'],'RECONCILE_RECEIPT');result=dict(status='COMMITTED',receipt=receipt[0],readonly=True)
        trace=dict(**self.pending,result=result,result_sha256=c.digest(result));self.trace.append(trace);self.pending=None
        self.ledger.append('TOOL_RETURN',**trace)
        if name==c.TOOLS[1]:self.fault['agent_exposed']=True;self.ledger.append('FAULT_EXPOSED',fault=self.fault)
        return result
    def execute(self,ctx,ct,ledger,*,driver):
        self.prepare(ctx,ct,ledger)
        try:
            sdk=driver.run(self)
            self.after=self.read('CONTROLLER_FINAL_RECONCILE')
            result=dict(source_kind=ctx.public()['source_kind'],backend='REAL_LOCAL_SQLITE',before=self.before,committed=self.committed,after=self.after,trace=self.trace,fault=self.fault,sdk=sdk,database_sha256=c.sha(self.sandbox.path.read_bytes()),cleanup={})
            return result
        finally:
            self.reader.available=False
            self.cleanup_result=self.cleanup(ctx,ct,None)
    def verify(self,ctx,ct,evidence):
        self.validate_contract(ctx,ct)
        return evaluate_order_effect(ct['effect'],ct['experiment']['environment_id'],evidence['before']['data'],evidence['after']['data'])
    def cleanup(self,ctx,ct,evidence):
        path=ctx.scope(ctx.root/'business/orders.sqlite3')
        with closing(sqlite3.connect(path,timeout=1)) as db:db.execute('BEGIN EXCLUSIVE');db.rollback()
        result=dict(connections_closed=True,exclusive_lock_probe=True,database_retained_for_evidence=True)
        if evidence is not None:evidence['cleanup']=result
        return result
