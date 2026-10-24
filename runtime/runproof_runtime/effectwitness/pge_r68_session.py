"""Sole typed SharedSession; verify and clean round one before feedback or round two."""
import secrets,os,shutil,subprocess,ast
from . import pge_r68_context as c
from .pge_r68_budget import Ledger
from .pge_r68_driver import Driver,Port,require_admission
from .pge_r68_explorer import choose,feedback
from .pge_r68_order_port import OrderPort
from .pge_r68_config_port import ConfigPort
REGISTRY={c.DOMAINS[0]:ConfigPort,c.DOMAINS[1]:OrderPort}
class SharedSession:
 def __init__(self,ctx,l):c.require(isinstance(l,Ledger) and l.ctx is ctx and l.path==ctx.scope(ctx.root/'wal.jsonl'),'SINGLE_LEDGER');self.ctx=ctx;self.l=l;self.rows=[]
 def execute(self,domain,ct,port,*,fixture=False,key=None):
  if not fixture:require_admission(self.ctx,self.l)
  c.require(domain in REGISTRY and type(port) is REGISTRY[domain] and ct['experiment']['domain']==domain and ct['experiment']['round']==len(self.rows)+1,'TYPED_DISPATCH');self.ctx.validate(ct);name='runtime/runproof_runtime/effectwitness/'+port.__class__.__module__.split('.')[-1]+'.py';self.l.append('PORT_ENTERED',domain=domain,round=ct['experiment']['round'],port_module=name,port_source_sha256=self.ctx.public()['sources'][name]['raw'],contract_sha256=c.digest(ct));driver=Driver(self.ctx,self.l,ct,fixture=fixture,key=key);prepared=False
  try:
   port.prepare(self.ctx,ct,self.l);prepared=True;sdk=driver.run(port);business=port.finish()
  except BaseException:
   if prepared:
    try:self.ctx.once(self.ctx.scope(self.ctx.root/'runs'/ct['experiment']['run_id'])/'failure-business-readback.json',port.finish())
    except Exception:pass
   raise
  finally:
   driver.key=None
   if prepared or hasattr(port,'proc'):cleanup=port.cleanup()
  evidence=dict(contract=ct,trace=port.trace,fault=port.fault,sdk=sdk,business=business,cleanup=cleanup);from .pge_r68_verify import verify_domain
  verify_domain(self.ctx.public(),ct,evidence);return evidence
 def run(self,*,candidates=None,key=None):
  fixture=self.ctx.public()['source_kind']==c.SYNTHETIC;c.require((candidates is not None)==fixture,'SOURCE_MODE');ticket=self.l.reserve('session')
  for index,domain in enumerate(c.DOMAINS,1):
   choice=choose(self.ctx,self.l,index,self.rows,fixture=candidates[index-1] if fixture else None,key=key);ct=self.ctx.contract(index,choice['candidate_id']);trial=self.l.reserve('trial',domain=domain,round=index);e=self.execute(domain,ct,REGISTRY[domain](),fixture=fixture,key=key);self.l.settle(trial,status='VERIFIED');seq=len(self.l.frames);self.l.append('DOMAIN_VERIFIED',domain=domain,round=index,evidence_sha256=c.digest(e),contract_sha256=c.digest(ct),oracle=e['business']['oracle']);fb=feedback(ct,e,choice,seq);self.l.append('FEEDBACK_FROZEN',domain=domain,round=index,feedback=fb,feedback_sha256=c.digest(fb));self.rows.append(dict(choice=choice,evidence=e,feedback=fb))
  self.l.settle(ticket,status='COMPLETED');self.l.append('SESSION_COMPLETE',rounds=2);self.l.read();from .pge_r68_verify import seal,verify
  witness=seal(dict(context=self.ctx.public(),frames=self.l.frames,rounds=self.rows,admission=c.strict((self.ctx.root/'paid-gate.json').read_bytes()) if not fixture else None,boundaries=c.BOUNDARIES));verify(witness);return witness

