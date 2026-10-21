"""RPF-63 gated metadata/cold/one Target trial. No historical live entry; a single two-round real dual-role session."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import uuid
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_dual_contracts as c,pge_dual_config_port as bridge,pge_dual_verify as v
def task():return c.TaskLedger(c.WORK/'account')
def base_gate():
    c.require(bridge.old._git('rev-parse','HEAD')==c.BASE and bridge.old._git('branch','--show-current')==c.BRANCH,'GIT_BASE')
    c.require(bridge.old._git('remote','get-url','origin')=='https://github.com/MyKr-YSteinsK/runproof.git','ORIGIN')
def metadata():
    base_gate();total=c.TaskLedger(c.WORK/'account',create=not (c.WORK/'account').exists());ticket=total.reserve('metadata')
    sdk=bridge.sdk_identity_direct();source=bridge.old._verify_source_bundle();java=bridge.old._java_identity()
    bridge.JAR.parent.mkdir(exist_ok=True)
    if not bridge.JAR.exists():
        with bridge.old.SOURCE_JAR.open('rb') as src,bridge.JAR.open('xb') as dst:shutil.copyfileobj(src,dst)
    c.require(bridge.old._sha_file(bridge.JAR)==c.SOURCE_JAR_SHA256 and bridge.JAR.stat().st_size==c.SOURCE_JAR_BYTES,'JAR_PIN')
    value={'status':'PASS','sources':c.sources(),'verifier':v.identity(),'sdk':sdk,'java':java,'source':source,'price':c.PRICE}
    c.once(c.WORK/'preflight/metadata.json',value);total.settle(ticket,status='PASS',sources_sha256=c.digest(c.sources()));return {'status':'PASS','metadata':1}
def cold():
    base_gate();meta=c.strict_json((c.WORK/'preflight/metadata.json').read_bytes());offline=c.strict_json((c.WORK/'preflight/offline.json').read_bytes())
    c.require(meta['sources']==offline['sources']==c.sources() and offline['status']=='PASS','FROZEN_OFFLINE')
    total=task();folder=c.WORK/'cold';folder.mkdir();ct=c.contract('63'+uuid.uuid4().hex[:16],bridge.old._free_port(),bridge.old._free_port(),c.digest(c.sources()),c.CANDIDATES[1],fixture=True)
    journal=bridge.Journal(total,ct['experiment']['run_id']);host=bridge.CapabilityHost(ct,bridge.ProviderLedger.fixture_only(journal.run_id),bridge.ConfigLiveMemoryBackend(),journal,fixture=True)
    sdk=bridge.ConfigTargetDriver().run(ct['capability'],{'contracts':ct,'host':host,'ledger':total,'sdk':meta['sdk'],'folder':folder,'fixture':True})
    checks={'pid':sdk['popen_pid']==sdk['ready']['pid']==sdk['report'].get('pid'),'status':sdk['report']['status']=='COMPLETED','tools':[x['name'] for x in host.tool_trace]==list(c.TOOLS)+['inspect_config'],
        'returns':[t['returned_in_request'] for t in host.tool_trace]==[2,3,4,5],'unknown':host.tool_trace[2]['result']==c.UNKNOWN,'requests':len(host.provider_responses)==5,'guard':sdk['report'].get('guard_denials')==[],'stderr':sdk['stderr_bytes']==0,'cleanup':all(c.strict_json((folder/'sdk-cleanup.json').read_bytes()).values())}
    value={'status':'PASS' if all(checks.values()) else 'FAIL','sources':c.sources(),'verifier':v.identity(),'source_kind':'FIXTURE_SCRIPTED','sdk':sdk,'checks':checks,'tool_trace':host.tool_trace,'completions':host.provider_responses,'contracts':ct,'events':journal.events}
    c.once(c.WORK/'preflight/cold.json',value);c.require(all(checks.values()),'COLD_FAIL');return {'status':'PASS','provider':0,'cold':1,'pid':sdk['popen_pid']}
def live():
    base_gate();meta=c.strict_json((c.WORK/'preflight/metadata.json').read_bytes());cold_value=c.strict_json((c.WORK/'preflight/cold.json').read_bytes());offline=c.strict_json((c.WORK/'preflight/offline.json').read_bytes())
    c.require(meta['sources']==cold_value['sources']==offline['sources']==c.sources() and cold_value['status']==offline['status']=='PASS' and meta['verifier']==cold_value['verifier']==v.identity(),'LIVE_GATES')
    c.require(c.strict_json((c.WORK/'preflight/price-reviewed.json').read_bytes())==c.PRICE,'CURRENT_PRICE_REVIEW')
    bridge.h55.resolve_direct_python(meta['sdk']);c.require(bridge.old._java_identity()==meta['java'] and bridge.old._verify_source_bundle()==meta['source'],'INSTALL_DRIFT')
    key=os.environ.get('DEEPSEEK_API_KEY','');c.require(bool(key),'PROVIDER_KEY_UNAVAILABLE')
    from runtime.runproof_runtime.effectwitness import pge_dual_session as session
    total=task();total.token_pool();rounds=[];ports=set()
    def port():
        for _ in range(16):
            value=bridge.old._free_port()
            if value not in ports:ports.add(value);return value
        c.require(False,'PORT_ALLOCATION')
    for index in (1,2):
        suffix='63'+uuid.uuid4().hex[:16];jp,hp=port(),port();rounds.append({candidate:c.contract(suffix,jp,hp,c.digest(c.sources()),candidate) for candidate in c.CANDIDATES})
    plan=c.plan('rpf63-session-'+uuid.uuid4().hex[:16],rounds);c.once(c.WORK/'preflight/live-plan.json',plan)
    rows=session.execute(plan,total,meta['sdk'],key)
    payload={'source_kind':'REAL_EXPLORER_REAL_TARGET','plan':plan,'rows':rows,'ledger':total.frames,'cold':cold_value,'boundaries':c.BOUNDARIES}
    try:verdict=v.verify_payload(payload)
    except Exception as exc:
        c.once(c.WORK/'diagnostics/live-inconclusive.json',{'status':'INCONCLUSIVE','error_code':getattr(exc,'code','VERIFICATION_REJECTED'),'source_sha256':c.digest(c.sources())});raise
    raw=c.canonical(v.seal(payload));sha=hashlib.sha256(raw).hexdigest();v.verify_bytes(raw,sha)
    c.once(c.WORK/'verified-witness.json',c.strict_json(raw));c.once(c.WORK/'diagnostics/live-result.json',{'status':'PASS','raw_sha256':sha,'bytes':len(raw),'verdict':verdict,'session_id':plan['session_id']})
    return {'status':'PASS','raw_sha256':sha,'verdict':verdict}

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('metadata','cold','live'));a=p.parse_args()
    try:print(c.canonical({'metadata':metadata,'cold':cold,'live':live}[a.mode]()).decode());return 0
    except Exception as exc:print(c.canonical({'status':'STOPPED','error_type':type(exc).__name__,'error_code':getattr(exc,'code','BOUNDED_GATE_REJECTED')}).decode());return 2
if __name__=='__main__':raise SystemExit(main())
