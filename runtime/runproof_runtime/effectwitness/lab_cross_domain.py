"""RPF-60: one durable account for real Explorer and either static domain.

Versioned WAL lifecycle adapted from RPF-58 v2; no historical globals changed.
"""
import copy,hashlib,os,time
from .lab_cross_domain_contracts import canonical,digest,strict_json,require,scoped,validate_plan,sources,DOMAINS,LIMITS,MODEL

def validate_state(s,p):
    require(set(s)=={'session_id','plan_sha256','started_ns','reservations','events'} and s['session_id']==p['session_id']
        and s['plan_sha256']==digest(p) and type(s['started_ns']) is int,'LEDGER_IDENTITY')
    totals={k:0 for k in LIMITS};keys=set();ids=set()
    for i,r in enumerate(s['reservations'],1):
        require(set(r)=={'id','round','domain','label','units','status','detail'} and r['id']==i and r['round'] in (1,2)
            and r['domain'] in (*DOMAINS,'explorer') and r['status'] in ('RESERVED','DONE','UNKNOWN'),'RESOURCE_FIELDS')
        key=(r['round'],r['domain'],r['label']);require(key not in keys,'RESOURCE_REPLAY');keys.add(key)
        require(type(r['units']) is dict and bool(r['units']) and set(r['units'])<=set(LIMITS)
            and all(type(v) is int and v>0 for v in r['units'].values()),'RESOURCE_UNITS')
        for k,v in r['units'].items():totals[k]+=v
        if r['domain']=='explorer':
            require(r['label']=='provider' and r['units']=={'provider':1,'token_reserve':3000,'cost_micro_cny':54000},'PROVIDER_RESERVATION')
            if r['status']=='DONE':
                d=r['detail'];u=d['usage']
                require(set(d)=={'request_sha256','usage','response_id','returned_model'} and type(d['response_id']) is str
                    and d['response_id'] not in ids and d['returned_model'] in (MODEL,'DeepSeek-V4.1-Flash-1017'),'PROVIDER_IDENTITY')
                ids.add(d['response_id'])
                require(set(u)=={'prompt_tokens','completion_tokens','total_tokens'} and all(type(v) is int and v>=0 for v in u.values())
                    and u['prompt_tokens']+u['completion_tokens']==u['total_tokens']<=3000 and u['completion_tokens']<=128,'USAGE_UNKNOWN_OR_LIMIT')
    require(all(totals[k]<=v for k,v in LIMITS.items()),'GLOBAL_BUDGET')
    events=s['events'];require([e['seq'] for e in events]==list(range(1,len(events)+1)) and all(set(e)=={'seq','monotonic_ns','kind','data'}
        and type(e['monotonic_ns']) is int and s['started_ns']<=e['monotonic_ns']<=s['started_ns']+2400*10**9 for e in events)
        and all(a['monotonic_ns']<b['monotonic_ns'] for a,b in zip(events,events[1:])),'EVENT_TIME')
    return totals

class Ledger:
    def __init__(self,path,plan,*,create=False):
        validate_plan(plan);require(plan['source_files']==sources(),'SOURCE_DRIFT')
        self.path,self.plan=scoped(path),plan
        if create:
            self.path.mkdir(exist_ok=False)
            self._write({'session_id':plan['session_id'],'plan_sha256':digest(plan),'started_ns':time.monotonic_ns(),'reservations':[],'events':[]},None,0)
        self.read()
    def _write(self,s,previous,seq):
        validate_state(s,self.plan);v={'seq':seq,'previous_sha256':previous,'state':s,'state_sha256':digest(s)}
        with scoped(self.path/f'snapshot-{seq:04}.json').open('xb') as f:f.write(canonical(v));f.flush();os.fsync(f.fileno())
    def read(self):
        files=sorted(scoped(self.path).glob('snapshot-*.json'));require(bool(files),'LEDGER_MISSING')
        chain=[strict_json(scoped(p).read_bytes()) for p in files]
        for i,path in enumerate(files):require(path.name==f'snapshot-{i:04}.json','TORN_SNAPSHOT')
        s=verify_chain(chain,self.plan)
        self.state,self.chain,self.previous,self.seq=s,chain,digest(chain[-1]),len(chain)
        return copy.deepcopy(s)
    def mutate(self,fn):
        lock=scoped(self.path/'mutation.lock')
        try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:require(False,'LOCK_COLLISION_OR_UNCLEAN_RESTART')
        try:
            s=self.read();require(time.monotonic_ns()-s['started_ns']<2400*10**9,'SESSION_DEADLINE')
            require(sources()==self.plan['source_files'],'SOURCE_DRIFT')
            out=fn(s);self._write(s,self.previous,self.seq);self.read();return out
        finally:os.close(fd);lock.unlink()
    @staticmethod
    def _event(s,kind,data):
        e={'seq':len(s['events'])+1,'monotonic_ns':time.monotonic_ns(),'kind':kind,'data':data};s['events'].append(e);return e
    def event(self,kind,**data):return self.mutate(lambda s:self._event(s,kind,data))
    def reserve(self,round_index,domain,label,units):
        def op(s):
            require(not any(r['status']=='UNKNOWN' or (r['status']=='RESERVED' and any(k in r['units'] for k in ('post','sqlite_mutation','provider'))) for r in s['reservations']),'UNKNOWN_IO_STOP')
            trials=[r for r in s['reservations'] if 'trial' in r['units']]
            if domain=='explorer':
                require(round_index==len(trials)+1 and all(r['status']=='DONE' for r in trials),'EXPLORER_ROUND_SEQUENCE')
            elif 'trial' in units:
                providers=[r for r in s['reservations'] if r['round']==round_index and r['domain']=='explorer']
                require(round_index==len(trials)+1 and all(r['status']=='DONE' for r in trials) and len(providers)==1 and providers[0]['status']=='DONE'
                    and units=={'trial':1,'order_trial' if domain==DOMAINS[0] else 'config_trial':1},'TRIAL_SEQUENCE_OR_PROVIDER')
            else:
                active=[r for r in trials if r['status']=='RESERVED']
                require(len(active)==1 and active[0]['round']==round_index and active[0]['domain']==domain,'ACTIVE_TRIAL_REQUIRED')
                allowed={'sqlite_mutation'} if domain==DOMAINS[0] else {'jvm','sdk','business_http','post','health'}
                require(set(units)<=allowed and all(v==1 for v in units.values()),'DOMAIN_RESOURCE_ALLOWLIST')
            r={'id':len(s['reservations'])+1,'round':round_index,'domain':domain,'label':label,'units':units,'status':'RESERVED','detail':None}
            s['reservations'].append(r);validate_state(s,self.plan)
            self._event(s,'RESOURCE_RESERVED',{k:r[k] for k in ('id','round','domain','label','units')});return r['id']
        return self.mutate(op)
    def settle(self,number,detail,*,unknown=False):
        def op(s):
            r=s['reservations'][number-1];require(r['status']=='RESERVED','SETTLEMENT_REPLAY')
            r.update(status='UNKNOWN' if unknown else 'DONE',detail=detail)
            self._event(s,'RESOURCE_SETTLED',{'id':number,'status':r['status'],'detail_sha256':digest(detail)})
        self.mutate(op)
    def reserve_request(self,role,round_index,body):
        require(role=='EXPLORER' and len(canonical(body))+128<=3000,'PROVIDER_REQUEST_SIZE')
        n=self.reserve(round_index,'explorer','provider',{'provider':1,'token_reserve':3000,'cost_micro_cny':54000})
        self.event('PROVIDER_REQUEST_FROZEN',round=round_index,reservation_id=n,request_sha256=digest(body));return n
    def received(self,attempt,data):
        self.read();events=[e for e in self.state['events'] if e['kind']=='PROVIDER_REQUEST_FROZEN' and e['data']['reservation_id']==attempt]
        require(len(events)==1,'REQUEST_BINDING')
        u=data.get('usage');require(type(u) is dict and all(k in u for k in ('prompt_tokens','completion_tokens','total_tokens')),'USAGE_UNKNOWN')
        detail={'request_sha256':events[0]['data']['request_sha256'],'usage':{k:u[k] for k in ('prompt_tokens','completion_tokens','total_tokens')},
            'response_id':data.get('id'),'returned_model':data.get('model')}
        self.settle(attempt,detail)

