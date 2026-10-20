"""RPF-58 sole task entry: offline gates, one cold fixture, one dual-domain run."""
import argparse,hashlib,importlib.util,os,shutil,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_shared_contracts as c,pge_shared_core as core,pge_shared_verify as v,pge_config_port as config
OUT=ROOT/"spikes/rpf-58/rev-2"
SOURCES=set(c.NEW_FILES)|{"runtime/tests/test_effectwitness_pge_shared_core.py"}
EXPORTS={"spikes/rpf-58/rev-2/"+n for n in ("README.md","RESULT.md","cold-fixture-diagnostic.json","session-summary.json","verification-diagnostic.json","cross-domain-portability-evidence.json")}
def once(path,value):
    path=Path(path)
    if path.is_relative_to(c.WORK):c.scoped(path)
    else:c.require(str(path.relative_to(ROOT)).replace("\\","/") in EXPORTS and not config.old._has_link_component(path),"EXPORT_SCOPE")
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as f:f.write(c.canonical(value)+b"\n");f.flush();os.fsync(f.fileno())
def guard(event,args):
    if event=="socket.connect":
        addr=args[1]
        if isinstance(addr,tuple):c.require(addr[0] in ("127.0.0.1","::1","localhost"),"NON_LOOPBACK_FORBIDDEN")
def scope():
    old=config.old
    c.require(Path(old._git("rev-parse","--show-toplevel")).resolve()==ROOT and old._git("rev-parse","HEAD")==c.BASE
        and old._git("branch","--show-current")==c.BRANCH,"GIT_BASE_IDENTITY")
    c.require(old._git("remote","get-url","origin")==old._git("remote","get-url","--push","origin")=="https://github.com/MyKr-YSteinsK/runproof.git","ORIGIN")
    raw=old._git("status","--porcelain=v1","-z",binary=True).decode()
    for row in filter(None,raw.split("\0")):
        status,name=row[:2],row[3:]
        if status=="??" and name=="docs/reviews/":continue
        c.require(((status==" M" and name in SOURCES) or (status=="??" and (name in EXPORTS or name=="spikes/rpf-58/rev-2/"))),"WORKTREE_SCOPE")
    extra=old._git("ls-files","--others","--exclude-standard","--",*sorted(SOURCES),"spikes/rpf-58/rev-2")
    c.require(set(extra.splitlines())<=SOURCES|EXPORTS,"UNAPPROVED_NEW_FILE")
    c.scoped(c.WORK)
    for name in ("preflight","diagnostics","tests","jar","sandboxes","replay"):
        c.scoped(c.WORK/name).mkdir(parents=True,exist_ok=True)
def gate_path():return c.WORK/"preflight"/("offline-"+c.digest(c.sources())+".json")
def identity_path():return c.WORK/"preflight"/("identity-"+c.digest(c.sources())+".json")
def preflight():
    scope();c.require(not identity_path().exists(),"IDENTITY_ALREADY_FROZEN")
    source=config.old._verify_source_bundle();java=config.old._java_identity()
    task=core.TaskGuard(c.WORK/"task-intents");reservation=task.reserve("METADATA",c.digest(c.sources()))
    try:sdk=config.sdk_identity_direct()
    except Exception as exc:task.result(reservation,"FAIL",error=getattr(exc,"code",type(exc).__name__));raise
    if not config.JAR.exists():
        with config.old.SOURCE_JAR.open("rb") as src,config.JAR.open("xb") as dst:shutil.copyfileobj(src,dst)
    c.require(config.JAR.stat().st_size==c.SOURCE_JAR_BYTES and config.old._sha_file(config.JAR)==c.SOURCE_JAR_SHA256,"TASK_JAR_IDENTITY")
    value={"sources":c.sources(),"verifier":v.identity(),"sdk":sdk,"java":java,"source":source,"provider":0,"jvm":0}
    once(identity_path(),value);task.result(reservation,"PASS",identity_sha256=c.digest(value));return {"status":"PASS","provider":0,"jvm":0}
