# RPF-37 — 全仓收束、规范化与瘦身审计结果

## 1. 结论与边界

- `Status: Complete`
- `Lifecycle: Stabilization / Feature Freeze / Portfolio Maintenance`
- `Plan: RPF-37 Investigation / Checkpoint Review`
- `starting HEAD: d2945e00e16254563364303d73a5e8f3f8451725`
- `resulting HEAD: 882997b4e25e3a66231484d6eaa69c8393033c87`
- `audit-only: YES`
- `product behavior changed: NO`
- `release/deploy: NOT EXECUTED`
- 用户未跟踪的 `docs/reviews/` 未读取其内容、未修改、未删除、未暂存。

本轮形成清理合同和可复核盘点，不执行大规模删除、移动、格式化、重构、
reviewed artifact refresh、Git history rewrite、云操作或新产品功能实现。
`spikes/rpf-37/audit.py` 只使用 Python 标准库读取 Git tree；输出到
`.local/rpf-37/`，不改变仓库内容。

## 2. Product completion

`V1_FEATURE_COMPLETE = YES`

这里的 YES 只针对已声明的 v1 reliability/control-plane 产品边界：两个显式
Agent、Controlled Stateful/Multi-service Environment、Failure→Regression、
Failure Intelligence、Statistical Reliability、Quality Policy/Release Gate、
durable Job/Attempt/Operation、PostgreSQL canonical truth、Local/S3
ArtifactStore、diagnostic OTel、bounded Execution/Canonical read model、双语
只读 Control Plane、Golden Demo 和 hosted canonical gate 均已有正式代码与分层证据。

以下不是本轮遗漏的 v1 功能，而是明确的 deferred/unauthorized 边界：真实
Production Cloud deployment、Production HA、多主机 supervisor、OAuth/OIDC/SSO、
tenant/RBAC、broker、scheduler/autoscaling、真实 destructive remediation、
artifact streaming、GC、Production capacity/SLA、real-device verification 和
自动 `ELIGIBLE` deploy。它们不能因为仓库收束而被默认为已实现。

## 3. Repository inventory

审计入口：

```powershell
python spikes/rpf-37/audit.py --root . --output .local/rpf-37/audit.json
```

在 RPF-37 起始 HEAD 上的 Git tree 基线为：

| Area | Tracked files | Bytes | 判断 |
|---|---:|---:|---|
| `(root)` | 10 | 125,502 | KEEP；配置、入口与锁文件 |
| `.github` | 11 | 25,620 | workflow surface，后续按触发策略收束 |
| `ci` | 2 | 52,428 | canonical Release Gate，KEEP/谨慎抽取 |
| `control-plane` | 28 | 433,101 | 正式 Java/API/probe，KEEP；结构审计候选 |
| `demo` | 8 | 111,104 | Golden Demo 与生命周期，KEEP |
| `docs` | 15 | 209,982 | public/governance/history，KEEP；current/history 分层可压缩 |
| `runtime` | 136 | 2,196,574 | 正式 runtime + reviewed corpus，KEEP；不能按体积删除 |
| `spikes` | 116 | 1,401,390 | 19 个 Investigation/probe，首要治理对象 |
| `web` | 50 | 672,587 | 正式只读 Web，KEEP；模块化候选 |
| **合计** | **376** | **5,228,288** | 与 Plan 基线一致 |

本轮新增的 RPF-37 入口和报告属于审计交付资产；它们不会被误算为历史基线的
产品能力或 reviewed evidence。交付后的 tree 为 `379 tracked files / 5,273,530
bytes`、`20` 个 Spike、`11` 个 workflow；`.local/rpf-37/` 仍被忽略，用户
`docs/reviews/` 仍未跟踪。

### Top large files

大文件是调查信号，不是删除证据。起始 tree 的主要大文件为：

