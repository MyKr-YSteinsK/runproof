# TASK_RESULT — RPF-56 rev-3

**Status: Partial**

执行日期：2026-10-20，Asia/Shanghai。恢复与无付费预演通过；唯一 Live Session 在第一轮 Explorer 工具结构校验处停止，真实双角色联合闭环未完成，**no-valid-Witness**。

## 1. 恢复结果与身份

用户已调整系统设置的说法来自本 rev-3 Plan，记为 `REPORTED_IN_REV3_PLAN`，没有猜测管理员身份或调整时间。本轮 Codex 未修改系统安全策略、注册表、服务、签名或解释器，也未安装、复制/改名/重签 exe、提权、换终端/WSL/容器执行。

2026-10-20 **11:35:55.7077710–11:35:56.0237850 +08:00**，完成唯一一次原路径、原 SHA CPython smoke：Popen PID=31100，与子进程报告 PID 一致；Python=3.12.13、`-I -B` 生效、exit=0、stderr=0、WinError=null。无网络、SDK、Java、Provider 或 key 读取。先以独占、fsync 的 smoke-intent 预约，未重试。exe SHA=`e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f`；launcher SHA=`74e020321eb8f828f0c2cfe865082fcf94aa6e7cf488e8a744d89b9282eaeb83`，路径 hash 与 rev-2 固定绑定相同，父路径及文件均做 link/reparse 检查。

当前最小只读状态：Usermode Code Integrity enforcement=0，SmartAppControlState 不可取得（`UNAVAILABLE`，没有记作 Off）。实际 smoke/后续固定 SDK 进程成功，支持当前执行上下文的运行资格已恢复；不能推出所有安全产品关闭、唯一策略根因或未来始终可运行。本轮没有再广泛读取安全日志。此前 rev-2 的 3077 是历史事实，未把它作为本轮新的拒绝或恢复事件。

随后由同一直接 CPython 实际检查当前 SDK：Pydantic AI 2.57.0 / OpenAI 3.35.1、SDK/OpenAI core SHA、site-root/runtime mapping、RECORD 均匹配固定身份，hashed entries=443/1999，mismatches=0。该元数据检查为额外 **1 个 SDK 身份进程**，不混算为 smoke 或三个 Fixture。详细 hash 见 `recovery-diagnostic.json`。

Root=`D:/CS/runproof`；执行 Parent/Base=`fed5354eb70c6e2b25198f9a92c340cbf24bb551`；父分支 `codex/rpf-56-rev2-appcontrol-sdk-recovery`；新分支 `codex/rpf-56-rev3-compliant-sdk-recovery-live`。origin fetch/push=`https://github.com/MyKr-YSteinsK/runproof.git`；main 基线=`bda0cd49e50e3181f604324e94877a24b9885334`。初始 fresh remote 父分支匹配、新分支不存在，tracked/index clean，仅已有 `?? docs/reviews/`。该目录未进入、枚举、读取、修改或暂存。

## 2. 最小迁移与无付费预演

只修改五个白名单路径：`config_pge_contracts.py`、`config_pge_session.py`、`config_pge_verify.py`、对应测试、`spikes/rpf-56/probe.py`。新建五个 rev-3 报告/诊断文件。Explorer、Target、旧 helper/Verifier、旧证书、rev-1/rev-2 报告、AGENTS、Project State/history、Web/CI 与 Java 外部仓库保持原样；没有新正式证书。

合同改为 v3，owner=`rpf-56-rev3`，Session/Run/Agent 采用新身份，task root=`.local/rpf-56-rev3/`，JAR/export/Base/branch/Journal/总账校验同步迁移，Verifier=`rpf56-config-pge-verifier-v3`。原先 Runner 的“仅允许 untracked 新源码”状态门改为严格允许白名单 tracked 未暂存修改和新 rev-3 输出，仍拒绝 staged 污染、无关路径和额外输出。移除 Runner 对旧 helper 内存构造检查函数的依赖，使用本轮实际 smoke/SDK 检查结果及每次直接路径/hash 再校验；不回落 wrapper。

preflight 不启动 SDK/Java/Provider、不提前复制 JAR；只在三 Fixture 和价格 Gate 后，从原固定 source manifest/JAR 复制本轮 task-owned JAR 并核对。Java 身份由 release 文件/hash 检查，无诊断 JVM。

