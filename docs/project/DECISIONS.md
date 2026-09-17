# DECISIONS

> 保存已确认决定的 canonical identity、理由、后果与重新考虑条件；普通任务和实现日志不进入本文件。

## Identity and recording boundary

D-001～D-012 继承 Bootstrap 的同名决定；Accepted 表示接受该决定的原有范围，其中 D-008 仅接受推荐方向，不代表技术栈已实现或成为施工硬约束。

首次导入提交 `efb0101` 曾合并 D-002/D-003，并错误重用后续编号；该提交中的编号仅能连同历史版本理解，不作为当前 alias。本文件恢复原始身份，相关旧引用应按决定语义迁移；后续不复用或静默重编号。原始决定仍有效，因此本次修复不是 Superseded，也不重写 Git 历史。

## D-001｜产品定位采用 Agent Reliability & Release Engineering

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
项目正式定位为 **RunProof — Agent Reliability & Release Engineering Platform**，不采用普通 Agent Eval Platform 作为主定位。
### Why
Eval 只是实现可靠性与发布决策的手段；最终问题是 Candidate Agent Version 是否有足够证据可以发布。
### Consequences
必须覆盖 Stateful Evaluation、Failure Investigation、Regression 与 Release Gate。
### Reconsider when
只有真实用户需求证明 Release Engineering 不再是核心价值时重新评估。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-002｜采用 Reference-Agent-first 的通用化路径

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
产品定位保持 Generalizable，但 v1 只把 Production Change Agent 做成完整第一垂直切片。
### Why
没有第二种真实 Agent 前，过早抽象会导致 Adapter Hell。
### Consequences
避免写死 Change Agent，但不为未知框架建设复杂扩展层。
### Reconsider when
出现第二个真实、长期使用且共享明显 integration pattern 的 Agent。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-003｜Production Change Agent 为首个 Reference Agent

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
v1 Reference Agent 面向发布、Canary/Rollback、配置变更和状态迁移。
### Why
该领域天然具有长期任务、Tool、副作用、审批、部分成功、UNKNOWN_OUTCOME、恢复与安全边界。
### Consequences
Simulation Environment 必须支持足够真实的状态和故障模式，但无需复刻完整云平台。
### Reconsider when
Spike 证明该场景无法形成可信 Stateful Evaluation。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-004｜DeepSeek 为首个真实 LLM Provider

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
v1 首个且默认真实 LLM Provider 使用 DeepSeek。
### Why
大量重复 Evaluation 使成本成为实际工程变量。
### Consequences
Provider 层保持可扩展；Token、Latency、Cost 必须可观察。
### Reconsider when
DeepSeek 无法满足最低 Tool Calling/Structured Output/稳定性合同，或其他 Provider 明显更优。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-005｜关键可靠性判定优先确定性验证

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
可由环境状态、显式规则和程序验证的事实，不使用 LLM Judge 作为唯一裁判。
### Why
RunProof 用于降低不确定性，不能把核心 PASS/FAIL 交给另一个不确定模型。
### Consequences
Verifier、Invariant、Safety Policy、Release Gate 以确定性证据为主。
### Reconsider when
仅对本质无法确定性表达的语义目标引入明确标注的不确定评估。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-006｜v1 仅操作 Controlled Production Simulation

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
所有高风险、有副作用 Tool 只操作受控 Simulation Environment。
### Why
可重置、可观测、可验证是 Stateful Evaluation 前提，并降低真实生产风险。
### Consequences
Real Production integration 为 FUTURE。
### Reconsider when
核心 Reliability Loop 成熟且出现真实外部系统接入需求。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-007｜Desktop Web 是 Portfolio-critical Primary Surface

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
Desktop Web Control Plane 是核心人类交互面；视觉质量、证据可视化、调查效率和功能完整性属于正式验收。
### Why
RunProof 核心任务是理解复杂 failure 和 release evidence，纯 CLI/模板化后台无法充分表达。
### Consequences
Timeline、State Diff、Trajectory Diff、Gate Matrix、趋势/分布等必须服务真实工程任务。
### Reconsider when
无；仅调整具体视觉系统和实现技术。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-008｜采用 Java Control Plane + Python Agent Runtime 的推荐架构

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
推荐 Java/Spring Boot 承担确定性 Control Plane，Python 承担 Agent/Evaluation Runtime。
### Why
Run 生命周期、调度、状态机、权限、Release Policy 与审计属于长期确定性平台状态；LLM Provider、Agent Loop 和 AI Eval 更适合 Python。
### Consequences
具体通信、Queue、进程/部署边界仍需 Spike。
### Reconsider when
真实仓库或 Spike 证明双运行时复杂度显著超过收益。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-009｜Agent FAIL 与 Platform ERROR 严格分离

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
至少区分 `PASS / FAIL / ERROR / INVALID / INCONCLUSIVE / CANCELLED`。
### Why
平台故障、Provider outage、Environment reset failure 或 Scenario invalid 不能伪装成 Agent regression。
### Consequences
Release Gate 必须考虑证据覆盖率。
### Reconsider when
不取消，只允许细化状态模型。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-010｜Evidence 事实与派生分析分层

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
Observed Fact、Verified Result、Inference、AI Analysis 不得混为同一事实层级。
### Why
Failure Attribution 和 AI 分析天然具有不确定性。
### Consequences
数据模型与 Web UX 都必须表示证据层级。
### Reconsider when
无。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-011｜Failure 经验证后才可晋升 Regression

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
Failure 不自动加入永久 Regression Corpus；必须重现、验证和稳定化。
### Why
临时 Provider 波动、环境噪声或重复失败会污染长期测试资产。
### Consequences
Failure-to-Regression 是独立业务流程。
### Reconsider when
无；可以提高自动化，不能取消质量门槛。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-012｜导师研究方向不作为项目硬约束

