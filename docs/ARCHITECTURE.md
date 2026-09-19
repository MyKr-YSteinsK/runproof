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
| Controlled Simulation Environment | Fresh, observable stateful environment for side-effect tools and fault scenarios; formal RPF-28 can compose target, dependency, Toxiproxy, and Agent-shaped client on a private network | No real Production destructive credentials; Agent sees only the data-plane boundary |
| Provider boundary | Optional model/provider call boundary; DeepSeek is the first reference Provider | Credentials stay outside Git, browser, evidence, and default traces |
| GitHub Actions Release Gate | Fresh CI checks, durable evaluation path, canonical Decision read-back, and redacted artifacts | CI records evidence; it does not execute release or deployment |

## Canonical data flow

1. A versioned Agent, Scenario, Environment, Verifier, and Evaluation identity define the candidate.
2. The Control Plane submits a durable Job. A worker claims it with lease and fencing identity.
3. The Agent operates only inside the Controlled Simulation Environment. The single-container path remains supported; the formal RPF-28 path uses a fresh Docker `--internal` network and keeps fault activation/observation in the Environment adapter. Observable actions, transitions, receipts, fault provenance, and verification facts become Run and Evidence records.
4. The Control Plane stores canonical metadata and accepts only verified immutable artifact references.
5. Failure investigation may derive Failure Case, Regression, Failure Intelligence, Statistical Evaluation, and Comparison artifacts without rewriting source evidence.
6. Quality Policy produces a Gate and Release Decision. `ELIGIBLE` is a decision-only outcome; it is not a release command.

## Formal diagnostic observability

The formal RPF-30 slice adds optional OpenTelemetry instrumentation across the
Java Control Plane, PostgreSQL durable Job/Attempt boundary, Python Worker,
Agent, Tool, Environment, RPF-28 target/dependency transport, reconcile, and
verifier. The SDK path uses W3C `traceparent` plus a small allowlisted W3C
Baggage set. `job_id`, `attempt_id`, `run_id`, `environment_id`, and
`operation_id` remain canonical RunProof identities; `trace_id` and `span_id`
are diagnostic identities only.

The three supported modes have the same canonical semantics: disabled/no-op,
enabled with a healthy external Collector, and enabled with an unavailable
Collector. Export is bounded and asynchronous; queue drops and export failures
are diagnostic counters/logs, never Agent outcomes. A response-lost Run can
therefore show the Job → Attempt → Agent → Tool → target/dependency → reconcile
graph while receipt, effect count, `UNKNOWN_OUTCOME`, verifier, Evidence, Gate,
and Decision remain owned by the canonical execution path.

The Collector is an optional pinned verification fixture, not a startup
dependency or authority. RPF-30 does not add a canonical trace field, trace
artifact, Web trace UI, Jaeger/Tempo/Grafana dependency, SaaS backend, or
long-term retention promise. Telemetry attributes and metric labels are
allowlisted and exclude credentials, prompts, bodies, private reasoning,
private paths, and high-cardinality IDs as metric labels.

## Formal S3-compatible artifact storage

RPF-32 adds `S3ArtifactStore` as an explicit provider adapter behind the same
provider-neutral `ArtifactStore` contract. `local` remains the default
backend; `s3` must be selected explicitly and an invalid backend fails closed.
The Control Plane, canonical metadata service, Web read model, and durable
worker do not depend on AWS or SeaweedFS types.

The object store holds immutable bytes only. PostgreSQL remains canonical for
artifact registration, entity identity, schema, source identity, RunProof
SHA-256, and metadata relationships. A cross-process Worker uploads bytes
through the authenticated Control Plane before manifest ingest; object
existence alone is never evidence. Conditional `PutObject` with
`If-None-Match: *` provides the first-create boundary. Same bytes reconcile as
an idempotent replay; different bytes are an immutable conflict. Unknown write
outcomes use bounded GET/retry reconciliation and never silently fall back to
the local store.

Verified reads use one object GET and then validate the body hash, JSON header,
schema, artifact kind, entity identity, source identity, and runtime identity.
ETag, versioning, and Object Lock are not RunProof identity. SeaweedFS `4.47`
is the pinned disposable compatibility provider for the current proof; the
result does not establish managed-object-store durability, HA, replication,
lifecycle/GC, capacity, migration, or Production release authority.

