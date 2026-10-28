# TASK_RESULT — RPF-76 / rev-1

Status: Partial（本报告封存时：实现、离线评价、源码提交/推送/双读已完成；最终 evidence commit/push/readback 尚待执行。Plan §8.5 允许最终交付回执补齐 A10，不为回填自身 SHA 再次修改报告。）

Plan ID：RPF-76 / rev-1；Base：`163cdff3fdd96d6de87fa0fc31d19295994dc86a`；branch：`codex/rpf-76-offline-pge-generalization-evaluation`；Owner：`rpf-76-rev-1`；ABI：`rpf76-offline-generalization-v1`。

实现了领域中立离线候选、预冻结完整合成 roster、独立 Stop/Eligibility Oracle、公平三策略对照及不调用生成器的 verifier。正式评价为 24 development + 12 exposed holdout、108 policy replays、182 decisions。128 个方法连续两次通过，78 个实际独立 CLI 负控全部拒绝，其中 12 个为组合重锚。

重要负结论：PGE 在 development / holdout 分别错失 2 / 1 次应继续探索的机会；holdout 汇总成本与基线相同，但少得到 1 个合成已验证事实。该实验不支持“PGE 普遍更强”。这类可信负结论不使完整执行的离线评价协议失败。

## Gates

| Gate | 状态 | 实际依据 |
|---|---|---|
| G0 | PASS | repo/origin、远端确切 Base/main、新 branch/path 不存在、24 CREATE_ONLY 路径、owner/忽略/非重解析点、AGENTS/产品合同、无 feature push workflow 均现场核验 |
| R76-A01 | PASS | 10 新源码 + 2 输入冻结；raw/LF/Git blob 与 source map 绑定；6 只读参考未改；source push、Git blob 与 GitHub API 读回一致 |
| R76-A02 | PASS | 开发 3 抽象域、holdout 3 新抽象域；候选 1～6；12 个事实键；权限/成本/风险/前提/时间/域内 UNKNOWN/空池/重复有实际正反例 |
| R76-A03 | PASS | 完整 roster 作为预冻结输入；拒绝自算 digest、伪 VERIFIED、越域、未来、迟到、错合同和重复记录；弱信任等级明确 |
| R76-A04 | PASS | Oracle 不接收 Decision；verifier 独立重算；dev-01 等反例被计为机会损失，停止/不确定分母分开 |
| R76-A05 | PASS | 24/12 split 不重叠，新域和候选形状；输入/规则/源先冻结，holdout 曝光如实标注；三策略逐例表和负结果齐全 |
| R76-A06 | PASS | 原始 trace CLI 0/2/3；来源、可见记录、candidate、Oracle、状态和指标独立重放；公开原字节归档再次 exit0 |
| R76-A07 | PASS | 78/78 真实 CLI 负控 exit3，12 个组合重锚；每项原始/变体 SHA、PID、exit、reason、日志 SHA 均保留，未接受关键攻击 |
| R76-A08 | PASS | 冻结后两次 128 tests exit0，0 failures/errors/skips；不同候选/记录迭代顺序的两次完整 replay raw SHA 一致 |
| R76-A09 | PASS | 五项工程判断及局限已记录；旧 RPF-74/75、canonical Project State 和 main 未改 |
| R76-A10 | NOT_RUN（最终 evidence 部分） | Source commit/push/Git + GitHub API blob 核验 PASS；报告封存后的 evidence commit/push/最终双读由最终交付回执补齐 |

## Source、输入和实际命令

Source identity：`7f1d22ed4a269aec4af210c5e5bf50803622b9f7784582f6a30061bf25007d37`。Source commit：`6af54dd28a5e6ba890e6f84542306f2c8c8f2b46`。正式测试前 freeze，之后未改 12 个源/输入文件。18 个源/参考 Git LF blob 均匹配冻结清单；GitHub API 独立读回 contracts blob `f8f8ac77838bbf3c198ea7e3d337683aa5413754`，字节 SHA 匹配。报告不参与自身 Source digest。

Development seed=7601，24 个手工案例，domain 为 lab-amber / lab-bronze / lab-cobalt，候选形状 1～4。Holdout seed=7602，12 个手工案例，domain 为 lab-quartz / lab-nova / lab-opal，候选形状 5～6。每 case 12 个事实键，split case IDs 不交叉；种子只是可复验身份，不表示总体随机抽样。

Development raw SHA：`8a7ecf764bd16a17832eebf099486613300d8af2a877497309af1fe8f2d6d36b`。Holdout raw SHA：`80313d60ec288fa54c7547012e0dde6f2489fdabd2f6002a68a604b38b8cf577`。两份输入自创建起未改变。任务自身编写生成器，标签不是未知，因此标 `HOLDOUT_EXPOSED_NOT_BLIND`；未根据 holdout 结果调参或删除个案，不声称首次独立盲测。

