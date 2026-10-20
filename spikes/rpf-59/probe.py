"""RPF-59 owned entry: offline gates, bounded cold SDK, one live session."""
import argparse,hashlib,importlib.util,os,shutil,socket,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_select_contracts as c,pge_select_session as core,pge_select_verify as v,pge_select_config_port as config,pge_select_explorer as explorer
OUT=ROOT/'spikes/rpf-59';ALLOWED_IPS=set()
EXPORTS={'spikes/rpf-59/'+n for n in ('README.md','RESULT.md','verification-diagnostic.json','session-summary.json','protocol-diagnostic.json','cross-domain-selection-evidence.json')}
def once(path,value):
    path=Path(path)
    if path.is_relative_to(c.WORK):c.scoped(path)
    else:c.require(path.relative_to(ROOT).as_posix() in EXPORTS and not config.old._has_link_component(path),'EXPORT_SCOPE')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(c.canonical(value)+b'\n');f.flush();os.fsync(f.fileno())
def guard(event,args):
    if event=='socket.connect':
        addr=args[1]
        if isinstance(addr,tuple):c.require(addr[0] in ('127.0.0.1','::1','localhost') or (addr[0] in ALLOWED_IPS and addr[1]==443),'NETWORK_SCOPE')
def scope():
    old=config.old
    c.require(Path(old._git('rev-parse','--show-toplevel')).resolve()==ROOT and old._git('rev-parse','HEAD')==c.BASE
        and old._git('branch','--show-current')==c.BRANCH,'GIT_BASE_IDENTITY')
    c.require(old._git('remote','get-url','origin')==old._git('remote','get-url','--push','origin')=='https://github.com/MyKr-YSteinsK/runproof.git','ORIGIN')
    raw=old._git('status','--porcelain=v1','-z',binary=True).decode()
    for row in filter(None,raw.split('\0')):
        status,name=row[:2],row[3:]
        if status=='??' and name=='docs/reviews/':continue
        c.require(status=='??' and (name in set(c.NEW_FILES)|EXPORTS or name=='spikes/rpf-59/'),'WORKTREE_SCOPE')
    extra=old._git('ls-files','--others','--exclude-standard','--',*c.NEW_FILES,'spikes/rpf-59')
    c.require(set(extra.splitlines())<=set(c.NEW_FILES)|EXPORTS,'UNAPPROVED_NEW_FILE')
    for name in ('preflight','diagnostics','tests','jar','sandboxes','replay'):c.scoped(c.WORK/name).mkdir(parents=True,exist_ok=True)
