"""RPF-59: one durable account for real Explorer and either static domain.

Versioned WAL lifecycle adapted from RPF-58 v2; no historical globals changed.
"""
import copy,hashlib,os,time
from .pge_select_contracts import canonical,digest,strict_json,require,scoped,validate_plan,sources,DOMAINS,LIMITS,MODEL

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
    from . import pge_select_order_port,pge_select_config_port
    require(domain in DOMAINS,'STATIC_DOMAIN_ALLOWLIST')
    return {DOMAINS[0]:pge_select_order_port,DOMAINS[1]:pge_select_config_port}[domain]

def dispatch_identity(fn):
    return {'entry_code_sha256':hashlib.sha256(SharedSession.execute_trial.__code__.co_code).hexdigest(),
        'port_callable':fn.__module__+'.'+fn.__qualname__,'port_code_sha256':hashlib.sha256(fn.__code__.co_code).hexdigest()}

class SharedSession:
    def __init__(self,ledger):self.ledger,self.rows=ledger,[]
    def execute_trial(self,selection,body,observation,attempt):
        from .pge_select_contracts import domain_for
        from .pge_select_explorer import parse_selection,body_for,messages_for
        from .pge_select_feedback import visible,project
        from .pge_select_verify import domain_verdict,validate_observation
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
