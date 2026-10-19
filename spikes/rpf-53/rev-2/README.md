# RPF-53 rev-2：可信 SDK 只读边界与跨域闭环补验收

**Plan:** RPF-53 rev-2
**Status:** Partial

本轮完成了受限 SDK 只读边界修复、两次受限 Fixture 诊断及离线回归。两次 SDK 诊断额度已用完，A-03 未通过；本轮没有执行真实 Provider、Java/H2 或业务 HTTP Scenario，也没有创建 Live Evidence。

## 结果文件

- [RESULT.md](RESULT.md)：唯一 TASK_RESULT，列出 A-01～A-08 的实际状态与限制。
- [sdk-read-guard-diagnostic.json](sdk-read-guard-diagnostic.json)：两次 SDK 诊断的安全摘要、映射身份与清理状态。
- [live-summary.json](live-summary.json)：去敏的运行与来源身份摘要。
- `config-live-evidence.json` 未创建；没有真实 Live Scenario 可供签发。

## 关键结果

- SDK 读取只绑定经 RECORD/SHA 核验的 site-packages 根，以及哈希绑定的精确 Python runtime 映射。首次拒读项经固定解释器路径复核为 `python312.zip`；映射只加该精确归档项，不加其父目录。
- 首次诊断未执行 SDK 工具调用。第二次诊断完成 3 次 SDK 工具调用与 3 次返回回注；随后 SDK 报告阶段以 `TypeError` 退出。`result.usage()` 已修正为属性读取 `result.usage`，但因两次额度已耗尽，该修复没有再次通过 SDK 端到端诊断。
- 23 项 RPF-53 定向测试通过。隔离全 Runtime 套件首次运行 277 项，其中 2 项 loopback 用例出现 Windows `10053` 错误、Docker 2 项因环境不可用而跳过；两项 loopback 用例随后分别单测复跑通过。全量套件不记为 PASS。
- Reviewed Artifacts、Public Docs 和 RPF-43/44/48/49/50/51-rev4/52-rev3 七个历史锚验证均通过。

详细执行事实、哈希、验收门状态与交付边界见 [RESULT.md](RESULT.md)。
