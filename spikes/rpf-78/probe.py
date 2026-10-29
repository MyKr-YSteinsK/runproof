"""Offline generation, source/model freeze, replay and negative preparation."""
import argparse
import copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime'))
from runproof_runtime.effectwitness import pge_r78_contracts as c
from runproof_runtime.effectwitness.pge_r78_calibration import fit
from runproof_runtime.effectwitness.pge_r78_replay import run
from runproof_runtime.effectwitness.pge_r78_verify import verify,verify_file


def guard(event,args):
    if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.posix_spawn'):raise c.Invalid('OFFLINE_OPERATION_FORBIDDEN')


sys.addaudithook(guard)


def make_cases(split,count):
    cases=[]
    for i in range(count):
        kind=i%14;cid=split.replace('_','-')+'-'+str(i).zfill(2);domain=('lab-amber','lab-bronze','lab-cobalt')[i%3]
        size=1+i%(3 if split!='challenge' else 6);snapshot=cid+'-snapshot'
        pool=[];outcomes={}
        for j in range(size):
            if split=='fit':
                bucket='HIGH' if i<12 else 'RARE' if i in (22,23) and j==0 else 'LOW'
                useful=int(i%5!=0) if i<12 else int(i%5==0);cost=2+j;risk=j%3
            else:
                bucket='LOW' if kind in (1,6) else 'RARE' if kind==3 else 'UNSEEN' if kind==4 else 'HIGH'
                useful=0 if kind in (0,6) else 1;cost=(5 if kind==2 else 6 if kind==6 else 3 if kind==1 else 2)+j
                risk=2 if kind==10 else 0
            x=dict(candidate_id=domain+'-'+cid+'-c'+str(j),snapshot_id=snapshot,domain=domain,feature_kind=bucket,
                feature_status='UNKNOWN' if split!='fit' and kind==7 else 'KNOWN',visible_at=0,valid_until=100,
                source_id='source-'+cid+'-c'+str(j),source_sha256='',source_kind='SYNTHETIC_CONTRACT',benefit_units=8+2*j,
                cost=cost,risk=risk,permission='simulate',requires=['fact-00'],effect_keys=['fact-'+str(j+1).zfill(2)],
                verification_need=0 if bucket=='LOW' else 1,freshness_need=0 if bucket=='LOW' else 1,
                value_update_kind='NONE' if bucket=='LOW' else 'UPDATE',order=j,repeat=False)
            pool.append(x);outcomes[x['candidate_id']]=dict(outcome_id='outcome-'+cid+'-c'+str(j),useful_effect=useful,
                status='UNKNOWN' if split!='fit' and kind==13 and j==0 else 'VERIFIED',facts={'fact-'+str(j+1).zfill(2):'observed-'+str(j)})
        v=dict(schema=c.ABI,case_id=cid,split=split,domain=domain,snapshot_id=snapshot,candidates=pool,budget=0 if split!='fit' and kind==11 else 20,
            risk_cap=0 if split!='fit' and kind==10 else 2,permissions=['observe','simulate'],deadline=6,max_steps=2,
            initial_elapsed=1 if split!='fit' and kind==8 else 0,initial_unknown=[domain] if split!='fit' and kind==9 else ['lab-unrelated'] if split!='fit' and kind==13 else [])
        r=dict(evidence_id=cid+'-initial',case_id=cid,domain=domain,snapshot_id=snapshot,visible_at=0,seq=1,
            valid_until=0 if split!='fit' and kind==8 else 100,source_kind='FROZEN_SYNTHETIC',status='VERIFIED',facts={'fact-00':'ready'},contract_sha256='')
        records=[r]
        if split!='fit' and kind==12:records.append(dict(r,evidence_id=cid+'-conflict',facts={'fact-00':'conflict'}))
        case=dict(view=c.normalize(v),records=records,roster={},roster_sha256='',outcomes=outcomes,design='fit-predefined' if split=='fit' else 'kind-'+str(kind),parent_raw_sha256='',transform='NONE')
        c.seal(case);c.case_valid(case);cases.append(case)
    return cases


def generate():
    c.require(not (c.WORK/'source-freeze.json').exists(),'ALREADY_FROZEN')
    dev=dict(schema=c.ABI,owner=c.OWNER,seed=7801,fit=make_cases('fit',24),development_validation=make_cases('development_validation',12),exposure='DEVELOPMENT')
    challenge=dict(schema=c.ABI,owner=c.OWNER,seed=7802,challenge=make_cases('challenge',18),exposure='AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND')
    for rel,value in zip(c.INPUTS,(dev,challenge)):
        with (c.ROOT/rel).open('xb') as f:f.write(c.canonical(value))
    c.catalogs();return dict(status='PASS',fit=24,development_validation=12,challenge=18)