初始 Tier 0 的 15 项定向与两个完整合成会话通过：有信息增量和合法重复各自 external SHA correct/missing/wrong=`0/2/3`，11 类 rehashed tamper 均 exit=3。覆盖旧 v1/v2 schema/owner/Base/branch/JAR 拒绝、旧 root 禁写、共享预算、锁竞争、torn record、unknown usage、重复 POST/JVM、消息深拷贝、伪恢复/假 PID。这里只证明新 v3 协议，合成标签未升级为 Live。

三个独立固定 SDK cold-start 全通过，Provider/Java/业务 HTTP 均为 0：

| 候选 | completions / calls | 返回请求序列 | 真实观察 |
|---|---|---|---|
| normal | 4 / 3 | `[2,3,4]` | COMPLETED，三个独立 call IDs |
| planned-but-inhibited | 4 / 3 | `[2,3,4]` | 实际 FAULT_INHIBITED gate，COMPLETED |
| local-delivery-suppressed | 3 / 3 | `[2,3,null]` | SUCCESS_WITHHELD 一次，预期 SDK_ERROR / RuntimeError / exit 1 |

每个 Popen PID 与 Host ready PID 相等，正常完成报告 PID 也相等；suppressed 失败报告本身无 PID，保留 null，没有补造。guard、stderr、端口与线程清理检查全部通过。各 Runner/SDK PID、合同 hash、call IDs、实际检查和 source map 保存在脱敏恢复诊断。它们是 scripted Host Fixture 的真实 SDK 协议，不是三个真实 LLM Target。

## 3. 唯一真实 Session 与停止

Session=`rpf56r3-session-09bea184907340f8`；plan SHA=`5df7a1ec2a61bd8bdb1cdd2797f37066603a702c884ab30fa1cd5509bf641d4a`。在模型/业务 I/O 前，已冻结两轮完整三候选合同、新 Run/namespace、fault plan、全局额度和 source map，独占创建总账及 started marker。第一次请求前持久预留 2651 tokens，收到合法 usage 后在同一链中记账；请求额度不返还。

第 1 轮 Explorer：POST `/chat/completions`，request SHA=`6c54adea595b644b18fcd68ea2738550f1fb08079a74d08676f8219568dc397f`，response ID=`a1eb8488-a60b-4a4d-bbfe-d9864f5941b0`，returned model=`deepseek-flash`。收到并确认 input=468、output=72、total=540。随后 parser 返回 **`ONE_SELECTION_REQUIRED`**；没有接受合法 selection/candidate，尚未预约 Trial 或启动 Target/Java。

可确定的边界：JSON choices 通过了单项检查，但其 message.tool_calls 不满足“恰好一个调用”的结构要求。原始模型正文/推理未持久化，**响应结构摘要也未保留**，因此无法进一步区分字段缺少、空值/空数组或多项，也不能确定 Provider/适配的唯一根因。未把推测写成实测，未声称模型选择某候选或已触发故障。补充了纯离线“缺少/空/多项 calls 均拒绝”的回归，不重新调用模型。

分类为 `INCONCLUSIVE_EXPLORER_TOOL_PROTOCOL_REJECTED`；不能判定业务 Agent FAIL。没有 raw pending usage，消费记录为 RECEIVED；禁止重跑同一第一轮、换候选、改模型或重置 Session。已保留原 Runner 的 `session-summary.json` 原 bytes、完整本轮账本/事件和 CLOSED_PARTIAL_NO_RETRY 停止记录。无候选 Envelope，因此未调用真实 issuer，也未新建 `config-pge-evidence.json`。

## 4. Acceptance

| Gate | 状态 | 实际判定 |
|---|---|---|
| A-01 Identity/保护 | PASS | 精确 Parent、新分支、remote、规则、ignore/link、白名单与历史保护。 |
| A-02 合规执行恢复 | PASS | 一次原 SHA smoke、当前 SDK core/RECORD/ABI/映射通过，未改策略。 |
| A-03 rev-3 合同/总账 | PASS | 新身份/root/source、跨版拒绝、共享先预留、预算/损坏/unknown/replay 负控通过；实际唯一请求账可复算。 |
| A-04 零付费预演 | PASS | 两种合成 `0/2/3` + 11 tamper，三个真实 SDK 冷进程通过；无 Provider/Java。 |
| A-05 Live 双角色 | FAIL | Explorer 实际请求 1，但工具结构不合法；Target=0，未形成双角色。 |
| A-06 Java/故障/读回 | NOT_RUN | 只有 task JAR/source 身份准备；JVM/HTTP/POST=0，无业务效果。 |
| A-07 自主反馈链 | NOT_RUN | 无合法第一轮选择/Trial/verdict，未发送第二次请求。 |
| A-08 Live Witness | NOT_RUN | no-valid-Witness，文件不存在。 |
| A-09 回归安全 | PASS | 最终 16 定向/329 Runtime（2 Docker skips）、九旧锚、Reviewed/PublicDocs、源/范围/密钥检查通过。 |
| A-10 Git/回传 | NOT_RUN | 待 focused commit、普通 push 及 fresh remote 观察后更新。 |

