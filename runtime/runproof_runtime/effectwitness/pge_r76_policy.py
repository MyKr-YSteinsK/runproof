"""General finite policy, intentionally imperfect utility stopping heuristic."""
from . import pge_r76_contracts as c
from .pge_r76_provenance import project


def decide(v, records, state, roster, roster_anchor, policy='PGE-v2'):
    c.validate_view(v)
    c.validate_state(v, state)
    c.require(policy in c.POLICIES, 'POLICY_ID')
    evidence = project(v, records, roster, roster_anchor, state['step'])
    result = dict(policy=policy, action='STOP', candidate_id=None, reason=None, cost=0,
                  estimated_gain=0, ranking=[], rejected=[], evidence=evidence)
    for active, reason in ((v['domain'] in state['unknown_domains'], 'UNKNOWN_STOP'),
                           (state['elapsed'] >= v['deadline'], 'TIME_STOP'),
                           (state['step'] >= v['max_steps'], 'STEP_STOP')):
        if active:
            result['reason'] = reason
            return result
    if evidence['conflict'] or not evidence['accepted']:
        result.update(action='INCONCLUSIVE', reason='CONFLICT' if evidence['conflict'] else 'NO_TRUSTED_EVIDENCE')
        return result
    for x in v['candidates']:
        reasons = [(not x['repeat'] and x['candidate_id'] in state['attempted'], 'REPEAT'),
                   (x['cost'] > state['remaining'], 'BUDGET'), (x['risk'] > v['risk_cap'], 'RISK'),
                   (x['permission'] not in v['permissions'], 'PERMISSION'),
                   (not set(x['requires']) <= evidence['facts'].keys(), 'PRECONDITION')]
        blocked = next((reason for active, reason in reasons if active), None)
        if blocked:
            result['rejected'].append(dict(candidate_id=x['candidate_id'], reason=blocked))
            continue
        known = set() if policy == 'B1-score-ablation-v2' else set(evidence['facts'])
        gain = len(set(x['effects']) - known)
        w = v['weights']
        terms = dict(gain=w['gain'] * gain, priority=w['priority'] * x['priority'],
                     cost=-w['cost'] * x['cost'], risk=-w['risk'] * x['risk'])
        result['ranking'].append(dict(candidate_id=x['candidate_id'], gain=gain, terms=terms,
                                      score=sum(terms.values()), order=x['order']))
    result['rejected'].sort(key=lambda x: x['candidate_id'])
    result['ranking'].sort(key=(lambda x: (x['order'], x['candidate_id'])) if policy == 'B0-fixed-v2'
                           else lambda x: (-x['score'], x['candidate_id']))
    if not result['ranking']:
        result['reason'] = 'NO_ELIGIBLE'
    elif policy != 'B0-fixed-v2' and all(x['gain'] == 0 for x in result['ranking']):
        result['reason'] = 'ESTIMATED_ZERO_GAIN'
    else:
        selected = result['ranking'][0]
        candidate = next(x for x in v['candidates'] if x['candidate_id'] == selected['candidate_id'])
        result.update(action='SELECT', reason='FIXED_ORDER' if policy == 'B0-fixed-v2' else 'MAX_SCORE',
                      candidate_id=candidate['candidate_id'], cost=candidate['cost'], estimated_gain=selected['gain'])
    return result
