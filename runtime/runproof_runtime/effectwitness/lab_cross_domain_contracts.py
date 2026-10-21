"""RPF-60 frozen contracts. Static domains, no executable/path/URL registry."""
from pathlib import Path
import hashlib,re
from .config_live_contracts import (canonical,digest,strict_json,require,TOOLS,AGENT_INSTRUCTIONS,TASK_PROMPT,TOOL_HELP,
    SOURCE_COMMIT,SOURCE_MANIFEST_SHA256,SOURCE_JAR_SHA256,SOURCE_JAR_BYTES)
from .config_experiment_verify import pinned_sdk_fields
ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/".local/rpf-60"
BASE="c07236b72aea6690ba96d193178fc105f685ea50"
BRANCH="codex/rpf-60-cross-domain-live-lab-gateway-ui"
DOMAINS=("order-refund","config-java-http")
CANDIDATES=("order-refund/normal","config-java-http/planned-but-inhibited")
MODEL="deepseek-flash"
LIMITS={"trial":2,"order_trial":2,"config_trial":2,"sqlite_mutation":2,"jvm":2,"sdk":2,"business_http":16,"post":4,"health":6,"provider":2,"token_reserve":6000,"cost_micro_cny":150000}
PRICE={"checked_date":"2026-10-21","model":MODEL,"input_cny_per_million_bound":4.5,"output_cny_per_million_bound":18.0,
    "basis":"USD_PEAK_0.30_INPUT_1.20_OUTPUT_TIMES_15_GUARD_NOT_FX_OR_INVOICE",
    "sources":["https://api-docs.deepseek.com/quick_start/pricing/","https://api-docs.deepseek.com/guides/tool_calls/"]}
BOUNDARIES={"real_explorer":"REAL_PROVIDER","selection_source":"REAL_EXPLORER_TOOL_CALL",
    "target_sources":{"order-refund":"DETERMINISTIC_ORDER_TARGET","config-java-http":"FIXTURE_SCRIPTED"},
    "issuer_authenticity":"NOT_ESTABLISHED","database_independent_authority":"NOT_ESTABLISHED","independent_reproduction":"NOT_TESTED",
    "WorkSwarm":"NOT_PROVEN","attribution":"CORRELATIONAL_ONLY","H1":"NOT_PROVEN","H3":"NOT_PROVEN","CAUSAL_ADVANTAGE":"NOT_PROVEN","cross_domain_information_gain":"NOT_COMPARABLE"}
NEW_FILES=tuple('runtime/runproof_runtime/effectwitness/'+n+'.py' for n in ('lab_cross_domain_contracts','lab_cross_domain','lab_cross_domain_projection','lab_cross_domain_verify','lab_gateway','lab_store'))+('runtime/tests/test_effectwitness_lab_cross_domain.py','runtime/tests/test_effectwitness_lab_cross_domain_gateway.py','web/src/features/effectwitness/CrossDomainPage.tsx','web/src/features/effectwitness/crossDomainApi.ts','web/src/features/effectwitness/crossDomainCopy.ts','web/src/features/effectwitness/crossDomainApi.test.ts','web/src/App.tsx','web/src/components/AppShell.tsx','web/src/features/effectwitness/lab.css','vite.config.ts')
OLD_FILES=tuple("runtime/runproof_runtime/effectwitness/"+n+".py" for n in (
    "orders","contracts","effect_oracle","config_pge_target","config_pge_contracts","config_pge_session","config_live_runtime","config_live_contracts",
    "config_live_external","config_live_verify","config_experiment_adapter","config_experiment_contracts","config_experiment_verify"))+(
    "spikes/rpf-53/probe.py","spikes/rpf-55/probe.py","runtime/runproof_runtime/models.py")
def sources():return {p:hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in NEW_FILES+OLD_FILES}
def scoped(path):
    path=Path(path)
    require(path.is_absolute() and path.resolve().is_relative_to(WORK.resolve()) and not any(
        p.is_symlink() or getattr(p,"is_junction",lambda:False)() for p in (path,*path.parents)),"TASK_PATH_SCOPE")
    return path
