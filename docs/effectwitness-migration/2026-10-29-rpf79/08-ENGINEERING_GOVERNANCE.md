# ENGINEERING GOVERNANCE｜完整迁移版

> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

## 当前适用规则

本次RPF79正式Plan仅授权21个新迁移文件与AGENTS有界追加。docs/project/history仍只读；迁移目录非canonical真值的新权威副本。以后每轮按有效Plan冻结owner/根/白名单/费用/网络/Git，不从本迁移继承新实验额度。

## 协作与交付规则（2026-10-29有效）

主要中文，先结论，再源码/可核对证据、机制、成本、边界、反例和下一决策。高信息密度、低模板，避免空泛夸奖、无据数字、反复“不是……而是……”和劣质比喻。对复杂机制使用实际类型、字段、数据流和状态机；双语术语服务准确性。

用户希望持续研发、探索通用性与产品成熟度，比赛材料完成、某切片COMPLETE均不等于项目最终完成。不要重做已批准孵化访谈。Architect深入源码与证据审查、主动提出高价值下一任务；Codex负责获授权实施。能自主决定的架构/局部调试/重复聚焦验证无需微审批；只有目标、权限、生产、真实费用或外部操作等重大边界才另行批准。不得借自主执行放宽WAL/UNKNOWN/secret/用户文件保护。

正式Plan沿RPF-NN / rev-X连续编号，必须自包含、真实创建可下载.md后给普通Markdown链接；支持sandbox的设计环境使用 `[下载 文件名](sandbox:/mnt/data/实际文件名.md)`，这是格式约定而非本包已经生成的Plan。禁止文件卡片替代、占位“看附件”、只贴代码块。稳定文档推荐Medium，高风险跨系统推荐High；不把具体模型型号/猜测计价写死。

完整RESULT、诊断、源图随授权安全feature分支的focused Source/Evidence Commit普通Push并读回HEAD/blob；Codex最终聊天只报自然简洁的Status、branch、40位SHA、报告/产物和关键异常，不强制300～600字、不复制几百行审计报告。Architect独立读取GitHub原件，用户可只通知某RPF完成。报告封存A10与最终Git收据分别记录，不循环amend。

TASK_COMPLETE、EVIDENCE_ACCEPTED、STAGE_ADVANCED分别核实；ELIGIBLE非部署；Agent FAIL与Platform ERROR分开。真实双Agent/Web Live/Issuer/比赛提交不能由离线合成证据替代。可信负结果、PARTIAL/UNAVAILABLE是有效信息，不刷PASS或无限benchmark。Provider0任务不读取或探测Key。

保护docs/reviews/禁入、禁列举、禁读取、禁修改/暂存；旧.local/rpf-* WAL/marker、旧Witness/Source Map、用户草稿、原docs/project/history不清理不拼接。不擅自合并main、PR、部署或比赛提交。平台阻断准确保留现场，不申请Daybreak、不以变相提示绕过安全限制；继续独立获授权工作。

## 原合同与历史参考全文（HISTORY_2026_10_22）

> 下列旧快照中的“当前/下一轮/RPF65未实施”只描述2026-10-22，不与上方当前事实并列生效。稳定产品/安全/实验/UX约束继续有效；旧示例不构成重跑或越权许可。

