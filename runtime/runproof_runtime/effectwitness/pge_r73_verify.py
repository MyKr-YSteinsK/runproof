"""Independent anchored component replay, no Popen or current-env reconstruction."""
from . import pge_r73_contracts as c
from .pge_r73_launch_contract import LaunchRequest
from .pge_r73_domain_adapters import DomainAdapter
from .pge_r73_sdk_harness import Harness,ready_identity
RECEIPT_FIELDS=frozenset(('schema','factory_entrypoint','request_sha256','source_sha256','cfg_sha256','serialized_input_sha256','env_snapshot_sha256','actual_popen','pid','parent_pid','started_unix_ns','elapsed_seconds','exit','state','error','ready','report','stdout_raw','stdout_sha256','stderr_sha256','rows','callbacks','adapter_error','cleanup','scope','usage_type','observation','child_attestation','issuer','flags'))
class MemoryJournal:
 def __init__(self):self.events=[]
 def append(self,kind,**fields):self.events.append(dict(kind=kind,**fields))
def verify_bytes(raw,anchor):
 c.require(type(anchor) is str and len(anchor)==64 and c.sha(raw)==anchor,'RAW_ANCHOR')
 value=c.canonical_value(raw);c.require(set(value)=={'schema','request','receipt','frames','wal_raw_sha256'} and value['schema']=='rpf73-component-evidence-v1','COMPONENT_SCHEMA')
 request=LaunchRequest(c.canonical(value['request']));v=request.check(c.fixed_paths());r=value['receipt']
 c.require(type(r) is dict and set(r)==RECEIPT_FIELDS,'RECEIPT_FIELDS')
 c.equal({k:r[k] for k in ('schema','factory_entrypoint','request_sha256','source_sha256','cfg_sha256','serialized_input_sha256','env_snapshot_sha256','scope','usage_type','observation','child_attestation','issuer','flags')},dict(schema='rpf73-launch-receipt-v1',factory_entrypoint='pge_r73_launch_factory.LaunchFactory.launch',request_sha256=request.raw_sha256,source_sha256=c.digest(v['source']),cfg_sha256=v['cfg_sha256'],serialized_input_sha256=c.sha(v['cfg_raw'].encode('ascii')),env_snapshot_sha256=v['env_summary']['sha256'],scope='LOCAL_FIXED_SDK_COMPONENT_NOT_BUSINESS_WITNESS',usage_type='SYNTHETIC_VALIDATED_USAGE',observation=['CONTROLLER_OBSERVED','SDK_REPORT_OBSERVED'],child_attestation='NOT_ESTABLISHED',issuer=False,flags=c.FLAGS),'RECEIPT_BINDING')
 for k in ('pid','parent_pid','started_unix_ns'):c.require(type(r[k]) is int and r[k]>0,'PROCESS_ID_TYPE')
 c.require(r['pid']!=r['parent_pid'] and type(r['elapsed_seconds']) in (float,int) and 0<r['elapsed_seconds']<940,'PROCESS_LIFECYCLE')
 c.require(r['error'] is None and r['adapter_error'] is None,'COMPONENT_PLATFORM_ERROR')
 c.equal(r['cleanup'],dict(process_gone=True,thread_gone=True,port_closed=True,active_context_reset=True),'CLEANUP_REQUIRED')
 audit=dict(executable_type='NoneType',command=v['command'],cwd=v['cwd'],env=v['env'],tuple_types=['NoneType','str','str','dict'])
 c.equal(r['actual_popen'],[audit],'ACTUAL_AUDIT_BINDING');c.equal(r['ready'],ready_identity(r['pid']),'READY_BINDING')
 stdout=r['stdout_raw'];c.require(type(stdout) is str and c.sha(stdout.encode())==r['stdout_sha256'] and r['stderr_sha256']==c.sha(b''),'STDOUT_RAW_BYTES')
 report=c.canonical_value(stdout.strip().encode());report.pop('final_output_sha256',None);c.equal(report,r['report'],'ORIGINAL_SDK_REPORT')
 mem=MemoryJournal();host=Harness(v,DomainAdapter(v['domain']),mem);host.pid=r['pid'];host.ready=r['ready']
 c.require(type(r['rows']) is list and len(r['rows'])==4 and type(r['callbacks']) is list and len(r['callbacks'])==3,'MULTIROUND_COMPLETE')
 for n,row in enumerate(r['rows'],1):
  rawbody=row['body_raw'].encode('utf-8');c.equal(c.strict(rawbody),row['body'],'HTTP_BODY_RAW')
  host.completion(row['body'],rawbody);c.equal(host.rows[-1],row,'EXCHANGE_SEMANTIC_REPLAY')
  if n<=3:
   cb=r['callbacks'][n-1];host.callback(cb['call'],c.canonical(cb['call']));c.equal(host.callbacks[-1],cb,'CALLBACK_SEMANTIC_REPLAY')
 c.require(host.pending is None and r['rows'][-1]['response']['choices'][0]['finish_reason']=='stop','TERMINAL_STOP')
 if v['pressure']:
  c.equal(dict(state=r['state'],exit=r['exit']),dict(state='EXPECTED_REJECTION',exit=1),'EXPECTED_REJECTION_STATE')
  c.equal(report,dict(status='SDK_ERROR',stage='SDK_RUN',error_type='UsageLimitExceeded',guard_denials=[],denied_files=[]),'ACTUAL_SDK_LIMIT_ERROR')
  c.require(sum(x['response']['usage']['total_tokens'] for x in r['rows'])==v['budget']['cumulative']+1,'LIMIT_PLUS_ONE_HINT')
 else:
  c.equal(dict(state=r['state'],exit=r['exit']),dict(state='COMPLETED',exit=0),'COMPLETED_STATE')
  identity=ready_identity(r['pid']);extra=dict(status='COMPLETED',requests=4,tool_calls=3,tool_callbacks=3,input_tokens=sum(x['response']['usage']['prompt_tokens'] for x in r['rows']),output_tokens=80,usage_type='pydantic_ai.usage.RunUsage',final_text_persisted=False,provider_key_present=False,business_key_present=False,guard_denials=[],denied_files=[])
  c.equal(report,dict(identity,**extra),'SDK_RUNUSAGE_LINEAGE')
  c.require(35000<report['input_tokens']+report['output_tokens']<=v['budget']['cumulative'],'LEGAL_HIGH_ACTUAL_USAGE')
 expected=[dict(kind='ADMITTED',request_sha256=request.raw_sha256,source_sha256=c.digest(v['source']),cfg_sha256=v['cfg_sha256']),dict(kind='HOST_START',address='127.0.0.1',port=v['cfg']['port']),dict(kind='POPEN_AUDIT',observation=audit),dict(kind='PROCESS_START',pid=r['pid'],parent_pid=r['parent_pid'],started_unix_ns=r['started_unix_ns'],argv_sha256=c.digest(v['argv']),command_sha256=c.sha(v['command'].encode()),cwd_sha256=c.sha(v['cwd'].encode())),dict(kind='SERIALIZED_INPUT',pid=r['pid'],raw_sha256=v['cfg_sha256'],bytes=len(v['cfg_raw'])),dict(kind='READY',identity=r['ready'],raw_sha256=c.digest(r['ready'])),*mem.events,dict(kind='EXIT',pid=r['pid'],exit=r['exit'],report_sha256=c.digest(report),stdout_sha256=r['stdout_sha256'],stderr_sha256=r['stderr_sha256'],state=r['state']),dict(kind='CLEANUP',pid=r['pid'],**r['cleanup']),dict(kind='RESULT_BOUND',receipt_sha256=c.digest(r))]
 frames=value['frames'];c.require(type(frames) is list and len(frames)==len(expected),'WAL_EVENT_COUNT');previous='0'*64
 for n,(frame,event) in enumerate(zip(frames,expected),1):
  c.require(set(frame)=={'seq','previous','event','sha256'},'WAL_FIELDS')
  core=dict(seq=n,previous=previous,event=event);c.equal({k:frame[k] for k in core},core,'WAL_ORDER_SEMANTICS');c.require(frame['sha256']==c.digest(core),'WAL_CHAIN');previous=frame['sha256']
 c.require(value['wal_raw_sha256']==c.sha(b''.join(c.canonical(f)+b'\n' for f in frames)),'WAL_RAW_BYTES')
 return dict(status='PASS',run_id=v['run_id'],domain=v['domain'],case=v['case'],pid=r['pid'],state=r['state'],source_sha256=c.digest(v['source']),manifest_sha256=c.sha(raw),usage_type='SYNTHETIC_VALIDATED_USAGE',business_target_real=False,provider=0,issuer=False)
