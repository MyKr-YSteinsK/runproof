from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from runtime.runproof_runtime.control_plane_client import (
    ControlPlaneClient,
    ControlPlaneClientError,
    build_artifact_manifest,
)


class ControlPlaneClientTests(unittest.TestCase):
    def test_manifest_preserves_bytes_and_keeps_trajectory_out_of_summary(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = root / "runtime" / "reviewed-normal-run-v2.json"
        with tempfile.TemporaryDirectory() as directory:
            artifact = build_artifact_manifest(source, Path(directory))
            self.assertEqual(artifact.content, source.read_bytes())
            self.assertEqual(artifact.content_sha256, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(artifact.entity_type, "RUN")
            self.assertEqual(artifact.manifest["manifest_schema_version"], "rpf-canonical-ingest-v1")
            self.assertNotIn("trajectory", json.dumps(artifact.manifest["summary"]).lower())
            stored = Path(directory) / Path(*artifact.artifact_key.split("/"))
            self.assertEqual(stored.read_bytes(), source.read_bytes())

    def test_manifest_rejects_identity_path_traversal_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "malicious.json"
            source.write_text(json.dumps({
                "artifact_kind": "Run Evidence",
                "schema_version": "rpf-run-evidence-v2",
                "run": {"run_id": "../outside"},
            }), encoding="utf-8")
            with self.assertRaises(ControlPlaneClientError) as context:
                build_artifact_manifest(source, Path(directory) / "store")
            self.assertEqual(context.exception.code, "INVALID_ARTIFACT_PATH")
            self.assertFalse((Path(directory) / "outside").exists())

    def test_transport_reconcile_returns_existing_same_fingerprint(self) -> None:
        class ReconcileClient(ControlPlaneClient):
            def __init__(self) -> None:
                super().__init__("http://example.test/api/v1", "token")
                self.calls: list[str] = []

            def ingest(self, manifest):  # type: ignore[override]
                self.calls.append("POST")
                raise ControlPlaneClientError("uncertain", code="TRANSPORT_UNCERTAIN", retriable=True)

            def get(self, entity_type, entity_id):  # type: ignore[override]
                self.calls.append("GET")
                return {"canonical_metadata": {"artifact_ref": {"content_sha256": "a" * 64}}}

        client = ReconcileClient()
        response = client.ingest_with_reconcile({
            "entity_type": "RUN",
            "entity_id": "run-1",
            "artifact_ref": {"content_sha256": "a" * 64},
        })
        self.assertEqual(response["status"], "RECONCILED")
        self.assertEqual(client.calls, ["POST", "GET"])

    def test_http_error_classification_does_not_expose_body(self) -> None:
        class ErrorClient(ControlPlaneClient):
            @staticmethod
            def _raise_api_error(status, raw, correlation_id):
                ControlPlaneClient._raise_api_error(status, raw, correlation_id)

        with self.assertRaises(ControlPlaneClientError) as context:
            ErrorClient._raise_api_error(503, b'{"error":"PLATFORM_STORAGE_UNAVAILABLE","message":"secret"}', "request-1")
        self.assertEqual(context.exception.code, "PLATFORM_STORAGE_UNAVAILABLE")
        self.assertTrue(context.exception.retriable)
        self.assertNotIn("secret", str(context.exception))


if __name__ == "__main__":
    unittest.main()
