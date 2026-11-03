# TASK_RESULT — RPF-86/rev-4

Status: PARTIAL

Decision: B_UNACTIVATED

Base/main: `0d6c5c034e611b529af90c66b495f19eaa8b2df8`。限定实现与本轮 bounded forensic work 已完成；RPF86 整体和严格五方法准入仍 PARTIAL/FAIL。A08/A09 为 NOT_RUN_AT_SEAL，未来普通 Push/远端/hosted 收据仅最终聊天补充，不 amend。

## 主要发现

唯一新原生诊断 PID 20872，耗时 49.592s /120s，exit1，无 timeout/truncation，子进程已退出、输出排空。原五方法均 PASS；但 **两次 open/read 在 import 阶段、任何 method start 前被 READ_SCOPE_DENIED 拒绝**。两次已 fsync 的事件位于 journal seq1/2，原代码 caller 为 `ci/run-rpf86-owner-admission.py:native:471` 的 `importlib.import_module(MODULE)`。目标分类为未授权仓库路径，目标本身未被打开；没有许可导出其原始路径。两次不是本次原方法 broad assertion 中的拒绝，不能据此认定原攻击方法假绿。更深的导入调用者/目标确切身份 UNKNOWN；未读未列举这些目标，也未扩大白名单。

14 帧 chain 包含 INIT、2 DENY、5 START/STOP、terminal FAIL，raw SHA `08801af7f7b277f7517d5c0419706cb17312794291056aa6277828474c54d851`。五方法 PASS 不抵销 Guard denied；正式 native NOT_RUN，未运行聚焦复验、未再次诊断、工作流保持 blob `fe060ccb918acd318ff1b542cc6ece597a80d424`。

这些是 rev4 新运行事实，不能重建 rev2 原生现场。旧 rev2 两次拒绝只有计数，rev3 超时没有封存 journal；数量一致不证明同一原因。旧报告及旧 private owner 全部保留且未访问。

## 验收与实现

| Gate | 实际标签与证据 |
| --- | --- |
| G0/A01 | PASS：265 项现场检查、真实 Git HTTPS/Base、ACL/owner/privilege/casefold/空占及全部源码/证书 pin；三份实际 Base raw snapshot |
| A02 | PASS：预开合法 fd、重要帧 write-all+fsync；真实拒绝后 child exit7，另一进程仍恢复有效前缀；timeout 无 terminal 不算零拒绝 |
| A03 | FAIL：诊断 5 PASS+2 durable denied；正式 native NOT_RUN |
| A04/A06 | PASS：冻结后正式 23/23 单测，原16 IDs/实质断言保留；部分写、fsync异常、并发写、撕裂/seq/pid/source/caller/raw-path/overflow 与旧安全控制真实执行 |
| A05 | PASS：独立进程读真实 journal/report/receipt/log/source/manifest，8 份新 WAL 原逻辑 owner=rpf-63；没有重跑方法 |
| A07 | PASS：B，工作流原字节保持，不激活 hosted pilot |
| A08/A09 | NOT_RUN_AT_SEAL：只授权一次普通 Push；pilot NOT_APPLICABLE，CI 真实结论后续观察 |
| A10 | PASS：1232 required/539 UNAVAILABLE 不减；无 release/deploy，未取得 Architect 的 Evidence Accepted/Stage Advanced |

正常 native `run_suite` 不安装逐行/global trace，仅真正拒绝时做有限帧元数据归因。旧 synthetic broad-assert 因果控制保留局部明确 trace 并恢复；性能 microprobe 只比较相同算术调用在 Base global trace 与 no trace 下的 7 组样本，不把新49s与旧180s超时当作 tracing-only 因果实验。CPU profile NOT_RUN，无猜测倍数门槛。

每重要帧含 seq/前帧 raw hash/pid/monotonic/源 SHA/运行 identity，拒绝在 PermissionError 抛出前真实 fsync。单写者/32帧/每帧16KiB/最多16拒绝；失败或 overflow 不可准入。真实 syscall 的 fd write/fsync 未产生递归 Python audit open；测试验证 partial write-all 与 fsync failure fail-closed。磁盘有效字节前缀不是硬件断电/任意 native syscall/内核 sandbox 完整性证明。

## 冻结、资源与边界

冻结后正式 unit 恰一次：exit0、10.669s；独立 verifier 恰一次：exit0、0.971s。native开始至正式结算 wall=349.695s/cap480s（包含其间调查与准备）。所有启动子进程实际退出并排空；未超限。

独立核验使用本轮 task-owned、另行冻结的只读脚本，完整源码和 hash 嵌入 [verification-diagnostic.json](verification-diagnostic.json) 供审查；没有 import 原测试方法，没有修改冻结 harness。CLI `verify-failure` 分支本轮 NOT_RUN，不作为已验证入口。独立进程读取同一次现场，不是第三方 Issuer 或新环境重现。

冻结前首次23项控制有1项失败：microprobe 在安装 Guard 后读取自身 harness，触发正确拒绝。改为在安装前读取本来已授权的精确源码并仅持有 hash 后，第二次23 PASS；原失败日志/收据保留，没有宽目录许可。诊断之后只把通用 native runner 限额收紧为120s，随后冻结；未重跑原生诊断。所有源冻结前 AST/compile、strict JSON、snapshot raw/LF、diff check 已执行；B 无新 YAML/Bash。Windows目录 fsync UNAVAILABLE，文件 fsync 实际执行。

Provider0/Key探测0/真实SDK0/Java0/Docker0/实际业务HTTP0/生产写0/真实API费0。原Runtime/原方法/helper/证书、Router/matrix/RPF85、AGENTS/Project State/历史文件未改；docs/reviews 永久禁入，旧私有WAL/owner未读取或stat，暂停RPF74/RPF81未恢复。证书仍是精确单文件、只读、hash-bound，未复制或导出 SDK identity。

## 交付与建议

精确范围 **2M+11A**，同一 main，普通单次 Push；Git/CI 在报告封存时尚未执行，后续真实结果由最终聊天提供。详见 [denial-attribution.json](denial-attribution.json)、[performance-diagnostic.json](performance-diagnostic.json)、[counterexamples.json](counterexamples.json)、[preflight-diagnostic.json](preflight-diagnostic.json)。

后续若研究这两次 import-time 读取，应先明确可公开的最小目标元数据及权限，再判断是否是已授权模块解析的 instrumentation 问题。当前证据不支持开放目录、忽略 denied、降低覆盖义务或追加未经授权的 cohort。