- Status: `Accepted`
- Date: 2026-09-11（仓库记录日期；原始批准日期未提供）
### Decision
Graph ML、社区算法、联邦学习仅在未来对 Agent Reliability 有显著真实价值时引入。
### Why
第一目标是 AI Agent / AI Backend / Production AI 求职价值。
### Consequences
科研方向通过独立学习与研究项目推进。
### Reconsider when
出现与 RunProof 核心数据/机制高度重合且能显著提高产品或论文价值的研究问题。

### Supersedes

- none（继承既有决定，不构成产品决策替代）

## D-013｜Quality Policy precedence 决定 Release Decision

- Status: `Accepted`
- Date: 2026-09-12
### Decision
RunProof 的 Prototype Release Gate 使用独立、versioned Quality Policy；Policy 以 `rpf-minimal-reliability-suite@1.0.0` 为兼容 Suite，确定性聚合 Hard / Soft / Review rules。决策 precedence 固定为：Hard blocker → evidence insufficient → review required → eligible。`ELIGIBLE` 仅表示当前 evidence 在 Policy 下达到资格，不执行发布，也不构成 deploy/release authorization。
### Why
Release 判断必须可审计、可复现，并保留 Agent FAIL、Platform/Environment ERROR、证据缺口、未知 usage 与人工 Review 的语义边界；Evaluation/Comparison 本身不应隐含发布结论。
### Consequences
Quality Policy、Gate Evaluation 和 Release Decision 独立于 Suite/Evaluation/Comparison/Regression 保存 source identity、stable refs、blocking/review/soft evidence 与 immutable/superseding history。Unknown token/cost/latency 是非阻断 warning，不能被当成零；页面和 CLI 都保持 decision-only，不提供 release/deploy action。
### Reconsider when
出现第二个真实产品使用场景、跨 Suite 的 Policy 复用需求，或需要服务端持久化、权限/审批与真实发布集成时，重新评估 Policy registry、审批 authority 和 decision storage 边界。

### Supersedes

- none

## D-014｜Stabilization 的 metadata / artifact / API 最小边界

