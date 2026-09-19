# RPF Execution Index

[Current State](../project/CURRENT_STATE.md) | [Verification History](VERIFICATION_HISTORY.md)

这是 RPF-00 至 RPF-38 的执行导航，不是第二套产品合同或证据真相源：

- 稳定产品与 UX 合同以 [`PROJECT_BRIEF.md`](../project/PROJECT_BRIEF.md) 为准；
- 长期决定以 [`DECISIONS.md`](../project/DECISIONS.md) 为准；
- 当前能力、限制与交付以 [`CURRENT_STATE.md`](../project/CURRENT_STATE.md) 为准；
- 具体命令、参数、fixture 和 verifier 仍以对应 Spike/模块 README 与脚本为准。

## Lifecycle

`ARCHIVE` 只表示历史候选或被后续正式边界替代，绝不表示删除。所有 `spikes/rpf-*` 原路径、source identity、reviewed artifact 与历史 hosted link 保持不变。

| Lifecycle | Plans |
|---|---|
| ARCHIVE / historical candidate | RPF-01, RPF-02, RPF-09, RPF-10, RPF-13, RPF-15, RPF-27, RPF-29, RPF-31 |
| KEEP / formal or active regression | RPF-16, RPF-17, RPF-18, RPF-28, RPF-30, RPF-32, RPF-34, RPF-35 |
| KEEP / manual-heavyweight | RPF-33 |
| KEEP / deferred future topology evidence | RPF-36 |
| KEEP / current closure audit | RPF-37 |

RPF-28/30/32/34/35 与 RPF-33 仍是正式或风险扩展验证边界，但在普通 push/PR 上不自动运行；它们保留 manual-only 入口。RPF-12 canonical Release Gate 是唯一 always-on workflow。

## Execution routing

“Command source” 指向维护者应读取的命令入口；本索引不复制逐 Plan 命令百科，避免形成漂移的第二份命令真相。

