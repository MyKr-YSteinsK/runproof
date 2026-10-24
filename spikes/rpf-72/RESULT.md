# TASK_RESULT｜RPF-72/rev-1

Status: Partial

本轮停在父级原生启动接缝。Windows `Popen` 在审计事件前已用 `list2cmdline` 把 argv 转为字符串，新候选代码按列表比较，因此实际原生 Driver 在创建 child 前抛出 `NATIVE_CHILD_ARGV`。Plan §5/P3 要求 Source Freeze 后不得编辑已证源码；本轮保留失败 Source，未更改此检查，也未启动正式 N/F。`BUDGET_PARENT_CHILD_CONTRACT_EXECUTED=NO`。

旧 child 的六个成功压力样本执行了净化子环境的 Key 存在性检查。宿主凭据读取为0，但不能宣称严格的“从头到尾 Key 环境变量 lookup=0”；R72-A08 保留 FAIL。没有 Provider 调用、真实token或API费用。

## CURRENT STATE

已实现候选 OwnerScope v1.2、不可变 BudgetPolicy/ParentChildBudgetContract、唯一 native WAL 的 Policy gate、父级审计/profile 接缝与离线 Verifier。固定 SDK 的独立组件成立，原生运行接缝未成立。工程未完成，Architect EVIDENCE_ACCEPTED/STAGE_ADVANCED 均 PENDING。

## TARGET INTENT

新 Policy 应成为 child 累计预算的唯一授权来源，启动前严格比较实际 cfg，实际 serialized-input digest 与 child PID/ready/report/WAL 联结。候选方案不改原 Driver/child，只给其现有字段加父级授权；由于 Windows argv 检查失败，本轮尚未证明这条原生授权链。

## PLANNING CONTEXT

Repo `MyKr-YSteinsK/runproof`；Base `ed346dea7fc46fc289853ea673bfe100f8d0d8b7`；新分支 `codex/rpf-72-parent-child-budget-contract`；源码提交 `8bfc09022e8e7d159a5de289040b22441713bd7a`，已普通 push，并由 Git/API 双读同 SHA。main 保持 `bda0cd49e50e3181f604324e94877a24b9885334`，父分支保持 Base。当前报告生成时最后回执尚未提交；最终回执 SHA、22条 create-only 路径及远端双读在最终聊天回报，不以文件自记自身 SHA 形成循环。没有 PR、merge、tag、release、workflow dispatch、部署或赛事上传。

源码 frozen identity SHA `46295f001bf0b1e9c386186fc714107e0b62c1dc98b50bc8a71b7fd0ff65b569`；59条闭包 raw/LF 与 Git blob 已逐条比对。新源码冻结后未编辑，12条 source/test/probe 已按原始字节暂存与提交；10条文档/诊断随后形成此回执。原 tracked 文件修改0。完整身份、SDK/JAR pin、原历史 raw 与 helper SHA 见 [source-identity-map.json](source-identity-map.json)。固定 SDK 为 Python3.12.13/PydanticAI2.57.0/OpenAI3.35.1，父进程为 Python3.14.6。

## Gate

| Gate | Status | Evidence / limitation |
|---|---|---|
| G0 | PASS | Exact Base; 22 paths absent locally/index/Base/API; fresh ignored non-reparse root; protected paths preserved |
| R72-A01 | PASS | 59-entry raw/LF closure; typed Owner/Source/Policy; source and policy drift focused negatives; committed raw bytes checked |
| R72-A02 | PASS | Strict immutable domain contracts 250000/160000; 25 focused and 40 pure cfg negatives |
| R72-A03 | FAIL | Eight fixed SDK components pass, but actual native launch is rejected by Windows string argv versus frozen list comparator. No accepted native config/serialized-input/report binding |
| R72-A04 | PASS | Focused physical native WAL reserve/settle parity, direct bypass, orphan, torn receipt, UNKNOWN and SQLite fixture tests pass; no formal-session claim |
| R72-A05 | NOT_RUN | N/F withheld after mandatory A03 runtime failure; no formal business scene or corrective attempt |
| R72-A06 | NOT_RUN | 24 historical entries plus R69 0/2/3 pass; pure cfg 40/30. Manifest semantic 0/140, child-budget manifest 0/65, deep coupled 0/4, new valid-manifest CLI absent |
| R72-A07 | NOT_RUN | Source frozen and 25 focused pass; full Runtime NOT_RUN after mandatory execution gate failure; cannot claim >=546 |
| R72-A08 | FAIL | Provider/host-credential reads/real tokens/API fees are zero; unchanged child executes six sanitized-environment Provider-key presence probes. Literal no Key environment lookup condition is not met |
| R72-A09 | NOT_RUN | Controller/SDK/no-attestation levels implemented, but formal SDK proof/manifest tampering coverage not executed |
| R72-A10 | NOT_RUN | Source commit pushed and Git/API double-read; this report commit and final 22-path delivery double-read are reported in final chat after publication |

