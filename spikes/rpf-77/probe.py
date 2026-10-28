"""Offline CLI. Negative generation is not a substitute for CLI execution."""
import argparse
import copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime'))
from runproof_runtime.effectwitness import pge_r77_contracts as c
from runproof_runtime.effectwitness.pge_r77_replay import run
from runproof_runtime.effectwitness.pge_r77_verify import verify,verify_file


def guard(event,args):
    if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.posix_spawn'):
        raise c.Invalid('OFFLINE_OPERATION_FORBIDDEN')


sys.addaudithook(guard)


def reanchor(value):
    for run in value['runs']:
        previous='0'*64
        for row in run['rows']:
            row['previous_sha256']=previous;row['sha256']=c.digest({k:v for k,v in row.items() if k!='sha256'});previous=row['sha256']
    value['result_sha256']=c.digest({k:v for k,v in value.items() if k!='result_sha256'})
    return value


def specs():
    r=('runs',0,'rows',0);d=r+('decision',);v=('runs',0,'snapshot');x=v+('candidates',0)
    return [
        ('schema',('schema',),'future'),('owner',('owner',),'other'),('level',('level',),'REAL'),
        ('source',('source_sha256',),'0'*64),('split',('runs',0,'split'),'challenge'),
        ('blind-claim',('exposure',),'BLIND'),('case',('runs',0,'case_id'),'dev-01'),
        ('policy',('runs',0,'policy'),'unknown'),('no-limitations',('limitations',),[]),
        ('negative-budget',v+('budget',),-1),('overflow-budget',v+('budget',),2**63),
        ('snapshot-id',v+('snapshot_id',),'foreign-snapshot'),('domain',v+('domain',),'lab-foreign'),
        ('candidate-id',x+('candidate_id',),'../external'),('candidate-snapshot',x+('snapshot_id',),'foreign-snapshot'),
        ('candidate-source',x+('source_sha256',),'1'*64),('candidate-contract',x+('contract_sha256',),'2'*64),
        ('utility-verification',x+('verification_need',),2),('utility-freshness',x+('freshness_need',),2),
        ('utility-value-kind',x+('value_update_kind',),'NONE'),('utility-unknown',x+('feature_status',),'UNKNOWN'),
        ('utility-future',x+('feature_visible_at',),1),('utility-false-zero',x+('feature_visible_at',),False),
        ('candidate-cost',x+('cost',),99),('candidate-risk',x+('risk',),3),
        ('candidate-permission',x+('permission',),'admin'),('seq',r+('seq',),2),
        ('false-zero-step',r+('state','step'),False),('remaining',r+('state','remaining'),-1),
        ('elapsed',r+('state','elapsed'),2**63),('unknown-domain',r+('state','unknown_domains'),['lab-lumen']),
        ('snapshot-anchor',r+('snapshot_sha256',),''),('roster-anchor',r+('roster_sha256',),'3'*64),
        ('roster-self-anchor',r+('roster','entries','self-issued'),'4'*64),
        ('future-feedback',r+('records',0,'visible_at'),1),('future-feedback-seq',r+('records',0,'seq'),2),
        ('feedback-cross-domain',r+('records',0,'domain'),'lab-foreign'),
        ('feedback-cross-case',r+('records',0,'case_id'),'dev-01'),
        ('feedback-snapshot',r+('records',0,'snapshot_id'),'foreign-snapshot'),
        ('feedback-source',r+('records',0,'source_kind'),'SELF_SIGNED'),
        ('fake-fact',r+('records',0,'facts','fact-11'),'guessed'),
        ('out-of-pool',d+('candidate_id',),'lab-lumen-invented'),('selection-cost',d+('cost',),0),
        ('wrong-stop',d+('action',),'STOP'),('reason',d+('reason',),''),
        ('utility-score',d+('ranking',0,'score'),999),('utility-novelty',d+('ranking',0,'expected_key_novelty'),False),
        ('utility-cost-term',d+('ranking',0,'terms','cost'),9),
        ('utility-confidence',d+('ranking',0,'confidence_status'),'UNKNOWN'),
        ('fake-provenance',d+('evidence','accepted'),[]),
        ('oracle-stop',r+('oracle','verdict'),'MUST_STOP'),('oracle-eligible',r+('oracle','eligible'),[]),
        ('oracle-opportunity',r+('oracle','opportunities'),[]),
        ('oracle-label',('runs',0,'evaluation','worthwhile_ids'),[]),
        ('unknown-select',('runs',12,'rows',0,'decision','action'),'SELECT'),
        ('outcome-status',r+('outcome','status'),'OBSERVED'),('outcome-fact',r+('outcome','facts','fact-01'),'forged'),
        ('hidden-missed',('comparison','table',30,'missed_opportunity'),0),
        ('hidden-overexploration',('comparison','table',27,'over_exploration'),0),
        ('false-safe-zero',('comparison','table',0,'unsafe_select'),False),
        ('cost-denominator',('comparison','summaries','development','PGE-v3-utility','cost_per_verified_fact','denominator'),999),
        ('false-definition',('comparison','definitions','over_exploration'),'always zero'),
        ('forged-verified',('runs',9,'rows',0,'records',0,'source_kind'),'FROZEN_SYNTHETIC'),
        ('duplicate-record',r+('records',),[]),
        ('ranking-permutation',('runs',33,'rows',0,'decision','ranking'),[]),
        ('row-hash-order',r+('previous_sha256',),'f'*64),
    ]


