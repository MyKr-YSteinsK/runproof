"""One physical WAL and one execution pipeline, used by both static ports."""
import copy,os,time
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
        self.ledger.event("SHARED_PORT_DISPATCH",domain=domain,entry="SharedSession.execute_trial",contract_sha256=digest(contract))
        evidence=domain_port(domain).execute(contract,self.ledger)
        self.ledger.event("DOMAIN_RETURNED",domain=domain,evidence_sha256=digest(evidence))
        verdict=domain_verdict(contract,evidence)
        self.ledger.event("DOMAIN_VERIFIED",domain=domain,verdict_sha256=digest(verdict))
        fb=project(contract,evidence,prior)
        self.ledger.event("FEEDBACK_FROZEN",domain=domain,feedback_sha256=digest(fb))
        self.ledger.settle(reservation,{"evidence_sha256":digest(evidence),"feedback_sha256":digest(fb)})
        row={"contract":contract,"input":inp,"evidence":evidence,"feedback":fb,"trial_reservation":reservation}
        self.rows.append(row);return row