def verify_chain(chain,plan):
    require(type(chain) is list and bool(chain),'CHAIN_REQUIRED');previous=None;old=None
    for i,v in enumerate(chain):
        require(set(v)=={'seq','previous_sha256','state','state_sha256'} and v['seq']==i and v['previous_sha256']==previous and v['state_sha256']==digest(v['state']),'TORN_OR_CHAIN')
        s=v['state'];validate_state(s,plan)
        if old is not None:
            require(s['started_ns']==old['started_ns'] and s['events'][:len(old['events'])]==old['events'] and len(s['reservations'])>=len(old['reservations']),'WAL_HISTORY_REMOVED')
            for a,b in zip(old['reservations'],s['reservations']):
                require(all(a[k]==b[k] for k in ('id','round','domain','label','units')) and (a==b or (a['status']=='RESERVED' and b['status'] in ('DONE','UNKNOWN'))),'WAL_REFUND_OR_REWRITE')
        old=s;previous=digest(v)
    return copy.deepcopy(old)

class RoundAccount:
    """Capability limited view into the same physical ledger, never a new account."""
    def __init__(self,total,index):self.total,self.index=total,index
    def reserve(self,domain,label,units):return self.total.reserve(self.index,domain,label,units)
    def settle(self,*args,**kwargs):return self.total.settle(*args,**kwargs)
    def event(self,kind,**data):return self.total.event(kind,round=self.index,**data)

def domain_port(domain):
    require(domain in DOMAINS,'STATIC_DOMAIN_ALLOWLIST')
    return ORDER_PORT if domain==DOMAINS[0] else CONFIG_PORT

def dispatch_identity(fn):
    return {'entry_code_sha256':hashlib.sha256(SharedSession.execute_trial.__code__.co_code).hexdigest(),
        'port_callable':fn.__module__+'.'+fn.__qualname__,'port_code_sha256':hashlib.sha256(fn.__code__.co_code).hexdigest()}

class SharedSession:
    def __init__(self,ledger):self.ledger,self.rows=ledger,[]
    def execute_trial(self,selection,body,observation,attempt):
        from .lab_cross_domain_contracts import domain_for
        from .lab_cross_domain_contracts import parse_selection,body_for,messages_for
        from .lab_cross_domain_contracts import visible,project
        from .lab_cross_domain_verify import domain_verdict,validate_observation
        index=len(self.rows)+1;require(index<=2 and sources()==self.ledger.plan['source_files'],'SESSION_OR_SOURCE')
        require(body==body_for(messages_for(self.rows)),'EXPLORER_INPUT_DRIFT')
        validate_observation(selection,observation,body,{r['selection']['id'] for r in self.rows})
        candidate=strict_json(selection['function']['arguments'].encode())['candidate_id']
        contract=self.ledger.plan['rounds'][index-1]['candidates'][candidate];domain=domain_for(candidate)
        self.ledger.read();provider=self.ledger.state['reservations'][attempt-1]
        require(provider['round']==index and provider['domain']=='explorer' and provider['status']=='DONE' and provider['detail']['request_sha256']==digest(body),'SELECTION_PROVIDER_BINDING')
        self.ledger.event('CHOICE_FROZEN',round=index,selection_sha256=digest(selection),candidate_id=candidate,contract_sha256=digest(contract))
        account=RoundAccount(self.ledger,index);reservation=account.reserve(domain,'trial',{'trial':1,'order_trial' if domain==DOMAINS[0] else 'config_trial':1})
        fn=domain_port(domain).execute;identity=dispatch_identity(fn)
        account.event('SHARED_PORT_DISPATCH',domain=domain,runtime_identity=identity,contract_sha256=digest(contract))
        account.event('DOMAIN_CALL_ENTERED',domain=domain,runtime_identity=identity)
        evidence=fn(contract,account)
        account.event('DOMAIN_CALL_RETURNED',domain=domain,runtime_identity=identity,evidence_sha256=digest(evidence))
        verdict=domain_verdict(contract,evidence);account.event('DOMAIN_VERIFIED',domain=domain,verdict_sha256=digest(verdict))
        fb=project(contract,evidence,[r['feedback'] for r in self.rows]);account.event('FEEDBACK_FROZEN',domain=domain,feedback_sha256=digest(fb),tool_call_id=selection['id'])
        account.settle(reservation,{'evidence_sha256':digest(evidence),'feedback_sha256':digest(fb)})
        row={'round':index,'candidate_id':candidate,'contract':contract,'body':body,'observation':observation,'selection':selection,'provider_reservation':attempt,
            'trial_reservation':reservation,'evidence':evidence,'feedback':fb,'input':visible([r['feedback'] for r in self.rows])}
        self.rows.append(row);return row

class TaskGuard:
    """Separate append-only task intents, never reset by a source revision.

    Metadata <=2, cold <=2 (only after diagnosed FAIL and changed source),
    formal session <=1. A reservation remains spent after interruption.
    """
    def __init__(self,path):self.path=scoped(path);self.path.mkdir(parents=True,exist_ok=True)
    def read(self):
        scoped(self.path);previous=None;records=[];reservations={};counts={"METADATA":0,"COLD":0,"SESSION":0}
        files=sorted(self.path.glob("intent-*.json"))
        for i,path in enumerate(files,1):
            value=strict_json(scoped(path).read_bytes());record=value["record"]
            require(path.name==f"intent-{i:04}.json" and set(value)=={"seq","previous_sha256","record","record_sha256"}
                and value["seq"]==i and value["previous_sha256"]==previous and value["record_sha256"]==digest(record),"TASK_INTENT_TORN_OR_CHAIN")
            if record["action"]=="RESERVE":
                require(set(record)=={"action","kind","ordinal","source_sha256","data"} and record["kind"] in counts
                    and type(record["source_sha256"]) is str and len(record["source_sha256"])==64,"TASK_INTENT_FIELDS")
                kind=record["kind"];counts[kind]+=1;require(record["ordinal"]==counts[kind],"TASK_ATTEMPT_SEQUENCE")
                reservations[i]={**record,"reservation_id":i,"status":None}
            else:
                require(set(record)=={"action","reservation_id","status","detail"} and record["action"]=="RESULT"
                    and record["reservation_id"] in reservations and record["status"] in ("PASS","FAIL"),"TASK_RESULT_FIELDS")
                row=reservations[record["reservation_id"]];require(row["status"] is None,"TASK_RESULT_REPLAY");row.update(status=record["status"],detail=record["detail"])
            previous=digest(value);records.append(value)
        require(counts["METADATA"]<=2 and counts["COLD"]<=2 and counts["SESSION"]<=1,"TASK_ATTEMPT_BUDGET")
        self.previous,self.seq,self.rows=previous,len(records),list(reservations.values())
        return records
    def _append(self,make):
        lock=scoped(self.path/"intent.lock")
        try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:require(False,"TASK_INTENT_LOCK")
        try:
            self.read();record=make(self.rows);i=self.seq+1
            value={"seq":i,"previous_sha256":self.previous,"record":record,"record_sha256":digest(record)}
            with scoped(self.path/f"intent-{i:04}.json").open("xb") as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
            self.read();return i
        finally:os.close(fd);lock.unlink()
    def reserve(self,kind,source_sha256,**data):
        def make(rows):
            require(kind in ("METADATA","COLD","SESSION"),"TASK_KIND")
            same=[r for r in rows if r["kind"]==kind];limit={"METADATA":2,"COLD":2,"SESSION":1}[kind]
            require(len(same)<limit,"TASK_ATTEMPT_EXHAUSTED")
            if kind=="COLD" and same:
                require(all(r["status"]=="FAIL" for r in same) and same[-1]["source_sha256"]!=source_sha256
                    and bool(data.get("offline_gate_sha256")),"COLD_RETRY_REQUIRES_REPAIRED_SOURCE")
            return {"action":"RESERVE","kind":kind,"ordinal":len(same)+1,"source_sha256":source_sha256,"data":data}
        return self._append(make)
    def result(self,reservation_id,status,**detail):
        def make(rows):
            require(any(r["reservation_id"]==reservation_id and r["status"] is None for r in rows),"TASK_RESULT_REPLAY")
            return {"action":"RESULT","reservation_id":reservation_id,"status":status,"detail":detail}
        self._append(make)

