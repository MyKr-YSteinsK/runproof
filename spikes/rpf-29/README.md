# RPF-29 — OpenTelemetry 端到端可观测性 Spike

这是一个 disposable Investigation，不是正式 Runtime 的 OTel 接入。它用
独立的 Java durable-job candidate、PostgreSQL、Python worker/agent、两个 HTTP
service、RPF-28 Toxiproxy boundary 和临时 OpenTelemetry Collector，验证
correlation、propagation、response-loss 解释能力与 Collector 故障隔离。

正式 Run/Evidence、receipt、effect count、reconcile 和 Release Decision 仍然
是唯一可靠结果；trace 只属于 operator/debug signal。

## Topology

```text
Java durable-job candidate
        │ PostgreSQL job metadata: traceparent + canonical IDs
        ▼
Python worker → Agent → Toxiproxy → target → dependency
      │             │                  │         │
      └─────────────┴──── OTLP/HTTP ───┴─────────┘
                              ▼
             OpenTelemetry Collector 0.157.0
                    ├─ file exporter
                    └─ debug exporter
```

The candidate deliberately uses a small manual OTLP/HTTP JSON emitter rather than
changing the formal Java/Python Runtime. This isolates the wire contract and makes
the SDK/auto-instrumentation decision explicit for a later RPF-30.

The disposable Collector is run as `0:0` only so its bind-mounted diagnostic file
exporter is writable on both the Linux hosted runner and Windows Docker Desktop.
That is a Spike portability measure, not a Production container security model.

## Commands

The probe requires Java 17, Maven, Python 3.12, Docker Desktop, and the existing
`postgres:16-alpine` and `ghcr.io/shopify/toxiproxy:2.12.0` images. It pulls the
pinned Collector image only when absent.

```powershell
mvn -q -f spikes/rpf-29/java/pom.xml package
python spikes/rpf-29/probe.py --run
python spikes/rpf-29/verify-evidence.py .local/rpf-29/rpf29-result.json

# Hosted-style focused run
python spikes/rpf-29/probe.py --run --hosted --output-dir .local/rpf-29-hosted
python spikes/rpf-29/verify-evidence.py .local/rpf-29-hosted/rpf29-result.json
```

All outputs are ignored under `.local/rpf-29/`; no reviewed corpus is refreshed.
The probe labels and removes only `com.runproof.plan=rpf-29` containers and does
not create a volume or mount the Docker socket into an Agent-shaped process.

## Contract findings

| Boundary | Finding |
|---|---|
| RunProof identity | `job_id`, `attempt_id`, `run_id`, `environment_id`, and `operation_id` remain present with telemetry disabled; `trace_id` is not a product identity. |
| Durable Job | PostgreSQL stores the originating `traceparent`; a reclaimed Attempt uses the same trace with a new Attempt subtree and a span link to the expired Attempt. |
| HTTP propagation | W3C `traceparent` crosses the Toxiproxy TCP boundary unchanged. Allowlisted canonical IDs use W3C Baggage; no arbitrary baggage is accepted. |
| Response loss | The graph contains mutation request, target commit, reset/transport error, `UNKNOWN_OUTCOME`, reconcile, receipt/effect count, and verifier. Exactly one mutation is observed. |
| Error semantics | A tool/HTTP span may be `ERROR`; after receipt reconcile the Agent/Run canonical outcome is `PASS`. |
| Fault provenance | `planned`, `triggered`, `observed`, and `reconciled` are separate attributes/events; Toxiproxy remains outside Agent authority. |
| Collector failure | Java/Python/services still complete canonical `PASS`; export failure is recorded as telemetry-unavailable and never becomes a Release Gate result. |
| Missing propagation | The verifier detects a broken trace graph while canonical response-loss/reconcile remains correct. |

## Candidate span and metric contracts

Stable span names are `runproof.job.create`, `runproof.job.claim`,
`runproof.job.execute`, `runproof.job.complete`, `runproof.agent.run`,
`runproof.tool.call`, `runproof.environment.provision`, `runproof.fault.activate`,
`runproof.target.mutate`, `runproof.dependency.request`,
`runproof.operation.reconcile`, and `runproof.verifier.evaluate`. Dynamic IDs are
attributes, never span names.

Candidate metrics use only bounded labels such as `scenario`, `fault_profile`,
`outcome`, `service`, `route`, and `status`. `run_id`, `job_id`, `attempt_id`,
`operation_id`, `trace_id`, `span_id`, artifact IDs, and arbitrary error messages
are explicitly forbidden metric labels.

The allowlist rejects Authorization/bearer values, database passwords, API keys,
raw prompts, private reasoning, complete HTTP bodies, cookies, credentials, and
local private paths. The spike does not export provider prompts, responses, or
DeepSeek credentials.

## Collector and backend decision

The machine-verifiable candidate is OTLP/HTTP JSON → official Collector → file and
debug exporters. Jaeger and Tempo were not needed to answer propagation or
causality questions; adding a backend would increase local/CI maintenance without
new evidence in this Spike. A future backend must remain replaceable and must not
become a canonical Evidence dependency.

Sampling recommendation is always-on for local/dev and focused hosted contract
checks, with any future error-retention/tail policy requiring a separate retention
and cost decision. The local overhead loop is directional only: synchronous export
to an available Collector is measurable, and an unavailable Collector is much
slower by design. Formal RPF-30 should use bounded asynchronous/batch exporters and
must re-measure startup, runtime and memory overhead before adoption.

## Boundary decision

`PROCEED_TO_FORMAL_OTEL = CONDITIONAL`.

The evidence is sufficient for a narrow RPF-30 candidate covering submit/claim/
terminal Java spans, Python worker/agent/tool/environment/reconcile spans,
low-cardinality metrics, W3C propagation, optional Collector export, and strict
redaction. It is not evidence for full auto-instrumentation, Production telemetry
SaaS, long-term retention, alerting, Web observability UI, or OTel fields in the
canonical PostgreSQL schema.
