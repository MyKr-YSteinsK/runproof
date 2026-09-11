# PROJECT_BRIEF

> 保存稳定产品意图、核心架构边界与长期不变量。不要写开发历史、当前任务或临时实现细节。

## Product

- Name: RunProof (`RPF`)
- Purpose: Agent Reliability & Release Engineering Platform；用可追踪证据与确定性验证支撑 Agent 可靠性判断和 Release Gate。
- Primary users: 需要评估、验证与发布 Agent 变更的工程团队、可靠性/质量角色与平台操作者。
- Primary platforms: Desktop Web Control Plane；CLI、Programmatic API、CI 作为 automation surfaces。
- Lifecycle stage: `Discovery`

## Core user loop

1. 选择 Candidate 并执行 Evaluation。
2. 在 Controlled Environment 中运行并采集 Trajectory / Evidence。
3. 用 deterministic verification 形成 Verified Result，识别 Failure / Regression，并比较 Baseline / Candidate。
4. 依据 Quality Policy 与 Release Gate 证据决定是否允许发布。

这是稳定产品闭环的定义，不代表本仓库已实现上述能力。

## Product priorities

1. Evidence first：可靠性结论必须能回到可审查的事实与证据。
2. Reference-Agent-first：先用 Production Change Agent 验证平台闭环，再扩展 Agent 范围。
3. Deterministic verification 优先，并把 Desktop Web 的视觉与信息架构质量视为正式产品要求。

## Stable architecture boundary

- Runtime: 尚未锁定；推荐方向包括 Java/Spring Boot Control Plane 与 Python Agent/Evaluation Runtime，但具体边界需经过 Spike。
- Persistence / canonical source of truth: 尚未锁定；PostgreSQL 只是推荐方向，不是已验证实现。
- Backend / external services: DeepSeek 是 v1 首个 Provider boundary；当前不接入真实 Provider 或真实生产凭据。
- Deployment: v1 destructive/live side effect 仅允许在 Controlled Production Simulation Environment；当前没有部署实现或 endpoint。
- Offline/cache model: PWA/mobile 不属于 v1；当前没有 offline/cache 合同。
- Data/privacy boundary: Provider credentials、authorization token 与其他 secrets 不进入 Git、前端源码、Scenario、默认 Trace 或普通 Evidence export。

## Stable invariants

- Evidence first。
- Agent `FAIL` 与 Platform `ERROR` 分离。
- 环境起点不可验证时不得正式 Run。
- Release Gate 证据不足不得误报可发布。
- `Observed Fact` / `Verified Result` / `Inference` / `AI Analysis` 分层。
- `UNKNOWN_OUTCOME` 先 reconcile，再决定 retry。
- Failure 经重现、验证、稳定化后才能晋升 Regression。
- Run / Release 历史事实不可静默重写。
- DeepSeek 是首个 Provider，而不是平台身份。

## Stable non-goals

- 真实 Production destructive operation 与真实生产 destructive credentials。
- PWA/mobile。
- 通用 Agent Framework / Marketplace。
- 在技术边界完成调查前锁死 Queue、Job Transport、Environment isolation、Replay、durable resume/retry 等方案。

## Canonical UX baselines

- Desktop Web 是 Primary human surface。
- 视觉层级、信息架构与可靠性证据的可审查性属于正式产品质量，而非仅为内部工具的附加项。

## Enabled optional product modules

- 当前没有已启用的可选产品模块；后续模块需由新的产品/架构决策明确。

## Update rule

只有产品定位、核心用户循环、稳定架构边界、长期不变量/non-goal 或 canonical baseline 实质变化时更新。
