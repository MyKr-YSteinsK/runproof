# RunProof

[English](README.md) | [简体中文](README.zh-CN.md)

RunProof is an **Agent Reliability & Release Engineering Platform**. It turns Agent behavior, state transitions, failures, and release evidence into inspectable engineering assets instead of treating an evaluation score as the whole product.

## What it is

RunProof connects a Candidate Agent Version to a stateful evaluation, the observed trajectory and environment state, deterministic evidence, failure investigation, regression history, statistical reliability, and a decision-only Quality Gate.

It is more than a generic evaluation runner:

- It models two explicit reference Agents: `Production Change` and `Incident Remediation`.
- It keeps Agent behavior separate from platform/environment failures.
- It treats `UNKNOWN_OUTCOME` and `RECONCILE_REQUIRED` as first-class safety states.
- It preserves raw evidence and canonical identity while making derived investigation and statistical conclusions traceable.
- It never treats `ELIGIBLE` as deploy or release authorization.

## Why it exists

An Agent can return a plausible answer while leaving the environment in the wrong state, misdiagnosing an external dependency, or losing the response after a side effect. RunProof makes those cases reproducible and reviewable: the human can follow the evidence from the Candidate through the Failure, Regression, Gate, and final decision boundary.

## The core loop

```text
Candidate Agent Version
        ↓
Stateful Evaluation
        ↓
Run / Trajectory / State Diff
        ↓
Failure Investigation
        ↓
Failure → Regression
        ↓
Failure Intelligence
        ↓
Statistical Reliability
        ↓
Quality Policy
        ↓
Release Decision (decision-only)
```

`ELIGIBLE` means that the recorded policy evaluation found no blocking condition in its evidence scope. It does not publish a product, deploy a service, or grant authority to an Agent, worker, or runtime.

## Golden Demo

The local Golden Demo is the shortest way to inspect the product surface. It uses reviewed evidence, a formal Control Plane, PostgreSQL canonical metadata, an immutable local artifact store, and a durable worker. It does not require a Provider credential or a cloud account and does not call a real Production system.

```powershell
powershell -ExecutionPolicy Bypass -File demo/start-demo.ps1
```

Open <http://127.0.0.1:4173/overview>. The five-to-ten-minute walkthrough is documented in [docs/DEMO.md](docs/DEMO.md) and [docs/DEMO.zh-CN.md](docs/DEMO.zh-CN.md).

## Evidence-backed boundary

### Proven in the current scope

- A Desktop Web Control Plane for read-only investigation.
- Java/Spring Control Plane and PostgreSQL canonical metadata with an HTTP/JSON boundary.
- Immutable, verified artifact references and append-only decision history.
- Python Agent/Evaluation Runtime and a PostgreSQL poll/claim durable worker.
- Controlled stateful simulation, failure reproduction, Regression promotion, Failure Intelligence, and statistical trial semantics.
- A hosted GitHub Actions Release Gate that records canonical evidence and a decision read-back.
- A Windows local Golden Demo lifecycle with explicit child ownership and fail-closed cleanup checks.

### Not claimed or authorized

The repository does not claim Production HA, managed-cloud deployment, S3 durability, a human Approval service, OAuth/OIDC/SSO, multi-tenant RBAC, broker/scheduler/autoscaling, real destructive Production remediation, or long-term live Provider probability. No current Agent, worker, or `ELIGIBLE` Decision can execute release or deploy.

## Public documentation

| Purpose | English | 简体中文 |
|---|---|---|
| Architecture and boundaries | [ARCHITECTURE.md](docs/ARCHITECTURE.md) | [ARCHITECTURE.zh-CN.md](docs/ARCHITECTURE.zh-CN.md) |
| Reliability semantics | [RELIABILITY_MODEL.md](docs/RELIABILITY_MODEL.md) | [RELIABILITY_MODEL.zh-CN.md](docs/RELIABILITY_MODEL.zh-CN.md) |
| Local Golden Demo | [DEMO.md](docs/DEMO.md) | [DEMO.zh-CN.md](docs/DEMO.zh-CN.md) |
| Technical glossary | [GLOSSARY.md](docs/GLOSSARY.md) | [GLOSSARY.zh-CN.md](docs/GLOSSARY.zh-CN.md) |
| Verification history | [VERIFICATION_HISTORY.md](docs/history/VERIFICATION_HISTORY.md) | [VERIFICATION_HISTORY.zh-CN.md](docs/history/VERIFICATION_HISTORY.zh-CN.md) |
| Capability history | [CAPABILITY_HISTORY.md](docs/history/CAPABILITY_HISTORY.md) | [CAPABILITY_HISTORY.zh-CN.md](docs/history/CAPABILITY_HISTORY.zh-CN.md) |

The canonical governance files are not duplicated into translated copies: [AGENTS.md](AGENTS.md), [PROJECT_BRIEF.md](docs/project/PROJECT_BRIEF.md), [DECISIONS.md](docs/project/DECISIONS.md), and [CURRENT_STATE.md](docs/project/CURRENT_STATE.md). `CURRENT_STATE.md` is the current snapshot; historical verification belongs in `docs/history/`.

## Verification entry points

The lightweight public-document contract is checked with:

```powershell
python ci/verify-public-docs.py
```

The main repository checks remain:

```powershell
npm test
npm run typecheck
npm run build
python -m unittest discover -s runtime/tests -p 'test_*.py' -v
python runtime/verify-reviewed-artifacts.py
mvn -q test package -f control-plane/pom.xml
python demo/verify-golden-demo.py --root . --json
python ci/run_release_gate.py
```

The last command creates a fresh local canonical gate when its Docker/Java/Python prerequisites are available. It does not authorize or execute a release.

## Repository map

- [control-plane/README.md](control-plane/README.md): formal Java/Spring Control Plane and API boundary.
- [runtime/README.md](runtime/README.md): Python runtime, evidence, evaluation, and worker entry points.
- [web/README.md](web/README.md): Web read model and presentation implementation.
- [demo/](demo/): Golden Demo profile, seed, lifecycle, and verifier.
- [spikes/](spikes/): disposable investigations and historical contract probes; they are not production claims.
- [docs/project/](docs/project/): canonical product brief, decisions, and current state.

The current lifecycle is `Stabilization`. Product versioning, deployment, and release status are reported only by the canonical project state and verified delivery evidence.