| File | Bytes | 结论 |
|---|---:|---|
| `web/src/App.tsx` | 184,227 | REFACTOR candidate；先做 route/feature call graph |
| `web/src/styles.css` | 116,017 | REFACTOR candidate；先做 selector ownership |
| `control-plane/src/main/java/com/runproof/controlplane/DurableExecutionController.java` | 98,142 | REFACTOR candidate；command/read/DTO 边界审计 |
| `control-plane/probe.py` | 97,127 | KEEP probe；可在后续拆 transport/test data，但不能删 contract |
| `runtime/runproof_runtime/statistical.py` | 89,352 | KEEP semantics；safe extract candidate |
| `web/src/data/artifacts.ts` | 77,131 | REFACTOR candidate；artifact/read-model ownership |
| `spikes/rpf-29/probe.py` | 75,159 | ARCHIVE candidate；历史 OTel feasibility evidence |
| `runtime/runproof_runtime/evaluation.py` | 73,288 | KEEP semantics；safe extract candidate |
| `control-plane/src/main/java/com/runproof/controlplane/CanonicalMetadataService.java` | 71,909 | REFACTOR candidate；canonical validation/read model |
| `spikes/rpf-15/probe.py` | 71,777 | ARCHIVE candidate；production-like investigation |
| `package-lock.json` | 71,600 | KEEP；dependency lock truth |
| `web/src/i18n/messages.ts` | 65,144 | KEEP；产品级双语资源 |
| `spikes/rpf-33/probe.py` | 64,058 | KEEP manual-heavyweight capacity harness |
| `spikes/rpf-13/control-plane/src/main/java/com/runproof/rpf13/DurableExecutionController.java` | 63,944 | ARCHIVE candidate；历史 durable candidate |
| `runtime/reviewed-rpf18-statistical-evaluation-baseline.json` | 61,079 | KEEP；immutable reviewed corpus |

## 4. Governance / Project State findings

- `PROJECT_BRIEF.md` 仍是稳定产品/UX 意图，未混入本轮实现流水，KEEP。
- `DECISIONS.md` 的 durable authority、canonical PostgreSQL、evidence identity、
  Release authority、`ELIGIBLE != Released`、ArtifactStore 和 reliability 语义
  不能删除。历史或 superseded decision 只能在确认引用后压缩，RPF-37 不重写。
- `AGENTS.md` 同时承载当前执行规则和 RPF-00～36 的命令/证据矩阵；这对恢复任务
  有价值，但已开始承担历史说明书职责。RPF-38 可把“当前必须遵守的规则”和
  “按 Plan 的历史命令索引”分层；本轮只新增 RPF-37 审计命令，不大改治理文件。
- `CURRENT_STATE.md` 的当前快照、能力、限制是正确方向，但 Verification facts
  仍然较长，已经接近第二份历史账本。RPF-38 应只保留最新能力/限制/交付事实和
  历史链接，把逐 Plan 的 hosted digest/run 继续放在 `docs/history/`。
- `docs/history/VERIFICATION_HISTORY.*` 是历史证据账本，允许继续保留 RPF-36
  当时的 conditional 结论；历史事实不应被改写成当前生产承诺。
- `docs/reviews/` 是用户已有未跟踪材料，严格保护。

### 当前云 Production 状态校准

RPF-36 的核心调查结论保留，但产品已明确真实上云暂缓。因此当前事实改为：

- `Lifecycle = Stabilization / Portfolio Maintenance`；
- AWS `ap-southeast-1` 只是 future candidate，不是 provider Decision；
- 不创建云资源、不运行 provider credential、不执行 Production deploy/release；
- `READY_FOR_PRODUCTION_IMPLEMENTATION=CONDITIONAL` 只保留为 RPF-36 历史 gate，
  不作为当前“下一步立即上云”的授权；
- 下一边界是 RPF-38 的低风险 repository cleanup，而不是 Production implementation。

未新增 Production provider Decision。

## 5. Spike lifecycle classification

`ARCHIVE` 表示未来可按保留原始内容、稳定链接和复现说明的方式归档；不表示本轮
移出 Git、压缩或删除。`KEEP (manual-heavyweight)` 表示不进入每次 fast path，
但仍是长期验证/诊断入口。

