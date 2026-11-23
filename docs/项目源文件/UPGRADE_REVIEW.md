# RunProof 升级评审

**状态 `FROZEN_PROPOSAL / PENDING_USER_REVIEW`。** 2026-11-23 基于 `main@b076d2c4206683ba96eb8ffc6ae2cd290074af0c` 审查。已确认的是作品集与实际使用并重。本轮已落地的维护变更见 [CURRENT_STATE](../project/CURRENT_STATE.md)。下文的产品定位、技术选型、联动和退役顺序均为候选。

## 1. 产品目标

推荐把 RunProof 的第一句话收敛为 **一个能在受控配置环境中调查、执行并验证变更的 Agent**。使用者是需要判断「工具超时后究竟改没改，能不能继续」的后端维护者、Agent 开发者和评测工程师。实际价值是给危险的歧义提供可查的决策依据。作品价值来自四种能当面展示的工程行为：

1. Agent 根据目标、现有版本、变更约束和批准状态选择工具，遇到版本冲突重新读状态，遇到不可确认结果停在人工复核。
2. 在本地可重置的真实服务上发生一个可以观察和验证的状态变化。目标服务独立保存配置版本和变更历史，Verifier 从只读路径核对业务状态。
3. 同一个任务故意丢掉响应时，观众能看到工具超时与最终配置状态的差异，证明有无重复写。策略好坏由独立对照评测量化。
4. 面试者能拿着一个运行 ID 读到工具调用、人工批准、故障、状态差异和结论，并能用 CLI 复核导出的证据。

最短演示是「读取一个配置键 → 提出受限变更 → 人确认 → 写成功后响应丢失 → 权威读回 → 确认只生效一次 → 形成可复跑的回归案例」。配置 Agent 是切入点。既有 RunProof 平台提供可复用的评估和调查语义，EffectWitness 提供侧重副作用的验证机制及失败控制。两个旧演示继续可追溯，是否作为发布期兼容入口由路线评审确定。

