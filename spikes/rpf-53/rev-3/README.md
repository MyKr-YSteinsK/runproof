# RPF-53 rev-3｜真实 SDK 结果报告修复与 Provider 跨域补验收

本轮修复固定 Pydantic AI SDK 的 `RunResult.usage` 属性读取与严格字段报告，并补齐 rev-3 隔离 Fixture 诊断、不可覆盖 attempt marker 和 4/3/3 lineage 记录。

**执行结果：Partial。** 三次零付费 Fixture Attempt 均由 SDK 完成 4 次 Fixture completion、3 次 SDK-origin 工具调用和 3 个唯一 Tool Return；A-03 的完整报告门未通过，诊断额度已耗尽。因此没有启动 Java/config-center、业务 HTTP、DeepSeek Provider，也没有生成 Live Evidence。详见 [TASK_RESULT](RESULT.md)。

本目录中的 `sdk-fixture-diagnostic.json` 与 `live-summary.json` 是本轮 rev-3 新报告。不要重跑已消费的 `--diagnostic`；历史 rev-1/rev-2 marker 与证据保持冻结。