def verify_task_records(records):
    """Pure external-log checks, including cross-source retry eligibility."""
    previous=None;rows={};counts={"METADATA":0,"COLD":0,"SESSION":0}
    for i,value in enumerate(records,1):
        record=value["record"]
        require(set(value)=={"seq","previous_sha256","record","record_sha256"} and value["seq"]==i
            and value["previous_sha256"]==previous and value["record_sha256"]==digest(record),"TASK_EXTERNAL_CHAIN")
        if record["action"]=="RESERVE":
            kind=record["kind"];require(kind in counts,"TASK_KIND");prior=[r for r in rows.values() if r["kind"]==kind]
            if kind=="COLD" and prior:require(all(r["status"]=="FAIL" for r in prior)
                and prior[-1]["source_sha256"]!=record["source_sha256"] and bool(record["data"].get("offline_gate_sha256")),"TASK_RETRY_SOURCE")
            counts[kind]+=1;require(record["ordinal"]==counts[kind],"TASK_EXTERNAL_SEQUENCE")
            rows[i]={**record,"reservation_id":i,"status":None}
        else:
            require(record["action"]=="RESULT" and record["reservation_id"] in rows and record["status"] in ("PASS","FAIL"),"TASK_EXTERNAL_RESULT")
            row=rows[record["reservation_id"]];require(row["status"] is None,"TASK_EXTERNAL_RESULT_REPLAY");row.update(status=record["status"],detail=record["detail"])
        previous=digest(value)
    require(counts["METADATA"]<=2 and counts["COLD"]<=2 and counts["SESSION"]<=1,"TASK_EXTERNAL_BUDGET")
    return list(rows.values())

"""Fresh RPF-60 order sandbox; unchanged refund transaction and RO Reader."""
from contextlib import closing
from pathlib import Path
import hashlib,os,secrets,sqlite3,time
from .lab_cross_domain_contracts import WORK,DOMAINS,canonical,digest,require,scoped,validate_trial
from .orders import OrderSandbox,OrderAdapter,AuthorityReader
from .contracts import ENV_REVISION,READER_ID
from .effect_oracle import evaluate_order_effect

class OrderBridge:
    def __init__(self,c):validate_trial(c);require(c["experiment"]["domain"]==DOMAINS[0],"ORDER_DOMAIN");self.c=c
    @property
    def execution(self):return self.c["execution"]
    @property
    def effect(self):return self.c["effect"]
    @property
    def experiment(self):return self.c["experiment"]
    def validate(self):validate_trial(self.c)

class OrderTrialSandbox(OrderSandbox):
    def __init__(self,c):
        self.contracts=OrderBridge(c);self.owner="rpf-60";self.storage_task="rpf-60"
        self.directory=scoped(WORK/"sandboxes"/c["experiment"]["run_id"])
        self.path=scoped(self.directory/"orders.sqlite3");self.created=False;self.generation=0

class OrderTrialReader(AuthorityReader):
    def __init__(self,sandbox):
        self.path=scoped(sandbox.path);self.contracts=sandbox.contracts;self._seal=secrets.token_bytes(32);self.available=True

def order_execute(c,ledger):
    validate_trial(c);domain=c["experiment"]["domain"]
    sandbox=OrderTrialSandbox(c);timeline=[]
    def mark(kind,**data):
        event=ledger.event("ORDER_PORT_EVENT",port_kind=kind,**data);timeline.append({"kind":kind,"monotonic_ns":event["monotonic_ns"],"data":data})
    mark("PORT_ENTERED",run_id=c["experiment"]["run_id"])
    sandbox.initialize();reader=OrderTrialReader(sandbox);adapter=OrderAdapter(sandbox)
    before=reader.read();reader.validate(before);mark("AUTHORITY_BEFORE",sha256=before.sha256)
    inspect=adapter.invoke("inspect_order",{"order_id":c["effect"]["order_id"]})
    reservation=ledger.reserve(domain,"refund_order",{"sqlite_mutation":1})
    args={k:c["effect"][k] for k in ("order_id","operation_id","amount_minor")}
    try:
        result=adapter.invoke("refund_order",args)
        require(result["status"]=="COMMITTED","ORDER_UNCERTAIN_STOP_WRITES")
        ledger.settle(reservation,{"receipt_id":result["receipt_id"],"status":result["status"]})
        mark("REFUND_COMMITTED",operation_id=args["operation_id"],receipt_id=result["receipt_id"])
        after=reader.read();reader.validate(after);mark("AUTHORITY_AFTER",sha256=after.sha256)
    except Exception:
        # Preserve the one reservation and database; never replay the mutation.
        raise
    with closing(sqlite3.connect(sandbox.path,timeout=1)) as db:
        db.execute("BEGIN EXCLUSIVE");db.rollback()
    reader.available=False
    cleanup={"connections_closed":True,"exclusive_lock_probe":True,"database_retained_for_evidence":True}
    mark("CLEANUP_CONFIRMED",**cleanup)
    return {"schema":"rpf60-order-trial-v1","domain":domain,"source_kind":"REAL_LOCAL_SQLITE_DETERMINISTIC",
        "executor_pid":os.getpid(),"before":before.public(),"after":after.public(),"inspect":inspect,
        "tool_call":{"name":"refund_order","arguments":args,"result":result},"fault":{"planned":False,"triggered":False,"observed":False},
        "database_sha256":hashlib.sha256(sandbox.path.read_bytes()).hexdigest(),"timeline":timeline,"cleanup":cleanup}

