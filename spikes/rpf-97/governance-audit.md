# RunProof 治理与仓库维护审查｜2026-11-08

**审查性质**：以 GitHub `main@ef1a92b911e7ff6f414d7a357a6ec562530ec1c0` 的定向源码和本项目已提供的目标文档为依据的**架构/治理审查**。未接触用户本机未跟踪 RPF-96 草稿、`.local`、私有配置或 `docs/reviews/`，没有重新运行 Runtime / Provider / CI。以下不构成全仓库逐文件静态分析或可删除文件的完整鉴定。

## 主要发现

| 优先级 | 事实/源码依据 | 造成的问题 | 调整 |
|---|---|---|---|
| P0 | RPF-96/rev-1～3 用户回报：原 owner 缺发送预算起点；物理发送被禁止；但离线原型修复和 Git 提交也连续阻塞 | 将物理准入扩散到所有开发动作。此前 Architect Plan 有设计责任 | 按风险 Lane A/B/C/D 解耦；禁止物理发送仅限该动作，独立可交付成果先做完 |
| P0 | `AGENTS.md` 第 7 节保留迁移 feature-branch evidence 流程，第 8 节启用 main-first；RPF-79 迁移模板更载有大量全 G0/freeze/reseal 语义 | 历史流程覆盖/叠加当前默认，执行器难判定优先级 | 主合同 AGENTS 简化为唯一有效执行入口；旧模板注明 HISTORY、不继承为所有新任务权限 |
| P0 | `docs/project/CURRENT_STATE.md` 带日期 2026-10-30；目前仍描述 RPF-82 及 RPF-81 的旧状态，未记录 main 的 RPF-94/95 | 当前导航不可信，Codex 可能错误恢复旧工作 | 更新 2026-11-08 snapshot，明确 remote SHA、RPF-95 PARTIAL、RPF-96 LOCAL_REPORTED / 未 push |
| P1 | `.github/workflows/release-gate.yml` `push(main)` 过滤包含 `AGENTS.md`、`docs/**`，`Run repository contract checks` 启动 1232 方法的 Runtime Router | 低风险文档修改也触发重量 CI；混同“已 push”与“发布资格门禁” | 文档/局部提交允许按聚焦检查独立交付；保留 canonical CI 失败事实，不为变绿削弱测试 |
| P1 | CI Run `42459651864`：676 PASS、12 ERROR、5 SKIP、539 UNAVAILABLE；`verify-runtime-coverage-handoff.py` 检查 `runner_rc=0`、固定测试 ID 与必需覆盖 | 12 ERROR 导致下游证据无效，失败原因没有被充分归因 | 单独建立 CI 根因治理任务，不把 ERROR 改 SKIP、调低 required coverage 或绕过来源绑定 |
| P1 | `runtime/runproof_runtime/effectwitness` 具有大量 `pge_r65_*` 到 `pge_r81_*` 的任务版本实现，`spikes/rpf-*` 有封存 source/evidence | 重复、难维护，但不少与原不可变身份/验证器/历史回归互相依赖 | 将版本资产分类为 Active / Historical Evidence / Candidate Dead Code，先核对 import/reachability/reviewed verifier 后决定迁移/弃用；先不批量删除 |
| P1 | `docs/effectwitness-migration/2026-10-29-rpf79` 是 2026-10-29 的非 canonical snapshot，根 `AGENTS` 仍直接引导使用 | 多套旧治理材料被误认为最新指令 | 保留历史字节；从 AGENTS 的 active workflow 去掉旧快照的指令地位，仅作可溯源历史链接 |
| P1 | Windows 执行 `python` 意外触发 Python Install Manager 安装 3.15.2（用户回报）；仍无 owner 外副作用完整审计 | 环境约束演变为新阻断，解释器别名带意外系统写 | 高风险外部命令前确认可执行文件身份，使用已验证的绝对 CPython 路径；保存事故事实，但不要求无关文档开发反复证明安装环境完全无副作用 |
| P2 | RPF-95 read-only MCP Manager `MCPTool.invoke` 已证明，`pip check` 仍为 exit1 | 可复用接缝是真实进展，完整依赖环境尚不可靠 | 后续独立补依赖/可重现环境，不扩大读工具为带写工具，不要求本次治理任务解决全部依赖 |

## 保留的产品/安全底线

`R-01～R-10` 与 D-COMP 目标不删除；`UNKNOWN_OUTCOME` 禁止盲重试有副作用写，RPF-74 仍有 UNKNOWN 后新 `provider RESERVE` 反证；Verifier/Oracle/Release Authority 不交给 LLM。发行/部署仍需单独授权，不能将 hash/self-signature 当独立 Issuer 或离线重审当全新复现。

`docs/reviews/` 不读、不列举、不修改。旧 `.local/rpf-*` WAL/receipts/markers、历史 Witness/Source Map 与封存 `RESULT` 不因“瘦身”被消除。不要将无可见依赖 ≈ 安全删除。

## 本次可执行的整理范围

1. **治理主干实改**：根 `AGENTS.md` 精简并统一 main-first 与风险等级；`docs/project/CURRENT_STATE.md` 更新事实；`docs/project/DECISIONS.md` 只追加 D-029，不改 D-001～D-028。旧 Project Brief 的产品/UX 语义不变。
2. **有效减负**：明确日常实现不要求 freeze、旧物理账本、严格双阶段 commit、每任务 owner 或全量 Runtime；G0 仅检查当前任务相关风险、路径、改动；允许 preserved untracked RPF-96 草稿与普通文档 scoped commit 共存。
3. **垃圾分类交付**：产出 `cleanup-inventory.json`，对被审查的具体候选记录 `path`、`category`、`evidence`、`action`，将未鉴定版本化源码列为 `REVIEW_REQUIRED`。本轮不删除封存证据或用户私有文件。
4. **CI 改进待办**：明确 12 个 ERROR 和 539 个 UNAVAILABLE 的根因分析要独立完成；无证据不得缩小 required inventory。

## 整体研发建议

接下来暂停“RPF-96 再修一个补签 Plan”的循环。治理变更完成后，如果继续 UNKNOWN 基础设施，先把 offline implementation、独立 Oracle 与聚焦测试做成一次可核验提交；物理发送由独立准入决定。并行关注 Desktop Web 的真实会话闭环、JiuwenSwarm 的可重现依赖安装、真实双 Agent/双域验证与 Issuer 信任边界，避免历史任务编号驱动产品路线。

**范围限制**：远端不存在 RPF-96 未跟踪源，未能判定其最新具体语义缺陷；不能凭本次静态审查认定所有旧版本实现是“垃圾”。该部分须由 Codex 在本地按明确只读范围提交 inventory，之后才能做依赖安全的删除。
