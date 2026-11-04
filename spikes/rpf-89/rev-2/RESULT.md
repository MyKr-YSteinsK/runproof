# TASK_RESULT — RPF-89/rev-2

Status: PARTIAL

Decision: **B_UNACTIVATED**。固定 Base/main 为 `7e12a7b6b2315977b975ec42672cbf101c37bf19`。实际交付范围 **2M+10A**；原 workflow 恢复 Base 原始字节，未激活 RPF89。A08 和 Push 的既有 CI 尚为 NOT_RUN_AT_SEAL；最终 SHA、远端 blob 与真实 CI 结果在聊天补充，不 amend 本报告。

## 实现与来源

在两个获准 Python 文件中实现了 rev-2 候选：同 job 的 post-completion stamp、原 RPF87 enforce 重验接口、RPF88 私有 report/receipt/hash/journal/manifest 与只读双库验证、exact 18 项原子派生、两个独立 Barrier 的 workflow 候选。它保留原 RPF87/RPF88/Router/Handoff/Matrix/Runtime 及旧报告，未执行原 18 个方法。rev-1 的 12 项控制保留原义；旧 diagnose 仍只描述 RPF87 原生完成字段缺失，不能冒称成功。

Checkpoint 的含义是：同一 Actions job 中 RPF87 成功后再次接受只读重验的观测，scope=`POST_COMPLETION_OBSERVATION_NOT_RPF87_NATIVE_FINISH`。它不是 RPF87 原进程自身的完成时刻，也不是独立 Issuer。候选要求同 Run/attempt/SHA/job、旧 enforce exit1、旧结果和源码 hash、stamp 早于 native 启动、PID 分离和原子十八项。Hosted 入口还要求已激活 workflow 的身份。B 恢复原 workflow 后，候选不会在现有 CI 中执行。

RPF88 纯验证函数按固定源载入，未启动其 run/native/verify。模块局部的 manifest reader 将读入限制到明确文件及受控父目录，模块局部 SQLite namespace 只接受已核对的两份 DB 的 exact `?mode=ro`，不改全局 sqlite3 或原 SQL。WAL 校验覆盖字节链、owner/time、真实资源拒绝和 UNKNOWN 后新写拒绝；它不是对故意 crash/orphan 测试做一次正常业务 replay。两库相同字节冒充两个独立来源会拒绝。

## 真实验证与失败

G0 144 项检查通过，实际 main/remote、Base、8 pins、空占/ignore、ACL、非 reparse 和 push 副作用已核实。预冻结的 24 项、扩展 32 项、随后 6 项聚焦与 2 项小检查分别实际通过；这些只是各版本预冻结证明，不能代替最终正式全套。

首次冻结前 `diff --check` 发现 Python 文件 EOF 多余空行，冻结收据尚未产生、正式测试尚未启动。保留 attempt01 快照与错误说明后，仅去掉多余行末，完成 attempt02 正式冻结：AST/compile/显式 owner py_compile、将 YAML `on` 按字符串处理的结构验证、原步骤语义及授权增量、正确转换 GitHub 表达式后的实际 Bash `-n`、diff check 均通过。

**冻结后正式 35 项测试在 300 秒上限超时，整体 FAIL。** 实际已完成 10 项 PASS；`test_missing_checkpoint_and_missing_native_reject` 已启动但没有完成；24 项尚未启动。原始日志没有记录断言 FAIL/ERROR，但这不等于其余测试通过，也不能将超时改签为工具成功。测试 PID9804 已退出，恢复时检查其存活和直接子进程数量均为0。超时的具体性能原因 **UNAVAILABLE/未查明**；没有归因于断言错误、暂停、重启或某个未经证实的环境原因。

