# RunProof Golden Demo

[English](DEMO.md) | [简体中文](DEMO.zh-CN.md) | [README](../README.md)

The Golden Demo is a local, reviewed-evidence walkthrough for the current RunProof product boundary. It is designed for a short interview or architecture review: Candidate → Evidence → Failure → Regression → Gate → Release Decision.

It does not call DeepSeek, require a Provider credential, create cloud resources, connect to real Production, or execute release/deploy.

## Prerequisites

- Windows with Docker Desktop and the existing `postgres:16-alpine` image available.
- Java 17+, Maven, Python 3.11+, and Node.js/npm.
- A free local port for PostgreSQL, the Control Plane, and Vite.

The demo uses the repository's reviewed corpus. It does not require `DEEPSEEK_API_KEY`.

## Start, inspect, stop, and resume

Start the formal Control Plane, seed reviewed artifacts idempotently, and start the Web surface:

```powershell
powershell -ExecutionPolicy Bypass -File demo/start-demo.ps1
```

Open <http://127.0.0.1:4173/overview>. The start script packages the formal `control-plane/`, starts or resumes the Demo-owned PostgreSQL resource, seeds through the formal HTTP/JSON client, reads back canonical metadata and verified artifacts, and then starts Vite in API-backed mode.

Stop while preserving the named volume, reviewed artifact copies, and local Demo state:

```powershell
powershell -ExecutionPolicy Bypass -File demo/stop-demo.ps1
```

Run the same start command again to resume. A repeated seed is expected to produce idempotent replays, not duplicate canonical records.

Remove only exact, Demo-owned resources and local copies after verifying that they are disposable:

```powershell
powershell -ExecutionPolicy Bypass -File demo/stop-demo.ps1 -RemoveData
```

Legacy resources without the current ownership label fail closed for destructive removal. A normal stop preserves data; removal is not a generic Docker cleanup command.

## Lifecycle contract

The Windows lifecycle probe checks the child-specific environment, worker `--allowed-root` containment, state-v2 process/session identity, foreign process/port/container negatives, startup rollback, restart, stop, and ownership-gated `RemoveData`:

```powershell
powershell -ExecutionPolicy Bypass -File demo/verify-lifecycle.ps1 -Mode contracts
powershell -ExecutionPolicy Bypass -File demo/verify-lifecycle.ps1 -Mode lifecycle
```

The Web child receives only its read boundary. The Worker receives only its worker boundary and explicit IO roots. The local state/log/bundle boundary must not contain credentials. This is a Windows local lifecycle check, not an OS sandbox or Production isolation claim.

## Three stories to show

### 1. Incident remediation and failure intelligence

The Incident Remediation Agent sees a symptom while an external dependency is unhealthy. A known-bad version misdiagnoses the incident and performs a harmful local remediation. The controlled environment exposes the violated invariant; the failure is reproduced into a Failure Case, clustered by deterministic Failure Intelligence, and promoted into a Regression. The fixed candidate observes the dependency and safe-stops instead.

This story demonstrates why an Agent `FAIL` is different from a platform `ERROR`, why exact identity and structural family are separate, and why no automatic promotion or release follows from an analysis.

### 2. Response loss after a side effect

The side effect succeeds, but the response is lost between the worker and the operation boundary:

```text
effect succeeds → response lost → UNKNOWN_OUTCOME
→ RECONCILE_REQUIRED → receipt/state proves one effect
→ recovered PASS, effect count = 1
```

The worker does not blind-retry. The response-lost Run, operation identity, reconcile evidence, and final State Diff remain inspectable.

### 3. Statistical Reliability and safety precedence

The Statistical surface contains controlled Stable, Flaky, Safety, and Evidence-poor cohorts. Expand the trial matrix to explain the valid Agent denominator, attempted/evidence denominator, Wilson interval, `OBSERVED_FLAKY`, and zero-tolerance safety precedence. A high pass rate cannot override a safety event or insufficient evidence.

## Suggested path

1. **Overview**: follow Candidate → Evidence → Failure → Regression → Gate and confirm both explicit Agents.
2. **Statistical**: inspect the four cohorts and interval-aware Comparison.
3. **Failure Intelligence**: open the Incident family, exact Failure Case, first divergence, and Version Bisect.
4. **Durable execution**: open the response-lost Run and show reconcile-before-retry.
5. **Release Decision**: show that `ELIGIBLE` is a decision-only outcome, not a deploy button.

Useful routes:

| Surface | Route |
|---|---|
| Overview | `/overview` |
| Agents | `/agents` |
| Statistical evaluations | `/statistical-evaluations` |
| Statistical comparisons | `/statistical-comparisons` |
| Failure Intelligence | `/failure-intelligence` |
| Version Bisects | `/version-bisects/version-bisect-8ad1ee6051c564080255` |
| Release Decisions | `/release-decisions` |
| Executions | `/executions` |

When the Control Plane is stopped, the Overview must show canonical data unavailable and must not silently display fixture data. Restarting the formal service and rerunning the start/seed path restores the API-backed view.

## Integrity and evidence

The versioned profile freezes Demo identity, two Agent identities, reviewed corpus refs, artifact/source hashes, expected assertions, and the no-Provider/no-cloud/no-release boundary:

- `demo/rpf-19-golden-demo-v1.json`
- `demo/verify-golden-demo.py --root . --json`
- `demo/seed_demo.py --root . --repeat 2 --json`

The formal Control Plane, PostgreSQL durable worker, reviewed RPF-16/RPF-17/RPF-18 corpus, and hosted Release Gate provide the evidence behind the screens. Historical source identities and hosted run links are collected in [VERIFICATION_HISTORY.md](history/VERIFICATION_HISTORY.md).

## Current limits

The Demo is a local/interview delivery surface, not Production deployment. It does not prove managed PostgreSQL HA, object-storage durability, multi-host supervision, human Approval, tenant/RBAC identity, broker/scheduler/autoscaling, live Provider probability, or real destructive remediation. The Web build may still report a shared-bundle size warning; that warning is separate from the evidence and authority contracts.
