# JiuwenSwarm → RunProof MCP 候选接缝

Status: DESIGN_ONLY / INTEGRATION_NOT_RUN。上游默认分支 develop 固定提交 `6c6434e8ed7ae5cc7df00d16d9f4e39dc26bfb71`；本轮未安装、注册或调用 JiuwenSwarm、MCP server、Provider、业务写入。

## 已核查的上游合同

- [README 固定版本](https://github.com/openJiuwen-ai/jiuwenswarm/blob/6c6434e8ed7ae5cc7df00d16d9f4e39dc26bfb71/README.md) 将命令行包列为 `workswarm`；包和 CLI 随版本变化，非本轮安装授权。
- [SlashCommands 固定版本](https://github.com/openJiuwen-ai/jiuwenswarm/blob/6c6434e8ed7ae5cc7df00d16d9f4e39dc26bfb71/docs/en/SlashCommands.md) 的 `/mcp add --name ... --transport <stdio|sse>`：stdio 需要 `command`，可选 `args/cwd/env`；sse 需要 `url`，可选 `headers/timeout_s`。写入 `config.yaml` 的 `mcp.servers` 并触发重载；本轮未执行。
- [MCPConfiguration 固定版本](https://github.com/openJiuwen-ai/jiuwenswarm/blob/6c6434e8ed7ae5cc7df00d16d9f4e39dc26bfb71/docs/en/MCPConfiguration.md) 同时列出 `streamable-http`，通用服务器配置字段为 `name/enabled/transport`、stdio 的 `command/args/cwd/env` 和网络 transport 的 `url/headers/timeout_s`。这是配置文档，不等于这些传输已在本项目验证。stdio 是子进程与标准流；SSE 是服务端事件网络连接，权限、认证及网络隔离必须独立设计。

## 候选工具（均不是已有 MCP API）

| 候选工具与输入 | 输出与证据 ID（提案） | 已有支撑和缺口 |
| --- | --- | --- |
| `get_capabilities({domain,source})` | `{availability,reason,remaining_budget,source_identity}` | 现有 Lab `GET /effectwitness-api/capabilities`、Live `/explorations/capabilities`、Cross `/cross-domain/capabilities` 分别有不同 DTO；需 adapter 明确来源和权限，不把配额缺失当 0。 |
| `read_session({source,session_id})` | `{session_id,status,events,evidence_ids}` | 按各 Typed Client 的 `/sessions/:id`、`/explorations/:id`、`/cross-domain/sessions/:id` 路由；必须按来源验证 DTO，不能合并历史与 live。 |
| `verify_witness({source,session_id,witness_id})` | `{verification_status,content_sha256,issuer_authenticity}` | 现有下载客户端核对大小和哈希；独立离线 verifier 不是当前通用 HTTP endpoint。须后续明确安全服务和证据来源，哈希不证明 Issuer。 |
| `create_experiment({domain,profile,request_id,nonce,budget})` | `{accepted_session_id,status,receipt_id}` 或错误码 | 概念提案，非新增 API。必须另行授权并实测，服务端冻结参数/权限、nonce、幂等、并发、费用和预算；需 UNKNOWN 持久屏障和只读对账。 |

所有接口须服务端 enforcing scoped permissions、请求身份、速率与费用预算，禁止客户端或模型改写业务 Authority、Oracle、Witness、Issuer、Release authority。错误至少区分 `UNAVAILABLE`、`PERMISSION_DENIED`、`BUDGET_EXHAUSTED`、`UNKNOWN_RECONCILE_REQUIRED`、`INVALID_SOURCE`；命名为提案而非现有实现。

## 请求示意（未执行）

- 合法：`get_capabilities({"domain":"order","source":"LOCAL_CONTROLLED"})`；无权限时返回权限拒绝。
- 非法：要求 `create_experiment` 改写 Oracle 规则或强行标记 PASS，拒绝 `PERMISSION_DENIED`。
- 非法：同一领域在 `UNKNOWN_OUTCOME` 后重复写或重新预约 Provider，拒绝 `UNKNOWN_RECONCILE_REQUIRED`，只允许受合同约束的确定性只读对账。

真正端到端证据需固定上游和 adapter 身份、受限 owner/预算、真实 Agent 工具请求及响应 ID、工具到 RunProof 的链路、独立业务读回、Oracle 与反馈、可验 Witness、拒绝和零越权记录；需独立授权和运行。RPF-74 零新 Provider 预约缺口未获修复验收；第三方 Issuer 与 Release Gate 均未建立。