> # ENGINEERING GOVERNANCE｜EffectWitness 增量工程治理
>
> > **2026-10-22 迁移说明：** 当前实际任务已推进至 RPF-64；仓库中旧 Project State 仍停留 RPF-39 是因为未获授权修改 canonical 文件，**不是** RPF-40～64 尚未完成。把 RPF-64 证据视为最新功能分支，不能推导已 merge main。新增执行纪律：G0 对白名单新路径逐一验证未占用；源码冻结 **之前**执行格式检查，冻结后发现纯格式问题如实 FAIL，不静默改写已签 Witness 的 Source Map；Provider 0 的任务不读取 Provider Key。
>
>
> > 适用：**已有** `MyKr-YSteinsK/runproof` 的竞赛研发分支。此文档是 ChatGPT Project 的治理种子，不能替换仓库已有 `AGENTS.md`；Codex 执行优先读取当期现有 repo 事实、有效历史合同和当前自包含 Plan。正式权限只来自当前 Plan/用户授权。
>
> ## 1. 决策权与状态权威
>
> | 角色/载体 | 权限与责任 |
> |---|---|
> | 用户 | 批准重大目标/范围、安全边界外部操作、额外费用/生产副作用与最终交付 |
> | Planner Main | 形成 Plan、审查证据、接受研究结论、阶段推进与重要合并建议 |
> | Codex | 在 Plan 内调查/实现/实验、更新获授权的实施事实、聚焦 Git 交付与单一 TASK_RESULT |
> | Research/Lab/Review | 限当前研究结论和证据；不能凭局部分支自动推进正式项目 |
> | GitHub repo 与可追溯 Artifact | 代码、运行事实与历史正式证据的来源，需核对分支、SHA 和配置 |
>
> 旧 RunProof 产品规范分别由 `docs/project/PROJECT_BRIEF.md`（长期目标）、`DECISIONS.md`（已批准决定）、`CURRENT_STATE.md`（当前实现），执行规则由 `AGENTS.md` 负责。新 Project 附件表示新目标，不自动成为本地 canonical truth。旧历史的 RPF-00～39、决定 ID 和 Reviewed Artifact 不重写。
>
> ## 2. 本地工作空间与文件所有权
>
> - 正式启动前核实本地仓库根目录、真实 Git HEAD、status、remote/upstream、当前未提交修改、`.gitignore` 与所有已生效目录保护规则；`<REPOSITORY_ROOT>` 是待核验的历史路径，**不是**自动可写授权。
> - 仓库父目录及相邻项目没有默认写权限，不以 `../` 散落临时输出。优先使用仓库现有 `.local/`、明确忽略目录及现有允许的 spikes/代码模块；具体新路径按 Plan 明确，检查工具默认 cwd/temp/output。
> - 分支/Worktree 按真实冲突隔离代码、Docker 容器/网络/volume、数据库、端口、模型密钥、日志与临时输出。Worktree 不自动隔离共享环境；未确认可写路径不先行创建。
> - **保护** `docs/reviews/`（按原 AGENTS 禁止读取/修改）、其他用户文件和未提交更改、旧 Reviewed JSON/Hash、原 Demo/历史验证路径。不能静默格式化、移动、重生成、删除原证据。
> - 仓库内 `AGENTS.md` 有旧合同，新增入口若获授权，应以最小有界修改补充而非完全覆盖；现有等价文档直接引用，不制造第二套全量状态注册表。
>
> ## 3. 代码/合同与架构风险边界
>
> - **身份与业务**：冻结 Agent/Scenario/Environment/Effect/Verifier/Run identity 与独立权威状态；LLM 不自行改变 oracle、不替代 Verifier。
> - **Fault 与真实执行**：planned、triggered、observed 分开；未触发为负向控制，不当作“注入故障条件下通过”。
> - **结果分类**：Agent FAIL vs Platform ERROR、INVALID、INCONCLUSIVE、CANCELLED 分开；业务 Contract 维度与旧 Run Outcome 分开。
> - **不确定副作用**：`UNKNOWN_OUTCOME -> RECONCILE_REQUIRED`，根据 operation receipt/state 确认后决定是否 retry；禁止 blind whole-run retry。Worker 崩溃/租约失效不证明副作用没发生。
> - **授权**：Exploration Agent 只能使用 allowlisted tools；新 Web 不获取 Worker/Decision credentials、数据库密钥、Docker socket。`ELIGIBLE` 仅为质量策略资格，不能部署/发布。
> - **数据与安全**：测试只操作 Controlled Simulation，绝不接真实支付或生产破坏性 credential。Provider token、授权信息、自由 Prompt/Tool payload/CoT 等按现有证据脱敏合同管理；无默认导出机密。
> - **平台变更**：新 API/Schema/Worker 变动先核对 migration、逆向兼容、旧 Gate 与 Golden Demo；不能为了“更通用”删掉旧约束。
>
> ## 4. 产物生命周期
>
> | 类别 | 典型内容 | 处理原则 |
> |---|---|---|
> | 一次性 runtime | Docker/数据库临时资源、缓存、日志、纯排障副本 | 限已授权忽略目录；资源须记录 owner，安全清理；不能删未知用户资源 |
> | 阶段复现证据 | 最小测试脚本、Agent/Contract 版本、Witness 样例、失败验证、费用摘要、实验 Result | 有交接价值且无秘密时优先按仓库规定提交；必要时存受控位置与内容哈希 |
> | 长期事实 | 真正新增能力、可重用约束/决定、当前实现及未实现限制 | 写入原仓库适用状态/模块 README/测试，不冗余建多套索引 |
>
> 不可因“保持仓库干净”删除仍有研究价值的失败样例；也不可因“实验文件都上传”就提交 `.venv`、secret、巨型 trace、未授权数据。Git 删除不会自动从历史删除误提交的凭据，须首次提交前阻止。
>
> ## 5. Git 与部署权限
>
> - 原 repo 公开、`main` 为默认分支；开发应使用**执行前核实并授权的竞赛分支**，按任务范围 focused Commit/Push。没有适用变更不制造空提交。
> - 此 Bootstrap **没有**授权改动 GitHub 仓库。后续每份正式 Plan 应写明允许创建/修改、分支与必要 Push；用户批准孵化包不等于批准未来任意变更。
> - Push 前先检查 `push/PR` 触发的 CI/部署副作用；仅允许既有范围内的 GitHub CI 运行，不可从 Push 推导可做生产部署。Push/Commit/Merge/Release/Publish 分开报告。
> - 无授权禁止创建/删除远端、修改仓库可见性、force push、amend 已推送历史、重写 Git history、merge `main`、tag/release、部署、云资源或密钥改动。
> - 交付需验证真实 remote branch/SHA；本地 commit 或 tracking ref 不等于远端成功。并行进度导致 SHA 不相同，要检查提交是否被祖先包含，不能仅凭相等/不等草率判断。
> - 必要 Push 未完成则 TASK_RESULT 整体不能标 COMPLETE，按 PARTIAL/BLOCKED/FAILED 具体条件报告。阶段接受与最终 Main merge 由 Planner/用户授权流程决定。
>
> ## 6. 回归验证与证据接受
>
> 依据受影响边界选实际验证，不能机械跑遍旧数十个手工探针，也不能因为 CI 绿色就宣称新 Agent 真实可用。
>
> 已有快路径可参考（先核对仓库实况）：
>
> ```powershell
> python -m unittest discover -s runtime/tests -p 'test_*.py' -v
> python runtime/verify-reviewed-artifacts.py
> python ci/verify-public-docs.py
> python demo/verify-golden-demo.py --root . --json
> mvn -q test package -f control-plane/pom.xml
> npm test
> npm run typecheck
> npm run build
> ```
>
> 跨 RPF-28/30/32/34/35 正式合同改动时使用现有 manual probe/Verifier，但受时间/费用预算约束，具体选择根据改动风险。原 `.github/workflows/release-gate.yml` 需保留 canonical evidence/read-back 语义。
>
> **新 EffectWitness Gate**：真实 Agent Tool 调用；受控环境权威状态；故障触发与否；独立 Witness Verifier；跨领域共享内核；Web 用真实 API；样本缺失/篡改拒绝；如实报告 NOT_RUN/UNAVAILABLE。少量 LLM 实验只能证明局部机制，不能推广长期 Agent 成功率。
>
> ## 7. 实验、模型与成本治理
>
> - 本次竞赛**已批准最小必要 LLM 验证预算**。每个探索 Plan 写具体 LLM calls、steps、time、fault trials、token/cost 软/硬界限；实际 usage 记录模型、调用次数与费用，依执行时可核实价格，不猜测账单。
> - 绝大多数 Contract/Verifier/Fault/恢复测试靠确定性脚本完成，不为凑数量运行完整 LLM 多次。复杂失败需要额外调用时先说明信息增益。
> - 对照需固定 Agent/Effect/Experiment/Environment/Verifier、预算和随机性，保留固定顺序 B0 与 PGE 的相同候选信息；不能把已看过的答案漏给自适应策略。
> - 允许可信负结果、无效实验和预算耗尽结论；不能宣称没发现故障就证明安全。证据泄漏/环境污染/未触发 fault 不能当有效发现。
> - 可复用故障知识记录最小的触发条件、观察、关键 root-cause 证据、替代方案、适用范围；不要每次报错建空文档。
>
> ## 8. Stage / TASK_RESULT 责任
>
> `TASK_COMPLETE → EVIDENCE_ACCEPTED → STAGE_ADVANCED` 是事实/判断/权限分界：Codex 在本任务内按授权更新已观察实施事实，Main 审核实验结论与阶段，重大目标/研究路线变化需用户批准。只有工具实际更新文件、提交/推送成功后才能报告已经写入仓库。
>
> 任务具体技术权限、`COMPLETE / PARTIAL / BLOCKED / FAILED`、`PASS / FAIL / NOT_RUN / UNAVAILABLE / NOT_APPLICABLE` 和单一 TASK_RESULT 语义以 [07-CODEX_PLAN_SPEC.md](07-CODEX_PLAN_SPEC.md) 为准。结果文件入 Git 不写自己最终 SHA，最终提交回执补充；不可通过循环 Amend 伪造完整性。
>
> ## 9. 有界故障与停止条件
>
> - 出现可能污染业务状态、并发互相干扰、source identity/Artifact 校验失败或无法安全恢复时立即停止受影响运行并隔离。
> - 工具/模型网络错误若是平台故障，应记录 `PLATFORM_ERROR`，不得计入 Agent FAIL；修复诊断问题后可在授权预算内重试，不进行盲目有副作用重试。
> - 发现重大历史治理冲突、旧证据不可变保护冲突、未经授权的 API/Remote/生产操作，先报告具体冲突与受影响动作。其余独立授权工作可继续。
> - 同一失败路径无新的证据增益时停止重复排障，提出有限候选与最佳推荐，不机械启动额外复杂组件。
