"""Current observable evidence and hard eligibility precede utility ranking."""
from . import pge_r77_contracts as c


def evidence(v, records, roster, anchor, step):
    c.keys(roster, 'case_id entries', 'ROSTER_SCHEMA')
    c.require(c.digest(roster) == anchor and roster['case_id'] == v['case_id'], 'ROSTER_ANCHOR')
    c.require(type(records) is list and type(roster['entries']) is dict, 'ROSTER_TYPE')
    facts, accepted, refused, seen, conflict = {}, [], [], set(), False
    for r in sorted(records, key=lambda x: x['evidence_id']):
        c.keys(r, 'evidence_id case_id domain snapshot_id contract_sha256 visible_at seq status source_kind facts', 'RECORD_SCHEMA')
        c.require(r['evidence_id'] not in seen, 'DUPLICATE_RECORD')
        seen.add(r['evidence_id'])
        c.require(roster['entries'].get(r['evidence_id']) == c.digest(r), 'FROZEN_ROSTER_MEMBER')
        c.integer(r['visible_at'], 'RECORD_TIME', high=100)
        c.integer(r['seq'], 'RECORD_SEQ', low=1, high=101)
        reason = ('FUTURE' if r['visible_at'] > step or r['seq'] > step+1 else
                  'LATE' if r['seq'] < r['visible_at']+1 else 'CROSS_CASE' if r['case_id'] != v['case_id'] else
                  'CROSS_DOMAIN' if r['domain'] != v['domain'] else 'SNAPSHOT' if r['snapshot_id'] != v['snapshot_id'] else
                  'CONTRACT' if r['contract_sha256'] != c.snapshot_sha(v) else
                  'SOURCE' if r['source_kind'] != 'FROZEN_SYNTHETIC' else 'STATUS' if r['status'] != 'VERIFIED' else None)
        if reason:
            refused.append(dict(evidence_id=r['evidence_id'], reason=reason))
            continue
        c.require(type(r['facts']) is dict and set(r['facts']) <= set(v['fact_keys']) and all(type(x) is str for x in r['facts'].values()), 'RECORD_FACTS')
        for key, value in r['facts'].items():
            conflict |= key in facts and facts[key] != value
            facts[key] = value
        accepted.append(dict(evidence_id=r['evidence_id'], raw_sha256=c.digest(r)))
    return dict(facts=facts, accepted=accepted, refused=refused, conflict=conflict)


def eligibility(v, s, ev):
    barrier = ('UNKNOWN_STOP' if v['domain'] in s['unknown_domains'] else 'TIME_STOP' if s['elapsed'] >= v['deadline']
               else 'STEP_STOP' if s['step'] >= v['max_steps'] else None)
    allowed, filtered = [], []
    if not barrier and not ev['conflict'] and ev['accepted']:
        for x in v['candidates']:
            why = ('REPEAT' if not x['repeat'] and x['candidate_id'] in s['attempted'] else
                   'BUDGET' if x['cost'] > s['remaining'] else 'RISK' if x['risk'] > v['risk_cap'] else
                   'PERMISSION' if x['permission'] not in v['permissions'] else
                   'PRECONDITION' if not set(x['requires']) <= ev['facts'].keys() else None)
            (filtered if why else allowed).append(dict(candidate_id=x['candidate_id'], reason=why) if why else x)
    return barrier, allowed, sorted(filtered, key=lambda x: x['candidate_id'])