def gate_path():return c.WORK/'preflight'/('offline-'+c.digest(c.sources())+'.json')
def identity_path():return c.WORK/'preflight'/('identity-'+c.digest(c.sources())+'.json')
def tests_module():
    spec=importlib.util.spec_from_file_location('rpf59_pure_controls',ROOT/'runtime/tests/test_effectwitness_pge_select.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def offline():
    scope();folder=c.WORK/'tests'/('offline-'+uuid.uuid4().hex);folder.mkdir()
    p=subprocess.run([sys.executable,'-B','-m','unittest','runtime.tests.test_effectwitness_pge_select','-v'],cwd=ROOT,env=config.old._sdk_env(folder),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=360)
    (folder/'unittest.log').write_bytes(p.stdout);c.require(p.returncode==0,'OFFLINE_TEST_FAILURE')
    tests=tests_module();result={}
    for seq in ((0,0),(0,1),(1,0),(1,1)):
        raw=c.canonical(v.seal(tests.synthetic_payload(seq)));result[str(seq)]=tests.controls(raw,folder/('controls-'+''.join(map(str,seq))))
    value={'status':'PASS','sources':c.sources(),'verifier':v.identity(),'controls':result,'provider':0,'jvm':0,'sqlite_business_trials':0}
    once(gate_path(),value);return {'status':'PASS','controls_sequences':4,'semantic_controls_each':len(tests.mutations())}
def preflight():
    scope();c.require(not identity_path().exists(),'IDENTITY_ALREADY_FROZEN')
    source=config.old._verify_source_bundle();java=config.old._java_identity();task=core.TaskGuard(c.WORK/'task-intents')
    n=task.reserve('METADATA',c.digest(c.sources()))
    try:sdk=config.sdk_identity_direct()
    except Exception as exc:task.result(n,'FAIL',error=getattr(exc,'code',type(exc).__name__));raise
    if not config.JAR.exists():
        with config.old.SOURCE_JAR.open('rb') as src,config.JAR.open('xb') as dst:shutil.copyfileobj(src,dst)
    c.require(config.JAR.stat().st_size==c.SOURCE_JAR_BYTES and config.old._sha_file(config.JAR)==c.SOURCE_JAR_SHA256,'JAR_IDENTITY')
    value={'sources':c.sources(),'verifier':v.identity(),'sdk':sdk,'java':java,'source':source,'provider':0,'jvm':0}
    once(identity_path(),value);task.result(n,'PASS',identity_sha256=c.digest(value));return {'status':'PASS','metadata_processes_used':1}
def frozen_gate():
    scope();gate=c.strict_json(gate_path().read_bytes());identity=c.strict_json(identity_path().read_bytes())
    c.require(gate['status']=='PASS' and gate['sources']==identity['sources']==c.sources() and gate['verifier']==identity['verifier']==v.identity(),'FROZEN_SOURCE_GATE')
    return identity
def fixture():
    identity=frozen_gate();contract=c.trial(c.DOMAINS[1],'rpf59-config-'+uuid.uuid4().hex[:16],c.digest(c.sources()),config.old._free_port(),config.old._free_port())
    result=config.cold_fixture(contract,identity['sdk']);return {'status':result['status'],'attempt':result['capture']['attempt'],'provider':0,'jvm':0,'capture_sha256':result['verdict']['capture_sha256']}
def live():
    frozen_gate();task=core.TaskGuard(c.WORK/'task-intents');task.read()
    passes=[r for r in task.rows if r['kind']=='COLD' and r['status']=='PASS'];c.require(len(passes)==1 and passes[0]['source_sha256']==c.digest(c.sources()),'COLD_GATE')
    cold=c.strict_json((c.WORK/'preflight'/f"cold-attempt-{passes[0]['ordinal']:02}"/'result.json').read_bytes())['capture']
    config.validate_cold_capture(cold);c.require(cold['source_kind']=='REAL_SDK_COLD_FIXTURE' and passes[0]['detail']=={'capture_sha256':c.digest(cold)},'COLD_BINDING')
    ports=[]
    while len(ports)<4:
        port=config.old._free_port()
        if port not in ports:ports.append(port)
    slots=[('rpf59-order-'+uuid.uuid4().hex[:16],'rpf59-config-'+uuid.uuid4().hex[:16],*ports[2*i:2*i+2]) for i in range(2)]
    plan=c.plan('rpf59-session-'+uuid.uuid4().hex[:16],slots,c.sources())
    # All free gates have passed before reading the existing configured secret.
    key=os.environ.get('DEEPSEEK_API_KEY','');c.require(bool(key),'EXISTING_PROVIDER_KEY_UNAVAILABLE')
    once(c.WORK/'preflight/session-plan.json',plan)
    n=task.reserve('SESSION',c.digest(c.sources()),plan_sha256=c.digest(plan),cold_capture_sha256=c.digest(cold))
    once(c.WORK/'preflight/started.json',{'session_id':plan['session_id'],'source_sha256':c.digest(c.sources()),'pid':os.getpid(),'started_monotonic_ns':time.monotonic_ns()})
    ledger=core.Ledger(c.WORK/'ledger',plan,create=True);session=core.SharedSession(ledger)
    try:
        for index in (1,2):
            body=explorer.body_for(explorer.messages_for(session.rows))
            once(c.WORK/'replay'/f'round-{index}-request.json',body)
            ALLOWED_IPS.update(row[4][0] for row in socket.getaddrinfo('api.deepseek.com',443,type=socket.SOCK_STREAM))
            try:data,attempt=explorer.request(body,ledger,index,key,shape_writer=lambda obs:once(c.WORK/'replay'/f'round-{index}-observation.json',obs))
            finally:ALLOWED_IPS.clear()
            selection=explorer.parse_selection(data,{r['selection']['id'] for r in session.rows});del data
            row=session.execute_trial(selection,body,ledger.response_observation,attempt)
            once(c.WORK/'replay'/f'round-{index}.json',row)
        key=None;ledger.read()
        task.result(n,'PASS',ledger_chain_sha256=c.digest(ledger.chain),rows_sha256=c.digest(session.rows))
        payload={'source_kind':v.REAL,'claim':v.CLAIM,'plan':plan,'rows':session.rows,'ledger_chain':ledger.chain,'cold_fixture':cold,
            'task_intents':task.read(),'boundaries':c.BOUNDARIES,'research':v.research(session.rows)}
        raw=c.canonical(v.seal(payload))+b'\n';anchor=hashlib.sha256(raw).hexdigest();verdict=v.verify_bytes(raw,anchor)
        once(c.WORK/'replay/candidate.json',c.strict_json(raw));controls=tests_module().controls(raw,c.WORK/'replay/issuance-controls')
        once(OUT/'protocol-diagnostic.json',{'status':'PASS','rounds':[{'round':r['round'],'candidate_id':r['candidate_id'],'selection':r['selection'],'request_sha256':c.digest(r['body']),'observation':r['observation']} for r in session.rows]})
        once(OUT/'verification-diagnostic.json',{'status':'PASS','sources':c.sources(),'verifier_identity':v.identity(),'raw_sha256':anchor,'controls':controls})
        once(OUT/'session-summary.json',{'status':'COMPLETE','session_id':plan['session_id'],'verdict':verdict,'rounds':[{'round':r['round'],'candidate_id':r['candidate_id'],'run_id':r['contract']['experiment']['run_id'],'feedback':r['feedback']} for r in session.rows],'raw_sha256':anchor})
        once(OUT/'cross-domain-selection-evidence.json',c.strict_json(raw));return verdict
    except Exception as exc:
        once(OUT/'session-summary.json',{'status':'PARTIAL','completed_rounds':len(session.rows),'error':getattr(exc,'code',type(exc).__name__),'ledger':ledger.read(),'no_success_witness':True})
        raise
    finally:key=None;ALLOWED_IPS.clear()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('offline','preflight','fixture','live','verify'));parser.add_argument('--sha256');args=parser.parse_args();sys.addaudithook(guard)
    try:
        result=v.verify_bytes((OUT/'cross-domain-selection-evidence.json').read_bytes(),args.sha256) if args.mode=='verify' else {'offline':offline,'preflight':preflight,'fixture':fixture,'live':live}[args.mode]()
        print(c.canonical(result).decode());return 0
    except Exception as exc:print(c.canonical({'status':'STOPPED','error':getattr(exc,'code',type(exc).__name__)}).decode());return 1
if __name__=='__main__':raise SystemExit(main())
