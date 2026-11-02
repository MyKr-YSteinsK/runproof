# TASK_RESULT — RPF-86/rev-3

Status: PARTIAL

Decision: B_UNACTIVATED

Base/main: `8953f6a4f85a614c7cabf74903e4c7e1d89c45dd`。本轮完成限定 harness 实现、安全负控、冻结和只读超时证据核验；核心两次拒绝的原生归因仍未取得，不宣称任务完整达成或五方法准入通过。

## 实际 Gate

| Gate | 结果 |
| --- | --- |
| G0/A01 | PASS：main/远端/Base、256 项有界检查、真实 ACL/casefold/reparse/空占、原源码/helper/证书身份 |
| A02 | UNAVAILABLE：唯一新诊断在第一方法达到 180s；内存 journal 未封存，两次历史拒绝原因 UNKNOWN |
| A03 | 正式五方法 NOT_RUN；本轮没有任何完成的原生方法 PASS 结论 |
| A04/A06 | PASS：冻结后正式 16/16 单测，原 12 IDs/原断言保留，exit0，4.557s |
| A05 | PASS_INCOMPLETE_NEGATIVE_EVIDENCE_ONLY：独立进程校验真实 timeout/PID/exit/log/snapshot、当前物理 manifest、4 份新 WAL 的逻辑 owner；没有补造 method/guard 事件 |
| A07 | B：workflow 完整 blob fe060ccb918acd318ff1b542cc6ece597a80d424 不变，pilot 未激活 |
| A08/A09 | NOT_RUN_AT_SEAL；后续普通 Push/远端 blob 与自动 hosted CI 由最终聊天单独报告 |
| A10 | 1232 required、539 UNAVAILABLE 不变；RPF86 overall PARTIAL，未取得 EVIDENCE_ACCEPTED/STAGE_ADVANCED/release/deploy |

## 实现与因果证据

新增最多 16 事件的内存 journal：sequence/reason/audit operation/intent、NativeResult start/stop 绑定的方法、call/return 绑定 phase、批准文件帧元数据 caller/实际行号、运行期加盐 target token。禁止输出任意原始拒绝路径、私有 owner 名称或证书/SDK 值。仅在批准源码上预计算 AST/源 hash，不调用 inspect.stack 或读取被拒路径。缺失/重复/来源漂移/伪造 caller/overflow 证据被拒绝；任何 Guard denied 仍使原生准入 FAIL。

合成独立负控实际展示 `assertRaises(Exception)` 捕获 PermissionError 后方法 PASS。trace 观察到 PermissionError 到达原方法帧、跨出 broad context 后继续运行，再由 NativeResult 记录 PASS；控制判定 admission FAIL。该结论只属于新合成控制，**不证明原 RPF63 历史方法已经发生同样假绿**。具体事件见 [denial-attribution.json](denial-attribution.json)。证书单文件读及目录/兄弟/写/O_TRUNC/case、old-root open/mkdir/stat、进程/网络、reparse、日志/收据/source/事件等控制保留。

## 唯一原生诊断与停止

子进程 PID 14792，实际 180.022s，timeout=true、exit=1、truncated=false、child_exited=true、drain_joined=true。stdout 只有 `test_four_paths ...` 的起始行（90 bytes），没有完成行。没有 child-result.json，journal 在内存尚未封存；事件数量、具体原因、caller、方法 taint 均 UNAVAILABLE/UNKNOWN，不能把空列表算作零拒绝。原监督脚本在已保存 timeout receipt 后尝试读取缺失 report，真实 FileNotFoundError 保留在工具记录；没有重试 cohort。

全局 trace 每次调用构造 Path 的成本是超时的合理怀疑，但本轮没有性能对照，原因未被证实。诊断后仅在 harness 将无关调用早退移到路径解析之前，并增加严格的 incomplete-negative verifier；没有第二次原生诊断，也没有通过正式 native 绕开次数限制。原失败 harness snapshot、stdout、receipt、新 WAL 现场保留。

冻结前第一轮 16 项测试有 1 failure：object.__getattr__ 审计事件覆写了正在归因的 Guard.check 操作标签。只让实际拦截事件更新上下文后，第二轮 16 PASS；此缺陷与修复原始日志保留。冻结后的正式 unit 恰一次、独立 verifier 恰一次，formal-native NOT_RUN。诊断开始至正式结束实际 wall=282.533s，cap600；本轮所有启动的子进程已结束并排空。

## 证据、范围与交付

G0 第一次纯只读检查因宽文本匹配把 workflow 的无部署声明误判为副作用，未产生任何文件；随后按真实执行步骤重验通过。G0 PASS 先输出，再创建唯一授权 fresh owner 的 receipt 容器并 exclusive-create/fsync 收据，完成后才创建源码快照/实验文件。Windows 目录 fsync UNAVAILABLE；未改变 ACL。三份 snapshot 来自 G0 实际工作树 raw bytes，workflow 原 CRLF 保留，LF 归一后分别匹配固定 Base blobs；原字节 SHA 独立保存。

旧 Runtime/原测试/helper/证书、Router/matrix/RPF85、AGENTS/Project State/历史报告不变。未读取/列举 docs/reviews 或 rev1/rev2/其它旧私有 owner，也未访问任何宿主 Key。Provider0/真实SDK0/Java0/Docker0/业务HTTP0/生产写0/实际API费用0。完整 Runtime、暂停 RPF74/RPF81 NOT_RUN。

交付范围为 **2M+10A**，本轮仅普通 main Push 自动触发原有 CI，pilot NOT_APPLICABLE；报告不为回填自身 SHA 或未来 CI amend。详见 [verification-diagnostic.json](verification-diagnostic.json)、[counterexamples.json](counterexamples.json)、[preflight-diagnostic.json](preflight-diagnostic.json)。

建议后续先解决归因采集的性能与超时保全问题，再在新的明确运行授权下取得那两次拒绝的真实事件；当前证据不足以扩大权限、忽略 Guard denied 或减少 required 覆盖。
