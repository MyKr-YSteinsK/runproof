"""Controller-observed budget ABI; the pinned child never attests this capsule.

The audit hook observes native Popen's caller before process creation. The
scoped profiler observes the actual canonical(cfg) return passed to communicate.
Neither replaces a native function, module global, guard, or child report.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import copy
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from . import pge_r72r2_contracts as c, pge_r72r2_budget_policy as b
from . import pge_r68_context as n
from . import pge_r68_contracts as nc
from .pge_r68_driver import Driver as NativeDriver, fixture_response

SCHEMA = 'rpf72r2-parent-child-budget-v2'
TAG = 'RPF72R2_SDK_CONTRACT'
CHILD = 'runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py'
FIELDS = frozenset(('port','token','write_root','sdk_readonly_path',
                    'sdk_site_root_binding_sha256','python_runtime_mapping_sha256',
                    'instructions','task_prompt','domain','total_token_limit'))
LEVELS = dict(config='CONTROLLER_OBSERVED', execution='SDK_EXECUTION_OBSERVED',
              child='CHILD_ATTESTATION_NOT_ESTABLISHED')
_active = ContextVar('rpf72r2_native_launch', default=None)
_installed = False

def validate_launch(args, expected, direct, folder, env, child_sha, pin):
    c.require(type(args) is tuple and len(args)==4,'NATIVE_AUDIT_SHAPE')
    c.require(type(expected) is list and expected==[str(direct),'-I','-B','-X','utf8',str(n.ROOT/CHILD)],'TRUSTED_ARGV')
    c.require(Path(direct).is_absolute() and c.sha(Path(direct).read_bytes())==pin['python_executable_sha256'],'NATIVE_EXECUTABLE_PIN')
    c.require(c.sha((n.ROOT/CHILD).read_bytes())==child_sha,'NATIVE_CHILD_PIN')
    if os.name=='nt':
        wanted=subprocess.list2cmdline(expected)
        c.require(args[0] is None and type(args[1]) is str and args[1]==wanted,'NATIVE_CHILD_ARGV')
    else:
        c.require(False,'UNTESTED_AUDIT_PLATFORM')
    c.require(type(args[2]) is str and args[2]==str(folder),'NATIVE_CHILD_CWD')
    c.require(type(args[3]) is dict and all(type(k) is str and type(v) is str for k,v in args[3].items()),'NATIVE_ENV_TYPE')
    c.equal(args[3],env,'NATIVE_ENV_EXACT')
    c.require(set(env)=={'SYSTEMROOT','WINDIR','PATH','HOME','USERPROFILE','TEMP','TMP','PYTHONDONTWRITEBYTECODE','OTEL_SDK_DISABLED','LOGFIRE_SEND_TO_LOGFIRE'},'SANITIZED_ENV_ALLOWLIST')
    return dict(platform='WINDOWS',executable_type=type(args[0]).__name__,argv_type=type(args[1]).__name__,
                expected_command_sha256=c.sha(wanted.encode()),observed_command_sha256=c.sha(args[1].encode()),
                executable_sha256=pin['python_executable_sha256'],child_sha256=child_sha,exact_equality=True,
                cwd_bound=True,env_exact=True,env_keys=sorted(env),env_sha256=c.digest(env),shell=False)

def validate_raw_config(raw,capsule,ctx,policy,ct,folder,port):
    c.require(type(raw) is bytes and 0<len(raw)<=16384,'CONFIG_RAW_SIZE')
    cfg=c.strict(raw)
    c.require(raw==c.canonical(cfg),'CONFIG_RAW_CANONICAL')
    return validate_config(cfg,capsule,ctx,policy,ct,folder,port)

def specification(ctx, policy, ct):
    c.require(type(policy) is b.BudgetPolicy, 'PARENT_POLICY_TYPE')
    policy.check(ctx)
    ctx.validate(ct)
    p = policy.public()
    d, r = ct['experiment']['domain'], ct['experiment']['round']
    c.require(d in c.DOMAINS and type(r) is int and r == c.DOMAINS.index(d)+1, 'PARENT_DOMAIN')
    slots = [x for x in p['slots'] if x['domain']==d and x['role']=='TARGET']
    total = p['child_cumulative'][d]
    c.require(type(total) is int and total == (250000 if d==c.DOMAINS[0] else 160000), 'PARENT_TOTAL')
    c.require(p['reachable_tokens']==474000 and p['global_tokens']==600000 and p['max_slot']==160000,
              'PARENT_ARITHMETIC')
    return dict(schema=SCHEMA, owner=ctx.owner.public(), source_kind=c.KIND,
                source_capsule_sha256=ctx.source.raw_sha256,
                source_raw_digest=p['source_raw_digest'], source_lf_digest=p['source_lf_digest'],
                policy_sha256=policy.raw_sha256, contract_sha256=c.digest(ct),
                domain=d, round=r, role='TARGET', slots=slots,
                child_target_cumulative=total, global_tokens=p['global_tokens'],
                reachable_tokens=p['reachable_tokens'], max_slot=p['max_slot'],
                maximum_output=512, child_raw_sha256=ctx.public()['sources'][CHILD]['raw'],
                sdk_pin=p['sdk_pin'], unknown=p['unknown'], provider_calls=0,
                issuer=False, child_attestation=False)

@dataclass(frozen=True, slots=True)
class ParentChildBudgetContract:
    frozen: bytes

    @classmethod
    def create(cls, ctx, policy, ct):
        return cls(c.canonical(specification(ctx,policy,ct)))

    def public(self):
        c.require(type(self.frozen) is bytes, 'PARENT_BYTES')
        return c.strict(self.frozen)

    @property
    def raw_sha256(self):
        return c.sha(self.frozen)

    def check(self, ctx, policy, ct):
        c.equal(self.public(),specification(ctx,policy,ct),'PARENT_CONTRACT_IDENTITY')
        c.require(self.frozen==c.canonical(self.public()),'PARENT_CANONICAL')

def validate_config(cfg, capsule, ctx, policy, ct, folder, port):
    capsule.check(ctx,policy,ct)
    c.require(type(cfg) is dict and set(cfg)==FIELDS,'CHILD_CONFIG_FIELDS')
    p = capsule.public()
    c.require(type(cfg['total_token_limit']) is int and
              cfg['total_token_limit']==p['child_target_cumulative'],'CHILD_CONFIG_LIMIT')
    c.require(type(cfg['port']) is int and cfg['port']==port and 1024<=port<=65535,'CHILD_CONFIG_PORT')
    c.require(type(cfg['token']) is str and re.fullmatch('[a-f0-9]{64}',cfg['token']),'CHILD_CONFIG_TOKEN')
    _, old = n.helpers()
    expected = dict(domain=p['domain'],write_root=str(ctx.scope(folder)),
                    sdk_readonly_path=str(old.SDK_SITE.resolve()),
                    sdk_site_root_binding_sha256=p['sdk_pin']['sdk_site_root_binding_sha256'],
                    python_runtime_mapping_sha256=p['sdk_pin']['python_runtime_mapping_sha256'],
                    instructions=n.INSTRUCTIONS[p['domain']],task_prompt=n.prompt(ct))
    for key,value in expected.items():
        c.equal(cfg[key],value,'CHILD_CONFIG_'+key.upper())
    c.require(len(c.canonical(cfg))<=16384,'CHILD_CONFIG_SIZE')
    return dict(domain=cfg['domain'],total_token_limit=cfg['total_token_limit'],port=port,
                write_root=folder.relative_to(ctx.root).as_posix(),
                sdk_site_root_binding_sha256=cfg['sdk_site_root_binding_sha256'],
                python_runtime_mapping_sha256=cfg['python_runtime_mapping_sha256'],
                instructions_sha256=c.sha(cfg['instructions'].encode()),
                task_prompt_sha256=c.sha(cfg['task_prompt'].encode()))

def _audit(event, args):
    driver = _active.get()
    if event!='subprocess.Popen' or driver is None:
        return
    frame = sys._getframe(1)
    while frame is not None and frame.f_code is not NativeDriver.run.__code__:
        frame = frame.f_back
    c.require(frame is not None and frame.f_locals.get('self') is driver,'NATIVE_LAUNCH_CALLER')
    cfg, folder = frame.f_locals['cfg'], frame.f_locals['folder']
    direct = frame.f_locals['direct']
    _,old=n.helpers()
    launch=validate_launch(args,[str(direct),'-I','-B','-X','utf8',str(n.ROOT/CHILD)],direct,folder,
                           old._sdk_env(folder),driver._capsule.public()['child_raw_sha256'],driver._capsule.public()['sdk_pin'])
    c.require(driver._cfg is None,'ONE_NATIVE_CHILD')
    view = validate_config(cfg,driver._capsule,driver.ctx,driver.l.policy,driver.ct,
                           folder,driver.ct['execution']['host_port'])
    driver._cfg = cfg
    driver._proof = dict(schema=SCHEMA,contract=driver._capsule.public(),
                         contract_sha256=driver._capsule.raw_sha256,config=view,
                         actual_config_sha256=c.sha(c.canonical(cfg)),levels=LEVELS,launch=launch)
    driver.l.append('INTENT',audit_type=TAG,status='CONFIG_VALIDATED',
                    domain=view['domain'],round=driver.ct['experiment']['round'],proof=driver._proof)

def _profile(frame, event, arg):
    driver = _active.get()
    if driver is None or event!='return' or frame.f_code is not nc.canonical.__code__:
        return
    caller = frame.f_back
    if caller is None or caller.f_code is not NativeDriver.run.__code__ or frame.f_locals.get('x') is not driver._cfg:
        return
    c.require(driver._cfg is not None and type(arg) is bytes and
              c.sha(arg)==driver._proof['actual_config_sha256'],'ACTUAL_SERIALIZED_CONFIG')
    c.require('serialized_input_sha256' not in driver._proof,'ONE_SERIALIZED_INPUT')
    driver._proof = copy.deepcopy(driver._proof)
    driver._proof.update(serialized_input_sha256=c.sha(arg),pid=driver.pid)
    driver.l.append('INTENT',audit_type=TAG,status='SERIALIZED_INPUT',domain=driver._proof['config']['domain'],
                    round=driver.ct['experiment']['round'],pid=driver.pid,sha256=c.sha(arg))

class ContractDriver(NativeDriver):
    def run(self, port):
        global _installed
        c.require(self.fixture is True and self.key is None and not self.cold,'SCRIPTED_NATIVE_ONLY')
        c.require(sys.getprofile() is None and _active.get() is None,'CONTROLLER_PROFILE_SCOPE')
        self._capsule = ParentChildBudgetContract.create(self.ctx,self.l.policy,self.ct)
        self._capsule.check(self.ctx,self.l.policy,self.ct)
        self._cfg, self._proof = None, None
        if not _installed:
            sys.addaudithook(_audit)
            _installed = True
        token = _active.set(self)
        try:
            sys.setprofile(_profile)
            result = super().run(port)
        finally:
            sys.setprofile(None)
            _active.reset(token)
        c.require(self._proof is not None and self._proof.get('pid')==result['pid'] and
                  self._proof.get('serialized_input_sha256')==self._proof['actual_config_sha256'],
                  'CHILD_EXECUTION_OBSERVATION')
        binding = c.digest(result)
        self.l.append('INTENT',audit_type=TAG,status='RESULT_BOUND',domain=port.domain,
                      round=self.ct['experiment']['round'],pid=result['pid'],sdk_sha256=binding,
                      contract_sha256=self._capsule.raw_sha256)
        result['parent_child'] = dict(self._proof,sdk_sha256=binding)
        self._cfg = None
        return result

def verify_proof(ctx, policy, ct, sdk, events=None):
    proof = sdk['parent_child']
    capsule = ParentChildBudgetContract(c.canonical(proof['contract']))
    capsule.check(ctx,policy,ct)
    c.require(set(proof)=={'schema','contract','contract_sha256','config','actual_config_sha256','levels','launch',
                           'serialized_input_sha256','pid','sdk_sha256'},'PARENT_PROOF_FIELDS')
    c.equal(proof['levels'],LEVELS,'CHILD_ATTESTATION_LEVEL')
    launch=proof['launch'];pin=capsule.public()['sdk_pin']
    c.require(set(launch)=={'platform','executable_type','argv_type','expected_command_sha256','observed_command_sha256','executable_sha256','child_sha256','exact_equality','cwd_bound','env_exact','env_keys','env_sha256','shell'},'LAUNCH_PROOF_FIELDS')
    c.require(launch['platform']=='WINDOWS' and launch['executable_type']=='NoneType' and launch['argv_type']=='str' and
              launch['exact_equality'] is True and launch['cwd_bound'] is True and launch['env_exact'] is True and launch['shell'] is False,
              'LAUNCH_PROOF_SEMANTICS')
    h,old=n.helpers();direct=h.resolve_direct_python(pin)
    expected_command=subprocess.list2cmdline([str(direct),'-I','-B','-X','utf8',str(n.ROOT/CHILD)])
    c.require(launch['expected_command_sha256']==launch['observed_command_sha256']==c.sha(expected_command.encode()) and
              launch['executable_sha256']==pin['python_executable_sha256'] and launch['child_sha256']==capsule.public()['child_raw_sha256'],
              'LAUNCH_PROOF_PIN_COMMAND')
    expected_env=old._sdk_env(ctx.root/'runs'/ct['experiment']['run_id']/'sdk')
    c.require(launch['env_keys']==sorted(expected_env) and launch['env_sha256']==c.digest(expected_env),'LAUNCH_ENV_BINDING')
    c.require(proof['schema']==SCHEMA and proof['contract_sha256']==capsule.raw_sha256 and
              proof['pid']==sdk['pid']==sdk['ready']['pid']==sdk['report']['pid'],'PARENT_RESULT_IDENTITY')
    d = ct['experiment']['domain']
    pin = capsule.public()['sdk_pin']
    expected = dict(domain=d,total_token_limit=capsule.public()['child_target_cumulative'],
                    port=ct['execution']['host_port'],write_root='runs/'+ct['experiment']['run_id']+'/sdk',
                    sdk_site_root_binding_sha256=pin['sdk_site_root_binding_sha256'],
                    python_runtime_mapping_sha256=pin['python_runtime_mapping_sha256'],
                    instructions_sha256=c.sha(n.INSTRUCTIONS[d].encode()),task_prompt_sha256=c.sha(n.prompt(ct).encode()))
    c.equal(proof['config'],expected,'PARENT_CONFIG_BINDING')
    c.require(type(proof['actual_config_sha256']) is str and re.fullmatch('[a-f0-9]{64}',proof['actual_config_sha256']) and
              proof['serialized_input_sha256']==proof['actual_config_sha256'],'PARENT_RAW_CONFIG_BINDING')
    original = {k:v for k,v in sdk.items() if k!='parent_child'}
    c.require(proof['sdk_sha256']==c.digest(original),'PARENT_SDK_BINDING')
    c.require(sdk['report']['input_tokens']+sdk['report']['output_tokens']<=capsule.public()['child_target_cumulative'],
              'PARENT_SDK_TOTAL')
    if events is not None:
        rows = [(i,e) for i,e in enumerate(events) if e.get('audit_type')==TAG and e['domain']==d]
        c.require([e['status'] for _,e in rows]==['CONFIG_VALIDATED','SERIALIZED_INPUT','RESULT_BOUND'], 'PARENT_WAL_ORDER')
        a,z = rows[0][1],rows[2][1]
        initial = {k:v for k,v in proof.items() if k not in ('serialized_input_sha256','pid','sdk_sha256')}
        c.equal(a['proof'],initial,'PARENT_PRELAUNCH_WAL')
        c.require(all(e['round']==ct['experiment']['round'] for _,e in rows),'PARENT_WAL_DOMAIN')
        c.require(rows[1][1]['pid']==z['pid']==sdk['pid'] and rows[1][1]['sha256']==proof['actual_config_sha256'] and
                  z['sdk_sha256']==proof['sdk_sha256'] and z['contract_sha256']==capsule.raw_sha256,'PARENT_WAL_RESULT')
        start = next(i for i,e in enumerate(events) if e['kind']=='PROCESS_START' and e.get('pid')==sdk['pid'])
        req = next(i for i,e in enumerate(events) if e['kind']=='MODEL_REQUEST' and e.get('role')=='TARGET' and e['domain']==d)
        c.require(rows[0][0]<start<rows[1][0]<req<rows[2][0],'PARENT_LAUNCH_BEFORE_REQUEST')
    return dict(status='PASS',levels=LEVELS)

def smoke(ctx, *, reject=False):
    """Original Driver.run; typed synthetic callback only, no DB/JVM/effects."""
    from .pge_r72r2_budget_ledger import BudgetLedger
    from .pge_r72r2_capability import Gate
    from .pge_r68_driver import Port
    from unittest.mock import patch
    c.require(type(reject) is bool,'SMOKE_REJECT_TYPE')
    task=ctx.root.parents[1]
    claim=task/('smoke-reject.json' if reject else 'smoke-accept.json')
    with claim.open('xb') as f:f.write(c.canonical(dict(run=ctx.owner.run_id)))
    ctx.root.mkdir(parents=True)
    ct=ctx.contract(2,n.CANDIDATES[1][0])
    ledger=BudgetLedger(ctx,create=True)
    gate=Gate(ctx,ct,ledger);gate.prepared=True;op=gate.enter('driver')
    class SyntheticPort(Port):
        domain=c.DOMAINS[1]
        def business(self,name,args):
            return dict(status='SYNTHETIC_NO_BUSINESS_EFFECT',tool=name)
    port=SyntheticPort();port.prepare_common(ctx,ct,ledger)
    driver=ContractDriver(ctx,ledger,ct,fixture=True)
    original=validate_launch
    def reject_validator(args,*rest):
        altered=list(args);altered[1]=args[1]+' --rpf-tripwire-extra-flag'
        return original(tuple(altered),*rest)
    error=None;sdk=None
    try:
        if reject:
            with patch(__name__+'.validate_launch',reject_validator):sdk=driver.run(port)
        else:sdk=driver.run(port)
    except ValueError as exc:error=str(exc)
    if sdk is not None:
        gate.complete(op,sdk)
        verify_proof(ctx,ledger.policy,ct,sdk,ledger.read()['events'])
    with socket.socket() as sock:
        sock.settimeout(.2);closed=sock.connect_ex(('127.0.0.1',ct['execution']['host_port']))!=0
    state=ledger.read()
    accepted=error is None and sdk is not None and driver.pid is not None
    denied=error=='NATIVE_CHILD_ARGV' and sdk is None and driver.pid is None
    result=dict(status='PASS' if (denied if reject else accepted) and closed and sys.getprofile() is None and _active.get() is None else 'FAIL',
                schema=SCHEMA,case='NATIVE_REJECT_PRE_CREATEPROCESS' if reject else 'NATIVE_ACCEPT',
                source=ctx.source.public(),owner=ctx.owner.public(),policy=ledger.policy.public(),contract=ct,
                sdk=sdk,error=error,pid=driver.pid,port_closed=closed,profile_restored=sys.getprofile() is None,
                active_context_reset=_active.get() is None,wal_raw_sha256=c.sha(ledger.path.read_bytes()),frames=ledger.frames,
                counts=state['counts'],unsettled_tickets=sorted(set(state['tickets'])-set(state['results'])),
                business_effects=0,jvm=0,sqlite=0,provider_calls=0,
                fixture='NativePort with synthetic no-effect business callback; no production/business adapter')
    ctx.once(ctx.root/'smoke-result.json',result)
    return result

def pressure(ctx, domain, case):
    """Real pinned SDK, synthetic usage, isolated no-business callbacks.

    'legal-high' respects slot/presend bounds and crosses 35000. Boundary cases
    deliberately supply an over-slot usage hint on the final response; they test
    SDK cumulative semantics only, never legal Provider reservation capacity.
    """
    c.require(domain in c.DOMAINS and case in ('legal-high','limit-minus-one','limit-equal','limit-plus-one'), 'PRESSURE_CASE')
    index = c.DOMAINS.index(domain)+1
    ct = ctx.contract(index,n.CANDIDATES[index-1][0])
    policy = b.BudgetPolicy.create(ctx)
    capsule = ParentChildBudgetContract.create(ctx,policy,ct)
    folder = ctx.scope(ctx.root/('pressure-'+case))
    folder.mkdir(parents=True,exist_ok=False)
    h,old = n.helpers()
    pin = capsule.public()['sdk_pin']
    direct = h.resolve_direct_python(pin)
    token = secrets.token_hex(32)
    rows, returns, ready, failures = [],[],[],[]
    tool_names = list(n.TOOLS[domain]) + ([n.TOOLS[domain][0]] if index==1 else [])
    schedule = [500,12000,18000,24000,30000][:len(tool_names)+1]
    prior = None
    pid = None
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_POST(self):
            nonlocal prior
            try:
                self.connection.settimeout(60)
                c.require(self.headers.get('Authorization')=='Bearer '+token and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}', 'PRESSURE_AUTH')
                length = int(self.headers.get('Content-Length','0'))
                c.require(0<length<=262144,'PRESSURE_SIZE')
                body = c.strict(self.rfile.read(length))
                if self.path=='/ready':
                    expected = dict(framework='pydantic-ai-slim',version='2.57.0',openai_version='3.35.1',pid=pid,
                                    python_executable_sha256=pin['python_executable_sha256'],
                                    sdk_source_sha256='70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa',
                                    openai_source_sha256=pin['openai_core_sha256'],
                                    sdk_site_root_binding_sha256=pin['sdk_site_root_binding_sha256'],
                                    python_runtime_mapping_sha256=pin['python_runtime_mapping_sha256'])
                    c.require(not ready,'PRESSURE_ONE_READY')
                    c.equal(body,expected,'PRESSURE_READY')
                    ready.append(body)
                    result = {'ready':True}
                elif self.path=='/tool':
                    j = len(returns)
                    c.require(j<len(tool_names) and body['name']==tool_names[j] and body['arguments']==n.args_for(ct,tool_names[j]),'PRESSURE_TOOL')
                    result = dict(status='SYNTHETIC_NO_BUSINESS_EFFECT',padding='x'*(12000 if j==0 else 8000))
                    returns.append(dict(name=body['name'],call_id=body['call_id'],result_sha256=c.digest(result)))
                else:
                    c.require(self.path=='/v1/chat/completions' and ready and len(rows)<=len(tool_names),'PRESSURE_ROUTE')
                    ordinal = len(rows)+1
                    messages = body['messages']
                    c.require(prior is None or messages[:len(prior)]==prior,'PRESSURE_PREFIX')
                    suffix = messages if prior is None else messages[len(prior):]
                    prompt = schedule[ordinal-1]
                    total_limit = capsule.public()['child_target_cumulative']
                    if case!='legal-high' and ordinal==len(schedule):
                        offset = {'limit-minus-one':-1,'limit-equal':0,'limit-plus-one':1}[case]
                        prompt = total_limit+offset-sum(x['input_tokens']+x['output_tokens'] for x in rows)-20
                    upper = len(c.canonical(body)) if prior is None else rows[-1]['input_tokens']+len(c.canonical(suffix))+512
                    if case=='legal-high':
                        c.require(prompt<=upper and upper+512<=n.CAPS[domain][ordinal-1],'PRESSURE_PRESEND_SLOT')
                    result = fixture_response(ct,ordinal,tool_names[ordinal-1] if ordinal<=len(tool_names) else None,prefix='pressure')
                    result['usage'] = dict(prompt_tokens=prompt,completion_tokens=20,total_tokens=prompt+20)
                    rows.append(dict(ordinal=ordinal,input_tokens=prompt,output_tokens=20,input_upper=upper,
                                     slot_cap=n.CAPS[domain][ordinal-1],request_sha256=c.digest(body),response_sha256=c.digest(result)))
                    prior = copy.deepcopy(messages)
                raw = c.canonical(result)
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except BaseException as exc:
                failures.append(dict(error_type=type(exc).__name__,code=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z0-9_]+',str(exc)) else 'PLATFORM_ERROR'))
                self.send_response(409)
                self.end_headers()
    server = HTTPServer(('127.0.0.1',0),Handler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    cfg = dict(port=port,token=token,write_root=str(folder),sdk_readonly_path=str(old.SDK_SITE.resolve()),
               sdk_site_root_binding_sha256=pin['sdk_site_root_binding_sha256'],python_runtime_mapping_sha256=pin['python_runtime_mapping_sha256'],
               instructions=n.INSTRUCTIONS[domain],task_prompt=n.prompt(ct),domain=domain,
               total_token_limit=capsule.public()['child_target_cumulative'])
    view = validate_config(cfg,capsule,ctx,policy,ct,folder,port)
    rawcfg = c.canonical(cfg)
    proc = None
    started = time.monotonic()
    try:
        proc = subprocess.Popen([str(direct),'-I','-B','-X','utf8',str(n.ROOT/CHILD)],cwd=folder,env=old._sdk_env(folder),
                                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        pid = proc.pid
        stdout,stderr = proc.communicate(rawcfg,timeout=220)
        report = c.strict(stdout)
        report.pop('final_output_sha256',None)
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    with socket.socket() as sock:
        sock.settimeout(.2)
        closed = sock.connect_ex(('127.0.0.1',port))!=0
    expected_error = case=='limit-plus-one'
    total = sum(x['input_tokens']+x['output_tokens'] for x in rows)
    passed = not stderr and not failures and bool(ready) and len(rows)==len(schedule) and closed and not thread.is_alive()
    if expected_error:
        passed = passed and proc.returncode==1 and report.get('error_type')=='UsageLimitExceeded' and report.get('stage')=='SDK_RUN'
    else:
        passed = passed and proc.returncode==0 and report.get('status')=='COMPLETED' and report.get('input_tokens',-1)+report.get('output_tokens',-1)==total and total>35000
    result = dict(schema=SCHEMA,status='PASS' if passed else 'FAIL',source_kind='REAL_FIXED_SDK_SYNTHETIC_USAGE_COMPONENT',
                  scope='LEGAL_SLOT_AND_CUMULATIVE' if case=='legal-high' else 'INTENTIONALLY_OVER_SLOT_FINAL_USAGE_HINT_SDK_CUMULATIVE_ONLY',
                  case=case,domain=domain,contract=capsule.public(),contract_sha256=capsule.raw_sha256,config=view,
                  actual_config_sha256=c.sha(rawcfg),serialized_input_sha256=c.sha(rawcfg),pid=pid,ready=ready,report=report,
                  rows=rows,returns=returns,scripted_total_hint=total,synthetic_run_usage_established=not expected_error and passed,
                  failures=failures,exit=proc.returncode,stderr_bytes=len(stderr),elapsed_seconds=time.monotonic()-started,
                  cleanup=dict(process_gone=proc.poll() is not None,thread_gone=not thread.is_alive(),port_closed=closed),
                  levels=LEVELS,provider_calls=0,business_effects=0,real_key_lookup=0,
                  child_sanitized_absence_probes='ORIGINAL_CHILD_ENV_GET_PRESENT_CHECKS_RETAINED_NO_CREDENTIAL_INHERITED')
    ctx.once(folder/'result.json',result)
    return result