- Status: `Accepted`
- Date: 2026-09-13
### Decision
进入 Stabilization 后，Run、Evaluation、Regression、Quality Gate 与 Release Decision 的 canonical metadata 与大型/不可变 artifact 逻辑分层：metadata 只保存可查询 identity、outcome/summary、source/schema/version、stable artifact ref/hash 与必要历史关系；artifact 由独立 registry/store 保存并在 ingest/query 时验证 identity、content hash、schema 与 source identity。completed-result 首个同步边界采用受约束 HTTP/JSON manifest；同一 `(entity_type, entity_id)` 与相同 immutable fingerprint 的重复 ingest 幂等成功，不同 fingerprint 冲突并禁止覆盖；后续解释通过新 version 或 superseding reference，不能 update-in-place 改写历史。该决定不解决 TU-005 Job Transport，也不增加 release/deploy authorization。
### Why
RPF-09 的真实 Spring Boot 3.4.5 + H2 2.3.232 跨进程 probe 已验证 migration、canonical summary insert/query、artifact stable ref、事务回滚、duplicate/conflict、服务重启恢复及 missing/corrupt/unknown schema 的 fail-closed 语义；Python Runtime 可通过同步 HTTP/JSON 送入 Run、Evaluation 与 Release Decision manifest。证据支持最小逻辑边界，但尚未验证 PostgreSQL 运行/运维属性。
### Consequences
PostgreSQL 仍是正式 v1 canonical metadata 的推荐 candidate，必须由后续专门兼容性/运维 probe 验证；正式 Control Plane 可先实现 authenticated idempotent ingest、summary read model 与 append-only decision history。Web 可以从 static corpus adapter 迁移到 API DTO adapter，不应直接依赖数据库字段或把 raw artifact blob 复制进 canonical metadata。Approval authority、Policy registry、CI integration、Queue/durable execution 与 production release architecture 仍是后续边界。
### Reconsider when
PostgreSQL candidate probe、第二个真实产品场景、跨租户/权限需求或 TU-004/TU-005 的 durable/job transport 设计提供了足够新证据。

### Supersedes

- none

## D-015｜确认 PostgreSQL canonical metadata 与 scoped service authentication candidate

- Status: `Accepted`
- Date: 2026-09-13
### Decision
RunProof v1 的 canonical metadata persistence 继续采用 PostgreSQL-compatible 方向；RPF-10 在真实 PostgreSQL 16.15 candidate 上确认 RPF-09 的 migration、canonical identity、immutable artifact ref、transaction rollback、idempotency/conflict、并发 race、restart 与最小 backup/restore 合同可行。Control Plane 的首个 service-to-service authentication boundary 使用仅由环境/临时运行配置提供的 Bearer credential，并至少分离 `metadata:read`、`evidence:write`、`decision:write` 与不受信 Agent 的观察身份；该决定不引入用户登录、OAuth/OIDC/SSO 或完整 RBAC。
### Why
真实 PostgreSQL 执行获得了 PostgreSQL-specific schema、约束、数据库重启、独立 restore database 与 storage failure 证据，避免把 H2 行为当成 PostgreSQL 事实。四类 principal 的实际 HTTP 负向测试证明未认证、无权限、invalid evidence 与 identity conflict 可以保持稳定区分，且 Agent/runtime 无法自授 `Release Decision` authority。
### Consequences
正式 Control Plane persistence 可以围绕 PostgreSQL migration、canonical summary、immutable artifact registry、authenticated synchronous HTTP/JSON ingest/read 与 append-only history 施工；数据库不可用返回 retriable platform error，identity/content 或 idempotency conflict 不盲重试，invalid evidence 不计为 Agent FAIL。Bearer secret 不进入 metadata、artifact、API response、audit identity 或普通日志。该 candidate 仍不证明 production HA、replication、性能、retention、backup policy 或 durable execution。
### Reconsider when
生产运维/HA、跨租户身份模型、完整 Approval/用户权限、第二个真实产品场景或 TU-004/TU-005 的 durable/job transport 证据改变当前边界时重新评估。

### Supersedes

- none（继承 D-008、D-013、D-014，不构成替代）

## D-016｜Release Decision 采用受信任的外部 decision writer 登记边界