| Spike | Current role | Classification | Preserve | Candidate removal / next action | Risk |
|---|---|---|---|---|---|
| RPF-01 | DeepSeek Agent Contract 原始 disposable probe | ARCHIVE | README、probe、脱敏 reviewed evidence、source identity | 将来仅归档执行入口；不删历史 contract | High |
| RPF-02 | Host/Docker isolation/recovery 原始 proof | ARCHIVE | host/Docker evidence 与 cleanup 语义 | 与正式 DockerEnvironment 关系写入索引后再决定 | High |
| RPF-09 | H2 Control Plane precursor | ARCHIVE | migration/idempotency/rollback 结论 | 可保留结果摘要与源码；不删本轮历史 probe | Medium |
| RPF-10 | PostgreSQL/auth Control Plane precursor | ARCHIVE | real PostgreSQL/auth boundary 结论 | 先确认无外部复现消费者，再归档执行 workflow/source | High |
| RPF-13 | durable transport candidate | ARCHIVE | claim/lease/fencing/UNKNOWN_OUTCOME 候选证据 | 正式 RPF-14/22 已接管执行路径，历史源仍保留 | High |
| RPF-15 | production-like Candidate A investigation | ARCHIVE | 本机 replacement/restore/rollback/secret 边界 | 与 RPF-36 future recovery 结论交叉链接 | Medium |
| RPF-16 | 第二真实 Agent contract 与 corpus | KEEP | probe、reviewed corpus、tests、Web/CI 引用 | 无删除候选 | High |
| RPF-17 | Failure Intelligence / bisect | KEEP | deterministic attribution、signature v1、negative controls | 无删除候选 | High |
| RPF-18 | Statistical Evaluation / flaky gate | KEEP | policy/evaluation/comparison/decision corpus | 无删除候选 | High |
| RPF-27 | 多服务 network candidate comparison | ARCHIVE | Toxiproxy/custom shim/Envoy 对比与 unique negative evidence | RPF-28 接管正式边界；workflow 可在 RPF-38 改为手动 | High |
| RPF-28 | formal multi-service Toxiproxy Environment | KEEP | formal probe、8 negative controls、reviewed Runs、durable path | 无删除候选；风险扩展时运行 | High |
| RPF-29 | disposable OTel feasibility candidate | ARCHIVE | candidate/provider portability 与 hosted evidence | RPF-30 接管正式 SDK；workflow 改为 manual/历史 | Medium |
| RPF-30 | formal Java/Python OTel boundary | KEEP | SDK、Collector modes、propagation/reclaim/verifier | 无删除候选；影响 OTel 时回归 | High |
| RPF-31 | S3 provider comparison | ARCHIVE | SeaweedFS/RustFS compatibility、credential/negative evidence | RPF-32 接管正式 adapter；workflow 改为 manual/历史 | High |
| RPF-32 | formal provider-neutral S3ArtifactStore | KEEP | formal adapter、PostgreSQL canonical、worker/read-back、tests | 无删除候选；影响 S3 时回归 | High |
| RPF-33 | capacity/Large-Trace measurement harness | KEEP (manual-heavyweight) | full fixture generator、SQL/EXPLAIN/resource/cleanup evidence | 不放入 fast path；只有容量 harness 失效时再拆 | High |
| RPF-34 | bounded Execution read model | KEEP | keyset cursor、timeline、eligible discovery 与 regression | 作为长期 read-model regression，不只是历史 Spike | High |
| RPF-35 | bounded Canonical metadata read model | KEEP | metadata cursor、registered/verified 分层、route loaders | 作为长期 canonical read regression | High |
| RPF-36 | deferred managed operations/topology investigation | KEEP | dated sources、AWS candidate、restore/rollback/Release Identity blockers | 云恢复时继续调查；当前不扩展为 deploy | High |

特别结论：RPF-27/29/31 的 candidate 实现不是 formal replacement 的重复副本，
而是 provider/feasibility 取证；不能因为 RPF-28/30/32 已 formalize 就直接删除。RPF-34/35
应长期保留为 read contract regression。RPF-33 保留完整代码，但只在 checkpoint/release
路径使用。

## 6. CI / GitHub Actions classification

当前共有 11 个 workflow；均使用已存在的 `actions/checkout@v4`、
`actions/setup-java@v4`、`actions/setup-python@v5`、`actions/setup-node@v4`、
`actions/upload-artifact@v4` 的组合。GitHub hosted annotations 已报告既有 Node.js 20、
setup-java v4 与 `ubuntu-latest` migration warning；本轮不做 major action/runtime upgrade。

| Workflow | Current trigger role | Classification | Current permissions/artifact | RPF-38 direction |
|---|---|---|---|---|
| `release-gate.yml` | main push / PR / manual canonical gate | Always-on | `contents: read`, `actions: write`; redacted artifact + Summary，14 days | KEEP；唯一 canonical fast/release evidence入口 |
| `rpf-27-network-spike.yml` | main push / manual candidate | Historical-only | `contents: read`, `actions: write`; 14 days | 保留 source/RESULT，workflow 改 manual 或归档 |
| `rpf-28-multi-service.yml` | selected runtime/spike push/PR/manual | Manual heavyweight | `contents: read`, `actions: write`; 14 days | formal risk-expanded regression，避免每次 docs push |
| `rpf-29-otel-spike.yml` | spike push/PR/manual | Historical-only | `contents: read`; missing artifact warn，7 days | workflow 改 manual/历史；保留 candidate evidence |
| `rpf-30-otel.yml` | control/runtime/OTel push/PR/manual | Manual heavyweight | `contents: read`; 14 days | formal OTel regression，按影响域运行 |
| `rpf-31-s3-spike.yml` | spike/AGENTS push/PR/manual | Historical-only | `contents: read`; 14 days | workflow 改 manual/历史；保留 provider comparison |
| `rpf-32-s3-artifact-store.yml` | control/runtime/S3 push/PR/manual | Manual heavyweight | `contents: read`, `actions: write`; 14 days | formal S3 regression，按影响域运行 |
| `rpf-33-capacity-spike.yml` | control/runtime/capacity push/PR/manual | Manual heavyweight | `contents: read`, `actions: write`; 14 days | checkpoint/release only，不进入 fast path |
| `rpf-34-read-model.yml` | control/runtime/Web read-model push/PR/manual | Manual heavyweight | `contents: read`; 14 days | bounded Execution regression，按 read-path 运行 |
| `rpf-35-canonical-read-model.yml` | control/client/Web/AGENTS push/PR/manual | Manual heavyweight | `contents: read`; 14 days | bounded Canonical regression，按 read-path 运行 |
| `rpf-36-production-topology.yml` | spike/AGENTS push/PR/manual | Historical-only | `contents: read`; 14 days | 保留调查 source/RESULT，workflow 改 manual/历史 |

