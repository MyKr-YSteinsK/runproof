# RPF-95 只读 MCP 与工作台

Status: PARTIAL。固定 JiuwenSwarm `6c6434e8ed7ae5cc7df00d16d9f4e39dc26bfb71` 的配置构造器与其固定 agent-core 的 StdioClient 完成实际工具发现和一次调用；完整 JiuwenSwarm 管理器注册未运行。Provider、Gateway、业务写入均未授权及未运行。

在任务 owner（`.local/rpf-95-jiuwenswarm/<owner>`）中，以任务 venv Python 和 `PYTHONPATH` 指向本仓库，运行 `python -B -m integrations.jiuwenswarm.mcp_readonly`；只通过 stdio MCP 客户端通信。Server 要求工作目录恰为新任务 owner，避免 SDK 自动读取仓库根 `.env`。工具仅 `get_capabilities`、`inspect_recorded_experiment`、`verify_witness`；输入仅固定 source ID，不接受任意文件路径或写工具。

工作台路径 `/effectwitness/workbench?domain=order`；事件可进入 Recorded 后返回相同事件，运维样本为独立证据。浏览器不连接 stdio 服务或伪报服务在线。

只读来源是历史摘要与两份不同会话的样本；`VERIFIED_ANCHORED` 不是第三方签名，Issuer 身份未建立；RPF-46 摘要不是完整 Live Witness。
