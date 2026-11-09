# RPF-102 rev-2 离线交付

本机和远端基线均为 `0138fedd5e90bae7a7d53f140b363e84341a310e`。封存时离线实现与验证已通过，远端交付和本次 hosted 结果为 `NOT_RUN_AT_SEAL`。

首次正式运行在 `5e58bf0023d8a4271a478b6f11573d120abebafb` 安装了固定 SDK，准入后 NORMAL 以 `SDK_EXECUTION_FAILED` 结束，UNKNOWN 未开始。Run 的 Artifact 数为 0，原异常和原物理用量无法重建，根因保持 `UNDETERMINED`。rev-1 最终提交只通过了离线 CI，未获正式复验。[正式 Run](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42580171633) · [rev-1 离线 Run](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42580627909)

本修订将 SDK 的导入、初始化、运行、工具回调和结果处理分别记录，并从持久回执核对父子退出、WAL 事件及 Receiver 的独立字节。新 owner 内的诊断只按当前源码与场景身份读取。公开 JSON 有严格字段、枚举、整数和 8192 字节上限，缺失事实用 `null`。失败退出与 Host 拒绝可同时保留。诊断摘要用于排查，完整物理验收仍由独立 Oracle 判断。

源码审查确认了两处可复现的本地问题。Host 曾在持久记录 `SEND_BEGIN` 前建连，且曾在入站事件落盘前递增计数。两处顺序已修正。请求校验现在明确拒绝布尔 `n`、不合法的消息或工具对象及非字符串工具回注。UNKNOWN 的 409 需要 WAL 中已有对应的 UNKNOWN 事件。固定上游源码支持两种 token 上限字段、字符串工具回注、409 到 `ModelHTTPError` 的转换及零重试配置。现场实际请求体、HTTP 头和旧异常仍无证据。测试输入为 `SYNTHETIC_CONTRACT_ONLY`。[PydanticAI 2.57.0 模型源码](https://github.com/pydantic/pydantic-ai/blob/v2.57.0/pydantic_ai_slim/pydantic_ai/models/openai.py) · [OpenAI 3.35.1 重试源码](https://github.com/openai/openai-python/blob/v3.35.1/src/openai/_base_client.py)

Windows 上 12 项测试通过，包括真实标准库子进程退出码、畸形及截断输出、凭据样本、未决计数、原件保护、独立 Receiver 身份、工具回注以及 UNKNOWN 后的预约和发送重锚负控。另通过 7 个 Python 文件的 AST 和编译检查、文档检查及工作流命令白名单检查。本轮正式运行、SDK 子进程、Receiver、物理发送、外部 Provider 和业务写入均为 0。

当前自动 workflow 仅有离线测试、文档检查和 `SDK_PHYSICAL_NOT_RUN_BY_PLAN` 通知。未来物理运行需明确批准固定提交和独立预算，并在失败后用 `always()` 只收集通过校验的脱敏 JSON。诊断缺失时记录证据不可用。rev-2 A07 为 `NOT_APPLICABLE`，rev-1 的 NORMAL 仍为 `FAIL`，UNKNOWN 仍为 `NOT_RUN`。证据接受和产品阶段推进由 Architect 独立决定。
