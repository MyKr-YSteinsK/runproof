"""RPF-74 command entry; no provider access and no old private runtime roots."""
import argparse
import copy
import datetime
import importlib
import importlib.util
import json
import ntpath
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from runtime.runproof_runtime.effectwitness import pge_r74_contracts as c

def _set(obj, path, value):
    for key in path[:-1]:
        obj = obj[key]
    obj[path[-1]] = value

def _write_once(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as out:
        out.write(c.canonical(value)); out.flush(); os.fsync(out.fileno())

def require_freeze():
    from runtime.runproof_runtime.effectwitness.pge_r74_owner_source import source_identity
    frozen=c.strict((c.WORK/'source-freeze.json').read_bytes())
    c.require(frozen['identity']==source_identity() and frozen['source_sha256']==c.digest(frozen['identity']), 'SOURCE_FROZEN')
    return frozen

def freeze():
    from runtime.runproof_runtime.effectwitness.pge_r74_owner_source import source_identity
    evidence=c.strict((c.WORK/'pre-freeze-diffcheck.json').read_bytes())
    c.require(evidence['exit']==0 and evidence['paths']==list(c.SOURCE_NAMES), 'DIFFCHECK_BEFORE_FREEZE')
    identity=source_identity();git_blobs={}
    for name in c.SOURCE_NAMES:
        git_blobs[name]=subprocess.check_output(['git','hash-object','--',name],cwd=c.ROOT,text=True).strip()
    result=dict(owner=c.OWNER,abi=c.ABI,source_kind=c.SOURCE_KIND,identity=identity,source_sha256=c.digest(identity),
                git_blobs=git_blobs,source_files=list(c.SOURCE_NAMES),pre_freeze_diffcheck=evidence)
    _write_once(c.WORK/'source-freeze.json',result)
    print(json.dumps(dict(status='FROZEN',source_sha256=result['source_sha256'],files=len(git_blobs))))
    return 0

_COMMAND_ORDINAL = 0

def _invoke(command, path, anchor=None):
    global _COMMAND_ORDINAL
    _COMMAND_ORDINAL += 1
    argv=[sys.executable,'-X','utf8','-B','-m','spikes.rpf-74.probe',command,str(path)]
    if anchor is not None: argv.extend(['--sha256',anchor])
    start=time.time_ns(); before=time.monotonic()
    proc=subprocess.Popen(argv,cwd=c.ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try: stdout,stderr=proc.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        proc.terminate();stdout,stderr=proc.communicate(timeout=15)
    log=c.WORK/'negative'/'logs';log.mkdir(exist_ok=True)
    logname='command-%04d'%_COMMAND_ORDINAL
    for name,raw in ((logname+'.stdout',stdout),(logname+'.stderr',stderr)):
        with (log/name).open('xb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
    try: result=json.loads(stdout)
    except (ValueError,UnicodeError): result={'status':'TEST_INVALID'}
    return dict(argv=argv,cwd=str(c.ROOT),
                pid=proc.pid,parent_pid=os.getpid(),started_unix_ns=start,elapsed_seconds=time.monotonic()-before,
                exit=proc.returncode,stdout_sha256=c.sha(stdout),stderr_sha256=c.sha(stderr),
                stdout_log=(log/(logname+'.stdout')).relative_to(c.ROOT).as_posix(),
                stderr_log=(log/(logname+'.stderr')).relative_to(c.ROOT).as_posix(),stderr_empty=not stderr,result=result)

def _deep_clone(original, destination, index):
    """Rebind a negative copy and rehash its dependent local artifacts and WAL."""
    from runtime.runproof_runtime.effectwitness.pge_r73_launch_contract import env_summary
    m=copy.deepcopy(original); old_root=c.ROOT/m['context']['workspace']; root=destination/m['context']['session_id']
    root.mkdir(parents=True,exist_ok=False)
    m['context']['workspace']=root.relative_to(c.ROOT).as_posix()
    m['policy']['owner']['workspace']=m['context']['workspace'];m['policy_sha256']=c.digest(m['policy'])
    data=m['domains'][1]['effect']['after']['data']
    attacks=(('order','status','PAID'),('order','refunded_minor',2499),('order','paid_minor',2499),
             ('receipt','status','REJECTED'),('receipt','amount_minor',True),('receipt','receipt_id','forged-receipt'))
    group,key,value=attacks[index]; target=data['order'] if group=='order' else data['receipts'][0]; target[key]=value
    m['domains'][1]['effect']['after']['sha256']=c.digest(data)
    m['domains'][1]['feedback']['source_effect_sha256']=c.digest(m['domains'][1]['effect'])
    for row in m['domains']:
        ct=row['contract'];old_folder=old_root/'runs'/ct['experiment']['run_id'];new_folder=root/'runs'/ct['experiment']['run_id']
        (new_folder/'sdk').mkdir(parents=True)
        for name in ('stdout.raw','stderr.raw'):
            shutil.copyfile(old_folder/'sdk'/name,new_folder/'sdk'/name)
        launch=c.strict((old_folder/'sdk'/'launch-input.json').read_bytes())
        sdk_folder=new_folder/'sdk';launch['cwd']=str(sdk_folder);launch['cfg']['write_root']=str(sdk_folder)
        for key in ('HOME','USERPROFILE','TEMP','TMP'):launch['env'][key]=str(sdk_folder)
        launch['env_summary']=env_summary(launch['env'],sdk_folder);launch['cfg_sha256']=c.digest(launch['cfg'])
        _write_once(sdk_folder/'launch-input.json',launch)
        sdk=row['sdk'];sdk['cfg_sha256']=launch['cfg_sha256'];sdk['request_sha256']=c.digest(launch)
        sdk['env_observation'][0]['cwd_sha256']=c.sha(str(sdk_folder).encode())
        sdk['env_observation'][0]['env_sha256']=launch['env_summary']['sha256']
        if ct['experiment']['domain']==c.DOMAINS[1]:
            (new_folder/'business').mkdir()
            shutil.copyfile(old_folder/'business'/'orders.sqlite3',new_folder/'business'/'orders.sqlite3')
    previous_request=None;active_operation=None
    for frame in m['wal']:
        event=frame['event']
        if event['kind']=='OWNER':event['context_sha256']=c.digest(m['context'])
        if event.get('audit_type')=='RPF74_AUTHORIZATION':
            if event.get('status') in ('CHECK','GRANTED'):
                event['operation']['owner']=m['policy']['owner'];active_operation=c.digest(event['operation'])
                event['operation_sha256']=active_operation
            elif event.get('status')=='COMPLETED':
                event['operation_sha256']=active_operation
        if event.get('audit_type')=='RPF74_BUDGET':
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
    path=root/'manifest.json';_write_once(path,m)
    return path

def negative():
    """Execute bounded, independently anchored rejection probes without business writes."""
    require_freeze();work=c.WORK/'negative';work.mkdir(exist_ok=False)
    originals={}
    for scenario in ('N','F'):
        claim=c.strict((c.WORK/(scenario+'-result.json')).read_bytes())
        path=c.ROOT/claim['manifest'];raw=path.read_bytes();c.require(c.sha(raw)==claim['sha256'],'NEGATIVE_INPUT_ANCHOR')
        originals[scenario]=(path,c.strict(raw),c.sha(raw))
    baseline=[]
    for scenario,(path,_,anchor) in originals.items():
        for given,expected in ((anchor,0),(None,2),('0'*64,3)):
            result=_invoke('verify',path,given);c.require(result['exit']==expected,'NEGATIVE_BASELINE');baseline.append(result)
    npath,n,original_sha=originals['N'];ct=n['domains'][1]['contract']
    launch=c.strict((npath.parent/'runs'/ct['experiment']['run_id']/'sdk'/'launch-input.json').read_bytes())
    proposed=dict(context=n['context'],domain=c.DOMAINS[1],launch=launch)
    admission=[
      (('context','owner'),'wrong-owner'),(('context','abi'),'wrong-abi'),(('context','source_kind'),'WRONG_KIND'),
      (('context','source_capsule_sha256'),'0'*64),(('context','session_id'),'rpf73-old'),(('context','scenario'),'F'),
      (('context','ports'),[1234,1234,1234]),(('context','workspace'),'.local/escape'),
      (('domain',),'config-java-http'),(('domain',),'unknown'),(('launch','schema'),'old-abi'),
      (('launch','owner'),'rpf-73'),(('launch','source_kind'),'SYNTHETIC_ONLY'),(('launch','source_sha256'),'0'*64),
      (('launch','run_id'),'rpf74-0000000000000000'),(('launch','domain'),'config-java-http'),
      (('launch','scenario'),'F'),(('launch','cwd'),'D:\\unsafe'),(('launch','timeout_seconds'),901),
      (('launch','issuer'),True),(('launch','argv',0),'C:\\unknown\\python.exe'),
      (('launch','argv',1),'-c'),(('launch','argv',4),'unsafe'),(('launch','windows_command'),'unsafe & command'),
      (('launch','env','PYTHONPATH'),'C:\\unknown'),(('launch','env','PATH'),'C:\\unknown'),
      (('launch','env','HOME'),'D:\\unknown'),(('launch','env','TEMP'),'..\\unsafe'),
      (('launch','env','PYTHONDONTWRITEBYTECODE'),'0'),(('launch','env','SYSTEMROOT'),'\\\\server\\root'),
      (('launch','env','CONFIG_CENTER_API_KEY'),'dummy'),(('launch','env','TMP'),True),
      (('launch','cfg','port'),True),(('launch','cfg','token'),'invalid'),
      (('launch','cfg','total_token_limit'),True),(('launch','cfg','total_token_limit'),160001),
      (('launch','cfg','sdk_readonly_path'),'D:\\unknown'),(('launch','cfg','sdk_site_root_binding_sha256'),'0'*64),
      (('launch','cfg','instructions'),'forged'),(('launch','cfg','task_prompt'),'forged'),
      (('launch','cfg','domain'),'config-java-http'),(('launch','cfg','unexpected'),True),
      (('launch','unexpected'),True)]
    cases=[];seen=set()
    for number,(field,value) in enumerate(admission,1):
        mutant=copy.deepcopy(proposed);_set(mutant,field,value)
        if field[:2]==('launch','cfg'):mutant['launch']['cfg_sha256']=c.digest(mutant['launch']['cfg'])
        path=work/'admission'/('case-%03d.json'%number);_write_once(path,mutant);sha=c.sha(path.read_bytes())
        c.require(sha not in seen,'NEGATIVE_DUPLICATE');seen.add(sha);result=_invoke('admit',path,sha)
        cases.append(dict(category='PRE_SIDE_EFFECT_ADMISSION',field=list(field),original_sha256=c.digest(proposed),
                          mutated_sha256=sha,expected_exit=3,business_touched=False,command=result))
    fpath,f,fsha=originals['F']
    fields=[
      (('owner',),'old-owner'),(('abi',),'old-abi'),(('schema',),'wrong-schema'),(('source_kind',),'REAL_PROVIDER'),
      (('scenario',),'N'),(('provider_calls',),1),(('issuer',),True),(('child_attestation',),True),
      (('model_source',),'REAL_PROVIDER'),(('source_sha256',),'0'*64),
      (('context','owner'),'wrong-owner'),(('context','abi'),'wrong-abi'),(('context','source_kind'),'wrong'),
      (('context','scenario'),'N'),(('context','session_id'),'rpf73-old'),(('context','source_capsule_sha256'),'0'*64),
      (('policy','provider_calls'),1),(('policy','one_native_wal'),False),(('policy','refundable'),True),
      (('policy','source'),'0'*64),(('domains',0,'choice','candidate_id'),'forged'),
      (('domains',1,'choice','candidate_id'),'forged'),(('domains',1,'choice','input','feedback_sha256'),'0'*64),
      (('domains',1,'choice','input','feedback','verdict'),'UNVERIFIED'),
      (('domains',0,'contract','experiment','owner'),'rpf-73'),(('domains',1,'contract','experiment','domain'),c.DOMAINS[0]),
      (('domains',0,'sdk','factory'),'old-factory'),(('domains',1,'sdk','factory'),'old-factory'),
      (('domains',0,'sdk','pid'),0),(('domains',1,'sdk','exit'),1),(('domains',0,'sdk','error'),'forged'),
      (('domains',0,'sdk','report','provider_key_present'),True),(('domains',1,'sdk','report','business_key_present'),True),
      (('domains',0,'sdk','fault','planned'),False),(('domains',0,'sdk','fault','triggered'),False),
      (('domains',0,'sdk','fault','observed'),False),(('domains',0,'sdk','fault','agent_exposed'),False),
      (('domains',1,'sdk','fault','planned'),False),(('domains',1,'sdk','fault','triggered'),False),
      (('domains',1,'sdk','fault','observed'),False),(('domains',1,'sdk','fault','agent_exposed'),False),
      (('domains',1,'sdk','fault','transport_error'),'FORGED'),(('domains',1,'sdk','fault','committed_sha256'),'0'*64),
      (('domains',0,'effect','backend'),'FAKE'),(('domains',1,'effect','backend'),'FAKE'),
      (('domains',0,'feedback','source_effect_sha256'),'0'*64),
      (('domains',1,'feedback','source_contract_sha256'),'0'*64),
      (('domains',0,'sdk','callbacks',0,'call','name'),'refund_order'),
      (('domains',1,'sdk','callbacks',0,'call','call_id'),'forged'),
      (('domains',1,'sdk','callbacks',1,'result','status'),'COMMITTED'),
      (('domains',1,'effect','after','data','order','refunded_minor'),0),
      (('domains',1,'effect','after','data','receipts',0,'amount_minor'),True)]
    for number,(field,value) in enumerate(fields,1):
        mutant=copy.deepcopy(f);_set(mutant,field,value)
        if field[0]=='policy':mutant['policy_sha256']=c.digest(mutant['policy'])
        path=fpath.parent/('negative-%03d.json'%number);_write_once(path,mutant);sha=c.sha(path.read_bytes())
        c.require(sha not in seen,'NEGATIVE_DUPLICATE');seen.add(sha);result=_invoke('verify',path,sha)
        cases.append(dict(category='CROSS_DOMAIN_BUSINESS_FAULT_FEEDBACK',field=list(field),original_sha256=fsha,
                          mutated_sha256=sha,expected_exit=3,business_touched=False,command=result))
    for index in range(6):
        path=_deep_clone(f,work/('deep-%02d'%index),index);sha=c.sha(path.read_bytes())
        c.require(sha not in seen,'NEGATIVE_DUPLICATE');seen.add(sha);result=_invoke('verify',path,sha)
        cases.append(dict(category='DEEP_REANCHOR',field=['order_authority',index],original_sha256=fsha,
                          mutated_sha256=sha,expected_exit=3,business_touched=False,command=result))
    accepted=[x for x in cases if x['command']['exit']==3 and x['command']['result'].get('status')=='REJECTED'
              and re.fullmatch('[A-Z0-9_]+',x['command']['result'].get('reason','')) and x['command']['stderr_empty']
              and (x['category']!='DEEP_REANCHOR' or x['command']['result'].get('reason') in
                   ('ORDER_AUTHORITY','ORDER_DATABASE_AUTHORITY'))]
    counts={k:sum(x['category']==k for x in accepted) for k in ('PRE_SIDE_EFFECT_ADMISSION',
              'CROSS_DOMAIN_BUSINESS_FAULT_FEEDBACK','DEEP_REANCHOR')}
    passed=len(accepted)>=80 and counts['PRE_SIDE_EFFECT_ADMISSION']>=30 and counts['CROSS_DOMAIN_BUSINESS_FAULT_FEEDBACK']>=20 and counts['DEEP_REANCHOR']>=6 and len(accepted)==len(cases)
    result=dict(status='PASS' if passed else 'FAIL',count=len(accepted),counts=counts,baseline=baseline,cases=cases,
                source_sha256=c.digest(__import__('runtime.runproof_runtime.effectwitness.pge_r74_owner_source',fromlist=['source_identity']).source_identity()),
                test_invalid=len(cases)-len(accepted),business_writes=0)
    _write_once(c.WORK/'negative-result.json',result)
    print(json.dumps(dict(status=result['status'],count=result['count'],counts=counts)))
    return 0 if passed else 1

def history():
    require_freeze();work=c.WORK/'history';work.mkdir(exist_ok=False)
    entries=c.strict((c.ROOT/'spikes/rpf-73/history-regression.json').read_bytes())['commands']
    c.require(len(entries)==27,'HISTORY_ENTRY_COUNT')
    rows=[]
    for index,entry in enumerate(entries):
        command=entry['command']
        c.require(command[:4]==['python','-X','utf8','-B'] and not any('.local' in x for x in command),
                  'HISTORY_PUBLIC_ONLY')
        argv=[sys.executable,*command[1:]];start=time.time_ns();before=time.monotonic()
        proc=subprocess.Popen(argv,cwd=c.ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:stdout,stderr=proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:proc.terminate();stdout,stderr=proc.communicate(timeout=15)
        for suffix,raw in (('stdout',stdout),('stderr',stderr)):
            with (work/('history-%02d.%s'%(index,suffix))).open('xb') as f:
                f.write(raw);f.flush();os.fsync(f.fileno())
        rows.append(dict(label='history-%02d'%index,argv=argv,cwd=str(c.ROOT),pid=proc.pid,parent_pid=os.getpid(),
                         started_unix_ns=start,elapsed_seconds=time.monotonic()-before,exit=proc.returncode,
                         expected_exit=entry['exit'],stdout_sha256=c.sha(stdout),stderr_sha256=c.sha(stderr),
                         status='PASS' if proc.returncode==entry['exit'] else 'FAIL'))
    value=dict(status='PASS' if all(row['status']=='PASS' for row in rows) else 'FAIL',rows=rows,
               native_public_entries=24,r69_exits=[0,2,3],old_private_roots='NOT_READ')
    _write_once(c.WORK/'history-result.json',value)
    print(json.dumps(dict(status=value['status'],commands=len(rows))))
    return 0 if value['status']=='PASS' else 1

def full_runtime():
    """Run one original discovery in the expressly authorized new snapshot."""
    started=datetime.datetime(2026,10,27,3,5,15,tzinfo=datetime.timezone.utc)
    c.require((datetime.datetime.now(datetime.timezone.utc)-started).total_seconds()+7200+600 < 16200,
              'INSUFFICIENT_TASK_WALL_BUDGET')
    require_freeze()
    from runtime.runproof_runtime.effectwitness.pge_r74_owner_source import source_identity
    original=source_identity();owner=c.ROOT/'.local/rpf-73-rev-2'
    snapshot=owner/'rpf-74-regression-20261027'
    c.require(not snapshot.exists() and not owner.is_symlink() and not owner.is_junction(), 'FULL_SNAPSHOT_SCOPE')
    marker=c.WORK/'full-claim.json'
    _write_once(marker,dict(snapshot=snapshot.relative_to(c.ROOT).as_posix(),source_sha256=c.digest(original),attempt=1))
    snapshot.mkdir(exist_ok=False)
    roots=['runtime','spikes','demo','ci','control-plane','.github','AGENTS.md','.gitignore','README.md','README.zh-CN.md','web/README.md']
    names=set(subprocess.check_output(['git','ls-files','--',*roots],cwd=c.ROOT,text=True).splitlines())
    names.update('docs/'+stem+suffix for stem in ('ARCHITECTURE','RELIABILITY_MODEL','DEMO','GLOSSARY') for suffix in ('.md','.zh-CN.md'))
    contracts=importlib.import_module('runtime.runproof_runtime.effectwitness.lab_cross_domain_contracts')
    names.update(contracts.NEW_FILES+contracts.OLD_FILES)
    hashes={}
    for name in sorted(names):
        c.require(not name.startswith(('.local/','docs/reviews/','docs/project/','docs/history/')), 'SNAPSHOT_PROTECTED')
        source=c.ROOT/name
        if not source.is_file():continue
        c.require(not any(p.is_symlink() or p.is_junction() for p in (source,*source.parents)), 'SNAPSHOT_SOURCE_LINK')
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True)
        with source.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
        hashes[name]=c.sha(source.read_bytes());c.require(c.sha(target.read_bytes())==hashes[name], 'SNAPSHOT_BYTES')
    for name in ('rpf-55-rev2','rpf-56-rev4','rpf-57','rpf-58-rev2','rpf-59','rpf-60','rpf-67-rev4',
                 'rpf-68-rev3','rpf-69','rpf-70','rpf-71','rpf-72','rpf-72-rev-2','rpf-72-rev-3',
                 'rpf-73','rpf-73-rev-2','rpf-74'):
        (snapshot/'.local'/name/'tests').mkdir(parents=True,exist_ok=True)
    _write_once(c.WORK/'full-snapshot-index.json',dict(snapshot=snapshot.relative_to(c.ROOT).as_posix(),
                source_sha256=c.digest(original),files=hashes))
    contract_file=snapshot/'spikes/rpf-73/rev-2/environment_contract.py'
    spec=importlib.util.spec_from_file_location('rpf74_full_frozen_r73_environment',contract_file)
    e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)
    c.require(e.digest(e.source_identity())=='6fc5ec95b69953bb891f4e58d5fc1d62a89177cc099b2f0114b80203d53f9979',
              'R73_RUNNER_IDENTITY')
    folder=snapshot/'rpf74-command';folder.mkdir();scratch=folder/'scratch';scratch.mkdir();descriptor=folder/'environment.json'
    host={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH')}
    host['COMSPEC']=ntpath.join(host['SYSTEMROOT'],'System32','cmd.exe');host['PATHEXT']='.COM;.EXE;.BAT;.CMD'
    env_contract=e.SuiteEnvironmentContract.build(scratch,descriptor,host=host,reference_root=c.ROOT,owner_root=owner)
    value=env_contract.check();e.write_once(descriptor,dict(contract=value,cwd=str(snapshot),source_sha256=e.digest(e.source_identity())))
    inventory_code="""import json,unittest\ns=unittest.TestLoader().discover('runtime/tests',pattern='test_*.py')\ndef walk(x):\n for y in x:\n  if isinstance(y,unittest.TestSuite): yield from walk(y)\n  else: yield y.id()\nprint(json.dumps(list(walk(s))))\n"""
    inv=subprocess.run([value['python'],'-X','utf8','-B','-c',inventory_code],cwd=snapshot,env=value['env'],
                       stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
    c.require(inv.returncode==0 and not inv.stderr,'INVENTORY_PROCESS')
    ids=c.strict(inv.stdout);c.require(type(ids) is list and len(ids)==len(set(ids)),'INVENTORY_IDS')
    allowed={prefix:[x for x in ids if x.startswith(prefix+'.')] for prefix in
             ('test_docker_integration.DockerIntegrationTests','test_rpf05_runtime.Rpf05RuntimeTests')}
    _write_once(c.WORK/'full-inventory.json',dict(ids=ids,discovered=len(ids),allowed_class_skips=allowed,
                stdout_sha256=c.sha(inv.stdout),snapshot_source_sha256=c.digest(original)))
    argv=[value['python'],'-X','utf8','-B','-m','unittest','discover','-s','runtime/tests','-p','test_*.py','-v']
    log=folder/'full-output.log';start=time.time_ns();before=time.monotonic()
    with log.open('xb') as output:
        proc=subprocess.Popen(argv,cwd=snapshot,env=value['env'],stdin=subprocess.DEVNULL,stdout=output,
                              stderr=subprocess.STDOUT,close_fds=True)
        _write_once(c.WORK/'full-started.json',dict(pid=proc.pid,parent_pid=os.getpid(),started_unix_ns=start,
                    argv=argv,cwd=str(snapshot),env=env_contract.redacted(),source_sha256=c.digest(original),timeout=7200))
        timed=False
        try:exit_code=proc.wait(timeout=7200)
        except subprocess.TimeoutExpired:
            timed=True;proc.terminate();exit_code=proc.wait(timeout=15)
    raw=log.read_bytes();summary=e.parse_summary(raw.decode('utf-8',errors='replace'))
    c.require(source_identity()==original,'SOURCE_CHANGED_DURING_FULL')
    for name,sha in hashes.items():
        c.require(c.sha((snapshot/name).read_bytes())==sha and c.sha((c.ROOT/name).read_bytes())==sha,'SNAPSHOT_DRIFT')
    import collections
    actual=[];skips=[];method_skips=[];pending=None
    for line in raw.decode('utf-8',errors='replace').splitlines():
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
        if skip:skips.append(dict(class_id=skip[1],reason=skip[2]))
    omitted=[item for row in skips if row['class_id'] in allowed and 'Docker provider unavailable:' in row['reason'] for item in allowed[row['class_id']]]
    exact=collections.Counter(ids)==collections.Counter(actual+omitted)
    observed=folder/('actual-env-'+str(proc.pid)+'.json')
    env_observation=e.strict(observed.read_bytes()) if observed.is_file() else None
    status='PASS' if (exit_code==0 and not timed and summary['pass_summary'] and not summary['errors'] and
            not summary['failures'] and not method_skips and summary['tests']==len(actual) and len(skips)==2 and len(omitted)==5 and exact and
            pending is None and env_observation is not None and env_observation['pid']==proc.pid and
            env_observation['env_sha256']==value['env_sha256']) else 'FAIL'
    result=dict(status=status,argv=argv,cwd=str(snapshot),pid=proc.pid,parent_pid=os.getpid(),started_unix_ns=start,
                elapsed_seconds=time.monotonic()-before,exit=exit_code,timed_out=timed,summary=summary,
                discovered=len(ids),actual_ids=len(actual),skipped_classes=skips,skipped_methods=len(omitted),method_skips=method_skips,
                exact_multiset=exact,source_sha256=c.digest(original),snapshot_files=len(hashes),
                stdout_sha256=c.sha(raw),log=str(log),env=env_contract.redacted(),actual_environment=env_observation)
    _write_once(c.WORK/'full-result.json',result)
    print(json.dumps({k:result[k] for k in ('status','exit','summary','discovered','actual_ids','skipped_methods','exact_multiset')}))
    return 0 if status=='PASS' else 1

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run'); run.add_argument('scenario', choices=('N','F'))
    verify = sub.add_parser('verify'); verify.add_argument('manifest'); verify.add_argument('--sha256')
    admit = sub.add_parser('admit'); admit.add_argument('manifest'); admit.add_argument('--sha256')
    sub.add_parser('negative')
    sub.add_parser('history')
    sub.add_parser('full')
    sub.add_parser('freeze')
    sub.add_parser('diagnostic')
    smoke = sub.add_parser('smoke'); smoke.add_argument('domain', choices=('config','order'))
    args = parser.parse_args()
    if args.command == 'diagnostic':
        print(json.dumps(dict(owner=c.OWNER, abi=c.ABI, source_kind=c.SOURCE_KIND, provider=0)))
        return 0
    if args.command in ('verify','admit'):
        if args.sha256 is None:
            print(json.dumps(dict(status='UNANCHORED')))
            return 2
        try:
            if args.command == 'verify':
                from runtime.runproof_runtime.effectwitness.pge_r74_verify import verify as check
                result = check(Path(args.manifest), args.sha256)
            else:
                from runtime.runproof_runtime.effectwitness.pge_r74_verify import _scope
                from runtime.runproof_runtime.effectwitness.pge_r74_owner_source import Context, OwnerScope, SourceCapsule
                from runtime.runproof_runtime.effectwitness.pge_r74_launch_contract import LaunchRequest
                raw=_scope(Path(args.manifest)).read_bytes()
                c.require(re.fullmatch('[0-9a-f]{64}',args.sha256) and c.sha(raw)==args.sha256,'RAW_ANCHOR')
                bundle=c.strict(raw);c.require(c.canonical(bundle)==raw and set(bundle)=={'context','domain','launch'},'ADMIT_FIELDS')
                value=bundle['context'];ctx=Context(OwnerScope(value['session_id']),SourceCapsule.observe(),value['ports'],value['scenario'])
                c.require(ctx.public()==value and bundle['domain'] in c.DOMAINS,'ADMIT_CONTEXT')
                ct=value['rounds'][c.DOMAINS.index(bundle['domain'])]
                LaunchRequest(c.canonical(bundle['launch'])).check(ctx,ct)
                result=dict(status='PASS',phase='PRE_SIDE_EFFECT_ADMISSION')
            print(json.dumps(result, sort_keys=True))
            return 0
        except (OSError, ValueError, TypeError, KeyError, IndexError, sqlite3.Error) as error:
            reason=str(error) if type(error) is ValueError and re.fullmatch('[A-Z0-9_]+',str(error)) else type(error).__name__
            print(json.dumps(dict(status='REJECTED',reason=reason)))
            return 3
    if args.command == 'negative':
        return negative()
    if args.command == 'history':
        return history()
    if args.command == 'full':
        return full_runtime()
    if args.command == 'freeze':
        return freeze()
    if args.command == 'smoke':
        from runtime.runproof_runtime.effectwitness.pge_r74_session import allocate_ports, JAR
        from runtime.runproof_runtime.effectwitness.pge_r74_owner_source import Context, OwnerScope, SourceCapsule
        from runtime.runproof_runtime.effectwitness.pge_r74_budget_gate import BudgetLedger
        from runtime.runproof_runtime.effectwitness.pge_r74_domain_ports import ConfigPort, OrderPort
        from runtime.runproof_runtime.effectwitness.pge_r74_launch_contract import LaunchRequest
        from runtime.runproof_runtime.effectwitness.pge_r74_launch_factory import LaunchFactory
        import secrets, shutil
        from runtime.runproof_runtime.effectwitness import pge_r68_contracts as native
        marker=c.WORK/('smoke-'+args.domain+'-claim.json')
        owner=OwnerScope('rpf74-'+secrets.token_hex(8)); source=SourceCapsule.observe()
        with marker.open('xb') as stream:
            stream.write(c.canonical(dict(run_id=owner.run_id,source_sha256=source.raw_sha256,kind='DEVELOPMENT_ONLY')))
            stream.flush();__import__('os').fsync(stream.fileno())
        ctx=Context(owner,source,allocate_ports(),'N');owner.root.mkdir(parents=True,exist_ok=False)
        ctx.once(ctx.root/'context.json',ctx.public());ledger=BudgetLedger(ctx,create=True)
        if args.domain == 'order':
            ledger.append('FEEDBACK_FROZEN',domain=c.DOMAINS[0],round=1,feedback={'kind':'DEVELOPMENT_FIXTURE_ONLY'})
            ct=ctx.public()['rounds'][1];port=OrderPort()
        else:
            target=ctx.scope(ctx.root/'jar/config-center-server-1.0.0.jar');target.parent.mkdir()
            c.require(c.sha(JAR.read_bytes())==native.SOURCE_JAR_SHA256 and JAR.stat().st_size==native.SOURCE_JAR_BYTES,'JAR_PIN')
            with JAR.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
            c.require(c.sha(target.read_bytes())==native.SOURCE_JAR_SHA256,'JAR_COPY')
            ct=ctx.public()['rounds'][0];port=ConfigPort()
        try:
            port.prepare(ctx,ct,ledger)
            result=LaunchFactory().launch(ctx,ct,ledger,port,LaunchRequest.build(ctx,ct))
            effect=port.finish();cleanup=port.cleanup();port=None
            c.require(all(cleanup.values()),'SMOKE_CLEANUP')
            ctx.once(ctx.root/'smoke-result.json',dict(status='PASS',kind='DEVELOPMENT_ONLY',sdk=result,effect=effect,cleanup=cleanup))
            print(json.dumps(dict(status='PASS',kind='DEVELOPMENT_ONLY',domain=args.domain,pid=result['pid'])))
            return 0
        finally:
            if port is not None:
                try:port.cleanup()
                except BaseException:pass
    require_freeze()
    from runtime.runproof_runtime.effectwitness.pge_r74_session import run as execute
    from runtime.runproof_runtime.effectwitness.pge_r74_verify import verify as check
    if args.scenario == 'F':
        previous=c.strict((c.WORK/'N-result.json').read_bytes())
        check(c.ROOT/previous['manifest'],previous['sha256'])
    path = execute(args.scenario)
    sha = c.sha(path.read_bytes())
    result = check(path, sha)
    payload = dict(status='VERIFIED', scenario=args.scenario, manifest=path.relative_to(c.ROOT).as_posix(), sha256=sha)
    with (c.WORK/(args.scenario+'-result.json')).open('xb') as stream:
        stream.write(c.canonical(payload)); stream.flush(); __import__('os').fsync(stream.fileno())
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == '__main__':
    sys.exit(main())
