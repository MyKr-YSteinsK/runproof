# TASK_RESULT｜RPF-65/rev-1

**Status: Partial**。正式配置 Target 入口在 Host 构造参数绑定阶段发生平台错误。Source Freeze 后没有修改源码、重试 Trial 或续额；真实 Provider 尚未调用，没有真实 Witness。按 Plan 的冻结后语义修复条款保留现场，需 rev-2 继续。

## 1. 身份与保护

- Repository：Public `MyKr-YSteinsK/runproof`；checkout root 为 `runproof`，ignored task root 为 `.local/rpf-65/`。
- Base：`a4d956c0b69f7dacd34e842676d10c1898353cdf`；parent：`7896e9789015da946b5a057c620b2faa90b57318`；main：`bda0cd49e50e3181f604324e94877a24b9885334`。
- 新分支：`codex/rpf-65-real-config-target-port-bridge`，origin 为 `https://github.com/MyKr-YSteinsK/runproof.git`。创建前本地和远端同名分支均不存在；13 个白名单路径在 Base、相同 SHA 的远端 Base 和工作树均不存在。新根不存在、受 ignore、父路径无链接逃逸。
- 原工作树只有顶层 `?? docs/reviews/`；没有枚举、进入或操作该目录。旧 tracked 源、canonical docs、历史 Witness/Source Map 均未改。普通新分支 push 没有部署触发器。

## 2. 验收状态

| Gate | 状态 | 实际证据与缺口 |
|---|---|---|
| A-01 | PASS | 精确 Base/父/main/远端、create-only、root 和 push 安全检查 |
| A-02 | FAIL | 新 ABI 与结构协议已实现；真实 ConfigPort 的 Host 参数绑定失败 |
| A-03 | PASS | 单物理 fsync/hash-chain WAL、TARGET 预约、未知 usage 停止、预算/锁负控通过；真实 Provider 计量 NOT_RUN |
| A-04 | PASS | metadata 1 次和 cold 1 次；固定 SDK/JDK/JAR/source 身份、cold Tool Return/PID/cleanup 通过 |
| A-05 | NOT_RUN | 正式入口进入后立即失败；Provider、正式 SDK/JVM、业务 HTTP 全为零 |
| A-06 | FAIL | planned=true，triggered/observed/agent_exposed=false；故障与恢复未形成现场证据 |
| A-07 | NOT_RUN | 没有真实证书；合成 CLI `0/2/3` 和 22 类重锚攻击有效 |
| A-08 | PASS | 组合验证：首轮418项因快照漏输入而2失败/12错误/2 Docker skip；补齐8个 tracked 输入后，受影响13项全部通过。未声称单轮全绿；focused/历史16锚/Reviewed/Public 通过 |
| A-09 | PASS | 真实费用/Provider/POST 为零，cold 已退出、端口关闭；未决预约与失败现场保留 |
| A-10 | NOT_RUN | 本结果待 focused commit、普通 push 和 fresh 远端读回 |

工程任务尚未 COMPLETE；真实 Target 经版本化 Port 的研究假设为 `NOT_PROVEN`。不作 `EVIDENCE_ACCEPTED` 或 `STAGE_ADVANCED` 决定。

## 3. 接口、复用和复制债

新 ABI 为 `rpf65-config-domain-port-v2`。新 Context/Session、角色预算和 Verifier 不修改 RPF-64 Provider0 的语义；旧 selector、projection、TaskContext 和 SharedSession 不用于本轮真实来源。

Cold 实际调用链：probe → session.cold → 新 Host/SDK runner → 原 `ProcessSupervisor.start/received/close` → 固定外部 SDK → loopback Host → fixture/memory backend。Supervisor 使用新 Context 的 `scope/once/public` 与新 Ledger 的 `reserve/settle/append`；Provider transport 和正式 Java lifecycle 没有实际运行。

`DomainPort` 四方法结构接口直接引用原定义。底层 `ConfigLiveHost` 的启动、身份、工具注册/回注和 fixture 方法在 cold 中复用。Broker、Host guard、metadata、SDK runner 和 Java readiness/cleanup 包含从 RPF63/64 适配的代码；不声称完全泛化。RPF62 Java driver 和 RPF63 Port 各有直接 Popen=2、global WORK=5；RPF64 和新 Port 各为 0/0，实际 Supervisor 复用本轮只证明 cold child。逐文件 SHA、A/B/C 选择和复制维护成本见 capability-assessment。

本次缺陷也暴露复制接口与调用点之间的维护风险：测试的 `fake_scene` 替换了实际执行体，未覆盖真实 Host factory。必要后续测试必须覆盖该装配边界。

## 4. Source Freeze、固定环境与实际执行

冻结 Source Map 共 24 项，包括 6 个新增源/测试/probe、实际依赖、固定外部 SDK 源和 SDK pin 的历史公开证书。LF Source Map digest：`e8fe7cdcaccb5eb8db59b4aa2e0f2e70e3f2ac8b3078a8bc4dc58f8e3c2a6910`。冻结前 staged/unstaged whitespace 检查 exit0；冻结后源码与 index/Source Map 保持一致。

