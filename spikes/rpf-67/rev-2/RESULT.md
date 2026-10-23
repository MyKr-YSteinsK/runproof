# TASK_RESULT｜RPF-67/rev-2｜响应形状取证与订单协议执行结果

Status: Partial

## 结论

- Gate：G0=PASS；R2-A01=PASS；R2-A02=PASS；R2-A03=PASS；R2-A04=FAIL；R2-A05=NOT_RUN；R2-A06=NOT_RUN；R2-A07=NOT_RUN；R2-A08=NOT_RUN；R2-A09=PASS；R2-A10=NOT_RUN。
- ABI：`rpf67-order-real-target-v2`；owner=`rpf-67-rev-2`；source digest=`ae67572a127bae4a67469487dba67e1b8917bf90c0ab7b7f279bc4380bdacc8b`。
- Base=`09411b48c432ce45d225552015e2c2039eb8375c`；新分支=`codex/rpf-67-rev2-provider-shape-order-recovery`。Source Map raw/LF、Verifier、变更路径和全部命令/exit/快照见 [verification-diagnostic.json](verification-diagnostic.json)。
- 第一版仅已知 FINISH_SHAPE 拒绝；原实际响应形状/ID/usage 不可靠留存，不能反推或回填。当前分支中的公开 Base Parser 最小复现：纯null+tool通过，mixed/stop+tool/空tool三类同报FINISH_SHAPE，全部为免费合成诊断。

## 实现与采用

- FROZEN：新owner/Root/ABI、单物理fsync WAL、CAPS和一Trial、原业务金额/Reader/故障、SDK pin和guard、冻结后不改源码、历史与用户保护保持。
- RECOMMENDED：有界安全shape在严格解析之前exclusive写receipt并绑定WAL；失败保留UNTRUSTED hint和UNKNOWN。有限mixed content仅用于SDK透传，文本及短文本hash不持久化，不能成为Tool/Authority。
- DELEGATED：沿用原Driver/Port/Child；增加有限状态replay和in-memory receipt能力，receipt fsync→WAL崩溃后禁止重开/续发，保留TORN_DIAGNOSTIC。SDK最终文本hash在父接收报告时移除；Child及其guard原字节不变。
- order SQLite、mode=ro/query_only Reader和纯Oracle方法保持原件；只把task-owned构造owner改为rev2。无新通用framework模块；四方法Port仍由Session显式注入gated driver。

## 免费验证

- R2-A04=FAIL：第二次全量也在同一旧 HTTP fixture 出现ERROR，随后主动停止剩余免费测试。第二次没有完整unittest汇总，绝不称473项全绿；日志、PID、退出码和取消原因完整保留。两次额度已用完，没有第三次全量。
- 正式Source Freeze/metadata/cold/paid-gate/Trial/Provider均NOT_RUN；新主WAL与真实Witness路径保持不存在，未读取Provider Key。实现与免费正负证据交付为Partial。
- 首次完整全量 PID=28484，473 tests、1 error/0 failures/2 skips、exit1；旧 config fixture在HTTP getresponse出现WinError10053。隔离10次复查1 error/0 failures，未改旧源或系统策略；未读完请求体后关闭连接的竞态仅为代码支持的推断。首次记录保留，第二次另留取消记录，不拼接绿段。
- Focused 19 tests，exit0；固定真实SDK mixed-content端到端0Provider、3原ToolCall callbacks、一次本地SQLite退款/一receipt、原样反馈、清理通过。文本冒充Authority/二次退款指令未控制业务。
- 合成重锚攻击 66 类全部 exit3；独立CLI正确/无锚/错锚0/2/3；新增shape/receipt/parse/ticket跨域、equal-clock重排、抢先Tool与hint冒充known等。
- 19件原历史成功证书（原18+RPF66/rev5）+Reviewed/Public共21个原入口 exit0；rev1没有真实成功Witness，不增列第20个锚。
- 第二次完整入口运行已取消：PID=25620，exit=4294967295，没有最终unittest汇总。观察到的旧HTTP测试ERROR=1；保留已完成片段但不作为完整PASS。
- 全新完整快照 `.local\rpf-67-rev-2\snapshots\full02-5c1a72c752`，716 tracked/白名单文件，Source closure20与RPF60 closure32核对；只在快照内seed空历史测试父目录，不复制旧runtime/WAL。
- 开发12/16项进程通过；18项预备进程因运行中源变更导致一个CONTEXT_SOURCE_IDENTITY失败，原日志保留，不复用为PASS。最终focused、首个完整full和第二次取消记录分别保留。
- 正负矩阵包括合法null/mixed/stop、两条故障恢复路径、falsey对象、长度/类型、并发/错误参数/ID、usage、thinking/refusal、HTTP/timeout/size/JSON/重复键、源与环境/权限、Torn receipt和WAL重锚。
- 固定SDK子Python3.12.13不证明父3.12完整兼容；Windows父3.12 `NOT_ESTABLISHED`，Hosted Ubuntu3.12/CI `NOT_RUN`，原Docker两项 `UNAVAILABLE`。