当前触发扇出是维护成本的 concrete finding：`AGENTS.md` 一次改动会命中 7 个
workflow；`control-plane/**` 会命中 canonical gate、RPF-30、32、33、34、35；
`runtime/**` 会命中 canonical gate、RPF-30、33、34。RPF-27 只有 push 没有 PR，
也是当前矩阵不一致点。

### Proposed maintenance modes

- **Fast path**：canonical `release-gate.yml` + repository contract checks、runtime
  unit/reviewed verifier、Web tests/typecheck/build、Maven package、public docs；不因
  历史 candidate workflow 自动启动。
- **Risk-expanded path**：只在对应 domain 或 focused patch 运行 RPF-28、30、32、34、35。
- **Checkpoint/release path**：手动运行 RPF-33 full/Medium，必要时再跑其他 heavyweight。
- **Historical path**：RPF-27/29/31/36 保留可复现资料，hosted workflow 不再成为普通
  push 的固定负担，除非下一计划明确需要。

预计简化不是“少证明”：对 `AGENTS.md` 这种治理变更，自动 job 数可从 7 降为 1；
对纯历史 Spike 变更，可从对应的自动 hosted job 降为手动 0 个。实际分钟数不在本轮
虚构，因为各 job 的 Docker image pull/cache 与 hosted queue 时间未做同一 SHA 基准测量。

## 7. Verification matrix / 去重结论

| Contract | Authoritative verifier | Supporting / historical | Classification |
|---|---|---|---|
| Runtime Agent/evidence semantics | `python -m unittest discover -s runtime/tests -p 'test_*.py' -v` | reviewed artifact verifier | Authoritative + supporting |
| Reviewed Run corpus/source identity | `python runtime/verify-reviewed-artifacts.py` | RPF-04～08/16～18 file-specific verifiers | Authoritative; filenames are intentionally explicit |
| PostgreSQL canonical Control Plane | `mvn -q test package -f control-plane/pom.xml` + `control-plane/probe.py`/verifier | canonical gate | Authoritative formal + hosted supporting |
| Durable execution/job transport | formal Control Plane tests/probe and worker contract | RPF-13 candidate | Formal authoritative; RPF-13 historical |
| Network fault/reconcile | RPF-28 probe/verifier and `test_rpf28_runtime.py` | RPF-27 | Formal authoritative; RPF-27 historical |
| OpenTelemetry | RPF-30 probe/verifier + runtime/Java tests | RPF-29 | Formal authoritative; RPF-29 historical |
| S3 ArtifactStore | RPF-32 probe/verifier + Java S3 tests | RPF-31 | Formal authoritative; RPF-31 historical |
| Bounded Execution read | RPF-34 probe/verifier + Web/API tests | RPF-33 measurements | Formal read-path regression |
| Bounded Canonical read | RPF-35 probe/verifier + Web/API tests | RPF-33 measurements | Formal read-path regression |
| Web presentation/read-only boundary | `npm test`, `npm run typecheck`, `npm run build` | desktop/in-app observation where recorded | Authoritative for static/client contract |
| Golden Demo | `python demo/verify-golden-demo.py --root . --json` + lifecycle contracts | hosted gate seed/read-back | Authoritative local entry path |
| Public documentation | `python ci/verify-public-docs.py` | human review | Authoritative lightweight contract |
| Release decision authority | `.github/workflows/release-gate.yml` + `ci/run_release_gate.py` | local gate/result verifier | Canonical hosted authority; never deploys |

