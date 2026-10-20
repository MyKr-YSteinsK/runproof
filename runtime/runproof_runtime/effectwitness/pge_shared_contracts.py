"""RPF-58 frozen contracts. Static domains, no executable/path/URL registry."""
from pathlib import Path
import hashlib,re
from .config_live_contracts import (canonical,digest,strict_json,require,TOOLS,AGENT_INSTRUCTIONS,TASK_PROMPT,TOOL_HELP,
    SOURCE_COMMIT,SOURCE_MANIFEST_SHA256,SOURCE_JAR_SHA256,SOURCE_JAR_BYTES)
from .config_experiment_verify import pinned_sdk_fields
ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/".local/rpf-58-rev2"
BASE="1af24d94610c4e5dcf36d65c182add172e1401d2"
BRANCH="codex/rpf-58-rev2-cross-domain-controlled-closeout"
DOMAINS=("order-refund","config-java-http")
LIMITS={"trial":2,"order_trial":1,"config_trial":1,"sqlite_mutation":1,"jvm":1,"sdk":1,"business_http":12,"post":2,"health":3,"provider":0}
BOUNDARIES={"real_explorer":"NOT_EXECUTED_IN_THIS_PLAN","selection_source":"DETERMINISTIC_PORTABILITY_DRIVER",
    "issuer_authenticity":"NOT_ESTABLISHED","database_independent_authority":"NOT_ESTABLISHED",
    "independent_reproduction":"NOT_TESTED","WorkSwarm":"NOT_PROVEN","attribution":"CORRELATIONAL_ONLY",
    "H1":"NOT_PROVEN","H3":"NOT_PROVEN","cross_domain_information_gain":"NOT_COMPARABLE"}
NEW_FILES=tuple("runtime/runproof_runtime/effectwitness/"+n+".py" for n in (
    "pge_shared_contracts","pge_shared_core","pge_shared_feedback","pge_shared_verify","pge_order_port","pge_config_port"))+("spikes/rpf-58/probe.py",)
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
    require(domain in DOMAINS and type(run_id) is str and re.fullmatch(r"rpf58r2-(?:order|config)-[a-f0-9]{16}",run_id),"DOMAIN_OR_RUN")
    require(run_id.startswith("rpf58r2-order-" if domain==DOMAINS[0] else "rpf58r2-config-"),"DOMAIN_RUN_MISMATCH")
    require(type(source_sha) is str and re.fullmatch(r"[a-f0-9]{64}",source_sha),"SOURCE_SHA")
    x={"schema":"rpf58-experiment-v2","owner":"rpf-58-rev2","domain":domain,"run_id":run_id,"source_sha256":source_sha,
        "candidate_id":"normal" if domain==DOMAINS[0] else "planned-but-inhibited","fault":"none","environment_id":"env-"+run_id,"reset_generation":0}
    if domain==DOMAINS[0]:
        e={"schema":"rpf58-execution-v2","driver":"DETERMINISTIC_ORDER_TARGET","tools":["inspect_order","refund_order"],"provider_requests":0}
        f={"schema":"rpf58r2-order-effect-v2","order_id":"order-"+run_id,"operation_id":"refund-"+run_id,
            "authority_id":"authority-"+run_id,"amount_minor":2500,"currency":"CNY","authority":"SQLITE_READ_ONLY_RECEIPT_READER"}
    else:
        require(type(java_port) is int and type(host_port) is int and 1024<=java_port<=65535 and 1024<=host_port<=65535 and java_port!=host_port,"PORTS")
        e={"schema":"rpf58-execution-v2","owner":"rpf-58-rev2","agent_id":"target-"+run_id,"role":"TARGET_FIXTURE","model_source":"FIXTURE_SCRIPTED",
            "framework":{"name":"pydantic-ai-slim","version":"2.57.0","openai_version":"3.35.1","identity":pinned_sdk_fields()},
            "tools":list(TOOLS),"agent_instructions":AGENT_INSTRUCTIONS,"task_prompt":TASK_PROMPT,"tool_help":TOOL_HELP,
            "service":{"host":"127.0.0.1","port":java_port},"agent_host":{"host":"127.0.0.1","port":host_port},"release_authority":"NOT_HELD_BY_AGENT"}
        f={"schema":"rpf58r2-config-effect-v2","app":"rpf53app"+run_id.replace("-",""),"env":"rpf53local"+run_id.replace("-",""),
            "key":"rpf53.item."+run_id,"initial_state":"ABSENT","initial_value":"rpf53-v1","required_value":"rpf53-v2","initial_version":1,"required_version":2,"history_versions":[2,1]}
        x.update(fault_plan={"planned":True,"enabled":False,"kind":"LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200","tool":"update_config_v2",
            "max_activations":1,"channel":"EXPLICIT_TOOL_DELIVERY_ERROR","after_fault":"STOP_WRITES_READ_ONLY_RECONCILE"},
            source={"commit":SOURCE_COMMIT,"manifest_sha256":SOURCE_MANIFEST_SHA256,"jar_sha256":SOURCE_JAR_SHA256,"jar_bytes":SOURCE_JAR_BYTES,
                "task_jar":".local/rpf-58-rev2/jar/config-center-server-1.0.0.jar"},runtime_source_sha256=source_sha)
    return {"schema":"rpf58-domain-contracts-v2","execution":e,"effect":f,"experiment":x}
def validate_trial(c):
    require(type(c) is dict and set(c)=={"schema","execution","effect","experiment"},"TRIAL_FIELDS")
    x,e=c["experiment"],c["execution"]
    expected=trial(x["domain"],x["run_id"],x["source_sha256"],e.get("service",{}).get("port",45001),e.get("agent_host",{}).get("port",46001))
    require(c==expected,"FROZEN_DOMAIN_CONTRACT")
def plan(session_id,runs,ports,source_map):
    require(re.fullmatch(r"rpf58r2-session-[a-f0-9]{16}",session_id) is not None and len(runs)==2,"SESSION_ID")
    return {"schema":"rpf58-shared-session-v2","owner":"rpf-58-rev2","base":BASE,"branch":BRANCH,"session_id":session_id,
        "selection_source":"DETERMINISTIC_PORTABILITY_DRIVER","limits":LIMITS,"source_files":source_map,"boundaries":BOUNDARIES,
        "trials":[trial(d,r,digest(source_map),*ports) for d,r in zip(DOMAINS,runs)]}
def validate_plan(p):
    config=p["trials"][1]["execution"]
    expected=plan(p["session_id"],[t["experiment"]["run_id"] for t in p["trials"]],(config["service"]["port"],config["agent_host"]["port"]),p["source_files"])
    require(p==expected,"FROZEN_SESSION")