这条路线应有清晰的差异和验收。LangSmith 已有离线评估、版本对比和代码型 evaluator，能复用时无需自研通用 Eval 平台。LangGraph 提供检查点和 durable execution；官方建议对副作用操作注意确定性及幂等性。RunProof 的评审增量应体现在独立业务读回、动作权限、可恢复状态机和工具故障的可核验业务后果。MCP 的工具 schema 适合作为接口，并由宿主承担审批。OTel 的 Agent/tool spans 适合作诊断映射，应用定义的回执和 Evidence 身份继续作为 Verifier 输入。[LangSmith 评估](https://docs.langchain.com/langsmith/evaluation-types) · [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) · [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) · [OTel GenAI instrumentation](https://opentelemetry.io/blog/2026/agent-harness-genai-instrumentation/)

## 2. 仓库审查

覆盖正式命令、部署与测试入口、主要数据和业务路径、已提交历史资产及其集成引用。下面的判断以静态源码和本次聚焦证据为基础。`spikes/` 的个别历史实验需要按自己的冻结版本复验。基线中有 978 个 `spikes/` 跟踪文件和 297 个 `runtime/runproof_runtime/effectwitness/` 跟踪文件，适合先做依赖分类，再按切片迁移。

| 优先级 / 范围 | 现状与代价 | 建议与验收 |
| --- | --- | --- |
| P0 产品入口和可复现度 | [根 README](../../README.md) 和 [Demo](../DEMO.md) 描述 Golden Demo。`demo/competition-bundle/` 又有独立 Node/Python 网关，带 `live-local`、Reference Agent 等模式。首次了解难以分辨如何运行和各自证据。 | 下一版确立一个默认命令和一个默认任务。新工作区按锁文件复现，读者从输入、独立读回到导出 Witness 完成一条连续体验。历史入口单独链接且标版本。 |
| P0 Agent/Runtime | [CLI](../../runtime/runproof_runtime/cli.py) 原路径与 [EffectWitness 模块](../../runtime/runproof_runtime/effectwitness/) 的多代实现并行。RPF-114 采用确定性参考 Agent。历史 live 尝试进入 UNCERTAIN 后尚无通过的复跑对照。 | 用单 Agent、少量 typed tool 和可替换策略完成第二条候选切片。先对同一场景跑确定性与负控，待准入再做有预算的 LLM 对照。审批、业务真值和执行由宿主决定。 |
| P0 副作用与恢复 | [CURRENT_STATE](../project/CURRENT_STATE.md) 保留 RPF-74 的 UNKNOWN 后新预约反例。研究守卫、预算 ledger、真实发送器在不同版本有不同强度的证据。 | 建立可检查的 Operation 状态机。把状态迁移、申请 ID、幂等标识、回执链接、权限和预算绑定。响应丢失后断开下一写入，单独验证并发、重放与进程中断。 |
| P0 CI 与证据可信度 | [release-gate.yml](../../.github/workflows/release-gate.yml) 普通 docs 变更也触发旧重型门禁。Router 固定每个测试输入的 SHA，coverage handoff 又绑定整个 matrix。首个接管提交曾因扩写一个已固定的测试而在生成账本前失败。真实 required coverage 持续有缺口，产品工作流分布在多个 RPF 版本。 | 建普通产品 CI、隔离环境集成和固定历史证据三类可测目标，先跑同一 candidate 的新旧交叉结果。按原因补 required 覆盖并保持失败诚实可见。涉及覆盖规则迁移、关闭旧门禁或新的发布门禁须评审。 |
| P1 Python domain / Storage | [evaluation.py](../../runtime/runproof_runtime/evaluation.py) 约 1,439 行，[statistical.py](../../runtime/runproof_runtime/statistical.py) 约 1,586 行。评估编排、读写和统计结果表达集中。历代 EffectWitness 模块与 frozen digest、fixture、动态入口存在耦合。 | 以版本化 Scenario、Operation、Evidence、Verifier result 为迁移边界。把业务 Adapter、存储、评估指标从调度拉开。对历史 evidence 用读侧 adapter，保留原生验证器及固定 SHA。 |
| P1 Java Control Plane | [DurableExecutionController](../../control-plane/src/main/java/com/runproof/controlplane/DurableExecutionController.java) 约 1,582 行，混合 HTTP、SQL 事务与任务状态迁移。[CanonicalMetadataService](../../control-plane/src/main/java/com/runproof/controlplane/CanonicalMetadataService.java) 约 1,115 行。已有 scoped auth、worker fencing 和读后仲裁。 | Java 进入下一主线的条件是多 worker、独立服务权限或可量化的真实集成需求。若沿用，先为 lease 并发、fencing、reconcile 和 append-only API 建契约再抽事务服务与 repository。既有 HTTP/DTO 客户端继续可读。 |
| P1 Web | [App.tsx](../../web/src/App.tsx) 约 1,838 行，承载主路由、调查状态及多条 EffectWitness 入口。[artifacts.ts](../../web/src/data/artifacts.ts) 约 1,460 行，规范化器和 reviewed corpus 接线同处。接管构建主 JS 约 1,429 kB，gzip 约 229 kB。 | 按运行详情、评测矩阵、已记录历史分 route，把证据 fixture 和竞赛页面按需加载。保留 stable deep link、locale、焦点与证据分层；对比首屏依赖和走通一条实际调查。 |
| P1 依赖和打包 | 基线 RPF-114 工程包有独立解压证据，builder 维护源码/静态产物清单。RPF-95 的 JiuwenSwarm 子集 `pip check` 失败。历史项目曾依赖 Git 工作树换行复现 raw JSON。 | 锁定可复建的最小跨平台包。检查依赖闭包，区分启动、调用和行为证据。从同一 SHA 构建与解压验证。保留老包 checksum 及适用的换行处理。 |
| P2 工具和观测 | [只读 MCP](../../integrations/jiuwenswarm/README.md) 证明注册后调用。[observability.py](../../runtime/runproof_runtime/observability.py) 为诊断提供已存在的接缝。 | 确定性工具接口先稳定。默认由宿主控制写权限，MCP 先暴露查询和证据，再按明确授权考虑受限写。统一 trace 与 operation 的关联和脱敏，证据从独立通道保留。 |

本次低风险实现集中于 Python Control Plane JSON/二进制请求的共享传输与非对象错误响应回退、Web 两个本地模式的共享网关。请求媒体类型、端点、模式、超时和重试协议有聚焦断言。Java、核心 Agent、历史证据格式及 CI 规则的重构留在本案。

## 3. 架构取舍

| 候选 | 结构与适用条件 | 主要风险 |
| --- | --- | --- |
| A 在现有 Java/Python/Web 上继续加功能 | 保留 durable worker、PostgreSQL 和 canonical Web API，增加 `config-center` Adapter。适合马上需要展示现存分布式耐久实现的目标。 | 继续维护两套产品路径，第一次启动和错误归因成本高。业务闭环可能被复杂拓扑掩盖。 |
| **B 平行建立单服务主切片，按验收逐步替换** | 默认 Python Agent/Controller + SQLite 运行动作日志与配置后端 adapter，真实 config-center 作独立被测目标。Verifier 保持只读策略边界，CLI/Web 共用同一可读数据。原平台与冻结证据保留逐步迁移。 | 双路径短期共存。需要明确当前权威数据、可比较指标和何时退役旧入口。SQLite 不是旧 PostgreSQL 的无损迁移承诺。 |
| C 一次性重写应用和证据模型 | 若旧证据外部依赖极少并允许归档，可创建全新包和 API，验收后再决定兼容。 | 会同时更改多项变量，旧数据回放、兼容证明和失败归因成本最高。短期容易只剩新 UI 和空基础设施。 |

推荐 B。先使用标准库或已有合适 adapter 做一个可运行对照。等到采用成熟编排框架能明显减少 checkpoint/暂停/恢复实现，并通过相同故障验收时再选框架。人机界面优先展示可复制的请求、状态、证据和下一步。扩展 Memory 需要实际跨次任务价值，先用当前任务状态与版本历史。只有第二种业务或并发运行确有需求时才把抽象推广到泛用平台。

### 候选组件与数据

```text
User Goal / Approval → Agent policy → typed intent
                                Controller → operation ledger → allowlisted tool adapter → config-center
                                Controller ← verifier result ← read-only Authority ← state / version history
                                UI / CLI ← immutable report + linked events / evidence
```

- **Agent policy** 输入任务、允许工具、当前版本、权威反馈和剩余预算。输出少量结构化意图，例如 Read、Propose、Apply、Stop。记录工具决策和观察，LLM 说明可作为派生文本。
- **Controller 与运行存储** 对意图做 schema、能力、批准、键范围、版本和预算校验。持久化 `run_id`、`operation_id`、source/version、审批身份与请求指纹，动作和回执可按 ID 对账。状态包含 `PLANNED`、`DISPATCHED`、`CONFIRMED`、`REJECTED`、`UNKNOWN_OUTCOME` 和 `REVIEW_REQUIRED`。写操作超时后冻结后续写，权威验证缺少因果绑定时停在 `REVIEW_REQUIRED`。
- **Adapter 与 Authority** 接目标服务的窄接口。写 Adapter 与独立只读 Authority 各有凭据和能力边界。根据实际服务支持决定幂等复用。正向证明动作未发生且目标端合同允许有界重试时，通过人确认或受信规则重新进入执行。
- **Evidence 与评估** 每条运行绑定任务、Agent、工具合约、目标版本、Verifier 与故障四态。事件有顺序、业务锚、脱敏内容。支持导出、错源/缺失/篡改验证和不确定传播。只有独立可查的锚才能强调来历，离线 hash 保持可复核能力。基线与候选用相同场景、数据和判定。
- **UI/CLI** 一条任务链同一 deep link，显示动作意图、审批、前后状态、故障、读回与结果。交互中断时保留恢复入口。历史 fixture 明示来源。CI 以无凭据的确定性路由先跑，真实小样本独立验收。

## 4. config-center 集成候选

已读默认分支 `master@0258b9cef02ea74a40989d035c79256c776409c0` 的 README、状态、控制器、DTO、compose 与示例。服务有 H2 本地/测试路径、MySQL/Flyway 持久化 profile、配置与 feature flag 版本/回滚、长轮询、ETag、限流、Java 客户端缓存和降级。RunProof 这轮没有启动该仓库或跨仓写入。[config-center 固定源码](https://github.com/MyKr-YSteinsK/config-center/tree/0258b9cef02ea74a40989d035c79256c776409c0) · [既有验证](https://github.com/MyKr-YSteinsK/config-center/blob/0258b9cef02ea74a40989d035c79256c776409c0/docs/project/CURRENT_STATE.md)

| 接缝 | 代码事实 | 第一版合同候选 |
| --- | --- | --- |
| 读与观测 | `ConfigController` 有 `GET /api/configs`、`/configs/{key}`、`/configs/history`、`/configs/watch`。Watch 游标表达 namespace revision。 | 每次运行固定隔离的 app/env/key。用当前 key 版本和历史核对业务动作，Watch/ETag 做观察和读优化。 |
| 批准与写 | `POST /api/configs` 经 `X-API-Key`，upsert DTO 有可选 `expectedVersion`。Feature 有单独 Controller。 | 宿主强制把批准绑定固定键、值摘要、当前版本和期限。默认先做单配置键；flag 灰度纳入第二案例前核对评价接口与读回。 |
| UNKNOWN / 回滚 | `POST /api/configs/rollback` 的 DTO 指定 `targetVersion`。版本历史能帮助查看变化，现有 HTTP DTO 未提供可供 RunProof 证明动作唯一归因的 operation receipt。 | 首版用合成隔离目标，一旦历史无法归因就停在人工复核。回滚作为新的写动作，批准并绑定版本。若需要跨重启幂等与严谨归因，再单独评审 config-center 持久的 operation ID + receipt、同时提交业务更新与回执、并发冲突和重放语义。 |

`sinceVersion` 与写入的 `expectedVersion` 属于不同版本域。客户端缓存和长轮询确认观察一致性时另做对照。Verifier 通过独立会话读取权威状态，不以 UI、缓存或工具自己的成功文本封案。业务模型采用本地合成的配置、flag、主体和作用域；用伴随场景定义正常、落后版本、有并发修改、成功后丢响应、失败前断开、批准撤回六条路径。生产写、共享真实配置以及外部凭证不进入首轮。

## 5. 里程碑、验收与迁移

| 阶段（候选） | 可交付 | 进到下一阶段的条件 |
| --- | --- | --- |
| M0 固定可对照基线 | 两条旧产品入口与来源可恢复。列出受影响 API、fixture、验证器、workflow 和历史容器。确定首个场景及数据版本。 | 现有审查索引可定位关键证据。验收可从提交复制。CI 失败以实际步骤与原因记录。 |
| M1 只读诊断 + 运行回放 | 一个配置差异任务、分析并提出有依据的计划。实现模型无关的 typed intents、可读状态与进程重启后可读的最小运行记录。 | 干净环境可跑 CLI 与一条 Web 深链，验证真实 target 读取。复制的 run 能查 source、版本与上下文。拒绝越域请求，记录缺失与不可用。 |
| M2 受控执行、UNKNOWN 与回归 | 人审、一次写、权威读回、结构化导出；同一数据集保存正常、冲突、一次提交后超时、证据不全、重放与篡改的对照。 | 各允许场景的 expected/actual 可独立核对。超时后首选只读对账；覆盖到的重放无额外业务写，冲突保留旧业务状态与证据。工作区可逐案复现，明确运行时间和失败归因。 |
| M3 小规模真实模型比较 | 在独立批准的调用预算内，对照确定性策略和一版或两版 LLM。固定数据、工具、故障、停止、评估和预算。 | 独立验收实际模型/工具调用、任务完成、违规、UNKNOWN 安全结案、异常率、成本和延迟。报告分母、不可用覆盖和抽样条件。根据结果决定是否扩展。 |
| M4 展示和主线切换 | 现场可运行 demo、一次失败的工程复盘、独立可校验 artifact、明确的 README 与架构；维护 CI、可比评估、旧入口退役清单。 | 候选路线在冷启动、业务结果、可追溯和清理边界上通过验收。冻结旧公开链接和 source identity；按用户批准逐项迁移或退役。 |

统计报告至少显示 attempted / valid / PASS / FAIL / ERROR / INVALID / INCONCLUSIVE / CANCELLED 分布、confirmed effect 和 duplicate-effect 计数、UNKNOWN 可结案与升级人工比例、P50/P95 延迟及适用样本。同一故障 seed、目标 revision、允许工具和权威读回条件用于对照。真实模型按实际供应商记录可核对的调用量、用时和费用，离线路径标对应范围。小样本保留逐例与区间解释。CI 大类门禁缺项建立清单，验证补足后再迁移。

**回退策略。** 新切片用独立命令、存储路径和 schema。旧 SQLite/PostgreSQL 数据与 frozen artifacts 保留原身份。首轮读侧兼容用静态 fixtures，迁移时验证老版本、空数据、坏数据、重复导入、中断后 resume。退役先切 README 默认入口、验证旧入口与历史链仍可定位，再由用户批准路径清单移动。本轮未执行迁移。

## 6. 提交给用户的取舍

1. 产品首选 **安全配置变更 Agent** 是否成为默认展示路径。旧平台在什么条件下继续作为主线。
2. 是否接受候选 B 的 Python 单服务与独立 config-center target，保留 Java/PostgreSQL 作既有验证路径。何时需要跨进程、PostgreSQL 或 LangGraph。
3. 竞赛双域、真实 Explorer 和 R-01～R-10 继续作为下一阶段目标，或作为历史研究线独立维护。D-COMP 的已批准历史按原范围解释。
4. 首次执行授权范围，包含合成 config-center、具体本机资源边界、后续模型预算、是否允许跨仓 PR 和产物分发。
5. 对旧 CI required coverage、证据保留与入口退役按何种证据接受。一次真实流程优先于多套静态演示。

在取舍落定后，可从 M1 发一份短、完整的 Codex 任务。验证计划包含工作区、固定 target、可写范围、验收与证据、Git 授权。作品组合、对照项目及可写进简历的范围见 [PORTFOLIO](PORTFOLIO.md)。
