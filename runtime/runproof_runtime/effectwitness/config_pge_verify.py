"""Independent RPF-56 offline session/role/feedback/effect verifier; no model IO."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
from .config_pge_contracts import (canonical,digest,strict_json,require,validate_plan,validate_trial,
    EVIDENCE_SCHEMA,BOUNDARIES,CANDIDATES)
from .config_pge_explorer import initial_messages,body_for,parse_selection
from .config_pge_session import validate_budget,feedback
from .config_live_runtime import _api_response,_valid_item,_http_contract
from .config_live_verify import _history
from .config_experiment_verify import pinned_sdk_fields

ROOT=Path(__file__).resolve().parents[3]
SOURCE_FILES=tuple("runtime/runproof_runtime/effectwitness/"+n+".py" for n in (
    "config_pge_contracts","config_pge_explorer","config_pge_target","config_pge_session",
    "config_live_contracts","config_live_runtime","config_live_external","config_live_verify",
    "config_experiment_adapter","config_experiment_contracts","config_experiment_verify"))+("spikes/rpf-56/probe.py","spikes/rpf-53/probe.py","spikes/rpf-55/probe.py")
def source_identity():
    return {p:hashlib.sha256((ROOT/p).read_bytes().replace(b"\r\n",b"\n")).hexdigest() for p in SOURCE_FILES}
def verifier_identity():
    return {"version":"rpf56-config-pge-verifier-v1","sha256":hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n",b"\n")).hexdigest()}
def seal(payload):
    return {"schema":EVIDENCE_SCHEMA,"payload":payload,"payload_sha256":digest(payload),"verifier_identity":verifier_identity()}

def verify_trial(t):
    require(set(t)=={"contracts","contracts_sha256","http","events","tool_trace","completions","sdk","environment","fault","outcome","target_requests"},"TRIAL_FIELDS")
    c=t["contracts"];validate_trial(c)
    require(c["execution"]["model_source"]=="REAL_PROVIDER" and t["contracts_sha256"]==digest(c),"REAL_TARGET_REQUIRED")
    candidate=c["experiment"]["candidate_id"];suppressed=candidate==CANDIDATES[2]
    effect=c["effect"]
    require(t["fault"]=={"planned":candidate!="normal","triggered":suppressed,"observed":suppressed,
        "channel":"EXPLICIT_TOOL_DELIVERY_ERROR" if suppressed else "NONE"},"FAULT_TRUTH")
    require(t["outcome"]=={"agent_failure":"NOT_DETERMINED","platform_error":"EXPECTED_TOOL_DELIVERY_ERROR" if suppressed else "NONE",
        "contract_outcome":"SATISFIED","business_violation":"NOT_PROVEN","target_ack":"UNKNOWN_OUTCOME" if suppressed else "RECEIVED",
        "read_only_reconcile":"CONFIRMED_V2" if suppressed else "NOT_REQUIRED"},"OUTCOME_BOUNDARIES")
    kinds=["initial_current","initial_history","inspect_config","create_config_v1","update_config_v2"]+(
        ["reconcile_current","reconcile_history","final_list"] if suppressed else ["final_current","final_history","final_list"])
    require(len(t["http"])==8,"HTTP_COUNT")
    for i,(o,kind) in enumerate(zip(t["http"],kinds),1):
        method,path,body=_http_contract(effect,kind)
        require(set(o)=={"seq","kind","method","path","request","status","content_type","response","response_body_sha256","elapsed_ms","transport_error"}
            and (o["seq"],o["kind"],o["method"],o["path"],o["request"])==(i,kind,method,path,body),"HTTP_LINEAGE_OR_REPLAY")
        absent=kind in ("initial_current","inspect_config")
        listed=kind.endswith("history") or kind=="final_list"
        ok,data=_api_response(o,404 if absent else 200,4041 if absent else 0,"none" if absent else "list" if listed else "item")
        require(ok and o["response_body_sha256"]==digest(o["response"]),"HTTP_RESPONSE")
        if kind=="initial_history":require(data==[],"INITIAL_STATE")
        elif listed:require((len(data)==1 and _valid_item(data[0],effect,2,"rpf53-v2")) if kind=="final_list" else _history(data,effect),"AUTHORITY_NAMESPACE")
        elif not absent:
            version=1 if kind=="create_config_v1" else 2
            require(_valid_item(data,effect,version,"rpf53-v"+str(version)),"EFFECT_ITEM")
    trace=t["tool_trace"]
    names=["inspect_config","create_config_v1","update_config_v2"]
    require([x["name"] for x in trace]==names and len({x["call_id"] for x in trace})==3,"TARGET_TOOL_LINEAGE")
    for i,call in enumerate(trace):
        args=({}, {"value":"rpf53-v1"},{"expected_version":1,"value":"rpf53-v2"})[i]
        result={"state":"ABSENT"} if i==0 else {"status":"COMMITTED","version":i,"value":"rpf53-v"+str(i)}
        require(call["sequence"]==i+1 and call["arguments"]==args and call["arguments_sha256"]==digest(args)
            and call["result"]==result and call["result_sha256"]==digest(result) and call["http_observation_seq"]==i+3
            and call["returned_in_request"]==(None if suppressed and i==2 else i+2),"TOOL_ARGS_OR_FALSE_ACK")
    completions=t["completions"]
    require(len(completions)==(3 if suppressed else 4) and len(t["target_requests"])==len(completions),"TARGET_REQUEST_COUNT")
    for i,(comp,req) in enumerate(zip(completions,t["target_requests"])):
        require(comp["response_id"]==req["response_id"] and comp["model"]==req["returned_model"]
            and comp["usage"]==req["usage"] and comp["request_sha256"]==req["request_sha256"],"TARGET_PROVIDER_BINDING")
        require(comp["tool_returns"]==[{"call_id":x["call_id"],"result_sha256":x["result_sha256"]} for x in trace[:i]],"TARGET_RETURN_INJECTION")
        require(comp["tool_calls"]==([{"call_id":trace[i]["call_id"],"name":trace[i]["name"],"arguments_sha256":trace[i]["arguments_sha256"]}] if i<3 else []),"TARGET_CALL_ORIGIN")
        if i<3:require(trace[i]["provider_response_id"]==comp["response_id"],"TARGET_RESPONSE_ID")
    events=t["events"]
    require([e["seq"] for e in events]==list(range(1,len(events)+1)) and events[0]["kind"]=="PRE_REGISTERED"
        and events[0]["candidate"]==candidate and all(e["run_id"]==c["experiment"]["run_id"] for e in events)
        and [e["monotonic_ns"] for e in events]==sorted(e["monotonic_ns"] for e in events),"EVENT_RUN_ORDER")
    def one(kind,**fields):
        matches=[e for e in events if e["kind"]==kind and all(e.get(k)==v for k,v in fields.items())]
        require(len(matches)==1,"EVENT_BINDING_"+kind)
        return matches[0]["seq"]
    for o in t["http"]:
        require(one("HTTP_RESERVED",http_seq=o["seq"],method=o["method"],operation=o["kind"])<
            one("HTTP_COMPLETED",http_seq=o["seq"],status=o["status"],code=o["response"]["code"]),"HTTP_EVENT_ORDER")
    for i,x in enumerate(trace):
        end="SUCCESS_WITHHELD" if suppressed and i==2 else "SUCCESS_RELEASED"
        require(one("TOOL_RESERVED",call_id=x["call_id"],name=x["name"])<one("HTTP_RESERVED",http_seq=i+3)<
            one("HTTP_COMPLETED",http_seq=i+3)<one("TOOL_RESULT_READY",call_id=x["call_id"])<one(end,call_id=x["call_id"]),"TOOL_HTTP_EVENT_ORDER")
    require(sum(e["kind"]=="SUCCESS_WITHHELD" for e in events)==int(suppressed)
        and sum(e["kind"]=="SUCCESS_RELEASED" for e in events)==(2 if suppressed else 3)
        and sum(e["kind"]=="FAULT_INHIBITED" for e in events)==int(candidate==CANDIDATES[1]),"ACTIVATION_CARDINALITY")
    if suppressed:
        require(one("SUCCESS_WITHHELD",http_seq=5,channel="EXPLICIT_TOOL_DELIVERY_ERROR")<one("SDK_ERROR_OBSERVED")<one("HTTP_RESERVED",http_seq=6),"SUPPRESSION_OBSERVATION_ORDER")
    if candidate==CANDIDATES[1]:
        require(one("TOOL_RESULT_READY",call_id=trace[2]["call_id"])<one("FAULT_INHIBITED",reason="PRE_REGISTERED_GATE_DISABLED")<one("SUCCESS_RELEASED",call_id=trace[2]["call_id"]),"INHIBITED_GATE")
    sdk=t["sdk"];ready=sdk["ready"];report=sdk["report"];pin=pinned_sdk_fields()
    require(type(sdk["popen_pid"]) is int and sdk["popen_pid"]>0 and ready["pid"]==sdk["popen_pid"] and sdk["stderr_bytes"]==0,"SDK_PID")
    require(c["execution"]["framework"]["identity"]==pin and all(ready[k]==pin[k] for k in
        ("python_executable_sha256","sdk_site_root_binding_sha256","python_runtime_mapping_sha256")),"SDK_PIN")
    if suppressed:require(report["status"]=="SDK_ERROR" and report["stage"]=="sdk_run" and report["error_type"]=="RuntimeError" and report["guard_denials"]==[] and sdk["returncode"]==1,"SDK_ERROR_OBSERVATION")
    else:require(report["status"]=="COMPLETED" and report["pid"]==sdk["popen_pid"] and report["tool_callbacks"]==report["tool_calls"]==3
        and report["requests"]==4 and report["guard_denials"]==[] and report["provider_key_present"] is False and report["business_key_present"] is False and sdk["returncode"]==0,"SDK_REPORT")
    env=t["environment"]
    require(env["source_level"]=="REAL_JAVA_H2_LOCAL_SIMULATION" and env["authority"]=="SAME_SERVICE_READ_ONLY_HTTP"
        and env["jar_sha256"]==c["experiment"]["source"]["jar_sha256"] and env["jar_bytes"]==66981576
        and env["listener_owned"] is True and env["jar_command_verified"] is True and type(env["java_pid"]) is int and env["java_pid"]>0,"JAVA_IDENTITY_OR_AUTHORITY")
    require(1<=len(env["health"])<=3 and env["health"][-1]["status"]==200 and env["health"][-1]["body"]=={"status":"UP"},"HEALTH")
    require(env["cleanup"]=={"java_exited":True,"java_port_closed":True,"sdk_exited":True,"host_port_closed":True,"host_thread_stopped":True,"local_key_released":True},"CLEANUP")
    return True

def verify_payload(p):
    require(set(p)=={"source_kind","plan","plan_sha256","rounds","events","ledger","limits","research"},"SESSION_FIELDS")
    require(p["source_kind"] in ("SYNTHETIC_TEST_ONLY","REAL_EXPLORER_REAL_TARGET_CONFIG_JAVA_HTTP"),"SOURCE_KIND")
    plan=p["plan"];validate_plan(plan)
    require(plan["source_files"]==source_identity() and p["plan_sha256"]==digest(plan) and p["limits"]==BOUNDARIES,"SESSION_SOURCE")
    state=p["ledger"];usage=validate_budget(state)
    require(state["plan_sha256"]==digest(plan) and state["session_id"]==plan["session_id"] and usage["usage_known"],"SESSION_LEDGER")
    require(len(p["rounds"])==2 and len(state["trials"])==2 and len(state["posts"])==4,"TWO_ROUNDS_REQUIRED")
    events=p["events"]
    require([e["seq"] for e in events]==list(range(1,len(events)+1)) and all(e["run_id"]==plan["session_id"] for e in events),"SESSION_EVENTS")
    messages=initial_messages();seen=set();facts=[];used=set()
    for index,row in enumerate(p["rounds"],1):
        require(set(row)=={"round","request_body","request_sha256","explorer_attempt","selection","trial","feedback","feedback_sha256","feedback_event_seq","input_event_seq"}
            and row["round"]==index and row["request_body"]==body_for(messages) and row["request_sha256"]==digest(row["request_body"]),"EXPLORER_INPUT_OR_FEEDBACK")
        r=state["requests"][row["explorer_attempt"]-1]
        require(r["role"]=="EXPLORER" and r["round"]==index and r["request_sha256"]==row["request_sha256"] and r["status"]=="RECEIVED","EXPLORER_LEDGER_BINDING")
        used.add(r["attempt"])
        call=row["selection"]
        require(parse_selection({"choices":[{"message":{"tool_calls":[call]}}]},seen)==call,"SELECTION_SCHEMA")
        seen.add(call["id"])
        candidate=strict_json(call["function"]["arguments"].encode())["candidate_id"]
        require(r.get("selection")==call,"REAL_SELECTION_BINDING")
        trial=row["trial"];verify_trial(trial)
        require(trial["contracts"]==plan["rounds"][index-1]["candidates"][candidate] and state["trials"][index-1]==trial["contracts"]["experiment"]["run_id"],"PRE_REGISTERED_TRIAL")
        for req in trial["target_requests"]:
            g=state["requests"][req["global_attempt"]-1]
            require(g["role"]=="TARGET" and g["round"]==index and all(g[k]==req[k] for k in ("request_sha256","response_id","returned_model","usage")) and g["attempt"] not in used,"ROLE_LEDGER_SPLIT")
            require(g["attempt"]>r["attempt"] and (index!=1 or g["attempt"]<p["rounds"][1]["explorer_attempt"]),"REQUEST_ROLE_TEMPORAL_ORDER")
            used.add(g["attempt"])
        require(row["feedback"]==feedback(trial) and row["feedback_sha256"]==digest(row["feedback"]),"VERIFIED_FEEDBACK")
        inp=events[row["input_event_seq"]-1];fb=events[row["feedback_event_seq"]-1]
        require(inp["kind"]=="PROVIDER_INPUT_FROZEN" and inp["round"]==index and inp["body_sha256"]==row["request_sha256"]
            and fb["kind"]=="FEEDBACK_VALIDATED" and fb["round"]==index and fb["feedback_sha256"]==row["feedback_sha256"] and inp["seq"]<fb["seq"],"FEEDBACK_EVENT_BINDING")
        if index==2:require(p["rounds"][0]["feedback_event_seq"]<row["input_event_seq"] and events[p["rounds"][0]["feedback_event_seq"]-1]["monotonic_ns"]<inp["monotonic_ns"],"FEEDBACK_CAUSAL_ORDER")
        messages += [{"role":"assistant","content":None,"tool_calls":[call]}, {"role":"tool","tool_call_id":call["id"],"content":canonical(row["feedback"]).decode()}]
        facts.append(digest({"fault":trial["fault"],"ack":trial["outcome"]["target_ack"],"effect":"SATISFIED"}))
    require(used=={r["attempt"] for r in state["requests"]},"UNACCOUNTED_PROVIDER_REQUESTS")
    expected_posts=[{"run_id":t["trial"]["contracts"]["experiment"]["run_id"],"operation":op} for t in p["rounds"] for op in ("create_config_v1","update_config_v2")]
    require(state["posts"]==expected_posts,"GLOBAL_POST_LINEAGE")
    require(p["research"]=={"L1":"TWO_REAL_ROLES_EXECUTED" if p["source_kind"]!="SYNTHETIC_TEST_ONLY" else "SYNTHETIC_ONLY",
        "L2":facts[0]!=facts[1],"H1":"NOT_PROVEN","information_gain_proxy":int(facts[0]!=facts[1])},"RESEARCH_OVERCLAIM")
    return {"status":"PASS","source_kind":p["source_kind"],"budget":usage,"research":p["research"]}

def verify_bytes(raw,anchor):
    require(anchor is not None,"EXTERNAL_ANCHOR_REQUIRED")
    require(hashlib.sha256(raw).hexdigest()==anchor,"EXTERNAL_ANCHOR_MISMATCH")
    e=strict_json(raw)
    require(set(e)=={"schema","payload","payload_sha256","verifier_identity"} and e["schema"]==EVIDENCE_SCHEMA
        and e["payload_sha256"]==digest(e["payload"]) and e["verifier_identity"]==verifier_identity(),"EVIDENCE_ENVELOPE")
    return verify_payload(e["payload"])
def main():
    p=argparse.ArgumentParser();p.add_argument("path",type=Path);p.add_argument("--sha256");a=p.parse_args()
    if a.sha256 is None:return 2
    try:print(canonical(verify_bytes(a.path.read_bytes(),a.sha256)).decode());return 0
    except Exception as exc:print(getattr(exc,"code","INVALID_EVIDENCE"));return 3
if __name__=="__main__":raise SystemExit(main())