没有发现 byte-for-byte duplicate 的 tracked JSON：审计共检查 98 个 reviewed-named
JSON，`duplicate_hash_groups=0`。多层 verifier 不是等价重复：它们分别验证源码
合同、固定证据、跨进程/hosted transport 和 Web presentation。唯一 negative control、
`UNKNOWN_OUTCOME` reconcile、fresh-per-run、operation/lease/fencing、S3 immutable
write、Release authority 均不能为缩短 CI 而删除。

## 8. Probe / helper infrastructure

- `control-plane/probe.py`、RPF-28/30/32/33/34/35 probe 都重复 PostgreSQL/Docker
  readiness、HTTP JSON、temporary credential、cleanup、source identity 的形状；
  但 fault activation、artifact backend、large-fixture、OTel failure isolation 和
  read budget 语义不同。当前不建立万能测试框架。
- `ci/run_release_gate.py` 是 canonical hosted orchestration，拥有独立 principal
  authority checks、Decision read-back 和 redaction；不应与 disposable probe 合并。
- `runtime/verify-reviewed-artifacts.py` 的显式 reviewed file list 是可审计的保护，
  不是普通重复代码。未来可用版本化 manifest 改善 discoverability，但必须保留
  source/hash/schema checks 和 immutable writer。
- RPF-33 的 Windows/non-Windows RSS helper 是平台差异修复，不能因为看起来像通用
  process helper 就抽走；RPF-36 的来源/拓扑验证也不应套进执行 probe。
- 安全的 RPF-38 抽取候选是小型 `ci/lib`/`testsupport` 中的明确、无 authority 的
  readiness/JSON helper；必须逐个验证 cleanup、环境隔离和错误分类，不做“万能 harness”。

## 9. Runtime / Control Plane / Web findings

### Runtime

- `statistical.py`、`evaluation.py`、`quality.py`、`failure_intelligence.py`、
  `incident.py`、`multi_service_environment.py` 均被 tests、reviewed corpus、formal
  probe 或 Web 使用，当前没有可证明的 dead module。
- `LEGACY_RPF18_SOURCE_SHA256`、旧 `failure_signature()` 语义和 compatibility branch
  是保护性兼容路径，不是可删除 dead code。它们直接支撑历史 reviewed identity。
- `REFACTOR` 只记录为未来 safe-extract candidate；本轮不重写 serialization、failure
  hierarchy、statistical denominator 或 Agent authority。

### Control Plane

- `DurableExecutionController.java`、`CanonicalMetadataService.java` 和
  `control-plane/probe.py` 大且职责密集，存在 command/read model/DTO/validation
  交织的维护成本，但 Maven package 与既有 contract 通过，未证明有 unused endpoint。
- `S3ArtifactStore`、`LocalFileArtifactStore`、OTel、PostgreSQL schema 和 auth token
  boundary 均有明确配置/测试使用；不能为了抽象而破坏 local default、S3 fail-closed
  或 Agent/worker/decision scope。
- `REFACTOR` candidate：先为 read/command 与 validation 建立 call-site map，再按小步
  提取；不得在 RPF-38 与历史 Spike 删除混成一个提交。

### Web

- `App.tsx`、`styles.css`、`data/artifacts.ts` 和 `i18n/messages.ts` 是真实大文件，
  但 route-scoped loaders、canonical selectors、双语/legacyCopy compatibility 和
  Golden Demo refs 仍在使用。
- `npm test` 11/11 files、43/43 tests，`npm run typecheck` 和 `npm run build` 通过。
  build 仍有 shared JS chunk 约 1,276.03 kB minified 的既有 warning；这支持“未来
  route-level code split 调查”，不支持现在机械拆文件或删除 legacy copy。
- `REFACTOR` candidate：以 route/feature ownership 为单位拆分，并保持 API fail-closed、
  fixture explicit-only、locale identity 不变；需要 Web regression 后再实施。

## 10. Reviewed evidence / Demo

- `runtime/` 有 93 个 `reviewed*.json`，`spikes/` 有 5 个 reviewed JSON；审计检查的
  reviewed-named JSON 共 98 个，无 byte duplicate。
- reviewed bytes、hash、source identity、failure signature、Agent FAIL/Platform ERROR/
  UNKNOWN_OUTCOME hierarchy 和 `historical_bytes_unchanged` 规则全部 KEEP。
- verifier 对文件名有显式引用，增加 discoverability manifest 可以是 RPF-38 的小范围
  CONSOLIDATE，但不得 rename/move/normalize/regenerate。本轮没有触碰任何 reviewed file。