A10 的 NOT_RUN 是本文件生成时的最终报告提交/双读状态；源码交付已完成，最终聊天给出回执交付实况。本轮总体仍 Partial。

## 真实固定 SDK 与原生失败

| Domain | Case | PID | 合成 total hint | SDK result |
|---|---|---:|---:|---|
| config-java-http | limit-equal | 6948 | 250000 | COMPLETED |
| config-java-http | legal-high | 3484 | 84600 | COMPLETED |
| config-java-http | limit-minus-one | 13404 | 249999 | COMPLETED |
| config-java-http | limit-plus-one | 21608 | 250001 | UsageLimitExceeded |
| order-sqlite | limit-equal | 5264 | 160000 | COMPLETED |
| order-sqlite | legal-high | 16836 | 54580 | COMPLETED |
| order-sqlite | limit-minus-one | 13992 | 159999 | COMPLETED |
| order-sqlite | limit-plus-one | 25788 | 160001 | UsageLimitExceeded |

八个 child 均使用固定原件及原 Guard、仅连接任务自有127.0.0.1。legal-high 两域84600/54580，跨过35000；输入上界加保守512输出界仍在对应槽 cap 内。limit-minus/equal/plus 刻意让最后 usage hint 超槽，仅用于 SDK 累计阈值，不属于合法 Provider 预约。减1与等于完成；加1在 SDK_RUN 阶段产生真实 `UsageLimitExceeded`。成功六例报告的是合成 RunUsage；失败两例只有不可信 scripted hint，没有编造已完成 RunUsage。

组件 Controller 生成并验证 cfg，记录 raw SHA 与实际发送 bytes SHA；旧 child 没有回显 cfg digest，不能宣称 CHILD_ATTESTED。原生启动诊断 Run `rpf72-f08e69b696ebca32` 在 SDK创建前失败，child PID为空，Host端口关闭，SDK/Host各1张预约未结算；未补账、未重试、未创建 JVM/DB/业务 Adapter。其私有 WAL 保留于 `.local/rpf-72/tests/rpf72-f08e69b696ebca32/wal.jsonl`，raw SHA `bf0b0314e2fdd623ac9777ab873cf6c68a00ef53b26f41d083956f054180a4d6`。诊断进程 exit0 表示“预期阻断被复现”，**不表示 A03 PASS**。

## 验证范围与未运行项

聚焦一次25项全部通过，耗时110.97秒，0 errors/0 failures；未消耗第二次。包含实际物理 native WAL 的 reserve/settle、直接绕过、崩溃孤儿、UNKNOWN、junction 拒绝与两个独立 SQLite 单元 fixture。40项纯配置负控全部被真实校验器拒绝，包含阈值±1/35000/bool/float/负值、域、SDK pin、路径、token形状、字段缺失与增加；它们未调用 SDK，不能计为140项 manifest 语义负控。

正式正常 N=0、故障 F=0、纠错=0。正式 JVM/POST/refund=0；八个 SDK 压力组件业务效果0。两个 focused SQLite fixture 为独立测试虚拟退款，不充作 N/F。没有正式独立 Authority/ToolCall/WAL反馈证据，四态与UNKNOWN闭环不得冒认。完整 Runtime NOT_RUN，不能引用上一轮546项为本轮通过；Win parent3.12 full和Hosted CI NOT_RUN。140项manifest/65项预算面/4项深度耦合负控均NOT_RUN；新有效manifest CLI 0/2/3闭环也未建立。

原历史24入口重用各原始 SHA 与原生 CLI，全部exit0；R69原CLI0/2/3符合预期。R70/R71私有manifest均UNAVAILABLE，本轮未读取旧`.local`；仅保留已允许公开源码/身份的原字节回归。[history-regression.json](history-regression.json)保留每条命令。

每个组件、聚焦及历史命令的 argv/cwd/PID/start/elapsed/exit/log SHA/source-before-after 见 [verification-diagnostic.json](verification-diagnostic.json)。私有WAL、完整组件结果、日志和失败现场保存在`.local/rpf-72/`，不进Git。所有命令均保持同一 frozen identity。额外诊断 helper 与执行 Source 分开标注和哈希，未悄然替换 frozen runner。

独立晚次 Windows 只读查询确认八个 SDK PID均NOT_PRESENT、八端口均关闭；失败原生Host也关闭。进程创建时间及SID hash未在退出前采集，UNAVAILABLE；物理symlink创建返回WinError1314，UNAVAILABLE，未提权；junction在聚焦测试中实际创建并被拒绝。没有杀陌生PID，没有清理旧任务现场。

## 费用与权限