## 5. 实际用量、清理与源码

| 项目 | 本轮实际 |
|---|---:|
| 固定 CPython 最小 smoke | 1，成功 |
| 固定 SDK 元数据身份进程 | 1，成功 |
| 正式 Fixture cold SDK | 3，全部通过 |
| Live Session / 完成业务回合 | 1 / 0 |
| Explorer / Target HTTPS | 1 / 0 |
| prompt / completion / total tokens | 468 / 72 / 540 |
| 费用保守估算 CNY | 0.003402 |
| 正式 JVM / 业务 HTTP / POST / health | 0 / 0 / 0 / 0 |
| 自动重试 / 未知 Provider usage | 0 / 0 |

费用使用当日官方峰值 cache-miss 输入 USD0.30、输出1.20 每百万 tokens，×15 guard 后为 CNY4.5/18，计算 `(468×4.5+72×18)/1,000,000=0.003402`。这是保守预算估算，不是实际汇率或扣款。当天核对 [官方价格](https://api-docs.deepseek.com/quick_start/pricing/)、[Flash-1017 更新](https://api-docs.deepseek.com/updates/?release=deepseek-coder) 与 [Chat API](https://api-docs.deepseek.com/api/create-chat-completion/)：non-thinking 支持 required tool choice。Tool Guide 抓取超时，协议细节采用可读的官方 API；没有额外付费探测。

Java source commit=`0258b9cef02ea74a40989d035c79256c776409c0`，manifest SHA=`33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`，本轮 JAR=66981576 bytes / SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。这些只证明准备身份，未启动服务。JAR、诊断、失败 marker/ledger、Fixture、合成样本/负控和隔离快照保留 ignored 新 task root；没有读取、重置或清理旧 `.local/rpf-56/**`、rev-2 或 53/55 运行账本/marker。SDK 固定安装与原 Java pinned source 仅按授权只读。

三个 Fixture 均已清理 Host/SDK/端口；Live 没有启动服务，CLI 已退出，业务本地 key 未创建，模型 key 未进入 SDK child 或证据。无本轮受控进程/端口残留，无未知费用或待定 POST。

执行源码为精确 Parent 加本轮允许的未提交补丁，运行与交付 source map/Verifier SHA 相同；详见 `verification-diagnostic.json` 的两个 source map。真实停止后只添加一个纯离线测试，没有改变已冻结执行源码或 Verifier。源 hash 按 LF 规范化，外部 Evidence anchor 按原始 bytes。

最终定向16项、隔离全 Runtime329项（2 Docker unavailable skips）、九件历史 RPF-43/44/48/49/50/51r4/52r3/53r6/55r2 固定 SHA 独立 verifier 均通过。隔离快照为 Parent git archive 叠加五个允许文件，全部 hash 匹配；回归阻止 Java/Docker 与外部网络。未运行 Maven/Web/hosted heavyweight Gate，未将离线结果替代真实 SDK/Provider/Java 集成。

## 6. 剩余边界与交付

本轮解决了固定 Python 的当前执行阻塞，证明 v3 迁移和三个真实 SDK Fixture，但未得到合法 Explorer 选择、真实 Target、业务 Effect、UNKNOWN_OUTCOME 的真实只读 reconcile、两轮反馈或联合 Witness。L1/L2=`NOT_PROVEN`，H1=`NOT_PROVEN`；不能从一次响应拒绝推导业务 Agent 不可靠、Provider 普遍不支持工具或系统安全。issuer authenticity/database independence/independent reproduction/WorkSwarm/attribution 继续为原未建立边界。

下一步需要新的受限 Plan，先补全不保留正文/推理的 response-shape/finish-reason 诊断，并在新的明确额度内核查 Explorer 协议；不能借本轮剩余额度追加调用、切换模型/SDK/Provider或修改 Windows 策略。无需重新索取 API key。

本次提交/推送与 fresh 远端核验完成后在同一报告收口，最终 SHA 在聊天回执给出。仅向指定新分支交付，无 main push/merge、PR、tag、release、workflow dispatch、deploy 或阶段接受声明。
