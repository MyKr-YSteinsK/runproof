"""Local CLI; negative prepares variants for separately recorded CLI executions."""
import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime'))
from runproof_runtime.effectwitness import pge_r76_contracts as c
from runproof_runtime.effectwitness.pge_r76_replay import run
from runproof_runtime.effectwitness.pge_r76_verify import verify, verify_file


def guard(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.posix_spawn'):
        raise c.Invalid('OFFLINE_OPERATION_FORBIDDEN')


sys.addaudithook(guard)


def reanchor(value):
    for run in value['runs']:
        previous = '0' * 64
        for row in run['rows']:
            row['previous_sha256'] = previous
            row['sha256'] = c.digest({k: v for k, v in row.items() if k != 'sha256'})
            previous = row['sha256']
    value['result_sha256'] = c.digest({k: v for k, v in value.items() if k != 'result_sha256'})
    return value


def specs():
    row = ('runs', 0, 'rows', 0)
    d = row + ('decision',)
    snap = ('runs', 0, 'snapshot')
    return [
        ('unknown-schema', ('schema',), 'future'),
        ('owner-substitute', ('owner',), 'other-owner'),
        ('level-upgrade', ('level',), 'REAL'),
        ('source-substitute', ('source_sha256',), '0' * 64),
        ('input-reanchor', ('inputs', 'development'), '1' * 64),
        ('false-blinding-claim', ('exposure',), 'BLIND'),
        ('policy-set', ('policies',), ['PGE-v2']),
        ('claim-upgrade', ('limitations',), []),
        ('fake-holdout-split', ('runs', 0, 'split'), 'holdout'),
        ('cross-case', ('runs', 0, 'case_id'), 'dev-01'),
        ('wrong-policy', ('runs', 0, 'policy'), 'unknown'),
        ('negative-budget', snap + ('budget',), -1),
        ('overflow-budget', snap + ('budget',), 2 ** 63),
        ('snapshot-domain', snap + ('domain',), 'lab-foreign'),
        ('candidate-cross-domain', snap + ('candidates', 0, 'domain'), 'lab-foreign'),
        ('invalid-candidate-id', snap + ('candidates', 0, 'candidate_id'), '../external'),
        ('candidate-source', snap + ('candidates', 0, 'source_sha256'), '2' * 64),
        ('candidate-contract', snap + ('candidates', 0, 'contract_sha256'), '3' * 64),
        ('cost-forgery', snap + ('candidates', 0, 'cost'), 100),
        ('priority-forgery', snap + ('candidates', 0, 'priority'), 100),
        ('row-seq-duplicate', row + ('seq',), 2),
        ('false-zero-seq', row + ('state', 'step'), False),
        ('state-budget', row + ('state', 'remaining'), -1),
        ('state-time-overflow', row + ('state', 'elapsed'), 2 ** 63),
        ('state-domain-unknown', row + ('state', 'unknown_domains'), ['lab-amber']),
        ('snapshot-anchor', row + ('snapshot_sha256',), ''),
        ('roster-anchor', row + ('roster_sha256',), '4' * 64),
        ('roster-entry', row + ('roster', 'entries', 'dev-00-initial'), '5' * 64),
        ('roster-owner-case', row + ('roster', 'case_id'), 'dev-01'),
        ('future-feedback', row + ('visible_records', 0, 'visible_at'), 1),
        ('future-sequence', row + ('visible_records', 0, 'seq'), 2),
        ('record-cross-domain', row + ('visible_records', 0, 'domain'), 'lab-foreign'),
        ('record-cross-case', row + ('visible_records', 0, 'case_id'), 'dev-01'),
        ('record-wrong-source', row + ('visible_records', 0, 'source_kind'), 'SELF_SIGNED'),
        ('record-wrong-contract', row + ('visible_records', 0, 'contract_sha256'), ''),
        ('record-fake-fact', row + ('visible_records', 0, 'facts', 'fact-11'), 'guessed'),
        ('out-of-pool', d + ('candidate_id',), 'lab-amber-invented'),
        ('cross-domain-selection', d + ('candidate_id',), 'lab-quartz-c0'),
        ('selection-cost', d + ('cost',), 0),
        ('selection-gain', d + ('estimated_gain',), 100),
        ('wrong-stop-action', d + ('action',), 'STOP'),
        ('missing-reason', d + ('reason',), ''),
        ('rank-score', d + ('ranking', 0, 'score'), 999),
        ('rank-feature', d + ('ranking', 0, 'gain'), 999),
        ('rank-false-cost', d + ('ranking', 0, 'terms', 'cost'), False),
        ('fake-accepted-evidence', d + ('evidence', 'accepted'), []),
        ('oracle-verdict', row + ('oracle', 'verdict'), 'MUST_STOP'),
        ('oracle-eligibility', row + ('oracle', 'eligible'), []),
        ('oracle-opportunities', row + ('oracle', 'opportunities'), []),
        ('oracle-labels', ('runs', 0, 'oracle_labels', 'worthwhile_ids'), []),
        ('outcome-status', row + ('outcome', 'status'), 'OBSERVED'),
        ('outcome-fact', row + ('outcome', 'facts', 'fact-01'), 'forged'),
        ('unknown-select', ('runs', 6, 'rows', 0, 'decision', 'action'), 'SELECT'),
        ('false-missed-opportunity-zero', ('evaluation', 'table', 3, 'missed_opportunity'), 0),
        ('self-certified-stop', ('evaluation', 'table', 3, 'correct_stop'), 1),
        ('false-unsafe-zero', ('evaluation', 'table', 0, 'unsafe_select'), False),
        ('metric-cost', ('evaluation', 'table', 0, 'simulated_cost'), 999),
        ('denominator', ('evaluation', 'summaries', 'development', 'PGE-v2', 'stop_correctness', 'denominator'), 999),
        ('paired-gain', ('evaluation', 'pairs', 0, 'facts_delta'), 999),
        ('metric-definition', ('evaluation', 'definitions', 'correct_stop'), 'all stops are correct'),
        ('forged-verified', ('runs', 21, 'rows', 0, 'visible_records', 0, 'status'), 'VERIFIED'),
        ('roster-self-anchor', row + ('roster', 'entries', 'self-issued'), '6' * 64),
        ('duplicate-original-record', row + ('visible_records',), []),
        ('reordered-candidate-order-forgery', ('runs', 3, 'snapshot', 'candidates', 0, 'order'), 6),
    ]


def set_value(value, path, replacement):
    node = value
    for key in path[:-1]:
        node = node[key]
    c.require((type(node) is dict and path[-1] not in node) or not c.equal(node[path[-1]], replacement), 'INVALID_NO_OP')
    node[path[-1]] = replacement


def mutant(original, index):
    all_specs = specs()
    value = copy.deepcopy(original)
    if index < len(all_specs):
        name, path, replacement = all_specs[index]
        if name == 'duplicate-original-record':
            replacement = copy.deepcopy(original['runs'][0]['rows'][0]['visible_records']) * 2
        set_value(value, path, replacement)
        if name == 'reordered-candidate-order-forgery':
            value['runs'][3]['snapshot']['candidates'].reverse()
    else:
        i = index - len(all_specs)
        name = 'compound-%02d' % (i + 1)
        # Twelve distinct attacks couple inner semantics with self-signed linkage.
        first, second = ((29, 27), (35, 27), (52, 46), (40, 50), (53, 54), (18, 38),
                         (15, 36), (32, 28), (49, 48), (41, 59), (22, 56), (43, 58))[i]
        for n in (first, second):
            _, path, replacement = all_specs[n]
            set_value(value, path, replacement)
        for run in value['runs']:
            for row in run['rows']:
                # Fully re-anchor forged evidence into the supplied roster.
                for record in row['visible_records']:
                    row['roster']['entries'][record['evidence_id']] = c.digest(record)
                row['roster_sha256'] = c.digest(row['roster'])
        if i == 5:
            for x in value['runs'][0]['snapshot']['candidates']:
                x['contract_sha256'] = c.digest({k: v for k, v in x.items() if k != 'contract_sha256'})
            value['runs'][0]['rows'][0]['snapshot_sha256'] = c.snapshot_sha(value['runs'][0]['snapshot'])
    return name, reanchor(value)


def prepare_negative(original, directory):
    verify(original)
    directory = c.allowed_file(Path(directory) / 'scope.json').parent
    directory.mkdir(parents=True, exist_ok=False)
    entries = []
    for index in range(len(specs()) + 12):
        name, value = mutant(original, index)
        path = directory / (name + '.json')
        raw = c.canonical(value)
        with path.open('xb') as f:
            f.write(raw)
        entries.append(dict(name=name, file=str(path.relative_to(c.ROOT)).replace('\\', '/'),
                            original_sha256=c.digest(original), raw_sha256=c.sha(raw),
                            compound=index >= len(specs()), expected_exit=3))
    result = dict(status='PREPARED_NOT_EXECUTED', controls=entries)
    (directory / 'controls.json').write_bytes(c.canonical(result))
    return result


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
            code, result = verify_file(args.file, args.sha) if args.file else (2, dict(status='NOT_RUN', reason='FILE_REQUIRED'))
        elif args.command == 'freeze':
            result = dict(source=c.source_map(), source_sha256=c.source_identity())
            with (c.WORK / 'source-freeze.json').open('xb') as f:
                f.write(c.canonical(result))
            code = 0
        else:
            frozen = c.strict((c.WORK / 'source-freeze.json').read_bytes())
            c.require(c.equal(frozen['source'], c.source_map()), 'SOURCE_FROZEN')
            path = c.allowed_file(args.file)
            if args.command == 'run':
                value = run(reverse=args.reverse)
                checked = verify(value)
                with path.open('xb') as f:
                    f.write(c.canonical(value))
                result = dict(status='PASS', raw_sha256=c.sha(path.read_bytes()), verification=checked)
            else:
                code, result = verify_file(path, args.sha)
                c.require(code == 0, result['reason'])
                result = prepare_negative(c.strict(path.read_bytes()), args.directory)
            code = 0
    except (c.Invalid, OSError, KeyError, TypeError, IndexError) as exc:
        code, result = 3, dict(status='FAIL', reason=str(exc) if isinstance(exc, c.Invalid) else type(exc).__name__)
    print(c.canonical(result).decode())
    return code


if __name__ == '__main__':
    raise SystemExit(main())