## Bounded canonical metadata read model

RPF-35 separates canonical metadata discovery from verified artifact detail.
`GET /api/v1/metadata` is bounded by default to 50 rows and capped at 100. Its
opaque `rpf-metadata-cursor-v1` keyset cursor binds the entity scope, ordering,
page size, and cursor version; malformed or incompatible cursors fail closed.
The primary type order is `created_at,entity_id:asc`, while bounded cross-type
discovery uses `created_at,entity_type,entity_id:asc`. The implementation uses
keyset predicates rather than `OFFSET`; the cross-type EXPLAIN is recorded and
its sequential scan is intentionally deferred to a future focused index plan.

Metadata pages return registered identity, summary, references, and ArtifactRef
facts with `REGISTERED_REFERENCE` availability. They do not read every artifact
body and do not claim that current bytes were re-verified. A canonical detail
read first obtains one metadata row with `verify=false`, then reads the selected
artifact through the existing Local/S3 verification authority. Hash, schema,
kind, entity, source, and runtime identity checks remain mandatory on that
detail path.

API-mode Web ownership is route-scoped: each canonical index requests one
bounded metadata page, each detail deep link requests only its entity metadata
and verified artifact, and Overview uses fixed reviewed Golden Demo references
and bounded aggregate dependencies. The App root no longer bootstraps a full
corpus or automatically crawls every metadata cursor. The legacy complete-corpus
adapter remains only for explicit fixture/compatibility callers. Previous/Next
cursor state is URL-backed, while raw/expert views identify the current bounded
page or entity rather than pretending to be a full historical snapshot.

The local RPF-35 proof measured 13,502 metadata rows: a 100-row page used at
most two SQL statements and 139,940 bytes, list artifact-body reads were zero,
and a verified detail read used one artifact body of 15,202 bytes. This is a
repository regression budget, not a Production SLA. RPF-35 does not add
artifact streaming, browser virtualization, retention/GC, broker, topology, or
release/deploy authority.

## Production topology and managed operations investigation

RPF-36 is an investigation-only boundary. It compares AWS ECS/Fargate + RDS +
S3, Render + Cloudflare R2, and Railway + Cloudflare R2 using dated provider
sources. The preferred candidate is a single-region AWS topology with
`ap-southeast-1` (Singapore) as a future region candidate. Region, latency,
data-residency, account quota, and cost remain authorization/preflight facts;
no provider account, paid resource, or cloud API operation was used by RPF-36,
and RPF-37 did not authorize one. Real Production Cloud deployment remains
Deferred.

The candidate flow is:

```text
Internet -> static Web/CDN -> read-only API edge -> stateless Control Plane
                                              -> managed PostgreSQL
                                              -> S3-compatible artifact store
private Durable Worker -> Control Plane HTTP/JSON -> scoped RPF-28 Simulation task
GitHub Actions -> canonical gate -> protected human Approval -> Release principal
```

The Web is read-only and fails closed when the API or verified artifact is
unavailable. The Control Plane is stateless; PostgreSQL and object storage are
canonical. The Worker is initially one private, outbound-only replica with
concurrency one. A fresh RPF-28 target/dependency/Toxiproxy environment must be
implemented as a scoped per-run task or a separately operated sandbox host;
the Agent and Worker never receive a Docker socket, database credential, or
Release principal.

The minimum Release boundary remains
`Release Decision ELIGIBLE -> human/product Approval -> protected Release
principal -> deployment -> target verification`. A candidate
`rpf-product-release-identity-v1` binds commit, source tree, application and
image/static digests, migration identity, build run, target environment,
deployment id, and timestamp. This identity is separate from Agent Version
Identity and is append-only. GitHub Actions OIDC is a candidate for short-lived
release identity, with repository/workflow/environment conditions; the
canonical gate never deploys by itself.

RPF-36 proposes RDS backup/PITR and an independent restore-to-new-instance
rehearsal, application-level S3 immutability, a seven-day orphan grace plus
dry-run inventory, additive expand/contract migrations, and ECS rolling
deployment with circuit-breaker/alarm rollback. These are candidate operations,
not Production SLAs. Initial sizing is directional from RPF-33: one small
Control Plane task, one Worker task at concurrency one, a small production-
eligible database tier, bounded connection pools, and explicit backlog/object/
log cost thresholds. `BROKER_REQUIRED=NOT_YET` remains unchanged.