def trial(domain,run_id,source_sha,java_port=45001,host_port=46001):
    require(domain in DOMAINS and type(run_id) is str and re.fullmatch(r"rpf60-(?:order|config)-[a-f0-9]{16}",run_id),"DOMAIN_OR_RUN")
    require(run_id.startswith("rpf60-order-" if domain==DOMAINS[0] else "rpf60-config-"),"DOMAIN_RUN_MISMATCH")
    require(type(source_sha) is str and re.fullmatch(r"[a-f0-9]{64}",source_sha),"SOURCE_SHA")
    x={"schema":"rpf60-experiment-v1","owner":"rpf-60","domain":domain,"run_id":run_id,"source_sha256":source_sha,
        "candidate_id":"normal" if domain==DOMAINS[0] else "planned-but-inhibited","fault":"none","environment_id":"env-"+run_id,"reset_generation":0}
    if domain==DOMAINS[0]:
        e={"schema":"rpf60-execution-v1","driver":"DETERMINISTIC_ORDER_TARGET","tools":["inspect_order","refund_order"],"provider_requests":0}
        f={"schema":"rpf60-order-effect-v1","order_id":"order-"+run_id,"operation_id":"refund-"+run_id,
            "authority_id":"authority-"+run_id,"amount_minor":2500,"currency":"CNY","authority":"SQLITE_READ_ONLY_RECEIPT_READER"}
    else:
        require(type(java_port) is int and type(host_port) is int and 1024<=java_port<=65535 and 1024<=host_port<=65535 and java_port!=host_port,"PORTS")
        e={"schema":"rpf60-execution-v1","owner":"rpf-60","agent_id":"target-"+run_id,"role":"TARGET_FIXTURE","model_source":"FIXTURE_SCRIPTED",
            "framework":{"name":"pydantic-ai-slim","version":"2.57.0","openai_version":"3.35.1","identity":pinned_sdk_fields()},
            "tools":list(TOOLS),"agent_instructions":AGENT_INSTRUCTIONS,"task_prompt":TASK_PROMPT,"tool_help":TOOL_HELP,
            "service":{"host":"127.0.0.1","port":java_port},"agent_host":{"host":"127.0.0.1","port":host_port},"release_authority":"NOT_HELD_BY_AGENT"}
        f={"schema":"rpf60-config-effect-v1","app":"rpf53app"+run_id.replace("-",""),"env":"rpf53local"+run_id.replace("-",""),
            "key":"rpf53.item."+run_id,"initial_state":"ABSENT","initial_value":"rpf53-v1","required_value":"rpf53-v2","initial_version":1,"required_version":2,"history_versions":[2,1]}
        x.update(fault_plan={"planned":True,"enabled":False,"kind":"LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200","tool":"update_config_v2",
            "max_activations":1,"channel":"EXPLICIT_TOOL_DELIVERY_ERROR","after_fault":"STOP_WRITES_READ_ONLY_RECONCILE"},
            source={"commit":SOURCE_COMMIT,"manifest_sha256":SOURCE_MANIFEST_SHA256,"jar_sha256":SOURCE_JAR_SHA256,"jar_bytes":SOURCE_JAR_BYTES,
                "task_jar":".local/rpf-60/jar/config-center-server-1.0.0.jar"},runtime_source_sha256=source_sha)
    return {"schema":"rpf60-domain-contracts-v1","execution":e,"effect":f,"experiment":x}
def validate_trial(c):
    require(type(c) is dict and set(c)=={"schema","execution","effect","experiment"},"TRIAL_FIELDS")
    x,e=c["experiment"],c["execution"]
    expected=trial(x["domain"],x["run_id"],x["source_sha256"],e.get("service",{}).get("port",45001),e.get("agent_host",{}).get("port",46001))
    require(c==expected,"FROZEN_DOMAIN_CONTRACT")
def domain_for(candidate):
    require(candidate in CANDIDATES,"CANDIDATE_ALLOWLIST")
    return dict(zip(CANDIDATES,DOMAINS))[candidate]

def plan(session_id,slots,source_map):
    require(re.fullmatch(r"rpf60-session-[a-f0-9]{16}",session_id) is not None and len(slots)==2,"SESSION_ID")
    rounds=[]
    for i,(order_run,config_run,java,host) in enumerate(slots,1):
        rounds.append({"round":i,"candidates":{name:trial(domain_for(name),run,digest(source_map),java,host)
            for name,run in zip(CANDIDATES,(order_run,config_run))}})
    runs=[t["experiment"]["run_id"] for row in rounds for t in row["candidates"].values()]
    require(len(set(runs))==4,"NAMESPACE_REPLAY")
    ports=[r["candidates"][CANDIDATES[1]]["execution"][kind]["port"] for r in rounds for kind in ("service","agent_host")]
    require(len(set(ports))==4,"PORT_REPLAY")
    return {"schema":"rpf60-select-session-v1","owner":"rpf-60","base":BASE,"branch":BRANCH,"session_id":session_id,
        "explorer_id":"rpf60-explorer","catalog":list(CANDIDATES),"limits":LIMITS,"price":PRICE,"source_files":source_map,"boundaries":BOUNDARIES,"rounds":rounds}

