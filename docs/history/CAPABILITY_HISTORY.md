# RunProof Capability History

[English](CAPABILITY_HISTORY.md) | [简体中文](CAPABILITY_HISTORY.zh-CN.md) | [Verification History](VERIFICATION_HISTORY.md)

This is a capability-level history, not a plan log. It explains how the current Stabilization boundary was assembled; detailed evidence anchors are in [VERIFICATION_HISTORY.md](VERIFICATION_HISTORY.md).

| Stage | Capability assembled | Boundary retained |
|---|---|---|
| Bootstrap and probes | Agent contract, minimum Controlled Environment, and Provider/error classification experiments | Probes are disposable evidence; Docker is not a permanent Production identity |
| Stateful Run slice | Production Change reference Agent, Scenario, Tool loop, Docker state, response-loss reconcile, and Run Evidence | No general Agent SDK, streaming/thinking continuation, or real destructive Production operation |
| Evidence and investigation | Timeline, State Diff, Failure Case, Regression promotion, focused rerun, and read-only Web investigation | Source evidence is not silently rewritten; `FAIL` and `ERROR` remain distinct |
| Evaluation and policy | Evaluation Suite, Baseline/Candidate Comparison, Quality Policy, Release Gate, and decision-only Release Decision | `ELIGIBLE` is not deploy/release authority |
| Persistence and durable execution | Formal Java/Spring Control Plane, PostgreSQL canonical metadata, immutable artifacts, durable Jobs, worker leases, fencing, and reconcile | No broker, scheduler, autoscaling, Production HA, Approval, or tenant/RBAC claim |
| Production-like boundary | Candidate A replacement/restore evidence and Candidate B managed-persistence/stateless target comparison | Candidate A is local reproduction; Candidate B is not a completed cloud deployment |
| Cross-Agent investigation | Incident Remediation Agent, narrow integration contract, independent evidence domain, Failure Intelligence, Version Bisect, and statistical cohorts | No plugin marketplace, LLM/embedding/ML analysis, auto-promotion, or real remediation |
| Delivery surface | Golden Demo, API-backed Overview, lifecycle ownership checks, and hosted canonical CI Gate | Local/interview delivery is not Production release |
| Presentation and public docs | Web `en-US`/`zh-CN` presentation-only i18n followed by bilingual public documentation and a current/history split | Canonical governance remains single-source; raw evidence and identifiers remain English/unchanged |
| Formal diagnostic observability | Optional official Java/Python OpenTelemetry SDKs, W3C propagation, allowlisted correlation context, bounded asynchronous export, Collector health/unavailability diagnostics, and cross-service durable-run trace correlation | Telemetry is diagnostic only: trace/span identity is not canonical evidence, release authority, Web schema, retention, SaaS observability, or Production capacity proof |
| Object-backed artifact durability investigation | Disposable standard S3-compatible client boundary, conditional immutable create, replay/conflict classification, verified read, credential/fail-closed checks, restart/unavailable observation, and candidate comparison across SeaweedFS and RustFS | This is an investigation boundary only: `LocalFileArtifactStore` remains formal, no managed object-storage/HA/replication/lifecycle authority or Production durability claim is established |

The current active mode is `Feature Freeze / Portfolio Maintenance` within `Stabilization`. A new capability requires a new Plan and new evidence; it should not be inferred from this history.