def order_verify(c,e):
    validate_trial(c);require(set(e)=={"schema","domain","source_kind","executor_pid","before","after","inspect","tool_call","fault","database_sha256","timeline","cleanup"}
        and e["schema"]=="rpf60-order-trial-v1" and e["domain"]==DOMAINS[0] and e["source_kind"] in ("REAL_LOCAL_SQLITE_DETERMINISTIC","SYNTHETIC_TEST_ONLY"),"ORDER_EVIDENCE_FIELDS")
    if e["source_kind"]!="SYNTHETIC_TEST_ONLY":require(type(e["executor_pid"]) is int and e["executor_pid"]>0,"ORDER_REAL_ORIGIN")
    x,f=c["experiment"],c["effect"]
    for snapshot in (e["before"],e["after"]):
        d=snapshot["data"]
        require(set(snapshot)=={"data","sha256"} and snapshot["sha256"]==digest(d) and set(d)=={"reader_id","reader_version","source_id","environment","order","receipts"}
            and d["reader_id"]==READER_ID and d["reader_version"]=="1" and d["source_id"]==f["authority_id"]
            and d["environment"]=={"owner":"rpf-60","run_id":x["run_id"],"environment_id":x["environment_id"],"environment_revision":ENV_REVISION,"reset_generation":0},"ORDER_AUTHORITY_IDENTITY")
        require(all(type(d["order"][k]) is int for k in ("paid_minor","refunded_minor","revision")) and type(d["environment"]["reset_generation"]) is int
            and type(d["receipts"]) is list and all(type(r[k]) is int for r in d["receipts"] for k in ("amount_minor","committed_revision")),"ORDER_AUTHORITY_TYPES")
    verdict=evaluate_order_effect(f,x["environment_id"],e["before"]["data"],e["after"]["data"])
    require(verdict["contract_outcome"]=="CONTRACT_SATISFIED_IN_RUN","ORDER_EFFECT_REJECTED")
    receipt=e["after"]["data"]["receipts"][0]
    require(e["inspect"]=={"order_id":f["order_id"],"status":"PAID","revision":0}
        and e["tool_call"]=={"name":"refund_order","arguments":{k:f[k] for k in ("order_id","operation_id","amount_minor")},
            "result":{"status":"COMMITTED","operation_id":f["operation_id"],"receipt_id":receipt["receipt_id"],"committed_revision":1}},"ORDER_TOOL_RECEIPT")
    require(e["fault"]=={"planned":False,"triggered":False,"observed":False} and e["cleanup"]=={"connections_closed":True,"exclusive_lock_probe":True,"database_retained_for_evidence":True},"ORDER_FAULT_OR_CLEANUP")
    timeline=e["timeline"]
    require([t["kind"] for t in timeline]==["PORT_ENTERED","AUTHORITY_BEFORE","REFUND_COMMITTED","AUTHORITY_AFTER","CLEANUP_CONFIRMED"]
        and all(a["monotonic_ns"]<b["monotonic_ns"] for a,b in zip(timeline,timeline[1:]))
        and timeline[1]["data"]=={"sha256":e["before"]["sha256"]} and timeline[3]["data"]=={"sha256":e["after"]["sha256"]},"ORDER_AUTHORITY_TIME")
    return {"domain":DOMAINS[0],"outcome":"SATISFIED","authority":"SQLITE_READ_ONLY_RECEIPT_READER","receipt_hash":verdict["receipt_hash"]}