- Golden Demo 的 `start-demo.ps1`、`stop-demo.ps1`、`lifecycle.ps1`、
  `verify-lifecycle.ps1`、`verify-golden-demo.py`、`seed_demo.py` 形成唯一推荐路径；
  child-specific environment、read/worker scope、label ownership、PID/port/container
  lifecycle 不能合并成无边界 helper。

## 11. Dependency / supply chain

- **Unused**：静态引用检查未发现 root Web direct dependency 无使用；React/ReactDOM、
  Vite/plugin、TypeScript/Vitest 均在源码/config/tests 中出现。Java AWS SDK、OTel、
  PostgreSQL、Spring 依赖均在正式 source/test 中出现；Python OTel 依赖被 formal
  runtime observability 使用。
- **Outdated/deprecation**：现有 hosted annotation 明确提示 Node.js 20、setup-java v4、
  ubuntu-latest migration；`npm audit --audit-level=high` 返回 0 high/critical，
  但没有把这次 audit 当作完整 Java/Python license/security 认证。版本升级另开维护
  任务，不在 RPF-37 自动 major-upgrade。
- **License/security**：本轮没有引入依赖；未运行新的 Maven/Python license database
  扫描，因此不声称全供应链 clean。当前 package/pom/requirements 的 pin/lock 继续 KEEP。
- **No action now**：不为审计永久引入 ruff/pytest/ESLint/dependency-check 等新生产
  依赖；如 RPF-38 需要静态分析，优先临时工具或独立 CI evidence。

## 12. Config / environment / security

- Java canonical config 在 `control-plane/src/main/resources/application.properties`：
  PostgreSQL、schema version、local/S3 backend、S3 endpoint/timeouts、optional OTel、
  probe flag 和 read/evidence/decision/agent/CI/worker token 均以 `RPF_*` 注入。
- Python canonical surface 包含 `DEEPSEEK_API_KEY`、`RPF_MODEL`、Control Plane URL/token、
  artifact root/backend、worker IO root、OTel enabled/endpoint/queue 和 child-role env；
  Provider key 不进入 tracked corpus、前端 bundle 或普通 evidence。
- Web 只从 Vite dev proxy 注入 read token；`VITE_CONTROL_PLANE_DATA_SOURCE=fixture` 是
  显式测试模式，API 不可用时 fail closed。`RPF_CONTROL_PLANE_READ_TOKEN` 与
  `RPF_AUTH_READ_TOKEN` 是 proxy/service 边界的有意别名，不合并成更宽权限。
- Demo 使用 dummy/local credentials 进行 lifecycle proof；child-specific env 禁止 Web/
  Worker 获得其他 authority。RPF-32 的 S3 credential 只在 disposable process/container
  注入；RPF-36 没有 provider credential。
- CI workflows 没有 `id-token` permission，没有 release/deploy step；需要 `actions: write`
  的 workflow 仍应在 RPF-38 单独复核是否可缩为 artifact 最小权限。
- `ci/verify-public-docs.py`、reviewed verifiers 和 lifecycle verifier 已覆盖 secret-like
  field、Authorization/private protocol、absolute path、raw artifact 和 child env 边界。

## 13. Git hygiene / documentation / static analysis

- `git ls-files` 未发现 tracked `target/`、`node_modules/`、`dist/`、`.local/`、
  `__pycache__`、`.log`、`.pyc` 或 `.class`；没有 tracked binary/large file。
- 本机存在若干被 `.gitignore` 保护的 Maven `target/`，总量约 44–53 MB/目录级别，
  属于可重建的 ignored local build debris，不纳入本轮提交，也不触碰用户本地运行状态。
- `docs/reviews/` 仍只出现在 Git status 的 user-owned untracked 状态；RPF-37 不操作它。
- public docs verifier：`PUBLIC_DOCS_PASS files=18 pairs=7`。README → Architecture →
  Demo → Core Modules 的入口关系清楚；Architecture 当前的 RPF-37 “上云 slice”文字
  属于过期 current boundary，本轮已校准为 Deferred/maintenance。
- 静态工具实际结果：TypeScript typecheck PASS、Maven test/package PASS、runtime tests
  PASS；没有配置专门的 ESLint/Java/Python unused-dead-code gate，因此不能把“编译通过”
  当成无死代码。TODO/FIXME 搜索未发现待办型代码块；出现的 `legacy`/`compatibility`
  均有测试/旧 identity/生命周期保护语义。

## 14. Exact cleanup contract for RPF-38

### DELETE candidates

**None identified and approved.**

当前没有一个文件同时满足“无 runtime/CI/docs/verifier 引用、无唯一历史证据、无
compatibility/rollback 价值、删除后正式合同仍完整可证明”。因此不删除 reviewed
JSON、早期 Spike source、focused workflow 或 legacy compatibility path。

