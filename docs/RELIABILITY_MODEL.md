# RunProof Reliability Model

[English](RELIABILITY_MODEL.md) | [简体中文](RELIABILITY_MODEL.zh-CN.md) | [Architecture](ARCHITECTURE.md)

RunProof separates what the Agent did, what the platform could prove, and what a policy is allowed to conclude. This separation is the reliability contract.

## Outcome vocabulary

| Status | Meaning | Quality denominator |
|---|---|---|
| `PASS` | Required outcome and invariants were verified | Valid Agent result when attributable to the Agent |
| `FAIL` | Agent behavior violated a Scenario invariant or expected outcome | Valid Agent result; may become a Failure Case or Regression |
| `ERROR` | Platform, Provider, Environment, or execution infrastructure failed outside the Agent contract | Attempt/evidence history, not Agent quality success rate |
| `INVALID` | Scenario, verifier, identity, or input was not valid for evaluation | Attempt history; not a valid Agent trial |
| `INCONCLUSIVE` | Evidence is insufficient to decide safely | Blocks or requires review; never silently becomes PASS |
| `CANCELLED` | Execution was intentionally stopped before a valid conclusion | Attempt history; not a valid Agent trial |
| `UNKNOWN_OUTCOME` | A side-effecting operation may have happened but its response/receipt is uncertain | Must reconcile before retry |
| `RECONCILE_REQUIRED` | The environment or receipt must be checked before a safe next action | Safety blocker until reconciled |

`Agent FAIL != Platform ERROR`. A high Agent success rate plus a safety violation is still blocked: safety precedence is stronger than a point estimate.

## Evidence and investigation chain

```text
Observed Fact
    → Verified Result
    → Failure Case (reproducible identity)
    → Regression (explicit expected behavior)
    → Failure Intelligence (attribution / family / first divergence)
    → Statistical Evaluation (repeated observations)
    → Quality Gate
    → Release Decision (decision-only)
```

- **Run** is one execution with Agent, Scenario, Environment, Verifier, timeline, state, and outcome identity.
- **Trajectory / State Diff** explain observable actions and state transitions; they do not depend on private model reasoning.
- **Evidence** preserves verified raw facts and stable references. Derived conclusions link back to those facts.
- **Failure Case** is a reproducible, validated failure identity. It is not automatically a Regression.
- **Regression** adds an explicit expectation, reproduction, stability, and focused-rerun history.
- **Failure Intelligence** is deterministic attribution, first meaningful divergence, exact grouping, structural family, and version location. It does not auto-promote or release.

## Safety and recovery

When a response is lost after a possible side effect:

```text
side effect may have happened
        → UNKNOWN_OUTCOME
        → RECONCILE_REQUIRED
        → inspect receipt/state
        → prove effect count and final invariant
        → recover or stop safely
```

Lease expiry is not proof that a side effect did not happen. A worker must fence stale attempts, reconcile environment state, and preserve the operation identity. Blind whole-run retry is prohibited when safe recovery is unproven.

## Formal network fault profiles

RPF-28 adds the formal `multi-service-toxiproxy-v1` Environment without replacing the single-container Environment. Each run owns a fresh internal Docker network containing a target, dependency, Toxiproxy boundary, and Agent-shaped client. The client can reach only the data-plane proxy; fault activation and toxic configuration remain harness authority.

The versioned `rpf-network-fault-profile-v1` distinguishes `none`, `latency`, `timeout`, `dependency-unavailable`, `response-lost`, and `pre-side-effect-failure`. Evidence records `planned`, `triggered`, `observed`, and `reconciled` separately. A response lost after the target commits must show no successful client response, a stable operation receipt, exactly one effect, and reconcile-before-retry. A dependency or pre-side-effect failure must show the contrast: no receipt and zero effect. Readiness, initial state, fault reset, and cleanup are part of the terminal proof; an unverified cleanup quarantines the Environment.

## Optional OpenTelemetry diagnostic contract

RPF-30 adds a formal but optional OpenTelemetry path. The same canonical
execution semantics must hold when telemetry is disabled, when an external
Collector is healthy, and when the configured Collector is unavailable. The
disabled path is a no-op with no exporter thread; enabled export is bounded and
asynchronous, and queue drops/export failures are diagnostic health signals.
They must not turn a Run into `FAIL`, prevent terminal Evidence, introduce
blind retry, or block `UNKNOWN_OUTCOME` reconciliation.

W3C `traceparent` and a bounded allowlist of W3C Baggage correlate the Java
Control Plane, durable Job/Attempt, Python Worker, Agent/Tool, RPF-28
target/dependency, and verifier. Canonical `job_id`, `attempt_id`, `run_id`,
`environment_id`, and `operation_id` remain independent identities; trace/span
IDs are never business keys. Attempt reclaim keeps the Job correlation, starts a
new Attempt subtree, and may link the previous Attempt without pretending it is
the same execution.

The response-lost trace is useful for investigation only: an error span may
coexist with an Agent `PASS` when the target receipt, effect count, reconcile,
and verifier prove the Scenario. Telemetry completeness can be `COMPLETE`,
`PROPAGATION_MISSING`, or `EXPORT_UNAVAILABLE`; missing propagation is detected
but fails open for the canonical Run. Attributes and metric labels are
allowlisted, low-cardinality, and never contain credentials, prompts, bodies,
private reasoning, private paths, or canonical IDs as metric labels. The
Collector is an optional pinned verification fixture; there is no trace UI,
long-term retention, or Jaeger/Tempo/Grafana product dependency.

## Statistical Reliability

Statistical evaluation is separate from a single Evaluation/Comparison. A Sampling Plan freezes trial count, attempt budget, Agent/config, Scenario, environment sequence, metric definitions, and Wilson method/version.

- The valid Agent denominator contains `AGENT_PASS + AGENT_FAIL` only.
- Platform/Environment, Invalid, Inconclusive, and Cancelled observations remain in the attempted/evidence denominator and trial matrix, but do not become Agent successes or failures.
- A minimum valid sample is required; `1/1` or `3/3` is not enough when the policy requires a larger denominator.
- Wilson score intervals describe the controlled observation; the current deterministic corpus is not a live Provider probability estimate.
- `OBSERVED_FLAKY` is a review observation, not an automatic probability claim.
- A zero-tolerance safety event, harmful remediation, authority violation, Historical Regression failure, or blind retry after `UNKNOWN_OUTCOME` is a hard blocker.

Comparison classifications are `IMPROVED`, `REGRESSED`, `NO_CLEAR_DIFFERENCE`, or `INCOMPARABLE`, based on compatible plans, evidence sufficiency, and interval relationship rather than point estimate alone.

## Quality Policy and Release Decision

The current precedence is:

```text
HARD_BLOCKER → EVIDENCE_INSUFFICIENT → REVIEW_REQUIRED → ELIGIBLE
```

`ELIGIBLE`, `BLOCKED`, `REVIEW_REQUIRED`, and `INCONCLUSIVE` belong to the Release Decision domain, not the Run outcome domain. The decision records why it reached its state and links to Evaluation, Comparison, Regression, Failure, and Evidence refs. It never grants deployment authority.

## Current evidence boundary

The reviewed corpus demonstrates deterministic controlled semantics across two explicit Agents, the formal multi-service network fault Environment, Failure Intelligence, statistical cohorts, and PostgreSQL durable Trial Jobs. It does not establish long-term live Provider reliability, statistical significance at Production scale, Production remediation safety, or HA. See [VERIFICATION_HISTORY.md](history/VERIFICATION_HISTORY.md) for source identities and verification anchors.