## 正式环境与唯一真实 Trial

- metadata=NOT_RUN；cold=NOT_RUN；Source Freeze=NOT_RUN。
- 真实Trial=0，Target Provider=0，Explorer=0，Java=0；永久预约tokens=0，预约guard=¥0.0000000；usage tokens=0，guard非实际账单。
- Agent=NOT_RUN；Platform=NOT_RUN；业务=INCONCLUSIVE；UNKNOWN=False，all_settled=True。
- 每张票据的role/request SHA/输入上界/输出cap/usage与settlement、合法原ID及工具回注、Authority/receipt/operation、故障四态与恢复见 [session-summary.json](session-summary.json)。真实shape条件、失败指纹和置信度见 [provider-shape-diagnostic.json](provider-shape-diagnostic.json)。
- 新真实Witness `NOT_RUN`；public路径必须不存在。停止原因：`R2-A04 / FREE_GATE_FAILED`；详细日志、退出码及下一步授权范围见 [verification-diagnostic.json](verification-diagnostic.json)。不以synthetic或旧Config证据补位。

## 清理、隐私与证据保留

- 本轮正式Provider key从未读取；免费SDK子进程仅loopback token；task-owned PID/thread/port清理按OS查询与Popen/ready/report交叉核对。免费SDK/合成夹具的DB/WAL/shape receipt及完整日志保留在ignored `.local/rpf-67-rev-2/`；正式主WAL/failure/freeze均未创建，不删除或重置未知票据，不重发live。
- Source Freeze未准入；最终候选Source Map raw/LF保持与聚焦/全量快照一致。旧RPF67公开报告、19证书/源与AGENTS/Project State保持原字节；旧运行DB/WAL/额度/marker及用户docs/reviews内容未读改，仅根级marker保留。原固定SDK安装仅作获准的pin/source只读核验。无私密凭据、个人主目录、raw Provider body、自由文本/reasoning、原arguments文本或hash进入公共shape。
- 未完成验证的usage即使shape有数值hint也UNKNOWN；不计入known tokens，不称真实账单。HTTPS请求SHA在真正canonical发送处取值，与不可返还票据一致。

## Git 与研究边界

- focused Commit/普通Push/远端双读尚未完成，A10=NOT_RUN。
- main=`bda0cd49e50e3181f604324e94877a24b9885334`与父branch不变；无PR/merge/rebase/force/tag/release/dispatch/deploy/赛事操作。
- `Explorer=NOT_RUN`、`L2=NOT_TESTED`、`cross_domain_same_session=NOT_PROVEN`、`web=NOT_INTEGRATED`、`causality=NOT_PROVEN`、`independent_reproduction=NOT_TESTED`、`issuer=NOT_ESTABLISHED`、`production_release=NOT_AUTHORIZED`。
- Witness是冻结机制、单WAL和独立只读观测约束下的工程证据，不是第三方签名/不可抵赖/外部生产事实；R-01～R-10仍保持。当前先需新Plan明确授权修复受保护config_target_bridge.py中旧HTTP fixture的Windows连接关闭问题，并重新完成免费门禁；本任务不扩白名单或重发Paid。未来共享Config+Order Session仍需独立编号授权，不能拼接历史证书。
- TASK_COMPLETE由Codex据Gate报告；EVIDENCE_ACCEPTED/STAGE_ADVANCED由Architect后审。