def reanchor(v):
    v['model_raw_sha256']=c.digest(v['model'])
    for runrow in v['runs']:
        previous='0'*64
        for row in runrow['rows']:
            row['previous_sha256']=previous;row['sha256']=c.digest({k:z for k,z in row.items() if k!='sha256'});previous=row['sha256']
    v['result_sha256']=c.digest({k:z for k,z in v.items() if k!='result_sha256'});return v


def specs():
    r=('runs',0,'rows',0);d=r+('decision',);x=('runs',0,'snapshot','candidates',0);b=('model','buckets','HIGH')
    return [
        ('schema',('schema',),'future'),('owner',('owner',),'other'),('source',('source_sha256',),'0'*64),
        ('blind-claim',('exposure',),'BLIND'),('model-count',b+('n',),0),('model-positive',b+('positive',),24),
        ('model-probability',b+('p_hat',),1.0),('model-lower-bound',b+('lower',),1.0),
        ('model-method',('model','method'),'self-signed'),('model-min-support',('model','min_n'),0),
        ('false-zero-model-count',('model','buckets','RARE','positive'),False),
        ('fit-validation-mix',('model','fit_case_ids'),['development-validation-00']),
        ('challenge-fit-leak',('model','fit_outcome_ids'),['outcome-challenge-00-c0']),
        ('fit-partition',('model','fit_partition'),'challenge'),('fit-input-anchor',('model','fit_input_sha256'),'1'*64),
        ('fake-high-support',('model','buckets','RARE','status'),'SUPPORTED'),
        ('cross-split',('runs',0,'split'),'challenge'),('candidate-domain',x+('domain',),'lab-foreign'),
        ('candidate-snapshot',x+('snapshot_id',),'foreign'),('candidate-benefit',x+('benefit_units',),99),
        ('candidate-cost',x+('cost',),0),('candidate-source',x+('source_sha256',),'2'*64),
        ('candidate-unknown',x+('feature_kind',),'UNSEEN'),('false-zero-step',r+('state','step'),False),
        ('negative-budget',r+('state','remaining'),-1),('snapshot-anchor',r+('snapshot_sha256',),''),
        ('roster-self-anchor',r+('roster','entries','self-issued'),'3'*64),
        ('future-record',r+('records',0,'visible_at'),1),('cross-domain-record',r+('records',0,'domain'),'lab-foreign'),
        ('expired-record',r+('records',0,'valid_until'),0),('forged-verified',r+('records',0,'source_kind'),'MODEL_ASSERTION'),
        ('low-support-select',('runs',12,'rows',0,'decision','action'),'SELECT'),
        ('unknown-select',('runs',36,'rows',0,'decision','action'),'SELECT'),
        ('interval-net-forgery',d+('ranking',0,'lower_net'),999),('point-net-forgery',d+('ranking',0,'point_net'),999),
        ('forecast-count',d+('ranking',0,'n'),999),('forecast-source',d+('evidence','accepted'),[]),
        ('out-of-pool',d+('candidate_id',),'lab-amber-invented'),('oracle-stop',r+('oracle','verdict'),'MUST_STOP'),
        ('oracle-net',r+('oracle','net_units','lab-amber-development-validation-00-c0'),999),
        ('outcome-useful',r+('outcome','useful_effect'),1),('prediction-label',('predictions',0,'observed_useful'),1),
        ('hidden-missed',('comparison','table',8,'missed_opportunity'),0),
        ('fake-abstention',('comparison','table',8,'abstention_count'),0),
        ('abstention-denominator',('comparison','summaries','development_validation','R78-BOUNDED_ABSTAIN','abstention_appropriateness','denominator'),0),
        ('calibration-denominator',('comparison','prediction_quality','development_validation','brier','denominator'),0),
        ('coverage-forgery',('comparison','summaries','challenge','R78-BOUNDED_ABSTAIN','coverage','numerator'),999),
        ('row-sequence',r+('seq',),2),
        ('row-hash-order',r+('previous_sha256',),'f'*64),
        ('after-abstention',('runs',8,'rows'),[]),
        ('ranking-permutation',('runs',9,'rows',0,'decision','ranking'),[]),
    ]


def change(v,path,value):
    node=v
    for k in path[:-1]:node=node[k]
    c.require((type(node) is dict and path[-1] not in node) or not c.equal(node[path[-1]],value),'TEST_INVALID_NO_OP');node[path[-1]]=value


