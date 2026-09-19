# RunProof 架构

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md) | [README](../README.zh-CN.md)

本文描述当前有证据支持的架构边界。它是产品地图，不是对所有推荐 Production 组件已经部署的承诺。

## 架构一览

```text
User / CI
    → Desktop Web Control Plane
    → Java / Spring Control Plane
    → PostgreSQL canonical metadata
    → Durable Job
    → Python Worker
    → Controlled Simulation Environment
    → Run / Trajectory / State Diff / Evidence
    → Quality Policy 与 Release Gate
    → Release Decision（只读决策）

Provider boundary ── Agent run 的可选输入；Golden Demo 不依赖它
Immutable Artifact Store ── 由 Control Plane 引用的经验证据字节
```

主路径通过正式 Control Plane 使用 HTTP/JSON。浏览器不连接 PostgreSQL，不持有 worker 或 decision credential；canonical API 不可用时也不会静默回退到 fixture data。

## 组件与 ownership

| 组件 | 当前职责 | 权限边界 |
|---|---|---|
| Desktop Web Control Plane | 只读 Overview、调查、比较、执行和决策页面 | 仅 presentation；不发起 live Agent、worker、promotion、release 或 deploy mutation |
| Java/Spring Control Plane | canonical metadata、经验证 artifact 注册/回读、durable Job API 和 decision history | service principal 有范围；decision writer 与 Agent/worker 执行分离 |
| PostgreSQL | canonical metadata 与 durable Job/Attempt/Operation/Event 状态 | 当前正式 transport 是有界 poll/claim/lease；不等于 broker 或 HA 结论 |
| Immutable Artifact Store | 保存经过 schema、kind、identity、source、hash 验证的 evidence bytes | candidate writer 不能创建 canonical verified/release authority |
| Python Agent/Evaluation Runtime | Agent contract、受控评测、evidence、regression、统计和 HTTP client | 不把 Provider credential 或 release authority 暴露给 Web |
| Durable Worker | claim、heartbeat、reconcile、执行显式 profile、报告 evidence | `UNKNOWN_OUTCOME` 必须先 reconcile；worker 不能写 Release Decision |
| Controlled Simulation Environment | 为副作用 Tool 和 fault scenario 提供 fresh、可观察的有状态环境；RPF-28 正式路径可在 private network 组合 target、dependency、Toxiproxy 和 Agent-shaped client | 不连接真实 Production destructive credential；Agent 只能看到 data-plane boundary |
| Provider boundary | 可选的模型/provider 调用边界；DeepSeek 是首个参考 Provider | credential 不进入 Git、浏览器、evidence 或默认 trace |
| GitHub Actions Release Gate | fresh CI 检查、durable evaluation、canonical Decision read-back 和脱敏 artifact | CI 记录 evidence，不执行 release/deployment |

## Canonical 数据流

1. Agent、Scenario、Environment、Verifier 和 Evaluation identity 共同定义候选版本。
2. Control Plane 提交 durable Job；worker 使用 lease 和 fencing identity claim。
3. Agent 只在 Controlled Simulation Environment 内操作。既有单容器路径继续支持；RPF-28 正式路径使用 fresh Docker `--internal` network，并把 fault activation/observation 保留在 Environment adapter 内。可观察 action、transition、receipt、fault provenance 和 verification fact 成为 Run/Evidence 记录。
4. Control Plane 保存 canonical metadata，只接受经过验证的 immutable artifact 引用。
5. Failure investigation 可以派生 Failure Case、Regression、Failure Intelligence、Statistical Evaluation 和 Comparison，但不能改写源 evidence。
6. Quality Policy 产生 Gate 和 Release Decision。`ELIGIBLE` 是只读决策结果，不是 release command。

## 正式诊断 Observability

正式 RPF-30 在 Java Control Plane、PostgreSQL durable Job/Attempt 边界、
Python Worker、Agent、Tool、Environment、RPF-28 target/dependency transport、
reconcile 和 verifier 上增加了可选 OpenTelemetry instrumentation。SDK 路径
使用 W3C `traceparent` 与一组严格 allowlisted 的 W3C Baggage。`job_id`、
`attempt_id`、`run_id`、`environment_id`、`operation_id` 仍是 RunProof
canonical identity；`trace_id` 与 `span_id` 仅是诊断 identity。

三种正式模式保持相同 canonical 语义：disabled/no-op、enabled 且外置
Collector 健康、enabled 但 Collector 不可用。Export 使用有界异步路径；
queue drop 和 export failure 只形成 telemetry diagnostic counter/log，不会
成为 Agent outcome。response-lost Run 因此可以显示 Job → Attempt → Agent →
Tool → target/dependency → reconcile 链，而 receipt、effect count、
`UNKNOWN_OUTCOME`、verifier、Evidence、Gate 和 Decision 仍由 canonical
execution path 持有 authority。

