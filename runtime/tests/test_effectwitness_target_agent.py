"""Target boundaries and independent evidence checks. No paid Provider calls."""
import copy
import hashlib
import http.client
import json
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from runtime.runproof_runtime.models import RuntimeFailure
from runtime.runproof_runtime.effectwitness.contracts import ROOT, canonical, digest
from runtime.runproof_runtime.effectwitness.orders import AuthorityReader, OrderAdapter, OrderSandbox
from runtime.runproof_runtime.effectwitness.effect_oracle import evaluate_order_effect
from runtime.runproof_runtime.effectwitness.target_contracts import TargetContracts, arguments_for, strict_json
from runtime.runproof_runtime.effectwitness.target_driver import ProviderLedger, TargetToolHost, PydanticAgentDriver, TaskLock
from runtime.runproof_runtime.effectwitness.target_evidence import LIMITATIONS, seal, verify_bytes
from runtime.runproof_runtime.effectwitness.target_external import guard
from runtime.runproof_runtime.effectwitness.verifier import OrderEffectVerifier

LOCAL = ROOT / ".local/rpf-48/tests"


class TargetAgentTests(unittest.TestCase):
    def setUp(self):
        LOCAL.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=LOCAL)
        self.folder = Path(self.temp.name)
        self.contracts = TargetContracts.create("test-" + uuid.uuid4().hex)
        self.sandbox = None

    def tearDown(self):
        if self.sandbox and self.sandbox.path.exists():
            self.sandbox.cleanup()
        self.temp.cleanup()

    def host(self, fault="none"):
        c = TargetContracts.create(self.contracts.experiment["run_id"], fault=fault)
        self.contracts = c
        self.sandbox = OrderSandbox(c, self.folder / "business", storage_task="rpf-48")
        self.sandbox.initialize()
        reader = AuthorityReader(self.sandbox.path, c, storage_task="rpf-48")
        return TargetToolHost(c, OrderAdapter(self.sandbox), reader)

    def register(self, host, name, call_id="call-1", response="response-1", args=None):
        args = arguments_for(name, self.contracts.effect) if args is None else args
        host.register([{"id": call_id, "type": "function", "function": {
            "name": name, "arguments": canonical(args).decode()}}], response)
        return args

    def test_contract_versions_role_budget_and_identity_fail_closed(self):
        for section, key, value in (("execution", "role", "EXPLORER"), ("execution", "driver", "dynamic-import"),
                                   ("experiment", "owner", "rpf-46"), ("effect", "amount_minor", 1)):
            doc = self.contracts.document()
            doc[section][key] = value
            with self.assertRaises(RuntimeFailure):
                TargetContracts.from_document(doc)
        doc = self.contracts.document()
        del doc["execution"]["agent_id"]
        with self.assertRaises(RuntimeFailure):
            TargetContracts.from_document(doc)
        self.assertNotEqual(TargetContracts.create("reference", driver="deterministic-reference").execution["framework"],
                            self.contracts.execution["framework"])

    def test_strict_json_and_illegal_arguments_never_reach_database(self):
        host = self.host()
        for raw in ('{"x":1,"x":2}', '{', '{"x":NaN}'):
            with self.assertRaises((RuntimeFailure, ValueError)):
                strict_json(raw)
        for name, args in (("shell", {"url": "https://example.invalid"}),
                           ("refund_order", {**arguments_for("refund_order", self.contracts.effect), "amount_minor": 2500.0}),
                           ("inspect_order", {"order_id": "other", "path": "../secret"})):
            with self.assertRaises(RuntimeFailure):
                self.register(host, name, args=args)
        self.assertEqual(host.authority.validate(host.authority.read())["receipts"], [])

    def test_documented_index_extension_does_not_relax_business_or_other_fields(self):
        host = self.host()
        call = {"id": "indexed", "type": "function", "index": 0, "function": {"name": "inspect_order",
                "arguments": canonical(arguments_for("inspect_order", self.contracts.effect)).decode()}}
        host.register([call], "response-indexed")
        self.assertEqual(host.intents["indexed"]["name"], "inspect_order")
        for patch_value in ({"index": True}, {"index": 1}, {"extra": "forbidden"}):
            altered = {**call, "id": "other", **patch_value}
            with self.assertRaises(RuntimeFailure):
                host.register([altered], "response-bad")

    def test_observe_first_duplicate_id_and_intent_binding(self):
        host = self.host()
        args = self.register(host, "refund_order")
        with self.assertRaisesRegex(RuntimeFailure, "OBSERVE_FIRST"):
            host.invoke("call-1", "refund_order", args)
        with self.assertRaisesRegex(RuntimeFailure, "DUPLICATE"):
            self.register(host, "inspect_order")
        args = self.register(host, "inspect_order", "call-2")
        with self.assertRaisesRegex(RuntimeFailure, "BINDING"):
            host.invoke("call-2", "inspect_order", {"order_id": "other"})
        host.invoke("call-2", "inspect_order", args)
        with self.assertRaisesRegex(RuntimeFailure, "REPLAY"):
            host.invoke("call-2", "inspect_order", args)

    def test_unknown_outcome_requires_agent_reconciliation_no_blind_retry(self):
        host = self.host("response-lost")
        for name, cid in (("inspect_order", "inspect"), ("refund_order", "refund")):
            args = self.register(host, name, cid)
            result = host.invoke(cid, name, args)
        self.assertEqual(result["status"], "UNKNOWN_OUTCOME")
        args = self.register(host, "refund_order", "retry")
        with self.assertRaisesRegex(RuntimeFailure, "RECONCILE_REQUIRED"):
            host.invoke("retry", "refund_order", args)
        args = self.register(host, "reconcile_order", "reconcile")
        self.assertEqual(host.invoke("reconcile", "reconcile_order", args)["status"], "RECONCILED_COMMITTED")
        with self.assertRaisesRegex(RuntimeFailure, "ALREADY_COMMITTED"):
            host.invoke("retry", "refund_order", arguments_for("refund_order", self.contracts.effect))
        self.assertEqual(len(host.authority.validate(host.authority.read())["receipts"]), 1)

    def test_missing_authority_does_not_establish_effect(self):
        host = self.host()
        host.authority.available = False
        result = OrderEffectVerifier(self.contracts, host.authority)(host.before, None)
        self.assertEqual(result["contract_outcome"], "INCONCLUSIVE")

    def test_timeout_and_steps_block_before_tool_effect(self):
        host = self.host()
        args = self.register(host, "inspect_order")
        host.started = time.monotonic() - 1201
        with self.assertRaisesRegex(RuntimeFailure, "TIMEOUT"):
            host.invoke("call-1", "inspect_order", args)
        host.started = time.monotonic()
        host.steps = 12
        with self.assertRaisesRegex(RuntimeFailure, "STEPS"):
            host.invoke("call-1", "inspect_order", args)
        self.assertEqual(host.calls, [])

    def test_tool_return_roundtrip_cannot_be_forged(self):
        host = self.host()
        args = self.register(host, "inspect_order")
        result = host.invoke("call-1", "inspect_order", args)
        with self.assertRaisesRegex(RuntimeFailure, "RETURN_SET"):
            host.verify_returns([{"role": "user"}], 2)
        with self.assertRaisesRegex(RuntimeFailure, "RETURN_CONTENT"):
            host.verify_returns([{"role": "tool", "tool_call_id": "call-1", "content": "{}"}], 2)
        self.assertEqual(host.verify_returns([{"role": "tool", "tool_call_id": "call-1", "content": canonical(result).decode()}], 2)[0]["result_sha256"], digest(result))

    def test_persistent_unknown_usage_and_unclosed_trial_freeze_followups(self):
        ledger = ProviderLedger(self.folder / "ledger.json", fixture=True)
        ledger.start_trial("first")
        ledger.reserve({}, "first", [])
        reopened = ProviderLedger(ledger.path, fixture=True)
        self.assertFalse(reopened.usage()["usage_known"])
        with self.assertRaisesRegex(RuntimeFailure, "USAGE_UNKNOWN"):
            reopened.reserve({}, "first", [])
        with self.assertRaises(RuntimeFailure):
            reopened.start_trial("second")
        with self.assertRaises(RuntimeFailure):
            reopened.received(reopened.data["requests"][0], {"id": "bad", "model": "deepseek-flash", "usage": {}})

    def test_hard_request_token_trial_budgets(self):
        ledger = ProviderLedger(self.folder / "ledger.json", fixture=True)
        ledger.start_trial("first")
        for i in range(6):
            r = ledger.reserve({}, "first", [])
            ledger.received(r, {"id": "response-" + str(i), "model": "deepseek-flash",
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
        with self.assertRaises(RuntimeFailure):
            ledger.reserve({}, "first", [])
        ledger.finish_trial("first", True)
        ledger.start_trial("second")
        ledger.finish_trial("second", True)
        with self.assertRaises(RuntimeFailure):
            ledger.start_trial("third")
        other = ProviderLedger(self.folder / "other.json", fixture=True)
        other.start_trial("one")
        with self.assertRaises(RuntimeFailure):
            other.reserve({"too_big": "x" * 15000}, "one", [])

    def test_task_lock_rejects_second_writer_and_preserves_crash_hold(self):
        path = self.folder / "owner.lock"
        with TaskLock(path):
            with self.assertRaises(FileExistsError):
                with TaskLock(path):
                    self.fail("second writer admitted")
        self.assertFalse(path.exists())
        with self.assertRaises(RuntimeError):
            with TaskLock(path):
                raise RuntimeError("fixture crash")
        self.assertTrue(path.exists())

    def test_child_guard_denies_shell_external_network_and_file_escape(self):
        audit = guard(12345, self.folder, [])
        for event, args in (("subprocess.Popen", ("cmd",)), ("socket.connect", (None, ("example.com", 443))),
                            ("socket.connect", (None, ("127.0.0.1", 8765))),
                            ("open", (str(ROOT / "private.txt"), "w", 1)),
                            ("socket.getaddrinfo", ("api.deepseek.com", 443))):
            with self.assertRaises(PermissionError):
                audit(event, args)
        audit("socket.connect", (None, ("127.0.0.1", 12345)))

    def test_scoped_process_timeout_has_no_provider_and_terminates(self):
        host = self.host()
        ledger = ProviderLedger(self.folder / "ledger.json", fixture=True)
        ledger.start_trial(self.contracts.experiment["run_id"])
        class FakeProcess:
            returncode = -1
            killed = False
            def communicate(self, *_args, **_kwargs):
                if not self.killed:
                    raise subprocess.TimeoutExpired("fixture", 1)
                return b'{"status":"STOPPED"}', b''
            def kill(self):
                self.killed = True
            def poll(self):
                return self.returncode
        fake = FakeProcess()
        with patch("subprocess.Popen", return_value=fake) as popen:
            report = PydanticAgentDriver(self.folder / "python.exe", self.folder / "child", fixture_completion=lambda _: {}).run(self.contracts, host, ledger)
        self.assertTrue(fake.killed)
        self.assertEqual(report["failure"]["code"], "TARGET_PROCESS_TIMEOUT")
        self.assertNotIn("DEEPSEEK_API_KEY", popen.call_args.kwargs["env"])
        self.assertEqual(ledger.usage()["provider_http_attempts"], 0)

    def test_missing_credentials_blocks_before_process_or_request(self):
        host = self.host()
        ledger = ProviderLedger(self.folder / "ledger.json")
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.Popen") as popen:
            with self.assertRaisesRegex(RuntimeFailure, "KEY_UNAVAILABLE"):
                PydanticAgentDriver(self.folder / "python.exe", self.folder / "child").run(self.contracts, host, ledger)
        popen.assert_not_called()
        self.assertEqual(ledger.usage()["provider_http_attempts"], 0)

    def test_real_loopback_host_rejects_unauthenticated_tool_without_effect(self):
        host = self.host()
        ledger = ProviderLedger(self.folder / "ledger.json", fixture=True)
        class FakeProcess:
            returncode = 1
            def communicate(self, data, **_kwargs):
                config = json.loads(data)
                connection = http.client.HTTPConnection("127.0.0.1", config["port"])
                connection.request("POST", "/tool", b'{}', {"Content-Type": "application/json"})
                response = connection.getresponse()
                self.status = response.status
                response.read()
                connection.close()
                return b'{"status":"SDK_ERROR","stage":"fixture","error_type":"HTTPError","denied":[],"guard_code":null}', b''
            def poll(self):
                return self.returncode
        fake = FakeProcess()
        with patch("subprocess.Popen", return_value=fake):
            report = PydanticAgentDriver(self.folder / "python.exe", self.folder / "child", fixture_completion=lambda _: {}).run(self.contracts, host, ledger)
        self.assertEqual(fake.status, 400)
        self.assertEqual(report["failure"]["code"], "HOST_AUTH_REJECTED")
        self.assertEqual(host.calls, [])
        self.assertEqual(host.authority.validate(host.authority.read())["receipts"], [])

    def fixture_bundle(self):
        host = self.host()
        args = self.register(host, "inspect_order")
        result = host.invoke("call-1", "inspect_order", args)
        host.verify_returns([{"role": "tool", "tool_call_id": "call-1", "content": canonical(result).decode()}], 2)
        snap = host.authority.read().public()
        requests = [{"attempt": i, "run_id": self.contracts.experiment["run_id"], "status": "RECEIVED", "response_id": "response-" + str(i),
            "intents": [host.intents["call-1"]] if i == 1 else [], "transport": "FIXTURE_TEST_ONLY",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "tool_returns": [] if i == 1 else [{"call_id": "call-1", "result_sha256": digest(result)}]} for i in (1, 2)]
        return seal({"schema_version": "rpf-target-evidence-v1", "source_level": "FIXTURE_TEST_ONLY", "contracts": self.contracts.document(),
            "sdk": {"source": "FIXTURE_TEST_ONLY"}, "calls": host.calls, "provider_requests": requests,
            "usage": {"tokens": 4, "input_tokens": 2, "output_tokens": 2, "provider_http_attempts": 0,
                      "usage_known": True, "automatic_retries": 0, "estimated_cost_cny_upper": 0.0},
            "authority_before": host.before.public(), "authority_after": snap,
            "effect": evaluate_order_effect(self.contracts.effect, self.contracts.experiment["environment_id"], host.before.public()["data"], snap["data"]),
            "fault": host.domain.fault, "controller_reconciliation": None, "cleanup": {}, "limitations": LIMITATIONS})

    def test_independent_evidence_corruption_false_live_and_external_anchor(self):
        bundle = self.fixture_bundle()
        raw = canonical(bundle)
        sha = hashlib.sha256(raw).hexdigest()
        self.assertEqual(verify_bytes(raw, sha)["source_level"], "FIXTURE_TEST_ONLY")
        self.assertEqual(verify_bytes(raw)["status"], "CONTENT_CHECKED_UNANCHORED")
        for mutate in (lambda b: b.update(source_level="EXTERNAL_AGENT_EFFECT_VERIFIED"),
                       lambda b: b["calls"][0].update(returned_in_request=1),
                       lambda b: b["authority_after"]["data"]["environment"].update(owner="rpf-46")):
            altered = copy.deepcopy(bundle)
            mutate(altered)
            del altered["digests"]
            with self.assertRaises(Exception):
                verify_bytes(canonical(seal(altered)))
        with self.assertRaises(RuntimeFailure):
            verify_bytes(raw, "0" * 64)
        with self.assertRaises(Exception):
            verify_bytes(raw[:-1])


if __name__ == "__main__":
    unittest.main()