- Status: `Accepted`
- Date: 2026-09-13
### Decision
首个正式 Control Plane implementation 采用 Candidate B：当前 Python `quality.py` 或等价的受信任 deterministic quality component 生成已绑定 Evaluation/Comparison/Policy evidence 的 Decision manifest；独立 `decision:write` principal 仅负责向 Control Plane 登记、校验和保留 Release Decision history。普通 evidence-ingest principal、被测 Agent/runtime 与未来 CI principal 不得创建 canonical Release Decision；Approval authority 仍与 decision writer 分离，`ELIGIBLE` 不授予 deploy/release 权限。
### Why
该边界复用已验证的确定性 Quality Policy 逻辑，保持 D-013 的 decision-only 语义，并把 decision registration、evidence reference validation、idempotency/conflict 与 audit 集中在 Control Plane。Candidate A 的 Control Plane-owned evaluator 具有更强集中性，但会更早把 Python evaluator 迁移/耦合进 Java service；当前没有足够证据证明这项耦合值得扩大 Spike 范围。
### Consequences
后续实现需要单独保护和审计 `decision:write` credential，验证 Decision manifest 的 evidence refs、identity、policy/gate compatibility、immutable/superseding history，并为 CI 暴露只读结果与 evidence ingest contract；不得提供 release/deploy endpoint。若未来需要服务端执行 Quality Policy 或统一审批编排，再基于新证据复评 Candidate A。
### Reconsider when
需要服务端统一执行跨 Suite Policy、外部 decision writer 无法保持独立可信、Approval workflow 与 Control Plane 合并，或第二个真实产品场景证明当前 ownership 不足时重新评估。

### Supersedes

- none（继承 D-013、D-014，不构成替代）

## D-017｜Durable execution 使用 fenced PostgreSQL job state 与 reconcile-before-retry

- Status: `Accepted`
- Date: 2026-09-13
### Decision
下一正式 durable execution implementation 采用 PostgreSQL-backed mutable execution state、worker poll/claim/lease/heartbeat、append-only attempt/event history，以及与 execution 分层的 immutable Run/Evaluation evidence。delivery 按 at-least-once 处理；每次 re-claim 创建新 `attempt_id`，owner mutation 必须通过 `job_id`、`attempt_id`、`worker_id`、lease token/version fencing。所有 state-changing operation 保持稳定 `operation_id`；`UNKNOWN_OUTCOME`、`IN_FLIGHT` 或无法证明未发送的 operation 必须先按 environment/receipt reconcile，再决定 retry。该决定是下一正式实现方向，不宣称 production HA、exactly-once、scheduler 或 broker 已实现。
### Why
RPF-13 在真实 PostgreSQL 16.15 candidate 上验证了 durable submit/replay、并发 claim 单 owner、heartbeat/version fencing、lease expiry safe reclaim、stale finalize rejection、跨 worker process 的 response-lost → `UNKNOWN_OUTCOME` → receipt reconcile、effect count 保持 1、immutable evidence replay、数据库/服务重启读回与 platform failure 分界。证据也证明 lease expiry 不是 side effect 未发生的证明。
### Consequences
正式 Control Plane 需要将 job/attempt/operation/evidence 分表或分域，保持 D-009 的 Agent FAIL 与 Platform ERROR/INCONCLUSIVE 分离；worker 只拥有执行/报告权限，不拥有 Release Decision、Approval 或 deploy/release authority。无法证明安全恢复的 execution 必须停在 `RECONCILE_REQUIRED` 或 `INCONCLUSIVE`，不能静默 whole-run retry。
### Reconsider when
真实吞吐/延迟、延迟投递、fan-out、跨服务背压、multi-region 或 broker-specific operational evidence 表明 PostgreSQL poll/claim 不再满足需要，或第二个真实产品场景改变 execution identity/retention 边界。

### Supersedes

- none（细化 D-008、D-014、D-015 的后续 durable execution 边界，不修改其既有语义）

## D-018｜Evaluation Job Transport 首选 PostgreSQL poll/claim，broker 延后

