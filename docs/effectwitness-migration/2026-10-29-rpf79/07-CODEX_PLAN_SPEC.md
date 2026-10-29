# CODEX PLAN SPEC｜完整迁移版

> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

## 当前适用规则

当前正式任务为RPF79文档迁移，RPF65～78已存在；新编号/修订必须先核验，不能预定78已接受。下列旧九项/十项是仓库完整版报告字段，不是要求聊天复制长报告或固定字数。常规授权内调试/修订/聚焦测试可自主，源freeze后不伪造修复历史。

## 协作与交付规则（2026-10-29有效）

主要中文，先结论，再源码/可核对证据、机制、成本、边界、反例和下一决策。高信息密度、低模板，避免空泛夸奖、无据数字、反复“不是……而是……”和劣质比喻。对复杂机制使用实际类型、字段、数据流和状态机；双语术语服务准确性。

用户希望持续研发、探索通用性与产品成熟度，比赛材料完成、某切片COMPLETE均不等于项目最终完成。不要重做已批准孵化访谈。Architect深入源码与证据审查、主动提出高价值下一任务；Codex负责获授权实施。能自主决定的架构/局部调试/重复聚焦验证无需微审批；只有目标、权限、生产、真实费用或外部操作等重大边界才另行批准。不得借自主执行放宽WAL/UNKNOWN/secret/用户文件保护。

正式Plan沿RPF-NN / rev-X连续编号，必须自包含、真实创建可下载.md后给普通Markdown链接；支持sandbox的设计环境使用 `[下载 文件名](sandbox:/mnt/data/实际文件名.md)`，这是格式约定而非本包已经生成的Plan。禁止文件卡片替代、占位“看附件”、只贴代码块。稳定文档推荐Medium，高风险跨系统推荐High；不把具体模型型号/猜测计价写死。

完整RESULT、诊断、源图随授权安全feature分支的focused Source/Evidence Commit普通Push并读回HEAD/blob；Codex最终聊天只报自然简洁的Status、branch、40位SHA、报告/产物和关键异常，不强制300～600字、不复制几百行审计报告。Architect独立读取GitHub原件，用户可只通知某RPF完成。报告封存A10与最终Git收据分别记录，不循环amend。

TASK_COMPLETE、EVIDENCE_ACCEPTED、STAGE_ADVANCED分别核实；ELIGIBLE非部署；Agent FAIL与Platform ERROR分开。真实双Agent/Web Live/Issuer/比赛提交不能由离线合成证据替代。可信负结果、PARTIAL/UNAVAILABLE是有效信息，不刷PASS或无限benchmark。Provider0任务不读取或探测Key。

保护docs/reviews/禁入、禁列举、禁读取、禁修改/暂存；旧.local/rpf-* WAL/marker、旧Witness/Source Map、用户草稿、原docs/project/history不清理不拼接。不擅自合并main、PR、部署或比赛提交。平台阻断准确保留现场，不申请Daybreak、不以变相提示绕过安全限制；继续独立获授权工作。

## 原合同与历史参考全文（HISTORY_2026_10_22）

> 下列旧快照中的“当前/下一轮/RPF65未实施”只描述2026-10-22，不与上方当前事实并列生效。稳定产品/安全/实验/UX约束继续有效；旧示例不构成重跑或越权许可。

