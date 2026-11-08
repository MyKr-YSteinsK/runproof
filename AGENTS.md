# AGENTS.md — RunProof engineering execution contract

> 2026-11-08 现行执行规则。稳定产品要求在 `docs/project/PROJECT_BRIEF.md`，正式决定在 `docs/project/DECISIONS.md`，实际进度和已知限制在 `docs/project/CURRENT_STATE.md`。本文件只规定执行权限和风险边界；历史 Spike/迁移文档是带日期的证据，不是对全部未来任务自动生效的流程命令。

## 1. Scope, authority, and default workflow

- 仓库 `MyKr-YSteinsK/runproof`，默认分支 `main`。实际 root、remote、branch、HEAD 和允许修改路径以每次开始时的 Git 检查为准。常规已授权工作在现有 main 工作树开发、验证、focused commit、普通 push；不默认建立每个 RPF 专属 worktree、owner、双阶段 Source/Evidence Commit。
- 用户与 Architect 确定任务目标、外部权限、生产/真实费用边界；Codex 在已授权范围内选择技术细节、调试、添加有界测试并交付。任务中的一次局部失败通常不要求停掉无关工作，也不要求用户批准每次修复。
- 本仓库属于持续研发，完成单项 RPF/比赛材料/本地测试不等于项目完成、证据被 Architect 接受或版本已发布。`TASK_COMPLETE`、`EVIDENCE_ACCEPTED`、`STAGE_ADVANCED` 分别核实。
- 已批准的 R-01～R-10、D-COMP、MUST/SHOULD/NON-GOAL 和 Desktop Web 首要人类体验持续有效，具体产品合同以 `PROJECT_BRIEF.md` 为准。

## 2. Risk-scaled execution — apply the narrowest sufficient gate

**Lane A — read-only / docs / source audit**：核对 Git 位置、当前 HEAD 和文件范围；阅读与审查、修文档可按普通 Git 纪律进行。无需物理预算、SDK source freeze、历史 WAL 验证或自动搭建任务 owner。

**Lane B — ordinary software implementation**：核对所改路径与既有未提交工作，完成聚焦单元测试、typecheck/build/必要回归；允许在最终提交前持续修改源码和测试。未经任务特别要求，无需先固定 Source SHA、重复两轮同一测试、先提交源码再提交证据、逐文件 create-only 冻结审计或完整历史 Runtime Gate。失败应明确记录，修复后复验；非相关失败可独立跟踪。

**Lane C — controlled local effects**：涉及新本地数据库写入、localhost socket、容器、真实子进程故障、持久化预算时，限定 owner、目标/端口、进程数量、时间、日志与退出清理。物理资源消费必须有当次可核验准入与剩余额度；旧账本未知就禁止**相关物理执行**，不禁止无副作用的源码、模拟、纯内存负控与交付。已生成的旧 WAL/marker/证书不能删除、复制、截断、改名重获额度。需要分支/独立 owner 时仅为对应实验创建。

**Lane D — real-world/high-risk**：真实 Provider/LLM 付费调用、生产/外部服务写入、权限/secret、不可逆历史删除、正式发布/部署或外部竞赛提交，需要逐项明确授权、预算与准入；无授权不得执行。不得通过修改报告、Mock、Fixture 或隐藏失败绕过安全规则。

风险只向实际发生副作用的动作传播。一个高风险动作被阻断时，继续其余已获授权且独立安全的工作；交付时将受阻 Gate 标为 `NOT_RUN`、`UNAVAILABLE` 或 `PARTIAL`，不得称 PASS。

## 3. Non-negotiable safety and evidence semantics

