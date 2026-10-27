# TASK_RESULT｜RPF-74 / rev-1

Plan ID: RPF-74

Revision: rev-1

Status: Partial

本轮真实本地双域 N/F、固定 SDK 与受控故障闭环已执行；但合成模型槽没有逐项原生 reserve/result，**R74-A03 FAIL**；独立离线验证器漏检了一项用量重锚篡改，**R74-A06 FAIL**，因此不能报告 COMPLETE。真实 F 原始 SDK 输出与 Factory 在线核对通过；这一缺陷影响的是离线验证器对伪造摘要的独立识别，不能据此推翻或扩大真实业务事实。

Base `22276cb6aa44eeaef46bcc576170eb317b73e7cf`；Source commit `a852d77a0e61322540b2ce8e606ec14abc5dd62a`；新 Source identity `16389b0d53de4f213959217a0d630dcec5b5ba01903cb7b9189d6cf36c06811f`。源码冻结后未修改。最终报告 commit 与 Git/API 两轮读回由聊天补足。任务分支 `codex/rpf-74-factory-controlled-business-fault`；main 未合并。

## Gate

| Gate | 状态 | 证据 |
|---|---|---|
| G0 | PASS | 25 paths absent at G0; pinned SDK/JDK/JAR verified; user authorized isolated full-snapshot exception |
| R74-A01 | PASS | New owner/source/contract and one versioned v2 factory; old exact-type Factory unchanged |
| R74-A02 | PASS | Four formal real fixed-SDK child PIDs; ready/report/callback/raw output and sanitized Popen evidence |
| R74-A03 | FAIL | Business resources have native reserve/result; synthetic model slots lack native reserve/result and native reserved_tokens is zero |
| R74-A04 | PASS | N all false; F both domains commit then internal HTTP RemoteDisconnected, SDK UNKNOWN reinjection and read-only reconcile |
| R74-A05 | PASS | Config DOMAIN_VERIFIED then FEEDBACK_FROZEN before scripted Order choice; no real Explorer claim |
| R74-A06 | FAIL | Reanchored order SDK report input_tokens+1 was accepted by offline verifier with exit 0; usage mismatch not independently rejected |
| R74-A07 | PASS | Focused and unfiltered Full with Docker accounting; see runtime-diagnostic |
| R74-A08 | PASS | 24 public verifier entries plus R69 CLI 0/2/3; old private roots not read |
| R74-A09 | PASS | Honest capability, 101 rejections, the additional accepted usage forgery, limitations and alternatives |
| R74-A10 | NOT_RUN | Report creation state; final commit/push and two remote readbacks supplied in chat |

A10 是报告生成时状态；最终交付状态以聊天回执为准。EVIDENCE_ACCEPTED 和 STAGE_ADVANCED 仍待 Architect。

## 本轮证据

| 场景 | Config | Order |
|---|---|---|
| N | Java/H2 ABSENT→v1→v2，SDK PID 16504，故障四态全 false | SQLite PAID→REFUNDED 2500，唯一 receipt，SDK PID 3852，故障四态全 false |
| F | 实际提交后内部 HTTP RemoteDisconnected，SDK PID 20940，四态全 true，只读回查 v2/history | 实际退款提交后内部 HTTP RemoteDisconnected，SDK PID 26720，四态全 true，只读确认唯一 receipt |

两个场景分别使用独立 Context 和一份 native WAL：N `0df9e8ae1cc8c065140c57c44361bb7a4458fb235152dad89e4ea49302318e10`，F `a304a5f5277896a60dde4ff939e32a6372ad2d79d69d80fa2acb7483fd32f6ab`；原始 Manifest SHA 分别为 `2179b444048de757e9f39150b1b6c1dd21d7d178810c4a97dc7a5c334ec3e719`、`1acd8eabdc34ac6328331e09402108ad5084c04f46c624d33a7d006ccc355cb5`。Config 的独立 Authority 是同一任务服务的只读 GET/history，Order 是独立 SQLite mode=ro/query_only 连接；均不是第三方签名。Config 验证后冻结反馈，Order 的 scripted choice 实际消费该反馈哈希；不证明真实模型自主策略或 L2。

N/F 各使用 Config/Order 一个真实固定 SDK child，共 4 个；另有开发 smoke 各 1 个，总计 6 个。固定 Python 3.12.13、PydanticAI 2.57.0、OpenAI SDK 3.35.1，Java 17.0.12 和 JAR pin 见 preflight/source map。Provider 调用、真实 token、费用和宿主 Key 查询均为 0；SDK child 的 absence getter 仅在净化环境中执行。每个进程/端口清理与实际 Popen 环境摘要见业务矩阵。

资源票在单一 native WAL 记录授权与原生 reserve/result；脚本合成模型槽同样持久记录在该 WAL 的 SLOT_GRANTED/MODEL_REQUEST。N/F 合成槽上限预约分别为 314000 / 474000，native Provider 的 `reserved_tokens` 为 0；不能把合成槽描述为真实 Provider token 或原生 Provider 票据。