> # CODEX PLAN SPEC｜RunProof EffectWitness 的 Plan 与 TASK_RESULT 合同
>
> > **2026-10-22 迁移说明：** RPF-40 已实施，不得再次下发；下文涉及「首个 RPF-40」的章节与例子只作历史 self-contained Plan 合同示例。下一待确定编号为 **RPF-65**，必须先核实占号、RPF-64 remote HEAD、用户指示和实施边界；新 Plan 仍完整自包含且按原 RPF 编号。不得把旧预览 RPF-41～45 当成未来路线。
>
>
> > 派生自孵化器 05-CODEX_PLAN_SPEC 的核心语义；必须与已有 RunProof `AGENTS.md` 和已生效的历史 Plan 合同并用。**本文件目前为 ChatGPT Project 附件，不自动存在于 Codex 工作区**。首个正式 Plan 应完整嵌入当前任务必要条款，而不是引用 Codex 不可见的本文件。
>
> ## 1. 基本协作契约
>
> **Planner Main / Development Architect**：查证任务所需状态、分析价值/约束、出具真正可下载的 Plan、验收 Codex TASK_RESULT、接受证据、决定阶段与主线整合，重大范围变化向用户确认。
>
> **Codex**：在明确任务和资源权限内核实源码/环境、实现、测试/实验、完成适用 Git 交付，并返回单一、可审查的 TASK_RESULT。未经明确授权不替 Main 决定产品路线、主线合并/部署或重写原项目决定。
>
> **三类事实**：已批准目标（本 Project Requirements/Decisions）、当前实现（实际分支/代码/环境/证据）、计划背景（历史讨论、候选、前次 Result）。Plan 的建议架构不是已实现事实；旧版本 README 不是实时 HEAD。
>
> ## 2. 任务类型与规划深度
>
> - `IMPLEMENTATION`：功能/接口比较明确；规定可观察行为、失败模式与必要验证。
> - `INVESTIGATION / SPIKE`：目标扩展点、SDK、错误根因、进程边界未知；先调查，再在明确范围内做 disposable proof。
> - `EXPERIMENT`：策略效果需要证据；提前确定基线、预算、对照、停止与可接受负结论。
> - `HIGH-RISK`：触及持久化证据、权限、生产副作用/敏感数据或发布；增加安全 Gate、回滚和恢复要求。
>
> 可组合类型；不是所有任务都写完整清单或分裂成多个 Plan。普通稳定任务推荐 Codex 的成本优先档（孵化器曾以 Luna Max 为例）；无法预先规划的跨系统根因/复杂设计才推荐更强推理档。Planner 每次在**聊天说明**模型与思考档位及原因，模型名称不必变成 Plan 硬约束，不能编造未来耗时/额度。
>
> ## 3. Plan 身份、编号、Revision 与可下载文件
>
> - 历史连续：现有 RunProof 已有 RPF-00～39；首个任务**候选** `RPF-40-竞赛升级审计与自主实验接入验证.md`，正式下发前核实是否被实际开发占用。
> - 新任务编号连续唯一、可检索；同一任务内容改变保留 Plan ID，更新 `Plan Revision`；不同任务新编号。编号与 Revision 不混用。历史 Plan 未记录 Revision 时以实际文件/SHA 解释，不补造。
> - **正式 Plan 必须作为实际可下载 `.md` 文件生成**，不能仅聊天示例。内容完整、标题与正文 ID 一致；不含伪造当前 SHA/接口/结果。
> - 正式 Plan 只授权当前任务，RPF-41～45 在孵化预览中的存在不授权提前施工。
>
> ## 4. 三级技术决定（每个正式 Plan 必须使用）
>
> | 标签 | 本项目语义 | Codex 操作 |
> |---|---|---|
> | `FROZEN` | 已批准任务目标、被保护产品/安全/证据/UX 合同、合法数据与必要验收 | 必须遵守；冲突或无法实现需报告，不可静默放宽 |
> | `RECOMMENDED` | 有依据的 SDK/模块/执行路径/设计与验证建议 | 先认真评估，证据显示更优方式可偏离，回传理由 |
> | `DELEGATED_TO_CODEX` | 需要实际仓库/运行环境、实验动态判断的明确选择 | 在**已授权范围**内调查对比并决定，保留证据和后果 |
>
> `CORE / MUST`、`SHOULD / FUTURE` 是产品范围，不等价于三级技术权限。`DELEGATED` 不赋予访问受保护目录、写入任意文件、产生任意费用、Git 合并或生产发布的新权限。
>
> 旧 RunProof 可能存在 `MUST / SHOULD / HINT` 合同：按其原语义保护，不机械替换词；同名旧 Plan/新 Plan 冲突时核对实际修订和明确授权，暂停冲突操作。
>
> ## 5. 正式 Plan 必答的九个问题
>
> 1. **Identity/Base**：Plan ID、实际 Revision、Repo/已核实分支/Source identity；尚未核实的本地环境和远端 SHA 明确为未知。
> 2. **Goal**：本次只解决什么实际问题、交付什么能力/知识或研究判定；为何现在做。
> 3. **Permissions**：按任务明确**允许读取/编辑/创建/运行/网络/模型 API/Git/Push/外部操作**；哪些目录（例如 `docs/reviews/`）不得触碰；临时与持久产物放哪里。可写位置依据真实仓库和用户授权确定，不假设某个父目录可用。
> 4. **FROZEN**：原 RunProof 不变量和本任务相关的已批准目标/合规边界，不得对原历史证据、Release authority 与旧 Web 做静默破坏。
> 5. **RECOMMENDED**：目前证据支持的路线；指出可优化环节与替代方案。
> 6. **DELEGATED**：需在真实代码里解决的问题、候选、评估规则、返回哪些事实。
> 7. **Work/Artifacts**：应执行的调查/实现/验证，数据和配置版本、脚本和日志、工作空间/安全清理。
> 8. **Acceptance/Decision Gate**：每一项有客观 PASS 条件或如实的研究结论；负向控制/取消/异常/无证据区分；何时停止并寻求决策。
> 9. **Delivery/Return**：必要 Commit/Push/远端验证或非 Git 交付、状态维护权限以及 TASK_RESULT 所需字段；不能把“commit 成功”当“push 成功”。
>
> 建议正文少量章节组合，不追求填满九种标题。Investigate/Experiment 需给已知证据、待验证假设、合法比较条件、费用时间预算与失败收口；High-risk 需额外迁移/恢复/授权 Gate。UX 必须引用并在 Plan 中提取受影响的 Canonical Baseline。
>
> ## 6. 历史 RPF-40 自包含性案例（新 Plan 同样必须自包含）
>
> 首 Plan **不得**默认新 Bootstrap 11 文件已经进入 Git，也不得只说“请遵循 07/08”。它必须提供：
>
> - RunProof 仓库身份、候选 Base 与执行时核实 HEAD/工作区方法；有效原 AGENTS、Project State 与已存在的真实路径。
> - 本次已确认的 EffectWitness/PGE 产品意图，关键不变量：原 Reviewed Evidence 不变、Agent FAIL 与平台 ERROR 分开、Unknown Outcome 先 reconcile、Verifier 独立于 LLM、Agent/worker/decision writer 权限隔离、无生产破坏性 Tool、`ELIGIBLE` 不等于部署。
> - 清楚列出允许写入的具体**核实后**路径/隔离 Spike 位置，禁止路径与外部调用预算。先检查 Git status 和 remote，再决定可否 Push；不允许直接 merge/release/deploy。
> - 要求核实 Java API、Python Worker、原两个 Agent contracts、实际 JiuwenSwarm/MCP 接口；**至少真实证明一个受限工具的调用、参数及响应**，或准确交付 BLOCKED/FAILED 证据。不得把 Mock 视为 live。
> - 三份合同候选语义、Orchestrator vs 正式 Worker 对比及后续真实接口决定；不要把尚未实现的字段命名写成冻结的 API。
> - 必要旧测试的取舍和新 Spike 验证；相关接口未验证时把接口能力标记未知。
> - 完整的 TASK_RESULT 规则、Git 交付和不自含最终 SHA 的文件规则；不可依赖 Codex 自动触发任何 Skill。
> - 明确本地合同接入授权：可核查/提出需有界合并的原 AGENTS/Decisions；未经 Plan 逐项指定的文件不得擅自改写。产生真正冲突时暂停受影响动作，报告版本、影响与候选解决路径。
>
> 这套条件允许 Codex 即使只拿到单份 Plan，仍能理解本次合法操作和返回义务。
>
> ## 7. 验证标签、执行状态与实验结论
>
> ### 任务状态（四态）
>
> | Status | 判定条件 |
> |---|---|
> | `COMPLETE` | 当前任务必要工作、必要验收、**适用且授权的交付**均完成。探索目标即使被证伪，也可在调查协议完成时 COMPLETE |
> | `PARTIAL` | 有真实成果，但必要工作/验收/交付未完成，又非明确前置条件阻塞或已最终失败 |
> | `BLOCKED` | 必要权限/环境/输入/用户决定目前无法获得，影响关键进展；给出已完成部分 |
> | `FAILED` | 已按任务协议执行到停止条件，必要验收最终不达标；不是一次普通错误或可信负面研究结论 |
>
> ### 验证状态（逐项）
>
> - `PASS`：实际执行或有效复用证据，给出 source/revision/适用条件。
> - `FAIL`：已执行且不满足标准。
> - `NOT_RUN`：适用但未执行，说明原因。
> - `UNAVAILABLE`：必要环境/权限/结果不可获得，说明限制。
> - `NOT_APPLICABLE`：与本任务确实无关，说明依据。
>
> 不得把工具注册成功说成真实工具调用成功；不得把上传 Artifact 当作源状态已验证；不得把本地 Web build 通过当作实际 Live Lab 已运行；不得把屏幕截图作为真实状态后果的单独证明。
>
> `TASK_COMPLETE -> EVIDENCE_ACCEPTED -> STAGE_ADVANCED` 为责任区分，**不要求三份形式文件**。Codex 结束任务不自动使 Main 接受假设或推进阶段；阶段接受由 Planner 审查。任何真实权威状态尚不可读的场景，不允许宣称已验证 EffectWitness 违规。
>
> ## 8. TASK_RESULT 返回合同（单一主结果）
>
> 一次任务提供一个中文 `TASK_RESULT`（可为仓库文件或聊天正文，按 Plan 规定），至少包含：
>
> 1. **Plan ID + Revision**（若历史来源无 Revision，报告真实输入来源）。
> 2. **Status**：四态及判定原因；区分实现、研究结论和必要交付。
> 3. **Base / Final State**：分支、基线 SHA、工作树、用户原有变更和本任务变更。
> 4. **Changes & Technical Decisions**：真实修改内容、RECOMMENDED 的偏离和 DELEGATED 的取舍/证据。
> 5. **FROZEN & Acceptance**：逐项结论与 PASS/FAIL/NOT_RUN 等。
> 6. **Verification/Evidence**：测试/运行命令的范围与结果、版本、source、实验输入、真实 API/工具调用/费用、复现与局限。
> 7. **Git / Remote**：Commit、Push、远端 URL/ref、核验 SHA、是否 Merge/Deploy，未完成原因；非 Git 任务据实。
> 8. **Deviations/Risk**：已知失败、阻塞、权限变化要求、残余风险。
> 9. **Artifacts/Durable Findings**：保存在哪、证据生命周期、实际更新的 Project State（如已授权）。
> 10. **Next Decision**：值得继续的边界、需 Main/用户批准的改变；不自动创建下一份 Plan。
>
> ### 建议可缩减的回传形态
>
> ```md
> ## TASK_RESULT｜RPF-40 / rev-1
> - Status：COMPLETE / PARTIAL / BLOCKED / FAILED
> - Source / Branch / Base / Worktree：...
> - Changes & Technical Decisions：...
> - FROZEN & Acceptance：...
> - Verification & Evidence（PASS / FAIL / NOT_RUN / UNAVAILABLE）：...
> - LLM Calls / Budget（如适用）：...
> - Deviations / Risks：...
> - Artifacts & Cleanup：...
> - Git / Remote / Deploy：...
> - Next Boundary / User Decision：...
> ```
>
> 若 `TASK_RESULT` 文件需要入 Git，不要求写其自身最终 Commit SHA；包含证据事实和已知基线后提交，最后 Commit/Push 完成后**在同一次对话回执中**补最终 SHA、远端验证和工作树。不要为回填 SHA 无限 Amend。Push 失败但其为必要交付时，不得整体 COMPLETE。
>
> ## 9. Git 与状态维护
>
> 在当前 Plan 授权范围内进行 focused Commit、Push 已核实的安全分支、核验远端；Push 不授权 Merge、Release、Publish 或 Production Deploy。没有适用变更不制造空 Commit；无仓库不得自行 git init；检测 push-triggered side effects。不允许 force push/history rewrite 或提交 secrets/无关用户更改。
>
> 实施事实的 `CURRENT_STATE` 更新仅在 Plan 指明范围内由 Codex 根据实际状态同改动交付；正式阶段接受、改变重要研究路线、合并 `main` 仍由 Main/用户审核并用具备权限的工具实际写入。旧 RunProof 的工程状态/历史不是一份空白模板，不能为了新合同重建并覆盖。
>
> ## 10. 历史孵化期任务依赖（全部不构成未来授权）
>
> `RPF-40` 入口审计 + Tool Spike → `RPF-41` Effect Contract/订单执行 → `RPF-42` PGE 反馈策略 → `RPF-43` Witness/运维复用 → `RPF-44/45` Lab、必要对照和竞赛材料。分割可由真实证据调整，若涉及项目范围或 FROZEN 修改需用户批准；不要预生成大批 Plan。
