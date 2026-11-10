"""Provider wire and callback controls without network or credentials."""
import unittest

from runtime.runproof_runtime.effectwitness import pge_r110_contracts as c
from runtime.runproof_runtime.effectwitness import pge_r110_explorer as explorer, pge_r110_provider as provider
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, strict


class ExplorerTests(unittest.TestCase):
    def test_refusal_error_timeout_and_malformed_choices(self):
        raw = provider.fixture(c.CHOICES[1], "dynamic")
        selected = provider.parse(raw, 200, 1, "fixture-request-1")
        self.assertEqual(explorer.validate_callback(explorer.callback(selected), selected), c.CHOICES[1])
        self.assertEqual(selected["provider_usage"], "NOT_RUN")
        for http, ms, code in ((500, 1, "PROVIDER_HTTP_ERROR"), (200, c.TIMEOUT_MS + 1, "PROVIDER_TIMEOUT")):
            with self.assertRaisesRegex(ValueError, code):
                provider.parse(raw, http, ms, "fixture-request-1")
        row = strict(raw)
        for finish, code in (("content_filter", "MODEL_REFUSAL"), ("aborted", "PROVIDER_TERMINAL_ERROR"),
                             ("length", "MODEL_TRUNCATED"), ("stop", "NO_TOOL_CALL")):
            bad = row | {"choices": [row["choices"][0] | {"finish_reason": finish}]}
            with self.assertRaisesRegex(ValueError, code):
                provider.parse(canonical(bad), 200, 1, "fixture-request-1")
        msg = row["choices"][0]["message"]
        tool = msg["tool_calls"][0]
        for bad_message in (msg | {"tool_calls": [tool, tool]}, msg | {"content": "PASS"},
                            msg | {"tool_calls": [tool | {"function": tool["function"] | {"arguments": "{bad"}}]}):
            bad = row | {"choices": [row["choices"][0] | {"message": bad_message}]}
            with self.assertRaises(ValueError):
                provider.parse(canonical(bad), 200, 1, "fixture-request-1")
        with self.assertRaisesRegex(ValueError, "CALLBACK_BINDING"):
            explorer.validate_callback(explorer.callback(selected | {"tool_call_id": "wrong"}), selected)