- Status: `Accepted`
- Date: 2026-09-13
### Decision
在当前 v1 scale 与已验证 failure semantics 下，下一份正式 Plan 首先实现 `POSTGRESQL_POLL_CLAIM_LEASE`：PostgreSQL 承担 canonical execution coordination，worker 通过 poll/claim/lease 获取工作。独立 broker/queue 作为 Candidate B 保留，不因 at-least-once delivery 或组件推荐而预先引入；broker 不提供 side-effect exactly-once 的替代证明。
### Why
RPF-13 的 Candidate A 是可重复的真实 PostgreSQL candidate，已覆盖 duplicate delivery、claim race、lease/retry、crash recovery、`UNKNOWN_OUTCOME` reconcile、CI/local reproducibility 与 operator read model；Candidate B 未被当前证据证明为必要，增加 broker 会扩大运维和故障边界而不自动解决 operation identity。
### Consequences
后续正式实现必须保留明确的 worker/CI submit-poll/read API、capacity/observability measurement、safe retry/reconcile 与 retention 设计，并以 measured trigger 决定是否开展 broker migration。该决定不引入 scheduler、autoscaling、multi-region、production HA 或 deploy/release endpoint。
### Reconsider when
出现经测量的吞吐/延迟瓶颈、需要独立 backpressure/fan-out/delayed delivery、跨进程 transport 的运维需求，或 Postgres candidate 在真实工作负载下无法满足 durable execution contract。

### Supersedes

- none（承接 D-014、D-015；不替代 D-016 的 decision-writer authority）

## D-019｜正式 durable path 分离 submitter、worker 与 decision writer

- Status: `Accepted`
- Date: 2026-09-13
### Decision
正式 durable execution 采用最小 scoped service principal：CI/submitter 只能 submit、read 和登记 evidence；durable worker 只能 poll、claim、heartbeat、reconcile、登记 execution evidence 与 terminalize；独立 decision writer 才能登记 Release Decision。RPF-12 的正式 durable path 失败时不得静默回退到同进程 direct Evaluation；`ELIGIBLE` 仍不构成 deploy/release authorization。
### Why
RPF-14 将 RPF-13 的 PostgreSQL poll/claim/lease、operation reconcile 和 immutable execution evidence 落入正式 Control Plane，并以真实独立 worker process 运行 Baseline/Candidate。明确 principal 与 fallback 边界可以避免 worker 越权写 Decision，也避免 durable transport 故障被 direct path 掩盖而产生不完整的审计证据。
### Consequences
正式 API 必须保留 `execution:submit` 与 `execution:worker` 的可验证分离，worker credential 不包含 `decision:write`；CI 必须通过 Job submit/poll/read 获得 Evaluation，canonical Release Decision read-back 仍由现有独立 decision writer 产生。当前不引入用户登录、OAuth/OIDC/SSO、tenant/RBAC、Approval、scheduler、broker 或 release/deploy endpoint。
### Reconsider when
真实容量/拓扑、跨租户身份或 Approval/release 集成需要更细的 principal、scheduler 或独立 transport，并有新的运维与安全证据支持迁移时重新评估。

### Supersedes

- none（细化 D-015～D-018 的正式 execution authority，不替代既有 durable state/reconcile 语义）

## D-020｜Production 目标采用 managed persistence/stateless，并保持显式 Release 边界

- Status: `Accepted`
- Date: `2026-09-14`
### Decision
RPF-15 的首个真实 Production 目标采用 Candidate B：stateless Web/Control Plane/Worker、managed PostgreSQL、S3-compatible object storage、platform-managed secrets，以及由 CI 产出证据、由受信任的人类/产品 Release principal 显式推进的 release 流程。Candidate A（单主机、容器化、PostgreSQL named volume、本地 immutable artifact path）保留为受控的本地 production-like reproduction profile 和恢复演练环境，不作为真实 Production 的 durability/HA 结论。Agent、worker、decision writer 与 `ELIGIBLE` Decision 均不能触发 deploy/release；本决定不授权真实 Production deploy/release。
### Why
RPF-15 的 Candidate A probe 在本机真实 Docker/PostgreSQL 环境通过 21 项检查：Web/Control Plane/Worker replacement、PostgreSQL named-volume replacement、custom-format `pg_dump` 与独立 `pg_restore`、artifact 独立备份恢复、active job 的 lease/reclaim/reconcile、migration/application rollback、release identity、secret rotation 与 authority/readiness 边界均保持可读回和 fail-closed。证据同时确认本地 artifact path 存在 host-loss 风险。Candidate B 的 provider、IAM、retention、restore SLA 与成本尚未执行，因为目标 provider/region/授权尚未确定；因此 Candidate B 是经证据约束的目标推荐，不是已完成的云端 Production 证明。
### Consequences
后续 Production implementation Plan 必须先明确 provider/region、managed PostgreSQL、object storage、secret manager、Product Release Identity registry、用户身份与 Approval authority、backup retention/restore SLA、rollout/rollback、capacity/backpressure 与 observability；main push 继续只产生 CI/evidence，真实 release/deploy 需要独立、可审计的显式 principal。Candidate A 的本地 artifact 必须保留 off-host backup/restore rehearsal；在新的吞吐、拓扑或故障证据出现前，不因该结论引入 broker、scheduler、autoscaling 或 HA。
### Reconsider when
目标 provider/region、租户/身份模型、恢复 SLA、容量/延迟或真实 Production side-effect 证据发生变化，或 managed persistence 的成本、IAM、restore 与 rollout 证据不能满足产品边界时重新评估。

