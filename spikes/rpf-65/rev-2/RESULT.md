# TASK_RESULT｜RPF-65/rev-2

**Status: PARTIAL（技术 Gate 已通过，等待 Git 交付）**。本修订完成真实 ConfigPort 工厂修复及唯一受控真实 Target Trial；任务整体 COMPLETE 仍需 focused commit、普通 push 和远端双读回执。`STAGE_ADVANCED` 与证据接受由 Architect 决定。

## 1. 身份、隔离与历史保护

- Repository：Public `MyKr-YSteinsK/runproof`；origin=`https://github.com/MyKr-YSteinsK/runproof.git`。
- 精确 Base/rev-1：`ddb3490543504377a2d2603ee6b088910399a723`；RPF64=`a4d956c0b69f7dacd34e842676d10c1898353cdf`；RPF63=`7896e9789015da946b5a057c620b2faa90b57318`；main=`bda0cd49e50e3181f604324e94877a24b9885334`。
- 新分支：`codex/rpf-65-rev2-real-config-target-factory-repair`；独立新根：`.local/rpf-65-rev-2/`。G0 确认该分支本地/远端不存在，八个 create-only 路径及新根不存在，ignore 与无链接逃逸检查通过。
- 原工作树仅顶层 `?? docs/reviews/`，没有枚举、进入或操作其内容。旧 `.local/rpf-65/` 只检查目录本身存在和属性，不读其 WAL/trace、不复制任何旧额度、JAR 或现场。
- rev-1 的公开证据、probe、README、RESULT、历史16证书保持原字节。其 `single_full_green=false` 和本地31帧摘要仍是历史报告，**本修订未独立读取或验证旧 WAL 字节**。

## 2. 实际修复、Source Identity 与工厂证明

`ConfigPort.execute` 现在直接调用 `assemble_host(ctx, ct, ledger, *, api_key=None)`，由该工厂创建同一 Journal、HTTP client、Broker、Business 并显式执行 `Host(ct, broker, business, journal, fixture=False, api_key=...)`。它验证 `Host.ledger is broker`、`broker.total is ledger` 及 Business/client/Journal 的同一性。

新增测试实际穿过这个生产工厂：签名绑定和对象同一性；故意漏 Broker 的 mutation 被 TypeError 阻断；未替换 execute 的真实调用到达工厂后注入 setup error，验证无 child/network/key 和清理；完整非模型集成保留 Session/Port/工厂/Host/Broker/Business/Oracle，仅模拟进程/SDK/HTTP 边界。原 `fake_scene` 仅用于合成 Verifier 测试。

邻近修复包括 SDK 错误后的 GET-only 对账、收据/读回异常仍执行嵌套 finally 清理、结构化 scene/cleanup 取证。免费测试还复现了固定 SDK 的 `SDK_ERROR` 报告不含 PID 所引发的 Verifier KeyError；修正后严格要求 ready/Popen PID 一致、精确错误报告形状，成功报告仍绑定 report PID 和 usage。没有放宽 Authority、Source、WAL 或工具来源条件。

ABI 保持 `rpf65-config-domain-port-v2`，序列化合同形状未变；base/branch/workspace/new probe/source hash 区分本修订。六个 source-lock 路径及其依赖共24项，LF Source Map digest：

`fef2a101a4ca1a59005182fb2e5ff08fe0db62ed446f0697ce3aa0826939141a`

逐文件 LF hash 见 preflight-diagnostic 的 `source_freeze.sources`。Verifier=`rpf65-target-config-verifier-v2`，LF SHA256：

`37ee561e827862ebc6cb33e11afdc943865c63f32bcb4914c0e6657eb50e578b`

Source Freeze 前 staged/unstaged 空白检查均 exit0，免费验证完成后冻结；metadata/cold/live 和证书验证后六个源保持一致。两个 ignored 验证脚本亦在冻结记录中锁定 hash。没有冻结后修源码或 whole-run retry。

## 3. Gate 实际状态

