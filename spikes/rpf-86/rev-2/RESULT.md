# TASK_RESULT — RPF-86/rev-2

Status: PARTIAL

Decision: B_UNACTIVATED

Base/main: `75799b74d97f6eb485182697b3608e5267b9a065`。G0 实测 PASS；源码与原方法身份不变。唯一公开证书实际 21,170 bytes，Git blob `b80c7d1b98daf9d336e8c90caa767b3d1113a3e9`，raw SHA-256 `f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43`。未输出正文或 SDK identity 值，未复制/改写证书。

## 验收事实

| Gate | 实际结果 |
| --- | --- |
| G0/A01/A02 | PASS：真实本地 Git HTTPS/Base、owner/ACL/空占、原源码和证书身份 |
| A03 | 正式 NOT_RUN。唯一冻结前预试 testsRun=5、5 PASS/0 ERROR/0 SKIP，但 guard READ_SCOPE_DENIED=2，子进程 exit1、admission FAIL |
| A04 | PASS（Python 接口范围）：原 old-root open/mkdir/stat、socket/subprocess、越界写入、原生子进程 exit/timeout/truncation、证书目录/兄弟/大小写/写入/hash/reparse、源漂移/伪绿/日志漂移均拒绝 |
| A05 | PASS_NEGATIVE_EVIDENCE_ONLY：新独立进程核对实际 report、snapshot、source、PID/exit/log、physical manifest、8 份新 WAL 的逻辑 owner；不重跑原方法 |
| A06 | 正式 12/12 PASS，原 8 test IDs 与原断言保留；exit0，3.152s |
| A07 | B：workflow Git blob 保持 fe060ccb918acd318ff1b542cc6ece597a80d424，不加 pilot step |
| A08/A09 | NOT_RUN_AT_SEAL；提交/Push/远端读回与自动 CI 的后续真实收据由最终聊天单独报告 |
| A10 | required=1232、UNAVAILABLE=539 不变；未获得 EVIDENCE_ACCEPTED/STAGE_ADVANCED/release/deploy |

## 解释与停止点

单文件授权使原 helper 在预试被 Guard 接纳 424 次，rev1 的 3 PASS/2 ERROR 不被追认或替换。rev2 方法事件虽为 5 PASS，仍有两次 READ_SCOPE_DENIED；原 Guard 只有计数，没有路径/调用者，归因 UNAVAILABLE。不能认为全部旧拒绝或这两次拒绝都来自证书，也不根据方法 PASS 忽略守卫。按 Plan 选择 B，既不开放证书目录，也不继续运行正式五方法。

冻结前第一次 12 项控制测试有 1 failure：certificate-controls 的子进程缺 ROOT 导入路径而 ModuleNotFoundError。原 child 日志保留，初次完整 unit 输出只在工具 stdout、未另存（UNAVAILABLE）；修正 harness 导入后第二次 12 PASS。随后完成最小 O_TRUNC 审计负控及负证据 verifier，冻结后恰一次正式 12 项 unit 与一次独立 verifier。正式总耗时 3.986s / 420s；预试 30.141s / 180s。所有已启动子进程已退出并排空。

独立复核不是第三方 Issuer，也不是新环境重现；Python audit/元数据拦截不证明任意 native syscall/kernel sandbox。目录 fsync 在 Windows UNAVAILABLE，文件 fsync 有实际执行。原 Runtime、原测试、helper、certificate、rev1 报告、Router/matrix/RPF85、Project State 均未修改。

## 成本、证据与交付

Provider/真实 SDK/Key/Java/Docker/业务 HTTP/生产写/真实 API 费用均 0。完整 Runtime、暂停 RPF74/RPF81、额外 native 与真实 Provider 实验 NOT_RUN。所有本轮私有输出在 G0 的唯一新 rev2 owner，原始失败记录不清理。

公开证据见 [verification-diagnostic.json](verification-diagnostic.json)、[certificate-read-boundary.json](certificate-read-boundary.json)、[counterexamples.json](counterexamples.json)、[preflight-diagnostic.json](preflight-diagnostic.json)。Base 快照逐字节等于固定 Git blobs。拟提交范围为 2M+9A；仅普通 main Push 自动触发既有 CI，pilot NOT_APPLICABLE。封存时 Push/CI 为 NOT_RUN_AT_SEAL，不为回填未来收据 amend。

建议后续独立授权时先增加安全的 denied-event 路径类别/调用者归因，再判断两次拒绝；不得仅凭五方法 PASS 放宽 guard 或削减 539 required。