规则、Oracle、指标和最终 source 在 2026-10-28T12:49:48Z 冻结；首次正式 holdout replay 从 12:50:02Z 开始。Policy 接收当前可见投影和完整冻结 roster，不接收 outcome 或 utility 标签；Oracle 只接收冻结 case、当前 records 和决策前状态。三策略拥有相同 pool、预算、权限、风险、外生可见时序和 outcome 查找时序。B1 仅消融评分反馈，不是完全无观察 Agent。

最终测试命令：`python -X utf8 -B -m unittest discover -s runtime/tests -p test_effectwitness_pge_r76.py -v`。两次 128 tests，unittest 用时 2.239s / 2.233s，进程墙钟 2.462s / 2.470s，PID 29988 / 16984，exit0。stderr SHA 分别为 `ed59aa35ac27c43d9362c3a59b0a87c80de78f8f932fcb2495c113161dea9ca7`、`883df26d75ed86ac1e0430e4793516b00be39d545bf026e924956458c6b1dd29`。

开发初次 126 项测试有一项失败：repeat guard 测试先遇到已构造的反馈冲突，因此断言未到达目标分支。冻结前改用无冲突的独立场景后通过；随后新增迟到原因和输入固定性测试，128 项通过。原始失败 stdout/stderr 保留。三个早期开发测试进程的 PID 未捕获，明确 `UNAVAILABLE`；不以事后推断补填。

两次正式 replay（PID 28076 / 23680）分别使用常规与反向候选/记录迭代顺序，raw SHA 均为 `4c05d2ea0b67b6fdef1e104f73c4952607c5bfe8336d6d170871fb9b0ac55e1a`，各包含 108 runs / 182 decisions。公开 decision-traces.json 是第一次实际输出的原字节归档，不是历史 Run 复制。

`probe.py verify` 的正确/缺/错原始 anchor 退出码分别 0/2/3（PID 20744 / 5932 / 13144）；公开归档复验 PID 31056、exit0。全部正式命令、PID、单调时间、exit、stdout/stderr SHA 见 runtime-diagnostic.json；CLI 不允许任意用户文件路径。

## 独立停止与公平对照结果

Oracle 的 MUST_STOP 来自当前域 UNKNOWN、时间/步数限额或不存在合法候选；SHOULD_SELECT 来自仍未尝试的合法、预标 worthwhile 候选；证据冲突/不足或无预定 fresh utility 时为 INCONCLUSIVE_ALLOWED。这里的 worthwhile 是预先规定的合成规范目标，不是实际业务真值或最优停止定理。

| split / policy | 合法 SELECT / SELECT | 模拟成本 | 已验证事实 | correct_stop / total_stop | 停止不可判断 | 机会损失 | unsafe SELECT | 合理 INCONCLUSIVE / INCONCLUSIVE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development / PGE | 12/12 | 30 | 16 | 14/18 | 2 | 2 | 0 | 6/6 |
| development / B0 | 18/18 | 42 | 20 | 16/16 | 0 | 0 | 0 | 8/8 |
| development / B1 | 18/18 | 42 | 20 | 16/16 | 0 | 0 | 0 | 8/8 |
| holdout / PGE | 8/8 | 21 | 9 | 8/9 | 0 | 1 | 0 | 3/3 |
| holdout / B0 | 9/9 | 21 | 10 | 8/8 | 0 | 0 | 0 | 4/4 |
| holdout / B1 | 9/9 | 21 | 10 | 8/8 | 0 | 0 | 0 | 4/4 |

PGE development 的 determinate stop correctness 为 14/(18−2)=14/16；另有 2 次 STOP 标 NOT_DETERMINABLE，没有被自动算正确。Holdout 为 8/9。原始 total_stop、每个错误和每个不确定都保留，不用单个“成功率”掩盖分母。所有 SELECT 的安全准入合法，不表示策略选择最有价值；浪费可由成本、重复和冗余反映。

可复验反例 dev-01：当前合法且预标值得评估的候选仍未尝试；PGE 由于其 effects 键已出现在可见反馈中，预计新键 gain=0 而 STOP。Oracle=SHOULD_SELECT，新指标 correct_stop=0、missed_opportunity=1。按 RPF-75 的形式化终止计数思路会得到 1/1；这不是对历史原件重新验收或改写，而是演示旧定义缺少独立正确性判据。

与 B0 的逐例 facts/cost Pareto：development 有利2、持平20、取舍2；holdout 持平10、取舍2。没有 pure unfavorable 个案不代表总体改善：holdout 两个取舍相抵后，PGE 成本同为21但事实9<10，汇总对 PGE 不利。全部 case 的 cost、事实、重复、冗余、拒绝、Oracle 错误和分母见 evaluation-report.json；终止逐条审计见 stop-oracle-audit.json。

“已验证事实”指被 SELECT 的 VERIFIED 合成 outcome 中独立 `(key,value)` 对；预计 gain 指决策前未知事实键数，两者明确不同，不是熵、已取得的信息增益或真实安全收益。外生反馈不证明动作导致信息，手工暴露 holdout 不证明统计显著泛化。

