# RPF-40 — 竞赛升级审计与自主实验接入验证

## 范围

这是一个受限调查与 disposable Spike，不是 RunProof 产品功能。它验证了一次 DeepSeek Tool Calling 往返：Provider 选择一个只读工具，适配器验证参数，在 .local/rpf-40/ 中读取由本任务创建的固定沙箱状态，再把工具结果按 tool_call_id 回传给模型。它不验证订单、退款、运维业务效果、Effect Verifier 或 Witness。

probe.py 仅依赖 Python 标准库。它不启动 WorkSwarm、Control Plane、Worker、Docker 或 Web，不调用 RunProof 业务工具，也不连接其他 MCP Server。--live 直连 api.deepseek.com，禁用环境代理，不自动重试；单次最多发出 2 个 Provider 请求，每请求最多生成 192 tokens，90 秒超时，总窗口不超过 20 分钟。它只公开一个函数工具和一个固定 scenario_id，拒绝任意文件路径、命令或网络参数。

## 复现

从仓库根目录运行确定性校验，不需要 API Key：

    python -X utf8 spikes/rpf-40/probe.py --self-check

在单独获得 Provider 调用预算、并确认 DEEPSEEK_API_KEY 已存在于进程环境后，才运行一次 live 模式：

    python -X utf8 spikes/rpf-40/probe.py --live

脚本不会读取、打印或持久化 Key；它会在 .local/rpf-40/sandbox-state.json 和 .local/rpf-40/live-result.json 采用 write-once 写入。若目标文件已存在，脚本会停止而不覆盖。live 结果记录脱敏的请求身份、Provider response ID、tool-call ID、usage、受控状态哈希和失败分类，不记录 Prompt、模型自由文本、隐藏推理或 Authorization。

本次运行使用 Python 3.12.13。WorkSwarm 不是该 probe 的运行依赖。包检查用一个位于 .local/rpf-40/ 的隔离 venv 安装了 workswarm==0.2.7 wheel 的 --no-deps 版本，只检查元数据和源码；该 venv、wheel 与临时目录因本地执行环境拒绝递归删除而保留在 .local/rpf-40/quarantine/，未启动应用或初始化 ~/.jiuwenswarm/。

## SDK 与 Provider 来源

截至 2026-10-17：

- JiuwenSwarm 官方安装文档将 PyPI 包名改为 workswarm，要求 Python >=3.11,<3.14，并将其描述为含 CLI/桌面应用的运行包。稳定 PyPI 版本为 0.2.7，Apache-2.0；本地 wheel SHA-256 为 723e8373d2288d60cad09f1aaf813f65bb2b245769c17808e0090b81ae3fb13e。官方 GitHub 已发布 0.2.8.beta1，但本次不追 Beta。包元数据声明 106 个依赖；静态源码中可见应用内部 MCP 配置与 Agent harness，但没有在官方资料中确认可供 RunProof 嵌入的稳定 SDK 调用合同，因此 WorkSwarm 集成为 NOT_PROVEN。
- DeepSeek 官方文档确认 deepseek-flash 支持 Tool Calls，并给出了返回 tool_calls、由应用执行工具、按相同 tool_call_id 追加 role=tool 消息、再请求模型的流程。probe.py 用标准库直接实现这个窄 HTTP 流程；这不是 JiuwenSwarm/MCP 集成。
- 官方价格页所列峰值单价为输入未命中缓存 $0.30 / 1M tokens、输出 $1.20 / 1M tokens。脚本按输入均为 cache-miss、输出均按峰值，并用 ¥10 / USD 作保守上界核算。

官方来源：

- [WorkSwarm 安装指南](https://github.com/openJiuwen-ai/jiuwenswarm/blob/develop/docs/en/InstallGuide.md)
- [WorkSwarm PyPI](https://pypi.org/project/workswarm/)
- [WorkSwarm 官方发行页](https://github.com/openJiuwen-ai/jiuwenswarm/releases)
- [DeepSeek Tool Calls 指南](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)

## 输出与证据边界

- 确定性自检：DETERMINISTIC_LOCAL_CONTROL，0 Provider 请求。
- Live 证据：仅适用于固定本地 JSON 沙箱的 Agent → Tool → 状态 readback → Tool Result → Agent 链路。
- .local/rpf-40/ 是本任务唯一运行输出目录，已被仓库 .gitignore 忽略。它不是 Reviewed Artifact，也不建立 canonical Run、Effect、Experiment、Witness、Release 或部署状态。
- 公开结果摘要、复现命令、来源身份和验收矩阵见 RESULT.md。