用户暂停后从同一实际 owner 恢复，三项冻结哈希全部匹配。遵守 Plan §5“冻结后失败原样保留，不改源码重签旧 Witness”：**未重跑全套、未延长300秒预算、未修改两份冻结 Python**，转为 B。仅按明确 B 合同恢复 workflow Base 原字节；冻结 A workflow 副本及其哈希仍保留，因此这不是静默改写失败候选。

独立 Python 只读 B 收口核对 exit0，确认冻结 Python、保留的 A workflow、当前 Base workflow、正式 timeout 以及当前唯一 owner 约20MB、低于64MiB。它还核对了已完成的正式合成 CLI 局部正例：1232 个唯一 IDs，五项旧准入不变，exact 十八项变化，其余1214行不变，模型为711 PASS/5 SKIP/516 UNAVAILABLE、Dedicated394、CLI exits0/1/2。该 fixture 的 checkpoint 明确 synthetic=true / legacy_verified=false；原 RPF87 上游执行是局部模型，两个短生命周期 Python 仅提供控制元数据，原测试事件是合成协议。**该局部核对 PASS 不是 A06 全套 PASS，更不是 hosted 准入。**

## Gate

| Gate | 实际状态 |
| --- | --- |
| G0 | PASS：现场144项；恢复时 Base/remote、冻结哈希及残留进程重新核实 |
| A01 | PASS（静态范围）：固定源、公开1232 inventory、5+18映射；同 Run 原始执行重验尚未发生 |
| A02 | PARTIAL：合成 stamp/身份/时序/拒绝与 dispatch 控制有通过记录；真实 hosted stamp NOT_RUN |
| A03 | NOT_RUN：未实际重算 hosted RPF87 私有链；本地上游是明确标识的模型 |
| A04 | NOT_RUN（hosted）；局部 synthetic physical/SQL 控制仅在预冻结或正式已完成部分得到验证 |
| A05 | PARTIAL：局部合成711/5/516已观察、差集独立检查；正式新覆盖未生成 |
| A06 | FAIL_TIMEOUT：35计划、10完成PASS、1未完成、24未启动；没有全套PASS |
| A07 | PASS（B停止与范围）：0新增外部资源、失败不重跑，workflow Base恢复，原Gate未降级 |
| A08 | NOT_RUN_AT_SEAL：2M+10A待普通commit/push与读回 |
| A09 | NOT_APPLICABLE（B不激活）；普通Push的既有CI待实际观察 |
| A10 | PASS（B封存范围）：失败、版本、未跑、来源与最终Git职责分离 |

完整负控设计见测试源码与 counterexamples；已完成、仅预冻结通过、未完成及未启动分别列明。没有把设计目标、测试函数存在或相邻旧证明当成本轮正式 PASS。

## 覆盖、资源与交付边界

正式覆盖保持既有 **693 PASS / 5 SKIP / 534 UNAVAILABLE**，原 Router 688/5/539不改；本轮新增正式准入0。711/5/516仅属于本地合成局部正例。没有新 hosted stamp/assess/派生artifact，不能称 Stage Advance、真实 Agent/Provider、独立 Issuer 或外部盲复现。

本任务新增 Provider/真实 SDK/Key lookup/Java/新Docker/外部业务HTTP/API费/真实业务写均0；仅新 owner 内 synthetic SQLite 与元数据控制。未读取旧 .local owner/WAL/marker、docs/reviews、用户草稿或恢复 RPF74/81；未更改旧证书、Source Map、Runtime、Project State 或历史报告。部分控制使用新 owner 自己创建的 junction/hardlink，留存但不跟随到其它目录。

Git交付只保存冻结候选代码、可信失败和新rev-2报告，workflow不进入差分；不force/amend/rebase/tag/merge/deploy。旧RPF87真正的always enforce仍保留，NO_RELEASE/NO_DEPLOY。

下一轮建议先审查此次正式测试的执行开销和超时收据，再决定是否授权新的冻结候选或按方法有界验证。当前计划下不通过清理 owner、扩大预算、修改失败源码或重复CI获得表面PASS。
