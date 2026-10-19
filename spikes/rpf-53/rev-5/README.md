# RPF-53 rev-5｜真实 Provider 参数合同与 task-owned JAR

**Status: PARTIAL**。本轮唯一真实 Provider + config-center Trial 完成了冻结的配置变更并通过业务 Oracle；独立 Live Evidence 自检在写证书前以 `KeyError` 失败，因此没有生成有效证书。

rev-5 修复了 Agent 可见任务/工具合同缺少合成参数字面值，以及 Java 需从本轮 task-owned JAR 副本启动的问题。真实 SDK Fixture、隔离 Runtime 回归、七个历史锚和文档检查均通过。真实运行得到 `v2/version 2/history [2,1]`，且 JAR 的实际 JVM `-jar` 路径核验通过。

## 记录

- [TASK_RESULT](RESULT.md)：逐项列出 A01–A08、冻结源身份、Fixture、唯一真实 Trial、预算、清理与未完成证据门槛。
- [Fixture 预检](sdk-fixture-preflight.json)：本轮真实 Pydantic AI SDK 的脱敏 Fixture 结果。
- [Live 摘要](live-summary.json)：唯一真实 Trial 的安全摘要。没有包含 Provider 原始文本、密钥或私有推理。
- `config-live-evidence.json`：未创建。Evidence 自检失败，不能把本轮业务效果描述为已签发或已离线验证的 Witness。

## 重要边界

真实 Trial 已消耗本 Plan 唯一授权。不要再次运行 `spikes/rpf-53/probe.py --run-scenario`，也不要复用或重置本轮 marker、账本、Run ID 或 H2 namespace。修复 Evidence 自检或 preflight 状态比较需要新的授权和重新验收。

发行者真实性、数据库独立认证和独立复现仍未建立；本轮没有执行 PGE 或 WorkSwarm。业务违规与 Agent 普遍失败均为 `NOT_PROVEN`。