| Gate | 状态 | 证据 |
|---|---|---|
| G0 | PASS | 精确 Base、独立新分支/8路径/新根、用户状态和 push 安全 |
| R2-A01 | PASS | 新 branch/root/Run/Source Map、单主 WAL；rev-1 证据未改 |
| R2-A02 | PASS | 同一生产 factory、signature/object identity、漏 Broker 负控、未替换 execute 集成 |
| R2-A03 | PASS | Role/预算/UNKNOWN/POST2/锁/非返还/cleanup 免费检查及真实 WAL 一致 |
| R2-A04 | PASS | 固定 SDK/JDK/JAR/source，metadata1/cold1，RECORD/PID/回注/cleanup |
| R2-A05 | PASS | 真实 Provider5、SDK/JVM 各1、真实业务 HTTP9/POST2及独立读回 |
| R2-A06 | PASS | v2已提交后 ACK suppression，故障四态均true，UNKNOWN后仅只读恢复 |
| R2-A07 | PASS | 新真实原件及外部锚、CLI0/2/3、22类重锚负控全部拒绝 |
| R2-A08 | PASS | focused14、合成22、历史16、Reviewed/Public；fresh full426单轮通过/2 Docker skip |
| R2-A09 | PASS | TARGET5/Explorer0、4841实际tokens、12600预约、费用守卫内、所有资源结算/清理 |
| R2-A10 | NOT_RUN | 等待本次交付 commit/push/fresh ls-remote 与 GitHub API 双读 |

## 4. 免费验证与固定环境

- 最终 focused 14项 PASS，wall42.972秒。生产工厂及完整非模型执行体均被覆盖。
- 开发第一轮13项有1个 KeyError，暴露 SDK error-report PID 不一致；第二轮14项有1个纯测试占位值缺失错误，触发 Host 的 `DEEPSEEK_KEY_UNAVAILABLE` 形状检查。修正的是合成 fixture，占位串不是真实凭据。两次均发生在冻结前，没有真实网络或 Provider Key 读取。详情和耗时保留在 verification-diagnostic。
- 明确合成证书 CLI0/2/3与22类重锚攻击通过；独立检查器还重算 history observation 内部 hash，验证空 history 的语义拒绝。来源攻击随真实/合成等级翻转，要求攻击副本字节确实改变。
- 历史16件按原 SHA 与原 Verifier 全部 exit0；Reviewed/Public 均 exit0。
- Runtime 快照预检637个 tracked/显式路径，验证rev-2的24项和RPF60的32项 Source Map 完整，包含全部8个 Web/vite依赖。Python3.14.6 下首次全套 **426项、0失败、0错误、2 Docker skip**，测试580.182秒，wall582.135秒；`single_full_green=true`，full runs=1。Docker provider unavailable 被明确跳过；未跑 Maven/Web build、未启动额外业务 JVM/SDK。
- 新 metadata inspector1次，通过固定 Python3.12.13、Pydantic AI2.57.0/OpenAI3.35.1 和 SDK RECORD mismatch=0。Java17.0.12 release/executable hash 匹配；JAR由固定已授权源新复制，66,981,576 bytes，SHA256=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。源commit=`0258b9cef02ea74a40989d035c79256c776409c0`。
- 唯一 cold SDK PID848，fixture五轮completion/四次工具回调，UNKNOWN→只读回注及cleanup通过；Provider/JVM/真实业务HTTP为零。所有路径与身份均为本修订新根，新旧现场不拼接。

## 5. 唯一真实 Trial 与独立效果

Session=`rpf65-session-1dc782fc322142a0`；Run=`rpf65-config-1dc782fc322142a0`；Environment=`env-rpf65-config-1dc782fc322142a0`。三份合同、owner/role、Source Map、端口与paid gate在执行前冻结。正式SDK PID3108、JVM PID25792，固定源码/argv/JAR/ready/SDK report和WAL身份一致。

实际 Provider 返回 model ID=`deepseek-flash`，5个唯一 response ID、4个真实 ToolCall ID，SDK5次request/4次callback与Host/Provider/WAL完全对齐；具体ID及各轮usage/hash见 trial-summary 和 Witness。官方文档所述 backend版本并非额外观测到的返回ID。

真实业务顺序：初态current不存在/history空 → Target inspect ABSENT → create v1 → update v2 HTTP200且业务code0 → Host记录真实提交成功后抑制ACK，以同一ToolCall返回显式UNKNOWN → 模型发起一次inspect → 父进程独立GET current/history/list。

