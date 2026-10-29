> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

> **保全说明：** 以下原批准合同全文保留。原文2026-10-22“迁移说明”及RPF65待规划等状态句仅为HISTORY_2026_10_22；其中产品要求/决定继续为TARGET INTENT。当前事实只以新版10/14为准，不将历史迁移说明当新执行指令。

# REQUIREMENTS｜EffectWitness 竞赛升级

> **2026-10-22 迁移说明：** R-01～R-10 仍为原批准的目标，不因个别任务未实现而删除或改写。逐项 *现有证据* 与缺口参阅 [10-CURRENT_STATE_AND_EVIDENCE.md](10-CURRENT_STATE_AND_EVIDENCE.md)，产品目标和局部工程能力不得混同。R-02 的真实反馈时序已证明，但“因果导致改变选择”未通过公平反事实证明；RPF-57 L2=true 为观察性，RPF-63 L2=false。R-10 的 PPTX/ZIP/门户提交仍未完成。


> 已批准的 `CORE / MUST` 表示当前阶段产品目标；不意味着每一个内部算法/SDK 选择都已冻结。`FROZEN / RECOMMENDED / DELEGATED_TO_CODEX` 为单份 Codex Plan 的**技术授权**，见 [07-CODEX_PLAN_SPEC.md](07-CODEX_PLAN_SPEC.md)。现有 RunProof 的可靠性要求继续生效。

## 1. 共同输入输出与身份

**输入**：业务任务与意图、目标 Agent 执行配置/工具能力（可用权限内）、三份版本化合同（Execution、Effect、Experiment）、受控环境与可用故障能力、调用/时间/成本预算、独立权威状态读取权限。

**输出**：Experiment Plan 与冻结身份、Agent 选择理由和证据引用、每次实际运行的事件/故障 planned-triggered-observed 记录、权威状态 Diff、Verifier 结果、反馈、Witness Certificate 或明确无有效见证的结果；需要时生成下一个候选实验。

身份原则：Agent Version（model/config/tool/runtime revision）、Scenario、Environment revision、Contract/Verifier version、experiment/run identity 具备可追溯引用；缺失关键身份的结果不得升级为正式可信 Evidence。LLM 的自然语言解释保持 `AI Analysis`，不覆盖 `Observed Fact` / `Verified Result`。

## 2. CORE / MUST 及验收矩阵

| ID | 能力与合同 | 最小必要可观察验收 |
|---|---|---|
| **R-01** | **真实 Exploration Agent**：实际 LLM 参与决策，经授权 API/MCP 调用 RunProof 工具；能感知工具成功/失败/超时 | 保留 Provider 真实调用/工具调用身份、输入合法参数及结果引用；不能以 Mock 冒充真实 LLM 运行；可在确定性测试使用 Mock，但标注范围 |
| **R-02** | **PGE 证据反馈探索**：有限候选空间、选择、执行、反馈、调整、停止 | 至少一次真实反馈导致不同实验选择；可展示选择前可见的证据，不喂答案；预算/环境故障会安全停止；无有效发现允许诚实收口 |
| **R-03** | **三份合同**：Execution（驱动被测 Agent）、Effect（业务安全目标与权威状态）、Experiment（故障/环境/预算） | 版本化、schema 校验、明确领域字段边界；真实两域使用同一核心接口；非法/缺失关键字段拒绝或 INCONCLUSIVE |
| **R-04** | **独立业务验证**：状态、收据、可观察副作用、禁止状态和业务不变量 | 同一故障运行中，Verifier 独立检查 expected/actual；LLM 不能改变冻结合同或 Verifier 结果；可区分真实违规与业务已满足 |
| **R-05** | **结构化 Witness**：包含真实实验依据而非仅 AI 文本报告 | 持有 Agent/contract/environment/verifier/run 身份、故障触发、事件顺序、权威状态、规则违反、证据引用、适用界限及复现状态；原始证据不可静默改写 |
| **R-06** | **确定性 Witness Verifier**：无 LLM 复核证据有效性 | 独立离线/本地命令检查身份、hash、schema、源引用、合同判定；篡改、缺失、错配均被拒绝；只做可支持的结论 |
| **R-07** | **跨领域核心复用**：订单/退款与运维/配置变更 | 第二域无需重写通用任务预算、反馈、Witness 校验逻辑；列出核心公共代码与领域特定 Adapter/Verifier 的清单并完成各一例实际测试 |
| **R-08** | **实时 EffectWitness Lab**：可理解、可操作、可追溯 | 用户能提交受控任务、查看 Agent 决策和实验状态、识别有效/无效/未知、打开原 Run/Timeline/State Diff/Witness；只读旧 UI 不被静默破坏；演示数据标识清晰 |
| **R-09** | **可靠性与权限安全**：保留既有 RunProof 契约 | UNKNOWN_OUTCOME 先 reconcile，再决定 retry；Agent/Worker/decision authority 分离；未验证源/不存在 artifact fail closed；禁止真实生产破坏性 Tool；预算限制有效 |
| **R-10** | **可提交的比赛作品**：真实 Demo、短视频、材料与事实清单 | 作品名称/简介/业务场景/技术方案/项目文档；视频 ≤3 分钟；运行证据可回到源码和实际 Run；未实现功能明确不宣传为已完成 |

