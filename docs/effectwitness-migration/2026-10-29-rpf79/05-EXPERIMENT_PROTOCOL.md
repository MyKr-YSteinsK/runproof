# EXPERIMENT PROTOCOL｜完整迁移版

> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

## 当前适用规则

当前离线研究必须冻结输入、Oracle、指标、源码，再仅fit拟合并冻结模型后评价；作者已见challenge明确曝光。不调参追分，不将区间保守拒绝当零错误；missed opportunity和覆盖分母必须保留。真实业务/模型测试只在新Plan明确授权时运行。


## 原合同与历史参考全文（HISTORY_2026_10_22）

> 下列旧快照中的“当前/下一轮/RPF65未实施”只描述2026-10-22，不与上方当前事实并列生效。稳定产品/安全/实验/UX约束继续有效；旧示例不构成重跑或越权许可。

> # EXPERIMENT PROTOCOL｜最小必要 LLM 与可信创新验收
>
> > **2026-10-22 迁移说明：** 以下「最小实验矩阵、H1～H3、3–4目的/12–30调用」是孵化时的计划与费用偏好，不是新 Session 的累计硬上限，也不允许补跑历史任务。已实现 RPF-42、57、59、60、62、63 与负研究结果见 [10-CURRENT_STATE_AND_EVIDENCE.md](10-CURRENT_STATE_AND_EVIDENCE.md)。今后每份 Plan 重新冻结资源与余额；旧 `live/cold` 一次额度不能通过复制工作目录、清空 WAL 或改 Run 复用。
>
>
> > 当前用户已确认：**竞赛截止前显著压缩完整 LLM 闭环实验**，以少量真实运行证明机制存在，不进行大规模统计 Benchmark。研究治理仍要求明确比较条件、证据、负向控制和适用界限。详细产品要求见 [02-REQUIREMENTS.md](02-REQUIREMENTS.md)。
>
> ## 1. 研究主张与范围
>
> | 假设 | 待验证的实际主张 | 最低可接受证据 |
> |---|---|---|
> | H1 / PGE | 根据独立结构化 Evidence Feedback，Exploration Agent 会改变下一次实验选择，获得新信息 | 实际两轮不同候选、决策时可见反馈、模型/工具记录、合法预算、不同结果 |
> | H2 / Witness | 平台能在真实状态上核验业务副作用，并拒绝将故障未触发或证据不足判成有效违规/安全 | 明确受控正例、故障未触发负例、篡改/缺失 Witness 验证失败 |
> | H3 / Generality | 订单退款与运维配置变更共享主要探索/证据/Witness 框架 | 两领域运行产物 + 公共代码入口/可验证 Adapter 边界 |
>
> **研究问题不等于技术优势已证。** H1 可以在功能级别成立，但尚不能推出 PGE 比所有固定策略、Codex Skill、专业测试器有效。若正式比较失败，则保留负结果并调整创新宣传力度。
>
> ## 2. 当前实验预算与费用边界
>
> - 正式目标约 **3–4 类验证目的**，约 **12–30 次 Provider 调用软预算**，并不意味着必须消耗完。首要是可运行真实闭环；精确上限由每份 Plan 根据实际模型/tool/重试开销设定。
> - 单次探索：建议首次选实验 1 次 LLM、必要时根据反馈再调用 1 次；其余 schema 验证/故障注入/状态检查/见证验证尽量由程序完成。JiuwenSwarm 内部实际 API 次数必须由日志/usage 校验，不因设计目标假定只有两次。
> - Provider 推荐从已配置的 DeepSeek Flash 开始；具体模型 ID、工具支持、实时单价及出账口径 **执行时核实**。不因赛事要求自动升级昂贵 GPT 模型；难例需要时进行受控模型替代并记录费用。
> - 每项任务设定 `max_llm_calls`, `max_steps`, `max_fault_trials`, `max_time`, `max_token_or_cost`，达到预算就停止；出错不允许无界循环。软预算变更记录何以必要。
> - **确定性单元/集成/权限/证据测试不随 LLM 预算压缩**，按失败风险验证：多跑规则测试通常不消耗 Provider Token。
>
> ## 3. 最小实验矩阵
>
> | 实验 | 目标域 | 要求 | LLM / 验证 |
> |---|---|---|---|
> | E-01 | 订单/退款 | 未直接告知错误答案时，Agent 从合法候选选择高风险故障，受测 Agent 真实执行 | 真实 LLM+工具；状态/Effect 独立核验 |
> | E-02 | 订单/退款 | 首次实验无有效目标证据后，读取反馈再选择新的注入时点，保留当时选择所见证据 | 可与 E-01 同一探索会话；必要的第二次 LLM；无 LLM 伪装必须标记 |
> | E-03 | 运维/配置变更 | 使用通用框架+另一份 Effect Contract/Adapter 运行有状态场景 | 可利用已验证 deterministic profiles，但至少证明新共用引擎真正贯通 |
> | E-04 | 跨域/订单 | 负向控制：fault NOT_TRIGGERED / Artifact 缺失 / 环境不就绪，不误报 PASS 或 VIOLATION | 优先确定性，不必为了演示人工增加 LLM 调用 |
>
> 这些是不同**验证目的**，不要求机械安排四条独立昂贵会话。若 E-01 未达目标，允许记录如实失败；不得伪造第二轮变好来满足演示脚本。
>
> ## 4. 最低基线与对照设计
>
> - **B0 固定故障顺序**：预先登记固定候选列表和顺序，在相同环境、Agent 版本、合同和实验预算下执行。
> - **PGE 自适应选择**：使用与 B0 相同的候选空间、故障能力和预算；必须隐藏未来真值，只提供实际反馈。比较有效触发覆盖、违规发现、每次成功证据对应预算和额外 LLM 开销。
> - Codex + Skill 的“手工/通用 Coding Agent 开发测试”属于产品替代方案而非必须在本次做大规模自动对照；需要宣称性能优势时再追加公平基线。
> - **最低对照**只需一个风险有代表性、真实运行的同预算案例。它仅支持“在该案例中...”的结论。策略相同/无优势也是有效结果。
>
> 预注册或冻结：Scenario/Effect/Verifier 版本、工具允许集合、被测 Agent 版本、环境 revision、种子、Fault trigger、预算、指标与记录时间。不得把 PGE 试出的正确故障顺序回填 B0，再假装盲测公平。
>
> ## 5. 指标与结果口径
>
> | 指标 | 定义 | 解释边界 |
> |---|---|---|
> | `valid_fault_activation` | planned fault 实际 triggered 且证据显示其观察范围 | 不代表业务必然违规 |
> | `verified_violation` | 独立 verifier 在已冻结 Effect Contract 下确认违规 | 仅适用于本次状态和规则 |
> | `information_gain_proxy` | 新实验是否带来此前缺失的触发/状态/违规证据 | 启发式代理指标，不是未经定义的理论信息增益 |
> | `witness_admissibility` | Witness 校验身份、完整性和合同判定 | 不自动证明因果/生产安全 |
> | `cross_domain_reuse` | 两领域真实共用的代码合同/执行与校验模块及新增 Adapter 成本 | 不用“支持任意 Agent”替代实证 |
> | `llm_calls/tokens/cost` | 实际 Provider 用量，分别按 Agent 任务归属统计 | 完整工作流的总成本，不遗漏失败重试 |
> | `latency/run_time` | 含平台开销与真实模型调用的可观察时间 | 不以一次样例推断生产 SLA |
>
> ### Outcome 失效分类
>
> 区分 `AGENT_FAIL`、`PLATFORM_ERROR`、`INVALID_SCENARIO`、`INCONCLUSIVE`、`CANCELLED`，与原 RunProof 的状态含义一致。`fault planned`≠`triggered`；`ContractSatisfiedInRun`≠长期安全；`PGE 成功触发故障`≠成功归因。足够证据时才给 `INTERVENTION_SUPPORTED`，否则使用 `CORRELATIONAL_ONLY`/`UNKNOWN`。
>
> ## 6. 实验执行纪律
>
> 1. **先预检**环境可恢复、独立状态源可读、执行权限、无真实生产凭据、Source/Schema 固定。
> 2. **执行**：保留 Agent 第一次选择的机器可核实身份/依据，运行候选、注入/观察 Fault、独立读回状态；不在运行后篡改选择解释。
> 3. **反馈**：产生结构化 Verified Result 与 missing evidence，给模型的下一次观察严格以真实当时可用信息为边界。
> 4. **验证**：离线见证 verifier；至少一种恶意篡改、证据缺失或错配测试必须拒绝。验证失败时不可用漂亮描述代替。
> 5. **复现**：要宣称 reproduced，必须有新执行；只复核同一份 Artifact 是 `VERIFIED_ARTIFACT` 级别，不等于复现。
> 6. **清理/保留**：有价值脚本、数据版本、合同、运行摘要、见证、Verifier 和失败证据按仓库规则保存；敏感 Trace/密钥/巨型缓存不提交。环境 reset/cleanup 失败须隔离。
> 7. **收口**：记录 `PASS / FAIL / NOT_RUN / UNAVAILABLE` 与原因，允许可信负结果，不把未知写成 0/通过。
>
> ## 7. Stop 与 Decision Gates
>
> - 因环境/合同不可信导致的实验：停止，必要时 quarantine，不让后续重试污染结果。
> - 预算耗尽或仍未找到合格反例：如实收口为“未在本预算内发现”，不能说“证明安全”。
> - 多次相同无信息排障：改变技术诊断路径，记录关键失败条件；不是无限重复调用 LLM。
> - H1/H2/H3 中任一未证：展示仅已证明的能力，作品创新主张降级；阶段是否进入下一任务由 Main 根据证据判断。
> - 修复候选/Witness Shrinking 若消耗过多工期，优先保留核心实验、负向控制和实际 Demo。
>
> ## 8. 报告格式与可信结论模板
>
> 每项实验最少保存：身份（branch/SHA/config/Contract/Agent/Env/Verifier）、假设、候选空间、试验输入、调用/工具计数、触发/状态/证据判定、结果、局限、停止原因。结论明确采用下列等级：
>
> - **L1 功能证明**：真实 Agent 工作流可完成；
> - **L2 机制证据**：本次反馈引起策略变化并产生有效证据；
> - **L3 有限对照**：在声明的这一场景/相同预算下相对 B0 有信息增益；
> - **L4 泛化/统计优势**：需要扩大独立实验，本次不声称。
>
> 实验源码/证据位置必须来自实际运行，不能预先在 Bootstrap 虚构文件路径、结果分数或调用成功。