def copy_jar(ctx):
 ctx.once(ctx.root/'context-capsule.json',ctx.public());_,old=c.helpers();target=ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar');target.parent.mkdir();c.require(c.sha(old.SOURCE_JAR.read_bytes())==c.SOURCE_JAR_SHA256 and old.SOURCE_JAR.stat().st_size==c.SOURCE_JAR_BYTES,'JAR_SOURCE_PIN')
 with old.SOURCE_JAR.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
 c.require(c.sha(target.read_bytes())==c.SOURCE_JAR_SHA256,'JAR_COPY')
def synthetic(candidates=None):
 ctx=c.make(synthetic=True);ctx.root.mkdir(parents=True);copy_jar(ctx);l=Ledger(ctx,create=True);w=SharedSession(ctx,l).run(candidates=candidates or (c.CANDIDATES[0][1],c.CANDIDATES[1][1]));ctx.once(ctx.root/'synthetic-witness.json',w);return w
class ColdPort(Port):
 def __init__(self,ctx,ct,l):self.domain=ct['experiment']['domain'];self.prepare_common(ctx,ct,l,cold=True);self.cold=True
 def business(self,name,args):
  if self.domain==c.DOMAINS[0]:return dict(state='ABSENT') if name=='inspect_config' else dict(status='COMMITTED',version=1 if name=='create_config_v1' else 2,value='rpf53-v1' if name=='create_config_v1' else 'rpf53-v2')
  if name=='inspect_order':return dict(order_id=args['order_id'],status='PAID',revision=0)
  return dict(status='COMMITTED',operation_id=args['operation_id'],receipt_id='receipt-'+'a'*24,committed_revision=1)
def load():
 p=c.strict((c.ROOT/'.local/rpf-68-rev-3/context.json').read_bytes());return c.Context(c.ROOT/p['workspace'],c.canonical(p))
def freeze_check(ctx):
 f=c.strict((ctx.root/'source-freeze.json').read_bytes());g=c.strict((ctx.root/'free-gates.json').read_bytes());sd=ctx.public()['source_digest'];c.require(f['sources']==ctx.public()['sources']==c.sources() and g['source_digest']==sd and g['status']=='PASS' and g['full']['source_digest']==g['focused']['source_digest']==g['matrix']['source_digest']==sd and g['full']['exit']==g['focused']['exit']==g['controls']['exit']==0 and g['full']['errors']==g['full']['failures']==0 and g['full']['skips']==2 and g['synthetic_controls']>=160 and g['matrix']['status']=='PASS' and g['ordinary_candidates']==4 and g['reachable_tokens']==c.REACHABLE_TOKENS<=c.GLOBAL_TOKENS and all(x['exit']==0 for x in g['anchors']) and len(g['anchors'])==21 and g['historical_rpf67']['exit']==0,'FREE_GATES');c.require(all(c.sha(ctx.scope(c.ROOT/name).read_bytes())==h for name,h in f['helpers'].items()),'FROZEN_HELPER_DRIFT');return f,g

def initialize():
 root=c.ROOT/'.local/rpf-68-rev-3';c.require(not (root/'context.json').exists() and c.strict((root/'g0.json').read_bytes())['status']=='PASS','INIT_ONCE');ctx=c.make();freeze_check(ctx);ctx.once(root/'context.json',ctx.public());Ledger(ctx,create=True);copy_jar(ctx);return ctx

def metadata(ctx,l):
 h,old=c.helpers();pin=c.pinned_sdk_fields();direct=h.resolve_direct_python(pin);ticket=l.reserve('metadata');tree=ast.parse((c.ROOT/'spikes/rpf-53/probe.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_sdk_identity');script=ast.literal_eval(next(n.value for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='script' for t in n.targets)));script=script.replace('base=pathlib.Path(sys.prefix,"Lib","site-packages").resolve(strict=True)','base=pathlib.Path(sys.argv[1]).resolve(strict=True);sys.path.insert(0,str(base))').replace('venv_root=pathlib.Path(sys.prefix).resolve(strict=True)','venv_root=base.parent.parent');folder=ctx.scope(ctx.root/'metadata-scratch');folder.mkdir();proc=subprocess.Popen([str(direct),'-I','-B','-X','utf8','-c',script,str(old.SDK_SITE.resolve()),str(direct)],cwd=folder,env=old._sdk_env(folder),stdout=subprocess.PIPE,stderr=subprocess.PIPE);l.append('PROCESS_START',resource='metadata',pid=proc.pid,domain='metadata',round=0,parent_pid=os.getpid());out,err=proc.communicate(timeout=60);c.require(proc.returncode==0 and not err,'METADATA_PROCESS');sdk=c.strict(out);sdk['python_launcher_sha256']=old._sha_file(old.SDK_LAUNCHER);sdk.pop('base_executable_sha256',None);c.require(h.identity_fields(sdk)==pin and sdk['pydantic']['record_mismatches']==sdk['openai']['record_mismatches']==0,'SDK_PIN');ctx.once(ctx.root/'metadata.json',sdk);ctx.once(ctx.root/'java-identity.json',old._java_identity());l.append('PROCESS_CLEANUP',resource='metadata',pid=proc.pid,domain='metadata',round=0,process_gone=proc.poll() is not None);l.settle(ticket,status='PASS',identity=pin);return sdk

