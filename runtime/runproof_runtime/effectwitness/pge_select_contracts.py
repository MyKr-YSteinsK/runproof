"""RPF-59 frozen contracts. Static domains, no executable/path/URL registry."""
from pathlib import Path
import hashlib,re
from .config_live_contracts import (canonical,digest,strict_json,require,TOOLS,AGENT_INSTRUCTIONS,TASK_PROMPT,TOOL_HELP,
    SOURCE_COMMIT,SOURCE_MANIFEST_SHA256,SOURCE_JAR_SHA256,SOURCE_JAR_BYTES)
from .config_experiment_verify import pinned_sdk_fields
ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/".local/rpf-59"
BASE="03d13513ad958cf01455a39bede4f873ed474e21"
BRANCH="codex/rpf-59-cross-domain-real-explorer-selection"
DOMAINS=("order-refund","config-java-http")
CANDIDATES=("order-refund/normal","config-java-http/planned-but-inhibited")
MODEL="deepseek-flash"
LIMITS={"trial":2,"order_trial":2,"config_trial":2,"sqlite_mutation":2,"jvm":2,"sdk":2,"business_http":16,"post":4,"health":6,"provider":2,"token_reserve":6000,"cost_micro_cny":150000}
PRICE={"checked_date":"2026-10-20","model":MODEL,"input_cny_per_million_bound":4.5,"output_cny_per_million_bound":18.0,
    "basis":"USD_PEAK_0.30_INPUT_1.20_OUTPUT_TIMES_15_GUARD_NOT_FX_OR_INVOICE",
    "sources":["https://api-docs.deepseek.com/quick_start/pricing/","https://api-docs.deepseek.com/guides/tool_calls/"]}
BOUNDARIES={"real_explorer":"REAL_PROVIDER","selection_source":"REAL_EXPLORER_TOOL_CALL",
    "target_sources":{"order-refund":"DETERMINISTIC_ORDER_TARGET","config-java-http":"FIXTURE_SCRIPTED"},
    "issuer_authenticity":"NOT_ESTABLISHED","database_independent_authority":"NOT_ESTABLISHED","independent_reproduction":"NOT_TESTED",
    "WorkSwarm":"NOT_PROVEN","attribution":"CORRELATIONAL_ONLY","H1":"NOT_PROVEN","H3":"NOT_PROVEN","CAUSAL_ADVANTAGE":"NOT_PROVEN","cross_domain_information_gain":"NOT_COMPARABLE"}
NEW_FILES=tuple("runtime/runproof_runtime/effectwitness/"+n+".py" for n in (
    "pge_select_contracts","pge_select_explorer","pge_select_session","pge_select_order_port","pge_select_config_port","pge_select_feedback","pge_select_verify"))+("spikes/rpf-59/probe.py","runtime/tests/test_effectwitness_pge_select.py")
OLD_FILES=tuple("runtime/runproof_runtime/effectwitness/"+n+".py" for n in (
    "orders","contracts","effect_oracle","config_pge_target","config_pge_contracts","config_pge_session","config_live_runtime","config_live_contracts",
    "config_live_external","config_live_verify","config_experiment_adapter","config_experiment_contracts","config_experiment_verify"))+(
    "spikes/rpf-53/probe.py","spikes/rpf-55/probe.py","runtime/runproof_runtime/models.py")
def sources():return {p:hashlib.sha256((ROOT/p).read_bytes().replace(b"\r\n",b"\n")).hexdigest() for p in NEW_FILES+OLD_FILES}
def scoped(path):
    path=Path(path)
    require(path.is_absolute() and path.resolve().is_relative_to(WORK.resolve()) and not any(
        p.is_symlink() or getattr(p,"is_junction",lambda:False)() for p in (path,*path.parents)),"TASK_PATH_SCOPE")
    return path
