"""Inference accepts current features plus frozen training export, no labels."""
from . import pge_r78_contracts as c


def estimate(x,model,s,ev):
    status=('UNTRUSTED_EVIDENCE' if ev['conflict'] or not ev['accepted'] else 'UNKNOWN_FEATURE' if x['feature_status']=='UNKNOWN'
        else 'FUTURE_FEATURE' if x['visible_at']>s['elapsed'] else 'EXPIRED_FEATURE' if x['valid_until']<s['elapsed']
        else 'UNSUPPORTED_DOMAIN' if x['domain'] not in model['domain_support'] else 'UNSUPPORTED_BUCKET' if x['feature_kind'] not in model['buckets']
        else model['buckets'][x['feature_kind']]['status'])
    out=dict(bucket=x['feature_kind'],status=status,n=0,p_hat=None,lower=None,upper=None,point_net=None,lower_net=None,upper_net=None)
    if x['feature_kind'] in model['buckets']:out['n']=model['buckets'][x['feature_kind']]['n']
    if status=='SUPPORTED':
        row=model['buckets'][x['feature_kind']]
        for key in ('p_hat','lower','upper'):out[key]=row[key]
        for key,prob in (('point_net',row['p_hat']),('lower_net',row['lower']),('upper_net',row['upper'])):
            out[key]=round(x['benefit_units']*prob-x['cost']-x['risk'],12)
    return out
