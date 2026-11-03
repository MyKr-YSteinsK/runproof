# TASK_RESULT — RPF-88/rev-1

Status: PARTIAL

Decision: **B_UNACTIVATED**。预试在 Guard 下未能导入目标模块，正式 18 方法 cohort 和其独立 readback 均 **NOT_RUN**。没有 18/18、没有新 Pilot admission、没有跨 lane promotion。

Base/main：`ed242f02cc3e40ac0a9f084619d4335a028bfbc6`。本报告在 Evidence Commit 前封存；A08 和既有 CI 结果为 NOT_RUN_AT_SEAL，最终完整 SHA、普通 Push、远端 blob 及 Run 收据仅在聊天回传，不回填或 amend。

## 已实现及来源

新增候选 harness 和 13 项控制测试，未修改原测试、OwnerScope、SourceCapsule、BudgetPolicy、Gate、SQLite 业务代码、Router/Handoff/RPF86/RPF87 或任何历史证据。原 `BudgetTests` 25 个方法及 class AST 逐字绑定固定 Git source；原矩阵为 24 DEDICATED_RUNNER + 1 WINDOWS_NATIVE。选择 exact 18 个 Dedicated，排除 6 个 `_config()` 方法及 junction 方法；[inventory](cohort-inventory.json) 保留所有方法、原路由、AST 与未执行状态。

候选仅实现子进程内 `OwnerScope.root` 描述符适配及 SQLite 连接目标准入，不替换原 SQL、结果、预算或断言。它包含原生 unittest durable STARTED/STOP journal、hash chain、有限 stdout/timeout、物理 manifest、第二进程只读 SQL 验证及严格脱敏投影；这些候选能力只经过合成/物理控制，**尚未在真实 R72 cohort 中验证**。逻辑 `owner=rpf-72` 可保留，但 workspace 合同字节会因 test-only 根改变，不能称历史合同完全相同。

源码闭包通过静态 AST/import 枚举，G0 记录 66 份现行公开文件，并追加 4 个 package init 的只读身份。候选实际 pin 64 份运行所需源码/公开固定材料（含矩阵），不加载 probe。公开固定 config-live-evidence 的原始 SHA-256 与 Plan 相符；未访问其私有兄弟目录、旧 SDK 或旧 task owner。SourceCapsule 原始代码未改；它的目标运行 observe/check 因导入失败 **NOT_RUN**。

## 真实失败与停止

唯一预试只安排目标模块导入与 setup 检查，没有选择或调用测试方法。真实 child exit **1**，错误为 `ModuleNotFoundError: No module named 'runtime'`，Guard 记录 `UNAPPROVED_PATH=1`、observed 为空，缓存与 work 为空，实际原测试方法数 **0**。没有生成正式 native、verify 或 cohort claim，未消费正式 cohort 来尝试越过拒绝。

后续独立 finder 控制只调用标准 `FileFinder.find_spec`，没有 import/执行目标包或原测试，实证它试图列举源码父目录，被 Guard 在实际 listing 前拒绝，返回找不到模块。这解释了预试观察到的导入失败机制；**预试本身没有保存拒绝的事件类型和目标，故原事件的精确归因仍 UNAVAILABLE**，不能把后续控制当成追补的原生事件。我们增加了后续候选的有界拒绝分类记录，未扩大 read roots、替换原 import loader、重新预试或运行正式 cohort。

预试尚未应用 OwnerScope patch，故报告中 descriptor_restored=false 表示恢复标记未到达，不能解读为原对象被改坏。预试 PID 与当时新 harness 的完整字节快照未归档，明确 **UNAVAILABLE**；真实 exit、时间、输出 hash、失败 JSON 完整保留。原测试及生产源码身份已独立复核保持不变。后续候选源码和测试先冻结，再正式验证，封存字节与 hash 均保留在本任务唯一新 owner。

## 验收与验证边界

