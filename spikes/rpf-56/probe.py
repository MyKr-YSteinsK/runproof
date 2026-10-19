"""RPF-56: offline gates, independent SDK fixtures, one live two-role session."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import types
import uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import config_pge_contracts as c, config_pge_verify as v, config_pge_explorer as explorer
from runtime.runproof_runtime.effectwitness.config_pge_session import TotalLedger,Journal,feedback
from runtime.runproof_runtime.effectwitness.config_pge_target import TargetHost,TargetLedger,BusinessHttp
from runtime.runproof_runtime.effectwitness.config_live_runtime import ConfigLiveBusiness,ConfigLiveMemoryBackend,ProviderLedger
WORK=ROOT/".local/rpf-56"
OUT=ROOT/"spikes/rpf-56"
JAR=WORK/"jar/config-center-server-1.0.0.jar"
spec=importlib.util.spec_from_file_location("rpf56_readonly_sdk_helpers",ROOT/"spikes/rpf-55/probe.py")
h55=importlib.util.module_from_spec(spec);spec.loader.exec_module(h55)
old=h55.old
# Reuse the reviewed SDK inspection code with NEW task-only cwd/env roots.
# Do not call old preflight/scenario or access historical task markers/ledgers.
inspect_sdk=types.FunctionType(h55.sdk_identity_direct.__code__,{**vars(h55),"WORK":WORK},"rpf56_inspect_sdk")
SOURCE_NEW={"runtime/runproof_runtime/effectwitness/"+name+".py" for name in (
    "config_pge_contracts","config_pge_explorer","config_pge_target","config_pge_session","config_pge_verify")}
SOURCE_NEW|={"runtime/tests/test_effectwitness_config_pge.py","spikes/rpf-56/probe.py"}
EXPORTS={"spikes/rpf-56/"+n for n in ("README.md","RESULT.md","session-summary.json","verification-diagnostic.json","config-pge-evidence.json")}

def once(path,value):
    c.require(path.resolve().is_relative_to(WORK.resolve()) or str(path.relative_to(ROOT)).replace("\\","/") in EXPORTS,"OUTPUT_SCOPE")
    c.require(not old._has_link_component(path),"OUTPUT_LINK")
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as stream:
        stream.write(c.canonical(value)+b"\n");stream.flush();os.fsync(stream.fileno())

def status_check():
    raw=old._git("status","--porcelain=v1","-z",binary=True).decode()
    for row in filter(None,raw.split("\0")):
        status,name=row[:2],row[3:]
        if status=="??" and name=="docs/reviews/":continue
        c.require(status=="??" and (name in SOURCE_NEW|EXPORTS or name=="spikes/rpf-56/"),"WORKTREE_OR_INDEX_SCOPE")
    extras=old._git("ls-files","--others","--exclude-standard","--","spikes/rpf-56")
    c.require(all(name in SOURCE_NEW|EXPORTS for name in extras.splitlines()),"EXTRA_EXPORT")

def preflight():
    c.require(old._git("rev-parse","HEAD")==c.BASE and old._git("branch","--show-current")==c.BRANCH
        and Path(old._git("rev-parse","--show-toplevel")).resolve()==ROOT,"REPO_BASE")
    c.require(old._git("remote","get-url","origin")=="https://github.com/MyKr-YSteinsK/runproof.git"
        and old._git("remote","get-url","--push","origin")=="https://github.com/MyKr-YSteinsK/runproof.git","ORIGIN")
    status_check()
    for path in (WORK,*WORK.parents):c.require(not old._is_link(path),"TASK_ROOT_LINK")
    WORK.mkdir(exist_ok=True)
    for name in ("preflight","fixture","scenarios","jar","tests","diagnostics","replay","quarantine"):
        c.require(not old._has_link_component(WORK/name),"TASK_DIRECTORY_LINK")
        (WORK/name).mkdir(exist_ok=True)
    source=old._verify_source_bundle()
    try:sdk=inspect_sdk()
    except OSError as exc:
        if getattr(exc,"winerror",None)==4551:c.require(False,"DIRECT_CPYTHON_APP_CONTROL_BLOCKED_4551")
        raise
    java=old._java_identity()
    if not JAR.exists():
        with old.SOURCE_JAR.open("rb") as src,JAR.open("xb") as dst:shutil.copyfileobj(src,dst)
    c.require(JAR.stat().st_size==66981576 and old._sha_file(JAR)==c.SOURCE_JAR_SHA256,"TASK_JAR")
    return {"base":c.BASE,"source_files":v.source_identity(),"verifier_identity":v.verifier_identity(),"sdk":sdk,"java":java,"config_source":source,"price":c.PRICE}

def run_sdk(host,contracts,sdk,folder,*,fixture):
    direct=h55.resolve_direct_python(sdk)
    scratch=folder/"sdk-scratch";scratch.mkdir()
    host.start()
    config={"port":host.port,"token":host.token,"write_root":str(scratch),"sdk_readonly_path":str(old.SDK_SITE.resolve()),
        "sdk_site_root_binding_sha256":sdk["sdk_site_root_binding_sha256"],"python_runtime_mapping_sha256":sdk["python_runtime_mapping_sha256"],
        "instructions":c.AGENT_INSTRUCTIONS,"task_prompt":c.TASK_PROMPT,"model":"rpf53-fixture-only" if fixture else c.MODEL,
        "max_runtime_seconds":180,"fixture":fixture}
    proc=None;thread=None
    try:
        proc=subprocess.Popen([str(direct),"-I","-B",str(ROOT/"runtime/runproof_runtime/effectwitness/config_live_external.py")],
            cwd=scratch,env=old._sdk_env(scratch),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        stdout,stderr=proc.communicate(c.canonical(config),timeout=180)
        report=c.strict_json(stdout)
        result={"popen_pid":proc.pid,"ready":host.runtime,"report":report,"returncode":proc.returncode,"stderr_bytes":len(stderr)}
        if host.activated:host.journal.add("SDK_ERROR_OBSERVED",returncode=proc.returncode,status=report.get("status"),error_type=report.get("error_type"))
        return result
    finally:
        if proc is not None and proc.poll() is None:proc.kill();proc.communicate(timeout=10)
        thread=host._thread;host.close()
        c.require(thread is None or not thread.is_alive(),"HOST_THREAD_CLEANUP")

def fixture(base,candidate):
    c.require(candidate in c.CANDIDATES and len(list((WORK/"fixture").glob("*/started.json")))<3,"FIXTURE_LIMIT")
    gate=c.strict_json((WORK/"preflight/tier0-pass.json").read_bytes())
    c.require(gate["source_files"]==base["source_files"] and gate["verifier_identity"]==base["verifier_identity"],"TIER0_REQUIRED")
    folder=WORK/"fixture"/candidate;folder.mkdir()
    contracts=c.trial_contract(candidate,"56"+uuid.uuid4().hex[:16],old._free_port(),old._free_port(),c.digest(base["source_files"]),h55.identity_fields(base["sdk"]),fixture=True)
    once(folder/"started.json",{"contracts":contracts,"runner_pid":os.getpid(),"source_files":base["source_files"]})
    journal=Journal(folder/"events.jsonl",contracts["experiment"]["run_id"])
    host=TargetHost(contracts,ProviderLedger.fixture_only(journal.run_id),ConfigLiveMemoryBackend(),journal,fixture=True)
    result=run_sdk(host,contracts,base["sdk"],folder,fixture=True)
    suppressed=candidate==c.CANDIDATES[2]
    checks={"ready_pid":host.runtime is not None and host.runtime["pid"]==result["popen_pid"],
        "status":result["report"]["status"]==("SDK_ERROR" if suppressed else "COMPLETED"),
        "tool_calls":len(host.tool_trace)==3,"returns":[x["returned_in_request"] for x in host.tool_trace]==([2,3,None] if suppressed else [2,3,4]),
        "completions":len(host.provider_responses)==(3 if suppressed else 4),"guard":result["report"].get("guard_denials")==[],
        "inhibited":sum(e["kind"]=="FAULT_INHIBITED" for e in journal.events)==int(candidate==c.CANDIDATES[1]),
        "suppressed_once":sum(e["kind"]=="SUCCESS_WITHHELD" for e in journal.events)==int(suppressed),
        "port_closed":old._port_closed(contracts["execution"]["agent_host"]["port"]),"stderr":result["stderr_bytes"]==0}
    once(folder/"result.json",{"candidate":candidate,"source_files":base["source_files"],"verifier_identity":base["verifier_identity"],
        "runner_pid":os.getpid(),"sdk":result,"events":journal.events,"tool_trace":host.tool_trace,"completions":host.provider_responses,"checks":checks})
    c.require(all(checks.values()),"FIXTURE_FAILED")
    return {"status":"PASS","candidate":candidate,"runner_pid":os.getpid(),"java":0,"provider":0}

def trial(base,round_index,candidate,key):
    plan=c.strict_json((WORK/"preflight/session-plan.json").read_bytes());c.validate_plan(plan)
    c.require(plan["source_files"]==base["source_files"],"SOURCE_DRIFT")
    total=TotalLedger(WORK/"ledger",plan)
    contracts=plan["rounds"][round_index-1]["candidates"][candidate]
    folder=WORK/"scenarios"/str(round_index);folder.mkdir()
    total.reserve_trial(contracts["experiment"]["run_id"])
    once(folder/"started.json",{"contracts":contracts,"source_files":base["source_files"],"verifier_identity":base["verifier_identity"],"runner_pid":os.getpid(),"round":round_index})
    journal=Journal(folder/"events.jsonl",contracts["experiment"]["run_id"])
    deadline=time.monotonic()+1200
    client=BusinessHttp(contracts,secrets.token_urlsafe(32),journal,total,deadline)
    ledger=TargetLedger(folder/"target-ledger.json",journal.run_id,total,round_index)
    host=TargetHost(contracts,ledger,ConfigLiveBusiness(contracts,client),journal,api_key=key)
    port=contracts["execution"]["service"]["port"]
    temp=folder/"java-tmp";temp.mkdir()
    args=[str(old.JAVA),f"-Djava.io.tmpdir={temp}","-jar",str(JAR),"--spring.profiles.active=local","--server.address=127.0.0.1",f"--server.port={port}",
        "--security.api-keys[0].key=${CONFIG_CENTER_API_KEY}","--security.api-keys[0].app="+contracts["effect"]["app"],"--security.api-keys[0].env="+contracts["effect"]["env"]]
    environment={"source_level":"REAL_JAVA_H2_LOCAL_SIMULATION","authority":"SAME_SERVICE_READ_ONLY_HTTP","java_pid":None,
        "jar_sha256":old._sha_file(JAR),"jar_bytes":JAR.stat().st_size,"listener_owned":False,"jar_command_verified":False,"health":[],"cleanup":{}}
    proc=log=sdk=None
    try:
        c.require(v.source_identity()==base["source_files"] and environment["jar_sha256"]==c.SOURCE_JAR_SHA256 and old._port_closed(port),"SOURCE_JAR_OR_PORT")
        proc=subprocess.Popen(args,cwd=folder,env=old._java_env(temp,client._api_key),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
        environment["java_pid"]=proc.pid
        log=old._RedactedJavaLog(proc,client._api_key.encode("ascii"))
        argv=old._split_windows_command_line(old._actual_process_command_line(proc.pid))
        environment["jar_command_verified"]=old._argv_jar_path_matches(argv,JAR,WORK)
        c.require(environment["jar_command_verified"],"JAVA_ARGV")
        health=[]
        c.require(old._wait_for_java(proc,port,log,deadline,health),"JAVA_READINESS")
        once(folder/"health-raw.json",health);environment["health"]=h55.health_projection(health)
        environment["listener_owned"]=old._listener_owned(proc.pid,port)
        c.require(environment["listener_owned"] and not old._external_connections(proc.pid),"JAVA_NETWORK")
        c.require(client.initial_state_valid(),"INITIAL_STATE")
        sdk=run_sdk(host,contracts,base["sdk"],folder,fixture=False)
        if host.activated:
            c.require(sdk["report"]["status"]=="SDK_ERROR","SUPPRESSION_OBSERVATION")
            client.final_readback(reconcile=True);client.request("final_list")
        else:
            c.require(sdk["report"]["status"]=="COMPLETED","TARGET_NOT_COMPLETED")
            client.final_readback()
        c.require(not old._external_connections(proc.pid),"JAVA_EXTERNAL_CONNECTION")
    finally:
        thread=host._thread;host.close()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if log is not None:log.close(folder/"java-redacted.log")
        client._api_key=None;host.api_key=None
        environment["cleanup"]={"java_exited":proc is not None and proc.poll() is not None,"java_port_closed":old._port_closed(port),
            "sdk_exited":sdk is not None,"host_port_closed":old._port_closed(contracts["execution"]["agent_host"]["port"]),
            "host_thread_stopped":thread is None or not thread.is_alive(),"local_key_released":True}
        once(folder/"raw.json",{"contracts":contracts,"http":client.observations,"events":journal.events,"tool_trace":host.tool_trace,
            "completions":host.provider_responses,"sdk":sdk,"environment":environment,"target_requests":ledger.data["requests"]})
    suppressed=host.activated
    result={"contracts":contracts,"contracts_sha256":c.digest(contracts),"http":client.observations,"events":journal.events,
        "tool_trace":host.tool_trace,"completions":host.provider_responses,"sdk":sdk,"environment":environment,"target_requests":ledger.data["requests"],
        "fault":{"planned":candidate!="normal","triggered":suppressed,"observed":suppressed and sdk["report"]["status"]=="SDK_ERROR",
            "channel":"EXPLICIT_TOOL_DELIVERY_ERROR" if suppressed else "NONE"},
        "outcome":{"agent_failure":"NOT_DETERMINED","platform_error":"EXPECTED_TOOL_DELIVERY_ERROR" if suppressed else "NONE",
            "contract_outcome":"SATISFIED","business_violation":"NOT_PROVEN","target_ack":"UNKNOWN_OUTCOME" if suppressed else "RECEIVED",
            "read_only_reconcile":"CONFIRMED_V2" if suppressed else "NOT_REQUIRED"}}
    v.verify_trial(result);once(folder/"verified-trial.json",result)
    return {"status":"PASS","round":round_index,"runner_pid":os.getpid()}

def live(base):
    tier0=c.strict_json((WORK/"preflight/tier0-pass.json").read_bytes())
    c.require(tier0["source_files"]==base["source_files"] and tier0["verifier_identity"]==base["verifier_identity"],"TIER0_REQUIRED")
    fixtures=[c.strict_json((WORK/"fixture"/name/"result.json").read_bytes()) for name in c.CANDIDATES]
    c.require(len({r["runner_pid"] for r in fixtures})==3 and all(all(r["checks"].values()) and r["source_files"]==base["source_files"] for r in fixtures),"THREE_COLD_FIXTURES_REQUIRED")
    c.require(c.strict_json((WORK/"preflight/official-price-reviewed.json").read_bytes())==c.PRICE,"PRICE_REVIEW_REQUIRED")
    key=os.environ.get("DEEPSEEK_API_KEY","")
    c.require(bool(key),"DEEPSEEK_KEY_UNAVAILABLE")
    slots=[("56"+uuid.uuid4().hex[:16],old._free_port(),old._free_port()) for _ in range(2)]
    plan=c.session_plan("rpf56-session-"+uuid.uuid4().hex[:16],slots,base["source_files"],h55.identity_fields(base["sdk"]))
    once(WORK/"preflight/session-plan.json",plan)
    total=TotalLedger(WORK/"ledger",plan,create=True)
    once(WORK/"preflight/session-started.json",{"session_id":plan["session_id"],"plan_sha256":c.digest(plan),"source_files":base["source_files"],"verifier_identity":base["verifier_identity"],"runner_pid":os.getpid()})
    journal=Journal(WORK/"session-events.jsonl",plan["session_id"])
    messages=explorer.initial_messages();seen=set();rounds=[]
    try:
        for index in (1,2):
            body=explorer.body_for(messages)
            event=journal.add("PROVIDER_INPUT_FROZEN",round=index,body_sha256=c.digest(body))
            data,attempt=explorer.request(body,total,index,key)
            call=explorer.parse_selection(data,seen);seen.add(call["id"]);total.selection(attempt,call)
            candidate=c.strict_json(call["function"]["arguments"].encode())["candidate_id"]
            env=old._sdk_env(WORK/"diagnostics");env["DEEPSEEK_API_KEY"]=key
            proc=subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),"trial","--round",str(index),"--candidate",candidate],
                cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1200)
            once(WORK/"diagnostics"/f"trial-runner-{index}.json",{"returncode":proc.returncode,"stdout":proc.stdout.decode("utf-8","replace"),"stderr_bytes":len(proc.stderr)})
            c.require(proc.returncode==0 and not proc.stderr,"TRIAL_RUNNER_FAILED")
            t=c.strict_json((WORK/"scenarios"/str(index)/"verified-trial.json").read_bytes());v.verify_trial(t)
            fb=feedback(t)
            validated=journal.add("FEEDBACK_VALIDATED",round=index,feedback_sha256=c.digest(fb))
            row={"round":index,"request_body":body,"request_sha256":c.digest(body),"explorer_attempt":attempt,"selection":call,
                "trial":t,"feedback":fb,"feedback_sha256":c.digest(fb),"feedback_event_seq":validated["seq"],"input_event_seq":event["seq"]}
            once(WORK/"replay"/f"round-{index}.json",row);rounds.append(row)
            messages += [{"role":"assistant","content":None,"tool_calls":[call]},{"role":"tool","tool_call_id":call["id"],"content":c.canonical(fb).decode()}]
        signatures=[c.digest({"fault":r["trial"]["fault"],"ack":r["trial"]["outcome"]["target_ack"],"effect":"SATISFIED"}) for r in rounds]
        payload={"source_kind":"REAL_EXPLORER_REAL_TARGET_CONFIG_JAVA_HTTP","plan":plan,"plan_sha256":c.digest(plan),"rounds":rounds,
            "events":journal.events,"ledger":total.read(),"limits":c.BOUNDARIES,"research":{"L1":"TWO_REAL_ROLES_EXECUTED",
                "L2":signatures[0]!=signatures[1],"H1":"NOT_PROVEN","information_gain_proxy":int(signatures[0]!=signatures[1])}}
        once(WORK/"replay/candidate-evidence.json",v.seal(payload))
        return issue()
    except Exception as exc:
        once(OUT/"session-summary.json",{"status":"PARTIAL","session_id":plan["session_id"],"completed_rounds":len(rounds),
            "error":getattr(exc,"code",type(exc).__name__),"ledger":total.read(),"no_valid_witness":True})
        raise

def issue():
    raw=(WORK/"replay/candidate-evidence.json").read_bytes();verdict=v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
    require_kind=c.strict_json(raw)["payload"]["source_kind"]
    c.require(require_kind=="REAL_EXPLORER_REAL_TARGET_CONFIG_JAVA_HTTP","REAL_SESSION_REQUIRED")
    spec2=importlib.util.spec_from_file_location("rpf56_controls",ROOT/"runtime/tests/test_effectwitness_config_pge.py")
    tests=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(tests)
    controls=tests.offline_controls(raw,WORK/"replay/final-controls")
    p=c.strict_json(raw)["payload"]
    once(OUT/"verification-diagnostic.json",{"status":"PASS","controls":controls,"verifier_identity":v.verifier_identity(),
        "source_files":p["plan"]["source_files"],"evidence_sha256":hashlib.sha256(raw).hexdigest()})
    once(OUT/"session-summary.json",{"status":"COMPLETE","session_id":p["plan"]["session_id"],"verdict":verdict,
        "rounds":[{"round":r["round"],"candidate":r["feedback"]["candidate_id"],"selection_call_id":r["selection"]["id"],
            "run_id":r["feedback"]["run_id"],"feedback_sha256":r["feedback_sha256"],"fault":r["trial"]["fault"]} for r in p["rounds"]],
        "evidence_sha256":hashlib.sha256(raw).hexdigest(),"limits":c.BOUNDARIES})
    once(OUT/"config-pge-evidence.json",c.strict_json(raw))
    return verdict

def offline():
    """Tier 0 only: deterministic synthetic checks, never SDK/Java/Provider."""
    status_check()
    c.require(not old._has_link_component(WORK),"TASK_ROOT_LINK")
    folder=WORK/"tests"/("tier0-"+uuid.uuid4().hex)
    folder.mkdir(parents=True)
    env={k:os.environ[k] for k in ("SYSTEMROOT","WINDIR","PATH") if k in os.environ}
    env.update(HOME=str(folder),USERPROFILE=str(folder),TEMP=str(folder),TMP=str(folder),PYTHONDONTWRITEBYTECODE="1")
    result=subprocess.run([sys.executable,"-B","-m","unittest","runtime.tests.test_effectwitness_config_pge","-v"],
        cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (folder/"unittest.log").write_bytes(result.stdout)
    c.require(result.returncode==0,"TIER0_UNITTEST_FAILED")
    spec2=importlib.util.spec_from_file_location("rpf56_offline_controls",ROOT/"runtime/tests/test_effectwitness_config_pge.py")
    tests=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(tests)
    controls={name:tests.offline_controls(c.canonical(v.seal(tests.synthetic_payload(choices))),folder/name)
        for name,choices in (("gain",("normal","local-delivery-suppressed")),("no-gain",("normal","normal")))}
    gate={"status":"PASS","scope":"SYNTHETIC_PROTOCOL_ONLY","source_files":v.source_identity(),
        "verifier_identity":v.verifier_identity(),"controls":controls,"sdk_java_provider_started":0}
    once(WORK/"preflight/tier0-pass.json",gate)
    return gate

def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=("offline","preflight","fixture","trial","live","issue"));p.add_argument("--candidate",choices=c.CANDIDATES);p.add_argument("--round",type=int,choices=(1,2));a=p.parse_args()
    try:
        if a.mode=="offline":result=offline()
        elif a.mode=="issue":result=issue()
        else:
            base=preflight()
            if a.mode=="preflight":once(WORK/"preflight/identity.json",base);result={"status":"PASS","provider":0,"java":0}
            elif a.mode=="fixture":result=fixture(base,a.candidate)
            elif a.mode=="trial":result=trial(base,a.round,a.candidate,os.environ.get("DEEPSEEK_API_KEY",""))
            else:result=live(base)
        print(c.canonical(result).decode());return 0
    except Exception as exc:
        print(c.canonical({"status":"STOPPED","error":getattr(exc,"code",type(exc).__name__)}).decode());return 1
if __name__=="__main__":raise SystemExit(main())
