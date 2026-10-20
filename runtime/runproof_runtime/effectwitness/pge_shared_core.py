"""One physical WAL and one execution pipeline, used by both static ports."""
import copy,os,time,hashlib
from .pge_shared_contracts import WORK,DOMAINS,LIMITS,canonical,digest,strict_json,require,scoped,validate_plan,sources

def validate_state(s,p):
    require(set(s)=={"session_id","plan_sha256","started_ns","reservations","events"} and s["session_id"]==p["session_id"]
        and s["plan_sha256"]==digest(p) and type(s["started_ns"]) is int,"LEDGER_IDENTITY")
    totals={k:0 for k in LIMITS};keys=set()
    for i,r in enumerate(s["reservations"],1):
        require(set(r)=={"id","domain","label","units","status","detail"} and r["id"]==i and r["domain"] in DOMAINS
            and type(r["label"]) is str and r["status"] in ("RESERVED","DONE","UNKNOWN"),"RESERVATION_FIELDS")
        key=(r["domain"],r["label"]);require(key not in keys,"DOUBLE_WRITE_OR_RESOURCE_REPLAY");keys.add(key)
        require(type(r["units"]) is dict and bool(r["units"]) and set(r["units"])<=set(LIMITS)
            and all(type(v) is int and v==1 for v in r["units"].values()),"RESOURCE_ALLOWLIST")
        for k,v in r["units"].items():totals[k]+=v
    require(all(totals[k]<=v for k,v in LIMITS.items()),"SHARED_PHYSICAL_BUDGET")
    events=s["events"]
    require([e["seq"] for e in events]==list(range(1,len(events)+1)) and all(set(e)=={"seq","monotonic_ns","kind","data"}
        and type(e["monotonic_ns"]) is int and e["monotonic_ns"]>=s["started_ns"] for e in events)
        and all(a["monotonic_ns"]<b["monotonic_ns"] for a,b in zip(events,events[1:])),"WAL_EVENT_ORDER")
    return totals

class Ledger:
    def __init__(self,path,plan,*,create=False):
        validate_plan(plan);require(plan["source_files"]==sources(),"SOURCE_DRIFT")
        self.path,self.plan=scoped(path),plan
        if create:
            self.path.mkdir(exist_ok=False)
            self._write({"session_id":plan["session_id"],"plan_sha256":digest(plan),"started_ns":time.monotonic_ns(),"reservations":[],"events":[]},None,0)
        self.read()
    def _write(self,s,prev,seq):
        validate_state(s,self.plan);v={"seq":seq,"previous_sha256":prev,"state":s,"state_sha256":digest(s)}
        with scoped(self.path/f"snapshot-{seq:04}.json").open("xb") as f:f.write(canonical(v));f.flush();os.fsync(f.fileno())
    def read(self):
        scoped(self.path)
        files=sorted(self.path.glob("snapshot-*.json"));require(bool(files),"LEDGER_MISSING")
        prev=old=None;chain=[]
        for i,path in enumerate(files):
            v=strict_json(scoped(path).read_bytes());s=v["state"]
            require(set(v)=={"seq","previous_sha256","state","state_sha256"} and v["seq"]==i and path.name==f"snapshot-{i:04}.json"
                and v["previous_sha256"]==prev and v["state_sha256"]==digest(s),"TORN_OR_HASH_CHAIN")
            validate_state(s,self.plan)
            if old is not None:
                require(s["started_ns"]==old["started_ns"] and s["events"][:len(old["events"])]==old["events"]
                    and len(s["reservations"])>=len(old["reservations"]),"WAL_HISTORY_REMOVED")
                for a,b in zip(old["reservations"],s["reservations"]):
                    require(all(a[k]==b[k] for k in ("id","domain","label","units"))
                        and (a==b or (a["status"]=="RESERVED" and b["status"] in ("DONE","UNKNOWN"))),"WAL_REFUND_OR_REWRITE")
            prev,old=digest(v),s;chain.append(v)
        self.previous,self.seq,self.state,self.chain=prev,len(files),s,chain
        return copy.deepcopy(s)
    @staticmethod
    def _event(s,kind,data):
        e={"seq":len(s["events"])+1,"monotonic_ns":time.monotonic_ns(),"kind":kind,"data":data};s["events"].append(e);return e
    def mutate(self,fn):
        lock=scoped(self.path/"mutation.lock")
        try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:require(False,"LOCK_COLLISION_OR_UNCLEAN_RESTART")
        try:
            s=self.read();require(time.monotonic_ns()-s["started_ns"]<1200*1_000_000_000,"TASK_DEADLINE")
            result=fn(s);self._write(s,self.previous,self.seq);self.read();return result
        finally:os.close(fd);lock.unlink()
    def event(self,kind,**data):return self.mutate(lambda s:self._event(s,kind,data))
    def reserve(self,domain,label,units):
        def op(s):
            require(domain in DOMAINS and not any(r["status"]=="UNKNOWN" or (r["status"]=="RESERVED" and
                ("post" in r["units"] or "sqlite_mutation" in r["units"])) for r in s["reservations"]),"UNKNOWN_WRITE_STOP")
            if "trial" in units:
                prior=[r for r in s["reservations"] if "trial" in r["units"]]
                require(all(r["status"]=="DONE" for r in prior) and domain==DOMAINS[len(prior)] and
                    units=={"trial":1,"order_trial" if domain==DOMAINS[0] else "config_trial":1},"DOMAIN_SEQUENCE_OR_TRIAL_REPLAY")
            else:
                active=[r for r in s["reservations"] if "trial" in r["units"] and r["status"]=="RESERVED"]
                require(len(active)==1 and active[0]["domain"]==domain,"NO_ACTIVE_DOMAIN")
                allowed={"sqlite_mutation"} if domain==DOMAINS[0] else {"jvm","sdk","business_http","post","health"}
                require(set(units)<=allowed,"DOMAIN_RESOURCE_MISMATCH")
            r={"id":len(s["reservations"])+1,"domain":domain,"label":label,"units":units,"status":"RESERVED","detail":None}
            s["reservations"].append(r);validate_state(s,self.plan)
            self._event(s,"RESOURCE_RESERVED",{"reservation_id":r["id"],"domain":domain,"label":label,"units":units})
            return r["id"]
        return self.mutate(op)
    def settle(self,number,detail,*,unknown=False):
        def op(s):
            r=s["reservations"][number-1];require(r["status"]=="RESERVED","SETTLEMENT_REPLAY")
            r.update(status="UNKNOWN" if unknown else "DONE",detail=detail)
            self._event(s,"RESOURCE_SETTLED",{"reservation_id":number,"status":r["status"],"detail_sha256":digest(detail)})
        self.mutate(op)

