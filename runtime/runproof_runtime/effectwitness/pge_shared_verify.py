"""Independent RPF-58 content verifier: shared relations and static domain Oracles."""
import argparse,hashlib
from pathlib import Path
from .pge_shared_contracts import (canonical,digest,strict_json,require,validate_plan,sources,DOMAINS,BOUNDARIES)
from .pge_shared_core import validate_state,verify_task_records,dispatch_identity,domain_port
from .pge_shared_feedback import visible,project
SCHEMA="rpf58-cross-domain-portability-evidence-v2"
CLAIM="CROSS_DOMAIN_SHARED_CORE_LOCAL_CONTROLLED_EXECUTION_PROVEN"
def identity():return {"version":"rpf58-shared-verifier-v2","sha256":hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n",b"\n")).hexdigest()}
def domain_verdict(contract,evidence):
    from . import pge_order_port,pge_config_port
    d=contract["experiment"]["domain"];require(d in DOMAINS,"DOMAIN_NOT_ALLOWLISTED")
    return {DOMAINS[0]:pge_order_port.verify,DOMAINS[1]:pge_config_port.verify}[d](contract,evidence)
def seal(p):return {"schema":SCHEMA,"payload":p,"payload_sha256":digest(p),"verifier_identity":identity()}

def verify_payload(p):
    require(set(p)=={"source_kind","plan","rows","ledger","ledger_chain_sha256","boundaries","claim","cold_fixture","task_intents"}
        and p["source_kind"] in ("BOTH_REAL_CONTROLLED","SYNTHETIC_TEST_ONLY") and p["boundaries"]==BOUNDARIES,"SOURCE_OR_BOUNDARIES")
    plan=p["plan"];validate_plan(plan);require(plan["source_files"]==sources(),"EXECUTED_SOURCE_IDENTITY")
    s=p["ledger"];counts=validate_state(s,plan)
    from .pge_config_port import validate_cold_capture
    validate_cold_capture(p["cold_fixture"])
    require(p["cold_fixture"]["source_kind"]==("REAL_SDK_COLD_FIXTURE" if p["source_kind"]=="BOTH_REAL_CONTROLLED" else "SYNTHETIC_TEST_ONLY"),"COLD_REAL_SOURCE_REQUIRED")
    task_rows=verify_task_records(p["task_intents"]);source_sha=digest(sources())
    cold_rows=[r for r in task_rows if r["kind"]=="COLD" and r["status"]=="PASS"]
    session_rows=[r for r in task_rows if r["kind"]=="SESSION"]
    metadata=[r for r in task_rows if r["kind"]=="METADATA" and r["status"]=="PASS" and r["source_sha256"]==source_sha]
    require(len(cold_rows)==len(session_rows)==1 and bool(metadata) and cold_rows[0]["source_sha256"]==session_rows[0]["source_sha256"]==source_sha
        and cold_rows[0]["ordinal"]==p["cold_fixture"]["attempt"] and cold_rows[0]["detail"]=={"capture_sha256":digest(p["cold_fixture"])}
        and session_rows[0]["status"]=="PASS" and session_rows[0]["data"]=={"plan_sha256":digest(plan),"cold_capture_sha256":digest(p["cold_fixture"])}
        and session_rows[0]["detail"]=={"ledger_sha256":digest(s),"rows_sha256":digest(p["rows"])},"COLD_TASK_SESSION_SOURCE_BINDING")
    require(len(p["rows"])==2 and all(r["status"]=="DONE" for r in s["reservations"]),"COMPLETE_SETTLEMENT_REQUIRED")
    require(p["claim"]==(CLAIM if p["source_kind"]=="BOTH_REAL_CONTROLLED" else "SYNTHETIC_TEST_ONLY"),"CLAIM_OVERREACH")
    prior=[];expected_labels={};bydomain={}
    for index,(row,c) in enumerate(zip(p["rows"],plan["trials"])):
        require(set(row)=={"contract","input","evidence","feedback","trial_reservation"} and row["contract"]==c
            and row["input"]==visible(prior),"SHARED_INPUT_OR_DOMAIN_SPLICE")
        d=c["experiment"]["domain"];e=row["evidence"];domain_verdict(c,e)
        expected_source=("REAL_LOCAL_SQLITE_DETERMINISTIC","REAL_LOCAL_SDK_FIXTURE_JAVA_HTTP")[index]
        require(e["source_kind"]==(expected_source if p["source_kind"]=="BOTH_REAL_CONTROLLED" else "SYNTHETIC_TEST_ONLY"),"MIXED_OR_SYNTHETIC_SOURCE_PROMOTION")
        require(row["feedback"]==project(c,e,prior),"CROSS_DOMAIN_FACT_OR_AUTHORITY_SPLICE")
        prior.append(row["feedback"]);bydomain[d]=row
        expected_labels[(d,"trial")]={"trial":1,"order_trial" if index==0 else "config_trial":1}
        r=s["reservations"][row["trial_reservation"]-1]
        require(r["domain"]==d and r["label"]=="trial" and r["detail"]=={"evidence_sha256":digest(e),"feedback_sha256":digest(row["feedback"])},"TRIAL_PARENT_LEDGER_BINDING")
    expected_labels[(DOMAINS[0],"refund_order")]={"sqlite_mutation":1}
    expected_labels[(DOMAINS[1],"java")]={"jvm":1}
    expected_labels[(DOMAINS[1],"sdk")]={"sdk":1}
    for i in range(3):expected_labels[(DOMAINS[1],f"health:{i}")]={"health":1}
    scene=p["rows"][1]["evidence"]["scene"]
    for obs in scene["http"]:
        expected_labels[(DOMAINS[1],"http:"+obs["kind"])]={"business_http":1,**({"post":1} if obs["method"]=="POST" else {})}
    require({(r["domain"],r["label"]):r["units"] for r in s["reservations"]}==expected_labels,"GLOBAL_BUDGET_SPLIT_OR_EXTRA_IO")
    for r in s["reservations"]:
        label=r["label"]
        if label.startswith("http:"):
            obs=next(o for o in scene["http"] if "http:"+o["kind"]==label)
            require(r["detail"]=={"http_seq":obs["seq"],"observation_sha256":digest(obs)},"HTTP_WAL_OBSERVATION")
        elif label=="java":require(r["detail"]=={"pid":scene["environment"]["java_pid"]},"JAVA_WAL_PID")
        elif label=="sdk":require(r["detail"]=={"pid":scene["sdk"]["popen_pid"],"report_sha256":digest(scene["sdk"]["report"])},"SDK_WAL_PID")
        elif label=="refund_order":
            receipt=p["rows"][0]["evidence"]["after"]["data"]["receipts"][0]
            require(r["detail"]=={"receipt_id":receipt["receipt_id"],"status":"COMMITTED"},"ORDER_WAL_RECEIPT")
        elif label.startswith("health:"):
            index=int(label.split(":")[1]);actual=len(scene["environment"]["health"])
            require((set(r["detail"])=={"health_sha256"} and type(r["detail"]["health_sha256"]) is str and len(r["detail"]["health_sha256"])==64)
                if index<actual else r["detail"]=={"status":"UNUSED_RESERVED_NO_IO"},"HEALTH_ACTUAL_VS_UNUSED")
    events=s["events"]
    require(sum(e["kind"]=="RESOURCE_RESERVED" for e in events)==len(s["reservations"])
        and sum(e["kind"]=="RESOURCE_SETTLED" for e in events)==len(s["reservations"])
        and all(sum(e["kind"]==kind for e in events)==2 for kind in ("INPUT_FROZEN","SHARED_PORT_DISPATCH","DOMAIN_CALL_ENTERED","DOMAIN_CALL_RETURNED","DOMAIN_RETURNED","DOMAIN_VERIFIED","FEEDBACK_FROZEN")),"EVENT_CARDINALITY")
    def one(kind,**fields):
        matches=[e for e in events if e["kind"]==kind and all(e["data"].get(k)==v for k,v in fields.items())]
        require(len(matches)==1,"EVENT_BINDING_"+kind);return matches[0]
    require(all(e["kind"] in ("INPUT_FROZEN","SHARED_PORT_DISPATCH","DOMAIN_RETURNED","DOMAIN_VERIFIED","FEEDBACK_FROZEN",
        "RESOURCE_RESERVED","RESOURCE_SETTLED","ORDER_PORT_EVENT","CONFIG_TOOL_EVENT","DOMAIN_CALL_ENTERED","DOMAIN_CALL_RETURNED") for e in events),"UNKNOWN_SHARED_EVENT")
    for r in s["reservations"]:
        a=one("RESOURCE_RESERVED",reservation_id=r["id"]);b=one("RESOURCE_SETTLED",reservation_id=r["id"])
        require(a["seq"]<b["seq"] and a["data"]=={"reservation_id":r["id"],"domain":r["domain"],"label":r["label"],"units":r["units"]}
            and b["data"]=={"reservation_id":r["id"],"status":"DONE","detail_sha256":digest(r["detail"])},"RESOURCE_EVENT_IDENTITY")
    stage=[]
    for row in p["rows"]:
        c,e=row["contract"],row["evidence"];d=c["experiment"]["domain"]
        inp=one("INPUT_FROZEN",domain=d,input_sha256=digest(row["input"]))
        start=one("SHARED_PORT_DISPATCH",domain=d,entry="SharedSession.execute_trial",contract_sha256=digest(c))
        runtime=start["data"]["runtime_identity"]
        require(set(runtime)=={"entry_code_sha256","port_callable","port_code_sha256"},"RUNTIME_DISPATCH_FIELDS")
        if p["source_kind"]=="BOTH_REAL_CONTROLLED":require(runtime==dispatch_identity(domain_port(d).execute),"ACTUAL_PORT_CALLABLE_IDENTITY")
        entered=one("DOMAIN_CALL_ENTERED",domain=d,runtime_identity=runtime)
        exited=one("DOMAIN_CALL_RETURNED",domain=d,runtime_identity=runtime,evidence_sha256=digest(e))
        returned=one("DOMAIN_RETURNED",domain=d,evidence_sha256=digest(e))
        verified=one("DOMAIN_VERIFIED",domain=d,verdict_sha256=digest(domain_verdict(c,e)))
        fb=one("FEEDBACK_FROZEN",domain=d,feedback_sha256=digest(row["feedback"]))
        require(inp["seq"]<start["seq"]<entered["seq"]<exited["seq"]<returned["seq"]<verified["seq"]<fb["seq"],"SHARED_EXECUTION_FEEDBACK_ORDER")
        reserve=one("RESOURCE_RESERVED",reservation_id=row["trial_reservation"])
        settle=one("RESOURCE_SETTLED",reservation_id=row["trial_reservation"])
        require(inp["seq"]<reserve["seq"]<start["seq"] and fb["seq"]<settle["seq"],"TRIAL_RESERVE_BEFORE_IO")
        for r in s["reservations"]:
            if r["domain"]==d and r["label"]!="trial":
                a=one("RESOURCE_RESERVED",reservation_id=r["id"]);b=one("RESOURCE_SETTLED",reservation_id=r["id"])
                require(start["seq"]<a["seq"]<b["seq"]<returned["seq"],"RESOURCE_OUTSIDE_DOMAIN")
        stage.append((inp,fb,settle))
    require(stage[0][2]["seq"]<stage[1][0]["seq"],"FEEDBACK_BEFORE_NEXT_DOMAIN")
    order_events=[e for e in events if e["kind"]=="ORDER_PORT_EVENT"]
    order=p["rows"][0]["evidence"]
    require([{"kind":e["data"]["port_kind"],"monotonic_ns":e["monotonic_ns"],"data":{k:v for k,v in e["data"].items() if k!="port_kind"}}
        for e in order_events]==order["timeline"],"ORDER_CORE_EVENT_LINEAGE")
    require([e["data"]["event"] for e in events if e["kind"]=="CONFIG_TOOL_EVENT"]==scene["events"],"CONFIG_CORE_EVENT_LINEAGE")
    require(counts["provider"]==0,"PROVIDER_FORBIDDEN")
    return {"status":"PASS","source_kind":p["source_kind"],"claim":p["claim"],"reserved_physical_budget":counts,
        "actual":{"provider":0,"tokens":0,"cost_cny":0,"jvm":1,"sdk":1,"sqlite_trial":1,"business_http":len(scene["http"]),
            "post":sum(o["method"]=="POST" for o in scene["http"]),"health":len(scene["environment"]["health"])},"boundaries":BOUNDARIES}
def verify_bytes(raw,anchor):
    require(anchor is not None,"EXTERNAL_ANCHOR_REQUIRED");require(hashlib.sha256(raw).hexdigest()==anchor,"EXTERNAL_ANCHOR_MISMATCH")
    e=strict_json(raw)
    require(set(e)=={"schema","payload","payload_sha256","verifier_identity"} and e["schema"]==SCHEMA
        and e["payload_sha256"]==digest(e["payload"]) and e["verifier_identity"]==identity(),"EVIDENCE_ENVELOPE")
    return verify_payload(e["payload"])
def main():
    p=argparse.ArgumentParser();p.add_argument("path",type=Path);p.add_argument("--sha256");a=p.parse_args()
    if a.sha256 is None:return 2
    try:print(canonical(verify_bytes(a.path.read_bytes(),a.sha256)).decode());return 0
    except Exception as e:print(getattr(e,"code","INVALID_EVIDENCE"));return 3
if __name__=="__main__":raise SystemExit(main())