| Plan | Role / status | Command source | Verifier / evidence source | Superseding or boundary note |
|---|---|---|---|---|
| RPF-00 | Bootstrap / governance baseline | `docs/project/PROJECT_BRIEF.md`, `docs/project/DECISIONS.md` | Project-State files | Stable product boundary |
| RPF-01 | ARCHIVE / Agent contract candidate | `spikes/rpf-01/README.md` | `spikes/rpf-01/probe.test.mjs`, `spikes/rpf-01/verify-evidence.mjs` | DeepSeek contract input for later Runtime |
| RPF-02 | ARCHIVE / Environment prototype | `spikes/rpf-02/README.md` | `spikes/rpf-02/probe.test.mjs`, Docker probe and verifier | Prototype Docker evidence; formal Runtime supersedes product boundary |
| RPF-03 | KEEP / first Runtime vertical slice | `runtime/README.md` | `runtime/tests/`, `runtime/verify-reviewed-artifacts.py` | Runtime contract foundation |
| RPF-04 | KEEP / Run Evidence and Web corpus | `runtime/README.md`, `web/README.md` | Web tests and reviewed RPF-04 artifacts | Read-only presentation boundary |
| RPF-05 | KEEP / Failure Case evidence | `runtime/README.md` | Runtime tests and reviewed Failure Case artifacts | RPF-06 promotes selected failures |
| RPF-06 | KEEP / Regression and focused rerun | `runtime/README.md` | Runtime verifier and reviewed Regression corpus | Feeds Evaluation |
| RPF-07 | KEEP / Evaluation Suite and comparison | `runtime/README.md` | Runtime verifier and reviewed Evaluation corpus | Feeds Quality Policy |
| RPF-08 | KEEP / Quality Gate and decision | `runtime/README.md` | Runtime verifier and reviewed Decision corpus | Decision-only; no release authority |
| RPF-09 | ARCHIVE / H2 Control Plane candidate | `spikes/rpf-09/README.md` | `spikes/rpf-09/probe.py` | RPF-11 formal Control Plane supersedes candidate |
| RPF-10 | ARCHIVE / PostgreSQL and authority candidate | `spikes/rpf-10/README.md` | `spikes/rpf-10/probe.py`, `spikes/rpf-10/verify-evidence.py` | RPF-11/RPF-14 formal boundaries supersede candidate |
| RPF-11 | KEEP / formal Control Plane | `control-plane/README.md`, `control-plane/probe.py` | `control-plane/verify-evidence.py` and Maven tests | Canonical PostgreSQL metadata/API boundary |
| RPF-12 | KEEP / canonical Release Gate | `.github/workflows/release-gate.yml`, `ci/run_release_gate.py` | Hosted canonical workflow artifact and Job Summary | Only always-on CI; never deploy/release |
| RPF-13 | ARCHIVE / durable transport candidate | `spikes/rpf-13/README.md` | `spikes/rpf-13/probe.py`, `spikes/rpf-13/verify-evidence.py` | RPF-14 formal durable execution supersedes candidate |
| RPF-14 | KEEP / formal durable execution | `control-plane/README.md`, `control-plane/probe.py` | `control-plane/verify-evidence.py`, Runtime durable worker | No broker/scheduler/Production HA |
| RPF-15 | ARCHIVE / production-readiness investigation | `spikes/rpf-15/README.md` | `spikes/rpf-15/probe.py`, `spikes/rpf-15/verify-evidence.py` | RPF-36 updates topology investigation boundary |
| RPF-16 | KEEP / second Agent contract | `spikes/rpf-16/README.md` | `spikes/rpf-16/probe.py`, `spikes/rpf-16/verify-evidence.py` | Cross-Agent corpus and Golden Demo refs |
| RPF-17 | KEEP / deterministic Failure Intelligence | `spikes/rpf-17/README.md` | `spikes/rpf-17/probe.py`, `spikes/rpf-17/verify-evidence.py` | No ML/LLM/auto-promotion |
| RPF-18 | KEEP / Statistical Evaluation and flaky gate | `spikes/rpf-18/README.md` | `spikes/rpf-18/probe.py`, `spikes/rpf-18/verify-evidence.py` | Decision-only statistical boundary |
| RPF-19 | KEEP / Golden Demo | `demo/start-demo.ps1`, `demo/seed_demo.py` | `demo/verify-golden-demo.py`, lifecycle verifier | Local API-backed product proof |
| RPF-20 | KEEP / architecture and product-health audit | `docs/ARCHITECTURE.md`, `docs/project/CURRENT_STATE.md` | Project-State and repository checks | Audit facts belong in history/current snapshot |
| RPF-21 | KEEP / statistical and release-trust hardening | `runtime/README.md`, `ci/run_release_gate.py` | Runtime verifier and canonical gate | Preserves decision trust chain |
| RPF-22 | KEEP / durable discovery and artifact integrity | `control-plane/README.md`, `control-plane/probe.py` | Control Plane verifier and Web checks | Bounded discovery; no broker/GC |
| RPF-23 | KEEP / Windows Demo lifecycle boundary | `demo/README.md`, `demo/verify-lifecycle.ps1` | Lifecycle contract and lifecycle mode | Local least privilege; not Production isolation |
| RPF-24 | KEEP / Web canonical truth and module boundary | `web/README.md` | Web tests, typecheck, build | Presentation and loader boundary |
| RPF-25 | KEEP / bilingual Control Plane surface | `web/README.md` | Web tests, typecheck, build | Locale changes presentation only |
| RPF-26 | KEEP / public documentation contract | `ci/verify-public-docs.py` and paired public docs | `python ci/verify-public-docs.py` | English/简体中文 public-doc pairing |
| RPF-27 | ARCHIVE / network-fault candidate | `spikes/rpf-27/README.md` | `spikes/rpf-27/probe.py`, `spikes/rpf-27/verify-evidence.py` | RPF-28 formal Environment supersedes candidate |
| RPF-28 | KEEP / formal multi-service Environment | `spikes/rpf-28/README.md` | `spikes/rpf-28/probe.py`, `spikes/rpf-28/verify-evidence.py` | Manual-only risk-expanded workflow |
| RPF-29 | ARCHIVE / OTel wire candidate | `spikes/rpf-29/README.md` | `spikes/rpf-29/probe.py`, `spikes/rpf-29/verify-evidence.py` | RPF-30 formal optional OTel boundary supersedes candidate |
| RPF-30 | KEEP / formal optional OpenTelemetry | `spikes/rpf-30/README.md` | `spikes/rpf-30/probe.py`, `spikes/rpf-30/verify-evidence.py` | Manual-only risk-expanded workflow |
| RPF-31 | ARCHIVE / S3 compatibility candidate | `spikes/rpf-31/README.md` | `spikes/rpf-31/probe.py`, `spikes/rpf-31/verify-evidence.py` | RPF-32 formal S3ArtifactStore supersedes candidate |
| RPF-32 | KEEP / formal S3-compatible ArtifactStore | `spikes/rpf-32/README.md` | `spikes/rpf-32/probe.py`, `spikes/rpf-32/verify-evidence.py` | Manual-only risk-expanded workflow; Local remains default |
| RPF-33 | KEEP / manual-heavyweight capacity evidence | `spikes/rpf-33/README.md` | `spikes/rpf-33/probe.py`, `spikes/rpf-33/verify-evidence.py` | Manual checkpoint; diagnostic, not Production SLA |
| RPF-34 | KEEP / formal bounded Execution read model | `spikes/rpf-34/README.md` | `spikes/rpf-34/probe.py`, `spikes/rpf-34/verify-evidence.py` | Manual-only risk-expanded workflow |
| RPF-35 | KEEP / formal bounded Canonical read model | `spikes/rpf-35/README.md` | `spikes/rpf-35/probe.py`, `spikes/rpf-35/verify-evidence.py` | Manual-only risk-expanded workflow |
| RPF-36 | KEEP / deferred future topology evidence | `spikes/rpf-36/README.md` | `spikes/rpf-36/probe.py`, `spikes/rpf-36/verify-evidence.py` | Production Cloud remains Deferred; manual-only |
| RPF-37 | KEEP / current closure audit | `spikes/rpf-37/README.md`, `spikes/rpf-37/audit.py` | `spikes/rpf-37/RESULT.md`, ignored audit JSON | Established the RPF-38 low-risk cleanup contract |
| RPF-38 | KEEP / portfolio maintenance cleanup | This Plan and repository maintenance files | Workflow matrix, core regression, audit before/after, canonical gate | No product behavior, cloud operation, release or deploy |

## Workflow routing after RPF-38

- Always-on: `.github/workflows/release-gate.yml` on `push(main)`, `pull_request(main)`, and `workflow_dispatch`.
- Manual historical candidates: RPF-27, RPF-29, RPF-31, RPF-36.
- Manual heavyweight/checkpoint: RPF-28, RPF-30, RPF-32, RPF-33, RPF-34, RPF-35.
- No workflow file, Spike source, reviewed evidence, or legacy compatibility path was deleted or moved.
