"""Only exact frozen fixture records can become policy evidence."""
from . import pge_r75_contracts as c


def visible(v, records, trusted_records, step):
    c.require(type(records) is list and type(trusted_records) is dict, 'FEEDBACK_LIST')
    roster = trusted_records
    c.require(len(roster) == len(trusted_records), 'FIXTURE_DUPLICATE_ID')
    facts, anchors, rejected, seen = {}, [], [], set()
    conflict = False
    for record in sorted(records, key=lambda r: r.get('evidence_id', '')):
        c.keys(record, 'evidence_id case_id domain source_kind contract_sha256 seq visible_at status facts payload_sha256', 'EVIDENCE_SCHEMA')
        eid = record['evidence_id']
        c.require(eid not in seen, 'DUPLICATE_EVIDENCE')
        seen.add(eid)
        c.require(eid in roster and c.digest(record) == roster[eid], 'EVIDENCE_NOT_FROZEN')
        payload = {k: v for k, v in record.items() if k != 'payload_sha256'}
        c.require(c.digest(payload) == record['payload_sha256'], 'EVIDENCE_HASH')
        c.units(record['seq'], 'EVIDENCE_SEQ', low=1, high=100)
        c.units(record['visible_at'], 'EVIDENCE_TIME', high=100)
        c.require(record['visible_at'] <= step and record['seq'] <= step + 1, 'FUTURE_EVIDENCE')
        if record['case_id'] != v['case_id'] or record['domain'] != v['domain']:
            rejected.append(dict(evidence_id=eid, reason='EVIDENCE_SCOPE'))
        elif record['contract_sha256'] != c.digest(v):
            rejected.append(dict(evidence_id=eid, reason='EVIDENCE_CONTRACT'))
        elif record['source_kind'] != 'SYNTHETIC_VERIFIED_FIXTURE' or record['status'] != 'VERIFIED':
            rejected.append(dict(evidence_id=eid, reason='EVIDENCE_UNTRUSTED'))
        else:
            c.require(type(record['facts']) is dict and set(record['facts']) <= {'seed', 'version', 'receipt', 'recovery'}
                      and all(type(x) is str for x in record['facts'].values()), 'EVIDENCE_FACTS')
            for key, value in record['facts'].items():
                if key in facts and facts[key] != value:
                    conflict = True
                facts[key] = value
            anchors.append(dict(evidence_id=eid, sha256=record['payload_sha256']))
    return dict(facts=facts, anchors=anchors, rejected=rejected, conflict=conflict)
