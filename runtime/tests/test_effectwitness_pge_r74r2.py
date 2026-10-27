"""Pure pre-freeze checks; these do not constitute the RPF-74 rev-2 gates."""
import copy
import hashlib
import json
import unittest

from runtime.runproof_runtime.effectwitness import pge_r68_contracts as native
from runtime.runproof_runtime.effectwitness.pge_r74r2_slot_contract import slot, replay_usage


class SlotAndUsageTest(unittest.TestCase):
    def setUp(self):
        request = {'model': 'fixture', 'max_tokens': 512, 'messages': [{'role': 'user', 'content': 'hello'}]}
        proof = slot(native.DOMAINS[0], 1, 'TARGET', 1, len(native.canonical(request)), native.digest(request))
        request_raw = json.dumps(request)
        response = {'id': 'fixture-1', 'choices': [{'message': {}}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 20, 'total_tokens': 21}}
        self.row = {'request': request, 'request_raw': request_raw,
                    'request_raw_sha256': hashlib.sha256(request_raw.encode()).hexdigest(),
                    'response': response, 'response_raw': json.dumps(response, sort_keys=True,
                        separators=(',', ':'), ensure_ascii=True), 'proof': proof}
        self.report = {'input_tokens': 1, 'output_tokens': 20, 'requests': 1,
                       'tool_calls': 0, 'tool_callbacks': 0}

    def test_original_and_report_reanchor(self):
        self.assertEqual(replay_usage([self.row], self.report), self.report)
        bad = dict(self.report, input_tokens=2)
        with self.assertRaisesRegex(ValueError, 'SDK_USAGE_SUM_MISMATCH'):
            replay_usage([self.row], bad)

    def test_joint_usage_rewrite(self):
        row, report = copy.deepcopy(self.row), dict(self.report, input_tokens=2)
        row['response']['usage'].update(prompt_tokens=2, total_tokens=22)
        row['response_raw'] = json.dumps(row['response'], sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        with self.assertRaisesRegex(ValueError, 'SYNTHETIC_PROMPT_MISMATCH'):
            replay_usage([row], report)

    def test_native_slot_contract_and_invalid_bound(self):
        self.assertEqual(self.row['proof']['output_cap'], 256)
        with self.assertRaisesRegex(ValueError, 'SLOT_INPUT_BOUND'):
            slot(native.DOMAINS[0], 1, 'TARGET', 1, 10000, 'a' * 64)


if __name__ == '__main__':
    unittest.main()