### CONSOLIDATE candidates

以下是 RPF-38 可执行但仍需逐项验证的精确范围：

1. `.github/workflows/rpf-27-network-spike.yml`、`rpf-29-otel-spike.yml`、
   `rpf-31-s3-spike.yml`、`rpf-36-production-topology.yml`：从普通 push/PR 自动矩阵
   收敛为明确 manual/historical path；若要删除 workflow 文件，必须先保留可复现
   command、source identity、hosted evidence link 和 rollback patch。
2. `rpf-28-multi-service.yml`、`rpf-30-otel.yml`、`rpf-32-s3-artifact-store.yml`、
   `rpf-33-capacity-spike.yml`、`rpf-34-read-model.yml`、
   `rpf-35-canonical-read-model.yml`：把 broad path trigger 收窄到影响域或 manual
   checkpoint，保留各自 negative control 和 artifact verifier。
3. 反复出现的无 authority readiness/HTTP JSON/cleanup helper：只在 call-site 与错误
   分类证明相同后，抽到 `ci/lib` 或 `testsupport`；不合并 provider/fault/read-budget
   语义，不移动 reviewed evidence。
4. `AGENTS.md` 的历史命令矩阵与当前执行规则：将来可分层到 history/index，但必须保留
   当前 MUST、保护边界、source identity 与 recovery-before-retry 规则。
5. `runtime/verify-reviewed-artifacts.py` 的 file discovery：可增加版本化 manifest/index
   作为辅助入口，但保留当前 explicit paths、hash/identity verifier 和 immutable bytes。

### ARCHIVE candidates

保持内容可查和可复现的候选目录：

`spikes/rpf-01/`, `spikes/rpf-02/`, `spikes/rpf-09/`, `spikes/rpf-10/`,
`spikes/rpf-13/`, `spikes/rpf-15/`, `spikes/rpf-27/`, `spikes/rpf-29/`,
`spikes/rpf-31/`。

归档方式必须先决定“原路径是否为 public/documented/CI consumer”：优先增加
`docs/history/` 索引或在原 README 标记 superseded，再考虑可回滚的 Git move。RPF-16/17/18/
28/30/32/33/34/35/36 不在本列表中。

### REFACTOR candidates

仅作为后续结构任务，不与删除混做：

- Web：`web/src/App.tsx`、`web/src/styles.css`、`web/src/data/artifacts.ts`、
  `web/src/i18n/messages.ts`；按 feature/route ownership 拆，保持 locale/API/fail-closed。
- Control Plane：`DurableExecutionController.java`、`CanonicalMetadataService.java`、
  `control-plane/probe.py`；按 command/read/DTO/validation 小步提取。
- Runtime：`statistical.py`、`evaluation.py`、`quality.py`、`failure_intelligence.py`、
  `incident.py`、`multi_service_environment.py`；先锁定 source identity、serialization
  和 contract tests，再 safe-extract。
- Orchestration/verifier：`ci/run_release_gate.py`、`runtime/verify-reviewed-artifacts.py`
  只允许低风险辅助提取；canonical authority 和 explicit evidence list 不重写。

### Protected KEEP list

`runtime/reviewed-*.json`、`spikes/*/reviewed-*.json`、source/hash identity、
`runtime/runproof_runtime/failure_intelligence.py` 的 signature v1、Agent FAIL /
Platform ERROR / `UNKNOWN_OUTCOME` / `RECONCILE_REQUIRED` hierarchy、fresh-per-run/trial、
operation/lease/fencing/idempotency、`control-plane/` PostgreSQL canonical truth、
`LocalFileArtifactStore` default、S3 immutable/no-overwrite contract、RPF-16/17/18/28/30/32/
34/35 formal paths、Golden Demo stable identity、`release-gate.yml` + release authority、
public docs claims、`PROJECT_BRIEF.md`/`DECISIONS.md` durable decisions、以及用户
`docs/reviews/`，全部 KEEP。

## 15. Estimate, risk and regression matrix

### Estimated RPF-38 reduction

- RPF-37 当前提交：**不删除产品/证据资产，预期 0 个历史产品文件、0 个 reviewed
  bytes 被删除**。
- RPF-38 safe workflow phase：最多先处理 4 个 historical-only workflow 的自动触发
  收敛；若最终删除 workflow 文件，预计约 `0–4 files / 0–25 KB tracked`，取决于是否
  保留 manual workflow。此估计不包含未跟踪 ignored target 的本地磁盘清理。
