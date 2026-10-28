"""Independent offline admission, evidence, ranking, transition and metric replay.

Does not call policy.decide, feedback.visible, replay.run or comparison. An external
raw-byte anchor is necessary; internal hashes are integrity links, not signatures.
"""
from . import pge_r75_contracts as c


def equal(a, b):
    return c.canonical(a) == c.canonical(b)


def expected_decision(v, records, state, policy):
    facts, anchors, rejected, conflict = {}, [], [], False
    for record in sorted(records, key=lambda r: r['evidence_id']):
        payload = {k: value for k, value in record.items() if k != 'payload_sha256'}
        c.require(record['payload_sha256'] == c.digest(payload), 'FIXTURE_HASH')
        c.require(record['seq'] <= state['step'] + 1, 'FUTURE_EVIDENCE')
        reason = ('EVIDENCE_SCOPE' if record['case_id'] != v['case_id'] or record['domain'] != v['domain']
                  else 'EVIDENCE_CONTRACT' if record['contract_sha256'] != c.digest(v)
                  else 'EVIDENCE_UNTRUSTED' if record['status'] != 'VERIFIED'
                  or record['source_kind'] != 'SYNTHETIC_VERIFIED_FIXTURE' else None)
        if reason:
            rejected.append(dict(evidence_id=record['evidence_id'], reason=reason))
        else:
            for key, value in record['facts'].items():
                conflict |= key in facts and facts[key] != value
                facts[key] = value
            anchors.append(dict(evidence_id=record['evidence_id'], sha256=record['payload_sha256']))
    d = dict(policy=policy, action='STOP', candidate_id=None, reason=None, cost=0, risk=0,
             evidence=dict(facts=facts, anchors=anchors, rejected=rejected, conflict=conflict),
             ranking=[], rejected=[])
    guards = [(state['unknown'], 'UNKNOWN_STOP'), (state['elapsed'] >= v['deadline'], 'DEADLINE_STOP'),
              (state['step'] >= v['max_steps'], 'STEP_STOP'), (conflict, 'CONTRADICTORY_FEEDBACK'),
              (not anchors, 'NO_TRUSTED_FEEDBACK'), (not v['candidates'], 'NO_CANDIDATES')]
    stop = next((reason for active, reason in guards if active), None)
    if stop:
        d['reason'] = stop
        if stop in ('CONTRADICTORY_FEEDBACK', 'NO_TRUSTED_FEEDBACK'):
            d['action'] = 'INCONCLUSIVE'
        return d
    for candidate in v['candidates']:
        cid = candidate['candidate_id']
        checks = [(not v['repeat'] and cid in state['attempted'], 'ALREADY_ATTEMPTED'),
                  (candidate['permission'] not in v['permissions'], 'PERMISSION'),
                  (candidate['risk'] > v['risk_cap'], 'RISK'),
                  (candidate['cost'] > state['remaining'], 'BUDGET'),
                  (not set(candidate['requires']) <= facts.keys(), 'PRECONDITION')]
        failure = next((reason for active, reason in checks if active), None)
        if failure:
            d['rejected'].append(dict(candidate_id=cid, reason=failure))
            continue
        score_keys = {'seed'} if policy == 'B1-no-feedback-v1' else set(facts)
        gain = sum(key not in score_keys for key in candidate['effects'])
        w = v['weights']
        terms = {'gain': w['gain'] * gain, 'priority': w['priority'] * candidate['priority'],
                 'cost': -w['cost'] * candidate['cost'], 'risk': -w['risk'] * candidate['risk']}
        d['ranking'].append(dict(candidate_id=cid, gain=gain, terms=terms,
                                 score=sum(terms.values()), order=candidate['order']))
    d['rejected'].sort(key=lambda r: r['candidate_id'])
    d['ranking'].sort(key=(lambda r: (r['order'], r['candidate_id'])) if policy == 'B0-fixed-v1'
                      else lambda r: (-r['score'], r['candidate_id']))
    if not d['ranking']:
        d['reason'] = 'NO_LEGAL_CANDIDATE'
    elif policy != 'B0-fixed-v1' and max(r['gain'] for r in d['ranking']) == 0:
        d['reason'] = 'NO_NEW_VISIBLE_FACT'
    else:
        chosen = next(x for x in v['candidates'] if x['candidate_id'] == d['ranking'][0]['candidate_id'])
        d.update(action='SELECT', candidate_id=chosen['candidate_id'], cost=chosen['cost'], risk=chosen['risk'],
                 reason='FIXED_ORDER' if policy == 'B0-fixed-v1' else 'MAX_EXPLAINABLE_SCORE')
    return d


