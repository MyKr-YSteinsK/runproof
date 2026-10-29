> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

> **保全说明：** 以下原批准合同全文保留。原文2026-10-22“迁移说明”及RPF65待规划等状态句仅为HISTORY_2026_10_22；其中产品要求/决定继续为TARGET INTENT。当前事实只以新版10/14为准，不将历史迁移说明当新执行指令。

# DECISIONS｜RunProof EffectWitness 增量决策账本

> **2026-10-22 迁移说明：** 下文所有 `D-COMP-*` / `COMP-03` 保留原有用户批准身份，不自动新增一个 `D-COMP-07`，也不覆盖仓库 `D-*`。新的执行阶段决策（RPF-64 Accepted、RPF-65 待规划、下一期泛化路线）详见 [11-RPF65_ROADMAP_AND_DECISION_GATE.md](11-RPF65_ROADMAP_AND_DECISION_GATE.md)。


> 本文件记录孵化期间用户已经确认的竞赛项目决定；不是覆盖原仓库 `docs/project/DECISIONS.md` 的新版 canonical 决策文件。正式写入仓库时须核对版本、保留历史决定 ID，并由获授权 Plan 有界合并。本账本的 `D-COMP-*` 为**孵化讨论身份**，不擅自占用原仓库 `D-###` 编号。

## 已确认的决定

### D-COMP-01｜自主诊断 + 可信改进验证的总体方向
- **Status:** `ACCEPTED`（用户确认过推荐 C 方案）。
- **Decision:** 竞赛作品需要真实 Agent 行动能力，不只是原 RunProof 文档/静态 Demo；系统应调查失败，提出改进方向，并由独立程序验证。
- **演进说明：** 后续 D-COMP-04 将主要突破收窄到“主动发现工具副作用错误与可靠失败见证”；通用自动改代码降为辅助/SHOULD，而不是丢弃可信改进愿景。
- **Reconsider when:** 首轮运行证据显示核心方向不可实现或更有价值的替代主张出现；重大范围调整需用户批准。

### COMP-03｜竞赛提交前最小必要 LLM 评测预算
- **Status:** `ACCEPTED`（用户明确要求）。
- **Decision:** 大幅减少标准完整 LLM 闭环实验；优先少量高信息量真实运行、复用确定性测试与 Reviewed Evidence，不开展大规模模型性能试验。
- **Consequence:** 规划目标约 3–4 种验证目的、约 12–30 次 Provider 调用软预算（具体调用由实际框架验证并受每任务预算控制）；不声明统计显著优势。确定性合同/证据测试不可因此取消。
- **Reconsider when:** 核心功能的真实性仍未证实或运行异常需要额外最小复现，记录增量成本和目的；不要默认放宽为无限调用。

### D-COMP-04｜EffectWitness 为核心参赛定位
- **Status:** `ACCEPTED`。
- **Decision:** 以业务副作用安全、Agent 可观察信息、权威业务状态和可复现失败见证为核心价值；普通 Coding Agent 自动修复能力为辅助。
- **Why:** Codex + Skill 已能执行代码审查/修复/测试；成熟 Eval、Fault Injection、Effect Contract 产品覆盖广。需在真实状态后果与证据约束上做深。
- **Consequence:** 不把 Trace 仪表盘、MCP 包装、普通故障注入宣称原创突破；应给出与 Agent Crash Test、AgentCheck、现有 Eval 工具可检验的差别。
- **Reconsider when:** 强对照证据显示选择的细分机制无独立使用价值。

### D-COMP-05｜双领域验证与跨领域合同
- **Status:** `ACCEPTED`。
- **Decision:** 先覆盖 **订单/退款**、**运维/配置变更**；首领域突出直观真实副作用，第二领域复用原 RunProof 运维底座；Coding Agent 作为 FUTURE。
- **Consequence:** 不允许用两套完全独立的脚本宣称泛用性。复用体现在共享实验预算、反馈、见证与验证接口；允许必要领域 Adapter/Verifier。
- **Reconsider when:** 首领域确实不可合法、可重置地验证时，需用户批准替代领域。

### D-COMP-06｜四项正式核心技术方案
- **Status:** `ACCEPTED`（用户明确批准四项）。
- **Decision A:** 以 **Proof-Guided Exploration** 为主要新增 Agent 能力，根据真实证据选择下一次有限实验。
- **Decision B:** 采用三份合同：**Agent Execution / Effect / Experiment**，领域能力通过有界 Adapter/Contract 表达。
- **Decision C:** 形成结构化 **Witness Certificate** 和不依赖 LLM 的独立 Verifier，业务结果、故障触发、归因和重现分开表达。
- **Decision D:** 优先采用受限 Experiment Orchestrator 接入既有 RunProof；是否扩展正式 Durable Worker 由源码/Spike 事实决定。
- **Why:** 突出可检验的 Agent 决策增量，保留已验证平台的安全与证据合同，减少实施与 Provider 成本。
- **Consequence:** 算法评分公式、具体 SDK 版本、Gateway/Orchestrator 进程拓扑并未冻结，遵循调查证据决定。
- **Reconsider when:** 工作流无法获得权威状态，或者现有 Worker 扩展确实比旁路 Orchestrator 更安全/低成本，并有记录支持。

## 尚未单独批准的候选／拒绝方向

- `D-COMP-02` 曾讨论从通用 Agent Doctor 转向自主故障探索；该提案已被 D-COMP-04/06 **细化替代**，不是一个额外必须建设的独立产品。
- 自动生成修复、Witness 最小化、第三领域、复杂反事实归因、模型自动升级均是 `SHOULD / FUTURE`，不得无授权提升为本期 MUST。
- 大规模 LLM Benchmark、真实生产破坏性 Tool、自造通用 Agent 框架、以 LLM Judge 替代权威状态为 `NON-GOAL`。

## 与原 RunProof 决策/约束的交叉兼容

下列仓库有效决定需持续保护（以运行时真实 `DECISIONS.md` 为准）：

- `D-001` Reliability & Release Engineering 定位；本竞赛仅为增量切片，不自动更名原产品。
- `D-002` Reference-Agent-first 泛用路线：本次以第二业务域/外部 Agent 接口检验可泛化性，不强制抽象完整 Framework。
- `D-004` 既有 DeepSeek Provider 首选：仍可默认 Flash，但接口/能力与模型现价须在实际环境核验。
- `D-005` 核心事实由确定性 Verifier 判定；`D-006` 仅受控仿真高风险 Tool；`D-007` Desktop Web 体验核心。
- `D-009` Agent FAIL 与 Platform ERROR 分离；`D-010` Fact/Result/Inference/AI Analysis 分层；`D-011` 失败进入 Regression 需通过验证门槛。
- `D-013` 或当前有效后续决定：Release Policy precedence，`ELIGIBLE` 不具有 deploy/release authority。

**冲突处理：** 保留旧决定历史和理由；先核对冲突是否只是实现快照过时，再查当期任务权限。涉及重要目标改变由 Main 提议、用户批准；仅需技术路线选择的任务内决定可按 Plan 授权交给 Codex。不得把孵化器附件直接覆盖原仓库同名文件。
