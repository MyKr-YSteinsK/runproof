# TASK_RESULT — RPF-81 / rev-1

**Status: Partial**。本地正常发送、UNKNOWN 后旧票/新票阻断、两个受控交错及独立负控取得实际证据；恢复试验存在保守重启禁发的因果混杂，R81-A05 未完整验收。未修冻结源码，未恢复 RPF74。

- Plan：`RPF-81-rev-1-Durable-Unknown-PreSend-Loopback-Conformance-Plan.md`。
- Base：`f9a4e48981aecfa4ef584ffa220488e84c17bbae`；branch：`codex/rpf-81-durable-unknown-presend-loopback`；Source SHA：`ae38691160a9ff951b357802d289b49a6e436b0c`。
- Owner：`rpf-81-rev-1`；ABI：`rpf81-loopback-v1`；source id：`93808dbbcd3850501875e315e393ed201d36f62956802c3e570ed6ecb08bc67c`。
- 原工作树／main／旧 RPF74 与旧证据受保护；仅 8 个新 Source 和 11 个新 Evidence 路径。封存时 A10 待最终交付，最终 SHA 和远端核验由聊天回执补证，不 amend 本文。

## G0 与冻结时序

G0 首写前 stdout 的原始 SHA256：`bd9daaef9fd512b2e93740807000fa673708fc32de501c9e594a12d1bfa2428c`。观察 `2026-10-29T14:17:37.260000+00:00` / mono `100064.2970468`，首次创建 `2026-10-29T14:17:37.260713+00:00` / mono `100064.2977528`；严格先后为真。事前完成原树 tracked-clean、Base/remote/分支无占用、19 路径 Base/index/大小写与 reparse、ignore、ACL/owner、磁盘和 feature-push 无部署核验。原始带本机身份字节保留私有根，公开只给去隐私摘要与原始锚。

冻结前完成编译/AST、strict JSON、25 输入根、发现和 help、正常／旧票／真实新进程恢复预检。首轮后细化计数和读取前路径检查，保留旧版本字节与全部现场，再用新预注册 ID 重验；没有复用失败 case 或重获额度。两个 Windows 工具长度问题如实保留，未触发实验副作用。Source 普通 push、固定 SHA 的8个 GitHub blob 逐字节/raw/LF/blob 核对与定向 fetch 后，于 `2026-10-29T15:02:55.450279+00:00` / mono `102782.4873214` create-only freeze。其后源和 fixtures 零修改。

## 逐 Gate

| Gate | 状态 | 实际证据／限制 |
|---|---|---|
| G0 | PASS | 严格首写前收据和创建顺序；见 preflight |
| A01 Source/Scope | PASS | 8 create-only，Source commit/API8/raw/LF/blob 相同，固定 Owner/ABI/roster |
| A02 Journal | PASS | 实际 WAL/提交回执、独立重放；断裂/缺尾/seq/previous/owner/source 拒绝，正常不误拒 |
| A03 Barrier | PASS（本地受控范围） | durable UNKNOWN 后新增票、SEND_BEGIN、sendall 均0；write/fsync failure停发；计数分栏 |
| A04 Physical | PASS（localhost） | P0 79 bytes；P1 0 calls/0 bytes；独立 receiver PID 和实际 raw 绑定 |
| A05 Restart/Race | **PARTIAL** | 新进程原 WAL 前缀保持且拒绝；两个 race 完成。但无 UNKNOWN 的重启对照也拒绝，不能独立归因于 durable UNKNOWN |
| A06 Oracle/Negative | PASS | stdlib-only独立 Oracle；2个有效来源根语义反例 + 6个互异重锚负控，分别计数，全部独立CLI拒绝 |
| A07 Freeze/Focus | PASS | 冻结后两轮各19方法，exit0/fail0/error0/skip0；正常0、拒绝3、缺锚2、错锚3、不完整4均实跑 |
| A08 Budget | PASS（遥测缺项已声明） | 全任务7/64次sendall，最大单case1/4；无外部Provider/SDK/Key/业务/JVM；CPU/memory/I/O峰值UNAVAILABLE |
| A09 Conclusions | PASS | 保留PARTIAL/INCOMPLETE和来源、因果、scope限制；无阶段或生产结论 |
| A10 Delivery | PENDING_FINAL_DELIVERY | Source已推送/回读；Evidence最终commit/push/API/19A回读在封存后完成，由聊天补证 |

## 正式场景

| Case | 独立 Oracle 实际结果 | sendall entry | 接收 bytes |
|---|---|---:|---:|
| p0-normal | CONFORMANT / NORMAL_LOOPBACK | 1 | 79 |
| p1-old | CONFORMANT / RECONCILE_ONLY | 0 | 0 |
| p2-new | CONFORMANT / RECONCILE_ONLY | 0 | 0 |
| p3-readonly | CONFORMANT / RECONCILE_ONLY | 0 | 0 |
| p4-recovery | CONFORMANT / RECONCILE_ONLY | 0 | 0 |
| p5-unknown | CONFORMANT / RECONCILE_ONLY | 0 | 0 |
| p5-send | CONFORMANT / PRE_UNKNOWN_IN_FLIGHT | 1 | 77 |
| p7-connect | INCOMPLETE / INCOMPLETE | 0 | 0 |
| p7-reset | INCOMPLETE / INCOMPLETE | 1 | 0 |
| p7-write | INCOMPLETE / INCOMPLETE | 0 | 0 |
| p7-fsync | INCOMPLETE / INCOMPLETE | 0 | 0 |
| p8-unsafe-send | VIOLATION / FROZEN_SEMANTIC_PROPOSAL | 0 | 0 |
| p8-unsafe-reserve | VIOLATION / FROZEN_SEMANTIC_PROPOSAL | 0 | 0 |