### Supersedes

- none（细化 D-014、D-015、D-018、D-019 的 Production boundary，不改变 durable state/reconcile 或 decision-only 语义）

## D-021｜第二真实 Agent 采用显式窄 Integration Contract，Incident Remediation 保持独立证据域

- Status: `Accepted`
- Date: 2026-09-14
### Decision
RPF-16 接入第二个真实产品 Agent：`Incident Remediation Agent`。它与既有 `Production Change Agent` 共享的边界仅为窄的、显式 versioned `rpf-agent-integration-contract-v1`：Agent identity/domain/type、Scenario、Tool、Environment、Verifier、supported execution profile 与 evidence schema compatibility。两个 Agent 保持独立的 profile、scenario、Failure Case/Regression、Evaluation Suite、Quality Policy 与 evidence identity；registry 只允许 reviewed adapters，不支持 plugin、marketplace、SDK 或 dynamic loading。

Incident Remediation 的 mutation 只能发生在受控、fresh-per-run simulation，并且必须先观察 service health、dependency/change evidence；external dependency fault 只能 safe stop/escalate，不得执行 harmful local remediation；local remediation 最多一次，response-lost 必须 `UNKNOWN_OUTCOME` → reconcile → recovery verification。Agent、worker 与 decision writer 均不获得 Release/Deploy authority。
### Why
第二个真实 domain 能验证 Reliability contract 是否跨 Agent 复用，同时避免把不同的故障语义压进 Production Change 的名称或分支。RPF-16 的 known-bad symptom-driven path 产生真实 Agent `FAIL` 与 harmful external side effect 证据，fixed Candidate 在相同 Scenario/Regression 下区分 dependency、执行 bounded action 或 safe stop，并通过独立三成员 Suite 与正式 durable worker 验证了跨 Agent 证据链。
### Consequences
Web 提供 `/agents` 与 `/agents/:agentId` 只读 registry/detail；既有 Run、Failure、Regression、Evaluation、Comparison 与 Decision surface 必须显示 Agent identity/domain。Incident reviewed corpus 绑定独立 source identity；Baseline Gate/Decision 为 `BLOCKED`，fixed Candidate 为 `ELIGIBLE`，但仍是 decision-only。正式 durable worker 只执行 explicit suite/profile，不能通过 payload 动态加载任意 Agent。
### Reconsider when
出现第三个真实 Agent、跨 domain 的通用 Policy/Scenario 复用需求、需要 plugin/marketplace/dynamic loading，或真实 Production remediation、用户身份/Approval 与多租户权限要求扩大 authority boundary 时，基于新证据重新评估该窄 contract。

### Supersedes

- none（承接并细化 D-009、D-013、D-017～D-020；不替代既有 Agent/Run/Evaluation/Release 与 durable reconcile 语义）

## D-022｜Failure Intelligence 采用确定性归因、结构族与 fail-closed 版本定位

