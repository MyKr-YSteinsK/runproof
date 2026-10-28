"""Offline CLI. Writes only explicitly selected task-owned JSON files."""
import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime'))
from runproof_runtime.effectwitness import pge_r75_contracts as c
from runproof_runtime.effectwitness.pge_r75_replay import run
from runproof_runtime.effectwitness.pge_r75_verify import verify_file, verify


def offline_guard(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.posix_spawn', 'os.spawn'):
        raise c.Invalid('OFFLINE_OPERATION_FORBIDDEN')


sys.addaudithook(offline_guard)


def reanchor(value):
    for replay in value['runs']:
        previous = '0' * 64
        for row in replay['rows']:
            row['previous_sha256'] = previous
            row['sha256'] = c.digest({k: v for k, v in row.items() if k != 'sha256'})
            previous = row['sha256']
    value['result_sha256'] = c.digest({k: v for k, v in value.items() if k != 'result_sha256'})
    return value


def control_specs():
    row = ('runs', 0, 'rows', 0)
    decision = row + ('decision',)
    return [
        ('unknown-schema', ('schema',), 'future-v9'),
        ('wrong-owner', ('owner',), 'other-owner'),
        ('evidence-level-upgrade', ('level',), 'REAL'),
        ('wrong-source', ('source_sha256',), '0' * 64),
        ('wrong-fixture-anchor', ('fixture_sha256',), '1' * 64),
        ('seed-change', ('seed',), 7502),
        ('policy-set-change', ('policies',), ['PGE-v1']),
        ('claim-escalation', ('limitations',), []),
        ('duplicate-trace-seq', row + ('seq',), 2),
        ('wrong-case-scope', row + ('case_id',), 'case-01'),
        ('wrong-policy-id', row + ('policy',), 'unknown-policy'),
        ('step-skip', row + ('step',), 1),
        ('budget-negative', row + ('state', 'remaining'), -1),
        ('budget-overflow', row + ('state', 'remaining'), 2 ** 63),
        ('elapsed-time-forgery', row + ('state', 'elapsed'), 9),
        ('unknown-state-forgery', row + ('state', 'unknown'), True),
        ('repeated-attempt-forgery', row + ('state', 'attempted'), ['normal', 'normal']),
        ('wrong-contract-anchor', row + ('contract_sha256',), '2' * 64),
        ('future-feedback-id', row + ('visible_ids',), ['case-00-update']),
        ('missing-visible-anchor', row + ('visible_sha256',), ''),
        ('out-of-pool-candidate', decision + ('candidate_id',), 'invented'),
        ('cross-domain-candidate', decision + ('candidate_id',), 'normal-full-refund'),
        ('candidate-cost-forgery', decision + ('cost',), 0),
        ('candidate-risk-forgery', decision + ('risk',), 3),
        ('unverified-promoted-fact', decision + ('evidence', 'facts', 'recovery'), 'guessed'),
        ('missing-evidence-provenance', decision + ('evidence', 'anchors'), []),
        ('ranking-score-forgery', decision + ('ranking', 0, 'score'), 999),
        ('ranking-feature-forgery', decision + ('ranking', 0, 'gain'), 8),
        ('ranking-cost-term-forgery', decision + ('ranking', 0, 'terms', 'cost'), 5),
        ('missing-reason', decision + ('reason',), ''),
        ('outcome-future-label', row + ('outcome', 'facts', 'recovery'), 'future'),
        ('unknown-continues', ('runs', 30, 'rows', 0, 'decision', 'action'), 'SELECT'),
        ('timeout-continues', ('runs', 33, 'rows', 1, 'decision', 'action'), 'SELECT'),
        ('empty-pool-selects', ('runs', 39, 'rows', 0, 'decision', 'action'), 'SELECT'),
        ('baseline-future-ranking', ('runs', 1, 'rows', 0, 'decision', 'candidate_id'), 'local-delivery-suppressed-after-http200'),
        ('metric-fact-forgery', ('comparison', 'table', 0, 'verified_facts'), 100),
        ('metric-denominator-forgery', ('comparison', 'summaries', 'PGE-v1', 'legal_selection_rate', 'denominator'), 0),
        ('paired-advantage-forgery', ('comparison', 'paired', 0, 'label'), 'FAKE_ADVANTAGE'),
        ('run-source-substitution', ('runs', 0, 'source_sha256'), '3' * 64),
        ('boolean-zero-step', row + ('step',), False),
        ('boolean-zero-state-step', row + ('state', 'step'), False),
        ('boolean-zero-metric', ('comparison', 'table', 0, 'failures'), False),
        ('metric-definition-forgery', ('comparison', 'definitions', 'fairness'), 'future outcome labels allowed'),
    ]


def mutate(original, spec):
    name, path, replacement = spec
    value = copy.deepcopy(original)
    node = value
    for key in path[:-1]:
        node = node[key]
    c.require((isinstance(node, dict) and path[-1] not in node)
              or c.canonical(node[path[-1]]) != c.canonical(replacement), 'TEST_INVALID_NO_OP')
    node[path[-1]] = replacement
    # All controls re-anchor every row and outer result; admission must be semantic.
    return reanchor(value)


def negatives(original, directory):
    c.require(verify(original)['status'] == 'PASS', 'NEGATIVE_BASELINE')
    directory = c.allowed_file(Path(directory) / 'scope.json').parent
    directory.mkdir(parents=True, exist_ok=False)
    rows = []
    for spec in control_specs():
        mutant = mutate(original, spec)
        target = directory / (spec[0] + '.json')
        raw = c.canonical(mutant)
        target.write_bytes(raw)
        code, result = verify_file(target, c.sha(raw))
        rows.append(dict(control=spec[0], expected_exit=3, actual_exit=code,
                         raw_sha256=c.sha(raw), reanchored=True, reason=result['reason'],
                         status='PASS' if code == 3 else 'FAIL'))
    # Compound: correct local hashes plus a fake UNKNOWN continuation and result label.
    compound = mutate(original, control_specs()[31])
    compound['runs'][30]['rows'][0]['decision']['candidate_id'] = 'normal'
    compound['runs'][30]['rows'][0]['outcome'] = dict(status='VERIFIED', facts={'version': 'v2'})
    compound['comparison']['table'][30]['selections'] = 1
    reanchor(compound)
    raw = c.canonical(compound)
    target = directory / 'compound-unknown-outcome-metrics.json'
    target.write_bytes(raw)
    code, result = verify_file(target, c.sha(raw))
    rows.append(dict(control='compound-unknown-outcome-metrics', expected_exit=3, actual_exit=code,
                     raw_sha256=c.sha(raw), reanchored=True, reason=result['reason'],
                     status='PASS' if code == 3 else 'FAIL'))
    report = dict(status='PASS' if all(r['status'] == 'PASS' for r in rows) else 'FAIL',
                  valid_controls=len(rows), rejected=sum(r['actual_exit'] == 3 for r in rows),
                  rejection_rate=dict(numerator=sum(r['actual_exit'] == 3 for r in rows), denominator=len(rows)),
                  controls=rows)
    (directory / 'results.json').write_bytes(c.canonical(report))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('freeze', 'run', 'verify', 'negative'))
    parser.add_argument('--file')
    parser.add_argument('--sha')
    parser.add_argument('--directory')
    parser.add_argument('--reverse', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'verify':
            if not args.file:
                code, result = 2, dict(status='NOT_RUN', reason='FILE_REQUIRED')
            else:
                code, result = verify_file(args.file, args.sha)
        elif args.command == 'freeze':
            result = dict(source_sha256=c.source_identity(), source=c.source_map())
            with (c.WORK / 'source-freeze.json').open('xb') as stream:
                stream.write(c.canonical(result))
            code = 0
        else:
            frozen = c.strict((c.WORK / 'source-freeze.json').read_bytes())
            c.require(frozen['source_sha256'] == c.source_identity() and frozen['source'] == c.source_map(), 'SOURCE_FROZEN')
            path = c.allowed_file(args.file)
            if args.command == 'run':
                result = run(reverse=args.reverse)
                verify(result)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as stream:
                    stream.write(c.canonical(result))
                result = dict(status='PASS', sha256=c.sha(path.read_bytes()), verification=verify(result))
            else:
                code, checked = verify_file(path, args.sha)
                c.require(code == 0, checked['reason'])
                result = negatives(c.strict(path.read_bytes()), args.directory)
            code = 0 if result['status'] == 'PASS' else 3
    except (c.Invalid, OSError, TypeError, KeyError) as exc:
        code, result = 3, dict(status='FAIL', reason=str(exc) if isinstance(exc, c.Invalid) else type(exc).__name__)
    print(c.canonical(result).decode())
    return code


if __name__ == '__main__':
    raise SystemExit(main())
