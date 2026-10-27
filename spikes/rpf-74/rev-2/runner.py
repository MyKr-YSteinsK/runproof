"""Bounded commands and private evidence for the rev-3 continuation."""
import datetime
import copy
import shutil
import re
import importlib
import importlib.util
import os
import secrets
import collections
import subprocess
import sys
import time
from runtime.runproof_runtime.effectwitness import pge_r74r2_contracts as c


def once(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(c.canonical(value)); stream.flush(); os.fsync(stream.fileno())


def sanitized_environment(folder):
    old = importlib.import_module('spikes.rpf-73.rev-2.environment_contract')
    host = {key:os.environ[key] for key in old.HOST_KEYS}
    host['PATH'], _ = old.filtered_path(host['PATH'])
    env = dict(host)
    env.update({key:str(folder) for key in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR')})
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    return env


def run_command(label, argv, *, cwd=None, timeout=180, env=None):
    c.require(label.isascii() and label.replace('-', '').isalnum(), 'COMMAND_LABEL')
    folder = c.WORK / 'commands' / label
    folder.mkdir(parents=True, exist_ok=False)
    scratch = folder/'scratch'; scratch.mkdir()
    if env is None: env = sanitized_environment(scratch)
    start = time.monotonic_ns(); utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    child = subprocess.Popen(argv, cwd=cwd or c.ROOT, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    try:
        out, err = child.communicate(timeout=timeout); timed_out = False
    except subprocess.TimeoutExpired:
        child.terminate(); out, err = child.communicate(timeout=15); timed_out = True
    for name, raw in (('stdout.raw',out), ('stderr.raw',err)):
        with (folder/name).open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    result = dict(label=label, argv=argv, cwd=str(cwd or c.ROOT), pid=child.pid,
                  start_utc=utc, start_monotonic_ns=start, elapsed_ns=time.monotonic_ns()-start,
                  exit=child.returncode, timed_out=timed_out, stdout_sha256=c.sha(out), stderr_sha256=c.sha(err),
                  environment_keys=sorted(env), environment_sha256=c.digest(env))
    once(folder/'receipt.json',result)
    return result


def history():
    entries = c.strict((c.ROOT/'spikes/rpf-73/history-regression.json').read_bytes())['commands']
    c.require(len(entries)==27, 'HISTORY_ENTRY_COUNT')
    results=[]
    for i, entry in enumerate(entries):
        args=entry['command']; c.require(args[:4]==['python','-X','utf8','-B'] and
                                         not any('.local' in x for x in args), 'HISTORY_PUBLIC_ONLY')
        result=run_command('history-%02d'%i,[sys.executable,*args[1:]],timeout=180)
        result['expected_exit']=entry['exit'];results.append(result)
    summary={'status':'PASS' if all(r['exit']==r['expected_exit'] for r in results) else 'FAIL',
             'public_verifiers':24,'rpf69_expected_exits':[0,2,3],'results':results}
    once(c.WORK/'history-result.json',summary)
    return summary


def source_freeze():
    from runtime.runproof_runtime.effectwitness.pge_r74r2_owner_source import source_identity
    from runtime.runproof_runtime.effectwitness.pge_r74r2_contracts import SOURCE_NAMES
    c.require((c.WORK/'receipts/rev3-continuation-g0.json').is_file() and
              (c.WORK/'receipts/final-pre-freeze-checks.json').is_file(), 'PRE_FREEZE_RECEIPTS_REQUIRED')
    receipt=c.strict((c.WORK/'receipts/final-pre-freeze-checks.json').read_bytes())
    c.require(receipt.get('status') == 'PASS' and receipt.get('identity') == source_identity(),
              'PRE_FREEZE_NOT_CURRENT')
    checks=[]
    for name in SOURCE_NAMES:
        path=c.ROOT/name;c.require(path.is_file() and not path.is_symlink(), 'SOURCE_MISSING_OR_LINK')
        check=subprocess.run(['git','-c','core.autocrlf=false','diff','--no-index','--check','--','NUL',name],
                             cwd=c.ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        c.require(check.returncode in (0,1) and not check.stdout and not check.stderr,'SOURCE_FORMAT')
        checks.append(name)
    identity=source_identity()
    frozen={'identity':identity,'source_sha256':c.digest(identity),'source_names':list(SOURCE_NAMES),
            'checked_paths':checks,'freeze_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    once(c.WORK/'source-freeze.json',frozen)
    return frozen


def deep_clone(original, destination, mutate):
    """Rebind a negative copy and rehash its dependent local artifacts and WAL."""
    from runtime.runproof_runtime.effectwitness.pge_r73_launch_contract import env_summary
    m=copy.deepcopy(original); old_root=c.ROOT/m['context']['workspace']; root=destination/m['context']['session_id']
    root.mkdir(parents=True,exist_ok=False)
    m['context']['workspace']=root.relative_to(c.ROOT).as_posix()
    m['policy']['owner']['workspace']=m['context']['workspace'];m['policy_sha256']=c.digest(m['policy'])
    for row in m['domains']:
        ct=row['contract'];old_folder=old_root/'runs'/ct['experiment']['run_id'];new_folder=root/'runs'/ct['experiment']['run_id']
        (new_folder/'sdk').mkdir(parents=True)
        for name in ('stdout.raw','stderr.raw'):
            shutil.copyfile(old_folder/'sdk'/name,new_folder/'sdk'/name)
        launch=c.strict((old_folder/'sdk'/'launch-input.json').read_bytes())
        sdk_folder=new_folder/'sdk';launch['cwd']=str(sdk_folder);launch['cfg']['write_root']=str(sdk_folder)
        for key in ('HOME','USERPROFILE','TEMP','TMP'):launch['env'][key]=str(sdk_folder)
        launch['env_summary']=env_summary(launch['env'],sdk_folder);launch['cfg_sha256']=c.digest(launch['cfg'])
        once(sdk_folder/'launch-input.json',launch)
        sdk=row['sdk'];sdk['cfg_sha256']=launch['cfg_sha256'];sdk['request_sha256']=c.digest(launch)
        sdk['env_observation'][0]['cwd_sha256']=c.sha(str(sdk_folder).encode())
        sdk['env_observation'][0]['env_sha256']=launch['env_summary']['sha256']
        if ct['experiment']['domain']==c.DOMAINS[1]:
            (new_folder/'business').mkdir()
            shutil.copyfile(old_folder/'business'/'orders.sqlite3',new_folder/'business'/'orders.sqlite3')
    mutate(m, root)
    m['policy_sha256']=c.digest(m['policy'])
    previous_request=None;active_operation=None
    for frame in m['wal']:
        event=frame['event']
        if event['kind']=='OWNER':event['context_sha256']=c.digest(m['context'])
        if event.get('audit_type')=='RPF74R2_AUTHORIZATION':
            if event.get('status') in ('CHECK','GRANTED'):
                event['operation']['owner']=m['policy']['owner'];active_operation=c.digest(event['operation'])
                event['operation_sha256']=active_operation
            elif event.get('status')=='COMPLETED':
                event['operation_sha256']=active_operation
        if event.get('audit_type')=='RPF74R2_BUDGET':
            if event.get('status')=='CHECK':
                event['request']['policy_sha256']=m['policy_sha256'];event['request']['operation_sha256']=active_operation
                previous_request=c.digest(event['request'])
            elif event.get('status') in ('GRANTED','CONFIRMED','SETTLED'):
                event['request_sha256']=previous_request
            elif event.get('status')=='SLOT_GRANTED':event['policy_sha256']=m['policy_sha256']
        index_round=event.get('round')
        if index_round in (1,2) and event['kind']=='DOMAIN_VERIFIED':
            row=m['domains'][index_round-1];event['effect_sha256']=c.digest(row['effect']);event['sdk_receipt_sha256']=c.digest(row['sdk'])
        if index_round in (1,2) and event['kind']=='FEEDBACK_FROZEN':
            fb=m['domains'][index_round-1]['feedback'];event['feedback']=fb;event['feedback_sha256']=c.digest(fb)
    previous=None
    for frame in m['wal']:
        frame['previous']=previous;frame['sha256']=c.digest({k:v for k,v in frame.items() if k!='sha256'});previous=c.digest(frame)
    wal=b''.join(c.canonical(frame)+b'\n' for frame in m['wal'])
    with (root/'wal.jsonl').open('xb') as out:out.write(wal);out.flush();os.fsync(out.fileno())
    m['wal_sha256']=c.sha(wal)
    path=root/'manifest.json';once(path,m)
    return path


def mutate_report_plus_one(manifest, root):
    row=manifest['domains'][1]; sdk=row['sdk']; sdk['report']['input_tokens'] += 1
    path=root/'runs'/row['contract']['experiment']['run_id']/'sdk'/'stdout.raw'
    raw=c.canonical(sdk['report'])
    with path.open('wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sdk['stdout_sha256']=c.sha(raw)


def no_mutation(manifest, root):
    pass


def snapshot(label, folder):
    from runtime.runproof_runtime.effectwitness.pge_r74r2_contracts import SOURCE_NAMES
    c.require(re.fullmatch('[a-z0-9-]+',label) is not None, 'SNAPSHOT_LABEL')
    folder.mkdir(parents=True,exist_ok=False)
    tracked=subprocess.check_output(['git','ls-files','--','runtime','spikes','demo','ci','control-plane',
        '.github','AGENTS.md','.gitignore','README.md','README.zh-CN.md','web/README.md'],cwd=c.ROOT,text=True).splitlines()
    names=set(tracked)|set(SOURCE_NAMES)
    names.update('docs/'+stem+suffix for stem in ('ARCHITECTURE','RELIABILITY_MODEL','DEMO','GLOSSARY')
                 for suffix in ('.md','.zh-CN.md'))
    lc=importlib.import_module('runtime.runproof_runtime.effectwitness.lab_cross_domain_contracts')
    names.update(lc.NEW_FILES+lc.OLD_FILES)
    hashes={}
    for name in sorted(names):
        c.require(not name.startswith(('.local/','docs/reviews/','docs/project/','docs/history/')),'SNAPSHOT_PROTECTED')
        src=c.ROOT/name
        if not src.is_file(): continue
        c.require(not any(p.is_symlink() or p.is_junction() for p in (src,*src.parents)), 'SNAPSHOT_REPARSE')
        dst=folder/name;dst.parent.mkdir(parents=True,exist_ok=True)
        raw=src.read_bytes()
        with dst.open('xb') as stream:stream.write(raw)
        c.require(c.sha(dst.read_bytes())==c.sha(raw),'SNAPSHOT_COPY')
        hashes[name]=c.sha(raw)
    once(c.WORK/'receipts'/('snapshot-'+label+'.json'),{'count':len(hashes),'files':hashes})
    return folder


def formal_original(manifest_path, anchor, scenario):
    manifest_path=manifest_path.absolute()
    claim=c.strict((c.WORK/(scenario+'-result.json')).read_bytes())
    c.require(claim['status']=='VERIFIED' and claim['scenario']==scenario and
              manifest_path==c.ROOT/claim['manifest'] and anchor==claim['sha256'] and
              manifest_path.is_relative_to(c.WORK/'sessions') and
              not any(p.is_symlink() or p.is_junction() for p in (manifest_path,*manifest_path.parents)),
              'FORMAL_ORIGINAL_SCOPE')
    return manifest_path.read_bytes()


def usage_counterexample(manifest_path, anchor):
    raw=formal_original(manifest_path,anchor,'F')
    c.require(c.sha(raw)==anchor, 'ORIGINAL_ANCHOR')
    manifest=c.strict(raw)
    work=c.WORK/'negative'/'usage-plus-one'
    baseline=deep_clone(manifest,work/'baseline',no_mutation)
    changed=deep_clone(manifest,work/'mutant',mutate_report_plus_one)
    command=['-X','utf8','-B','-m','spikes.rpf-74.rev-2.probe','verify','--manifest']
    original=run_command('usage-clone-baseline',[sys.executable,*command,str(baseline),
        '--sha256',c.sha(baseline.read_bytes())],timeout=180)
    mutant=run_command('usage-clone-plus-one',[sys.executable,*command,str(changed),
        '--sha256',c.sha(changed.read_bytes())],timeout=180)
    output=c.strict((c.WORK/'commands/usage-clone-plus-one/stdout.raw').read_bytes())
    result={'baseline_exit':original['exit'],'mutant_exit':mutant['exit'],'reason':output.get('reason'),
            'baseline_sha256':c.sha(baseline.read_bytes()),'mutant_sha256':c.sha(changed.read_bytes()),
            'reanchored':['stdout','receipt','policy','owner','wal','manifest','raw_anchor'],
            'status':'PASS' if original['exit']==0 and mutant['exit']==3 and
                      output.get('reason')=='SDK_USAGE_SUM_MISMATCH' else 'FAIL'}
    once(c.WORK/'usage-plus-one-result.json',result)
    return result


def mutate_slot_request(manifest, root, key, value):
    events=[frame['event'] for frame in manifest['wal']]
    pos=next(i for i,e in enumerate(events) if e['kind']=='RESERVE' and e.get('resource')=='provider'
             and e.get('role')=='TARGET' and e.get('domain')==c.DOMAINS[1])
    reserve=events[pos]; ticket=reserve['ticket']; request=reserve['request']
    target=request
    for part in key[:-1]: target=target[part]
    target[key[-1]]=value
    # Re-anchor both the authorization input and all recorded slot copies.
    events[pos-2]['request']['parameters']['request']=copy.deepcopy(request)
    model=next(e for e in events if e['kind']=='MODEL_REQUEST' and e.get('ticket')==ticket)
    model['request']=dict(copy.deepcopy(request), ticket=ticket)
    for row in manifest['domains'][1]['sdk']['rows']:
        if row['proof']['ticket']==ticket: row['proof']=copy.deepcopy(model['request'])


def mutate_manifest_path(manifest, root, path, value):
    obj=manifest
    for key in path[:-1]: obj=obj[key]
    obj[path[-1]]=value


def mutate_coupled_usage(manifest, root, mode):
    row=manifest['domains'][1];sdk=row['sdk'];wire=sdk['rows'][0]
    usage=wire['response']['usage'];old_input=usage['prompt_tokens'];old_output=usage['completion_tokens']
    if mode=='prompt_plus': usage['prompt_tokens']+=1
    elif mode=='prompt_minus': usage['prompt_tokens']-=1
    elif mode=='completion_plus': usage['completion_tokens']+=1
    elif mode=='completion_minus': usage['completion_tokens']-=1
    elif mode=='both_plus': usage['prompt_tokens']+=1;usage['completion_tokens']+=1
    elif mode=='completion_zero': usage['completion_tokens']=0
    elif mode=='output_over_cap': usage['completion_tokens']=wire['proof']['output_cap']+1
    elif mode=='prompt_over_cap': usage['prompt_tokens']=wire['proof']['input_upper']+1
    else: raise ValueError('ATTACK_MODE')
    usage['total_tokens']=usage['prompt_tokens']+usage['completion_tokens']
    wire['response_raw']=c.canonical(wire['response']).decode()
    sdk['report']['input_tokens']+=usage['prompt_tokens']-old_input
    sdk['report']['output_tokens']+=usage['completion_tokens']-old_output
    stdout=root/'runs'/row['contract']['experiment']['run_id']/'sdk'/'stdout.raw'
    raw=c.canonical(sdk['report'])
    with stdout.open('wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sdk['stdout_sha256']=c.sha(raw)
    ticket=wire['proof']['ticket'];events=[f['event'] for f in manifest['wal']]
    response=next(e for e in events if e['kind']=='MODEL_RESPONSE' and e.get('ticket')==ticket)
    response['response']=copy.deepcopy(wire['response'])
    pos=next(i for i,e in enumerate(events) if e['kind']=='RESULT' and e.get('ticket')==ticket)
    events[pos]['usage']=copy.deepcopy(usage)
    events[pos-2]['request']['parameters']['usage']=copy.deepcopy(usage)


def slot_attacks():
    return [
        (('ordinal',),0), (('ordinal',),2), (('ordinal',),True),
        (('stage',),'READ_ONLY'), (('stage',),'POST_RECONCILE_TERMINAL'), (('stage',),'INVALID'),
        (('input_upper',),0), (('input_upper',),-1), (('input_upper',),True),
        (('input_upper',),10000), (('input_upper',),262145), (('input_upper',),'1000'),
        (('output_cap',),512), (('output_cap',),0), (('output_cap',),-1), (('output_cap',),True),
        (('slot_cap',),9999), (('slot_cap',),10001), (('slot_cap',),True), (('slot_cap',),0),
        (('request_sha256',),'a'), (('request_sha256',),'z'*64), (('request_sha256',),17),
        (('slot_contract_sha256',),'0'*64), (('slot_contract_sha256',),''),
        (('slot_scope','role'),'EXPLORER'), (('slot_scope','domain'),c.DOMAINS[0]),
        (('slot_scope','round'),1), (('slot_scope','ordinal'),2),
        (('slot_scope','output_cap'),512), (('slot_scope','slot_cap'),30000),
        (('slot_scope','version'),'wrong'), (('slot_scope','reachable_tokens'),474001),
        (('slot_scope','global_tokens'),600001), (('slot_scope','max_slot'),160001),
        (('slot_scope','ordinal'),True), (('slot_scope','round'),True),
        (('slot_scope','output_cap'),True), (('slot_scope','slot_cap'),True)]


def manifest_attacks():
    fields=[(('owner',),'wrong'),(('abi',),'wrong'),(('schema',),'wrong'),(('source_kind',),'REAL'),
      (('scenario',),'N'),(('provider_calls',),1),(('issuer',),True),(('child_attestation',),True),
      (('model_source',),'REAL'),
      (('context','owner'),'wrong'),(('context','abi'),'wrong'),(('context','source_kind'),'REAL'),
      (('context','scenario'),'N'),(('context','session_id'),'old'),(('context','source_capsule_sha256'),'0'*64),
      (('policy','provider_calls'),1),(('policy','one_native_wal'),False),(('policy','refundable'),True),
      (('policy','source'),'0'*64),(('domains',0,'choice','candidate_id'),'wrong'),
      (('domains',1,'choice','candidate_id'),'wrong'),(('domains',1,'choice','input','feedback_sha256'),'0'*64),
      (('domains',1,'choice','input','feedback','verdict'),'UNVERIFIED'),
      (('domains',0,'contract','experiment','owner'),'wrong'),(('domains',1,'contract','experiment','domain'),c.DOMAINS[0]),
      (('domains',0,'sdk','factory'),'wrong'),(('domains',1,'sdk','factory'),'wrong'),
      (('domains',0,'sdk','pid'),0),(('domains',1,'sdk','exit'),1),(('domains',0,'sdk','error'),'wrong'),
      (('domains',0,'sdk','report','provider_key_present'),True),(('domains',1,'sdk','report','business_key_present'),True),
      (('domains',0,'sdk','fault','planned'),False),(('domains',0,'sdk','fault','triggered'),False),
      (('domains',0,'sdk','fault','observed'),False),(('domains',0,'sdk','fault','agent_exposed'),False),
      (('domains',1,'sdk','fault','planned'),False),(('domains',1,'sdk','fault','triggered'),False),
      (('domains',1,'sdk','fault','observed'),False),(('domains',1,'sdk','fault','agent_exposed'),False),
      (('domains',1,'sdk','fault','transport_error'),'FORGED'),
      (('domains',0,'effect','backend'),'FAKE'),(('domains',1,'effect','backend'),'FAKE'),
      (('domains',0,'feedback','source_effect_sha256'),'0'*64),
      (('domains',1,'feedback','source_contract_sha256'),'0'*64),
      (('domains',0,'sdk','callbacks',0,'call','name'),'refund_order'),
      (('domains',1,'sdk','callbacks',0,'call','call_id'),'forged'),
      (('domains',1,'sdk','callbacks',1,'result','status'),'COMMITTED'),
      (('domains',1,'effect','after','data','order','refunded_minor'),0),
      (('domains',1,'effect','after','data','receipts',0,'amount_minor'),True)]
    for domain in (0,1):
        for key,value in [('output_tokens',-1),('input_tokens',True),('requests',0),('tool_calls',0),
                          ('tool_callbacks',0),('status','FAIL'),('pid',0),('version','wrong'),
                          ('openai_version','wrong'),('sdk_source_sha256','0'*64),
                          ('openai_source_sha256','0'*64),('final_text_persisted',True)]:
            fields.append((('domains',domain,'sdk','report',key),value))
    return fields


def negative(manifest_path, anchor):
    raw=formal_original(manifest_path,anchor,'F');c.require(c.sha(raw)==anchor,'ORIGINAL_ANCHOR')
    original=c.strict(raw);c.require(original['scenario']=='F','FAULT_ORIGINAL_REQUIRED')
    base=c.WORK/'negative'/'bulk';base.mkdir(parents=True,exist_ok=False)
    tests=[]
    for i,(field,value) in enumerate(slot_attacks()):
        tests.append(('SLOT_%02d'%i, lambda m,r,field=field,value=value:mutate_slot_request(m,r,field,value), 'SLOT'))
    for i,mode in enumerate(('prompt_plus','prompt_minus','completion_plus','completion_minus',
                             'both_plus','completion_zero','output_over_cap','prompt_over_cap')):
        tests.append(('COUPLED_%02d'%i,lambda m,r,mode=mode:mutate_coupled_usage(m,r,mode),'COUPLED'))
    for i,(field,value) in enumerate(manifest_attacks()):
        tests.append(('MANIFEST_%02d'%i, lambda m,r,field=field,value=value:mutate_manifest_path(m,r,field,value), 'MANIFEST'))
    results=[]
    for label,mutation,category in tests:
        try:
            path=deep_clone(original,base/label.lower().replace('_','-'),mutation)
            sha=c.sha(path.read_bytes())
            receipt=run_command('negative-'+label.lower().replace('_','-'),
                [sys.executable,'-X','utf8','-B','-m','spikes.rpf-74.rev-2.probe','verify',
                 '--manifest',str(path),'--sha256',sha],timeout=180)
            data=c.strict((c.WORK/'commands'/('negative-'+label.lower().replace('_','-'))/'stdout.raw').read_bytes())
            reason=data.get('reason','')
            accepted=receipt['exit']==3 and reason not in ('RAW_ANCHOR','SOURCE_IDENTITY','SOURCE_DRIFT') and bool(reason)
            results.append({'label':label,'category':category,'anchor':sha,'exit':receipt['exit'],
                            'reason':reason,'status':'PASS' if accepted else 'FAIL'})
        except (KeyError,ValueError,TypeError,OSError) as exc:
            results.append({'label':label,'category':category,'status':'TEST_INVALID','reason':type(exc).__name__})
    passed=[r for r in results if r['status']=='PASS']
    slot_count=sum(r['category'] in ('SLOT','COUPLED') for r in passed)
    coupled_count=sum(r['category']=='COUPLED' for r in passed)
    result={'status':'PASS' if len(passed)>=100 and slot_count>=35 and coupled_count>=8 and len(passed)==len(results) else 'FAIL',
            'attempts':len(results),'passed':len(passed),'slot_passed':slot_count,
            'coupled_passed':coupled_count,
            'test_invalid':sum(r['status']=='TEST_INVALID' for r in results),'cases':results}
    once(c.WORK/'negative-result.json',result)
    return result


def full_runtime():
    from runtime.runproof_runtime.effectwitness.pge_r74r2_owner_source import source_identity
    frozen=c.strict((c.WORK/'source-freeze.json').read_bytes())
    c.require(frozen['identity']==source_identity(),'SOURCE_DRIFT')
    # The historical runner contract insists on this ancestor name.  Only this
    # newly-created, random child is owned by the rev-3 task.
    owner_root=c.ROOT/'.local/rpf-73-rev-2'
    c.require(owner_root.is_dir() and not any(p.is_symlink() or p.is_junction() for p in
              (owner_root,*owner_root.parents)), 'HISTORICAL_OWNER_BOUNDARY')
    private=owner_root/('rpf-74-rev-3-regression-'+secrets.token_hex(8))
    private.mkdir(exist_ok=False)
    snap=snapshot('full',private/'snapshot')
    for name in ('rpf-55-rev2','rpf-56-rev4','rpf-57','rpf-58-rev2','rpf-59','rpf-60','rpf-67-rev4',
                 'rpf-68-rev3','rpf-69','rpf-70','rpf-71','rpf-72','rpf-72-rev-2','rpf-72-rev-3',
                 'rpf-73','rpf-73-rev-2','rpf-74','rpf-74-rev-2'):
        (snap/'.local'/name/'tests').mkdir(parents=True,exist_ok=True)
    work=private/'runner';work.mkdir();scratch=work/'scratch';scratch.mkdir()
    descriptor=work/'environment.json'
    spec=importlib.util.spec_from_file_location('rpf74r2_snapshot_environment',snap/'spikes/rpf-73/rev-2/environment_contract.py')
    old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
    contract=old.SuiteEnvironmentContract.build(scratch,descriptor,reference_root=c.ROOT,owner_root=owner_root)
    env=contract.check()['env']
    old.write_once(descriptor,dict(contract=contract.check(),cwd=str(snap),source_sha256=old.digest(old.source_identity())))
    inventory_code="import json,unittest\ns=unittest.TestLoader().discover('runtime/tests',pattern='test_*.py')\ndef walk(x):\n for y in x:\n  if isinstance(y,unittest.TestSuite): yield from walk(y)\n  else: yield y.id()\nprint(json.dumps(list(walk(s))))\n"
    inventory=run_command('full-inventory',[sys.executable,'-X','utf8','-B','-c',inventory_code],cwd=snap,env=env)
    c.require(inventory['exit']==0,'FULL_INVENTORY_FAILED')
    ids=c.strict((c.WORK/'commands/full-inventory/stdout.raw').read_bytes())
    c.require(len(ids)==len(set(ids)),'INVENTORY_DUPLICATE')
    allowed={prefix:[x for x in ids if x.startswith(prefix+'.')] for prefix in
             ('test_docker_integration.DockerIntegrationTests','test_rpf05_runtime.Rpf05RuntimeTests')}
    argv=[sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','runtime/tests','-p','test_*.py','-v']
    result=run_command('full-runtime-01',argv,cwd=snap,timeout=7200,env=env)
    log=(c.WORK/'commands/full-runtime-01/stderr.raw').read_text(encoding='utf-8',errors='replace')
    result['summary']=old.parse_summary(log)
    actual=[];skips=[];method_skips=[];pending=None
    for line in log.splitlines():
        match=re.match(r'^test\w* \(([^)]+)\) \.\.\. (.*)$',line)
        if match:
            c.require(pending is None,'INCOMPLETE_TEST_LINE')
            if re.fullmatch(r'ok|ERROR|FAIL|skipped .*',match[2]):
                actual.append(match[1])
                if match[2].startswith('skipped '):method_skips.append(match[1])
            else:pending=match[1]
        elif pending and line in ('ok','ERROR','FAIL'):
            actual.append(pending);pending=None
        skip=re.match(r'^setUpClass \(([^)]+)\) \.\.\. skipped (.*)$',line)
        if skip:skips.append({'class_id':skip[1],'reason':skip[2]})
    omitted=[item for row in skips if row['class_id'] in allowed and 'Docker provider unavailable:' in row['reason']
             for item in allowed[row['class_id']]]
    exact=collections.Counter(ids)==collections.Counter(actual+omitted)
    result.update(discovered=len(ids),actual_ids=len(actual),skipped_classes=skips,
                  skipped_methods=len(omitted),method_skips=method_skips,exact_multiset=exact)
    result['source_unchanged']=frozen['identity']==source_identity()
    result['snapshot_relative']=private.relative_to(c.ROOT).as_posix()
    observed=work/('actual-env-'+str(result['pid'])+'.json')
    actual_env=old.strict(observed.read_bytes()) if observed.is_file() else None
    result['actual_environment']=actual_env
    result['status']='PASS' if (result['exit']==0 and result['summary']['pass_summary'] and result['source_unchanged']
        and not result['summary']['errors'] and not result['summary']['failures'] and not method_skips
        and result['summary']['tests']==len(actual) and len(skips)==2 and len(omitted)==5 and exact and pending is None
        and actual_env is not None and actual_env['pid']==result['pid'] and
        actual_env['env_sha256']==contract.check()['env_sha256']) else 'FAIL'
    once(c.WORK/'runtime-result.json',result)
    return result