- Status: `Accepted`
- Date: 2026-09-14
### Decision
RPF-17 的 Failure Intelligence 采用纯确定性、可重放的 `rpf-failure-intelligence-v1` derivation：保留既有 `failure_signature()` 作为 exact identity，不改写历史 Failure Case/Run bytes；在独立字段中记录责任归因（`AGENT`、`PROVIDER`、`ENVIRONMENT`、`PLATFORM`、`INVALID_INPUT`、`UNKNOWN`）、Agent failure class、first meaningful divergence、domain family 与 cross-Agent structural family。exact duplicate 与 structural recurrence 必须分开建模，使用 `rpf-failure-cluster-v1`；跨版本定位使用 `rpf-version-bisect-v1`，对非单调结果、兼容性错误和缺失 evidence fail closed。Recommendation 只能输出 `NOT_AGENT_FAILURE`、`ALREADY_COVERED`、`PROMOTE_CANDIDATE`、`COLLECT_MORE_EVIDENCE` 或 `NO_SAFE_ACTION`，不自动晋升 Regression、改变 canonical evidence 或触发 release/deploy。
### Why
RPF-17 的 Production Change 与 Incident Remediation 语料证明：相同结构性失败可跨 Agent 共享调查族，同时必须保留 domain/exact identity 的差异；历史 Failure Case signature 与新派生结果可以兼容共存。确定性字段、稳定 ID、source/reproduction/stability refs 与 evidence packet 使聚类和版本定位可审计、可重放，并避免把相似字符串或一次失败直接误报为同一缺陷。negative controls 证明 Provider/Environment/Invalid Input 不会被归因为 Agent failure。
### Consequences
Failure Intelligence、Cluster、Version Bisect 作为现有 Control Plane immutable artifact/metadata registry 的新 artifact kinds 登记，通过既有 authenticated HTTP/JSON read API 暴露；不新增数据库表、LLM、embedding、ML、第三 Agent 或自动 promotion。Web 只读显示 Facts、Verified、Derived、Inference、AI Analysis 分层，明确标注结构族与 exact grouping；非单调 bisect 保持 `ERROR`/`INCOMPATIBLE`/`NO_SAFE_ACTION`，不得盲目选版本。统计显著性、大规模聚类和真实 Production remediation 仍需新语料与新 Plan。
### Reconsider when
真实 Failure corpus 的规模、跨 Agent domain 数量、聚类误合并率、版本发布拓扑或调查延迟证明 deterministic structural features 不足，需要新的统计/语义方法，并且有可审计的解释性、回放与安全边界证据时重新评估。

### Supersedes

- none（承接并细化 D-009、D-013、D-021；不替代既有 Failure Case exact signature、Regression promotion 或 Release Decision authority 语义）

## D-023｜统计 Reliability 采用 additive sampling、Wilson 区间与 fail-closed Flaky Gate

- Status: `Accepted`
- Date: 2026-09-15
### Decision
RPF-18 在 deterministic Evaluation/Quality 旁新增独立的 `rpf-statistical-sampling-plan-v1`、`rpf-statistical-evaluation-v1` 与 `rpf-statistical-comparison-v1` 合同，并以独立 Statistical Policy/Gate/Decision 表达 repeated-trial reliability。Sampling Plan 冻结 trial 数、最大 attempt budget、fresh-per-trial、Agent/config、Scenario、controlled sequence、95% Wilson score method/version 与 metrics。`AGENT_PASS + AGENT_FAIL` 是 Agent quality denominator；Platform/Environment、Invalid、Inconclusive、Cancelled 保留在 attempted/evidence denominator 与 trial matrix 中但不进入 Agent denominator。低于 minimum valid sample 只能 `INCONCLUSIVE`，不能用 1/1 或 3/3 通过。

统计 Gate 遵循 D-013 的 `HARD_BLOCKER → EVIDENCE_INSUFFICIENT → REVIEW_REQUIRED → ELIGIBLE` precedence。Historical Regression FAIL、zero-tolerance safety event、authority violation、harmful remediation、blind retry after `UNKNOWN_OUTCOME` 保持 hard blocker；`OBSERVED_FLAKY` 只产生 review observation，不被解释为 live failure probability。比较必须基于兼容 Plan、证据充分性与区间关系输出 `IMPROVED`、`REGRESSED`、`NO_CLEAR_DIFFERENCE` 或 `INCOMPARABLE`，不能只看 point estimate。任何 `ELIGIBLE` 仍是 decision-only，不授权 release/deploy。

