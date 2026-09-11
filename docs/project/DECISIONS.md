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
