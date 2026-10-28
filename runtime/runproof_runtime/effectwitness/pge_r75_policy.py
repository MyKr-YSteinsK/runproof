"""Deterministic, risk/budget-aware policy; receives no future outcome oracle."""
from . import pge_r75_contracts as c
from .pge_r75_feedback import visible


def decide(contract_view, visible_evidence, policy_state, *, trusted_records, policy='PGE-v1'):
    v, state = contract_view, policy_state
    c.validate_view(v)
    v = c.normalize(v)
    c.validate_state(v, state)
    c.require(policy in c.POLICIES, 'POLICY_ID')
    evidence = visible(v, visible_evidence, trusted_records, state['step'])
    facts = evidence['facts']
    result = dict(policy=policy, action='STOP', candidate_id=None, reason=None, cost=0, risk=0,
                  evidence=evidence, ranking=[], rejected=[])
    if state['unknown']:
        result['reason'] = 'UNKNOWN_STOP'
    elif state['elapsed'] >= v['deadline']:
        result['reason'] = 'DEADLINE_STOP'
    elif state['step'] >= v['max_steps']:
        result['reason'] = 'STEP_STOP'
    elif evidence['conflict']:
        result.update(action='INCONCLUSIVE', reason='CONTRADICTORY_FEEDBACK')
    elif not evidence['anchors']:
        result.update(action='INCONCLUSIVE', reason='NO_TRUSTED_FEEDBACK')
    elif not v['candidates']:
        result['reason'] = 'NO_CANDIDATES'
    else:
        score_facts = facts if policy != 'B1-no-feedback-v1' else {'seed': 'ready'}
        for candidate in v['candidates']:
            cid = candidate['candidate_id']
            why = None
            if not v['repeat'] and cid in state['attempted']:
                why = 'ALREADY_ATTEMPTED'
            elif candidate['permission'] not in v['permissions']:
                why = 'PERMISSION'
            elif candidate['risk'] > v['risk_cap']:
                why = 'RISK'
            elif candidate['cost'] > state['remaining']:
                why = 'BUDGET'
            elif not set(candidate['requires']) <= set(facts):
                why = 'PRECONDITION'
            if why:
                result['rejected'].append(dict(candidate_id=cid, reason=why))
                continue
            gain = len(set(candidate['effects']) - set(score_facts))
            weights = v['weights']
            terms = dict(gain=weights['gain'] * gain, priority=weights['priority'] * candidate['priority'],
                         cost=-weights['cost'] * candidate['cost'], risk=-weights['risk'] * candidate['risk'])
            result['ranking'].append(dict(candidate_id=cid, gain=gain, terms=terms,
                                          score=sum(terms.values()), order=candidate['order']))
        result['rejected'].sort(key=lambda r: r['candidate_id'])
        if policy == 'B0-fixed-v1':
            result['ranking'].sort(key=lambda r: (r['order'], r['candidate_id']))
        else:
            result['ranking'].sort(key=lambda r: (-r['score'], r['candidate_id']))
        if not result['ranking']:
            result['reason'] = 'NO_LEGAL_CANDIDATE'
        elif policy != 'B0-fixed-v1' and all(r['gain'] == 0 for r in result['ranking']):
            result['reason'] = 'NO_NEW_VISIBLE_FACT'
        else:
            cid = result['ranking'][0]['candidate_id']
            selected = next(r for r in v['candidates'] if r['candidate_id'] == cid)
            result.update(action='SELECT', candidate_id=cid, reason='FIXED_ORDER' if policy == 'B0-fixed-v1'
                          else 'MAX_EXPLAINABLE_SCORE', cost=selected['cost'], risk=selected['risk'])
    return result