Provider calls0、宿主凭据读取0、真实token0、API费用¥0；净化子环境的Provider-key存在性检查6次，严格 Key lookup=0 不成立。474000是冻结槽表纯演算，不是发票或真实Provider usage。没有刷新官方价格。`SDK_GUARD_MIGRATED=NO`、`FULL_COMMON_CORE_MIGRATED=NO`、Issuer/L2未建立，第三域/Web/真实双Agent均NOT_RUN。

## VERIFIED_FINDINGS

1. Windows stdlib先序列化argv再发审计事件；实际原生路径证实字符串/列表不一致，错误为`NATIVE_CHILD_ARGV`，发生在CreateProcess前。
2. 原固定SDK累计限制机制有效：独立legal-high、阈值减1/等于/加1共8项均符合预期。不能据此推导原生Driver接缝成功。
3. 25聚焦和27历史CLI命令通过；已冻结59条Source raw/LF未漂移。没有本轮完整Runtime、N/F或manifest负控证据。
4. 旧child的Key存在性检查与本Plan严格零lookup有口径冲突；宿主没有凭据读取，不能隐去child检查事实。

## CODEX_ENGINEERING_JUDGMENT

根因位于Controller Windows审计参数形状假设，置信度HIGH。支持证据为stdlib执行顺序及真实原生诊断；反证是direct pinned SDK组件全部通过，故累计budget/SDK pin不是本次失败根因。最便宜的区分试验是在新修订冻结前修正平台参数规范化，并用无JVM/DB的原生launch component先验收，再启动正式业务。聚焦覆盖遗漏真实Driver启动，说明纯合同测试不足以给平台接缝放行。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

| 路线 | 安全与历史边界 | 成本与结论 |
|---|---|---|
| A 只读收口 | 保留失败冻结源，停止新SDK/业务 | 本轮选择；成本最低，可信Partial |
| B 窄父级Win argv规范化 | 严格保留executable/cwd/env/child pin及序列化比对，原Driver/child不变 | 推荐下一修订；需授权替换本轮冻结Source及增加启动集成测试 |
| C 新版本child回显capsule/digest | 扩大Guard/SDK审查面，历史原件仍只读 | 成本最高，本Plan未授权；仍不自动等于独立签名 |

## NEXT_DECISION_RECOMMENDATION

1. 新RPF-72修订授权仅修Win argv比对并新增冻结前启动smoke，使用全新Source身份、私有根和明确运行配额；不要在rev-1改冻结源。
2. 在再启SDK前明确是否允许净化子环境的Key存在性检查；若必须字面零lookup，则需另行授权新child路径，不能改旧Guard。
3. 满足两点后再安排完整Runtime、140/65/30负控与正式N/F。不会自动创建RPF73，也不把Provider、合并或部署并入建议。

## POTENTIAL_GENERALIZATION_DEBT

已证实：平台审计参数差异、聚焦测试缺少原生启动、Controller不能证明child独立见证、native cfg仍自行计算常量（Policy仅能通过相等门禁控制授权）。待验证：profile开销与未来显式Driver factory ABI能否减少栈耦合；本轮没有性能对照，不提出已测性能结论。

## 22条 create-only 交付路径

- `runtime/runproof_runtime/effectwitness/pge_r72_contracts.py`
- `runtime/runproof_runtime/effectwitness/pge_r72_owner_source.py`
- `runtime/runproof_runtime/effectwitness/pge_r72_capability.py`
- `runtime/runproof_runtime/effectwitness/pge_r72_budget_policy.py`
- `runtime/runproof_runtime/effectwitness/pge_r72_budget_ledger.py`
- `runtime/runproof_runtime/effectwitness/pge_r72_sdk_contract.py`
- `runtime/runproof_runtime/effectwitness/pge_r72_ports.py`
- `runtime/runproof_runtime/effectwitness/pge_r72_session.py`
- `runtime/runproof_runtime/effectwitness/pge_r72_verify.py`
- `runtime/runproof_runtime/effectwitness/pge_r72_migration.py`
- `runtime/tests/test_effectwitness_pge_r72.py`
- `spikes/rpf-72/probe.py`
- `spikes/rpf-72/README.md`
- `spikes/rpf-72/RESULT.md`
- `spikes/rpf-72/preflight-diagnostic.json`
- `spikes/rpf-72/verification-diagnostic.json`
- `spikes/rpf-72/parent-child-contract-matrix.json`
- `spikes/rpf-72/budget-negative-controls.json`
- `spikes/rpf-72/history-regression.json`
- `spikes/rpf-72/source-identity-map.json`
- `spikes/rpf-72/architecture-decision.json`
- `spikes/rpf-72/capability-assessment.json`

G0逐条初始不存在证明见[preflight-diagnostic.json](preflight-diagnostic.json)。原用户`?? docs/reviews/`仅在顶层status自然可见；未进入、列举、读取、哈希或暂存。最终公开URL由当前分支普通push后的聊天回执提供；私有本地路径不作为Architect可访问证据。
