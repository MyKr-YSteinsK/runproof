"""RPF-59 Java/SDK Fixture port; no Provider credentials or network permitted.

Domain-specific scene predicates are a reviewed copy of RPF-55 verify_scene,
bound to the new contract validator; shared orchestration lives in shared_core.
"""
import ast,hashlib,importlib.util,os,secrets,shutil,subprocess,sys,time
from pathlib import Path
from . import pge_select_contracts as c,config_live_contracts as oldc
from .pge_select_contracts import ROOT,WORK,canonical,digest,strict_json,require,scoped,validate_trial
from .config_pge_contracts import CANDIDATES
from .config_live_contracts import SOURCE_JAR_SHA256,SDK_CORE_SHA256
from .config_experiment_verify import pinned_sdk_fields
from .config_live_runtime import ConfigLiveHttp,ConfigLiveBusiness,ConfigLiveMemoryBackend,ProviderLedger,_http_contract,_api_response,_valid_item
from .config_live_verify import _history
from .config_pge_target import TargetHost as StableHost
from .config_pge_session import Journal as MemoryJournal
JAR=WORK/"jar/config-center-server-1.0.0.jar"
spec=importlib.util.spec_from_file_location("rpf59_pinned_helpers",ROOT/"spikes/rpf-55/probe.py")
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
    suppressed = candidate == CANDIDATES[2]
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
    require(len(activations) == int(suppressed) and len(inhibits) == int(candidate == CANDIDATES[1]), "ACTIVATION_COUNT")
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
    from .pge_select_session import TaskGuard
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
        capture={"schema":"rpf59-cold-capture-v1","source_kind":"REAL_SDK_COLD_FIXTURE","attempt":ordinal,"source_files":c.sources(),
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
        and value["schema"]=="rpf59-cold-capture-v1" and value["source_kind"] in ("REAL_SDK_COLD_FIXTURE","SYNTHETIC_TEST_ONLY")
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

def execute(contract,total):
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
    return {"schema":"rpf59-config-trial-v1","domain":"config-java-http","source_kind":"REAL_LOCAL_SDK_FIXTURE_JAVA_HTTP","executor_pid":os.getpid(),"scene":scene}

def verify(contract,evidence):
    validate_trial(contract)
    require(set(evidence)=={"schema","domain","source_kind","executor_pid","scene"} and evidence["schema"]=="rpf59-config-trial-v1"
        and evidence["domain"]=="config-java-http" and evidence["source_kind"] in ("REAL_LOCAL_SDK_FIXTURE_JAVA_HTTP","SYNTHETIC_TEST_ONLY"),"CONFIG_EVIDENCE_FIELDS")
    scene=evidence["scene"];require(scene["contracts"]==contract,"CONFIG_CONTRACT_BINDING")
    if evidence["source_kind"]!="SYNTHETIC_TEST_ONLY":
        require(type(evidence["executor_pid"]) is int and evidence["executor_pid"]>0
            and all(not r["response_id"].startswith("synthetic") for r in scene["completions"]),"CONFIG_REAL_ORIGIN")
    _verify_scene(scene,"planned-but-inhibited",contract["experiment"]["source_sha256"])
    return {"domain":"config-java-http","outcome":"SATISFIED","authority":"SAME_SERVICE_READ_ONLY_HTTP","history":"V2_HISTORY_2_1"}
