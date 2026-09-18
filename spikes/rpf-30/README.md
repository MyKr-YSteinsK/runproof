# RPF-30 — Formal OpenTelemetry Observability

RPF-30 converts the RPF-29 wire candidate into an optional formal boundary:

```text
Control Plane → durable Job/Attempt → Python Worker → Agent/Tool
             → RPF-28 target/dependency propagation → reconcile → verifier
```

OpenTelemetry is diagnostic-only. Canonical Job, Attempt, Run, Environment,
Operation, Evidence, Quality Gate, and Release Decision records remain the
authority, and the canonical PostgreSQL schema does not store `trace_id`.

The implementation uses the official OpenTelemetry Java and Python SDKs with
OTLP/HTTP exporters. Spans are accepted by bounded asynchronous processors;
export failure and dropped telemetry are diagnostics. The formal Collector is
external, pinned to `otel/opentelemetry-collector-contrib:0.157.0`, and used
only for an ephemeral file-export verification boundary. Jaeger, Tempo,
Grafana, long-term retention, and a Web trace page are intentionally out of
scope.

## Commands

```powershell
python -m pip install --requirement runtime/requirements.txt
mvn -q test package -f control-plane/pom.xml
python spikes/rpf-30/probe.py --run
python spikes/rpf-30/verify-evidence.py .local/rpf-30/local/rpf30-result.json
```

Hosted-style focused verification uses the same bounded probe and writes to an
ignored CI directory:

```powershell
python spikes/rpf-30/probe.py --run --hosted --output-dir ci-results/rpf30
python spikes/rpf-30/verify-evidence.py ci-results/rpf30/rpf30-result.json
```

The probe covers disabled, enabled+healthy Collector, and enabled+unavailable
Collector modes; Java/PostgreSQL durable execution; Python Worker; response
loss with one effect and no blind retry; W3C `traceparent`; allowlisted W3C
Baggage; Attempt reclaim with a new subtree and span link; RPF-28
target/dependency propagation; sensitive-data and span-cardinality checks; and
exact cleanup. It does not call DeepSeek or execute release/deploy.

The probe output and Collector file are disposable under `.local/rpf-30/` or
`ci-results/rpf30/`. No historical reviewed corpus is refreshed by this probe.