RPF-18 controlled corpus 使用现有 Incident Remediation Agent domain 的 deterministic sequence，不调用 Provider、不声称 live probability；正式多 trial 路径复用既有 PostgreSQL durable Job/Attempt/Operation/Evidence 与 worker，每个 Trial 独立 Job/Run/environment，replay 不增加样本计数，Platform attempts 不冒充 Agent trials。RPF-17 Failure Intelligence 是每个 Agent FAIL 的 deterministic derived linkage；统计 artifact 不新增数据库表。
### Why
小规模 deterministic Evaluation 只能证明合同和当前样本，不能证明 repeated reliability、evidence-poor 或 observed flaky 的边界。RPF-18 的 Stable Good、Flaky Reliability、High Pass + Safety Flake 与 Evidence-poor/Platform noisy cohorts 验证了 denominator separation、Wilson edge/small-sample semantics、interval-aware comparison、safety precedence 与 fail-closed decision。真实 PostgreSQL durable run 证明 20 个 Trial Job 的 claim/terminal/read-back、attempt identity、artifact replay 与 cleanup 边界。
### Consequences
Web 只读提供 Statistical Evaluation trial matrix/drilldown、Comparison、Gate/Decision reason 与 Facts/Verified/Derived/Inference/AI boundary；CI 只校验 reviewed statistical corpus，不把 controlled cohort 当 live provider probability。未来要引入 live stochastic cohort、Bayesian/p-value/adaptive sampling、ML/embedding、第三 Agent、broker/scheduler/HA 或 automatic promotion/release，必须有新 Plan、新授权和新证据；当前不引入这些范围。
### Reconsider when
真实 provider cohort、样本规模、成本/延迟、跨 Agent family 或 production capacity 证据显示 fixed sampling/Wilson/controlled corpus 不再足够，且有可审计的新统计方法、retention、身份与安全边界可验证时重新评估。

### Supersedes

- none（承接 D-013、D-021、D-022；不修改既有 deterministic Evaluation、Release Decision、Failure Intelligence 或 durable reconcile 语义）

## D-024｜Control Plane Web 采用 presentation-only 中英双语 locale 合同

- Status: `Accepted`
- Date: 2026-09-17
### Decision
RPF-25 的产品级 i18n 只覆盖 Desktop Web presentation layer，正式支持 `en-US` 与 `zh-CN`。首次 locale 解析为浏览器语言 `zh*` → `zh-CN`、其他或不支持语言 → `en-US`；用户显式选择写入本地持久化并覆盖浏览器推断。语言切换必须是当前页面内的低摩擦展示切换，不改变 route、entity、scroll、canonical API、Control Plane metadata、raw JSON/schema/enum、ID、hash、command、error code 或 evidence bytes。`Agent`、`Run`、`Regression`、`Evidence`、`Control Plane`、状态 enum 与其他 reliability contract 术语保持 English/raw 可追溯；纯 UI copy 翻译，状态同时展示 raw enum 与 locale explanation。
### Why
RPF-24 已建立 API-backed canonical snapshot、feature ownership 与 read-only evidence surface；双语需求属于人机展示契约，不应把语言状态写入 canonical data 或让翻译层改变审计身份。集中字典、terminology map、locale formatter、persisted selection、completeness test 与 pseudo expansion harness 能在不改变 backend/schema/reviewed corpus 的前提下覆盖 Golden Demo、调查面与 legacy read-only surface。
### Consequences
Web 必须集中管理 locale/provider、semantic message keys、technical vocabulary、date/number/percent/duration formatter、status accessibility label 与 missing-key/key-symmetry checks；API unavailable、not-found、raw JSON、expert escape hatch 与 deep links 也必须在两个 locale 下 fail closed 且保持可读。RPF-25 不引入第三 locale、backend/API locale negotiation、public docs translation、mobile/PWA 或 release/deploy 能力；legacy surface 的兼容文案桥只能作用于 presentation text，不能触碰 identifiers、enums、mono evidence 或 raw payload。
### Reconsider when
需要新的受支持 locale、服务端用户偏好/tenant locale、公共文档本地化、SSR/SEO、Mobile/PWA 或 locale-sensitive canonical/report export 时，先以新 Plan 与新的产品/数据边界证据重新评估。

### Supersedes

- none（细化 D-014、D-021、D-023 的只读 Web 展示边界，不改变 canonical evidence、统计、Agent authority 或 durable execution 语义）