def validate_plan(p):
    slots=[]
    for row in p["rounds"]:
        a,b=[row["candidates"][name] for name in CANDIDATES]
        slots.append((a["experiment"]["run_id"],b["experiment"]["run_id"],b["execution"]["service"]["port"],b["execution"]["agent_host"]["port"]))
    require(p==plan(p["session_id"],slots,p["source_files"]),"FROZEN_SESSION")

"""RPF-60 Explorer: named tool, strict parse, text-free response projection."""
import copy
import hashlib
import http.client
import re
import ssl
import time

SYSTEM="Choose one controlled experiment using verified feedback. Repeats allowed; no forced domain switch."
def tools():
    return [{"type":"function","function":{"name":"select_experiment","parameters":{"type":"object","properties":{
        "candidate_id":{"type":"string","enum":list(CANDIDATES)}},"required":["candidate_id"],"additionalProperties":False}}}]

def messages_for(prior):
    messages=[{"role":"system","content":SYSTEM},{"role":"user","content":canonical({"design":{
        CANDIDATES[0]:"fresh SQLite full refund 2500 CNY minor units; independent receipt Reader; deterministic Target",
        CANDIDATES[1]:"fresh Java H2 config ABSENT->v1->v2/history[2,1]; planned fault gate disabled; SDK scripted Target"},
        "rounds":2,"verified_coverage":visible([])}).decode()}]
    for row in prior:
        messages.append({"role":"assistant","tool_calls":[copy.deepcopy(row["selection"])]})
        fb=row["feedback"]
        projection={"domain":fb["domain"],"authority":fb["authority"],"status":fb["status"],"verified_fact_ids":fb["verified_fact_ids"],"new_fact_ids":fb["new_fact_ids"],"feedback_sha256":digest(fb)}
        messages.append({"role":"tool","tool_call_id":row["selection"]["id"],"content":canonical(projection).decode()})
        messages.append({"role":"user","content":canonical({"next_round":len(prior)+1,"verified_coverage":visible([r["feedback"] for r in prior])}).decode()})
    return messages

def body_for(messages):
    return {"model":MODEL,"messages":copy.deepcopy(messages),"tools":tools(),"tool_choice":{"type":"function","function":{"name":"select_experiment"}},
        "parallel_tool_calls":False,"thinking":{"type":"disabled"},"max_tokens":128,"stream":False}

def _type(x):
    return "null" if x is None else "boolean" if type(x) is bool else "object" if type(x) is dict else "array" if type(x) is list else "string" if type(x) is str else "number" if type(x) in (int,float) else "OTHER"
