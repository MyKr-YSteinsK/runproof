"""The policy API has no evaluation labels, outcomes or future evidence."""
from . import pge_r77_contracts as c
from .pge_r77_projection import evidence, eligibility
from .pge_r77_utility import features
from .pge_r77_baselines import rank


def decide(v, records, s, roster, anchor, policy='PGE-v3-utility'):
    c.validate(v)
    c.state_valid(v, s)
    c.require(policy in c.POLICIES, 'POLICY_ID')
    ev = evidence(v, records, roster, anchor, s['step'])
    barrier, allowed, filtered = eligibility(v, s, ev)
    d = dict(policy=policy, action='STOP', candidate_id=None, reason=None, cost=0,
             evidence=ev, ranking=[], filtered=filtered, feature_unknown=[])
    if barrier:
        d['reason'] = barrier
    elif ev['conflict'] or not ev['accepted']:
        d.update(action='INCONCLUSIVE', reason='CONFLICT' if ev['conflict'] else 'NO_TRUSTED_SOURCE')
    elif not allowed:
        d['reason'] = 'NO_ELIGIBLE'
    elif policy == 'PGE-v3-utility':
        for x in allowed:
            if x['feature_status'] == 'UNKNOWN':
                d['feature_unknown'].append(x['candidate_id'])
            else:
                d['ranking'].append(dict(candidate_id=x['candidate_id'], **features(x, ev['facts'], s['attempted'])))
        d['feature_unknown'].sort()
        d['ranking'].sort(key=lambda x: (-x['score'], x['candidate_id']))
        if not d['ranking']:
            d.update(action='INCONCLUSIVE', reason='UTILITY_FEATURES_UNKNOWN')
        elif d['ranking'][0]['score'] <= 0:
            d['reason'] = 'NONPOSITIVE_VISIBLE_UTILITY'
        else:
            d.update(action='SELECT', reason='MAX_VISIBLE_UTILITY', candidate_id=d['ranking'][0]['candidate_id'])
    else:
        d['ranking'] = rank(allowed, ev['facts'], policy)
        if policy != 'B0-fixed' and max(x['gain'] for x in d['ranking']) == 0:
            d['reason'] = 'ESTIMATED_ZERO_GAIN'
        else:
            d.update(action='SELECT', reason='FIXED_ORDER' if policy == 'B0-fixed' else 'MAX_SCORE', candidate_id=d['ranking'][0]['candidate_id'])
    if d['action'] == 'SELECT':
        d['cost'] = next(x['cost'] for x in allowed if x['candidate_id'] == d['candidate_id'])
    return d