def trial(domain,run_id,source_sha,java_port=45001,host_port=46001):
    require(domain in DOMAINS and type(run_id) is str and re.fullmatch(r"rpf59-(?:order|config)-[a-f0-9]{16}",run_id),"DOMAIN_OR_RUN")
    require(run_id.startswith("rpf59-order-" if domain==DOMAINS[0] else "rpf59-config-"),"DOMAIN_RUN_MISMATCH")
    require(type(source_sha) is str and re.fullmatch(r"[a-f0-9]{64}",source_sha),"SOURCE_SHA")
    x={"schema":"rpf59-experiment-v1","owner":"rpf-59","domain":domain,"run_id":run_id,"source_sha256":source_sha,
        "candidate_id":"normal" if domain==DOMAINS[0] else "planned-but-inhibited","fault":"none","environment_id":"env-"+run_id,"reset_generation":0}
    if domain==DOMAINS[0]:
        e={"schema":"rpf59-execution-v1","driver":"DETERMINISTIC_ORDER_TARGET","tools":["inspect_order","refund_order"],"provider_requests":0}
        f={"schema":"rpf59-order-effect-v1","order_id":"order-"+run_id,"operation_id":"refund-"+run_id,
            "authority_id":"authority-"+run_id,"amount_minor":2500,"currency":"CNY","authority":"SQLITE_READ_ONLY_RECEIPT_READER"}
    else:
        require(type(java_port) is int and type(host_port) is int and 1024<=java_port<=65535 and 1024<=host_port<=65535 and java_port!=host_port,"PORTS")
        e={"schema":"rpf59-execution-v1","owner":"rpf-59","agent_id":"target-"+run_id,"role":"TARGET_FIXTURE","model_source":"FIXTURE_SCRIPTED",
            "framework":{"name":"pydantic-ai-slim","version":"2.57.0","openai_version":"3.35.1","identity":pinned_sdk_fields()},
            "tools":list(TOOLS),"agent_instructions":AGENT_INSTRUCTIONS,"task_prompt":TASK_PROMPT,"tool_help":TOOL_HELP,
            "service":{"host":"127.0.0.1","port":java_port},"agent_host":{"host":"127.0.0.1","port":host_port},"release_authority":"NOT_HELD_BY_AGENT"}
        f={"schema":"rpf59-config-effect-v1","app":"rpf53app"+run_id.replace("-",""),"env":"rpf53local"+run_id.replace("-",""),
            "key":"rpf53.item."+run_id,"initial_state":"ABSENT","initial_value":"rpf53-v1","required_value":"rpf53-v2","initial_version":1,"required_version":2,"history_versions":[2,1]}
        x.update(fault_plan={"planned":True,"enabled":False,"kind":"LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200","tool":"update_config_v2",
            "max_activations":1,"channel":"EXPLICIT_TOOL_DELIVERY_ERROR","after_fault":"STOP_WRITES_READ_ONLY_RECONCILE"},
            source={"commit":SOURCE_COMMIT,"manifest_sha256":SOURCE_MANIFEST_SHA256,"jar_sha256":SOURCE_JAR_SHA256,"jar_bytes":SOURCE_JAR_BYTES,
                "task_jar":".local/rpf-59/jar/config-center-server-1.0.0.jar"},runtime_source_sha256=source_sha)
    return {"schema":"rpf59-domain-contracts-v1","execution":e,"effect":f,"experiment":x}
def validate_trial(c):
    require(type(c) is dict and set(c)=={"schema","execution","effect","experiment"},"TRIAL_FIELDS")
    x,e=c["experiment"],c["execution"]
    expected=trial(x["domain"],x["run_id"],x["source_sha256"],e.get("service",{}).get("port",45001),e.get("agent_host",{}).get("port",46001))
    require(c==expected,"FROZEN_DOMAIN_CONTRACT")
def domain_for(candidate):
    require(candidate in CANDIDATES,"CANDIDATE_ALLOWLIST")
    return dict(zip(CANDIDATES,DOMAINS))[candidate]

def plan(session_id,slots,source_map):
    require(re.fullmatch(r"rpf59-session-[a-f0-9]{16}",session_id) is not None and len(slots)==2,"SESSION_ID")
    rounds=[]
    for i,(order_run,config_run,java,host) in enumerate(slots,1):
        rounds.append({"round":i,"candidates":{name:trial(domain_for(name),run,digest(source_map),java,host)
            for name,run in zip(CANDIDATES,(order_run,config_run))}})
    runs=[t["experiment"]["run_id"] for row in rounds for t in row["candidates"].values()]
    require(len(set(runs))==4,"NAMESPACE_REPLAY")
    ports=[r["candidates"][CANDIDATES[1]]["execution"][kind]["port"] for r in rounds for kind in ("service","agent_host")]
    require(len(set(ports))==4,"PORT_REPLAY")
    return {"schema":"rpf59-select-session-v1","owner":"rpf-59","base":BASE,"branch":BRANCH,"session_id":session_id,
        "explorer_id":"rpf59-explorer","catalog":list(CANDIDATES),"limits":LIMITS,"price":PRICE,"source_files":source_map,"boundaries":BOUNDARIES,"rounds":rounds}

def validate_plan(p):
    slots=[]
    for row in p["rounds"]:
        a,b=[row["candidates"][name] for name in CANDIDATES]
        slots.append((a["experiment"]["run_id"],b["experiment"]["run_id"],b["execution"]["service"]["port"],b["execution"]["agent_host"]["port"]))
    require(p==plan(p["session_id"],slots,p["source_files"]),"FROZEN_SESSION")