结果为 `CONTRACT_SATISFIED_IN_RUN`、recovery=`OBSERVED`；fault planned/triggered/observed/agent_exposed均为true。HTTP共9次，POST恰好2次，health GET1次；UNKNOWN之后没有POST。最后current.version=2/value=`rpf53-v2`，history=[2,1]，list只有一个v2项目。Authority=`SAME_SERVICE_READ_ONLY_HTTP`，独立于模型Tool Return；不声称独立数据库或第三方审计。四个Tool Return在request2/3/4/5回注，返回hash和原ToolCall来源已验证。

## 6. 预约、费用、WAL 与清理

本修订 metadata1/cold1/session1/trial1/JVM1/正式SDK1；TARGET Provider5，Explorer0。输入4376/output465，总4841 tokens；全部usage已知。不可返还预约12600/15000 tokens，预约费用上界¥0.065817，实际usage按守卫价估算¥0.028062；都低于¥0.50，不是账单金额，没有返还或挪用rev-1额度。

2026-10-22执行前再次核查[官方定价](https://api-docs.deepseek.com/quick_start/pricing/)和[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)：按高峰输入/输出USD0.30/1.20每百万tokens，乘CNY/USD×15审慎守卫，分别4.5/18 CNY每百万tokens。每轮输出≤256，transport retry=0；全程只有一次真实 Trial。

唯一主账本 `.local/rpf-65-rev-2/account/ledger.jsonl` 为136帧，所有票据已结算，usage unknown=false；原始WAL SHA256=`2d880586aa2562556645fc147de398b3ff05314d59713b73abddfd7e14942115`。这是本修订新WAL，旧WAL未读取。SDK/JVM均退出、Host thread停止、Java/Host/cold端口关闭、business/Provider key引用释放；子进程环境无Provider Key，未提交JAR/本地WAL/scratch/logs。冻结后没有失败重跑、配额重置或扩大资源。

## 7. 真实 Witness

- 原件：[target-witness.json](target-witness.json)，197,496 bytes。
- 外部原始SHA256：`2c8691137603cc69d9a1cf92f7800da65dd803bd8e49291187caecac6c5eea2d`。
- Schema=`rpf65-target-config-witness-v2`；Source/Verifier hash见第2节。
- 正确锚CLI exit0、缺锚exit2、错锚exit3；22类修改副本重算Envelope与外部SHA后全部exit3。真实来源等级攻击方向为REAL→SYNTHETIC；不对原件写入或重新格式化。
- 所有公开证据仅保留固定合同、结构化Tool/HTTP/usage/PID/哈希；不保存实际Provider请求原文、模型自由输出、Reasoning、凭据或私人绝对路径。

## 8. 交付与能力结论

当前实际修改4个既有白名单文件：`pge_r65_context.py`、`pge_r65_target_config.py`、`pge_r65_verify.py`、`test_effectwitness_pge_r65.py`；`pge_r65_session.py`无需修改。新增本rev-2八个create-only文件。rev-1公开证据及其他旧源码/历史证书不改，用户目录保持原样。

本结果候选等待普通push和远端双读；不把本地commit当已交付。最后commit SHA在提交后的聊天TASK_RESULT提供，不循环回填自身未来SHA。main/RPF64/rev-1分支不推送、不合并；PR、force/rebase/amend已推送历史、release/deploy、比赛登录/报名/上传均NOT_RUN。

本轮证明：在RPF64结构协议/ProcessSupervisor基础上，**新版本Context/ConfigPort/Session与同一物理WAL**完成了一例真实配置Target闭环。没有宣称旧RPF64 `SharedSession.execute`直接运行真模型。三个native child实际共用同一个ProcessSupervisor实现。Host/Broker/metadata/SDK/Java生命周期仍有任务适配复制债，详见capability-assessment，不称完全泛化。

Explorer=NOT_RUN，订单真实Target=NOT_RUN，跨域双真实Agent=NOT_PROVEN，Web=NOT_INTEGRATED，L2=NOT_TESTED，统计因果=NOT_PROVEN，Issuer真实性=NOT_ESTABLISHED，独立新执行复现=NOT_TESTED。建议Architect审核本次证书与真实工厂边界，再决定是否推进其他Domain或共享Context配置化；本任务不自行扩展。
