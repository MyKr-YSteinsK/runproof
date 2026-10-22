"""Versioned, static, one-domain session. Feedback has no Explorer consumer."""
from . import pge_r65_context as c
from .pge_r65_target_config import ConfigPort, Host, Journal, ConfigLiveMemoryBackend, run_sdk
from .config_live_runtime import ProviderLedger
from .pge_portability_config import verify_sdk as verify_cold_sdk

def dispatch_identity():
    sm=c.sources()
    return {'abi':c.ABI,'domain':c.DOMAIN,'port_sha256':sm['runtime/runproof_runtime/effectwitness/pge_r65_target_config.py'],'session_sha256':sm['runtime/runproof_runtime/effectwitness/pge_r65_session.py'],'supervisor_sha256':sm['runtime/runproof_runtime/effectwitness/pge_port_context.py']}

def feedback(ctx,ct,verdict,e):
    return {'schema':'rpf65-verified-feedback-v2','source_kind':ctx.public()['source_kind'],'run_id':ct['experiment']['run_id'],'authority':ct['effect']['authority'],'verdict':verdict,'evidence_sha256':c.digest(e),'explorer_consumed':False,'L2':'NOT_TESTED'}

class Session:
    def execute(self,ctx,ledger,port):
        c.require(type(port) is ConfigPort,'STATIC_PORT_ALLOWLIST')
        ticket=ledger.reserve('session',session_id=ctx.public()['session_id'])
        ct=ctx.contract(); run=ct['experiment']['run_id']; trial=ledger.reserve('trial',domain=c.DOMAIN,run_id=run)
        ledger.append('PORT_ENTERED',domain=c.DOMAIN,run_id=run,dispatch=dispatch_identity(),contract_sha256=c.digest(ct))
        e=port.execute(ctx,ct,ledger); verdict=port.verify(ctx,ct,e)
        ledger.append('DOMAIN_VERIFIED',domain=c.DOMAIN,run_id=run,evidence_sha256=c.digest(e),verdict_sha256=c.digest(verdict))
        cleanup=port.cleanup(ctx,ct,e); ledger.append('DOMAIN_CLEANUP',domain=c.DOMAIN,run_id=run,cleanup=cleanup)
        fb=feedback(ctx,ct,verdict,e); ledger.append('FEEDBACK_FROZEN',domain=c.DOMAIN,run_id=run,feedback_sha256=c.digest(fb))
        row=dict(contract=ct,dispatch=dispatch_identity(),evidence=e,verdict=verdict,cleanup=cleanup,feedback=fb)
        ledger.settle(trial,status='COMPLETED',evidence_sha256=c.digest(e)); ledger.settle(ticket,status='COMPLETED',row_sha256=c.digest(row))
        return row

def cold(ctx,ledger,meta):
    ct=ctx.public()['cold_contract']; folder=ctx.folder(ct); folder.mkdir(parents=True,exist_ok=False)
    j=Journal(ledger,ct['experiment']['run_id']); host=Host(ct,ProviderLedger.fixture_only(ct['experiment']['run_id']),ConfigLiveMemoryBackend(),j,fixture=True)
    sdk=run_sdk(ctx,ct,ledger,meta['sdk'],folder,host,cold=True)
    verify_cold_sdk(sdk,host.tool_trace,host.provider_responses)
    c.require([t['name'] for t in host.tool_trace]==list(c.TOOLS)+['inspect_config'] and host.tool_trace[2]['result']==c.UNKNOWN and [t['returned_in_request'] for t in host.tool_trace]==[2,3,4,5] and host.failure is None,'COLD_PROTOCOL')
    value=dict(status='PASS',source_kind='FIXTURE_SCRIPTED',contract=ct,sources=c.sources(),sdk=sdk,tool_trace=host.tool_trace,completions=host.provider_responses,events=j.events,checks={'protocol':True,'provider_zero':True,'cleanup':True})
    ctx.once(ctx.root/'preflight/cold.json',value); return value