def mutant(original,index):
    v=copy.deepcopy(original);items=specs()
    if index<len(items):
        name,path,value=items[index]
        if name=='after-abstention':
            first=copy.deepcopy(original['runs'][8]['rows'][0]);second=copy.deepcopy(first);second['seq']=2;value=[first,second]
        if name=='ranking-permutation':value=list(reversed(copy.deepcopy(original['runs'][9]['rows'][0]['decision']['ranking'])))
        change(v,path,value)
    else:
        n=index-len(items);name='compound-%02d'%(n+1)
        for j in ((4,35),(7,33),(9,31),(11,42),(12,41),(19,34),(27,26),(43,44))[n]:
            _,path,value=items[j];change(v,path,value)
        for runrow in v['runs']:
            for row in runrow['rows']:
                for record in row['records']:row['roster']['entries'][record['evidence_id']]=c.digest(record)
                row['roster_sha256']=c.digest(row['roster'])
        if n==5:
            snap=v['runs'][0]['snapshot'];c.seal(dict(view=snap,records=[],roster={},roster_sha256=''))
            v['runs'][0]['rows'][0]['snapshot_sha256']=c.snapshot_sha(snap)
    reanchor(v)
    if name=='row-hash-order':
        row=v['runs'][0]['rows'][0];row['previous_sha256']='f'*64;row['sha256']=c.digest({k:z for k,z in row.items() if k!='sha256'})
        v['result_sha256']=c.digest({k:z for k,z in v.items() if k!='result_sha256'})
    return name,v


def prepare(original,directory):
    verify(original);directory=c.allowed_file(Path(directory)/'scope.json').parent;directory.mkdir(parents=True,exist_ok=False);entries=[]
    for i in range(len(specs())+8):
        name,v=mutant(original,i);raw=c.canonical(v);path=directory/(name+'.json')
        with path.open('xb') as f:f.write(raw)
        entries.append(dict(name=name,file=path.relative_to(c.ROOT).as_posix(),original_sha256=c.digest(original),raw_sha256=c.sha(raw),compound=i>=len(specs()),expected_exit=3))
    value=dict(status='PREPARED_NOT_EXECUTED',controls=entries);(directory/'controls.json').write_bytes(c.canonical(value));return value


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('generate','freeze','fit','run','verify','negative'));p.add_argument('--file');p.add_argument('--sha');p.add_argument('--directory');p.add_argument('--stress',action='store_true');p.add_argument('--reverse',action='store_true');args=p.parse_args()
    try:
        if args.command=='generate':result=generate();code=0
        elif args.command=='verify':code,result=verify_file(args.file,args.sha) if args.file else (2,dict(status='NOT_RUN',reason='FILE_REQUIRED'))
        elif args.command=='freeze':
            result=dict(source=c.source_map(),source_sha256=c.source_identity())
            with (c.WORK/'source-freeze.json').open('xb') as f:f.write(c.canonical(result))
            code=0
        else:
            frozen=c.strict((c.WORK/'source-freeze.json').read_bytes());c.require(c.equal(frozen['source'],c.source_map()),'SOURCE_FROZEN')
            if args.command=='fit':
                dev,_=c.catalogs();model=fit(dev['fit'],frozen['source_sha256']);raw=c.canonical(model)
                with (c.WORK/'fitted-model.json').open('xb') as f:f.write(raw)
                with (c.WORK/'model-freeze.json').open('xb') as f:f.write(c.canonical(dict(model_raw_sha256=c.sha(raw),source_sha256=frozen['source_sha256'])))
                result=dict(status='PASS',model_raw_sha256=c.sha(raw),fit_cases=len(model['fit_case_ids']))
            else:
                raw=(c.WORK/'fitted-model.json').read_bytes();mf=c.strict((c.WORK/'model-freeze.json').read_bytes());c.require(c.sha(raw)==mf['model_raw_sha256'],'MODEL_FROZEN')
                path=c.allowed_file(args.file)
                if args.command=='run':
                    v=run(c.strict(raw),'STRESS' if args.stress else 'MAIN',args.reverse);checked=verify(v)
                    with path.open('xb') as f:f.write(c.canonical(v))
                    result=dict(status='PASS',raw_sha256=c.sha(path.read_bytes()),verification=checked)
                else:
                    code,result=verify_file(path,args.sha);c.require(code==0,result['reason']);result=prepare(c.strict(path.read_bytes()),args.directory)
            code=0
    except (c.Invalid,OSError,KeyError,TypeError,IndexError) as exc:code,result=3,dict(status='FAIL',reason=str(exc) if isinstance(exc,c.Invalid) else type(exc).__name__)
    print(c.canonical(result).decode());return code


if __name__=='__main__':raise SystemExit(main())
