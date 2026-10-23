# RPF-67/rev-1｜订单 DomainPort 与唯一真实 Trial 的失败诊断

Status: Partial

## 结果

新 owner/Context、单物理 WAL、四方法版本化 OrderPort、固定 SDK child/Host 和独立离线 verifier 已实现；免费生产装配、历史锚、负控、完整 Runtime、source freeze、metadata/cold 均通过。唯一真实 Trial 的第一个 Provider 响应被 `FINISH_SHAPE` 拒绝，未执行任何业务工具。没有完整真实闭环，因此 **未生成 `order-target-witness.json`**，未开展真实证书攻击控制。

工程结果不宣布 `EVIDENCE_ACCEPTED` 或 `STAGE_ADVANCED`。真实订单 Agent 能力仍未被本轮证明；Architect 审查后决定后续任务。

## 身份与 Gate

- repo：`MyKr-YSteinsK/runproof`；分支：`codex/rpf-67-real-order-target-domain-port`；Base：`a8b1ca8bf895370c1d136c61301bb25f8e7a6c0d`。
- Source digest：`499d1546add4cd76a8a24015a79fbab1806beaf28f61091a3407ee3c3a957012`；Verifier：`rpf67-order-witness-verifier-v1` / LF SHA=`1b00bea769e93d51050353515ed0486b99a2547898fb6efa8bf14ee9632fd036`。
- G0=PASS；A01=PASS；A02=PASS；A03=PASS；A04=PASS；A05=PASS；A06=FAIL；A07=NOT_RUN；A08=NOT_RUN；A09=PASS；A10=NOT_RUN。
- A03 只表示免费 SDK 协议/负控通过；真实 Provider 兼容性在 A06 失败。A09 表示安全停机、边界和未知账本保留；不表示 usage 已知或票据全部 settled。
- Source Map raw/LF、依赖闭包、快照、精确命令、exit、所有失败记录见 [verification-diagnostic.json](verification-diagnostic.json)。

## 唯一真实 Trial：已确认事实

- Run `rpf67-order-cae8e80e0fb38806`；operation `refund-rpf67-order-cae8e80e0fb38806`；新本地 SQLite 模拟订单，授权 CNY 2500 minor units。
- Provider HTTPS attempt=1，Target=1，Explorer=0，Trial=1，Java=0。SDK ready 身份通过；父 Host 在处理响应时拒绝，SDK 报 `ModelHTTPError`，Host 失败码为 `FINISH_SHAPE`。
- accepted business ToolCall=0，refund mutation=0。Controller 失败后两次不同只读连接复核，订单仍 PAID、refunded=0、receipts=0。正式 authority 总读次数=3（含初始）。业务结论 `INCONCLUSIVE`；Agent=`NOT_ESTABLISHED_PROTOCOL_REJECTED`；Platform=`ERROR_PROVIDER_RESPONSE_PROTOCOL`。
- fault：planned=true，triggered=false，observed=false，agent_exposed=false。没有发生提交后 UNKNOWN 的真实工具反馈；不能用免费合成轨迹补位。
- 永久预约 Provider slot=3000 tokens、输入上界2027、输出cap256，request SHA=`38975246c912ed70350a51b48215d2e0ccd8abe35dd4b5a969d4c0e0a4fc07fc`，预约成本 guard=¥0.0137295。实际 usage/tokens/费用全部 UNKNOWN；guard 不是账单，未回收或转移额度。
- 原 Provider response ID、ToolCall ID、raw response SHA 和精确形状未留存。`provider-1` 为 UNKNOWN；session/trial/sdk/host 四张票据仍未结算，账本 quarantine。没有第二个 Trial、第二个 Provider 请求或二次业务写。

## 失败原因与诊断缺口

新驱动的 `FINISH_SHAPE` 同时检查工具调用与 `finish_reason` 是否一致、工具调用消息是否夹带非空 content。响应未保留，因此不能断言本次由哪一条件触发。只读源码诊断用三个 **SYNTHETIC_TEST_ONLY** 样本证明了这些不同形状都会触发同一码；正控纯工具调用通过。该复现新增 Provider=0、业务写=0、WAL 原字节不变，不能作为实际 Provider 形状证据。

根因定位的缺口是：验证失败前没有保存 allowlisted shape/ID/usage 摘要，丢失了可区分的响应元数据。建议后续新 Plan 先补失败摘要，并明确工具调用附带说明文本的接受策略；这不能通过本轮修改冻结源码或重跑付费 Trial 解决。

## 免费证据与环境