def fingerprint(mapping,key):
    if key not in mapping:return {"present":False,"type":"MISSING","length":None,"sha256":None}
    x=mapping[key];raw=canonical(x)
    return {"present":True,"type":_type(x),"length":len(x) if type(x) in (str,list,dict) else len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
def _identity(x,allow):
    return x if type(x) is str and re.fullmatch(allow,x) else "OTHER"
def safe_response_shape(data):
    """No arbitrary values, argument text, message content or reasoning leave here."""
    d=data if type(data) is dict else {};choices=d.get("choices");rows=[]
    if type(choices) is list:
        for choice in choices[:4]:
            ch=choice if type(choice) is dict else {};m=ch.get("message");m=m if type(m) is dict else {}
            calls=m.get("tool_calls");cs=[]
            if type(calls) is list:
                for call in calls[:4]:
                    call=call if type(call) is dict else {};f=call.get("function");f=f if type(f) is dict else {}
                    cs.append({"type":"function" if call.get("type")=="function" else "OTHER",
                        "function_name":"select_experiment" if f.get("name")=="select_experiment" else "OTHER",
                        "call_id":fingerprint(call,"id"),"arguments":fingerprint(f,"arguments")})
            rows.append({"finish_reason":ch.get("finish_reason") if ch.get("finish_reason") in ("stop","length","tool_calls","content_filter","aborted","insufficient_system_resource") else "OTHER",
                "message_type":_type(ch.get("message")),"message_role":m.get("role") if m.get("role") in ("assistant","tool","user","system") else "OTHER",
                "content":fingerprint(m,"content"),"reasoning_content":fingerprint(m,"reasoning_content"),
                "tool_calls_presence":"PRESENT" if "tool_calls" in m else "MISSING","tool_calls_type":_type(calls) if "tool_calls" in m else "MISSING",
                "tool_calls_count":len(calls) if type(calls) is list else None,"calls":cs})
    u=d.get("usage");u=u if type(u) is dict else {}
    return {"schema":"rpf60-response-shape-v1","response_type":_type(data),
        "response_id":_identity(d.get("id"),r"[A-Za-z0-9_-]{1,128}"),"response_id_fingerprint":fingerprint(d,"id"),
        "model":d.get("model") if d.get("model") in (MODEL,"DeepSeek-V4.1-Flash-1017") else "OTHER",
        "usage":{k:u[k] if type(u.get(k)) is int and 0<=u[k]<=1000000 else None for k in ("prompt_tokens","completion_tokens","total_tokens")},
        "choices_type":_type(choices),"choices_count":len(choices) if type(choices) is list else None,"choices":rows}

def parse_selection(data,seen):
    require(type(data) is dict,"EXPLORER_RESPONSE")
    require(type(data.get("id")) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}",data["id"]) is not None
        and data.get("model") in (MODEL,"DeepSeek-V4.1-Flash-1017"),"EXPLORER_IDENTITY")
    u=data.get("usage")
    require(type(u) is dict and all(type(u.get(k)) is int and u[k]>=0 for k in ("prompt_tokens","completion_tokens","total_tokens"))
        and u["prompt_tokens"]+u["completion_tokens"]==u["total_tokens"],"EXPLORER_USAGE")
    choices=data.get("choices")
    require(type(choices) is list and len(choices)==1 and type(choices[0]) is dict,"EXPLORER_CHOICES")
    m=choices[0].get("message")
    require(type(m) is dict and m.get("role")=="assistant","EXPLORER_MESSAGE")
    calls=m.get("tool_calls")
    require(type(calls) is list and len(calls)==1,"ONE_SELECTION_REQUIRED")
    require(choices[0].get("finish_reason")=="tool_calls","EXPLORER_FINISH_REASON")
    call=calls[0]
    require(type(call) is dict and set(call)<={"id","type","function","index"} and call.get("type")=="function"
        and type(call.get("id")) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}",call["id"]) is not None and call["id"] not in seen,"SELECTION_CALL_ID")
    f=call.get("function")
    require(type(f) is dict and set(f)=={"name","arguments"} and f["name"]=="select_experiment"
        and type(f["arguments"]) is str and len(f["arguments"].encode())<=256,"SELECTION_TOOL")
    args=strict_json(f["arguments"].encode())
    require(type(args) is dict and set(args)=={"candidate_id"} and args["candidate_id"] in CANDIDATES,"SELECTION_ARGUMENTS")
    return {"id":call["id"],"type":"function","function":dict(f)}

