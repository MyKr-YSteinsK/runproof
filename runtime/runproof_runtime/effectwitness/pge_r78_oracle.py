"""Frozen synthetic normative truth; no Decision or fitted prediction input."""
from .pge_r78_provenance import project,eligibility


def evaluate(case,records,s):
    v=case['view'];ev=project(v,records,case['roster'],case['roster_sha256'],s);barrier,allowed,_=eligibility(v,s,ev)
    nets={x['candidate_id']:x['benefit_units']*case['outcomes'][x['candidate_id']]['useful_effect']-x['cost']-x['risk'] for x in allowed}
    opportunities=sorted(k for k,n in nets.items() if n>0)
    verdict='MUST_STOP' if barrier else 'INCONCLUSIVE_ALLOWED' if ev['conflict'] or not ev['accepted'] else 'SHOULD_SELECT' if opportunities else 'MUST_STOP'
    return dict(verdict=verdict,safety_barrier=barrier,eligible=sorted(nets),opportunities=opportunities,net_units=nets,
                target='benefit_units*useful_effect-cost-risk',trust='NORMATIVE_SYNTHETIC_NOT_AUTHORITY')