- Focused 12 tests，exit0；真实 SQLite 原事务与独立 RO Reader，分别覆盖模拟模型选择 reconcile 和直接安全 stop。合成重锚攻击 46 类全部 exit3，正确/无锚/错锚 CLI0/2/3。
- 18 件原历史证书 + RPF66/rev5 原件共19件，以及 Reviewed/Public，共21个命令 exit0；原件与原 verifier 未改动。根目录 Reviewed/Public 也重新通过。
- 最终完整 Runtime：独立进程 PID=26192，466 tests，0 errors/0 failures，2 original Docker skips，exit0；runner 689.542s。快照 `.local\rpf-67\snapshots\source-fbaea7cf9fdc`，709 文件；当前 Source closure20及 RPF60 closure32逐项核对。
- 首个完整进程466 tests，2 FileNotFoundError、0 failures、2 skips；缺少旧 RPF60 测试父目录。第二个全新快照内仅补建空测试父目录，原源码/测试零修改，无 skip/xfail/filter/拼接；两个完整运行记录均保留。首次 Public 检查因快照遗漏九个公开文档依赖失败，补齐后通过；private runner 收据关键字错误也已保留说明。
- Source Freeze 前 staged/unstaged diff-check 均0；冻结20项 raw/LF、Verifier、固定 SDK pin 与私有执行辅助文件 SHA，冻结后均未修改。
- formal metadata=1，CPython3.12.13，PydanticAI2.57.0/OpenAI3.35.1，两包 RECORD mismatch=0；formal cold=1个真实子进程，4次免费 fixture completion、3次原 ToolCall 回调、0 Provider/0业务写，guard/ready/PID/report/cleanup通过。首次 canonical request=2027 bytes。
- 父完整 Gate 为 Windows Python3.14.6/executable SHA 已核实；子 SDK3.12不证明父3.12完整兼容。父3.12 `NOT_ESTABLISHED`，Linux hosted `NOT_RUN`，Docker 两项 `UNAVAILABLE`。

## 实现采用与复制债

FROZEN owner/新根/预算/一 Trial/单 WAL/Source Freeze/故障与 authority 边界保持。RECOMMENDED 采用原 `OrderSandbox.initialize/refund/inspect`、`OrderAdapter.invoke`、`AuthorityReader.read/validate` 和纯 `evaluate_order_effect`；构造器以 task-owned subclass 限定新路径，未调用旧 storage_task 表或旧独立 ProviderLedger。

DELEGATED 采用新 ABI `rpf67-order-real-target-v1`，四方法 OrderPort 由 Session 显式注入 gated driver；`execute(context, contract, ledger, *, driver)` 没有冒充旧冻结 ABI 的直接替换。旧 RPF64 是 Provider0确定性订单 Port；RPF66是配置域双真实角色，两者均未被改名为本轮真实订单能力。

Child 与 RPF66 v5 有 233 个序列匹配行，主要为 pinned SDK/文件/网络 guard；新版本重写订单工具、Host、预算/响应协议、单域 Session 和 Witness verifier。复制区域、导入方法、接口差异和风险见 [capability-assessment.json](capability-assessment.json)。这些 task-owned Context/Host/child 的复制与耦合债尚未抽取。

## 清理与长期证据

两个 SDK PID（26116 / 26436）与对应父进程（8196 / 29492）均经限于本任务 PID 的 Windows 查询确认退出；port6407关闭，Host线程退出，父临时 key 引用释放，用户环境凭据未改动。SQLite连接关闭、独占锁清理探针已完成；失败后的 Reader 均只读。

原 DB、单物理 WAL、source freeze、metadata/cold、失败响应诊断、完整运行日志和快照原位保存在 ignored `.local/rpf-67/`；不删除、不重置、不给未知费用回填0，不读取旧私有账本/配额。公共产物不含私密 key/token、个人主目录、private reasoning 或自由模型文本。`docs/reviews/` 仅保留原根级 marker，内容未访问。

RPF66/rev5 原 Witness 577721 bytes / SHA=`68dad2804edd3668e1e4b4ed19d18034b79d5fa1892e9fea75aaeb9080c4f3c5` 仅为历史锚，未改动且不与本轮合并。

## Git 与研究边界

- A10 尚未完成；后续仅对这14项新路径 focused commit 和普通 push。
- main=`bda0cd49e50e3181f604324e94877a24b9885334`、父分支=`a8b1ca8bf895370c1d136c61301bb25f8e7a6c0d` 不变；无PR/merge/tag/release/dispatch/deploy/赛事操作。feature 分支未触发自动 Release Gate，CI `NOT_RUN`。
- `Explorer=NOT_RUN`、`L2=NOT_TESTED`、`web=NOT_INTEGRATED`、`cross_domain_same_session=NOT_PROVEN`、`causality=NOT_PROVEN`、`issuer=NOT_ESTABLISHED`、`external_reproduction=NOT_TESTED`、`release=NOT_AUTHORIZED`。
- RPF66配置成功与本轮失败不能证明同一 Session 跨域真实能力，R-07仍未完成。先解决响应摘要/协议兼容，再以新授权验证同一 Session 的 Config+Order Real Target，并评估 Context/WAL/child 抽取；本轮不实施跨域真实 Explorer。