"""RPF-60 Java/SDK Fixture port; no Provider credentials or network permitted.

Domain-specific scene predicates are a reviewed copy of RPF-55 verify_scene,
bound to the new contract validator; shared orchestration lives in shared_core.
"""
import ast,hashlib,importlib.util,os,secrets,shutil,subprocess,sys,time
from pathlib import Path
from . import lab_cross_domain_contracts as c,config_live_contracts as oldc
from .lab_cross_domain_contracts import ROOT,WORK,canonical,digest,strict_json,require,scoped,validate_trial
from .config_pge_contracts import CANDIDATES as CONFIG_CANDIDATES
from .config_live_contracts import SOURCE_JAR_SHA256,SDK_CORE_SHA256
from .config_experiment_verify import pinned_sdk_fields
from .config_live_runtime import ConfigLiveHttp,ConfigLiveBusiness,ConfigLiveMemoryBackend,ProviderLedger,_http_contract,_api_response,_valid_item
from .config_live_verify import _history
from .config_pge_target import TargetHost as StableHost
from .config_pge_session import Journal as MemoryJournal
JAR=WORK/"jar/config-center-server-1.0.0.jar"
spec=importlib.util.spec_from_file_location("rpf60_pinned_helpers",ROOT/"spikes/rpf-55/probe.py")
h55=importlib.util.module_from_spec(spec);spec.loader.exec_module(h55);old=h55.old
identity_fields=h55.identity_fields
resolve_direct_python=h55.resolve_direct_python
validate_contracts=validate_trial
def once(path,value):
    path=scoped(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as f:f.write(canonical(value)+b"\n");f.flush();os.fsync(f.fileno())

class Host(StableHost):
    def __init__(self,contracts,ledger,business,journal,*,fixture=True,api_key=None):
        validate_trial(contracts);require(fixture and api_key is None and contracts["execution"]["model_source"]=="FIXTURE_SCRIPTED","FIXTURE_ONLY")
        self.contracts,self.ledger,self.business,self.journal=contracts,ledger,business,journal
        self.fixture,self.api_key=True,None
        self.expected_tool_schema_sha256=self.fixture_failure_code=None
        self.tool_schema_sha256=self.tool_schema_summary=self.tool_definitions=None
        self.runtime=self.failure=None;self.intents,self.tool_returns={},{}
        self.tool_trace,self.tool_rejections,self.visible_contract_checks,self.provider_responses=[],[],[],[]
        self._server=self._thread=None;self.fixture_index=0;self.request_started=time.monotonic();self.stopped=self.activated=False
        self.journal.add("PRE_REGISTERED",candidate=contracts["experiment"]["candidate_id"])

class Journal(MemoryJournal):
    def __init__(self,run_id,total):super().__init__(None,run_id);self.total=total
    def add(self,kind,**data):
        e=super().add(kind,**data);self.total.event("CONFIG_TOOL_EVENT",event=e);return e

class Http(ConfigLiveHttp):
    def __init__(self,contracts,api_key,journal,total,deadline):
        validate_trial(contracts);self.contracts,self.effect=contracts,contracts["effect"]
        self.port=contracts["execution"]["service"]["port"]
        self._api_key,self.journal,self.total,self.deadline=api_key,journal,total,deadline
        self.observations,self.post_count,self.stop_writes=[],0,False
    def request(self,kind,*,reconcile=False):
        method,_,_=_http_contract(self.effect,kind)
        require(len(self.observations)<12 and (method!="POST" or (not self.stop_writes and self.post_count<2)),"BUSINESS_BUDGET")
        units={"business_http":1}
        if method=="POST":units["post"]=1
        r=self.total.reserve("config-java-http","http:"+kind,units)
        self.journal.add("HTTP_RESERVED",http_seq=len(self.observations)+1,method=method,operation=kind)
        result=super().request(kind,reconcile=reconcile)
        self.total.settle(r,{"http_seq":result["seq"],"observation_sha256":digest(result)},unknown=result["transport_error"] is not None)
        self.journal.add("HTTP_COMPLETED",http_seq=result["seq"],status=result["status"],code=(result["response"] or {}).get("code"))
        return result

def sdk_identity_direct():
    """Inspect the authorized direct interpreter; never execute the venv wrapper."""
    cert_raw = (ROOT / "spikes/rpf-53/rev-6/config-live-evidence.json").read_bytes()
    c.require(hashlib.sha256(cert_raw).hexdigest() == "f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43", "OLD_ANCHOR")
    pinned = c.strict_json(cert_raw)["payload"]["contracts"]["execution"]["framework"]["identity"]
    cfg = old.SDK_LAUNCHER.parents[1] / "pyvenv.cfg"
    c.require(not old._has_link_component(cfg), "SDK_CFG_LINK")
    entries = dict(line.split(" = ", 1) for line in cfg.read_text().splitlines() if " = " in line)
    direct = resolve_direct_python(pinned)
    # Reuse the exact reviewed RECORD inspection body, with its venv roots supplied
    # explicitly because sys.prefix now belongs to the direct CPython interpreter.
    tree = ast.parse((ROOT / "spikes/rpf-53/probe.py").read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_sdk_identity")
    assignment = next(n for n in function.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "script" for t in n.targets))
    script = ast.literal_eval(assignment.value)
    script = script.replace('base=pathlib.Path(sys.prefix,"Lib","site-packages").resolve(strict=True)',
        'base=pathlib.Path(sys.argv[1]).resolve(strict=True); sys.path.insert(0,str(base))')
    script = script.replace('venv_root=pathlib.Path(sys.prefix).resolve(strict=True)', 'venv_root=base.parent.parent')
    result = subprocess.run([str(direct), "-I", "-B", "-X", "utf8", "-c", script,
        str(old.SDK_SITE.resolve(strict=True)), str(direct.resolve(strict=True))], cwd=WORK / "diagnostics",
        env=old._sdk_env(WORK / "diagnostics"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    c.require(result.returncode == 0 and not result.stderr, "DIRECT_RECORD_INSPECTION")
    value = c.strict_json(result.stdout)
    value["python_launcher_sha256"] = old._sha_file(old.SDK_LAUNCHER)
    value.pop("base_executable_sha256", None)
    c.require(identity_fields(value) == pinned and value["sdk_core_sha256"] == oldc.SDK_CORE_SHA256
        and value["pydantic"]["record_hashed_entries"] == 443
        and value["openai"]["record_hashed_entries"] == 1999, "DIRECT_SDK_PINNED_IDENTITY")
    return value

def run_sdk(host,contracts,sdk,folder,*,fixture):
    require(fixture,"FIXTURE_ONLY")
    direct=h55.resolve_direct_python(sdk)
    scratch=folder/"sdk-scratch";scratch.mkdir()
    proc=None;thread=None
    try:
        host.start()
        config={"port":host.port,"token":host.token,"write_root":str(scratch),"sdk_readonly_path":str(old.SDK_SITE.resolve()),
            "sdk_site_root_binding_sha256":sdk["sdk_site_root_binding_sha256"],"python_runtime_mapping_sha256":sdk["python_runtime_mapping_sha256"],
            "instructions":c.AGENT_INSTRUCTIONS,"task_prompt":c.TASK_PROMPT,"model":"rpf53-fixture-only",
            "max_runtime_seconds":180,"fixture":True}
        proc=subprocess.Popen([str(direct),"-I","-B",str(ROOT/"runtime/runproof_runtime/effectwitness/config_live_external.py")],
            cwd=scratch,env=old._sdk_env(scratch),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        once(folder/"sdk-process-started.json",{"source_files":c.sources(),"contracts_sha256":digest(contracts),"popen_pid":proc.pid})
        stdout,stderr=proc.communicate(c.canonical(config),timeout=180)
        try:
            parsed=c.strict_json(stdout)
            allowed={"status","framework","version","openai_version","pid","python_executable_sha256","usage_type","usage_fields","requests",
                "input_tokens","output_tokens","tool_calls","tool_callbacks","sdk_source_sha256","openai_source_sha256","final_output_sha256",
                "final_text_persisted","guard_denials","provider_key_present","business_key_present","stage","error_type","guard_code","denied_files"}
            if type(parsed) is not dict or not set(parsed)<=allowed:raise ValueError("REPORT_FIELDS")
            report={k:v for k,v in parsed.items() if k!="denied_files"}
        except Exception:
            report={"status":"REPORT_UNAVAILABLE","error_type":"MALFORMED_REPORT","raw_sha256":hashlib.sha256(stdout).hexdigest()}
        result={"popen_pid":proc.pid,"ready":host.runtime,"report":report,"returncode":proc.returncode,"stderr_bytes":len(stderr)}
        once(folder/"sdk-received.json",{"source_files":c.sources(),"contracts_sha256":digest(contracts),"sdk":result,
            "events":host.journal.events,"tool_trace":host.tool_trace,"completions":host.provider_responses})
        if host.activated:host.journal.add("SDK_ERROR_OBSERVED",returncode=proc.returncode,status=report.get("status"),error_type=report.get("error_type"))
        return result
    except Exception as exc:
        once(folder/"sdk-unavailable.json",{"source_files":c.sources(),"contracts_sha256":digest(contracts),
            "popen_pid":None if proc is None else proc.pid,"ready":host.runtime,"error_type":type(exc).__name__,"winerror":getattr(exc,"winerror",None),
            "events":host.journal.events,"tool_trace":host.tool_trace,"completions":host.provider_responses,"report_status":"UNAVAILABLE"})
        raise
    finally:
        if proc is not None and proc.poll() is None:proc.kill();proc.communicate(timeout=10)
        thread=host._thread;host.close()
        cleanup={"sdk_exited":proc is not None and proc.poll() is not None,
            "host_thread_stopped":thread is None or not thread.is_alive(),
            "host_port_closed":old._port_closed(contracts["execution"]["agent_host"]["port"])}
        once(folder/"sdk-cleanup.json",{"source_files":c.sources(),"cleanup":cleanup})
        c.require(all(cleanup.values()),"SDK_HOST_CLEANUP")

def _verify_scene(s, candidate, source_sha):
    require(type(s) is dict and set(s) == {"contracts", "contracts_sha256", "http", "events",
        "tool_trace", "completions", "sdk", "environment", "fault", "outcome"}, "SCENE_FIELDS")
    c = s["contracts"]
    validate_contracts(c)
    x, effect = c["experiment"], c["effect"]
    require(x["candidate_id"] == candidate and x["runtime_source_sha256"] == source_sha
            and s["contracts_sha256"] == digest(c), "SCENE_IDENTITY")
    suppressed = candidate == CONFIG_CANDIDATES[2]
    require(s["fault"] == {"planned": candidate != "normal", "triggered": suppressed,
        "observed": suppressed, "channel": "EXPLICIT_TOOL_DELIVERY_ERROR" if suppressed else "NONE"}, "FAULT_CLAIM")
    require(s["outcome"] == {"agent_failure": "NOT_EVALUATED_FIXTURE", "platform_error":
        "EXPECTED_DELIVERY_ERROR" if suppressed else "NONE", "business_violation": False,
        "contract_outcome": "SATISFIED", "reconcile": "READ_ONLY_CONFIRMED" if suppressed else "NOT_REQUIRED",
        "target_ack": "UNKNOWN_OUTCOME" if suppressed else "RECEIVED"}, "OUTCOME_CLAIM")
    observations = s["http"]
    kinds = ["initial_current", "initial_history", "inspect_config", "create_config_v1", "update_config_v2"]
    kinds += (["reconcile_current", "reconcile_history", "final_list"] if suppressed else
              ["final_current", "final_history", "final_list"])
    require(type(observations) is list and len(observations) == len(kinds), "HTTP_COUNT")
    for i, (o, kind) in enumerate(zip(observations, kinds), 1):
        require(type(o) is dict and set(o) == {"seq", "kind", "method", "path", "request", "status", "content_type",
            "response", "response_body_sha256", "elapsed_ms", "transport_error"}, "HTTP_FIELDS")
        method, path, body = _http_contract(effect, kind)
        require(o.get("seq") == i and o.get("kind") == kind and o.get("method") == method
                and o.get("path") == path and o.get("request") == body, "HTTP_PATH_NAMESPACE_OR_REPLAY")
        absent = kind in ("initial_current", "inspect_config")
        history = kind.endswith("history") or kind == "final_list"
        ok, data = _api_response(o, 404 if absent else 200, 4041 if absent else 0,
                                 "none" if absent else "list" if history else "item")
        require(ok and o["response_body_sha256"] == digest(o["response"]), "HTTP_RESPONSE")
        if kind == "initial_history":
            require(data == [], "INITIAL_HISTORY")
        elif history:
            require((len(data) == 1 and _valid_item(data[0], effect, 2, "rpf53-v2"))
                    if kind == "final_list" else _history(data, effect), "AUTHORITY_NAMESPACE_HISTORY")
        elif not absent:
            v = 1 if kind == "create_config_v1" else 2
            require(_valid_item(data, effect, v, "rpf53-v1" if v == 1 else "rpf53-v2"), "EFFECT_ITEM")
    events = s["events"]
    require(type(events) is list and events and events[0]["kind"] == "PRE_REGISTERED", "PRE_REGISTRATION")
    require([e["seq"] for e in events] == list(range(1, len(events) + 1))
            and all(e["run_id"] == x["run_id"] and type(e["monotonic_ns"]) is int for e in events)
            and [e["monotonic_ns"] for e in events] == sorted(e["monotonic_ns"] for e in events), "EVENT_ORDER_RUN")
    require(events[0]["candidate"] == candidate, "EVENT_CANDIDATE")
    fields = {"PRE_REGISTERED": {"candidate"}, "HTTP_RESERVED": {"http_seq", "method", "operation"},
        "HTTP_COMPLETED": {"http_seq", "status", "code"}, "TOOL_RESERVED": {"call_id", "name"},
        "TOOL_RESULT_READY": {"call_id", "name"}, "SUCCESS_RELEASED": {"call_id", "name"},
        "SUCCESS_WITHHELD": {"call_id", "name", "http_seq", "channel"},
        "FAULT_INHIBITED": {"reason"}, "SDK_ERROR_OBSERVED": {"returncode", "status", "error_type"}}
    require(all(e["kind"] in fields and set(e) == fields[e["kind"]] | {
        "seq", "run_id", "monotonic_ns", "kind"} for e in events), "EVENT_FIELDS")
    for kind, count in {"PRE_REGISTERED": 1, "TOOL_RESERVED": 3, "TOOL_RESULT_READY": 3,
            "SUCCESS_RELEASED": 2 if suppressed else 3, "SDK_ERROR_OBSERVED": int(suppressed)}.items():
        require(sum(e["kind"] == kind for e in events) == count, "EVENT_CARDINALITY")
    for o in observations:
        reserved = [e for e in events if e["kind"] == "HTTP_RESERVED" and e["http_seq"] == o["seq"]]
        completed = [e for e in events if e["kind"] == "HTTP_COMPLETED" and e["http_seq"] == o["seq"]]
        require(len(reserved) == len(completed) == 1 and reserved[0]["seq"] < completed[0]["seq"]
            and reserved[0]["method"] == o["method"] and reserved[0]["operation"] == o["kind"]
            and completed[0]["status"] == o["status"] and completed[0]["code"] == o["response"]["code"], "HTTP_EVENT_BINDING")
    trace = s["tool_trace"]
    names = ["inspect_config", "create_config_v1", "update_config_v2"]
    require([t["name"] for t in trace] == names and len({t["call_id"] for t in trace}) == 3, "TOOL_LINEAGE")
    for i, t in enumerate(trace):
        args = ({}, {"value": "rpf53-v1"}, {"expected_version": 1, "value": "rpf53-v2"})[i]
        result = {"state": "ABSENT"} if i == 0 else {"status": "COMMITTED", "version": i, "value": "rpf53-v" + str(i)}
        require(t["sequence"] == i + 1 and t["http_observation_seq"] == i + 3
            and t["arguments"] == args and t["arguments_sha256"] == digest(args)
            and t["result"] == result and t["result_sha256"] == digest(result)
            and t["returned_in_request"] == (None if suppressed and i == 2 else i + 2), "TOOL_RESULT_BINDING")
        for kind in ("TOOL_RESERVED", "TOOL_RESULT_READY", "SUCCESS_WITHHELD" if suppressed and i == 2 else "SUCCESS_RELEASED"):
            matches = [e for e in events if e["kind"] == kind and e.get("call_id") == t["call_id"]]
            require(len(matches) == 1 and matches[0]["name"] == t["name"], "TOOL_EVENT_BINDING")
        order = [next(e["seq"] for e in events if e["kind"] == kind and e.get("call_id") == t["call_id"])
                 for kind in ("TOOL_RESERVED", "TOOL_RESULT_READY", "SUCCESS_WITHHELD" if suppressed and i == 2 else "SUCCESS_RELEASED")]
        reserve = next(e["seq"] for e in events if e["kind"] == "HTTP_RESERVED" and e["http_seq"] == i + 3)
        complete = next(e["seq"] for e in events if e["kind"] == "HTTP_COMPLETED" and e["http_seq"] == i + 3)
        require(order[0] < reserve < complete < order[1] < order[2], "TOOL_HTTP_ORDER")
    activations = [e for e in events if e["kind"] == "SUCCESS_WITHHELD"]
    inhibits = [e for e in events if e["kind"] == "FAULT_INHIBITED"]
    require(len(activations) == int(suppressed) and len(inhibits) == int(candidate == CONFIG_CANDIDATES[1]), "ACTIVATION_COUNT")
    if suppressed:
        a = activations[0]
        require(a["http_seq"] == 5 and a["channel"] == "EXPLICIT_TOOL_DELIVERY_ERROR", "ACTUATOR_SOURCE")
        require(not any(e["kind"] == "SUCCESS_RELEASED" and e.get("call_id") == trace[2]["call_id"] for e in events), "FALSE_SUCCESS_ACK")
        observed = [e for e in events if e["kind"] == "SDK_ERROR_OBSERVED"]
        require(len(observed) == 1 and observed[0]["seq"] > a["seq"] and observed[0]["seq"] <
                next(e["seq"] for e in events if e["kind"] == "HTTP_RESERVED" and e["http_seq"] == 6), "SDK_OBSERVATION_ORDER")
        require(observed[0]["returncode"] == 1 and observed[0]["status"] == "SDK_ERROR"
            and observed[0]["error_type"] == "RuntimeError", "SDK_OBSERVATION_FIELDS")
    elif inhibits:
        ready = next(e["seq"] for e in events if e["kind"] == "TOOL_RESULT_READY" and e["call_id"] == trace[2]["call_id"])
        released = next(e["seq"] for e in events if e["kind"] == "SUCCESS_RELEASED" and e["call_id"] == trace[2]["call_id"])
        require(inhibits[0]["reason"] == "PRE_REGISTERED_GATE_DISABLED" and ready < inhibits[0]["seq"] < released, "INHIBITION_REASON")
    completions = s["completions"]
    require(len(completions) == (3 if suppressed else 4), "COMPLETIONS")
    for i, completion in enumerate(completions):
        require(set(completion) == {"response_id", "model", "tool_calls", "usage", "request_sha256", "tool_returns"}
            and completion["model"] == "rpf53-fixture-only"
            and completion["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "COMPLETION_SOURCE")
        require(completion["tool_returns"] == [{"call_id": t["call_id"], "result_sha256": t["result_sha256"]}
                for t in trace[:i]], "SDK_RETURN_INJECTION")
        calls = completion["tool_calls"]
        require(len(calls) == (1 if i < 3 else 0), "SDK_INTENT_COUNT")
        if calls:
            t = trace[i]
            require(calls[0] == {"call_id": t["call_id"], "name": t["name"], "arguments_sha256": t["arguments_sha256"]}
                    and completion["response_id"] == t["provider_response_id"], "SDK_INTENT_BINDING")
    sdk = s["sdk"]
    require(set(sdk) == {"popen_pid", "ready", "report", "returncode", "stderr_bytes", "identity"}, "SDK_FIELDS")
    require(type(sdk["popen_pid"]) is int and sdk["popen_pid"] > 0 and sdk["ready"]["pid"] == sdk["popen_pid"]
        and sdk["ready"]["version"] == "2.57.0" and sdk["ready"]["openai_version"] == "3.35.1"
        and sdk["ready"]["sdk_source_sha256"] == SDK_CORE_SHA256 and sdk["stderr_bytes"] == 0, "SDK_PID_SOURCE")
    identity = sdk["identity"]
    pinned = pinned_sdk_fields()
    require(all(identity.get(k) == value for k, value in pinned.items() if not k.startswith(("pydantic_", "openai_record_")))
        and all(identity[name].get(field) == pinned[name + "_" + field]
            for name in ("pydantic", "openai") for field in ("record_sha256", "record_entries", "record_mismatches")), "PINNED_SDK_IDENTITY")
    require(identity["python_version"] == "3.12.13" and identity["pydantic"]["record_mismatches"] == 0
        and identity["pydantic"]["record_entries"] == 444 and identity["openai"]["record_entries"] == 2000
        and identity["openai"]["record_mismatches"] == 0, "SDK_RECORD")
    for name in ("python_executable_sha256", "sdk_site_root_binding_sha256", "python_runtime_mapping_sha256"):
        require(sdk["ready"][name] == identity[name], "SDK_IDENTITY_BINDING")
    require(sdk["ready"]["openai_source_sha256"] == identity["openai_core_sha256"], "OPENAI_SOURCE")
    report = sdk["report"]
    if suppressed:
        require(report["status"] == "SDK_ERROR" and report["stage"] == "sdk_run"
            and report["error_type"] == "RuntimeError" and report["guard_code"] is None
            and report["guard_denials"] == [] and sdk["returncode"] == 1, "SDK_SUPPRESSION_OBSERVED")
    else:
        require(report["status"] == "COMPLETED" and report["pid"] == sdk["popen_pid"]
            and report["tool_callbacks"] == report["tool_calls"] == 3 and report["requests"] == 4
            and report["guard_denials"] == [] and report["provider_key_present"] is False
            and report["business_key_present"] is False and sdk["returncode"] == 0, "SDK_CALLBACK_REPORT")
    env = s["environment"]
    require(set(env) == {"source_level", "authority", "java_pid", "listener_owned", "jar_sha256",
        "jar_bytes", "jar_command_verified", "health", "cleanup"}, "ENV_FIELDS")
    require(env["source_level"] == "REAL_JAVA_H2_LOCAL_SIMULATION" and env["authority"] == "SAME_SERVICE_READ_ONLY_HTTP"
        and type(env["java_pid"]) is int and env["java_pid"] > 0 and env["listener_owned"] is True
        and env["jar_command_verified"] is True and env["jar_sha256"] == SOURCE_JAR_SHA256
        and env["jar_bytes"] == 66981576, "AUTHORITY_JAVA_SOURCE")
    require(1 <= len(env["health"]) <= 3 and env["health"][-1]["status"] == 200
        and env["health"][-1]["body"] == {"status": "UP"}, "HEALTH")
    require(env["cleanup"] == {"java_exited": True, "java_port_closed": True,
        "sdk_exited": True, "host_port_closed": True, "host_thread_stopped": True,
        "local_key_released": True}, "CLEANUP")

def cold_fixture(contract,sdk):
    guard=TaskGuard(WORK/"task-intents")
    reservation=guard.reserve("COLD",digest(c.sources()),offline_gate_sha256=digest(c.sources()),contracts_sha256=digest(contract))
    ordinal=next(r["ordinal"] for r in guard.rows if r["reservation_id"]==reservation)
    folder=scoped(WORK/"preflight"/f"cold-attempt-{ordinal:02}");folder.mkdir(exist_ok=False)
    once(folder/"started.json",{"source_files":c.sources(),"contracts":contract,"contracts_sha256":digest(contract),"attempt":ordinal,
        "reservation_id":reservation,"runner_pid":os.getpid(),"started_monotonic_ns":time.monotonic_ns(),"provider":0,"java":0})
    try:
        journal=MemoryJournal(None,contract["experiment"]["run_id"])
        host=Host(contract,ProviderLedger.fixture_only(journal.run_id),ConfigLiveMemoryBackend(),journal)
        result=run_sdk(host,contract,sdk,folder,fixture=True)
        cleanup=strict_json((folder/"sdk-cleanup.json").read_bytes())["cleanup"]
        capture={"schema":"rpf60-cold-capture-v1","source_kind":"REAL_SDK_COLD_FIXTURE","attempt":ordinal,"source_files":c.sources(),
            "contract":contract,"sdk":result,"events":journal.events,"tool_trace":host.tool_trace,"completions":host.provider_responses,"cleanup":cleanup}
        once(folder/"capture.json",capture) # No semantic postcondition before persistence.
        verdict=validate_cold_capture(capture)
        out={"status":"PASS","source_files":c.sources(),"reservation_id":reservation,"capture":capture,"verdict":verdict,"provider":0,"java":0}
        once(folder/"result.json",out);guard.result(reservation,"PASS",capture_sha256=digest(capture));return out
    except Exception as exc:
        detail={"status":"FAIL","error":getattr(exc,"code",type(exc).__name__),"source_files":c.sources(),"attempt":ordinal,
            "capture_available":(folder/"capture.json").exists(),"sdk_received_available":(folder/"sdk-received.json").exists()}
        once(folder/"failure.json",detail);guard.result(reservation,"FAIL",failure_sha256=digest(detail));raise

def validate_cold_capture(value):
    require(set(value)=={"schema","source_kind","attempt","source_files","contract","sdk","events","tool_trace","completions","cleanup"}
        and value["schema"]=="rpf60-cold-capture-v1" and value["source_kind"] in ("REAL_SDK_COLD_FIXTURE","SYNTHETIC_TEST_ONLY")
        and value["source_files"]==c.sources() and value["attempt"] in (1,2),"COLD_SOURCE_OR_FIELDS")
    validate_trial(value["contract"]);require(value["contract"]["experiment"]["source_sha256"]==digest(c.sources()),"COLD_CONTRACT_SOURCE")
    result=value["sdk"];report=result["report"];ready=result["ready"];pin=pinned_sdk_fields()
    require(type(result["popen_pid"]) is int and result["popen_pid"]>0 and ready["pid"]==report["pid"]==result["popen_pid"]
        and report["status"]=="COMPLETED" and result["returncode"]==0 and result["stderr_bytes"]==0
        and report["tool_calls"]==report["tool_callbacks"]==3 and report["requests"]==4 and report["guard_denials"]==[]
        and report["provider_key_present"] is False and report["business_key_present"] is False,"COLD_SDK_REPORT")
    require(ready["version"]=="2.57.0" and ready["openai_version"]=="3.35.1" and ready["sdk_source_sha256"]==SDK_CORE_SHA256
        and ready["openai_source_sha256"]==pin["openai_core_sha256"]
        and all(ready[k]==pin[k] for k in ("python_executable_sha256","sdk_site_root_binding_sha256","python_runtime_mapping_sha256")),"COLD_SDK_IDENTITY")
    trace=value["tool_trace"];completions=value["completions"]
    require([t["name"] for t in trace]==list(c.TOOLS) and len({t["call_id"] for t in trace})==3
        and [t["returned_in_request"] for t in trace]==[2,3,4] and len(completions)==4,"COLD_TOOL_LINEAGE")
    for i,comp in enumerate(completions):
        require(comp["model"]=="rpf53-fixture-only" and comp["usage"]=={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
            and comp["tool_returns"]==[{"call_id":t["call_id"],"result_sha256":t["result_sha256"]} for t in trace[:i]]
            and comp["tool_calls"]==([{k:trace[i][k] for k in ("call_id","name","arguments_sha256")}] if i<3 else []),"COLD_COMPLETION_LINEAGE")
        if i<3:
            call=trace[i];args=({}, {"value":"rpf53-v1"},{"expected_version":1,"value":"rpf53-v2"})[i]
            tool_result={"state":"ABSENT"} if i==0 else {"status":"COMMITTED","version":i,"value":"rpf53-v"+str(i)}
            require(call["sequence"]==i+1 and call["arguments"]==args and call["arguments_sha256"]==digest(args)
                and call["result"]==tool_result and call["result_sha256"]==digest(tool_result) and call["provider_response_id"]==comp["response_id"],"COLD_TOOL_ARGS_RESULTS")
    events=value["events"]
    require(events[0]["kind"]=="PRE_REGISTERED" and events[0]["candidate"]=="planned-but-inhibited"
        and sum(e["kind"]=="FAULT_INHIBITED" for e in events)==1 and not any(e["kind"] in ("SUCCESS_WITHHELD","SDK_ERROR_OBSERVED") for e in events)
        and sum(e["kind"]=="SUCCESS_RELEASED" for e in events)==3,"COLD_INHIBITED_GATE")
    require([e["seq"] for e in events]==list(range(1,len(events)+1))
        and all(e["run_id"]==value["contract"]["experiment"]["run_id"] for e in events)
        and all(a["monotonic_ns"]<b["monotonic_ns"] for a,b in zip(events,events[1:])),"COLD_EVENT_ORDER")
    inhibited=next(e for e in events if e["kind"]=="FAULT_INHIBITED")
    ready_event=next(e for e in events if e["kind"]=="TOOL_RESULT_READY" and e["call_id"]==trace[2]["call_id"])
    released=next(e for e in events if e["kind"]=="SUCCESS_RELEASED" and e["call_id"]==trace[2]["call_id"])
    require(ready_event["seq"]<inhibited["seq"]<released["seq"] and inhibited["reason"]=="PRE_REGISTERED_GATE_DISABLED","COLD_GATE_ORDER")
    require(value["cleanup"]=={"sdk_exited":True,"host_thread_stopped":True,"host_port_closed":True},"COLD_CLEANUP")
    return {"status":"PASS","source_kind":value["source_kind"],"popen_pid":result["popen_pid"],"capture_sha256":digest(value)}

def config_execute(contract,total):
    validate_trial(contract);require(contract["experiment"]["domain"]=="config-java-http","CONFIG_DOMAIN")
    base=strict_json((WORK/"preflight"/("identity-"+digest(c.sources())+".json")).read_bytes());require(base["sources"]==c.sources(),"SOURCE_DRIFT")
    sdk_identity=base["sdk"];h55.resolve_direct_python(sdk_identity)
    run=contract["experiment"]["run_id"];folder=scoped(WORK/"sandboxes"/run);folder.mkdir(exist_ok=False)
    once(folder/"started.json",{"contracts":contract,"sources":c.sources()})
    journal=Journal(run,total);client=Http(contract,secrets.token_urlsafe(32),journal,total,time.monotonic()+900)
    host=Host(contract,ProviderLedger.fixture_only(run),ConfigLiveBusiness(contract,client),journal)
    temp=folder/"java-tmp";temp.mkdir();port=client.port
    args=[str(old.JAVA),f"-Djava.io.tmpdir={temp}","-jar",str(JAR),"--spring.profiles.active=local","--server.address=127.0.0.1",f"--server.port={port}",
        "--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}","--security.api-keys[0].app="+contract["effect"]["app"],"--security.api-keys[0].env="+contract["effect"]["env"]]
    environment={"source_level":"REAL_JAVA_H2_LOCAL_SIMULATION","authority":"SAME_SERVICE_READ_ONLY_HTTP","java_pid":None,"jar_sha256":old._sha_file(JAR),
        "jar_bytes":JAR.stat().st_size,"listener_owned":False,"jar_command_verified":False,"health":[],"cleanup":{}}
    proc=log=sdk=None
    try:
        require(environment["jar_sha256"]==c.SOURCE_JAR_SHA256 and old._port_closed(port),"JAR_PORT_IDENTITY")
        reservation=total.reserve("config-java-http","java",{"jvm":1})
        proc=subprocess.Popen(args,cwd=folder,env=old._java_env(temp,client._api_key),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
        total.settle(reservation,{"pid":proc.pid});environment["java_pid"]=proc.pid
        log=old._RedactedJavaLog(proc,client._api_key.encode("ascii"))
        argv=old._split_windows_command_line(old._actual_process_command_line(proc.pid))
        environment["jar_command_verified"]=old._argv_jar_path_matches(argv,JAR,WORK)
        require(environment["jar_command_verified"],"JAVA_ARGV")
        # Reserve all three health slots before any GET. Unused slots stay spent.
        health_slots=[total.reserve("config-java-http",f"health:{i}",{"health":1}) for i in range(3)]
        health=[];ready=old._wait_for_java(proc,port,log,time.monotonic()+180,health)
        for i,res in enumerate(health_slots):total.settle(res,{"health_sha256":digest(health[i])} if i<len(health) else {"status":"UNUSED_RESERVED_NO_IO"})
        once(folder/"health-raw.json",health);environment["health"]=h55.health_projection(health)
        require(ready,"JAVA_READINESS")
        environment["listener_owned"]=old._listener_owned(proc.pid,port)
        require(environment["listener_owned"] and not old._external_connections(proc.pid) and client.initial_state_valid(),"JAVA_INITIAL_AUTHORITY")
        reservation=total.reserve("config-java-http","sdk",{"sdk":1})
        sdk=run_sdk(host,contract,sdk_identity,folder,fixture=True)
        total.settle(reservation,{"pid":sdk["popen_pid"],"report_sha256":digest(sdk["report"])})
        require(sdk["report"]["status"]=="COMPLETED","SDK_NOT_COMPLETED")
        client.final_readback();require(not old._external_connections(proc.pid),"JAVA_EXTERNAL_NETWORK")
    finally:
        thread=host._thread;host.close()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if log is not None:log.close(folder/"java-redacted.log")
        client._api_key=None
        environment["cleanup"]={"java_exited":proc is not None and proc.poll() is not None,"java_port_closed":old._port_closed(port),"sdk_exited":sdk is not None,
            "host_port_closed":old._port_closed(contract["execution"]["agent_host"]["port"]),"host_thread_stopped":thread is None or not thread.is_alive(),"local_key_released":True}
        once(folder/"raw.json",{"contracts":contract,"http":client.observations,"sdk":sdk,"environment":environment,"events":journal.events})
    sdk["identity"]=sdk_identity
    scene={"contracts":contract,"contracts_sha256":digest(contract),"http":client.observations,"events":journal.events,"tool_trace":host.tool_trace,
        "completions":host.provider_responses,"sdk":sdk,"environment":environment,"fault":{"planned":True,"triggered":False,"observed":False,"channel":"NONE"},
        "outcome":{"agent_failure":"NOT_EVALUATED_FIXTURE","platform_error":"NONE","business_violation":False,"contract_outcome":"SATISFIED","reconcile":"NOT_REQUIRED","target_ack":"RECEIVED"}}
    return {"schema":"rpf60-config-trial-v1","domain":"config-java-http","source_kind":"REAL_LOCAL_SDK_FIXTURE_JAVA_HTTP","executor_pid":os.getpid(),"scene":scene}

def config_verify(contract,evidence):
    validate_trial(contract)
    require(set(evidence)=={"schema","domain","source_kind","executor_pid","scene"} and evidence["schema"]=="rpf60-config-trial-v1"
        and evidence["domain"]=="config-java-http" and evidence["source_kind"] in ("REAL_LOCAL_SDK_FIXTURE_JAVA_HTTP","SYNTHETIC_TEST_ONLY"),"CONFIG_EVIDENCE_FIELDS")
    scene=evidence["scene"];require(scene["contracts"]==contract,"CONFIG_CONTRACT_BINDING")
    if evidence["source_kind"]!="SYNTHETIC_TEST_ONLY":
        require(type(evidence["executor_pid"]) is int and evidence["executor_pid"]>0
            and all(not r["response_id"].startswith("synthetic") for r in scene["completions"]),"CONFIG_REAL_ORIGIN")
    _verify_scene(scene,"planned-but-inhibited",contract["experiment"]["source_sha256"])
    return {"domain":"config-java-http","outcome":"SATISFIED","authority":"SAME_SERVICE_READ_ONLY_HTTP","history":"V2_HISTORY_2_1"}

from types import SimpleNamespace
ORDER_PORT=SimpleNamespace(execute=order_execute,verify=order_verify,READER_ID=READER_ID,ENV_REVISION=ENV_REVISION)
CONFIG_PORT=SimpleNamespace(execute=config_execute,verify=config_verify)