metadata 验证 Python3.12.13、Pydantic AI2.57.0/OpenAI3.35.1、RECORD mismatch=0；Java17.0.12 与 release/executable hash 已核对。源 commit 为 `0258b9cef02ea74a40989d035c79256c776409c0`，JAR 66,981,576 bytes、SHA256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`；复制到当前 task-owned jar。完整 hash 见 preflight-diagnostic。

Cold SDK PID=28384，五轮 completion、四次工具回调、UNKNOWN→只读回注、工具结果 `[2,3,4,5]` 轮次绑定通过；SDK 退出、Host thread/port 清理通过。没有 Provider/JVM/业务 HTTP。

正式 Session=`rpf65-session-98e1e526fcc24743`；Run=`rpf65-config-98e1e526fcc24743`；Environment=`env-rpf65-config-98e1e526fcc24743`。三合同与端口在 Context 冻结。实际链路停于 `pge_r65_target_config.py:119`：

```python
Host(ct, ConfigLiveBusiness(ct, client), j, fixture=False, api_key=self.api_key)
```

签名要求 `contracts, ledger, business, journal`，漏传 `broker` 导致后续位置参数移位，抛出 `TypeError: missing a required argument: 'journal'`。只读 `inspect.signature(...).bind(...)` 复核了原因，没有再次运行 Trial。初次本地诊断手写位置标签为136，实际 `rg` 校正为119，公开诊断记录了这次标签修正。

故障未触发，业务效果/Agent 恢复均未评估；这不是 `AGENT_FAIL_GUARDED`。本轮无实际模型 ID、Provider response/ToolCall/真实 Tool Return、HTTP/POST 或 Authority 收据。父 Host 已按 Gate 读取既有凭据，但没有网络调用，也未把密钥传给 SDK/JVM或写入证据。

## 5. 预算、WAL 与清理

单物理 WAL：`.local/rpf-65/account/ledger.jsonl`，owner=`rpf-65`，31帧。metadata=1、cold=1、session=1、trial=1，其余 Provider/JVM/正式 SDK/http/post/health 全为0。`session-1`、`trial-1` 未结算并保留，不退款、不重命名或删除根续额。

实际 TARGET/EXPLORER requests、输入/输出/总 tokens、费用均为0，usage 无未知 Provider 请求。上限为6次 TARGET、Explorer0、15000不可返还 tokens、¥0.50；按所有15000 tokens 均以输出守卫价计算为¥0.27。实际请求级预算未消耗。

2026-10-22 核查 [官方模型与价格](https://api-docs.deepseek.com/quick_start/pricing/) 和 [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)：候选 `deepseek-flash` 当前服务模型为 `DeepSeek-V4.1-Flash-1017`，高峰输入/输出分别 USD0.30/1.20 每百万 tokens；采用 CNY/USD×15 的保守汇率及附加守卫，对应输入4.5/输出18 CNY每百万。此为预约估算，不是账单。

正式子进程未启动，无正式 PID 需要终止；cold PID 已退出，三个冻结使用端口关闭。失败现场保留于 `.local/rpf-65/quarantine/`；没有对用户或旧任务资源做清理。公开工件检查无密钥形态、绝对私人路径或自由模型/推理文本；未提交本地 JAR、SDK scratch、WAL、snapshot 或日志。

## 6. 证书与回归边界

**没有创建 `target-witness.json`**，原件 bytes/raw SHA 为 NOT_APPLICABLE；真实证书 CLI 为 NOT_RUN。纯 Verifier 身份为 `rpf65-target-config-verifier-v2`，LF SHA256=`031a96d8b6af15b438b50f207ba2ebfd29788484eae36959cbd9f65d438d87df`。

冻结后的明确合成样本正确/缺锚/错锚 CLI 为0/2/3；22类重算 Envelope 和外部锚的语义攻击全部 exit3，涵盖来源升级、owner/ABI/source、角色、输入/费用上界、未知/缺 usage、模型/Tool ID/结果、重复 POST、Authority/历史/读回、故障真值、PID/cleanup、反馈与cold。合成通过不代替真实链路。

Focused tests=6 PASS；历史16件原锚校验全部 exit0；Reviewed/Public exit0。隔离 Runtime 全套首轮执行418项，625.227秒（wall 628.243秒），2失败、12错误、2 Docker skip；根因为快照漏带 RPF60 Source Map 所需8个 tracked Web/vite输入，FileNotFound 后造成 Gateway source gate 503。未改源码，补齐原字节后仅复验受影响的2模块13项，全部通过，wall 332.846秒；原首轮日志保留。组合复用未受影响首轮结果，未获得或声称第二次单轮全绿 full。此快照准备错误与正式 Host factory TypeError 分别记录，不重跑 paid/cold。独立复现 NOT_TESTED、Issuer真实性 NOT_ESTABLISHED、L2 NOT_TESTED、跨域双真实 Agent NOT_PROVEN、订单真实 Target NOT_RUN、Web NOT_INTEGRATED。

## 7. 交付与继续条件

本轮应交付12个新增白名单文件：4个 Runtime、1个测试、probe、README、RESULT、4个诊断/评估摘要。第13个真实 Witness 因证据不成立而不创建。旧文件不改，`docs/reviews/` 保持原顶层未跟踪状态。

交付待 commit→普通 push→fresh ls-remote/GitHub SHA 读回；最终 commit SHA 在提交后的聊天 TASK_RESULT 中提供，本文件不回填自身未来 SHA。main/parent 不推送；PR、合并、部署、发布、比赛登录/报名/上传均 NOT_RUN。

需要 Architect 审查本次平台失败与测试覆盖缺口。rev-2 的最小未实施修复为：`Host(ct, broker, ConfigLiveBusiness(ct,client), j, ...)`，增加实际 factory/binding 单测；明确允许改变冻结的源码与新 Source Identity，指定新的任务根/分支/额度后重新执行免费 Gate 和唯一真实 Trial。本轮 occupied root/分支与消费记录必须保留。
