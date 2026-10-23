"""RPF-66/rev-4 offline protocol investigation; paid modes fail closed.

The protected validator has a fourth, non-parameterized 256 output ceiling.
This runner proves that conflict without modifying responses or global state.
It does not implement the proposed v4 session ABI or issue a Witness.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from runtime.runproof_runtime.effectwitness import config_live_runtime as base

WORK = ROOT / '.local/rpf-66-rev-4'
CODE = 'PROTECTED_RESPONSE_OUTPUT_CEILING_256'
SOURCES = (
    'runtime/runproof_runtime/effectwitness/config_live_runtime.py',
    'runtime/runproof_runtime/effectwitness/config_live_contracts.py',
    'runtime/runproof_runtime/effectwitness/config_live_external.py',
    'runtime/runproof_runtime/effectwitness/pge_r66_target_config.py',
    'spikes/rpf-66/rev-4/probe.py',
)


def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCES}


def diagnose():
    before = hashes()
    rows = []
    for finish, output in [('stop', n) for n in (0, 128, 256, 257, 300, 512, 513)] + [
            ('length', 128), ('length', 256), ('length', 512),
            ('content_filter', 128), ('aborted', 128)]:
        response = dict(id='rpf66_rev4_offline_only', object='chat.completion',
            created=0, model=base.PROVIDER_MODEL,
            choices=[dict(index=0, finish_reason=finish,
                          message=dict(role='assistant', content='offline fixture'))],
            usage=dict(prompt_tokens=10, completion_tokens=output,
                       total_tokens=10 + output))
        original = json.dumps(response, sort_keys=True)
        try:
            base._validate_provider_response(response)
            outcome = 'ACCEPTED'
        except base.LiveRuntimeRejected as exc:
            outcome = exc.code
        assert json.dumps(response, sort_keys=True) == original
        expected = ('ACCEPTED' if output <= 256 else 'PROVIDER_OUTPUT_TOKEN_LIMIT') \
            if finish == 'stop' else 'PROVIDER_CHOICE'
        assert outcome == expected
        rows.append(dict(finish_reason=finish, completion_tokens=output,
                         result=outcome, expected=expected,
                         input_unchanged=True, transport_calls=0))
    assert hashes() == before
    assert base.LIMITS['max_output_tokens_per_request'] == 256
    return dict(schema='rpf66-rev4-terminal-boundary-diagnostic-v1',
        diagnostic_status='PASS', implementation_gate='BLOCKED', code=CODE,
        cases=rows, sources_raw_sha256=before, source_unchanged=True,
        parser='ORIGINAL_UNMODIFIED_DIRECT_CALL', patches=0,
        provider_calls=0, business_jvm_starts=0, sdk_starts=0,
        metadata_runs=0, cold_runs=0, key_accesses=0,
        full_runtime='NOT_RUN', source_freeze='NOT_RUN',
        witness='NOT_CREATED', paid='NOT_RUN')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('init', 'metadata', 'cold', 'admit', 'live', 'verify'))
    mode = parser.parse_args().mode
    if mode not in ('init', 'verify'):
        print(json.dumps(dict(status='BLOCKED', code=CODE, mode=mode,
                              resources_consumed=False)))
        return 3
    receipt = WORK / 'terminal-parser-diagnostic.json'
    if mode == 'init':
        assert WORK.is_dir() and not any(p.is_symlink() or p.is_junction()
            for p in (WORK, *WORK.parents))
        value = diagnose()
        with receipt.open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write('\n')
        print(json.dumps(dict(diagnostic='PASS', gate='BLOCKED', cases=len(value['cases']))))
        return 0
    value = json.loads(receipt.read_text(encoding='utf-8'))
    assert value == diagnose()
    print(json.dumps(dict(diagnostic='PASS', witness='NOT_CREATED', paid='NOT_RUN')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
