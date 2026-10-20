# TASK_RESULT — RPF-56 rev-4

**Status: Complete**

执行日期：2026-10-20，Asia/Shanghai。真实链、本地正式验收及指定分支 Git 交付均已完成；工程 Complete 不代表 Architect 已接受证据或推进阶段。

## 1. 结果与任务身份

独立 Probe 返回合法单个工具调用，随后新的真实 Session 完成两个 Explorer 选择、两个固定 SDK/DeepSeek Target 三工具链、两个新 Java/H2 的业务写入/只读校验，以及第一轮事实到第二轮输入的反馈链。新 Live Witness 已签发并独立验证。模型两轮均合法选择 **normal**；工程链完整，`L1=TWO_REAL_ROLES_EXECUTED`，`L2=false`、information_gain_proxy=0、`H1=NOT_PROVEN`。没有强制换候选或补跑故障场景。

Root=`D:/CS/runproof`；执行 Parent/Base=`296caf60afe6377634481986e3c383c9381c0f9a`，父分支 `codex/rpf-56-rev3-compliant-sdk-recovery-live`；授权新分支 `codex/rpf-56-rev4-explorer-tool-protocol-closeout`。origin fetch/push=`https://github.com/MyKr-YSteinsK/runproof.git`。建分支前 fresh ls-remote 验证 Parent 一致、新分支不存在、main=`bda0cd49e50e3181f604324e94877a24b9885334`；后续定向 fetch 再确认 Parent。初始 tracked/index clean，仅原有 `?? docs/reviews/`，该目录未进入、枚举、读取、修改或暂存。

只修改允许的六个源码/测试文件：config_pge contracts/explorer/session/verify、对应测试和 RPF-56 probe；只新增 rev-4 README/RESULT/三份诊断摘要及真实 Evidence 共六文件。Target、旧 SDK Host、RPF-53/55、旧证书、rev-1～3 报告、AGENTS、Project State/history、Java 外部仓库、Web/CI 未改。新 task root 创建前确认不存在、ignore 生效且父路径非 link/junction。未读取旧 `.local/rpf-56/**` 或 rev-2/rev-3、53/55 的运行账本/marker/raw；SDK 安装和固定 Java 来源仅按授权只读。

## 2. 协议调查、修复与版本选择

