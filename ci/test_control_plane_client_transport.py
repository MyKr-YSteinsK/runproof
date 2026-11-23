from __future__ import annotations

import unittest
from io import BytesIO
from urllib.error import HTTPError

from runtime.runproof_runtime.control_plane_client import ControlPlaneClient, ControlPlaneClientError


class ControlPlaneClientTransportTests(unittest.TestCase):
    def test_json_and_binary_requests_share_safe_error_classification(self) -> None:
        calls = []

        def unavailable(request, *, timeout):
            content_type = request.get_header("Content-type")
            calls.append((request.get_method(), request.full_url, content_type, request.data, timeout))
            raw = (
                b'{"error":"PLATFORM_STORAGE_UNAVAILABLE","message":"secret"}'
                if content_type == "application/json" else b'["secret"]'
            )
            raise HTTPError(request.full_url, 503, "unavailable", {"X-Request-Id": "request-1"}, BytesIO(raw))

        client = ControlPlaneClient("http://example.test/api/v1", "test-token", opener=unavailable)
        with self.assertRaises(ControlPlaneClientError) as ingest:
            client.ingest({"entity_type": "RUN"})
        with self.assertRaises(ControlPlaneClientError) as upload:
            client.put_artifact_bytes("fixture/root", b"bytes")

        self.assertEqual(ingest.exception.code, "PLATFORM_STORAGE_UNAVAILABLE")
        self.assertEqual(upload.exception.code, "CONTROL_PLANE_HTTP_ERROR")
        for error in (ingest.exception, upload.exception):
            self.assertEqual(error.correlation_id, "request-1")
            self.assertTrue(error.retriable)
            self.assertNotIn("secret", str(error))
        self.assertEqual(calls, [
            ("POST", "http://example.test/api/v1/ingest/completed-evidence", "application/json",
             b'{"entity_type":"RUN"}', 8.0),
            ("POST", "http://example.test/api/v1/artifact-bytes?artifact_key=fixture%2Froot",
             "application/octet-stream", b"bytes", 8.0),
        ])