def validate_response_shape(s):
    require(type(s) is dict and set(s)=={"schema","response_type","response_id","response_id_fingerprint","model","usage","choices_type","choices_count","choices"}
        and s["schema"]=="rpf60-response-shape-v1","SHAPE_FIELDS")
    kinds=("MISSING","null","boolean","object","array","string","number","OTHER")
    def fp(f):
        require(type(f) is dict and set(f)=={"present","type","length","sha256"} and type(f["present"]) is bool and f["type"] in kinds,"SHAPE_FINGERPRINT")
        if f["present"]:require(type(f["length"]) is int and 0<=f["length"]<=262144 and type(f["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}",f["sha256"]) is not None,"SHAPE_FINGERPRINT_VALUE")
        else:require(f=={"present":False,"type":"MISSING","length":None,"sha256":None},"SHAPE_ABSENCE")
    require(s["response_type"] in kinds and s["choices_type"] in kinds and s["model"] in (MODEL,"DeepSeek-V4.1-Flash-1017","OTHER")
        and type(s["response_id"]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}",s["response_id"]) is not None,"SHAPE_IDENTITIES")
    fp(s["response_id_fingerprint"])
    require(type(s["usage"]) is dict and set(s["usage"])=={"prompt_tokens","completion_tokens","total_tokens"}
        and all(v is None or (type(v) is int and 0<=v<=1000000) for v in s["usage"].values()),"SHAPE_USAGE")
    require((s["choices_count"] is None or (type(s["choices_count"]) is int and s["choices_count"]>=0)) and type(s["choices"]) is list and len(s["choices"])<=4,"SHAPE_CHOICES")
    for ch in s["choices"]:
        require(set(ch)=={"finish_reason","message_type","message_role","content","reasoning_content","tool_calls_presence","tool_calls_type","tool_calls_count","calls"}
            and ch["finish_reason"] in ("stop","length","tool_calls","content_filter","aborted","insufficient_system_resource","OTHER")
            and ch["message_type"] in kinds and ch["message_role"] in ("assistant","tool","user","system","OTHER")
            and ch["tool_calls_presence"] in ("PRESENT","MISSING") and ch["tool_calls_type"] in kinds
            and (ch["tool_calls_count"] is None or (type(ch["tool_calls_count"]) is int and ch["tool_calls_count"]>=0)) and type(ch["calls"]) is list and len(ch["calls"])<=4,"SHAPE_CHOICE_FIELDS")
        fp(ch["content"]);fp(ch["reasoning_content"])
        for call in ch["calls"]:
            require(set(call)=={"type","function_name","call_id","arguments"} and call["type"] in ("function","OTHER") and call["function_name"] in ("select_experiment","OTHER"),"SHAPE_CALL")
            fp(call["call_id"]);fp(call["arguments"])
    return True

def request(body,total,round_index,key,*,shape_writer):
    attempt=total.reserve_request("EXPLORER",round_index,body)
    connection=http.client.HTTPSConnection("api.deepseek.com",timeout=60,context=ssl.create_default_context());saved=False
    try:
        connection.request("POST","/chat/completions",canonical(body),{"Authorization":"Bearer "+key,"Content-Type":"application/json","Connection":"close"})
        response=connection.getresponse();raw=response.read(262145)
        try:data=strict_json(raw) if len(raw)<=262144 else None
        except Exception:data=None
        shape=safe_response_shape(data)
        validate_response_shape(shape)
        observation={"shape":shape,"attempt":attempt,"request_sha256":digest(body),"http_status":response.status,"received_monotonic_ns":time.monotonic_ns()}
        shape_writer(observation);saved=True;total.response_observation=observation
        require(response.status==200 and data is not None and len(raw)<=262144,"EXPLORER_HTTP_OR_JSON")
        total.received(attempt,data)
        return data,attempt
    except Exception:
        if not saved:shape_writer({"shape":safe_response_shape(None),"attempt":attempt,"request_sha256":digest(body),"http_status":None,"received_monotonic_ns":time.monotonic_ns()})
        raise
    finally:connection.close()

"""One projection entry, domain/Effect/Authority-qualified facts; no LLM IO."""
def visible(prior):
    return {"catalog":list(CANDIDATES),"prior_feedback_sha256":[digest(f) for f in prior],
        "seen_facts_by_domain":{d:sorted({fact for f in prior if f["domain"]==d for fact in f["verified_fact_ids"]}) for d in DOMAINS},
        "not_tested_domain_ids":[d for d in DOMAINS if d not in [f["domain"] for f in prior]]}

def project(contract,evidence,prior):
    # Recompute the domain predicates; the port cannot grant itself PASS.
    from .lab_cross_domain_verify import domain_verdict
    verdict=domain_verdict(contract,evidence)
    d=contract["experiment"]["domain"]
    authority=verdict["authority"]
    facts=(["order-refund:full_refund_v1:sqlite_receipt:receipt_unique"] if d==DOMAINS[0] else
        ["config-java-http:version2_history21:same_service_http:effect_satisfied","config-java-http:disabled_gate:same_service_http:fault_planned_inhibited"])
    before=visible(prior)["seen_facts_by_domain"][d]
    return {"schema":"rpf60-domain-feedback-v1","domain":d,"run_id":contract["experiment"]["run_id"],
        "evidence_sha256":digest(evidence),"source_kind":evidence["source_kind"],"authority":authority,
        "status":"VERIFIED","verified_fact_ids":facts,"seen_fact_ids_before":before,
        "new_fact_ids":sorted(set(facts)-set(before)),"not_applicable":["CROSS_DOMAIN_INFORMATION_GAIN_SUM"],
        "unknown":["ISSUER_AUTHENTICITY","INDEPENDENT_REPRODUCTION"]}