def cold(ctx,l):
 result=[]
 for index in (1,2):
  ct=ctx.contract(index,c.CANDIDATES[index-1][0]);port=ColdPort(ctx,ct,l);sdk=Driver(ctx,l,ct,fixture=True,cold=True).run(port);result.append(sdk)
 c.require(l.read()['counts']['provider']==0,'COLD_PROVIDER_ZERO');ctx.once(ctx.root/'cold.json',result);return result

def query_price(ctx):
 import urllib.request,datetime,html,re
 from html.parser import HTMLParser
 class Table(HTMLParser):
  def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
  def handle_starttag(self,tag,attrs):
   if tag=='tr':self.row=[]
   elif tag in ('th','td'):self.cell=[]
  def handle_data(self,data):
   if self.cell is not None:self.cell.append(data)
  def handle_endtag(self,tag):
   if tag in ('th','td') and self.cell is not None:
    if self.row is not None:self.row.append(re.sub(r'\s+',' ',''.join(self.cell)).strip())
    self.cell=None
   elif tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
 request=urllib.request.Request(c.PRICE['url'],headers={'User-Agent':'RunProof-RPF68-rev3-readonly-pricing'});response=urllib.request.urlopen(request,timeout=30)
 with response:raw=response.read(1048577);c.require(response.status==200 and len(raw)<=1048576,'OFFICIAL_PRICE_HTTP')
 parser=Table();parser.feed(raw.decode('utf-8'));category=None;prices={};version=False
 for row in parser.rows:
  text=' '.join(row).upper()
  if 'MODEL VERSION' in text:version=any('DeepSeek-V4.1-Flash-1017' in z for z in row)
  if 'CACHE MISS' in text:category='input'
  elif 'OUTPUT TOKENS' in text:category='output'
  elif 'CACHE HIT' in text:category='cache'
  if category in ('input','output') and any(z=='PEAK' for z in row):
   numbers=[float(z.replace('$','').strip()) for z in row if re.fullmatch(r'\$[0-9.]+',z)];c.require(len(numbers)==2,'OFFICIAL_PRICE_COLUMNS');prices[category]=numbers[0]
 c.require(version and set(prices)=={'input','output'},'OFFICIAL_PRICE_PARSE');price=dict(model='deepseek-flash',model_version='DeepSeek-V4.1-Flash-1017',url=c.PRICE['url'],queried_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),official_input_usd_per_million=prices['input'],official_output_usd_per_million=prices['output'],fx_guard=15,input_micro_cny=max(c.PRICE['input_micro_cny'],prices['input']*15),output_micro_cny=max(c.PRICE['output_micro_cny'],prices['output']*15),raw_sha256=c.sha(raw),invoice='NOT_QUERIED');c.validate_price(price)
 with ctx.scope(ctx.root/'official-pricing.html').open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 ctx.once(ctx.root/'price.json',price);return price