Collector 是可选且 pinned 的验证 fixture，不是启动依赖或 authority。RPF-30
不新增 canonical trace 字段或 trace artifact，不引入 Web trace UI、
Jaeger/Tempo/Grafana、SaaS backend 或长期 retention 承诺。Telemetry attribute
和 metric label 采用 allowlist，并排除 credential、prompt、body、private
reasoning、本机私有路径，以及作为 metric label 的高 cardinality ID。

## 正式 S3-compatible ArtifactStore

RPF-32 在同一个 provider-neutral `ArtifactStore` contract 后新增
`S3ArtifactStore` adapter。`local` 仍是默认 backend；必须显式选择 `s3`，
错误 backend 配置会 fail closed。Control Plane、canonical metadata service、
Web read model 与 durable worker 不依赖 AWS 或 SeaweedFS 类型。

对象存储只保存 immutable bytes。PostgreSQL 仍是 artifact 注册、entity identity、
schema、source identity、RunProof SHA-256 和 metadata relationship 的 canonical
来源。跨进程 Worker 通过 authenticated Control Plane 先上传 bytes，再 ingest
manifest；对象存在本身不是 evidence。首次写入使用带 `If-None-Match: *` 的
conditional `PutObject`；相同 bytes 是幂等 replay，不同 bytes 是 immutable
conflict。未知写入结果只允许 bounded GET/retry reconcile，不能静默回退到 local。

Verified read 只做一次 object GET，然后验证 body hash、JSON header、schema、
artifact kind、entity identity、source identity 和 runtime identity。ETag、
versioning、Object Lock 都不是 RunProof identity。SeaweedFS `4.47` 是当前
disposable compatibility proof 的 pinned provider；该证据不代表托管对象存储
durability、HA、replication、lifecycle/GC、capacity、migration 或 Production
release authority。

## 有界 Canonical Metadata read model

RPF-35 将 canonical metadata discovery 与经验证 artifact detail 分离。
`GET /api/v1/metadata` 默认只返回 50 行，hard maximum 为 100。其 opaque
`rpf-metadata-cursor-v1` keyset cursor 绑定 entity scope、排序、page size 和
cursor version；malformed 或不兼容 cursor 会 fail closed。主要 entity order
是 `created_at,entity_id:asc`；有界 cross-type discovery 使用
`created_at,entity_type,entity_id:asc`。实现使用 keyset predicate，不以
`OFFSET` 为主方案；cross-type EXPLAIN 已记录，当前 sequential scan 有意留给
后续 focused index plan。

Metadata page 只返回 registered identity、summary、refs 和 ArtifactRef
事实，并用 `REGISTERED_REFERENCE` 表示 availability。它不会逐项读取完整
artifact body，也不声称当前 bytes 已重新验证。Canonical detail 先以
`verify=false` 读取一条 metadata，再通过现有 Local/S3 verification authority
读取选中的 artifact；detail 仍必须执行 hash、schema、kind、entity、source 和
runtime identity 校验。

API mode Web 使用 route-scoped ownership：canonical index 每次只请求当前一页
有界 metadata，detail deep link 只请求该 entity 的 metadata 与 verified artifact，
Overview 使用固定 reviewed Golden Demo refs 与有界 aggregate 依赖。App root 不再
启动 full corpus bootstrap，也不自动爬取全部 metadata cursor。旧的完整 corpus
adapter 仅保留给显式 fixture/compatibility caller。Previous/Next cursor state
写入 URL；raw/expert view 会标明当前有界 page 或 entity，不把局部内容冒充完整
历史 snapshot。

RPF-35 本地 proof 在 13,502 条 metadata 上测得：100-row page 最多 2 条 SQL、
139,940 bytes；list artifact-body read 为 0；verified detail 使用一次、
15,202-byte artifact body。这是仓库 regression budget，不是 Production SLA。
RPF-35 不引入 artifact streaming、浏览器 virtualization、retention/GC、broker、
topology 或 release/deploy authority。

## Production topology 与 Managed Operations 调查

RPF-36 是调查边界，不是云部署。它按 `2026-09-19` 的 Provider 资料比较了
AWS ECS/Fargate + RDS + S3、Render + Cloudflare R2、Railway + Cloudflare R2。
当前首选 candidate 是单 region AWS topology，首个 Region candidate 为
`ap-southeast-1`（Singapore）。Region、latency、data residency、account quota
和 cost 仍须在 RPF-37 做 preflight 并取得授权；RPF-36 没有使用 provider
account、paid resource 或 cloud API。

