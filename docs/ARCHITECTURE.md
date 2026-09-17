# RunProof Architecture

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md) | [README](../README.md)

This document describes the current, evidence-backed architecture boundary. It is a product map, not a promise that every recommended Production component has been deployed.

## Architecture at a glance

```text
User / CI
    → Desktop Web Control Plane
    → Java / Spring Control Plane
    → PostgreSQL canonical metadata
    → Durable Job
    → Python Worker
    → Controlled Simulation Environment
    → Run / Trajectory / State Diff / Evidence
    → Quality Policy and Release Gate
    → Release Decision (decision-only)

Provider boundary ── optional input to an Agent run; outside the Golden Demo
Immutable Artifact Store ── verified evidence bytes referenced by the Control Plane
```

The primary path is HTTP/JSON through the formal Control Plane. The browser does not connect to PostgreSQL, hold worker or decision credentials, or silently fall back to fixture data when canonical API data is unavailable.

## Components and ownership

| Component | Current responsibility | Authority boundary |
|---|---|---|
| Desktop Web Control Plane | Read-only Overview, investigation, comparison, execution, and decision surfaces | Presentation only; no live Agent, worker, promotion, release, or deploy mutation |
| Java/Spring Control Plane | Canonical metadata, verified artifact registration/read-back, durable Job API, and decision history | Service principals are scoped; decision writing is separate from Agent/worker execution |
| PostgreSQL | Canonical metadata and durable Job/Attempt/Operation/Event state | Current formal transport is bounded poll/claim/lease; not a broker or HA claim |
| Immutable Artifact Store | Schema-, kind-, identity-, source-, and hash-verified evidence bytes | Candidate writers cannot create canonical verified/release authority |
| Python Agent/Evaluation Runtime | Agent contracts, controlled evaluation, evidence, regression, statistics, and HTTP client | Does not expose Provider credentials or release authority to the Web |
| Durable Worker | Claim, heartbeat, reconcile, execute an explicit profile, and report evidence | `UNKNOWN_OUTCOME` must reconcile before retry; worker cannot write Release Decision |
| Controlled Simulation Environment | Fresh, observable stateful environment for side-effect tools and fault scenarios | No real Production destructive credentials |
| Provider boundary | Optional model/provider call boundary; DeepSeek is the first reference Provider | Credentials stay outside Git, browser, evidence, and default traces |
| GitHub Actions Release Gate | Fresh CI checks, durable evaluation path, canonical Decision read-back, and redacted artifacts | CI records evidence; it does not execute release or deployment |

## Canonical data flow

1. A versioned Agent, Scenario, Environment, Verifier, and Evaluation identity define the candidate.
2. The Control Plane submits a durable Job. A worker claims it with lease and fencing identity.
3. The Agent operates only inside the Controlled Simulation Environment. Observable actions, transitions, receipts, and verification facts become Run and Evidence records.
4. The Control Plane stores canonical metadata and accepts only verified immutable artifact references.
5. Failure investigation may derive Failure Case, Regression, Failure Intelligence, Statistical Evaluation, and Comparison artifacts without rewriting source evidence.
6. Quality Policy produces a Gate and Release Decision. `ELIGIBLE` is a decision-only outcome; it is not a release command.

## Authority and recovery boundaries

- Agent and worker authority is narrower than decision-writer authority.
- `PASS`, `FAIL`, `ERROR`, `INVALID`, `INCONCLUSIVE`, and `CANCELLED` are execution outcomes; a Release Decision is a separate state domain.
- A lost response after a possible side effect becomes `UNKNOWN_OUTCOME` and then `RECONCILE_REQUIRED`; the system must prove the environment receipt/state before retrying.
- Historical Run, Evidence, Regression, and Decision facts are append-only or superseding. A later interpretation does not silently rewrite old bytes.
- Web/API failure is fail-closed. A missing or unverifiable artifact is not replaced with a static success fixture.

## Repository map and README audit

| Area | Its README is for | Public architecture entry |
|---|---|---|
| `control-plane/README.md` | Java build, server startup, API and worker implementation details | This document and [DEMO.md](DEMO.md) |
| `runtime/README.md` | Python runtime/evidence/evaluation entry points and contracts | [RELIABILITY_MODEL.md](RELIABILITY_MODEL.md) and [GLOSSARY.md](GLOSSARY.md) |
| `web/README.md` | Web adapter, read model, and presentation implementation | This document and [DEMO.md](DEMO.md) |
| `spikes/*/README.md` | Disposable investigations and historical probe boundaries | [VERIFICATION_HISTORY.md](history/VERIFICATION_HISTORY.md) |
| `demo/` | Golden Demo profile, seed, lifecycle, and verifier | [DEMO.md](DEMO.md) |
| `docs/project/` | Canonical governance and current project state | [README](../README.md) |

Module READMEs remain implementation-facing. Public claims are centralized here and in the paired public documents; no module README is promoted to a second Project-State authority.

## Claim → evidence map

| Claim | Evidence location | Verification entry |
|---|---|---|
| Durable execution and response-loss reconciliation | `control-plane/`, RPF-14 reviewed execution artifacts, response-lost Run | `python control-plane/probe.py`; RPF-14 evidence verifier |
| Two explicit Agent contracts | RPF-16 reviewed Agent-bearing corpus and `runtime/` contracts | `python spikes/rpf-16/probe.py --verify` |
| Deterministic Failure Intelligence and Version Bisect | RPF-17 reviewed artifacts and `spikes/rpf-17/` | `python spikes/rpf-17/verify-evidence.py` |
| Statistical Reliability boundary | RPF-18 reviewed statistical artifacts | `python spikes/rpf-18/verify-evidence.py` |
| API-backed, read-only Web | `web/src/data/`, `control-plane/`, reviewed corpus adapters | `npm test`; `npm run typecheck`; `npm run build` |
| Bilingual Control Plane presentation | `web/src/i18n/`, locale-aware view models, and RPF-25 compatibility tests | Web tests/typecheck/build; locale/API-unavailable checks |
| Hosted canonical Release Gate | `.github/workflows/release-gate.yml`, `ci/run_release_gate.py` | GitHub-hosted workflow and Job Summary contract |
| Golden Demo integrity and lifecycle | `demo/rpf-19-golden-demo-v1.json`, `demo/verify-golden-demo.py`, lifecycle verifier | `python demo/verify-golden-demo.py --root . --json` |

The detailed source identities, hosted runs, and historical compatibility facts are kept in [VERIFICATION_HISTORY.md](history/VERIFICATION_HISTORY.md), not repeated in the current snapshot.

## Production boundary

The current repository proves a controlled simulation, local production-like persistence/recovery, an explicit PostgreSQL durable workflow, immutable evidence, hosted CI checks, and a Windows local Golden Demo lifecycle. It does not prove or authorize Production HA, managed cloud deployment, object-storage durability, multi-host supervision, human Approval, tenant/RBAC identity, or real destructive remediation.

The next architectural boundary should be selected from measured need: realistic multi-service/network faults, OpenTelemetry-compatible observability, managed or S3-compatible artifact storage, and capacity/large-trace evidence. Those are investigations, not implicit additions to this architecture.