## 负控、资源与未运行

76 个内置变体中 64 个单项、12 个组合；额外 2 项覆盖 row hash 次序及重复候选快照。78 个变体均通过普通 Python 启动独立 `probe.py verify` CLI，实际 exit3、machine reason 已归档。每项有原始/变体 raw SHA、PID、耗时和 stdout/stderr SHA，原工件未修改。组合项各改两个语义字段，再对所供 roster、row 链和 result 重锚；其中一项还重算 candidate contract/snapshot，不能称为攻破第三方签名。row hash 次序项保留错误前驱并重签外层，实际被 ROW_HASH_ORDER 拒绝。

控制覆盖 false/0、候选次序及非法重名/跨域/ID、伪 VERIFIED、自签 roster、跨 case、未来/迟到、UNKNOWN 继续选择、错误 STOP/机会损失归零、Oracle 标签/分母、来源/anchor、holdout 分割、重复原记录和成本等。内置 `negative` 只产生 PREPARED_NOT_EXECUTED；独立 CLI 回执完成后才记 PASS。逐项见 metamorphic-controls.json，没有把计算预期当执行结果。

正式 recorder 记录 88 个 Python child，实测最大同时 child=2，加各自普通 Python recorder parent 后总并发上界4。所有局部正式命令均少于180秒、无 timeout；并未声称完成宿主全量进程盘点。开发日志、所有变体、freeze、原始轨迹保留，私有产物约58MB，未清理旧任务根。

Provider、真实 token、费用、Key 读取/存在性探针、SDK、JVM、服务/端口、真实业务写入均为0。旧完整 Runtime 为 NOT_RUN_BY_PLAN；真实 Agent/Target/Authority、第三方 Issuer、L2/L3、跨平台任意 clean checkout 复验为 NOT_RUN / NOT_ESTABLISHED。无网络代码、浏览器、Docker、故障注入、安装或下载；外部操作仅授权分支 Git 与 GitHub readback。

G0 首次 clock 为 2026-10-28T12:37:47Z；首条进程单调时间观测为7677.1806935，对应12:37:52.986641Z，差额5.986641秒单列，后续共用同一账本。总 deadline 为20:37:47Z。实现、freeze 和正式评价均在前6小时内完成；最终交付仍须在8小时内，回执记录最终时刻。

## VERIFIED_FINDINGS

泛化 schema 在6个抽象域、1～6候选及12事实键上实际重放；domain-scoped UNKNOWN 不误伤独立 domain。完整预冻结 roster 能拒绝待验证输入的自算 digest；独立 Oracle 和 verifier 识别出原先“所有终止均正确”的反例。已验证的是闭世界一致性和规范标签下的停止评估，不是现实来源真实性。

## CODEX_ENGINEERING_JUDGMENT

本轮最重要成果是可见的负评价，而非策略胜率。新策略50行，Oracle22行，全部10个 Python 源/测试/CLI 共1178行。PGE 的按事实键计 gain 过于粗糙，无法正确判断事实值更新或新实验价值；holdout 已出现相同成本更少事实。该策略适合离线研究接口，不宜凭这些结果直接作为真实控制器决策。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

选择有限纯函数及显式规范 worthwhile labels，而未引入模型、推断置信度或业务适配，便于逐项审查和受限输入测试。Oracle 与 verifier 各自重算，但共用合同概念/常量，仍可能存在共同建模错误。B0/B1 的安全准入相同，评估差异集中于排序与停止；规范 Oracle 不要求 SELECT 最优候选，只判准入和停止机会，最优性仍未测。

## NEXT_DECISION_RECOMMENDATION

建议先由 Architect 审查 utility 标签、停止分母及 holdout 负结果。后续若继续策略研究，可单独设计未被开发者看到的外部案例，并明确“值得继续”的业务目标、价值更新及预算权衡，再决定是否推进真实 Explorer。RPF-74 恢复、Web Lab 或新真实域接入均需另行授权，本任务不启动它们。

## POTENTIAL_GENERALIZATION_DEBT

抽象域仍是小型手工数据，不代表第三真实业务域；normative label 不等于独立业务 Authority。Roster 真实性、跨 session 认证、动态候选可见性、经过校准的信息获取模型和动作因果效应仍缺失。Source identity 绑定 exact raw byte layout，Git LF blob 单独核验；CRLF 转换仍可能改变 raw identity，没有任意 clean checkout 可移植证明。

CURRENT_STATE：新分支上的纯离线泛化/评估切片，canonical Project State 未改。TARGET_INTENT：真实 Explorer 在三合同与权限预算内选择，由真实 Target 和独立 Authority 证明效果，保持不变。main 及 RPF-75 branch 原 ref 未变，RPF-74 草稿仍暂停、未纳入 stage/commit。最终 evidence SHA 及 A10 完成事实以封存后交付回执为准；不声称 TASK_COMPLETE、EVIDENCE_ACCEPTED 或 STAGE_ADVANCED。
