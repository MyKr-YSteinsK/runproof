# RPF-95/rev-1 TASK_RESULT

Status: **PARTIAL**。基线 `0b775937f55427a2f5d56fbf24abae03fcb48d8f`。基本只读 stdio 与上游配置构造器 + 固定 agent-core 客户端的真实调用已验证；未执行 JiuwenSwarm 完整管理器注册/Agent 调用，不能宣称完整 A03 或端到端 Agent 集成。

| Gate | 实际结果 |
| --- | --- |
| G0 | PASS：main/remote 对齐、tracked clean，14 个 create-only 目标空闲，owner ignored，无已知 reparse；web push 触发 canonical CI。 |
| A01 | PARTIAL：既有 RPF-47 来源 verifier 和 Witness verifier 实际运行；两份固定锚 VERIFIED_ANCHORED，错误锚/缺文件拒绝。全部篡改组合未完成。 |
| A02 | PASS（有界）：真实 MCP SDK stdio initialize/list/call；摘要和运维样本实际返回，工具仅三项。首轮调用超时；用隔离子进程与 DEVNULL stdin 修复，失败保留。 |
| A03 | PARTIAL：固定上游 JiuwenSwarm `mcp_config.build_mcp_server_config` 生成配置，固定 agent-core `StdioClient` 真正发现三工具并调用运维 Witness，退出 0。未通过 JiuwenSwarm 完整 manager 注册；不是模型决策。 |
| A04 | PARTIAL：错误路径、额外 path、未知写工具、重复 JSON key、超大消息、错误锚和缺文件拒绝；剩余组合未穷举。 |
| A05 | PARTIAL：事件往返恢复 domain/event，非法事件提示；工作台只读，无 POST。未覆盖全部模式与状态组合。 |
| A06 | PARTIAL：Windows Edge 157 headless 1440/1120/768 截图检查，焦点和 Enter 导航、无水平溢出；完整 Tab 序列和真机 NOT_RUN。 |
| A07 | PARTIAL：Python 5 tests PASS；npm test 69 PASS；build/typecheck PASS；上游依赖不完整且完整 manager NOT_RUN。 |
| A08 | NOT_RUN_AT_SEAL；最终 Git/CI 收据见聊天。 |
| A09 | PARTIAL：Issuer NOT_ESTABLISHED；RPF-46 为摘要、样本非同会话；无 Provider/业务写，旧 Gateway 未启动。安全检查例外如下。 |

安全例外：早期 stdio 测试在仓库根启动 FastMCP；随后审查 SDK 发现其默认尝试从当前目录加载 `.env`。未检查该文件是否存在或内容，因而是否发生读取为 UNVERIFIED，不能证明零密钥访问。已停止该测试路径，后续 Server 强制新任务 owner 工作目录并使用显式环境；不能追认早期测试为安全 PASS。静态 Vite 使用 strictPort 成功取得 4177，但启动前未另行记录端口占用查询。

上游 `workswarm 0.2.8`、`openjiuwen 0.1.20`、`agent-gateway 0.0.1`、`openjiuwen-protocol 0.1.0` 均为固定 Git checkout 的 editable、`--no-deps` 安装，依赖并不完整；`mcp 1.30.0` 来自包源。首次上游 checkout 的 LFS 媒体 404，独立新 checkout 跳过媒体；普通 wheel 在 Windows 长路径失败后 editable 成功。未改系统 Python 或用户 Jiuwen 配置。RPF-74 UNKNOWN 物理安全缺口未修复，当前未达 Release 或阶段晋级。