def change(value,path,replacement):
    node=value
    for key in path[:-1]:node=node[key]
    c.require((type(node) is dict and path[-1] not in node) or not c.equal(node[path[-1]],replacement),'TEST_INVALID_NO_OP')
    node[path[-1]]=replacement


def mutant(original,index):
    value=copy.deepcopy(original);items=specs()
    if index<len(items):
        name,path,replacement=items[index]
        if name=='duplicate-record':replacement=copy.deepcopy(original['runs'][0]['rows'][0]['records'])*2
        if name=='ranking-permutation':replacement=list(reversed(copy.deepcopy(original['runs'][33]['rows'][0]['decision']['ranking'])))
        change(value,path,replacement)
    else:
        n=index-len(items);name='compound-%02d'%(n+1)
        pairs=((17,45),(18,47),(19,48),(34,33),(40,49),(54,50),(57,53),(58,61),(23,42),(30,51),(37,32),(20,43))
        for i in pairs[n]:
            _,path,replacement=items[i];change(value,path,replacement)
        for run in value['runs']:
            for row in run['rows']:
                for record in row['records']:row['roster']['entries'][record['evidence_id']]=c.digest(record)
                row['roster_sha256']=c.digest(row['roster'])
        if n<3 or n==8:
            v=value['runs'][0]['snapshot']
            for x in v['candidates']:x['contract_sha256']=c.digest({k:z for k,z in x.items() if k!='contract_sha256'})
            value['runs'][0]['rows'][0]['snapshot_sha256']=c.snapshot_sha(v)
    reanchor(value)
    if name=='row-hash-order':
        row=value['runs'][0]['rows'][0];row['previous_sha256']='f'*64
        row['sha256']=c.digest({k:v for k,v in row.items() if k!='sha256'})
        value['result_sha256']=c.digest({k:v for k,v in value.items() if k!='result_sha256'})
    return name,value


def prepare(original,directory):
    verify(original);directory=c.allowed_file(Path(directory)/'scope.json').parent;directory.mkdir(parents=True,exist_ok=False)
    entries=[]
    for i in range(len(specs())+12):
        name,value=mutant(original,i);raw=c.canonical(value);path=directory/(name+'.json')
        with path.open('xb') as f:f.write(raw)
        entries.append(dict(name=name,file=path.relative_to(c.ROOT).as_posix(),original_sha256=c.digest(original),
                            raw_sha256=c.sha(raw),compound=i>=len(specs()),expected_exit=3))
    result=dict(status='PREPARED_NOT_EXECUTED',controls=entries);(directory/'controls.json').write_bytes(c.canonical(result))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','run','verify','negative'))
    p.add_argument('--file');p.add_argument('--sha');p.add_argument('--directory');p.add_argument('--reverse',action='store_true');args=p.parse_args()
    try:
        if args.command=='verify':code,result=verify_file(args.file,args.sha) if args.file else (2,dict(status='NOT_RUN',reason='FILE_REQUIRED'))
        elif args.command=='freeze':
            result=dict(source=c.source_map(),source_sha256=c.source_identity())
            with (c.WORK/'source-freeze.json').open('xb') as f:f.write(c.canonical(result))
            code=0
        else:
            frozen=c.strict((c.WORK/'source-freeze.json').read_bytes());c.require(c.equal(frozen['source'],c.source_map()),'SOURCE_FROZEN')
            path=c.allowed_file(args.file)
            if args.command=='run':
                value=run(reverse=args.reverse);checked=verify(value)
                with path.open('xb') as f:f.write(c.canonical(value))
                result=dict(status='PASS',raw_sha256=c.sha(path.read_bytes()),verification=checked)
            else:
                code,result=verify_file(path,args.sha);c.require(code==0,result['reason']);result=prepare(c.strict(path.read_bytes()),args.directory)
            code=0
    except (c.Invalid,OSError,KeyError,TypeError,IndexError) as exc:code,result=3,dict(status='FAIL',reason=str(exc) if isinstance(exc,c.Invalid) else type(exc).__name__)
    print(c.canonical(result).decode());return code


if __name__=='__main__':raise SystemExit(main())
