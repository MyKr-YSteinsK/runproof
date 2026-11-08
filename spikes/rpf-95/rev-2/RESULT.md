# RPF-95/rev-2 TASK_RESULT

Status: **PARTIAL**。固定上游管理器及已注册 Tool Runtime 的有限只读调用取得真实 PASS；该环境仅安装导入所需依赖子集，`pip check` exit 1（缺失和冲突逐条见 integration-diagnostic），不能声称完整上游依赖图、生产环境或全部安全门禁通过。

基线 `77ec22ae878afe41b6b33fbee9cc4be7b6764862`；G0 本地/远端 main 一致、tracked clean、七个 create-only 路径未占用、owner ignored、父路径无已知 reparse。未修改 Web 或旧报告。上游 JiuwenSwarm `6c6434e8ed7ae5cc7df00d16d9f4e39dc26bfb71`，agent-core `f3f8f576164cc405c046e43079c8ad00ee17f0c4`；gateway `cff3b1b9c2dd02bf29e0cb331dec12be989bc656`，protocol `cbbadde9101db6e3d75e4ef2b9bdb6029fd92088`，Python 3.12.13，MCP SDK 1.30.0。

| Gate | 状态与实际边界 |
| --- | --- |
| G0 | PASS：新 task owner；原历史 owner 不读取、不复用。 |
| A01 | PASS：固定源码 `jiuwenswarm/common/mcp_config.py::probe_mcp_live_connection` 使用 `Runner.resource_mgr.add_mcp_server`；资源管理器经 ToolMgr 注册 MCPTool，后者 invoke 经过实际客户端。 |
| A02 | PARTIAL：CWD 和 HOME/USERPROFILE/APPDATA/LOCALAPPDATA/XDG/cache/TEMP 环境必须在 task owner，来源验证子进程只传限定字段；合成 .env 位置拒绝和缺失/越界 HOME 拒绝通过。未做全面系统调用审计。rev-1 早期 `.env` 读取仍 UNVERIFIED，不追认、不猜泄露。 |
| A03 | PASS（受限依赖子集）：真实 JiuwenSwarm probe 和 Runner 资源管理器注册三工具，通过 MCPTool.invoke 调用 `verify_witness` 和 `inspect_recorded_experiment`；固定来源、锚、反馈 hash 和 Issuer 限制已解析；退出 0 并注销。无模型。 |
| A04 | PARTIAL：stdio 原生测试通过路径、额外参数、写工具、重复 key、超大输入、错误锚、缺文件拒绝；全部 Source/Issuer 攻击组合与系统调用隔离未穷举。 |
| A05 | PASS（所列测试）：Python unittest 7/7、npm test 69/69、typecheck/build exit 0；`pip check` exit 1，依赖闭包 PARTIAL，缺失及冲突不计 PASS。 |
| A06 | PARTIAL：不主动调用 Provider、旧 Gateway、业务写入或旧 owner；无独立系统级网络/文件访问追踪，不能宣称其物理审计 PASS。 |
| A07 | NOT_RUN_AT_SEAL：focused commit/push、远端 blob 与可能触发的 CI 在最终聊天补充。 |

Manager 回执：运维 `rpf44-ops-sample`，锚 `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873`，`VERIFIED_ANCHORED`，Issuer `NOT_ESTABLISHED`；历史摘要 `rpf46-summary` 的反馈 hash `5cc9789a5034104ee1627e2afc9919dc77dce39d6026b20cb690ec9873714912`。实际工具资源 ID 与 schema 见 integration-diagnostic；请求 ID 未暴露。历史样本不是同一双域实时会话；摘要不是完整 Live Witness。RPF-74 的 UNKNOWN 后零新 Provider RESERVE 不变量仍未修复验收；无 release/deploy 或赛事操作。

安装与排障：上游源码获取首次直接连接失败，配置级代理重试成功；一次 checkout 的日志解码失败但实际固定 HEAD 已核对。Manager 导入依次缺少 pymilvus、pysbd、tiktoken、dashscope、bs4、Crypto、sqlalchemy、greenlet、alembic；在新 owner 安装上游声明的有界子集后成功。依赖存在 protobuf 和 OpenTelemetry 版本冲突，详见诊断；不触发真实模型或其他服务。
