# RPF-95/rev-2 管理器准入

Status: PARTIAL。固定 JiuwenSwarm `6c6434e8ed7ae5cc7df00d16d9f4e39dc26bfb71` 的 `probe_mcp_live_connection` 实际经 `Runner.resource_mgr` 注册只读 MCP，并通过已注册工具对象调用运维 Witness 与历史摘要。该运行采用**不完整的依赖子集**，不是完整安装或生产运行。

复验入口：`integrations/jiuwenswarm/manager_probe.py`。在新建 `.local/rpf-95-jiuwenswarm/<32-hex-owner>` 内准备任务专属 venv、固定上游及其固定 agent-core/gateway/protocol、配置和数据目录；工作目录必须是该 owner，设置 HOME、USERPROFILE、APPDATA、LOCALAPPDATA、XDG_CONFIG_HOME、XDG_CACHE_HOME、UV_CACHE_DIR、PIP_CACHE_DIR、TEMP、TMP、JIUWENSWARM_HOME、JIUWENSWARM_CONFIG_DIR、JIUWENSWARM_DATA_DIR 为 owner 下的绝对路径，将仓库放入 PYTHONPATH，运行 `python -B -m integrations.jiuwenswarm.manager_probe`。不要传递全量用户环境、密钥或模型配置。Probe 会在 owner 的数据目录 create-only 建立本地 MCP 配置，正常退出时注销自身的 Server；无业务写入授权。

固定来源、依赖缺口、安全例外和真实测试边界见 [RESULT](RESULT.md) 与两个诊断。此前 rev-1 的 `.env` 读取状态仍 UNVERIFIED。
