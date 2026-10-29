# UX BASELINE｜完整迁移版

> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

## 当前适用规则

Desktop Web仍是主要体验。RPF60旧Live与Reviewed/Fixture不能混称；目前没有依据宣称75～78策略已经进入Web Live。Policy Lab仅为PLANNING CONTEXT，未实施；新UX不能静默破坏旧只读路径/双语/Timeline/State Diff/deep links。


## 原合同与历史参考全文（HISTORY_2026_10_22）

> 下列旧快照中的“当前/下一轮/RPF65未实施”只描述2026-10-22，不与上方当前事实并列生效。稳定产品/安全/实验/UX约束继续有效；旧示例不构成重跑或越权许可。

> # UX BASELINE｜EffectWitness Lab 与原 RunProof 体验保护
>
> > **2026-10-22 迁移说明：** RPF-45/46 与 RPF-60 已实现不同层次的真实 Web Lab，旧版只读 Timeline、State Diff、双语、深链接和来源失败关闭仍应保护；RPF-63 双真实角色与 RPF-64 新 DomainPort 尚**没有接入 Web Live**。以下「新 Lab」「三分钟故事」中未发生的违规/反馈改选仅是 UX 目标，不能表述为某次已录制运行。参阅 [10-CURRENT_STATE_AND_EVIDENCE.md](10-CURRENT_STATE_AND_EVIDENCE.md)。
>
>
> > 适用项目：Desktop Web 为原 RunProof 认可的主要人类调查面，新增的 EffectWitness Lab 必须真实可用。本文件是体验/信息设计合同，不表示 UI 已实现。技术权威状态与运行轨迹见 [04-TECHNICAL_CONTEXT.md](04-TECHNICAL_CONTEXT.md)。
>
> ## 1. 产品体验目标
>
> 三分钟内让评委看到：一个 Agent 受控地处理实际业务 → EffectWitness 选择高风险条件 → 首次无效/证据不足 → 实际反馈与后续选择 → 权威状态（满足/违规/未知）→ 可验证的限定 Witness。用户不需先理解 Worker/Lease/OTel 才能知道系统发现了什么。
>
> 在较长时间的工程调查中，用户还应能：定位是哪个 Agent 版本、哪次实验、哪条业务不变量、哪次工具调用/状态变化导致结论；切换场景或返回上一页保留合理上下文。
>
> ## 2. 原 Web Canonical Baseline（必须保护）
>
> - 原 Desktop Web 是 API-backed、read-only 调查面，既有 `Overview/Agents/Executions/Failures/Regressions/Statistical/Release Decisions` 等路由不应因为新 Lab 改造变成可任意写数据库的界面。
> - 原 UX 以 Failure Timeline 为主，State Diff、Trajectory Diff、Blocking Invariant 与 Evidence 链接辅助；详情 Deep Link 的 identity/context 连续。
> - `en-US` 与 `zh-CN` 只变展示，不改变 route、enum、ID、raw evidence、hash；浏览器 `zh*` 自动中文及用户主动选择的具体持久化规则以实际仓库合同为准。
> - API/Artifact 不可用应显示明确故障与下一步，不得自动退回 fixture 数据显示成功。标识 Verified Result、Inference、AI Analysis 的来源层级；核心状态不能仅靠颜色。
> - 可访问性：键盘可达、可见焦点、非 Hover 关键动作、可预测局部滚动；避免模板化 SaaS 统计卡堆叠、没有内容价值的动效。
>
> ## 3. 新 Lab 的核心信息架构（拟议）
>
> **入口/主要步骤**：
>
> 1. `Task Setup`：用户选择合法领域（订单/退款或运维/配置）、受测 Agent Profile/Adapter、现有 Effect/Experiment Contract，查看预算和权限，确认启动。普通用户不能在执行后改变 Contract Oracle。
> 2. `Exploration Timeline`：以可排序时间轴列出候选、选择、执行、故障计划/触发、状态读回和反馈，清楚指示 LIVE/REVIEWED/DEMO 数据来源。
> 3. `Evidence Feedback`：本次是否实际触发、已观察到哪些业务效果、哪些信息缺失，为什么考虑下一项候选；AI 理由与独立证据视觉分层。
> 4. `Witness Detail`：显示业务规则期望/实际、源事件、可信来源、归因强度、复现状态及可运行的 verifier 入口；可以跳转原有 Run/Failure/Execution 详情。
> 5. `Comparison (SHOULD)`：必要时比较固定顺序与反馈选择、或 Baseline 与修复候选；未验证指标显示未知而非零。
>
> **操作边界**：页面对新任务的启动/取消经受限服务器端 Gateway，绝不将 DB/Worker/Decision Token、Docker socket 或 Provider key 下发客户端。既有只读 API 保持只读。任务取消必须明确“请求取消”与“已经终止”不同。
>
> ## 4. 状态文案合同
>
> | 状态情形 | 必须让用户理解 |
> |---|---|
> | `PLANNED` | 已选择方案但尚未执行或故障未触发 |
> | `RUNNING` | 正在执行，可能存在等待或延迟；显示唯一任务 identity |
> | `NOT_TRIGGERED` | 这次注入未达到故障条件，不能声称目标行为通过 |
> | `INCONCLUSIVE` | 缺少关键证据／安全终止，结论未知 |
> | `VIOLATION_CONFIRMED` | 独立验证证明确实违反了声明规则，提供源 Evidence |
> | `CONTRACT_SATISFIED_IN_RUN` | 本次执行满足指定合同，不意味着所有情况下安全 |
> | `RECONCILE_REQUIRED` | 有副作用状态尚不确定，禁止盲目重复操作 |
> | `PLATFORM_ERROR` | 评测执行/环境本身失败，与受测 Agent FAIL 分开 |
>
> 以上 UI 词汇可映射到真实 schema；不得直接与旧 Run Outcome 混用造成身份/语义漂移。时间线中的“自主选择理由”须来自当时保存的 Agent 输出或结构化依据，不允许事后编造。
>
> ## 5. 三分钟演示主故事（目标分镜，非既成结果）
>
> | 视频时段 | 画面 | 真实性条件 |
> |---|---|---|
> | 0–20 秒 | 一句直观业务任务与一次退款不得重复的约束 | 来源为冻结 Effect Contract |
> | 20–50 秒 | 探索 Agent 挑选第一实验，受测 Agent 真执行 | 显示真实 Tool/Run 身份，不需展开私有推理 |
> | 50–90 秒 | 首次故障未触发或无有效证据，Agent 读取反馈并改变选择 | 展示因反馈改变候选的证据关系 |
> | 90–130 秒 | 第二次执行，展示实际权威状态与是否违规 | 必须按本次真实结果决定叙事；不得补造违规镜头 |
> | 130–160 秒 | Witness Certificate 与独立校验、为何可信 | 证据身份/哈希/验证器结果可追溯 |
> | 160–180 秒 | 切换运维/配置变更的一条已测案例，说明共享框架 | 以实际第二域结果支持泛用性 |
>
> 编辑视频可以合理剪辑真实等待和无关调试，但不能剪出不存在的因果或伪装多次运行数据为一次执行。已审查 Golden Demo 只能标为**已有平台证据**，不能替代新 PGE 演示。
>
> ## 6. Web 验收与测试
>
> - 至少一次真实浏览器从 Setup 到 Witness/无效证据状态的操作验证，基于新执行 API，不用纯 fixture 模拟成功。
> - 保留旧 Web 最相关的读路径、zh/en 展示、深链接与 API 不可用逻辑；相关变化需运行 Web tests/typecheck/build 和所影响的后端测试。
> - 核查长事件时间线、状态切换、重试/取消、错误后的重新进入与任务身份保持。
> - 不要求移动端/PWA 产品化；Desktop Web 为主，若正式 Plan 增加真实设备 Gate 才将其视为必要，否则按自动测试范围如实报告。
> - 任何数据源 Mock / Static / Reviewed / Live 必须有清晰来源，不能在录制/交付时误导。
>
> ## 7. 体验取舍与风险
>
> 优先把复杂度投入到**一条高质量、可追溯的操作链**，不是同时开发聊天、图表墙和 Workflow Builder；不为组件统一覆盖旧版可用界面。新页面应当快速解释失败事实，但允许工程师逐层深入权威证据。视觉基线不是最终实现像素规范，具体组件需在真实代码与测试下选择。
