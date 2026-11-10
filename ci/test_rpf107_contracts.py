"""Pure request/schema controls. No SDK process or physical send."""
from copy import deepcopy
from pathlib import Path
from typing import get_args
import unittest
from unittest.mock import patch

from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r107_contracts as c, pge_r107_model_loopback as model
from runtime.runproof_runtime.effectwitness.pge_r107_sdk_client import Candidate
from runtime.runproof_runtime.effectwitness.sdk_presend_client import AuditDenied, guard
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import PINS, canonical

PACKAGE = {"python": "3.12.fixture", "exe_sha256": "a" * 64, "pins": PINS,
           "wheels": dict.fromkeys(PINS, "b" * 64)}


def model_message(feedback, call=None, value=None):
    messages = [{"role": "user", "content": c.prompt(feedback)}]
    if call is not None:
        messages.extend([{"role": "assistant", "tool_calls": [{"id": call["call_id"], "type": "function",
                          "function": {"name": c.TOOL, "arguments": canonical(call["arguments"]).decode()}}]},
                         {"role": "tool", "tool_call_id": call["call_id"], "content": canonical(value).decode()}])
    return {"model": c.MODEL, "messages": messages, "max_tokens": 128, "parallel_tool_calls": False,
            "tools": [{"type": "function", "function": {"name": c.TOOL, "parameters": {"type": "object",
                       "properties": {"candidate_id": {"type": "string", "enum": list(c.CHOICES)}},
                       "required": ["candidate_id"], "additionalProperties": False}}}]}


class ContractsTests(unittest.TestCase):
    def test_projection_is_only_seed_and_current_budget(self):
        frozen = inner.freeze(c.BASE, "1" * 32, "2" * 32, inner.source_identity())
        verdict = {"binding": inner.binding(frozen["catalog"][inner.SEED]), "outcome": inner.SUCCESS}
        view = {"phase": "VERIFIED", "remaining": inner.COST, "feedback_sha256": inner.digest(verdict)}
        feedback = c.project(frozen, view, verdict)
        self.assertEqual(set(feedback), {"schema", "seed", "remaining", "candidates"})
        self.assertEqual(feedback["candidates"], list(c.CHOICES))
        for bad in (view | {"phase": "READY"}, view | {"feedback_sha256": "0" * 64},
                    view | {"remaining": inner.LIMIT}):
            with self.assertRaisesRegex(ValueError, "SEED_PROJECTION"):
                c.project(frozen, bad, verdict)
        one = c.freeze(c.BASE, "9" * 32, "8" * 32, "SCRIPTED_OPS", frozen, feedback, PACKAGE)
        other = c.freeze(c.BASE, "9" * 32, "8" * 32, "FIXED_ORDER", frozen, feedback, PACKAGE)
        self.assertNotEqual(one["tool_call_id"], other["tool_call_id"])
        self.assertEqual(one["inner_scope"]["origin"], "LOCAL")
        self.assertEqual(one["inner_policy"], inner.POLICY)
        with self.assertRaisesRegex(ValueError, "INNER_MAPPING"):
            c.freeze(c.BASE, "9" * 32, "2" * 32, "SCRIPTED_OPS", frozen, feedback, PACKAGE)

    def test_tool_fields_prompt_enum_and_return_binding(self):
        feedback = {"schema": "fixture-feedback"}
        offer = c.tool_request("call_fixture", inner.OPS)
        valid = model_message(feedback)
        model.validate_request(canonical(valid), feedback)
        for key, value in (("model", "external"), ("parallel_tool_calls", True), ("max_tokens", 129),
                           ("endpoint", "unexpected"), ("messages", [{"role": "user", "content": "old"}])):
            with self.subTest(field=key), self.assertRaises(ValueError):
                model.validate_request(canonical(valid | {key: value}), feedback)
        injected = deepcopy(valid)
        injected["tools"][0]["function"]["parameters"]["properties"]["sql"] = {"type": "string"}
        with self.assertRaisesRegex(ValueError, "FIELDS"):
            model.validate_request(canonical(injected), feedback)
        model.validate_request(canonical(model_message(feedback, offer, c.UNKNOWN)), feedback,
                               callback=offer, tool_result=c.UNKNOWN)
        with self.assertRaisesRegex(ValueError, "SDK_RETURN_BINDING"):
            model.validate_request(canonical(model_message(feedback, offer, c.STOPPED)), feedback,
                                   callback=offer, tool_result=c.UNKNOWN)

    def test_reject_tool_injection_or_forged_accept(self):
        expected = c.tool_request("call_fixture", inner.OPS)
        self.assertEqual(c.validate_tool(canonical(expected), expected), inner.OPS)
        for bad in (expected | {"call_id": "other"}, expected | {"decision": "ACCEPT"},
                    expected | {"arguments": {"candidate_id": inner.OPS, "path": "fixture"}},
                    expected | {"arguments": {"candidate_id": "unknown"}}, [expected, expected]):
            with self.assertRaisesRegex(ValueError, "TOOL_BINDING"):
                c.validate_tool(canonical(bad), expected)

    def test_sdk_literal_and_network_audit_without_socket_io(self):
        self.assertEqual(get_args(Candidate), c.CHOICES)
        with patch("sys.addaudithook") as install:
            guard(41007, Path.cwd(), Path.cwd(), {"stage": "SDK_RUN"})
        audit = install.call_args.args[0]
        audit("socket.connect", (None, ("127.0.0.1", 41007)))
        with self.assertRaisesRegex(AuditDenied, "SOCKET_CONNECT_DENIED"):
            audit("socket.connect", (None, ("127.0.0.1", 41008)))
        with self.assertRaisesRegex(AuditDenied, "DNS_DENIED"):
            audit("socket.getaddrinfo", ("outside.invalid", 41007))
        with self.assertRaisesRegex(AuditDenied, "SUBPROCESS_DENIED"):
            audit("subprocess.Popen", ())