- Spike source 的第一安全阶段预期 `0 byte` 减少，因为 ARCHIVE 先保留原始证据；代码
  REFACTOR 预期文件数可能增加而不是减少。任何更大 reduction 必须另开明确 deletion
  decision。

### Risks by category

- DELETE：最高风险；当前无候选，保持 zero-delete。
- CONSOLIDATE：中高风险，可能遗漏 workflow path、external consumer、唯一 negative
  control；必须先做 same-source regression 和 rollback patch。
- ARCHIVE：中风险，Git move 或 workflow 停止可能破坏历史链接/hosted rerun；保留原
  README/RESULT、source identity、command 和索引后再动。
- REFACTOR：高风险，可能改变 serialization、authority 或 UI fail-closed；拆成小提交，
  先 contract tests 再结构变化。

### Required RPF-38 regression matrix

每个 cleanup commit 至少执行：

1. `python spikes/rpf-37/audit.py --root . --output .local/rpf-37/audit.json`、
   `git diff --check`、tracked generated/duplicate/hash/source identity 检查；
2. `python -m unittest discover -s runtime/tests -p 'test_*.py' -v`、
   `python runtime/verify-reviewed-artifacts.py`、`python ci/verify-public-docs.py`；
3. `npm test`、`npm run typecheck`、`npm run build`、
   `mvn -q test package -f control-plane/pom.xml`；
4. 若触及 runtime/Agent/reviewed：RPF-16、RPF-17、RPF-18 verifier 和 source identity
   checks；若触及 network/OTel/S3/read model：分别运行 RPF-28、30、32、34、35 focused
   probe/verifier；
5. 若触及 Demo：`python demo/verify-golden-demo.py --root . --json` 和
   `powershell -ExecutionPolicy Bypass -File demo/verify-lifecycle.ps1 -Mode contracts`；
6. cleanup 完成后运行 canonical `ci/run_release_gate.py`/hosted gate；只有明确触及
   RPF-33 capacity harness 时才运行其 heavyweight capacity path，不把它设为默认。

### RPF-38 readiness

`READY_FOR_REPOSITORY_CLEANUP = YES`

YES 仅授权下一计划执行本文列出的低风险 workflow trigger/docs/index 分层和可回滚
archive preparation；不授权无清单删除、reviewed artifact 迁移、全仓代码重构或云部署。
由于 DELETE list 为空，RPF-38 应先从 fast/historical workflow 和 governance/history
分层开始，正式代码 REFACTOR 另开 coherent commit 或后续 Plan。

## 16. Project State changes

本轮应同步记录：

- `CURRENT_STATE.md`：RPF-00～RPF-37 complete；Lifecycle 改为
  `Stabilization / Portfolio Maintenance`；RPF-37 是 audit-only；真实云 Production
  Deferred，AWS/ap-southeast-1 candidate-only；下一边界为 RPF-38 cleanup。
- `docs/ARCHITECTURE.md` 与 `.zh-CN.md`：保留 RPF-36 topology/authority 结论，把
  “conditional RPF-37 production slice” 改为当前 Deferred + RPF-38 maintenance boundary。
- `docs/history/VERIFICATION_HISTORY.md` 与 `.zh-CN.md`：追加 RPF-37 审计事实和验证
  边界；不修改 RPF-36 历史 run/digest 事实。
- `DECISIONS.md`：不新增 provider decision，不删除 durable decision。

## 17. Verification evidence executed in this checkpoint

| Command | Result |
|---|---|
| `python spikes/rpf-37/audit.py --root . --output .local/rpf-37/audit.json` | PASS; 376 files / 5,228,288 tracked bytes at starting HEAD; 11 workflows; 19 spikes; 0 duplicate hash groups; 0 tracked generated files |
| `npm test` | PASS; 11 files / 43 tests |
| `npm run typecheck` | PASS |
| `npm run build` | PASS; existing shared bundle warning remains |
| `python -m unittest discover -s runtime/tests -p 'test_*.py' -v` | PASS; 85 tests |
| `python runtime/verify-reviewed-artifacts.py` | PASS; source `cd31a021550f680a3ca512d210b9533a262fb734a769d4f8d3f6bee11adacaf7` |
| `python ci/verify-public-docs.py` | PASS; `PUBLIC_DOCS_PASS files=18 pairs=7` |
| `mvn -q test package -f control-plane/pom.xml` | PASS |
| `npm audit --audit-level=high --json` | PASS; 0 high/critical vulnerabilities reported by npm audit |

RPF-33 full capacity matrix、DeepSeek live call、provider credential、cloud API、Production
deploy/release 均未执行。
