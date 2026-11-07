"""Summarize the bounded, redacted RPF-90 observation for the RPF-92 review."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COMMIT = 'd9e985d41249a72be06167dccd19bccb8d17892f'


def inspect(path):
    p = Path(path)
    parent = ROOT / '.local/rpf-92-competition'
    if not p.is_absolute() or '..' in p.parts or p.name != 'router-redacted.json':
        raise ValueError('INPUT_SCOPE')
    if p.parent.parent != parent or not re.fullmatch('[a-f0-9]{32}', p.parent.name):
        raise ValueError('INPUT_OWNER')
    for q in (p, *p.parents):
        if os.path.lexists(q):
            st = q.lstat()
            if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & 1024:
                raise ValueError('INPUT_REPARSE')
    st = p.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > 65536:
        raise ValueError('INPUT_FILE')
    with p.open('rb') as stream:
        current = os.fstat(stream.fileno())
        if (st.st_dev, st.st_ino, st.st_size) != (current.st_dev, current.st_ino, current.st_size):
            raise ValueError('INPUT_CHANGED')
        raw = stream.read(65537)
    if hashlib.sha256(raw).hexdigest() != 'a0689946a2c3890012a376f4a375e2e08a10847345febc73d4415a4a9cb0a168':
        raise ValueError('OBSERVATION_HASH')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('DUPLICATE_JSON')
            value[key] = item
        return value
    v = json.loads(raw, object_pairs_hook=pairs,
                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
    if (v.get('schema') != 'rpf90-router-failure-observation-v1'
            or v.get('run_id') != '42371085659' or v.get('attempt') != '1'
            or v.get('commit') != EXPECTED_COMMIT
            or v.get('evidence_kind') != 'HOSTED_SAME_RUN'
            or v.get('validation_status') != 'VALIDATED_FAILURE'):
        raise ValueError('OBSERVATION_IDENTITY')
    methods = v.get('error_methods')
    modules = v.get('failure_modules')
    if not isinstance(methods, list) or len(methods) != 12 or not isinstance(modules, list) or len(modules) != 6:
        raise ValueError('OBSERVATION_INVENTORY')
    expected_modules = {'test_contracts', 'test_control_plane_client', 'test_durable_worker',
                        'test_effectwitness_config_http', 'test_incident', 'test_quality'}
    rows = []
    for item in methods:
        tid = item.get('id', '')
        if (not isinstance(tid, str) or not re.fullmatch(r'test_[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.test_[A-Za-z0-9_]+', tid)
                or tid.split('.')[0] not in expected_modules or item.get('route') != 'PORTABLE'
                or item.get('executed') is not True
                or item.get('module') != 'runtime/tests/' + tid.split('.')[0] + '.py'):
            raise ValueError('OBSERVATION_METHOD')
        rows.append({'id': tid, 'attribution': 'UNAVAILABLE'})
    if len({x['id'] for x in rows}) != 12 or set(Counter(x['id'].split('.')[0] for x in rows)) != expected_modules:
        raise ValueError('OBSERVATION_METHOD_SET')
    for module in modules:
        calls = module.get('invocations')
        if (not isinstance(calls, list) or len(calls) != 2 or calls[0].get('exit') != 0
                or calls[1].get('exit') != 1
                or any(c.get('timeout') is not False or c.get('truncated') is not False for c in calls)):
            raise ValueError('OBSERVATION_RECEIPT')
    return {'schema': 'rpf92-router-attribution-v1', 'status': 'UNAVAILABLE',
            'reason': 'METHOD_EXCEPTION_DETAIL_NOT_IN_LEDGER', 'methods': rows,
            'historical_run': '42371085659', 'source_sha': EXPECTED_COMMIT,
            'no_new_runtime_execution': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.input), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
        print('{"status":"INVALID_INPUT"}')
        return 2


if __name__ == '__main__':
    sys.exit(main())
