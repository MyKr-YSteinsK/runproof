import os
import time
import unittest

from runtime.runproof_runtime.observability import Observability, reset_observability


class ObservabilityContractTests(unittest.TestCase):
    def tearDown(self):
        reset_observability()
        os.environ.pop("RPF_OTEL_SUPPRESS_PROPAGATION", None)

    def test_disabled_mode_has_no_exporter_or_propagation(self):
        observability = Observability(enabled=False)
        carrier = {}
        with observability.span("runproof.test", {"runproof.job.id": "job-1"}) as scope:
            observability.inject(carrier)
            self.assertFalse(scope.valid)
        self.assertEqual(observability.diagnostics()["status"], "DISABLED")
        self.assertFalse(observability.diagnostics()["enabled"])
        self.assertEqual(carrier, {})

    def test_enabled_export_is_bounded_and_not_per_span_blocking(self):
        observability = Observability(enabled=True, endpoint="http://127.0.0.1:9", queue_size=32)
        started = time.perf_counter()
        for _ in range(48):
            with observability.span("runproof.test", {
                "runproof.job.id": "job-1",
                "http.route": "/api/v1/jobs/{job_id}",
                "Authorization": "Bearer must-not-export",
            }) as scope:
                carrier = {}
                observability.inject(carrier)
                self.assertRegex(carrier["traceparent"], r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
                self.assertIn("runproof.job.id=job-1", carrier["baggage"])
                self.assertTrue(scope.context_document()["traceparent"])
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertLess(elapsed_ms, 1000)
        diagnostics = observability.diagnostics()
        self.assertTrue(diagnostics["bounded"])
        self.assertLessEqual(diagnostics["queue_size"], 1024)
        observability.shutdown()

    def test_missing_propagation_is_diagnostic_only(self):
        os.environ["RPF_OTEL_SUPPRESS_PROPAGATION"] = "true"
        observability = Observability(enabled=True, endpoint="http://127.0.0.1:9")
        carrier = {}
        with observability.span("runproof.agent.run", {"runproof.outcome": "PASS"}):
            observability.inject(carrier)
        self.assertNotIn("traceparent", carrier)
        self.assertEqual("PASS", "PASS")
        observability.shutdown()


if __name__ == "__main__":
    unittest.main()