rev-3 仅有 `ONE_SELECTION_REQUIRED`，其原始 shape 不可恢复，本轮没有猜测实际 calls 数或其唯一根因。2026-10-20 再核对官方 [Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion/)、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[价格](https://api-docs.deepseek.com/quick_start/pricing/)：non-thinking 可显式指定函数。采用 `tool_choice={type:function,function:{name:select_experiment}}`，保留 disabled thinking、parallel_tool_calls=false、128 最大输出，并继续在 Host 拒绝多项调用。

为遵守 Probe 每次≤1,024 的预留，将提示与目录表示压缩为同一 v4 请求合同，保留全部三候选设计、业务版本/历史、不重复 POST、重复选择和反馈限制。初始完整 request bytes + 最大输出≤1,024，代码在预约前检查。新 Probe 的成功支持该整体方案在本次运行可用，**不单独证明具名 tool choice 修复了 rev-3 的根因**，因为提示也有变化，且没有 A/B 对照。

修复已确认的诊断缺口：响应一收到就独占/fsync 保存 safe_response_shape，绑定 Source/Request/全局 attempt/收到时间，之后才验 usage 和 parse。保存 choices、finish_reason、role、tool_calls presence/type/count、允许函数名、参数/文本指纹、ID/model/usage；未知值映射 OTHER，不保存正文、reasoning、完整 payload 或任意参数。指纹 hash 对 canonical JSON value bytes 计算。纯离线负控验证 malformed、zero/multi、缺字段/错误类型、错误 role/finish/ID/usage、无效函数/类型/参数、字段污染、Call ID 重复与文本冒充 Tool Call；还证明 usage 拒绝之前结构已持久化。

合同/Envelope/反馈/Verifier 全部 v4，owner=`rpf-56-rev4`，Session/Run/Agent 使用 `rpf56r4-*`，root/JAR/output/Base/branch 同步迁移。旧 v1/v2/v3 和 `PROTOCOL_PROBE_ONLY` 不享有 Live 证明等级。TaskBudget 纳入 Probe+正式两角色，SessionLedger 为逻辑子账；每次 I/O 先预约、未知 usage 不释放上界、快照链/锁/重启保持配额。两次合成会话（有增量与合法重复）都通过 `0/2/3` 与 11 rehashed tamper；完整任务账和子账一致/拆分负控也通过。

## 3. SDK 前置与独立 Probe

本轮用原直接 CPython 3.12.13 实际核对当前 SDK core、Pydantic AI 2.57.0 / OpenAI 3.35.1、RECORD、ABI/site-root/runtime mapping；mismatches=0，原 exe/launcher SHA 保持 `e9f7e4ba…645d520f` / `74e02032…2eaeb83`。没有重开系统策略诊断或变更设置，没有解释器 fallback、安装、复制/重签或提权。SDK 元数据检查 1 进程，另有 3 Fixture + 2 Live SDK，分别记账。

三个新 v4 冷进程 Fixture 同源通过，Provider/Java/业务 HTTP=0：normal 与 inhibited 为 4 completions/3 calls/回注 `[2,3,4]`；inhibited 实际到达 FAULT_INHIBITED gate；suppressed 为 3 completions/3 calls/`[2,3,null]`，Host 显式交付错误一次、SDK_ERROR/RuntimeError/exit1。Popen 与 ready PID 对应，正常 report PID 对应；失败 report 无 PID 时保留 null。guard、stderr、端口与线程清理全通过。没有复用旧 Fixture。

协议 Probe 仅执行 **1 次**，`PROTOCOL_PROBE_ONLY`：

- Request SHA=`571f9eb69c731166a5e27aabf2bea7c7d715455a8d7221a6c57b037a82e16230`。
- Response ID=`db76e673-05f9-4ec7-ad2f-8df85981faae`，returned model=`deepseek-flash`。
- choices=1，role=assistant，finish_reason=tool_calls；tool_calls PRESENT/array/count=1，function=select_experiment；参数仅保存类型/长度/hash，正文为空的指纹、reasoning MISSING。
- 386 prompt + 36 completion = 422 tokens；先预留1,024，实际费用保守估算 ¥0.002385，usage 已知。
- 单个真实选择通过严格验证后丢弃；dispatch、Target、Java、业务 HTTP 全为0，未充当 Round1，也未向后续 Explorer 注入 Probe choice。

第一次成功，无失败根因或修复需要，未执行第二次 Probe，未自动重试。Probe JSON 是本轮 Probe 完成时的任务账前缀，最终累计账另见 verification-diagnostic。

## 4. 真实两轮与反馈顺序

Session=`rpf56r4-session-26af76cc05ed4917`。在正式模型/业务 I/O 前冻结两轮各自三候选、Run、namespace、Execution/Effect/Experiment/FaultPlan、source、预算和 TaskBudget 绑定。第一次输入没有 Probe 选择、历史 outcome、B0 或未来反馈；两轮都呈现完整合法目录，没有人工指定 candidate。

| 项目 | Round1 | Round2 |
|---|---|---|
| 真实 candidate | normal | normal |
| Run ID | rpf56r4-564889010b77314ead | rpf56r4-56dfcd46296fc54ec3 |
| Selection Call ID | call_00_mFZkSI7khPJ3OkESJPVZ2973 | call_00_q6VeHNnEtP249ds5VFsZ9028 |
| Java PID / SDK PID | 26712 / 2452 | 15280 / 32700 |
| Target Provider 请求 | 4 | 4 |
| 业务 HTTP / POST / health | 8 / 2 / 1 | 8 / 2 / 1 |
| 最终业务 | v2、rpf53-v2、history[2,1] | v2、rpf53-v2、history[2,1] |
| planned/triggered/observed | false/false/false | false/false/false |

每轮真实 Target 模型发出 inspect_config/create_config_v1/update_config_v2，SDK 完成三次 callback/return，实际 HTTP 与 read-only Authority 对应，两个 POST 无重复。JAR 实际进程 argv 经 CIM 读回并匹配本轮路径、listener 归属和外连检查通过。两轮都是 normal，故没有实际 suppression 或 UNKNOWN_OUTCOME；不宣称本次新增了真实抑制故障样本。只读 reconcile 分支通过 Fixture/协议测试保留，但本次 Live 未触发。

Round1 独立 Trial verdict 成立后生成 feedback SHA=`23d9e56df151a458ca3df3e8d44db54eb1cc7f8d3d374cacde867459cb4af23f`，事件 seq=3；随后 Round2 输入冻结 seq=4，并回注真实 Round1 Call ID 和相同 feedback/Hash。单调时间同样满足先后；每次 response shape 持久事件在 parse/feedback 之前。Round2 feedback SHA=`64595f98bfe3f7dedcb3f46f46b5e6eb988561b13a652050c093cd1ee7b596ee`。完整响应 metadata、角色账、工具 lineage、参数/合同摘要和事件在 Witness，可离线复算。

Java source commit=`0258b9cef02ea74a40989d035c79256c776409c0`，manifest SHA=`33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`；本轮 task JAR=66981576 bytes / SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。仅从固定来源复制至新 root，两个独立 local Java17/H2 namespace；原 Java 源仓库未改。

## 5. 全任务预算与资源终态

| 角色/范围 | HTTPS | prompt | completion | total tokens | 保守 CNY |
|---|---:|---:|---:|---:|---:|
| Probe | 1 | 386 | 36 | 422 | 0.002385 |
| 正式 Explorer | 2 | 991 | 72 | 1063 | 0.0057555 |
| 正式 Target | 8 | 6028 | 533 | 6561 | 0.03672 |
| 正式 Session 小计 | 10 | 7019 | 605 | 7624 | 0.0424755 |
| **rev-4 合计** | **11** | **7405** | **641** | **8046** | **0.0448605** |

11 个请求全部 RECEIVED，unknown=0、pending reserved tokens=0，自动重试=0；每个预约都保留在不可变链中，成功 usage 结算实际消费，未知请求不按0或释放上界。遍历全部 TaskBudget 快照，“已确认+未决预约”的峰值 Probe=1024、Session=11136、全任务=11558，均在相应上限内。没有按角色拆出新的12次或另给Session ¥1。

价格使用当天官方峰值 cache-miss 输入 USD0.30、输出1.20 每百万 tokens，以 ×15 guard 得 CNY4.5/18；估算不是实际汇率/扣款。与 rev-3 的540 tokens 完全分开，不回收旧消费。当前 API returned model 记录为别名 deepseek-flash，不把别名写成独立验证的 backend build。

正式 JVM=2、业务 HTTP=16、POST=4、health=2。两个 Java、两个 Live SDK 与三个 Fixture 均退出；Java/Host ports closed、host thread stopped、local synthetic key released 全通过，收口再次检查两个业务/Host端口关闭。无 pending Provider/POST；SDK child 不带 Provider/业务 key，Java 仅获本地合成 key；无 secret/private text 导出。当前 ignored root 保留 JAR、SDK scratch、回归快照、结构诊断、WAL/marker/raw health 和控制样本；未清理或重置旧任务材料。

## 6. Witness、回归与源码

新证书：`spikes/rpf-56/rev-4/config-pge-evidence.json`，原始 bytes SHA256：

`4d565511cc1093d350700b4b360b276b519d6b5effa6be0e1cdfadfe2b32d26b`

真实 candidate raw 与正式文件 bytes hash 一致。独立 CLI correct/missing/wrong=`0/2/3`；11 类重新计算内外摘要的篡改均 exit3：伪造选择、反馈 hash/时序、分角色预算、重复 POST、伪造故障、namespace 拼接、虚假 ACK、source、SDK PID、cleanup。Task总账与正式子账相互映射、Probe被提升为Live/旧schema/shape污染也有离线负控；没有把Probe或合成数据拼成真实回合。

22 项定向、335 项隔离全 Runtime 通过，2 Docker unavailable skips 单列；九件 RPF-43/44/48/49/50/51r4/52r3/53r6/55r2 固定 SHA 独立 verifier、Reviewed/Public Docs、diff/范围/密钥检查通过。隔离测试使用 Parent git archive 叠加六个允许文件，源 hash 全匹配；阻止 Java/Docker 与外部网络，未用其替代实际 SDK/Provider/Java 验收。

执行/交付 runtime source map 完全相同；Verifier=`rpf56-config-pge-verifier-v4`，SHA=`697ccd3ec7d5b2ef0d3c7b4c8327b9a5bc7907f40e2a55046d6099d116b622e6`。所有可执行源码在 Fixture/Probe/Session 前冻结，之后未修改；只补充非证书诊断和报告，不改 payload。source hash 按 LF 规范化，证书外部 SHA 按原始 bytes。没有运行 Maven/Web/hosted heavyweight Gate，未改 UI 或部署。

## 7. Acceptance 与边界

| Gate | 状态 | 证据 |
|---|---|---|
| A-01 Identity/保护 | PASS | 精确 Parent/ref/root、规则、白名单、ignore/link和用户保护；旧运行材料未读。 |
| A-02 v4合同/硬边界 | PASS | 新身份/root/source、旧版本拒绝、角色/未来反馈边界与预算负控。 |
| A-03 协议可诊断 | PASS | parse前持久结构/时序，错误矩阵及正文/推理/参数泄漏负控。 |
| A-04 离线/SDK前置 | PASS | 两份合成0/2/3+11负控，三个新v4真实SDK冷进程。 |
| A-05 有界真实Probe | PASS | 1次真实合法单ToolCall，零工具/业务派发；第二次未需要。 |
| A-06 真实两角色 | PASS | 2真实Explorer selections、2真实Target三工具链与总账对账。 |
| A-07 Java/Effect/故障 | PASS | 两个fresh Java/H2，v2/history21、无重复POST、normal真实无故障、清理通过。 |
| A-08 真反馈时序 | PASS | 第1轮feedback seq3先于第2轮freeze seq4；Call ID/hash匹配，合法重复。 |
| A-09 真Live Witness | PASS | 新真实Envelope、外部SHA0/2/3和11 rehashed tamper，完整源/模型/业务/预算/清理。 |
| A-10 回归/Git/回传 | PASS | 回归/安全通过，focused commit普通push，fresh ls-remote与GitHub commit身份一致，main/Parent不变；本记录单独提交收口。 |

这是一次有限机制会话，正常候选重复不证明统计优势、强因果或系统安全。issuer_authenticity/database_independent_authority=`NOT_ESTABLISHED`，independent_reproduction=`NOT_TESTED`，WorkSwarm=`NOT_PROVEN`，attribution=`CORRELATIONAL_ONLY`。不由Codex宣布主线接受或阶段推进：**EVIDENCE_ACCEPTED=PENDING_ARCHITECT_REVIEW；STAGE_ADVANCED=NOT_DECIDED**。

首次完整交付 commit=`065f3c6ab9d876a6c443a1b3796cd411a3e324f5`，已普通 push 至指定新分支；fresh ls-remote与本地一致，GitHub connector独立取回同SHA的commit及12个精确白名单文件。main仍为`bda0cd49e50e3181f604324e94877a24b9885334`，Parent仍为`296caf60afe6377634481986e3c383c9381c0f9a`；工作树只剩用户原有`?? docs/reviews/`外层条目。暂存的证书Git blob与实际原始bytes相同，SHA未变；执行源码/Verifier/测试与交付blob一致。本状态记录单独文档提交收口，最终SHA由聊天回执给出。feature push不匹配main自动Gate，未请求hosted CI。

交付后由 Architect 独立审查新证据，另行决定是否需要重复实验/限定归因或后续整合。本轮不追加样本、不修改main、不建PR、不发布/部署、不改Canonical Project State。
