"""Independent normative utility/eligibility oracle; never sees a Decision."""
from . import pge_r76_contracts as c
from .pge_r76_provenance import project


def evaluate(case, records, state):
    v = case['view']
    c.validate_view(v)
    c.validate_state(v, state)
    evidence = project(v, records, case['roster'], case['roster_sha256'], state['step'])
    if v['domain'] in state['unknown_domains'] or state['elapsed'] >= v['deadline'] or state['step'] >= v['max_steps']:
        return dict(verdict='MUST_STOP', eligible=[], opportunities=[], reason='SAFETY_LIMIT')
    if evidence['conflict'] or not evidence['accepted']:
        return dict(verdict='INCONCLUSIVE_ALLOWED', eligible=[], opportunities=[], reason='EVIDENCE_UNCERTAIN')
    eligible = sorted(x['candidate_id'] for x in v['candidates'] if x['cost'] <= state['remaining']
        and x['risk'] <= v['risk_cap'] and x['permission'] in v['permissions']
        and set(x['requires']) <= evidence['facts'].keys()
        and (x['repeat'] or x['candidate_id'] not in state['attempted']))
    opportunities = sorted(set(eligible) & set(case['oracle']['worthwhile_ids']) - set(state['attempted']))
    return dict(verdict='MUST_STOP' if not eligible else 'SHOULD_SELECT' if opportunities else 'INCONCLUSIVE_ALLOWED',
                eligible=eligible, opportunities=opportunities,
                reason='NO_ELIGIBLE' if not eligible else 'FROZEN_FRESH_UTILITY' if opportunities else 'UTILITY_UNDETERMINED')