| Gate | 实际状态 |
| --- | --- |
| G0 | PASS：206 项身份、固定 Base/HTTPS、空占、ACL、reparse、ignore、源码和副作用检查；一个前写入路径谓词工具错误已保留说明并更正，无旧根写入 |
| A01 | PASS：25/24+1、18/6+1、原 class/method AST、源码与矩阵 exact 身份 |
| A02 | PARTIAL / FAIL 原生准入：合成 descriptor/SQLite/路径控制通过；真实导入遭 Guard 拒绝；原对象适配未运行 |
| A03 | NOT_RUN：18 个原始方法实际执行 0，不能计 PASS/SKIP |
| A04 | NOT_RUN：无 cohort 可供独立验真；另有独立 B 诊断，不代替此 Gate |
| A05 | PASS（B）：workflow raw bytes 与 Base blob 完全一致，无新增 Pilot/artifact |
| A06 | PASS（控制范围）：冻结后 13/13；原 RPF86/87 纯 strict JSON 交界控制及源身份保留；未重跑其原方法或 RPF87 全部合成测试 |
| A07 | PASS（B 资源及停止）：一次预试后停止，正式 cohort/verifier 为 0；534 / NO_RELEASE 约束不变 |
| A08 | NOT_RUN_AT_SEAL：本次 0M+10A，后续单次 focused commit/普通 Push 与逐 blob 读回 |
| A09 | NOT_APPLICABLE（RPF88 未激活）；Push 的既有 CI 待真实观察，NOT_RUN_AT_SEAL |
| A10 | PASS（封存范围）：失败、限制、源身份、预算、旧覆盖与职责分离如实保留 |

13 项正式控制包括：精确 inventory/AST、描述符恢复、非法目标先拒绝再 metadata、真实 Windows junction、真实 SQLite callable/只读 URI、跨 owner/URI 参数欺骗拒绝、独立进程拒绝网络/DNS/进程/Key lookup、strict JSON/独占输出、journal 缺 final/错链/重锚拒绝、假 native PASS/timeout/PID/source/manifest/Guard denial/缺 SQLite 拒绝、public 投影不提升覆盖、原 CI 边界和 finder 拒绝。控制中的 SQLite 真执行仅属于合成夹具，不是原两个 `_order` 方法的业务证明。

预冻结 11 项、12 项、13 项控制依次通过；第二次有连接未关闭 ResourceWarning，已在冻结前用明确 close 修正并保留原日志。冻结后 13 项 child exit0、约 1.019 秒，unittest 自报 0.737 秒；非法 CLI 旧路径字符串实际 exit2，未启动 native child。独立 B 诊断进程检查日志字节、源身份、空 work/cache、未启动正式 cohort，以及任务证据大小在 64MiB 内；它不是独立 Issuer 或跨环境复现。

## 费用、保护与交付

Provider/真实 SDK/真实 Java/新 Docker/外部业务 HTTP/实际 Key 值读取/API 费用均 **0**。控制中有主动拒绝的负例，但在 DNS/连接/进程启动/Key mapping lookup 前被阻断；不把这些拒绝控制称为外部调用成功。原生订单 SQLite、UNKNOWN 后停写和 authoritative readback 在本轮 **NOT_RUN**，没有实际新业务写入。任意 native syscall 的整机级覆盖 **UNAVAILABLE**；只主张 CPython 界面与 SQLite 目标准入的控制结果。

未读/list/stat 旧私有 owner、WAL、marker 或 docs/reviews；未恢复 RPF74/81；未改 Project State、history、原 workflow、matrix、Handoff 或 Reconciler。正式覆盖仍由 RPF87 保持 **693 PASS / 5 SKIP / 534 UNAVAILABLE**；本轮不减少缺口。NO_RELEASE / NO_DEPLOY / STAGE_ADVANCED 未批准。

下一步建议：在新的审查中明确“标准 import finder 对 exact 源码父目录的 listing”是否及如何准入，或审查另一种不改变原 loader 的可证明准备方案；先建立完整拒绝归因再安排新预试。不要放开整个仓库读取或反复刷新本轮 owner。
