# RunProof Glossary

[English](GLOSSARY.md) | [简体中文](GLOSSARY.zh-CN.md) | [Reliability Model](RELIABILITY_MODEL.md)

RunProof keeps the following technical terms in English in identifiers, raw evidence, routes, and status values. The Web may add localized explanations, but translation does not change canonical bytes.

| Term | Meaning in RunProof |
|---|---|
| Agent | A versioned actor under evaluation. Its behavior is evaluated separately from platform and environment health. |
| Agent Version | The behavior identity of an Agent, including model/provider reference, prompt/config, tool/runtime revision, and contract version. |
| Run | One execution bound to Agent, Scenario, Environment, Verifier, timeline, state, and outcome identity. |
| Trajectory | Observable actions, tool calls/results, faults, transitions, retries, recovery, and outcome facts; never private chain-of-thought. |
| State Diff | A verified before/after comparison of relevant environment state. |
| Controlled Simulation Environment | A fresh, owned, observable environment for safe side-effect and fault scenarios. |
| Evidence | Verified raw facts and stable references that support a conclusion. |
| Failure Case | A reproducible, validated failure identity with source/reproduction and evidence refs. |
| Regression | A historical expected behavior with explicit promotion, stability, and focused-rerun evidence. |
| Failure Intelligence | Deterministic attribution, first meaningful divergence, exact grouping, structural family, and version location. It cannot auto-promote or release. |
| Exact signature | Stable identity for the same failure bytes/contract. Historical signature semantics are preserved. |
| Structural family | A broader deterministic recurrence group. It must not erase domain or exact Failure Case identity. |
| Version Bisect | Fail-closed location of a first bad candidate under a compatible Regression oracle. |
| Statistical Evaluation | Repeated controlled trials under a frozen Sampling Plan; it is not a live Provider probability estimate. |
| Valid Agent denominator | `AGENT_PASS + AGENT_FAIL`; the denominator for Agent quality. |
| Attempted/evidence denominator | All relevant attempted/evidence observations, including platform, invalid, inconclusive, and cancelled observations. |
| Wilson score interval | The interval method used by the current controlled statistical contract. |
| `OBSERVED_FLAKY` | A review observation for inconsistent outcomes; not an automatic live probability claim. |
| Quality Policy | Versioned rules and precedence used to evaluate evidence sufficiency, blockers, warnings, and review. |
| Release Gate | The policy evaluation boundary that produces a decision input. |
| Release Decision | A separate, immutable or superseding decision record; `ELIGIBLE` is decision-only. |
| `UNKNOWN_OUTCOME` | A side-effect operation may have occurred, but response/receipt is uncertain. |
| `RECONCILE_REQUIRED` | Environment/receipt reconciliation is required before retry or a new side effect. |
| `PASS` / `FAIL` | Agent-facing execution outcomes when the evidence is valid and attributable. |
| `ERROR` | Platform, Provider, Environment, or execution failure outside the Agent quality contract. |
| `INVALID` / `INCONCLUSIVE` / `CANCELLED` | Non-quality, insufficient, or intentionally stopped execution states. |
| Control Plane | The formal Java/Spring API and canonical metadata authority used by Web, worker, seed, and CI boundaries. |
| Artifact Store | The immutable storage boundary for verified evidence bytes. |
| Durable Worker | The independent process that claims Jobs, fences attempts, reconciles uncertain operations, and reports evidence. |
| Observability signal | Optional diagnostic telemetry produced by the formal OpenTelemetry boundary; it is not canonical Evidence, a Quality Gate input, or Release authority. |
| Trace identity | OpenTelemetry `trace_id` / `span_id` used for correlation only; it is separate from RunProof Job, Attempt, Run, Environment, and Operation identity. |
| Telemetry completeness | A bounded diagnostic state such as `COMPLETE`, `PROPAGATION_MISSING`, or `EXPORT_UNAVAILABLE`; it does not change the canonical Run outcome. |
| W3C Baggage allowlist | The small set of low-risk correlation keys allowed to cross service boundaries; it excludes secrets, prompts, bodies, reasoning, and error narratives. |
| Golden Demo | The local reviewed-evidence walkthrough and lifecycle boundary; not a Production deployment. |

## Naming rule

Public documents use English canonical filenames with `.zh-CN.md` Chinese companions. Governance remains single-source: `AGENTS.md`, `docs/project/PROJECT_BRIEF.md`, `docs/project/DECISIONS.md`, and `docs/project/CURRENT_STATE.md` are not duplicated as translated Project-State files.