- `UNKNOWN_OUTCOME` 的有副作用操作禁止盲重试写；必须先按冻结合同通过受信宿主/Authority 确定性只读对账。任何依赖 UNKNOWN 后新 Provider 预约的研究路径仍禁止默认启用：RPF-74 历史反例未被旧实现修复。研究性守卫在未获物理验收前不得授予真实发送能力。
- Agent 不持有业务真值、独立 Verifier、Release/Approval Authority。`ELIGIBLE` 是资格判断，不等于 Release/Deploy。
- 事实区分 `Observed Fact / Verified Result / Inference / AI Analysis`；Agent `PASS/FAIL` 与 `ERROR/INVALID/INCONCLUSIVE/CANCELLED` 分开；fault `planned/triggered/observed/agent_exposed` 分栏。哈希与自签 Source Identity 不证明第三方 Issuer；同证书离线复核不等于独立新运行。
- Provider Key、Token、用户凭据不进入 Git、Web、普通 Trace/证书/日志。Provider-0/只读任务不探测 Key。未知资源用量不能记零；不得为了取得 PASS 重置旧账本、marker、预算或替换证据。
- `docs/reviews/` 是用户保护边界：禁止进入、列举、读取、修改、暂存。保留用户文件与无关未提交变更。`docs/history/`、已封存 `spikes/rpf-*` RESULT/Source Map/Witness、旧 `.local/rpf-*` WAL/receipt/marker 默认属于历史证据，不得批量删除、格式化或重签；历史瘦身先做引用/归属核对，再取得**具体删除目标**的授权。
- 除有界任务批准外，不 force-push、rebase/rewrite、amend 已推送提交、改仓库身份、创建 PR、merge/tag、发布/部署、改 workflow 权限、执行赛事上传。

## 4. Practical preflight, tooling, and test policy

- 所有写任务先检查 `git rev-parse --show-toplevel`、`git branch --show-current`、`git rev-parse HEAD`、remote、相关路径的 `git status --short`；校验当前任务的授权范围与 Git push workflow 的已知副作用。**不要求全仓 tracked-clean**：无关脏文件/未跟踪 WIP 留在原处，只 stage 当前授权路径；同一目标文件存在其他人的未提交内容时先保留并处理冲突。
- 仅在确实需要 create-only/隔离/权限敏感时检查该目标的 Git index、大小写冲突、忽略规则、symlink/reparse 和 owner。普通文件修改不要求对整个仓库逐一做 G0。
- 使用明确已核实的解释器/工具二进制路径；Windows Python App Execution Alias/Install Manager 若可能触发下载，先检查解释器，不允许因普通命令隐式安装。下载/安装/外部网络访问遵照当前任务授权；意外副作用记录、局部停止，独立安全工作继续。
- 测试按变更风险选择；可参考 `python -m unittest discover -s runtime/tests`、`python ci/verify-public-docs.py`、`python runtime/verify-reviewed-artifacts.py`、`mvn -q test package -f control-plane/pom.xml`、`npm test`、`npm run typecheck`、`npm run build`，但**不机械全部运行**。对受保护历史 proof 的正式 freeze/负控和两阶段收据，只在当前明确为正式 Witness 实验时适用。
- GitHub hosted Canonical Release Gate 是 release-evidence 门禁，失败须如实报告并跟踪；它不自动阻断与其失败原因无关的日常代码/文档 commit。不要改写 ERROR/UNAVAILABLE 为 PASS，不关闭原 Gate 来获得绿色状态。CI 配置仅在明确授权且有准确根因时修改。

## 5. Delivery and reporting

- 普通任务：完成相关实现和必要聚焦测试 → scoped `git add`/commit → ordinary push → 读回 remote SHA、文件并检查 CI 是否触发。没有强制建立 Spike 或进行双阶段 Source/Evidence commit；若任务已有 RESULT/diagnostic 约定，则同次交付。真正冻结的正式实验必须保持 freeze 前后身份连续、失败现场不改写。
- Chat 简报：`COMPLETE / PARTIAL / BLOCKED / FAILED`、实际分支、40 位 commit SHA（未提交写 `NONE`）、关键测试、未完成风险和 CI 状态。`BLOCKED` 指任务的关键前进路径因授权/物理安全限制无法进行；能完成独立开发与交付时应先完成并诚实报 `PARTIAL`。
- 变更 `docs/project/CURRENT_STATE.md` 时只写可核验的现况；重要长期决定增补 `docs/project/DECISIONS.md`，不得改写历史决定。历史说明保留在其原目录，现行入口不把过时迁移说明当成下一任务指令。
