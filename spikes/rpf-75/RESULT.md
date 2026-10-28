# TASK_RESULT — RPF-75 / rev-1

Status: Partial（报告封存时点：离线实现、验收和源码推送完成，A10 的最终 evidence commit/push/readback 尚待执行。完成后的最终状态及 SHA 由本次对话交付回执给出；本报告不为回填自身 SHA 重签。）

Plan：RPF-75 / rev-1。Base：`d5605c08af33c932f97529ae5b33228b56d8a113`；branch：`codex/rpf-75-offline-pge-explorer-policy`；owner：`rpf-75-rev-1`；ABI：`rpf75-offline-policy-v1`。

已完成可解释离线策略、B0 固定顺序和 B1 评分无反馈消融、独立离线 verifier、16 个合成案例、可复验决策轨迹及负控。证据上限为 `OFFLINE_POLICY_SIMULATION_ONLY`。本任务 Provider 调用 0、真实 token 0、费用 ¥0、SDK child 0、JVM 0、服务 0；未读取或探测宿主 Key。

## 验收事实

| Gate | 状态 | 实际证据 |
|---|---|---|
| G0 | PASS | origin、远端 Base、父分支、新分支不存在、新工作树、新根忽略与 owner/非重解析点、20 个 CREATE_ONLY 路径、适用 AGENTS/产品合同和 feature push 风险均已核验 |
| R75-A01 | PASS | 独立 owner/ABI/schema；9 个冻结输入/源码及 4 个只读参考 raw/LF/SHA/Git blob 对齐，source commit 已推送并双读 |
| R75-A02 | PASS | 候选、权限、成本、风险、前提、UNKNOWN、时限、重复模式和评分分解；两次最终测试及输入反转重放 |
| R75-A03 | PASS | case-00 消费 step-1 VERIFIED 后由 normal 改选恢复候选；case-01 空信息允许原选；不确定、矛盾、迟到、缺 anchor 均有实际案例 |
| R75-A04 | PASS | 16 cases × 3 policies；相同候选、预算、外生可见时序和 oracle；逐例表、汇总分子/分母及不利结果完整 |
| R75-A05 | PASS | 冻结原始 trace 锚；CLI 正确/缺少/错误 anchor 的退出码 0/2/3；独立重算可见记录、状态、排序、结果和指标 |
| R75-A06 | PASS | 44/44 有效重锚工件负控拒绝，含 UNKNOWN/outcome/指标组合；另有重复候选、越域、输入溢出、未来/伪造记录等聚焦控制 |
| R75-A07 | PASS | 最终 88 个方法连续两次 PASS，0 failures/errors/skips；130 条决策在反转输入重放时 raw SHA 完全相同 |
| R75-A08 | PASS | 任务只新增白名单文件，既有 tracked 文件无修改；原 RPF-74 工作树仅顶层 Git 核验，旧私有根未访问，reviews 未进入 |
| R75-A09 | PASS | architecture-decision.json 记录行数、接口、已测/未测范围、局限和通用化取舍 |
| R75-A10 | NOT_RUN（最终报告部分） | Source commit/push/双读 PASS；本报告及其余 evidence 的最终提交、推送、双读将在封存后执行，由最终回执记录 |

完整旧 Runtime、真实 Explorer/Target/Authority、HTTP/SQLite/SDK/JAR 均为 `NOT_RUN_BY_PLAN`，不是隐去的回归失败。未执行 CI workflow dispatch、PR、main 合并、tag/release/deploy 或竞赛提交。

## 冻结、复验与对照

Source SHA：`0238a0bee663d8e99da532236125a58d06dcfffe0e7c815395cf67243a3feccc`。Source commit：`cf59098f96aff03a543545c777131e5214513d94`，已 normal push；`ls-remote` 与 fetch/FETCH_HEAD 双读一致，13 个源码/参考 blob 与 LF hash 对齐。原始字节与冻结清单一致，冻结后没有修改源码、测试、CLI 或 fixture。参考代码只读，不作为可执行依赖导入。

Trace raw SHA：`58d905f6325587ee384f4e9f27e428d7f02092b57a4073ce517dd082c668ec67`。包含 16 cases、48 replays、130 decisions。同样的 SHA 来自实际第二次 `run --reverse` 输出，而非复制。公开 trace 是本任务第一次实际输出的原始字节归档。

最终命令：`python -X utf8 -B -m unittest discover -s runtime/tests -p test_effectwitness_pge_r75.py -v`。两次均 exit 0，88 tests，unittest 用时分别 0.830s / 0.850s；实际进程墙钟、起止 UTC 和日志 SHA 见 `runtime-diagnostic.json`。开发阶段一次 83 项测试中有 3 项因负控生成器以 Python 相等判断误认 False/0 为 no-op 而报错；冻结前修正为规范 JSON 比较，错误日志保留。没有删除失败现场以制造连续全绿。

| policy | 合法 SELECT / SELECT | 模拟成本 | 已验证 outcome 事实数 | 冗余选择 | 重复选择 | 正确终止 / 终止 | inconclusive |
|---|---:|---:|---:|---:|---:|---:|---:|
| PGE-v1 | 26/26 | 82 | 24 | 13 | 11 | 16/16 | 1 |
| B0-fixed-v1 | 28/28 | 85 | 23 | 16 | 15 | 16/16 | 1 |
| B1-no-feedback-v1 | 28/28 | 85 | 23 | 16 | 15 | 16/16 | 1 |