def domain_port(domain):
    # No dynamic import, executable or endpoint selected by input data.
    from . import pge_order_port,pge_config_port
    require(domain in DOMAINS,"DOMAIN_PORT_NOT_ALLOWLISTED")
    return {DOMAINS[0]:pge_order_port,DOMAINS[1]:pge_config_port}[domain]

def dispatch_identity(function):
    return {"entry_code_sha256":hashlib.sha256(SharedSession.execute_trial.__code__.co_code).hexdigest(),
        "port_callable":function.__module__+"."+function.__qualname__,
        "port_code_sha256":hashlib.sha256(function.__code__.co_code).hexdigest()}

class SharedSession:
    def __init__(self,ledger):self.ledger=ledger;self.rows=[]
    def execute_trial(self,contract):
        from .pge_shared_feedback import visible,project
        from .pge_shared_verify import domain_verdict
        require(sources()==self.ledger.plan["source_files"],"SOURCE_DRIFT_BEFORE_DOMAIN")
        index=len(self.rows);require(contract==self.ledger.plan["trials"][index],"PRE_REGISTERED_TRIAL_ONLY")
        domain=contract["experiment"]["domain"];prior=[r["feedback"] for r in self.rows]
        inp=visible(prior);self.ledger.event("INPUT_FROZEN",domain=domain,input_sha256=digest(inp))
        reservation=self.ledger.reserve(domain,"trial",{"trial":1,"order_trial" if domain==DOMAINS[0] else "config_trial":1})
        function=domain_port(domain).execute;runtime=dispatch_identity(function)
        self.ledger.event("SHARED_PORT_DISPATCH",domain=domain,entry="SharedSession.execute_trial",contract_sha256=digest(contract),runtime_identity=runtime)
        self.ledger.event("DOMAIN_CALL_ENTERED",domain=domain,runtime_identity=runtime)
        evidence=function(contract,self.ledger)
        self.ledger.event("DOMAIN_CALL_RETURNED",domain=domain,runtime_identity=runtime,evidence_sha256=digest(evidence))
        self.ledger.event("DOMAIN_RETURNED",domain=domain,evidence_sha256=digest(evidence))
        verdict=domain_verdict(contract,evidence)
        self.ledger.event("DOMAIN_VERIFIED",domain=domain,verdict_sha256=digest(verdict))
        fb=project(contract,evidence,prior)
        self.ledger.event("FEEDBACK_FROZEN",domain=domain,feedback_sha256=digest(fb))
        self.ledger.settle(reservation,{"evidence_sha256":digest(evidence),"feedback_sha256":digest(fb)})
        row={"contract":contract,"input":inp,"evidence":evidence,"feedback":fb,"trial_reservation":reservation}
        self.rows.append(row);return row

class TaskGuard:
    """Separate append-only task intents, never reset by a source revision.

    Metadata <=4, cold <=2 (only after diagnosed FAIL and changed source),
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
        require(counts["METADATA"]<=4 and counts["COLD"]<=2 and counts["SESSION"]<=1,"TASK_ATTEMPT_BUDGET")
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
            same=[r for r in rows if r["kind"]==kind];limit={"METADATA":4,"COLD":2,"SESSION":1}[kind]
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
    require(counts["METADATA"]<=4 and counts["COLD"]<=2 and counts["SESSION"]<=1,"TASK_EXTERNAL_BUDGET")
    return list(rows.values())