def verify(value):
    c.keys(value, 'schema owner level source_sha256 fixture_sha256 seed policies runs comparison limitations result_sha256', 'TRACE_SCHEMA')
    c.require(value['schema'] == c.ABI and value['owner'] == c.OWNER and value['level'] == c.LEVEL, 'TRACE_ID')
    c.require(value['source_sha256'] == c.source_identity(), 'SOURCE_IDENTITY')
    fixture = c.catalog()
    c.require(value['fixture_sha256'] == c.sha(c.CATALOG.read_bytes()) and value['seed'] == fixture['seed'], 'FIXTURE_IDENTITY')
    c.require(value['policies'] == list(c.POLICIES), 'POLICY_SET')
    c.require(value['limitations'] == ['REAL_EXPLORER_NOT_RUN', 'TARGET_NOT_RUN', 'AUTHORITY_NOT_RUN',
                                    'PROVIDER_TOKENS_ZERO', 'L2_NOT_ESTABLISHED', 'RPF74_NOT_REPAIRED'], 'CLAIM_BOUNDARY')
    c.require(value['result_sha256'] == c.digest({k: v for k, v in value.items() if k != 'result_sha256'}), 'RESULT_HASH')
    expected_keys = [(case['case_id'], p) for case in fixture['cases'] for p in c.POLICIES]
    c.require(type(value['runs']) is list and [(r['case_id'], r['policy']) for r in value['runs']] == expected_keys, 'RUN_SET')
    metrics = []
    for run, (cid, policy) in zip(value['runs'], expected_keys):
        c.keys(run, 'case_id policy source_sha256 rows', 'RUN_SCHEMA')
        c.require(run['source_sha256'] == value['source_sha256'], 'RUN_SOURCE')
        case = next(x for x in fixture['cases'] if x['case_id'] == cid)
        v, state, previous, terminal = c.view(case), c.initial(c.view(case)), '0' * 64, False
        c.require(type(run['rows']) is list and 1 <= len(run['rows']) <= v['max_steps'] + 1, 'ROW_COUNT')
        facts, ids, cost, redundant, rejects, stops, inconclusive = set(), [], 0, 0, 0, 0, 0
        for index, row in enumerate(run['rows']):
            c.require(not terminal, 'AFTER_TERMINAL')
            c.keys(row, 'seq case_id policy step contract_sha256 visible_ids visible_sha256 state decision outcome previous_sha256 sha256', 'ROW_SCHEMA')
            c.require(row['seq'] == index + 1 and type(row['seq']) is int and row['case_id'] == cid
                      and row['policy'] == policy and type(row['step']) is int and row['step'] == state['step'], 'ROW_SCOPE_SEQ')
            c.validate_state(v, row['state'])
            c.require(equal(row['state'], state), 'STATE_CHAIN')
            c.require(row['contract_sha256'] == c.digest(v), 'CONTRACT_ANCHOR')
            records = sorted([r for r in case['feedback'] if r['visible_at'] <= state['step']], key=lambda r: r['evidence_id'])
            c.require(row['visible_ids'] == [r['evidence_id'] for r in records]
                      and row['visible_sha256'] == c.digest(records), 'VISIBLE_SET')
            c.require(row['previous_sha256'] == previous and row['sha256'] == c.digest({k: x for k, x in row.items() if k != 'sha256'}), 'ROW_HASH_CHAIN')
            decision = expected_decision(v, records, state, policy)
            c.require(equal(row['decision'], decision), 'DECISION_SEMANTICS')
            rejects += len(decision['rejected'])
            if decision['action'] == 'SELECT':
                outcome = case['outcomes'][decision['candidate_id']]
                c.require(equal(row['outcome'], outcome), 'OUTCOME_ORACLE')
                additions = set(outcome['facts'].items()) - facts if outcome['status'] == 'VERIFIED' else set()
                redundant += int(not additions)
                if outcome['status'] == 'VERIFIED':
                    facts.update(outcome['facts'].items())
                ids.append(decision['candidate_id'])
                cost += decision['cost']
                state = dict(step=state['step'] + 1, remaining=state['remaining'] - decision['cost'],
                             attempted=state['attempted'] + [decision['candidate_id']],
                             unknown=outcome['status'] == 'UNKNOWN', elapsed=state['elapsed'] + 1)
            else:
                c.require(row['outcome'] is None, 'STOP_OUTCOME')
                terminal, stops = True, stops + 1
                inconclusive += int(decision['action'] == 'INCONCLUSIVE')
            previous = row['sha256']
        c.require(terminal, 'MISSING_TERMINAL')
        metrics.append(dict(case_id=cid, policy=policy, selections=len(ids), legal_selections=len(ids),
                            simulated_cost=cost, verified_facts=len(facts), redundant_selections=redundant,
                            repeated_selections=len(ids) - len(set(ids)), stops=stops, correct_stops=stops,
                            inconclusive=inconclusive, rejected_candidates=rejects, failures=0))
    comparison = value['comparison']
    c.keys(comparison, 'table summaries paired definitions', 'COMPARISON_SCHEMA')
    c.require(equal(comparison['table'], metrics), 'METRIC_REPLAY')
    c.require(set(comparison['summaries']) == set(c.POLICIES), 'SUMMARY_SET')
    for policy, actual in comparison['summaries'].items():
        subset = [r for r in metrics if r['policy'] == policy]
        expected = {k: sum(r[k] for r in subset) for k in metrics[0] if k not in ('case_id', 'policy')}
        expected['legal_selection_rate'] = dict(numerator=expected['legal_selections'], denominator=expected['selections'])
        expected['stop_correctness'] = dict(numerator=expected['correct_stops'], denominator=expected['stops'])
        c.require(equal(actual, expected), 'METRIC_DENOMINATOR')
    pairs = []
    for cid in sorted({r['case_id'] for r in metrics}):
        p, b = [next(r for r in metrics if r['case_id'] == cid and r['policy'] == policy)
                for policy in ('PGE-v1', 'B0-fixed-v1')]
        fd, cd = p['verified_facts'] - b['verified_facts'], p['simulated_cost'] - b['simulated_cost']
        label = 'TIE' if fd == cd == 0 else 'FAVORABLE' if fd >= 0 and cd <= 0 else 'UNFAVORABLE' if fd <= 0 and cd >= 0 else 'TRADEOFF'
        pairs.append(dict(case_id=cid, label=label, facts_delta=fd, cost_delta=cd))
    c.require(equal(comparison['paired'], pairs), 'PAIRED_REPLAY')
    c.require(equal(comparison['definitions'], c.METRIC_DEFINITIONS), 'METRIC_DEFINITIONS')
    return dict(status='PASS', reason='INDEPENDENT_OFFLINE_REPLAY', cases=len(fixture['cases']),
                runs=len(value['runs']), decisions=sum(len(r['rows']) for r in value['runs']), level=c.LEVEL)


def verify_file(path, anchor):
    if not anchor:
        return 2, dict(status='NOT_RUN', reason='ANCHOR_REQUIRED')
    try:
        path = c.allowed_file(path)
        if not path.is_file():
            return 2, dict(status='NOT_RUN', reason='FILE_REQUIRED')
        raw = path.read_bytes()
        c.require(c.sha(raw) == anchor, 'RAW_ANCHOR')
        return 0, verify(c.strict(raw))
    except (c.Invalid, OSError, KeyError, TypeError, IndexError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, c.Invalid) else 'MALFORMED_INPUT'
        return 3, dict(status='FAIL', reason=reason)
