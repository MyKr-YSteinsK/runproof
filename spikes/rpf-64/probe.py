"""RPF64 gated metadata/cold/one controlled session; Provider hard zero."""
import argparse,hashlib,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_port_context as c,pge_portability_config as config,pge_portability_session as session,pge_portability_verify as v
WORK=ROOT/'.local/rpf-64'
def base_gate():
 _,old=c.helpers();c.require(old._git('rev-parse','HEAD')==c.BASE and old._git('branch','--show-current')==c.BRANCH and old._git('remote','get-url','origin')=='https://github.com/MyKr-YSteinsK/runproof.git','BASE_BRANCH_ORIGIN')
def load():return c.TaskContext(WORK,(WORK/'context.json').read_bytes())
def account(ctx):return c.Ledger(ctx,ctx.root/'account')
def metadata():
 base_gate();_,old=c.helpers();ports=[]
 while len(ports)<4:
  port=old._free_port()
  if port not in ports:ports.append(port)
 ctx=c.make_context(uuid.uuid4().hex[:16],ports[:2],ports[2:]);ctx.once(WORK/'context.json',ctx.public());ledger=c.Ledger(ctx,WORK/'account',create=True);value=c.metadata(ctx,ledger);return {'status':value['status'],'metadata':1,'provider':0,'context_sha256':c.digest(ctx.public())}
def cold():
 base_gate();ctx=load();meta=c.strict_json((WORK/'preflight/metadata.json').read_bytes());gate=c.strict_json((WORK/'preflight/offline.json').read_bytes());c.require(meta['sources']==gate['sources']==c.sources() and gate['status']=='PASS' and gate['whitespace']=='PASS','FREE_GATES')
 ledger=account(ctx);ct=ctx.public()['cold_contract'];folder=ctx.folder(ct);folder.mkdir(parents=True,exist_ok=False);journal=config.Journal(ledger,ct['experiment']['run_id']);host=config.Host(ct,config.ConfigLiveMemoryBackend(),journal);sdk=config.run_sdk(ctx,ct,ledger,meta['sdk'],folder,host,cold=True)
 checks={'pid':sdk['popen_pid']==sdk['ready']['pid']==sdk['report'].get('pid'),'status':sdk['report']['status']=='COMPLETED','tools':[x['name'] for x in host.tool_trace]==list(c.TOOLS)+['inspect_config'],'returns':[x['returned_in_request'] for x in host.tool_trace]==[2,3,4,5],'unknown':host.tool_trace[2]['result']==c.UNKNOWN,'guard':sdk['report'].get('guard_denials')==[],'stderr':sdk['stderr_bytes']==0,'zero_tokens':sdk['report']['input_tokens']==sdk['report']['output_tokens']==0,'cleanup':all(c.strict_json((folder/'sdk-cleanup.json').read_bytes()).values())}
 value={'status':'PASS' if all(checks.values()) else 'FAIL','source_kind':'FIXTURE_SCRIPTED','contract':ct,'sources':c.sources(),'verifier':v.identity(),'sdk':sdk,'tool_trace':host.tool_trace,'completions':host.provider_responses,'events':journal.events,'checks':checks};ctx.once(WORK/'preflight/cold.json',value);c.require(all(checks.values()),'COLD_FAIL');return {'status':'PASS','cold':1,'sdk_pid':sdk['popen_pid'],'provider':0}
def live():
 base_gate();ctx=load();meta=c.strict_json((WORK/'preflight/metadata.json').read_bytes());cold_value=c.strict_json((WORK/'preflight/cold.json').read_bytes());gate=c.strict_json((WORK/'preflight/offline.json').read_bytes());c.require(meta['sources']==cold_value['sources']==gate['sources']==c.sources() and cold_value['status']==gate['status']=='PASS' and cold_value['verifier']==v.identity(),'FROZEN_GATES');h,old=c.helpers();c.require(old._verify_source_bundle()==meta['source_bundle'] and old._java_identity()==meta['java'],'INSTALL_DRIFT');h.resolve_direct_python(meta['sdk'])
 ledger=account(ctx);rows=session.SharedSession(ctx,ledger).run();payload={'source_kind':'BOTH_REAL_CONTROLLED','context':ctx.public(),'rows':rows,'ledger':ledger.frames,'cold':cold_value,'boundaries':c.BOUNDARIES}
 try:verdict=v.verify_payload(payload)
 except Exception as exc:ctx.once(WORK/'diagnostics/live-inconclusive.json',{'status':'INCONCLUSIVE','code':getattr(exc,'code','INVALID_EVIDENCE')});raise
 raw=c.canonical(v.seal(payload));sha=hashlib.sha256(raw).hexdigest();v.verify_bytes(raw,sha);ctx.once(WORK/'verified-witness.json',c.strict_json(raw));ctx.once(WORK/'diagnostics/live-result.json',{'status':'PASS','bytes':len(raw),'raw_sha256':sha,'verdict':verdict});return {'status':'PASS','raw_sha256':sha,'verdict':verdict}
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('metadata','cold','live-controlled','verify'));a=p.parse_args()
 try:
  if a.mode=='verify':raw=(WORK/'verified-witness.json').read_bytes();result=v.verify_bytes(raw,hashlib.sha256(raw).hexdigest())
  else:result={'metadata':metadata,'cold':cold,'live-controlled':live}[a.mode]()
  print(c.canonical(result).decode());return 0
 except Exception as exc:print(c.canonical({'status':'STOPPED','error_type':type(exc).__name__,'code':getattr(exc,'code','BOUNDED_GATE_REJECTED')}).decode());return 2
if __name__=='__main__':raise SystemExit(main())
