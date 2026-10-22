"""One new Context, physical WAL, two real role rounds and verified feedback."""
from . import pge_r66_context as c
from . import pge_r66_explorer as explorer
from .pge_r66_target_config import ConfigPort, Host, Journal, ConfigLiveMemoryBackend, run_sdk
from .config_live_runtime import ProviderLedger
from .pge_portability_config import verify_sdk as verify_cold_sdk

def dispatch_identity():
 sm=c.sources();return {'abi':c.ABI,'domain':c.DOMAIN,'port_sha256':sm['runtime/runproof_runtime/effectwitness/pge_r66_target_config.py'],'session_sha256':sm['runtime/runproof_runtime/effectwitness/pge_r66_session.py'],'supervisor_sha256':sm['runtime/runproof_runtime/effectwitness/pge_port_context.py']}

def feedback(ct,e,verdict,prior):
 facts=['effect.v2.history2-1','safe.two-posts','fault.suppressed.unknown-exposed' if verdict['fault']['agent_exposed'] else 'fault.normal.no-intervention']
 if verdict['recovery']=='OBSERVED':facts.append('target.read-only-recovery')
 seen={x for row in prior for x in row['facts']}
 return dict(round=ct['experiment']['round'],run_id=ct['experiment']['run_id'],candidate=ct['experiment']['candidate_id'],authority=verdict['authority'],effect=verdict['effect'],fault=verdict['fault'],recovery=verdict['recovery'],facts=facts,new_facts=[x for x in facts if x not in seen],capture_sha256=c.digest(e),oracle_sha256=c.digest(verdict))

class Session:
 def execute(self,ctx,ledger,port,choose=explorer.choose):
  c.require(type(port) is ConfigPort and ledger.context is ctx,'STATIC_PORT_ALLOWLIST')
  ticket=ledger.reserve('session',session_id=ctx.public()['session_id']);rows=[]
  try:
   for index in (1,2):
    choice=choose(ctx,ledger,index,port.api_key,rows);selection=choice['selection'];candidate=c.strict_json(selection['function']['arguments'].encode())['candidate_id'];ct=ctx.contract(index,candidate);run=ct['experiment']['run_id']
    ledger.append('CHOICE_FROZEN',run_id=run,selection_sha256=c.digest(selection),candidate_id=candidate,contract_sha256=c.digest(ct),provider_ticket=choice['provider_ticket'])
    trial=ledger.reserve('trial',domain=c.DOMAIN,run_id=run)
    ledger.append('PORT_ENTERED',domain=c.DOMAIN,run_id=run,dispatch=dispatch_identity(),contract_sha256=c.digest(ct))
    # ConfigPort releases its local key reference per round; Session retains the
    # parent-only credential for the next independently admitted round.
    key=port.api_key;e=port.execute(ctx,ct,ledger);port.api_key=key;key=None
    verdict=port.verify(ctx,ct,e)
    ledger.append('DOMAIN_VERIFIED',domain=c.DOMAIN,run_id=run,evidence_sha256=c.digest(e),verdict_sha256=c.digest(verdict))
    cleanup=port.cleanup(ctx,ct,e);ledger.append('DOMAIN_CLEANUP',domain=c.DOMAIN,run_id=run,cleanup=cleanup)
    fb=feedback(ct,e,verdict,[r['feedback'] for r in rows]);ledger.append('FEEDBACK_FROZEN',domain=c.DOMAIN,run_id=run,tool_call_id=selection['id'],feedback_sha256=c.digest(fb))
    row=dict(round=index,candidate_id=candidate,contract=ct,dispatch=dispatch_identity(),evidence=e,verdict=verdict,cleanup=cleanup,feedback=fb,**choice)
    ledger.settle(trial,status='COMPLETED',evidence_sha256=c.digest(e));ctx.once(ctx.root/f'round-{index}-verified.json',row);rows.append(row)
   ledger.settle(ticket,status='COMPLETED',rows_sha256=c.digest(rows));return rows
  finally:
   port.api_key=None;ctx.once(ctx.root/'session-receipt.json',dict(completed_rounds=len(rows),rows=rows,ledger=ledger.frames))

def cold(ctx,ledger,meta):
    ct=ctx.public()['cold_contract']; folder=ctx.folder(ct); folder.mkdir(parents=True,exist_ok=False)
    j=Journal(ledger,ct['experiment']['run_id']); host=Host(ct,ProviderLedger.fixture_only(ct['experiment']['run_id']),ConfigLiveMemoryBackend(),j,fixture=True)
    sdk=run_sdk(ctx,ct,ledger,meta['sdk'],folder,host,cold=True)
    verify_cold_sdk(sdk,host.tool_trace,host.provider_responses)
    c.require([t['name'] for t in host.tool_trace]==list(c.TOOLS)+['inspect_config'] and host.tool_trace[2]['result']==c.UNKNOWN and [t['returned_in_request'] for t in host.tool_trace]==[2,3,4,5] and host.failure is None,'COLD_PROTOCOL')
    value=dict(status='PASS',source_kind='FIXTURE_SCRIPTED',contract=ct,sources=c.sources(),sdk=sdk,tool_trace=host.tool_trace,completions=host.provider_responses,events=j.events,checks={'protocol':True,'provider_zero':True,'cleanup':True})
    ctx.once(ctx.root/'preflight/cold.json',value); return value
