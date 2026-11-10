"""Offline verifier negative controls. Fixture bytes carry no physical authority."""
from copy import deepcopy
from io import BytesIO
import unittest
from zipfile import ZipFile

from ci.test_rpf107_contracts import model_message
from ci.test_rpf107_host import LOCAL, first, fixture, offer
from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r107_capsule as capsule, pge_r107_model_loopback as model
from runtime.runproof_runtime.effectwitness import pge_r107_oracle as oracle
from runtime.runproof_runtime.effectwitness.pge_r107_host import application
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, sha


def rechain(rows):
    previous = "0" * 64
    raw = []
    for row in rows:
        entry = {key: value for key, value in row.items() if key != "sha256"}
        entry["previous"] = previous
        previous = inner.digest(entry)
        raw.append(canonical(entry | {"sha256": previous}) + b"\n")
    return b"".join(raw)


class OracleTests(unittest.TestCase):
    @unittest.skipUnless(LOCAL, "Requires admitted fresh-owner SQLite fixtures")
    def test_protocol_recomputes_bytes_after_reanchoring(self):
        with fixture() as (controller, host):
            seed = controller.ledger.snapshot()
            self.assertEqual(first(host)[0], 200)
            call = offer(host)
            self.assertEqual(host.handle(model.TOOL_PATH, canonical(call))[0], 200)
            late = model_message(host.frozen["feedback"], call, host.tool_result)
            self.assertEqual(host.handle(model.MODEL_PATH, canonical(late))[0], 409)
            host.journal.append("SDK_EXIT", {"fixture": True})
            raw = host.journal.path.read_bytes()
            rows = oracle.trace(raw)
            state, ledger = controller.ledger.persisted()
            claim = [row["body"] for row in ledger if row["kind"] == "CLAIMED"][1]
            decision = {key: claim[key] for key in ("proposal", "decision")}
            final = controller.ledger.snapshot()
            args = (seed, final, state["feedback_sha256"], decision)
            callback, exited = oracle.verify_protocol(host.frozen, rows, *args)
            self.assertEqual(callback["call"], call)
            self.assertEqual(exited, {"fixture": True})
            with self.assertRaises(FileNotFoundError):
                oracle.verify_sdk(host.frozen, host.journal.path.parent, callback, exited)
            tampered = deepcopy(rows)
            tampered[7]["body"]["application"] = application(canonical(late | {"model": "foreign"}))
            with self.assertRaisesRegex(ValueError, "MODEL_REQUEST"):
                oracle.verify_protocol(host.frozen, oracle.trace(rechain(tampered)), *args)
            tampered = deepcopy(rows)
            tampered[5]["body"]["decision"]["decision_sha256"] = "a" * 64
            with self.assertRaisesRegex(ValueError, "BRIDGE_DECISION"):
                oracle.verify_protocol(host.frozen, oracle.trace(rechain(tampered)), *args)
            with self.assertRaisesRegex(ValueError, "BRIDGE_TRUNCATED"):
                oracle.trace(raw[:-1])
            self.assertEqual(host.journal.path.read_bytes(), raw)

    def test_missing_zip_member_wrong_anchor_and_forged_issuer(self):
        source, run, owner = "a" * 40, "b" * 32, "c" * 32
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("manifest.json", b"{}")
        raw = stream.getvalue()
        with self.assertRaisesRegex(ValueError, "CAPSULE_ANCHOR"):
            capsule.verify(raw + b"x", sha(raw), source, run, owner)
        with self.assertRaisesRegex(ValueError, "CAPSULE_MEMBERS"):
            capsule.verify(raw, sha(raw), source, run, owner)
        forged = {"schema": "rpf107-public-v1", "source_git_sha": source, "run_id": run, "owner": owner,
                  "cases": [{}, {}], "issuer": "INDEPENDENT", "external_provider_requests": 0,
                  "real_explorer": "NOT_RUN", "evidence_kind": "VERIFIED_LOCAL_SCRIPTED_SDK_PROJECTION"}
        with self.assertRaisesRegex(ValueError, "CAPSULE_SCOPE"):
            capsule.build(forged, source, run, owner)