P2 在同域/跨域 TARGET/EXPLORER 的4次新预约全部 DENY；P4 新进程另4次也全部 DENY。P1、P4、UNKNOWN先赢以及两种持久化失败后的旧票共5次 DENY。`planned/triggered/observed=True, agent_exposed=False` 来自合成宿主测试注入，绝不是实际 Agent/Provider ToolReturn。write失败的UNKNOWN没有WAL提交；fsync失败保留未确认帧，均 INCOMPLETE，不把未提交当作可继续发送。

正式总量：`{"reconcile": {"allowed": 8, "attempted": 10, "denied": 0, "proposed": 10}, "reserve": {"allowed": 11, "attempted": 21, "denied": 10, "proposed": 21}, "send": {"actual_sendall": 3, "admission_unresolved": 1, "allowed": 3, "attempted": 9, "completion_inconclusive": 2, "denied": 5, "proposed": 9}}`。attempted 表示gate方法进入，与外部Provider调用分开；send allowed按SEND_BEGIN计，I/O失败可发生在准入之后；connect失败的1次 admission_unresolved 未当作 DENY。

P5 send先赢：SEND_BEGIN seq2 → SEND_END seq3 → UNKNOWN seq4，同一锁真实出现 CONTENDED；独立 receiver 被显式屏障延后到 UNKNOWN提交后才 recv，读取77 bytes。`PRE_UNKNOWN_IN_FLIGHT` 仅描述开始顺序和后读事实，不是网络到达时刻／零延迟交付证据。另一个UNKNOWN先赢顺序没有调用 sendall。两次固定交错不证明全部调度。

## 恢复反证及失败现场

Source中的 `self.recovered=not create` 被 `blocked()` 无条件并入拒绝谓词。补充无网络隔离对照：prepare PID `1952` 创建无 UNKNOWN 的 READY WAL并成功预约；recover PID `30192` 读取完全相同SHA `8c202b69f103cedc02d70890f1e50217b7c206cad24f86ebd60727cd25130574`，UNKNOWN仍False，却 DENY。正常恢复准入未被证明；原 P4 不能排除此保守策略这一原因。A05维持PARTIAL。该补充对照仅生成新的单位命名空间 WAL/审计回执，实际发送0，不改变两轮正式suite的方法计数。

connect拒绝、真实RST、Journal write/fsync注入四个正式case均 INCOMPLETE，无重试发送。RST确实进入一次sendall但没有接收字节，不能称为“没有发送尝试”。六个负控分别为bool seq、previous、重锚owner、重锚source、删除UNKNOWN后全链重锚、外层source+owner+frame source组合重锚；外锚均按变换后真实bytes重新计算。语义覆盖另由两个冻结合法提案给出，不以来源拒绝替代。

## 资源和证据范围

冻结前实际sendall4次，正式3次，全任务 **7/64**；返回成功4次，reset异常3次。向原语提供payload累计 **560 bytes**，独立receiver实际读取累计 **320 application bytes**，正式正常/在途分别79/77 bytes，其余为0。最大payload `82` bytes；19个真实localhost场景（8预检+11正式）。所有预算条目与实际进入日志一一对应，不因Source细化或新case重置。

Host/receiver共 `41` 个实际子进程回执，含3个故意exit23的崩溃宿主；其它均exit0，listener随进程关闭。父级回执时段估算峰值含一个编排driver不超过 `4` 个任务进程，listener同时最多1；这是受控生命周期上界，非CPU采样。CPU/memory/disk I/O峰值未采样，均UNAVAILABLE；本任务磁盘文件快照另见runtime diagnostic。

真实Provider calls/token/费用、SDK、Key读取或存在性探测、业务DB/HTTP、JVM/Docker/Web全为0。旧完整Runtime suite、Release Gate、Control Plane/Java/Web均 NOT_RUN_BY_PLAN，未冒称通过。Git/GitHub只用于授权feature交付和固定SHA读回；未创建PR、合并main、部署或提交比赛。

## 已证明与下一步候选

已证明的是这份冻结源、同一Windows宿主、任务自有localhost sink、显式调度下的持久门禁和拒绝事实；已识别恢复因果隔离不足。原始capsule和负结果可独立离线再审，但复制同证据不是异环境复现。Hash、自有Owner/receiver不认证第三方Issuer；不证明硬件断电持久性、通用并发安全、外部Provider发送/计费、真实业务Authority或旧RPF74已修。

建议后续独立授权revision消除无条件recovered禁发与UNKNOWN恢复之间的混杂，并加入无UNKNOWN的READY恢复positive及WAL缺失/断裂negative。本轮不新建RPF编号、不修改冻结source，也不恢复RPF74。Architect仍需独立决定TASK_COMPLETE/EVIDENCE_ACCEPTED/STAGE_ADVANCED；本结果没有代作决定。

封存前另从即将提交的公开 capsule 恢复13份隔离离线输入，独立 Oracle 重审结果逐项与原始 CLI 相同，实际网络发送0；这是同一证据的再审，不是新物理复现。报告私有 helper 曾因重复关键字在创建跟踪证据之前停止，保留草稿后修正，不影响冻结源或正式试验。