“事实”是所选 VERIFIED 合成 outcome 的独立 `(key,value)` 数，不包含初始/外生反馈，也不代表信息论增益或真实安全价值。冗余包括未增加可验证事实的 UNKNOWN/INCONCLUSIVE；有效 inconclusive 不算失败。安全过滤次数不是攻击拒绝率；负控拒绝率单独记为 44/44。

与 B0 的 fact/cost Pareto 对照：有利 1、不利 1、持平 13、取舍 1。case-00 多得 1 个事实但多花 2 单位；case-09 相同事实少花 6；case-12 相同事实多花 1。案例由本任务手工设计，固定 seed=7501 只作数据身份，没有进行随机总体抽样，不能据此主张真实统计优势。

完整输入与反馈在 source-freeze 前固定。Policy 不接收 outcome oracle，也不接收未来反馈正文；只接收当前可见记录及其冻结 digest。Replay 按 step 公开同一外生时间表，候选 outcome 的查找仅发生于 SELECT 之后。基线不能偷看未来标签。可见记录状态、来源、contract、domain、seq、hash 和 roster 必须相符；与 fixture 不一致的“VERIFIED”字符串不能建立信任。

CLI 原始锚测试已实际运行 exit 0/2/3。44 个独立工件变体由 `probe.py negative` 生成，以同一 CLI 的 `verify_file` 边界实测并保留 machine reason；每项重新计算 row 链及 result hash，原始输入不变。组合项同时改 UNKNOWN 后选择、outcome 和指标。逐项 raw SHA、reason、exit 和额外 admission 测试名见 `negative-controls.json`。

## VERIFIED_FINDINGS

离线策略确实消费已验证的可见反馈，能改变排序，也允许无新信息时不改选。独立 verifier 没有调用 policy.decide、feedback.visible 或 replay.run，单独重算准入、排序、转移及指标。两次聚焦测试和两次输入顺序不同的重放均成功；44 个重锚攻击不能靠自签内部 SHA 获得通过。

## CODEX_ENGINEERING_JUDGMENT

本切片可作为后续真实 Explorer 接口研究的算法基座，不能作为真实双 Agent 的可靠性证书。三个策略共享安全过滤有利于公平比较，但 verifier 与生成器仍可能共享概念错误；共享 ABI 常量和合成 trust root 都不是外部 Authority。997 行 Python 中含较多防御校验、测试和 CLI，运行时策略只有 66 行；不应把该规模解读为公共 Core 已完成。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

保留固定顺序基线和评分无反馈消融，而未加入 LLM 或随机采样，避免混入费用、协议与真实业务效应。用小型、显式 schema 代替旧 Runner import，减少启动副作用；代价是目前仅两个领域、两个候选对及四类事实，真实集成仍需独立授权和 provenance 适配。外生反馈使对照可控，但不测量动作产生信息的因果价值。

## NEXT_DECISION_RECOMMENDATION

建议 Architect 先审查独立 verifier、合成 trust root 与评分/指标定义，再决定是否接受离线切片证据。若随后推进真实接入，应单独约定可见反馈来源及序号、候选快照、domain-scoped UNKNOWN 控制边界和真实成本模型；本任务不授权该接入或 RPF-74 恢复。

## POTENTIAL_GENERALIZATION_DEBT

事实键数量不是预期信息增益；没有经校准的获取模型、多值置信度、真实因果反馈或跨 session 认证。B1 只消融评分，仍保留相同反馈安全检查；不等同于完全无观察 Agent。Source identity 绑定 exact raw byte layout，Git LF blob 与 raw identity 分开保存；不同 CRLF checkout 不能只凭 commit 相同直接声称可复验。本轮没有证明任意 clean checkout 的可移植性。

## 范围与交付边界

CURRENT_STATE：当前只有新分支上的离线策略、合成对照与离线验证；未修改 canonical Project State。TARGET_INTENT：真实 Explorer 在三合同、有限预算及权限内选择，再由真实 Target 和独立 Authority 证明效果，保持不变。RPF-74/rev-4 的源码和私有证据没有被读取、提交或重签为本任务证据。

本任务最多同时运行 2 个聚焦 Python 进程，未启动子服务。G0 保守计时起点 2026-10-28T11:57:00Z，首次 clock 实测 11:58:39Z；截止 19:57:00Z。本报告封存时距 6 小时实现窗及 8 小时总限均有余量。日志、冻结、原始 trace、负控变体及开发失败输出保留在任务私有根，没有清理旧目录或复制旧 Run。报告不记录秘密或用户私有绝对路径。

最终 evidence commit/push/readback 完成后，以本次对话的最终 SHA 和 task-owned delivery receipt 核验交付；不为写入报告自身 SHA 额外 amend 或增加第三次提交。`TASK_COMPLETE`、`EVIDENCE_ACCEPTED`、`STAGE_ADVANCED` 仍由 Architect 决定。