## 独立验证反例

101 项真实 CLI 负控被拒绝：43 启动前授权、52 跨域/业务/故障/反馈、6 项内部摘要和 WAL 深度重锚；无 TEST_INVALID。N/F 原件均实测 anchor 0、无 anchor 2、错误 anchor 3。

额外独立反例把 F 的 Order `sdk.report.input_tokens` 加 1，同时重算对应 stdout 原字节、摘要、关联 WAL 链和外层 anchor；原数据库无新增写入。新锚 `8621579e14d0f0876843e33682daba22c6c931eb40816c16d12dea93c7906e3c` 的原生 CLI **exit 0 / PASS**，属于不应接受的语义篡改。原因是 `pge_r74_launch_factory.py:69` 在线比较 SDK usage 与响应行，而 `pge_r74_verify.py:24` 没有在离线验证时重新计算该相等关系。冻结后未修改源码或重签旧证据。

## 验证与隔离

Focused 32 项、PASS；历史公开 24 入口及 R69 CLI 0/2/3 为 PASS。Full：Ran 723; OK (skipped=2); exit=0; errors=0; failures=0; discovered=728; exact ID multiset=True。原 Docker 两个类 skip 覆盖 5 个方法，实际统计与 stdout、发现清单对应关系见 runtime-diagnostic。旧 Win10053 是否修复仍未证明。

用户额外授权完整回归在原 `.local/rpf-73-rev-2/` 下新建专属 `rpf-74-regression-20261027/` 快照，以及在该根 `tests/` 下新建随机测试子目录；其余运行产物在 `.local/rpf-74/`，不读取、覆盖或删除已有旧任务证据。`docs/reviews/` 保持未跟踪、未读取。

## VERIFIED_FINDINGS

- F01 / HIGH：`pge_r74_launch_factory.py:30`、`pge_r74_sdk_harness.py`；四个正式 child 在相同 Factory frame 运行两域，原始请求和回调见任务私有 Manifest。反例：固定 scripted 模型和本地模拟不证明真实 Provider 或独立 child attestation。
- F02 / HIGH：`pge_r74_domain_ports.py:31`、`pge_r74_fault.py:12`；F 的真实提交、内部连接关闭、UNKNOWN 回注和只读对账均在当前 WAL 与 Reader 中。反例：同 Host 受控注入不证明生产网络行为。
- F03 / HIGH：`pge_r74_launch_factory.py:69`、`pge_r74_verify.py:24`；在线 usage 核对通过，但上述独立重锚篡改被 verifier 接受。反例：真实运行的原始结果未被改写，缺陷是离线拒绝能力。
- F04 / HIGH：`pge_r74_budget_gate.py:112`；合成 slot 上限记录为同 WAL 派生事件，native Provider 资源未预约。不要把这描述为真实 Provider 计量。各源码 raw/LF/Git blob 见 source-identity-map。

## CODEX_ENGINEERING_JUDGMENT

当前 v2 不应提升为公共默认 Launcher：合成模型槽缺少逐项原生 reserve/result，独立用量验证也出现具体反例。显式 Factory 确实不依赖旧 Driver 的 frame/profile 委托，但本轮没有测量可归因的维护或性能优势。组件在真实本地 Port 路径工作，不代表完整公共 Core 已迁移。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

| 方案 | 代码与依赖 | 平台、费用与历史兼容 |
|---|---|---|
| 继续任务特化 v2 | 本轮 12 个文件共 1951 行，依赖固定 SDK、旧业务适配器和新 Gate；重复维护 Source 闭包 | 仅证 Windows、本轮 Provider 0；旧证据不变，当前本地业务和验证缺口仍须处理 |
| 抽取显式公共 Factory/DomainPort 薄接口 | 行数未估；需版本化生命周期、Port、Policy 和 verifier 合同 | 先验证 Windows，其他平台未知；纯接口测试无 Provider 费用，需保留旧入口和原始证据 |
| 迁移 NativeCore/新 SDK child | 仅 R72R3 session、ports、SDK contract、verify 四个旧文件已有 949 行；新增工作未估 | 协议和业务风险最大，跨平台未知；真实 Provider 费用需另授权，旧 Guard 与证据不能改写 |

## NEXT_DECISION_RECOMMENDATION

建议在新任务中补齐合成模型槽与原生账本的逐票预约/结算合同，并为 verifier 的 SDK 请求/响应与 RunUsage 增加独立重算和重锚拒绝测试，建立新的源码身份并按实际权限重验；不要修补本轮冻结源码后重签现有 Manifest。后续真实 Provider、新 child 独立 attestation 及第三域扩展均需独立授权。

## POTENTIAL_GENERALIZATION_DEBT

已证：Windows 固定解释器/JDK 路径、版本化 Source/Owner 闭包、运行时与 SDK 凭据净化差异、控制器与独立 Reader 的信任边界、旧 inactive audit 存在、当前离线 usage 漏验。推测而未证明：v2 的长期维护或性能优势。无 Issuer/L2、真实模型、完整 Core 迁移、main merge 或部署。