候选数据流为：

```text
Internet -> static Web/CDN -> read-only API edge -> stateless Control Plane
                                              -> managed PostgreSQL
                                              -> S3-compatible artifact store
private Durable Worker -> Control Plane HTTP/JSON -> scoped RPF-28 Simulation task
GitHub Actions -> canonical gate -> protected human Approval -> Release principal
```

Web 只读，API 或 verified artifact 不可用时 fail closed。Control Plane 无状态，
PostgreSQL 与 object storage 是 canonical；Worker 初始为一个 private、
outbound-only replica、concurrency 1。RPF-28 的 fresh target/dependency/
Toxiproxy environment 必须映射为 scoped per-run task 或独立 sandbox host；
Agent/Worker 永不拿 Docker socket、数据库 credential 或 Release principal。

Release boundary 保持：
`Release Decision ELIGIBLE -> human/product Approval -> protected Release
principal -> deployment -> target verification`。候选的
`rpf-product-release-identity-v1` 绑定 commit、source tree、application 和
image/static digest、migration identity、build run、target environment、
deployment id、timestamp；它独立于 Agent Version Identity 且 append-only。
GitHub Actions OIDC 只作为受限短期 release identity 候选，必须绑定
repository/workflow/environment，canonical gate 本身不部署。

RPF-36 提出 RDS backup/PITR + independent restore-to-new-instance rehearsal、
应用层 S3 immutability、七天 orphan grace + dry-run inventory、additive
expand/contract migration，以及带 circuit-breaker/alarm rollback 的 ECS
rolling deployment。这些是 candidate operation，不是 Production SLA。初始
sizing 只复用 RPF-33 的方向性 evidence；`BROKER_REQUIRED=NOT_YET` 不变。

生命周期判断是
`READY_FOR_PRODUCTION_IMPLEMENTATION = CONDITIONAL`：仍需证明 per-run
Simulation hosting、provider/account/region/budget preflight、独立 restore、
human Approval/Release principal 配置，以及 Product Release Identity
read-back/rollback。完整矩阵、日期来源和离线 proof 见
[`spikes/rpf-36/`](../spikes/rpf-36/README.md)。

## Authority 与恢复边界

- Agent 和 worker 的 authority 小于 decision-writer authority。
- `PASS`、`FAIL`、`ERROR`、`INVALID`、`INCONCLUSIVE`、`CANCELLED` 是执行结果；Release Decision 属于独立状态域。
- 可能发生副作用后丢失响应时进入 `UNKNOWN_OUTCOME`，随后进入 `RECONCILE_REQUIRED`；必须先用 environment receipt/state 证明，再决定是否 retry。
- 历史 Run、Evidence、Regression 和 Decision 采用 append-only 或 superseding；后续解释不能静默改写旧字节。
- Web/API 故障采用 fail-closed；缺失或未验证 artifact 不会被静态成功 fixture 替代。

## 仓库地图与 README 审计

| 区域 | 其 README 的用途 | 公共架构入口 |
|---|---|---|
| `control-plane/README.md` | Java 构建、服务启动、API 与 worker 实现细节 | 本文和 [DEMO.zh-CN.md](DEMO.zh-CN.md) |
| `runtime/README.md` | Python runtime/evidence/evaluation 入口与合同 | [RELIABILITY_MODEL.zh-CN.md](RELIABILITY_MODEL.zh-CN.md) 和 [GLOSSARY.zh-CN.md](GLOSSARY.zh-CN.md) |
| `web/README.md` | Web adapter、read model 和 presentation 实现 | 本文和 [DEMO.zh-CN.md](DEMO.zh-CN.md) |
| `spikes/*/README.md` | disposable 调查与历史 probe 边界 | [VERIFICATION_HISTORY.zh-CN.md](history/VERIFICATION_HISTORY.zh-CN.md) |
| `demo/` | Golden Demo profile、seed、生命周期和 verifier | [DEMO.zh-CN.md](DEMO.zh-CN.md) |
| `docs/project/` | canonical governance 和当前 Project State | [README](../README.zh-CN.md) |

模块 README 保持 implementation-facing。公共声明集中在本文及配对公共文档中；没有任何模块 README 被提升为第二个 Project-State authority。

## Claim → evidence 映射