def late_readback(ctx,label):
 import ctypes,time,datetime,socket
 api=ctypes.WinDLL('kernel32',use_last_error=True);api.OpenProcess.restype=ctypes.c_void_p
 class FT(ctypes.Structure):_fields_=[('lo',ctypes.c_uint32),('hi',ctypes.c_uint32)]
 events=Ledger(ctx).read()['events'];rows=[];ports=[];now=time.time();mono=time.monotonic_ns()
 for e in events:
  if e['kind']!='PROCESS_START':continue
  pid=e['pid'];h=api.OpenProcess(0x1000,False,pid);expected=e.get('started_unix_ns',0)/1e9 or now+(e['clock']-mono)/1e9
  if not h:
   error=ctypes.get_last_error();row=dict(pid=pid,resource=e['resource'],original_gone=error==87,status='NOT_PRESENT' if error==87 else 'UNAVAILABLE',winerror=error)
  else:
   try:
    a,b,d,f=FT(),FT(),FT(),FT();ok=api.GetProcessTimes(ctypes.c_void_p(h),ctypes.byref(a),ctypes.byref(b),ctypes.byref(d),ctypes.byref(f));created=((a.hi<<32)+a.lo)/1e7-11644473600 if ok else None;row=dict(pid=pid,resource=e['resource'],original_gone=bool(created and created>expected+5),status='PID_REUSED' if created and created>expected+5 else 'PRESENT_OR_UNAVAILABLE')
   finally:api.CloseHandle(ctypes.c_void_p(h))
  row['cleanup_recorded']=any(z['kind']=='PROCESS_CLEANUP' and z['pid']==pid and z.get('process_gone') for z in events);rows.append(row)
 for port in ctx.public()['ports']:
  with socket.socket() as s:s.settimeout(.25);closed=s.connect_ex(('127.0.0.1',port))!=0
  ports.append(dict(port=port,closed=closed))
 result=dict(status='PASS' if all(r['original_gone'] and r['cleanup_recorded'] for r in rows) and all(p['closed'] for p in ports) else 'UNAVAILABLE',processes=rows,ports=ports,queried_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());ctx.once(ctx.root/('late-'+label+'.json'),result);return result

def admit(ctx,l):
 import datetime
 freeze,gates=freeze_check(ctx);a=l.read();cold=c.strict((ctx.root/'cold.json').read_bytes());c.require(a['counts']['metadata']==1 and a['counts']['cold']==2 and a['counts']['provider']==a['counts']['session']==0 and set(a['tickets'])==set(a['results']) and not a['unknown'] and all(all(x['cleanup'].values()) for x in cold) and c.strict((ctx.root/'late-cold.json').read_bytes())['status']=='PASS','ADMISSION_RESOURCES');price=c.validate_price(c.strict((ctx.root/'price.json').read_bytes()));c.require(0<=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(price['queried_utc'])).total_seconds()<3600,'OFFICIAL_PRICE_FRESH');gate=dict(context_sha256=c.digest(ctx.public()),sources=ctx.public()['sources'],freeze_sha256=c.digest(freeze),free_sha256=c.digest(gates),price=price,caps=ctx.public()['caps'],global_tokens=c.GLOBAL_TOKENS,budget_version=c.BUDGET_VERSION,cold_sha256=c.digest(cold));ctx.once(ctx.root/'paid-gate.json',gate);l.append('ADMISSION',gate_sha256=c.digest(gate),price=price);return gate

def live(ctx,l):
 freeze_check(ctx);a=l.read();gate=c.strict((ctx.root/'paid-gate.json').read_bytes());c.require(gate['context_sha256']==c.digest(ctx.public()) and a['counts']['provider']==a['counts']['session']==0 and not a['unknown'] and not a['blocked'] and subprocess.check_output(['git','rev-parse','HEAD'],cwd=c.ROOT,text=True).strip()==c.BASE and subprocess.check_output(['git','branch','--show-current'],cwd=c.ROOT,text=True).strip()==c.BRANCH,'FRESH_LIVE');key=os.environ.get('DEEPSEEK_API_KEY');c.require(bool(key),'KEY_UNAVAILABLE')
 try:w=SharedSession(ctx,l).run(key=key);ctx.once(ctx.root/'accepted-witness.json',w);return w
 finally:key=None

