"""Pure offline RPF64 dual-domain witness verifier; no execute or cleanup calls."""
import argparse,hashlib
from pathlib import Path
from . import pge_port_context as c
from .pge_domain_port import select
from .pge_portability_session import dispatch_identity,feedback
from .pge_portability_config import verify_sdk
SCHEMA='rpf64-portability-witness-v1'
def identity():return {'version':'rpf64-portability-verifier-v1','sha256':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
def seal(payload):return {'schema':SCHEMA,'payload':payload,'payload_sha256':c.digest(payload),'verifier_identity':identity()}
def verify_payload(p):
 c.require(set(p)=={'source_kind','context','rows','ledger','cold','boundaries'} and p['boundaries']==c.BOUNDARIES and p['source_kind']==p['context']['source_kind'],'WITNESS_SOURCE')
 ctx=c.TaskContext(c.ROOT/p['context']['workspace'],c.canonical(p['context']));real=p['source_kind']=='BOTH_REAL_CONTROLLED';account=c.replay(p['ledger'],p['context']);counts=account['counts'];events=account['events'];tickets=account['tickets'];results=account['results'];c.require(not account['unknown'],'UNKNOWN_ACCOUNT')
 c.require(counts['provider']==0 and counts['session']==counts['order_trial']==counts['config_trial']==counts['sqlite_setup']==counts['sqlite_refund']==counts['sdk']==counts['jvm']==counts['cold']==1 and counts['trial']==2 and 1<=counts['metadata']<=2,'PHYSICAL_COUNTS')
 c.require(set(tickets)==set(results),'UNSETTLED_RESOURCE');c.require([r['domain'] for r in p['rows']]==list(c.DOMAINS),'TWO_DOMAINS');prior=[];all_http=[]
 for row in p['rows']:
  c.require(set(row)=={'domain','contract','dispatch','evidence','verdict','feedback','cleanup'},'ROW_FIELDS');domain=row['domain'];ct=ctx.contract(domain);c.require(row['contract']==ct and row['dispatch']==dispatch_identity(domain),'PORT_SOURCE_OR_CONTRACT');e=row['evidence'];verdict=select(domain).verify(ctx,ct,e);c.require(row['verdict']==verdict and row['feedback']==feedback(ctx,ct,verdict,e),'ORACLE_OR_FEEDBACK');c.require(all(row['cleanup'].values()),'CLEANUP')
  def one(kind):
   matches=[x for x in events if x['kind']==kind and x.get('domain')==domain];c.require(len(matches)==1,'EVENT_'+kind);return matches[0]
  entered,verified,closed,frozen=[one(k) for k in ('PORT_ENTERED','DOMAIN_VERIFIED','DOMAIN_CLEANUP','FEEDBACK_FROZEN')]
  c.require(entered['dispatch']==row['dispatch'] and entered['contract_sha256']==c.digest(ct) and entered['prior_feedback_sha256']==[c.digest(r['feedback']) for r in prior] and entered['monotonic_ns']<verified['monotonic_ns']<closed['monotonic_ns']<frozen['monotonic_ns'] and verified['evidence_sha256']==c.digest(e) and verified['verdict_sha256']==c.digest(verdict) and closed['cleanup']==row['cleanup'] and frozen['feedback_sha256']==c.digest(row['feedback']),'SESSION_LINEAGE')
  specific=[r for r in tickets.values() if r['resource']==ct['execution']['resource']];trials=[r for r in tickets.values() if r['resource']=='trial' and r.get('domain')==domain];c.require(len(specific)==len(trials)==1 and specific[0]['run_id']==trials[0]['run_id']==ct['experiment']['run_id'],'DOMAIN_BUDGET')
  if prior:c.require(one('PORT_ENTERED')['monotonic_ns']>next(x['monotonic_ns'] for x in events if x['kind']=='FEEDBACK_FROZEN' and x['domain']==prior[-1]['domain']),'FUTURE_FEEDBACK')
  if domain==c.DOMAINS[0]:
   receipt=e['after']['data']['receipts'][0];rs=[r for r in tickets.values() if r['resource']=='sqlite_refund'];c.require(len(rs)==1 and rs[0]['run_id']==ct['experiment']['run_id'] and rs[0]['arguments_sha256']==c.digest(e['tool_call']['arguments']) and results[rs[0]['ticket']]['receipt_id']==receipt['receipt_id'] and results[rs[0]['ticket']]['status']=='COMMITTED','SQLITE_RECEIPT_BUDGET')
  else:
   all_http=e['http'];rs=[r for r in tickets.values() if r['resource']=='http'];c.require(len(rs)==len(all_http)==counts['http'],'HTTP_BUDGET_OMISSION')
   for r,o in zip(rs,all_http):
    z=results[r['ticket']];c.require((r['http_seq'],r['operation'],r['method'],r['run_id'])==(o['seq'],o['kind'],o['method'],ct['experiment']['run_id']) and z['status']==o['status'] and z['response_sha256']==o['response_body_sha256'] and z['transport_error'] is None,'HTTP_ACCOUNT')
   posts=[r for r in tickets.values() if r['resource']=='post'];c.require(len(posts)==counts['post']==2 and [r['operation'] for r in posts]==['create_config_v1','update_config_v2'] and all(results[r['ticket']]['status']==200 and not results[r['ticket']]['unknown'] for r in posts),'POST_ACCOUNT')
   c.require([x['event'] for x in events if x['kind']=='DOMAIN_EVENT' and x['run_id']==ct['experiment']['run_id']]==e['events'],'DOMAIN_EVENTS')
   for resource,pid in (('jvm',e['environment']['java_pid']),('sdk',e['sdk']['popen_pid'])):
    rs=[r for r in tickets.values() if r['resource']==resource];c.require(len(rs)==1 and results[rs[0]['ticket']]['popen_pid']==pid,'PROCESS_PID_ACCOUNT')
   health=[r for r in tickets.values() if r['resource']=='health'];c.require(len(health)==len(e['environment']['health'])==counts['health'],'HEALTH_ACCOUNT')
  prior.append(row)
 cold=p['cold'];c.require(set(cold)=={'status','source_kind','contract','sources','verifier','sdk','tool_trace','completions','events','checks'} and cold['status']=='PASS' and cold['source_kind']=='FIXTURE_SCRIPTED' and cold['contract']==p['context']['cold_contract'] and cold['sources']==c.sources() and cold['verifier']==identity() and all(cold['checks'].values()),'COLD_SOURCE')
 verify_sdk(cold['sdk'],cold['tool_trace'],cold['completions']);c.require([x['name'] for x in cold['tool_trace']]==list(c.TOOLS)+['inspect_config'] and [x['returned_in_request'] for x in cold['tool_trace']]==[2,3,4,5] and cold['tool_trace'][2]['result']==c.UNKNOWN,'COLD_PROTOCOL')
 cr=cold['contract']['experiment']['run_id'];c.require([x['event'] for x in events if x['kind']=='DOMAIN_EVENT' and x['run_id']==cr]==cold['events'],'COLD_WAL');cold_t=[r for r in tickets.values() if r['resource']=='cold'];c.require(results[cold_t[0]['ticket']]['popen_pid']==cold['sdk']['popen_pid'],'COLD_PID_ACCOUNT')
 if real:
  config_e=p['rows'][1]['evidence'];c.require(cold['sdk']['popen_pid']!=config_e['sdk']['popen_pid'] and type(config_e['environment']['java_pid']) is int and config_e['environment']['java_pid']>0 and type(p['rows'][0]['evidence']['executor_pid']) is int and p['rows'][0]['evidence']['executor_pid']>0,'REAL_PROCESS_IDENTITIES')
  for resource,pid in (('cold',cold['sdk']['popen_pid']),('sdk',config_e['sdk']['popen_pid']),('jvm',config_e['environment']['java_pid'])):
   cleanup=[e for e in events if e['kind']=='PROCESS_CLEANUP' and e['resource']==resource];c.require(len(cleanup)==1 and cleanup[0]['pid']==pid and cleanup[0]['process_exited'] is True,'PROCESS_CLEANUP_ACCOUNT')
 session=[r for r in tickets.values() if r['resource']=='session'];c.require(results[session[0]['ticket']]['status']=='COMPLETED' and results[session[0]['ticket']]['rows_sha256']==c.digest(p['rows']),'SESSION_RECEIPT')
 c.require(p['rows'][0]['dispatch']['shared_source_sha256']==p['rows'][1]['dispatch']['shared_source_sha256'],'SHARED_EXECUTION_PATH')
 return {'status':'PASS','source_kind':p['source_kind'],'domains':list(c.DOMAINS),'provider':0,'tokens':0,'cost_cny':0,'shared_dispatch':'OBSERVED' if real else 'SYNTHETIC_TEST_ONLY','physical':counts,'outcomes':[r['verdict']['outcome'] for r in p['rows']],'boundaries':c.BOUNDARIES}
def verify_bytes(raw,anchor):
 c.require(anchor is not None and hashlib.sha256(raw).hexdigest()==anchor,'EXTERNAL_ANCHOR');e=c.strict_json(raw);c.require(set(e)=={'schema','payload','payload_sha256','verifier_identity'} and e['schema']==SCHEMA and e['payload_sha256']==c.digest(e['payload']) and e['verifier_identity']==identity(),'ENVELOPE');return verify_payload(e['payload'])
def main():
 p=argparse.ArgumentParser();p.add_argument('path',type=Path);p.add_argument('--sha256');a=p.parse_args()
 if a.sha256 is None:return 2
 try:print(c.canonical(verify_bytes(a.path.read_bytes(),a.sha256)).decode());return 0
 except Exception as exc:print(getattr(exc,'code','INVALID_EVIDENCE'));return 3
if __name__=='__main__':raise SystemExit(main())