def tests_module():
    spec=importlib.util.spec_from_file_location("rpf58_pure_controls",ROOT/"runtime/tests/test_effectwitness_pge_shared_core.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def offline():
    scope();folder=c.WORK/"tests"/("offline-"+uuid.uuid4().hex);folder.mkdir()
    env=config.old._sdk_env(folder)
    p=subprocess.run([sys.executable,"-B","-m","unittest","runtime.tests.test_effectwitness_pge_shared_core","-v"],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
    (folder/"unittest.log").write_bytes(p.stdout);c.require(p.returncode==0,"OFFLINE_TEST_FAILURE")
    tests=tests_module();controls=tests.controls(c.canonical(v.seal(tests.synthetic_payload())),folder/"controls")
    result={"status":"PASS","sources":c.sources(),"verifier":v.identity(),"controls":controls,"provider":0,"java":0,"sqlite_business_trials":0}
    once(gate_path(),result);return result
def frozen_gate():
    scope();gate=c.strict_json(gate_path().read_bytes());identity=c.strict_json(identity_path().read_bytes())
    c.require(gate["status"]=="PASS" and gate["sources"]==identity["sources"]==c.sources() and gate["verifier"]==identity["verifier"]==v.identity(),"FROZEN_SOURCE_GATE")
    return identity
def fixture():
    identity=frozen_gate()
    contract=c.trial(c.DOMAINS[1],"rpf58r2-config-"+uuid.uuid4().hex[:16],c.digest(c.sources()),config.old._free_port(),config.old._free_port())
    result=config.cold_fixture(contract,identity["sdk"])
    once(OUT/"cold-fixture-diagnostic.json",result)
    return {"status":result["status"],"provider":0,"java":0,"attempt":result["capture"]["attempt"]}
def controlled_run():
    frozen_gate();task=core.TaskGuard(c.WORK/"task-intents");task.read()
    passes=[r for r in task.rows if r["kind"]=="COLD" and r["status"]=="PASS"]
    c.require(len(passes)==1 and passes[0]["source_sha256"]==c.digest(c.sources()),"CURRENT_COLD_PASS_REQUIRED")
    cold=c.strict_json((c.WORK/"preflight"/f"cold-attempt-{passes[0]['ordinal']:02}"/"result.json").read_bytes())
    c.require(cold["status"]=="PASS" and cold["source_files"]==c.sources(),"NEW_COLD_FIXTURE_REQUIRED")
    config.validate_cold_capture(cold["capture"])
    c.require(cold["capture"]["source_kind"]=="REAL_SDK_COLD_FIXTURE" and passes[0]["detail"]=={"capture_sha256":c.digest(cold["capture"])},"COLD_TASK_BINDING")
    plan=c.plan("rpf58r2-session-"+uuid.uuid4().hex[:16],["rpf58r2-order-"+uuid.uuid4().hex[:16],"rpf58r2-config-"+uuid.uuid4().hex[:16]],
        (config.old._free_port(),config.old._free_port()),c.sources())
    once(c.WORK/"preflight/session-plan.json",plan)
    session_reservation=task.reserve("SESSION",c.digest(c.sources()),plan_sha256=c.digest(plan),cold_capture_sha256=c.digest(cold["capture"]))
    once(c.WORK/"preflight/started.json",{"session_id":plan["session_id"],"source_sha256":c.digest(c.sources()),"pid":os.getpid()})
    ledger=core.Ledger(c.WORK/"ledger",plan,create=True);session=core.SharedSession(ledger)
    try:
        for contract in plan["trials"]:
            row=session.execute_trial(contract);once(c.WORK/"replay"/(contract["experiment"]["domain"]+".json"),row)
        state=ledger.read()
        task.result(session_reservation,"PASS",ledger_sha256=c.digest(state),rows_sha256=c.digest(session.rows))
        payload={"source_kind":"BOTH_REAL_CONTROLLED","plan":plan,"rows":session.rows,"ledger":state,
            "ledger_chain_sha256":c.digest(ledger.chain),"boundaries":c.BOUNDARIES,"claim":v.CLAIM,"cold_fixture":cold["capture"],"task_intents":task.read()}
        raw=c.canonical(v.seal(payload))+b"\n";verdict=v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
        once(c.WORK/"replay/candidate.json",c.strict_json(raw))
        controls=tests_module().controls(raw,c.WORK/"replay/issuance-controls")
        once(OUT/"verification-diagnostic.json",{"status":"PASS","sources":c.sources(),"verifier_identity":v.identity(),"raw_sha256":hashlib.sha256(raw).hexdigest(),"controls":controls})
        once(OUT/"session-summary.json",{"status":"COMPLETE","session_id":plan["session_id"],"verdict":verdict,
            "domains":[{"domain":row["contract"]["experiment"]["domain"],"run_id":row["contract"]["experiment"]["run_id"],"feedback":row["feedback"]} for row in session.rows],
            "raw_sha256":hashlib.sha256(raw).hexdigest()})
        once(OUT/"cross-domain-portability-evidence.json",c.strict_json(raw));return verdict
    except Exception as e:
        once(OUT/"session-summary.json",{"status":"PARTIAL","completed_domains":len(session.rows),"error":getattr(e,"code",type(e).__name__),"ledger":ledger.read(),"no_full_certificate":True})
        raise
def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=("preflight","offline","fixture","controlled-run","verify-offline"));p.add_argument("--sha256");a=p.parse_args()
    sys.addaudithook(guard)
    try:
        if a.mode=="verify-offline":result=v.verify_bytes((OUT/"cross-domain-portability-evidence.json").read_bytes(),a.sha256)
        else:result={"preflight":preflight,"offline":offline,"fixture":fixture,"controlled-run":controlled_run}[a.mode]()
        print(c.canonical(result).decode());return 0
    except Exception as e:print(c.canonical({"status":"STOPPED","error":getattr(e,"code",type(e).__name__)}).decode());return 1
if __name__=="__main__":raise SystemExit(main())
