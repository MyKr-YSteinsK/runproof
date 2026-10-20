"""Fresh RPF-59 order sandbox; unchanged refund transaction and RO Reader."""
from contextlib import closing
from pathlib import Path
import hashlib,os,secrets,sqlite3,time
from .pge_select_contracts import WORK,DOMAINS,canonical,digest,require,scoped,validate_trial
from .orders import OrderSandbox,OrderAdapter,AuthorityReader
from .contracts import ENV_REVISION,READER_ID
from .effect_oracle import evaluate_order_effect

class Bridge:
    def __init__(self,c):validate_trial(c);require(c["experiment"]["domain"]==DOMAINS[0],"ORDER_DOMAIN");self.c=c
    @property
    def execution(self):return self.c["execution"]
    @property
    def effect(self):return self.c["effect"]
    @property
    def experiment(self):return self.c["experiment"]
    def validate(self):validate_trial(self.c)

class Sandbox(OrderSandbox):
    def __init__(self,c):
        self.contracts=Bridge(c);self.owner="rpf-59";self.storage_task="rpf-59"
        self.directory=scoped(WORK/"sandboxes"/c["experiment"]["run_id"])
        self.path=scoped(self.directory/"orders.sqlite3");self.created=False;self.generation=0

class Reader(AuthorityReader):
    def __init__(self,sandbox):
        self.path=scoped(sandbox.path);self.contracts=sandbox.contracts;self._seal=secrets.token_bytes(32);self.available=True

def execute(c,ledger):
    validate_trial(c);domain=c["experiment"]["domain"]
    sandbox=Sandbox(c);timeline=[]
    def mark(kind,**data):
        event=ledger.event("ORDER_PORT_EVENT",port_kind=kind,**data);timeline.append({"kind":kind,"monotonic_ns":event["monotonic_ns"],"data":data})
    mark("PORT_ENTERED",run_id=c["experiment"]["run_id"])
    sandbox.initialize();reader=Reader(sandbox);adapter=OrderAdapter(sandbox)
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
    return {"schema":"rpf59-order-trial-v1","domain":domain,"source_kind":"REAL_LOCAL_SQLITE_DETERMINISTIC",
        "executor_pid":os.getpid(),"before":before.public(),"after":after.public(),"inspect":inspect,
        "tool_call":{"name":"refund_order","arguments":args,"result":result},"fault":{"planned":False,"triggered":False,"observed":False},
        "database_sha256":hashlib.sha256(sandbox.path.read_bytes()).hexdigest(),"timeline":timeline,"cleanup":cleanup}

def verify(c,e):
    validate_trial(c);require(set(e)=={"schema","domain","source_kind","executor_pid","before","after","inspect","tool_call","fault","database_sha256","timeline","cleanup"}
        and e["schema"]=="rpf59-order-trial-v1" and e["domain"]==DOMAINS[0] and e["source_kind"] in ("REAL_LOCAL_SQLITE_DETERMINISTIC","SYNTHETIC_TEST_ONLY"),"ORDER_EVIDENCE_FIELDS")
    if e["source_kind"]!="SYNTHETIC_TEST_ONLY":require(type(e["executor_pid"]) is int and e["executor_pid"]>0,"ORDER_REAL_ORIGIN")
    x,f=c["experiment"],c["effect"]
    for snapshot in (e["before"],e["after"]):
        d=snapshot["data"]
        require(set(snapshot)=={"data","sha256"} and snapshot["sha256"]==digest(d) and set(d)=={"reader_id","reader_version","source_id","environment","order","receipts"}
            and d["reader_id"]==READER_ID and d["reader_version"]=="1" and d["source_id"]==f["authority_id"]
            and d["environment"]=={"owner":"rpf-59","run_id":x["run_id"],"environment_id":x["environment_id"],"environment_revision":ENV_REVISION,"reset_generation":0},"ORDER_AUTHORITY_IDENTITY")
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
