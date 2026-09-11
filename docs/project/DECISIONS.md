# DECISIONS

> 只记录未来 Planner/Codex 需要知道“为什么不能随便改回去”的长期决定。普通 bug、Task 完成、commit 和临时实现细节不进入本文件。

## D-001｜主定位为 Agent Reliability & Release Engineering

- Status: `Accepted`
- Date: 2026-09-11

### Decision

RunProof 的主定位是 Agent Reliability & Release Engineering Platform，而不是通用 Agent Framework、单一 Agent 产品或普通任务编排器。

### Why

产品价值在于把 Agent 行为、证据、验证、Failure/Regression 与 Release Gate 连接成可审查的工程闭环。

### Consequences

- Benefits: 后续功能以可靠性判断和发布决策为中心，避免 scope 漂移。
- Costs / trade-offs: 通用 Agent 能力与产品功能必须服从可靠性闭环，不能先行泛化。

### Reconsider when

- 产品目标与主要用户需求被正式重新定义。

### Supersedes

- none

## D-002｜Reference-Agent-first，首个真实 Agent 为 Production Change Agent

- Status: `Accepted`
- Date: 2026-09-11

### Decision

先以 Production Change Agent 验证平台的 Evaluation、Controlled Environment、Evidence、deterministic verification 与 Release Gate 闭环，再考虑扩展 Agent 类型。

### Why

Reference-Agent-first 可以让平台在真实可靠性场景中收敛，同时避免为尚未验证的通用 Agent 抽象提前搭建大骨架。

### Consequences

- Benefits: Investigation 与 Prototype 有明确真实对象和验收路径。
- Costs / trade-offs: 早期平台抽象不会覆盖所有 Agent 形态。

### Reconsider when

- Production Change Agent 无法代表核心可靠性问题，或已有证据证明另一个 Agent 场景应成为首个 reference。

### Supersedes

- none

## D-003｜DeepSeek-first 但保持 Provider boundary

- Status: `Accepted`
- Date: 2026-09-11

### Decision

DeepSeek 是 v1 首个真实 LLM Provider；Provider 接口与平台身份分离，不能把 DeepSeek 写成平台固有身份。

### Why

需要尽早用真实 Provider 验证 Agent 场景，同时保留未来替换或增加 Provider 的边界。

### Consequences

- Benefits: 早期验证有具体依赖，平台不会被单一 Provider 永久绑定。
- Costs / trade-offs: 需要明确 credentials、调用与证据边界，不能把密钥散落在产品数据中。

### Reconsider when

- 真实 Provider 验证显示 DeepSeek 无法满足 reference scenario，或 Provider boundary 需要新的长期抽象。

### Supersedes

- none

## D-004｜Evidence-first 与 deterministic verification 优先

- Status: `Accepted`
- Date: 2026-09-11

### Decision

可靠性判断必须优先依赖可审查证据与 deterministic verification；`Observed Fact`、`Verified Result`、`Inference`、`AI Analysis` 分层保存。

### Why

仅凭模型分析或表面成功状态不足以支持 Failure、Regression 或 Release Gate；证据分层可以限制误报和不可解释结论。

### Consequences

- Benefits: 结论可复核、可审计，发布判断更稳健。
- Costs / trade-offs: 需要投入证据模型、验证器与可视化，早期实现速度可能较慢。

### Reconsider when

- 新证据证明某类可靠性结论无法通过当前 deterministic boundary 表达，且替代方案能维持可审查性。

### Supersedes

- none

## D-005｜Destructive/live side effect 仅限 Controlled Production Simulation

- Status: `Accepted`
- Date: 2026-09-11

### Decision

v1 的 destructive/live side effect 只能发生在 Controlled Production Simulation Environment；不接入真实生产 destructive credentials。

### Why

项目处于 Discovery，需要真实风险形态的验证，但尚未具备把 Agent 操作暴露给真实生产的安全与治理证据。

### Consequences

- Benefits: 可以在受控边界内调查可靠性，不把实验风险带入真实生产。
- Costs / trade-offs: simulation 与真实生产的差异必须显式记录，不能把 simulation 结果直接等同生产保证。

### Reconsider when

- 有新的正式安全、权限、审计、隔离与发布决策证明可以扩大边界。

### Supersedes

- none

## D-006｜Desktop Web 为 portfolio-critical Primary Surface

- Status: `Accepted`
- Date: 2026-09-11

### Decision

Desktop Web Control Plane 是 Primary human surface；CLI、Programmatic API、CI 是 automation surfaces，Desktop Web 的视觉与信息架构质量属于正式产品要求。

### Why

可靠性证据、Run 历史与 Release Gate 需要面向人的审查与决策；不能把 Web 仅当作内部调试面板。

### Consequences

- Benefits: 后续 UX、信息架构与证据可视化有明确优先级。
- Costs / trade-offs: UI 质量和可审查性会进入产品验收成本。

### Reconsider when

- 主要用户工作方式或产品交付形态被正式改变。

### Supersedes

- none

## D-007｜推荐 Java Control Plane + Python Agent Runtime，但暂不锁定施工方案

- Status: `Accepted`
- Date: 2026-09-11

### Decision

Java/Spring Boot Control Plane 与 Python Agent/Evaluation Runtime 作为推荐架构方向；具体通信、Queue、durable execution、environment execution model 与持久化边界必须在 Investigation / Spike 后决定。

### Why

该组合符合当前技术假设，但仓库尚无运行时、CI、部署或真实负载证据，直接脚手架化会把未知误写成事实。

### Consequences

- Benefits: 为后续调查提供方向，同时保留根据证据调整的空间。
- Costs / trade-offs: 当前不能通过创建空模块获得“架构已完成”的假象。

### Reconsider when

- Spike 证明其他边界、语言或执行模型更符合可靠性、不变量与交付约束。

### Supersedes

- none

## D-008｜运行结果、证据与历史事实不可混淆或静默改写

- Status: `Accepted`
- Date: 2026-09-11

### Decision

Agent `FAIL` 与 Platform `ERROR` 分离；环境起点不可验证时不得正式 Run；`UNKNOWN_OUTCOME` 先 reconcile 再决定 retry；Failure 只有经过重现、验证与稳定化后才能晋升 Regression；Run / Release 历史事实不可静默重写。

### Why

这些状态边界直接影响重试、回归、发布与审计判断；混淆状态会把基础设施故障误报为 Agent 行为，或把未知结果误报为成功/失败。

### Consequences

- Benefits: 失败分类与发布证据保持可解释、可追踪。
- Costs / trade-offs: 状态模型、reconcile 与历史存储需要更严格的设计。

### Reconsider when

- 新的领域证据要求更细的状态分类，但不能牺牲可追踪历史与证据分层。

### Supersedes

- none

## D-009｜导师研究方向不是项目硬约束

- Status: `Accepted`
- Date: 2026-09-11

### Decision

导师或外部研究方向可作为调查输入，但不自动成为 RunProof 的产品 scope、架构约束或实现验收条件。

### Why

项目需要以自身用户、证据与工程约束作决定，避免把背景研究误写成已确认的产品要求。

### Consequences

- Benefits: 后续决策可以回到真实产品证据和约束。
- Costs / trade-offs: 研究成果需要经过明确决策才能进入长期状态。

### Reconsider when

- 研究结果被正式纳入产品决策并形成可验证的约束。

### Supersedes

- none
