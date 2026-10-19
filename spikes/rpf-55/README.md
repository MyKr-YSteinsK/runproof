# RPF-55｜受限配置 Experiment Adapter

**rev-1 / Status: Partial**。本分支新增严格三合同、静态三候选、Fixture-only Host Adapter 和独立离线 Verifier。实际完成正常场景与本地成功回复抑制场景；inhibited 场景在 SDK 启动前受阻，三个 JVM 配额已用完。没有签发 `config-experiment-evidence.json`。

[中文主结果](RESULT.md) 解释验收缺口；[失败摘要](experiment-summary.json) 保存本轮独立 Run、合同、HTTP、Tool、故障事件、只读读回、SDK/JVM 身份与清理观察。摘要不是成功 Witness，不能送入 Verifier 冒充完整三场景证书。

## 机制与来源

`ExperimentHost` 继承既有 `ConfigLiveHost`，固定使用真实 Pydantic AI SDK 的本地 Fixture，禁止外部 Provider。现有 Runtime 文件、Live v6 Verifier 和旧证书均未修改。`ExperimentHttp` 复用原有静态 HTTP 路径、业务验证和请求预算，使用新合同初始化受限客户端。

新 Experiment/FaultPlan 单独冻结，owner=`rpf-55`；为兼容旧三工具协议，合成业务名沿用 `rpf53` 前缀，附本轮唯一 `55…` 后缀。内部旧 Fixture Host 的兼容合同只用于 wire protocol，其历史 task-JAR 字段不作本轮运行来源；本轮唯一执行来源是新 Experiment 合同与实际 task-owned JAR。

故障名称：`LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200`。业务 update 的 HTTP200/code0/v2 已实际确认后，Adapter 抑制成功 Tool 回复，Handler 返回明确 HTTP400，SDK 转为 `RuntimeError` 中止。实际通道为 `EXPLICIT_TOOL_DELIVERY_ERROR`，不是 TCP 丢包。父进程在 SDK 停止后只发 current/history/list GET；没有重复 POST。

GET 与写端属于同一个 Java 服务信任域。Issuer 真实性、数据库独立认证、独立复现未建立；真实 Explorer、真实模型未运行，PGE/WorkSwarm 均未证明。

## 只读验证

```powershell
python -B -m unittest runtime.tests.test_effectwitness_config_experiment -v
python -B -m runtime.runproof_runtime.effectwitness.config_experiment_verify <complete-envelope.json> --sha256 <external-sha256>
```

Verifier 接受完整合成测试 Envelope 时明确返回 `SYNTHETIC_TEST_ONLY`；它不将测试提升为真实实验。退出码：正确外部 SHA 与合法完整证据为0，缺外部 SHA为2，错锚/非法证据为3。七类重新计算内部摘要与外部 SHA 的语义篡改仍拒绝。当前失败摘要没有完整成功 Envelope，不能取得这项真实证书验收。

## 受控运行入口与本轮停止状态

`probe.py preflight`、`fixture`、`run-controlled`、`verify-offline` 分别提供身份预检、SDK 诊断、受控实验和候选证书离线签发入口。它们需要本轮专用 marker、冻结 source、Tier0 与 Tier1 通过记录；不能删除 marker、复用 Run 或重置配额。

本轮实际执行命令：

```powershell
python -B spikes/rpf-55/probe.py preflight
python -B spikes/rpf-55/probe.py fixture
python -B spikes/rpf-55/probe.py run-controlled
```

在正常场景完成后的证据整理错误处停止后，通过本轮 ignored 调度脚本继续调用同一个 `scenario` 实现，使用原有三份预注册合同，没有创建新的 Scenario 配额。第二场景的冷进程解释器绑定缺失被保留为失败；恢复直接解释器身份后只执行剩余第三场景。详细偏离、source 差异与原始日志位置见主结果。

**本轮不得再次执行受控入口。** 已用3 JVM、18业务HTTP、4 POST、3 health GET，Provider/tokens/费用为0。后续完整三场景复验需要新 Plan、新配额与新工作区。

运行目录为 `.local/rpf-55/`，只读来源为原 Plan 固定的 Java source manifest/JAR 与 SDK 安装；直接 CPython、RECORD、JAR、PID/listener 与 loopback 均检查。SDK 环境不携带 Provider/业务密钥；Java 的本地合成 API key 只从新进程环境提供。健康详情中的私有磁盘路径只保留在 ignored raw capture；公开摘要含标注的 status-only 投影及原响应摘要。

交付后的冷进程检查已移至 JVM 启动之前，健康投影也已纳入 Runner。修复通过纯测试和完整隔离 Runtime 回归，未重新运行三场景，不能据此补足当前缺失证书。
