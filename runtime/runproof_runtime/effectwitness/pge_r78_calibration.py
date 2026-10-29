"""Pure fit-only table. No dataset loader or validation/challenge access."""
import math
from . import pge_r78_contracts as c


def fit(fit_cases,source_sha256):
    counts={name:[0,0] for name in c.BUCKETS};ids=[];outcome_ids=[];domains=set()
    for case in fit_cases:
        c.require(case['view']['split']=='fit','FIT_PARTITION_ONLY');c.case_valid(case);v=case['view']
        ids.append(v['case_id']);domains.add(v['domain'])
        for x in v['candidates']:
            c.require(x['feature_status']=='KNOWN' and x['visible_at']==0 and x['valid_until']>=v['initial_elapsed'],'FIT_FEATURE_SUPPORT')
            o=case['outcomes'][x['candidate_id']];c.require(o['status']=='VERIFIED','FIT_COMPLETED_ONLY')
            outcome_ids.append(o['outcome_id']);bucket=x['feature_kind'];c.require(bucket in counts,'FIT_BUCKET')
            counts[bucket][0]+=1;counts[bucket][1]+=o['useful_effect']
    c.require(len(set(ids))==len(ids) and len(set(outcome_ids))==len(outcome_ids),'FIT_DUPLICATE_ID')
    rows={}
    for bucket,(n,k) in counts.items():
        if n:
            denom=1+c.Z*c.Z/n;center=(k/n+c.Z*c.Z/(2*n))/denom
            radius=c.Z*math.sqrt((k/n)*(1-k/n)/n+c.Z*c.Z/(4*n*n))/denom
            lo=round(max(0,center-radius),12);hi=round(min(1,center+radius),12)
        else:lo,hi=0.0,1.0
        rows[bucket]=dict(n=n,positive=k,p_hat=round((k+1)/(n+2),12),lower=lo,upper=hi,
                          width=round(hi-lo,12),status='SUPPORTED' if n>=c.MIN_N else 'INSUFFICIENT_SUPPORT')
    return dict(schema=c.ABI,owner=c.OWNER,method=c.METHOD,source_sha256=source_sha256,target='useful_effect-binary-v1',
                fit_partition='fit',fit_case_ids=sorted(ids),fit_outcome_ids=sorted(outcome_ids),fit_input_sha256=c.digest(fit_cases),
                domain_support=sorted(domains),min_n=c.MIN_N,z=c.Z,buckets=rows,
                warning='DESCRIPTIVE_SYNTHETIC_NON_IID_NO_COVERAGE_GUARANTEE')