**最低闭环**：① 受测 Agent 的真实操作；② 探索 Agent 真实选择实验；③ 注入故障与权威状态；④ Evidence Feedback；⑤ 至少一轮因反馈改变选择；⑥ 结构化 Witness 或明确证据不足；⑦ 非 LLM 验证与结果展示。`R-08` 的页面必须展示真实运行事实，不能以固定 JSON、文字叙述替代链路。

## 3. 合同语义与边界

### Agent Execution Contract

应定义：驱动协议/版本、受测 Agent identity、可用 Tool 能力、输入上下文、可观察事件边界、调用预算、超时/取消、重试边界、权限范围。既有两个 Profile **不能自动证明第三方框架兼容**；应优先建立一个真正外部 Agent 接入切片。支持 `MANAGED`（可重置/可观测环境）与 `EXTERNAL_EVIDENCE_ONLY`（只导入 Trace）的不同证据等级；后者不得取得同等状态可信等级。

### Effect Contract

由场景定义者**执行前冻结**任务正确条件、禁止状态、前提关系、时序/副作用不变量、权威读源和版本。例：`refund_count(order) <= 1`、退款前须符合订单状态条件；领域规则需与实际沙箱语义一致。模型只能建议测试目标，不能动态改写规则来影响结果。

### Experiment Contract

定义可用 fault 类型与触发阶段、合法参数和不允许的组合、环境初始/恢复条件、状态读回、目标 Agent 执行预算、exploration 预算、Identity 与 cleanup/quarantine。故障 `planned / triggered / observed` 严格区分；未触发不能报有效 PASS，更不能报已触发故障下 Agent 无异常。

## 4. Witness 结果分维度（候选 schema）

一份 Witness 的多个维度**相互独立**，不替换 RunProof 原 Run Outcome / Quality Decision：

| 维度 | 推荐枚举 | 语义 |
|---|---|---|
| Contract Outcome | `VIOLATION_CONFIRMED / CONTRACT_SATISFIED_IN_RUN / INCONCLUSIVE` | 只判断本次具备证据的业务约束；满足合同不意味着 Agent 普遍安全 |
| Fault Activation | `TRIGGERED / NOT_TRIGGERED / UNKNOWN` | 故障发生事实，与业务是否违规独立 |
| Attribution Strength | `INTERVENTION_SUPPORTED / CORRELATIONAL_ONLY / UNKNOWN` | 干预支持需要可比控制条件，不将时间先后直接当因果 |
| Reproduction | `REPRODUCED / NOT_REPRODUCED / NOT_TESTED` | 重现需新执行；不能只重复查看同一 Trace |

Agent Exposure（关键行动前是否接收到相关 Tool 观察/反证）应依据**实际可见事件**，不推测模型隐藏推理。Witness 见证如果过短缺少前提或真正的重新执行，不能声称全局最小复现。

## 5. SHOULD / FUTURE / NON-GOAL

**SHOULD**：Budgeted Witness Shrinking（每次有效裁剪须复跑）、受控修复候选与 Baseline/Candidate 独立对照、由 Effect Contract 生成受限故障候选、至少一个同预算固定顺序策略对照、MCP/Skill 通用工具链入口。若无法完成，必须说明原因而不宣传已实现。

**FUTURE**：第三业务领域/Coding Agent、更多外部 Agent 框架、深入因果推断、生产级租户/认证、长期统计 Benchmark 与大规模部署。

**NON-GOAL**：只靠二次 LLM Judge 判断事实；通用代码助手复制品；自研通用多 Agent 框架；未经授权访问真实支付/生产服务；将可观察事实用模型润色后冒充原始真相。

## 6. 验收 Gate 与诚实降级

- `Gate 1`：受控执行与独立状态验证成立，否则功能 Demo 不进入“可信见证”宣传。
- `Gate 2`：外部/探索 Agent 真实 Tool Calling 成立，否则不得称自主探索完成。
- `Gate 3`：反馈改变测试选择且有前后证据，否则只宣称有界测试选择，不宣称 PGE 自适应已证。
- `Gate 4`：第二领域公共核心复用有代码与运行证据，否则不宣称通用。
- `Gate 5`：Witness 离线校验、篡改拒绝、负向控制成立，否则见证可信主张不成立。

本次提交只需少量必要 LLM 流程；具体见 [05-EXPERIMENT_PROTOCOL.md](05-EXPERIMENT_PROTOCOL.md)。无证据的 Gate 标为 NOT_RUN/UNAVAILABLE/FAIL，不以漂亮 UI 或脚本预期替代。