| 声明 | 证据位置 | 验证入口 |
|---|---|---|
| Durable execution 与 response-loss reconciliation | `control-plane/`、RPF-14 reviewed execution artifacts、response-lost Run | `python control-plane/probe.py`；RPF-14 evidence verifier |
| 两个显式 Agent contract | RPF-16 reviewed Agent-bearing corpus 与 `runtime/` contracts | `python spikes/rpf-16/probe.py --verify` |
| 确定性 Failure Intelligence 与 Version Bisect | RPF-17 reviewed artifacts 与 `spikes/rpf-17/` | `python spikes/rpf-17/verify-evidence.py` |
| Statistical Reliability 边界 | RPF-18 reviewed statistical artifacts | `python spikes/rpf-18/verify-evidence.py` |
| API-backed、只读 Web | `web/src/data/`、`control-plane/`、reviewed corpus adapters | `npm test`；`npm run typecheck`；`npm run build` |
| 双语 Control Plane presentation | `web/src/i18n/`、locale-aware view model 与 RPF-25 compatibility tests | Web tests/typecheck/build；locale/API-unavailable checks |
| Hosted canonical Release Gate | `.github/workflows/release-gate.yml`、`ci/run_release_gate.py` | GitHub-hosted workflow 和 Job Summary contract |
| Golden Demo integrity 与生命周期 | `demo/rpf-19-golden-demo-v1.json`、`demo/verify-golden-demo.py`、lifecycle verifier | `python demo/verify-golden-demo.py --root . --json` |
| 正式多服务网络故障 | RPF-28 reviewed baseline/dependency/response-loss Run、`multi-service-toxiproxy-v1` 与 durable-worker focused result | `python spikes/rpf-28/probe.py --run`；`python spikes/rpf-28/verify-evidence.py .local/rpf-28/rpf28-formal-result.json` |
| 正式诊断 Observability | RPF-30 SDK instrumentation、三模式 durable probe、Collector trace file 与 span/cardinality verifier | `python spikes/rpf-30/probe.py --run`；`python spikes/rpf-30/verify-evidence.py .local/rpf-30/local/rpf30-result.json` |
| 正式 S3-compatible ArtifactStore | `S3ArtifactStore`、显式 backend wiring、SeaweedFS 4.47 proof、PostgreSQL canonical ingest 与 HTTP/JSON Worker upload | `python spikes/rpf-32/probe.py --run`；`python spikes/rpf-32/verify-evidence.py --result <rpf32-result.json>` |
| 有界 Execution read model | RPF-34 summary list、opaque keyset cursor、有界 detail/timeline、query/payload budget 与 eligible-discovery 兼容性 proof | `python spikes/rpf-34/probe.py --run --output-dir .local/rpf-34/<run>`；`python spikes/rpf-34/verify-evidence.py <rpf34-result.json>` |
| 有界 canonical metadata read model | RPF-35 metadata cursor contract、registered-reference list、verified Local/S3 detail、route-scoped Web loader、no-auto-crawl budget 与 Large fixture proof | `python spikes/rpf-35/probe.py --run --output-dir .local/rpf-35/<run>`；`python spikes/rpf-35/verify-evidence.py <rpf35-result.json>` |
| Production topology 与 Managed Operations 边界 | RPF-36 dated provider matrix、candidate region/topology、managed persistence/secrets、Simulation hosting boundary、Release Identity/Approval chain、restore/rollback/cost model 与 conditional RPF-37 scope | `python spikes/rpf-36/probe.py --run --output-dir .local/rpf-36/<run>`；`python spikes/rpf-36/verify-evidence.py <rpf36-result.json>` |

source identity、hosted run 和历史兼容性事实统一保存在 [VERIFICATION_HISTORY.zh-CN.md](history/VERIFICATION_HISTORY.zh-CN.md)，不重复塞入 current snapshot。

## Production 边界

当前仓库证明了 Controlled Simulation、正式 fresh 多服务网络故障 Environment、本地 production-like persistence/recovery、显式 PostgreSQL durable workflow、immutable evidence、正式 S3-compatible object-store adapter、hosted CI 检查和 Windows 本地 Golden Demo 生命周期。RPF-36 增加的是 conditional managed-topology 调查，不是云部署；它仍没有证明或授权 Production HA、托管云 operations、多主机 supervisor、human Approval 配置、tenant/RBAC identity 或真实破坏性 remediation。

下一架构边界是 conditional RPF-37 slice：取得 provider/account/region/budget
授权，证明一个 managed RDS/S3 connection 和一个 scoped RPF-28 Simulation
task，再验证 Product Release Identity、restore 和 rollback。RPF-36 不授权实际
Production deployment，也不引入 Kubernetes、broker、multiregion、完整
tenant/RBAC 或自动 `ELIGIBLE` deployment。RPF-35 仍不证明 Production capacity、
artifact streaming、virtualization、retention/GC 或 managed durability；S3
adapter 仍是 compatibility boundary，不是 durability、HA 或 release authority
结论。