def max_envelope():
 """Key-free actual SDK experiments. Any legal counterexample blocks admission."""
 import copy,time
 from unittest.mock import patch
 from . import pge_r68_driver as d,pge_r68_explorer as ex
 rows=[];original=d.fixture_response;completion=d.Driver.completion;explorer_exchange=ex.exchange
 for mode in ('legacy-commit-mixed','every-tool-mixed','trusted-upper-first','arguments8192','terminal-mixed','recursive-upper'):
  ctx=c.make(synthetic=True);ctx.root.mkdir(parents=True);copy_jar(ctx);l=Ledger(ctx,create=True);active=[None];observations=[];started=time.monotonic();error=None
  def observe(driver,body,port):
   active[0]=driver
   try:return completion(driver,body,port)
   finally:
    if hasattr(driver,'last_request'):observations.append(dict(domain=port.domain,round=driver.ct['experiment']['round'],request=copy.deepcopy(driver.last_request)))
  def response(ct,n,call,**kw):
   value=original(ct,n,call,**kw);index=ct['experiment']['round']
   if call:
    msg=value['choices'][0]['message']
    if mode!='arguments8192':msg['tool_calls'][0]['id']=(kw['prefix']+'-'+str(n)+'-').ljust(160,'x')
    if mode in ('arguments8192','recursive-upper'):
     f=msg['tool_calls'][0]['function'];f['arguments']=f['arguments'].ljust(8192,'\t' if mode=='recursive-upper' else ' ')
    if mode in ('every-tool-mixed','trusted-upper-first','recursive-upper') or mode=='legacy-commit-mixed' and n==(3 if index==1 else 2) or mode=='terminal-mixed' and n==3:msg['content']=('\x00' if mode=='recursive-upper' else 'x')*512
   if mode=='trusted-upper-first' and n==1 or mode=='recursive-upper':
    value['usage']['prompt_tokens']=active[0].last_request['input_upper'];value['usage']['total_tokens']=value['usage']['prompt_tokens']+value['usage']['completion_tokens']
   return value
  def explorer(*args,**kw):
   f=kw.get('fixture')
   if f is not None:
    f['id']=f['id'].ljust(160,'x');call=f['choices'][0]['message']['tool_calls'][0];call['id']=call['id'].ljust(160,'x')
    if mode=='recursive-upper':call['function']['arguments']=call['function']['arguments'].ljust(8192,'\t')
   return explorer_exchange(*args,**kw)
  try:
   with patch.object(d.Driver,'completion',observe),patch.object(d,'fixture_response',response),patch.object(ex,'exchange',explorer):
    witness=SharedSession(ctx,l).run(candidates=(c.CANDIDATES[0][1],c.CANDIDATES[1][1]));ctx.once(ctx.root/'synthetic-witness.json',witness)
  except Exception as exc:error=dict(type=type(exc).__name__,code=str(exc) if type(exc) is ValueError else 'REDACTED')
  late=late_readback(ctx,'envelope');state=l.read();row=dict(late=late,mode=mode,status='FAIL' if error or late['status']!='PASS' else 'PASS',source_kind=c.SYNTHETIC,source_digest=ctx.public()['source_digest'],workspace=ctx.public()['workspace'],elapsed_seconds=round(time.monotonic()-started,3),error=error,requests=observations,pre_send=[e for e in state['events'] if e['kind']=='PRE_SEND_REJECTED'],counts=state['counts'],unknown=state['unknown'],blocked=state['blocked'],cleanup=[e for e in state['events'] if e['kind']=='PROCESS_CLEANUP'],previous_usage='SYNTHETIC_STRICTLY_PARSED_HINT_NOT_REAL_PROVIDER_MEASUREMENT',provider_key_read=False);ctx.once(ctx.root/'envelope-case.json',row);rows.append(row)
 result=dict(owner=c.OWNER,status='PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL',source_digest=rows[0]['source_digest'],cases=rows,old_counterexample=dict(required=2706,old_config4=2400,new_config4=c.CAPS[c.DOMAINS[0]][3],calculation_only=True),coverage='FINITE_ACTUAL_SDK_CASES_NOT_ABSOLUTE_WORST_CASE',provider=0)
 root=c.ROOT/'.local/rpf-68-rev-3/tests';path=root/('max-envelope-'+secrets.token_hex(8)+'.json')
 with path.open('xb') as f:f.write(c.canonical(result));f.flush();os.fsync(f.fileno())
 return result
