# RPF-56 rev-4：Explorer 工具协议与双真实 Agent PGE

本轮完成一个独立协议 Probe 和一个全新的真实双角色、两轮 Java/H2 Session，已签发并独立验证新 Witness。两轮均由模型合法选择 `normal`，反馈真实回注，`L1=TWO_REAL_ROLES_EXECUTED`、`L2=false`、`H1=NOT_PROVEN`。最终任务交付状态以 `RESULT.md` 为准。

## 证据入口

- `protocol-diagnostic.json`：`PROTOCOL_PROBE_ONLY`，1 次真实请求、结构形态、费用与来源；无工具派发，不是正式 Round1。
- `session-summary.json`：唯一新 Session、两轮模型选择、反馈摘要、实际 Session 总账及研究边界。
- `verification-diagnostic.json`：全任务 Probe/Explorer/Target 总账、执行/交付源码、SDK/Fixture、两个 JVM、CLI/篡改与回归。
- `config-pge-evidence.json`：本轮真实原始字节 Envelope，SHA256=`4d565511cc1093d350700b4b360b276b519d6b5effa6be0e1cdfadfe2b32d26b`。

独立离线验证，不启动模型、SDK 或 Java：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.config_pge_verify spikes/rpf-56/rev-4/config-pge-evidence.json --sha256 4d565511cc1093d350700b4b360b276b519d6b5effa6be0e1cdfadfe2b32d26b
```

正确/缺失/错误外部 SHA 对应 `0/2/3`；本轮真实 Envelope 的 11 类 rehashed 语义负控均返回 3。`SYNTHETIC_TEST_ONLY`、`PROTOCOL_PROBE_ONLY` 与真实 Session 分级，旧 v1–v3 不能充当 v4 证书。

## 实际接口和顺序

普通离线测试：

```powershell
python -B -m unittest runtime.tests.test_effectwitness_config_pge -v
```

本轮实际执行顺序：固定 SDK 只读身份检查 → `probe.py preflight` → `offline` → 三次 `fixture --candidate <candidate>` → `protocol-probe` → `live` → 自动 `issue`。`protocol-probe` 不调用工具执行器、Target 或 Java；正式 `live` 必须读取同源 Probe PASS、三个新冷进程结果和当天价格 Gate。源码固定 `rev-4` Base/branch/root，不允许任意 executable/endpoint/任务根参数。

这些受控额度已使用，不可重跑 Probe、Fixture 或 Session；独占 marker/账本/结果不能删除重置。提交后 Runner 也不会将新的 HEAD 默认为旧运行起点。所有短期材料、SDK scratch、JAR、快照和日志留在 ignored `.local/rpf-56-rev4/`，旧运行目录未复用。

## 协议与持久化

Explorer 使用非 thinking 的具名 `select_experiment`、单一工具注册、`max_tokens=128`；保留 `parallel_tool_calls=False`，仍由 parser 严格拒绝多工具。为使 Probe 请求字节上界加最大输出在 1,024 的预留内，压缩了提示中的文字和重复 JSON；三候选设计、业务不变量、重复选择与反馈边界保留。

任何响应先保存白名单 `safe_response_shape`，再验 usage、再 parse。结构覆盖缺失/null/错误类型、finish_reason、role、calls 数量、允许函数名、ID/model/usage，以及 content/reasoning/arguments 的类型、长度与 hash；不保存正文、推理或任意参数。指纹 SHA 是对应值的 canonical JSON bytes 的 SHA256，缺失值显式记录为 MISSING。

TaskBudget 覆盖 Probe 和正式两角色，SessionLedger 再施加 12 请求/28,000 tokens/¥0.95 子限。编号快照、摘要链、fsync 和独占锁保留请求前预约，未知 usage 保留上界并停止；已知 usage 结算实际消费，未删除预约历史。Probe 选择验证后丢弃，未带入正式消息。

## 结果与限制

总计 **11 请求、8,046 tokens、费用保守估算 ¥0.0448605**：Probe 1/422，正式 Explorer 2/1,063，Target 8/6,561。两个新 Java/H2 各 8 HTTP、2 POST、1 health，最终 v2/history `[2,1]`，资源清理通过。三个 SDK Fixture 独立验证 normal/inhibited/suppressed 的 Tool 回注；真实 Session 的两个 normal 均无故障计划、触发或观测，没有新增真实 suppression 案例。

当日核对 [Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion/)、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[价格](https://api-docs.deepseek.com/quick_start/pricing/)：具名工具用于 non-thinking；峰值输入 USD0.30/输出1.20 每百万 tokens，以 ×15 guard 得 CNY4.5/18。估算不是账单/汇率。当前协议实测成功，仍不能确定 rev-3 未保留的响应结构或单独归因于 `required`。

一次有限会话不证明统计优势、强因果、安全性、发行者真实性、数据库独立 Authority、独立复现或 WorkSwarm。是否接受证据、推进阶段或追加实验，由 Architect 后续决定。
