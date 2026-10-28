"""Closed-world roster integrity; no external authenticity claim."""
from . import pge_r76_contracts as c


def project(v, records, roster, roster_anchor, step):
    c.keys(roster, 'schema case_id entries', 'ROSTER_SCHEMA')
    c.require(c.digest(roster) == roster_anchor and roster['schema'] == c.ABI
              and roster['case_id'] == v['case_id'], 'ROSTER_ANCHOR')
    c.require(type(roster['entries']) is dict and type(records) is list, 'ROSTER_RECORDS')
    facts, accepted, rejected, seen, conflict = {}, [], [], set(), False
    for r in sorted(records, key=lambda x: x['evidence_id']):
        c.keys(r, 'evidence_id case_id domain source_kind contract_sha256 seq visible_at status facts', 'RECORD_SCHEMA')
        eid = r['evidence_id']
        c.require(eid not in seen, 'DUPLICATE_RECORD')
        seen.add(eid)
        c.require(roster['entries'].get(eid) == c.digest(r), 'RECORD_NOT_IN_FROZEN_ROSTER')
        c.units(r['visible_at'], 'RECORD_TIME', high=100)
        c.units(r['seq'], 'RECORD_SEQ', low=1, high=101)
        reason = ('FUTURE_RECORD' if r['visible_at'] > step or r['seq'] > step + 1
                  else 'LATE_RECORD' if r['seq'] < r['visible_at'] + 1
                  else 'CROSS_CASE' if r['case_id'] != v['case_id']
                  else 'CROSS_DOMAIN' if r['domain'] != v['domain']
                  else 'WRONG_CONTRACT' if r['contract_sha256'] != c.snapshot_sha(v)
                  else 'UNTRUSTED_SOURCE' if r['source_kind'] != 'FROZEN_SYNTHETIC'
                  else 'UNVERIFIED_STATUS' if r['status'] != 'VERIFIED' else None)
        if reason:
            rejected.append(dict(evidence_id=eid, reason=reason))
            continue
        c.require(type(r['facts']) is dict and set(r['facts']) <= set(v['fact_keys'])
                  and all(type(value) is str for value in r['facts'].values()), 'RECORD_FACTS')
        for key, value in r['facts'].items():
            conflict |= key in facts and facts[key] != value
            facts[key] = value
        accepted.append(dict(evidence_id=eid, sha256=c.digest(r)))
    return dict(facts=facts, accepted=accepted, rejected=rejected, conflict=conflict)