The historical RPF-36 lifecycle gate was
`READY_FOR_PRODUCTION_IMPLEMENTATION = CONDITIONAL`: per-run Simulation
hosting, provider/account/region/budget preflight, independent restore, human
Approval/release-principal configuration, and Product Release Identity
read-back/rollback are still required. The full comparison, dated sources and
offline proof are in [`spikes/rpf-36/`](../spikes/rpf-36/README.md). The current
lifecycle is `Stabilization / Portfolio Maintenance`; RPF-37 is a repository
closure audit, and the next boundary is the low-risk, reversible RPF-38 cleanup
contract rather than Production implementation.

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
| Formal multi-service network faults | RPF-28 reviewed baseline/dependency/response-loss Runs, `multi-service-toxiproxy-v1`, and durable-worker focused result | `python spikes/rpf-28/probe.py --run`; `python spikes/rpf-28/verify-evidence.py .local/rpf-28/rpf28-formal-result.json` |
| Formal diagnostic observability | RPF-30 SDK instrumentation, three-mode durable probe, Collector trace file, and span/cardinality verifier | `python spikes/rpf-30/probe.py --run`; `python spikes/rpf-30/verify-evidence.py .local/rpf-30/local/rpf30-result.json` |
| Formal S3-compatible ArtifactStore | `S3ArtifactStore`, explicit backend wiring, SeaweedFS 4.47 proof, PostgreSQL canonical ingest, and HTTP/JSON Worker upload | `python spikes/rpf-32/probe.py --run`; `python spikes/rpf-32/verify-evidence.py --result <rpf32-result.json>` |
| Bounded Execution read model | RPF-34 summary list, opaque keyset cursors, bounded detail/timeline, query/payload budgets, and eligible-discovery compatibility proof | `python spikes/rpf-34/probe.py --run --output-dir .local/rpf-34/<run>`; `python spikes/rpf-34/verify-evidence.py <rpf34-result.json>` |
| Bounded canonical metadata read model | RPF-35 metadata cursor contract, registered-reference list, verified Local/S3 detail, route-scoped Web loaders, no-auto-crawl budget, and Large fixture proof | `python spikes/rpf-35/probe.py --run --output-dir .local/rpf-35/<run>`; `python spikes/rpf-35/verify-evidence.py <rpf35-result.json>` |
| Production topology and managed operations boundary | RPF-36 dated provider matrix, future candidate region/topology, managed persistence/secrets, Simulation-hosting boundary, Release Identity/Approval chain, restore/rollback/cost model, and RPF-37 Deferred/maintenance calibration | `python spikes/rpf-36/probe.py --run --output-dir .local/rpf-36/<run>`; `python spikes/rpf-36/verify-evidence.py <rpf36-result.json>`; `python spikes/rpf-37/audit.py --root . --output .local/rpf-37/audit.json` |

The detailed source identities, hosted runs, and historical compatibility facts are kept in [VERIFICATION_HISTORY.md](history/VERIFICATION_HISTORY.md), not repeated in the current snapshot.

## Production boundary

The current repository proves a controlled simulation, a formal fresh multi-service network fault Environment, local production-like persistence/recovery, an explicit PostgreSQL durable workflow, immutable evidence, a formal S3-compatible object-store adapter, hosted CI checks, and a Windows local Golden Demo lifecycle. RPF-36 adds a conditional managed-topology investigation, not a cloud deployment. The repository still does not prove or authorize Production HA, managed cloud operations, multi-host supervision, human Approval configuration, tenant/RBAC identity, or real destructive remediation.

The next architectural boundary is the reversible RPF-38 repository cleanup:
first reduce historical workflow fan-out and clarify governance/history
ownership, while preserving all formal contracts and reviewed evidence. The
Production Cloud boundary remains Deferred; RPF-36 does not authorize actual
Production deployment and does not introduce Kubernetes, a broker,
multiregion, full tenant/RBAC or automatic `ELIGIBLE` deployment. RPF-35 still
does not prove Production capacity, artifact streaming, virtualization,
retention/GC or managed durability; the S3 adapter remains a compatibility
boundary rather than a durability, HA or release-authority claim.
