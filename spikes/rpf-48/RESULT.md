# TASK_RESULT｜RPF-48 / rev-1

**Status: COMPLETE**

**核心结果：`EXTERNAL_AGENT_EFFECT_VERIFIED`，实际外部框架为 Pydantic AI 2.57.0。WorkSwarm 接入仍为 `NOT_PROVEN`。**

## 1. 身份、保护与交付范围

- ROOT：`D:\CS\runproof`；Base：`ec325ee9dd80e6663beb74d32d129a34fb4df40f`（RPF-47 reviewed parent）；分支：`codex/rpf-48-target-agent-integration`。
- `origin`：`https://github.com/MyKr-YSteinsK/runproof.git`；预检本地和远端目标分支不存在。`main` 在预检为 `bda0cd49e50e3181f604324e94877a24b9885334`；最终 push 后 refs 的实际对照在聊天回执给出。
- 初始工作树只有既存 `?? docs/reviews/`；该目录仅从 status 行可知其存在，本轮未进入、枚举、读取、修改、移动、暂存或提交。最终仍保留该未跟踪项。
- 没有创建新 worktree、clone 或其他 repository。回归源码副本只含本任务授权读取的 Runtime 源文件/测试及两份历史样本，没有 `.git`，所有副本和测试输出在 `.local/rpf-48` 下。
- RPF-40～47 本机账本/cache-hold、旧证书、旧 RESULT、`docs/project/**`、`docs/history/**`、Web、Java、workflows 和相邻仓库未改动；没有读取旧付费账本内容。RPF-47 rev-1 的 `PARTIAL` 保持，rev-2 补验收没有执行。
- 源码提交：`b65b4d90e5a7204076924d8a2d2858994a1335b4`（首版驱动）；`bf04f1a5bb311631e1845ccc2d085b093e734f40`（已知 DeepSeek envelope 兼容修正，成功 Trial 的代码版本）。最后的文档/去敏证据与此结果采用 focused commit、普通 push；本文件不写自身最终 SHA，最终回执补独立 `ls-remote` 对照。

## 2. SDK 调查与委托决定

[WorkSwarm 0.2.7 官方发布](https://github.com/openJiuwen-ai/jiuwenswarm/releases/tag/v0.2.7)和 [PyPI](https://pypi.org/project/workswarm/0.2.7/) 于 2026-10-18 核对：Apache-2.0，Python `>=3.11,<3.14`，wheel 32,123,505 bytes / SHA `723e8373d2288d60cad09f1aaf813f65bb2b245769c17808e0090b81ae3fb13e`。下载字节与官方摘要一致，仅静态检查；没有安装/启动 WorkSwarm、初始化 `~/.jiuwenswarm`、登录、连接 IM 或调用其后台服务。

官方 CLI/service、Home 配置和默认工具/后台组件耦合，本轮未证明一条具备窄工具暴露与逐次计费限制的 WorkSwarm 路径。这是受限接入尚未完成的证据，不宣称该框架普遍无法受控。按 Plan 的一个替代 Runtime 授权，选择 [Pydantic AI](https://pydantic.dev/docs/ai/core-concepts/agent/)：`pydantic-ai-slim==2.57.0`（MIT）、`openai==3.35.1`，在已有 Python 3.12.13 的 task-owned venv 安装 26 个 wheel 依赖，未改系统 Python/全局配置/根依赖。

Pydantic wheel SHA `a07d732e09df8d51f22bd3be2ad45ab644721a904809a2481146bf5d7bb47c67`；安装的 Agent core 与该 wheel 逐字节匹配，SHA `70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa`。握手固定该 core、框架/客户端版本和 Agent config hash。SDK 使用 [自定义客户端](https://pydantic.dev/docs/ai/models/openai/)连接本机代理，`max_retries=0`；Agent validation retries 也为 0。

实际协议为受限 `rpf-target-loopback-json-v1`，不是 MCP。零付费探针验证了真实 SDK 注册、请求、工具调用和结果回注；其来源为 `FIXTURE_TEST_ONLY`，不能据此宣称 Live。随后成功的付费 Trial 才满足外部 Agent Effect Gate。没有把自定义脚本循环或 MCP client smoke 当作第三方 Agent。

## 3. 实现和权限边界

新建 `target_contracts.py`、`target_driver.py`、`target_external.py`、`target_evidence.py`，以及 `test_effectwitness_target_agent.py`、本目录 README/probe/去敏摘要/RESULT。旧文件只在 `contracts.py` 与 `orders.py` 增加 `rpf-48` 存储根路由，并在 `runtime/README.md` 增加受限入口说明。没有改变旧 frozen schema、CrossContracts、Oracle 或 Witness verifier。

- 新合同：`rpf-target-execution-v1` / `rpf-target-experiment-v1`，明确 `role=TARGET`、Agent/framework/config/tools/budget/run/environment/fault/authority；静态 registry 分开 `pydantic-ai` 与 `deterministic-reference`，不支持动态 import。
- SDK 自己运行工具决策循环；Host 只将 Provider 实际返回的 call ID/name/合法参数摘要登记为 intent。SDK 的 `RunContext.tool_call_id` 必须绑定同一 intent；回注在下一次请求中按 call ID 和 result hash 检查。
- Child 不继承 Provider key，写入只在其任务目录；网络只可访问本轮 `127.0.0.1` 随机端口。Parent 持有固定 DeepSeek HTTPS transport 和预算；工具只有 inspect/refund/reconcile，未暴露 shell、任意 URL、数据库端口、Docker socket 或生产系统。
- 独立只读 Authority 与确定性订单 Oracle 复用已有代码。先观察、一次 mutation、UNKNOWN 时仅允许 reconcile；Agent 不修改业务合同或核验结果。Windows 路径别名及事件循环内部 socketpair 有定向处理；Python audit guard 不是 OS 安全沙箱。
- 新证据 `rpf-target-evidence-v1` 仅支持有界内容检查，保留 `issuer_authenticity=NOT_ESTABLISHED`、相关性和未测试复现的边界。Windows launcher/SDK PID 分开记录，来源绑定是私有 stdin capability + loopback token，不是 OS 远程证明。

## 4. 两条真实 Trial 与计量

| Trial | 时间 UTC / 代码 | Provider / 结果 | 业务与清理 |
| --- | --- | --- | --- |
| `target-b2101e0313b047088eed9a22a8dadc6a` | 06:23:29.475～06:23:36.423；`b65b4d9` | 1 次请求，648 input + 66 output = 714 tokens；¥0.001824 上界；`TARGET_CALL_FIELDS` / `AGENT_RUNTIME_CONNECTED` | 封装被拒绝，未 dispatch 业务工具、无退款/收据；独立读回后 reset/remove，generation 1 |
| `target-8c9731c09351407688142b416e7d9c05` | 06:25:29.448～06:25:39.142；`bf04f1a` | 3 次请求，2,396 input + 357 output = 2,753 tokens；¥0.007648 上界；SDK exit 0 | 自主 inspect → refund → 结果回注；全额 CNY 25.00，唯一 receipt；`CONTRACT_SATISFIED_IN_RUN`；reset/readback/remove，generation 1 |

第一条失败保持原样留存在 `.local/rpf-48/evidence/target-b2101e0313b047088eed9a22a8dadc6a.json`，SHA `eb3b0fda034e74c0ea4ca8b82c5acc6429465ca98284da942f16e6f9085a665f`；控制器结果/时间也分别保留。它是动作前的平台协议拒绝，不能包装成业务漏洞。未保存第一条原始响应或字段集合，因而不能事后断言其全部多余字段。

[DeepSeek 官方非流式示例](https://api-docs.deepseek.com/guides/thinking_mode/)含 `index=0`；免费探针重现旧拒绝后，仅兼容这一已知字段，非法 index/未知字段/业务参数仍 fail closed。第二条实际响应也记录 `function,id,index,type`。第二条是修正适配后的新鲜订单，未修改 Agent 提示、工具权限或第一条结果；没有重放同一订单/请求，也没有自动重试。

成功 Trial 的真实调用：

| 工具 / Call ID | 参数 SHA-256 | Tool result / 回注 |
| --- | --- | --- |
| `inspect_order` / `call_00_rRsdK70rfkRHay2imRTP7566` | `062cac039748d7800d5dcc035bba7368e9572f1d77d35be2b06dba1abfa7d834` | PAID/revision 0；返回 hash `f87afb3bc2230d9a300924a2d2a189876700b58ec32a2dd0ba67a934e89ee2a0`，回注 task attempt 3 |
| `refund_order` / `call_00_LJmLdMmZZkp1AzutvUPJ1681` | `dff08fe6e9b743a2482454b1d0edf008f434bfc5569cb96a3640135556e4d2de` | `COMMITTED`；receipt `receipt-b6d57883aa64a031af326e6d`；返回 hash `985a39b9594b7817205363ae4f63338ca0240fce238b3a6b0f0dcd80ac187c97`，回注 task attempt 4 |

SDK `pydantic-ai-slim 2.57.0` / Agent `rpf48-refund-target@1`，SDK PID 11404、launcher PID 17340；model requested/returned 为 `deepseek-flash`，实际模型别名映射以 Provider 为准。固定配置 hash `1fcbaabf7e6e96d3acc58c1c6ea7f296162f83a3b39254d6b5194ffcfcbed3a7`。正常 Trial 的 fault planned/triggered/observed/reconciled 均 false，没有宣称 Live 故障/复现/因果优势。

任务累计 **4 HTTP attempts、3,467 tokens（3,044 input / 423 output）、估算上界 ¥0.009472、2 Trial、automatic retries 0**；usage 全部已知，两个 Trial 都 `CLOSED`，无未决业务状态。整体真实执行跨度约 130 秒，每条均不足 10 秒；未开展第三条。官方 [2026-10-18 核对的人民币高峰价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)为缓存未命中输入 2 元/百万 tokens、输出 8 元/百万 tokens，直接使用 CNY，无汇率假设；该数值不是实际发票。

## 5. A-01～A-10

| Gate | 状态 | 证据 / 限制 |
| --- | --- | --- |
| A-01 身份/保护 | PASS | Base/local/remote/main/branch、根合同和 workflow 已核实。功能分支 push 无自动部署；只见并保留 `?? docs/reviews/`，没有旧账本/相邻项目操作。 |
| A-02 Driver 合同 | PASS | 新 target execution/experiment 与 explicit Port；缺失字段、角色/身份/预算/环境错误拒绝。旧模型 owner/Schema 校验未放宽，仅增加新 task 的存储根。 |
| A-03 SDK/协议 | PASS（替代 SDK） | WorkSwarm 0.2.7 官方 wheel 静态证据与许可证已核对，Live `NOT_PROVEN`；Pydantic AI 安装/core、真实 SDK 往返和受限 Host 协议实际通过，未称 MCP 已接入。 |
| A-04 真实 Target Tool Loop | PASS | 第二条真实 Provider → SDK 原生 Tool Loop → inspect/refund → 同 call ID/result hash 回注 → 最终请求。源码无 harness 固定代调业务顺序；SDK 与 Provider 计数一致。 |
| A-05 Authority Effect | PASS | 独立只读 SQLite before/after，PAID → REFUNDED，精确 CNY 2500 minor 和唯一 frozen-operation receipt，Oracle 合同满足；首条拒绝没有伪造效果。 |
| A-06 安全/负控 | PASS | 16 项新测试覆盖非法/重复 JSON、工具/参数、index、call ID、未知重放、缺 Authority/key、timeout/steps、预算/并发/crash hold、未鉴权真实 HTTP、损坏包/伪 Live。Mock/fixture 与实际 Live 分开。 |
| A-07 Evidence/Source | PASS | 10,257 bytes 的新去敏封装 SHA `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2`；独立进程禁 SDK/DB/网络导入，正确/无/错锚 native exits 0/2/3。7 个执行文件的实际 bytes hash 与记录一致，Git LF 规范化后与 `bf04f1a` 对应文件一致。来源仍是本机 Host 观察，不提供 issuer 认证。 |
| A-08 Budget | PASS | 4≤6 请求、3467≤15000 tokens、¥0.009472≤¥2、2≤2 Trial；每请求预留+fsync 在 paid socket 前，usage unknown 冻结、无自动重试，单任务锁禁止第二控制器。旧 RPF-46 未读取/修改。 |
| A-09 回归/清理 | PASS | 最终源码镜像全量 Runtime 181 tests：179 PASS / 2 Docker SKIP；原 RPF-43/44 anchored verifier exit 0、原摘要不变。实际 Sandbox 全部 reset/readback/remove，子进程/临时 Host 停止，paid-run.lock 已释放。uv cache 按授权可逆隔离，详见下文。 |
| A-10 Git 交付 | PASS（最终回执） | 仅 Plan 白名单；focused commits → 普通 push 到指定分支 → 独立 refs 对照。最终文档 commit 的 SHA、远端 ref 与最终工作树在本文件冻结后的聊天回执中列出，避免自指；无 PR/Merge/tag/Release/Deploy。 |

## 6. 验证命令与留存

- 最终完整 Runtime：在 171 个逐字节校验的 task-owned 源文件副本中执行 `python -B -m unittest discover -s runtime/tests -p 'test_*.py' -v`，native exit 0，181 tests / 2 skipped；日志 `.local/rpf-48/runtime-tests.log`。被跳过的是 `test_docker_integration`、`test_rpf05_runtime` 的 Docker provider unavailable 组。旧测试的 `.local/rpf-46` 临时路径只发生在源码副本内，没有接管真实旧任务。
- 原始根目录定向 target tests 16 PASS；最新实际 SDK transport-only exit 0、Provider requests/tokens/fee 0（合成 usage 明确标为 fixture）。新源码后重新跑了对应定向测试与完整回归。
- 新 summary 的独立 verifier：`python -B -m runtime.runproof_runtime.effectwitness.target_evidence spikes/rpf-48/target-agent-summary.json --expected-sha256 c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2`。另外在有 import blocker 的独立 Python 进程复核，拒绝 sqlite3/socket/http/SDK/Provider/Tool Host 导入；exit 0，issuer 仍 `NOT_ESTABLISHED`。
- RPF-43 / RPF-44 原 verifier 使用各自固定锚 `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e` / `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873`，均 exit 0 / `VERIFIED_ANCHORED`。
- `python -B runtime/verify-reviewed-artifacts.py` exit 0，历史/当前 Run、Evaluation、Gate、Decision 与 RPF-28 reviewed artifacts 全部 PASS；`python -B ci/verify-public-docs.py` exit 0（18 files / 7 pairs）。`git diff --check` 与 summary 私密协议/秘密扫描通过。
- 保留 `.local/rpf-48/paid-ledger.json`、两条真实 Trial 的去敏 wrapper/控制器结果/时间、零费失败与成功探针、SDK venv/下载 wheel/静态源码及版本元数据、回归副本/manifest/log。没有保存原始 Provider 消息、隐藏推理或自由输出文本；失败诊断只保留受限元数据，秘密扫描通过。
- `Remove-Item -Recurse -Force` 删除 `.local/rpf-48/uv-cache` 被执行策略以 `blocked by policy` 拒绝，命令未执行。按 Plan 授权，在核对 source/destination 绝对路径、所有实际 Trial 已关闭后，用同一 PowerShell 将该目录可逆移动到 `D:\CS\runproof\.local\quarantine\rpf-48\cache-hold\uv-cache`；移动前后均为 **3,321 files / 55,273,030 logical bytes**。这是隔离留存，没有声称已物理删除或释放磁盘空间，未换语言绕过删除策略。

## 7. 下一步范围

可将此 Port/来源模型送 Main 审查，然后用新授权与新预算验证真实 Target 在 `response-lost` 下自主 reconcile，或规划 config-center 的独立 HTTP 沙箱。当前不声称 WorkSwarm、ops 付费 Target、多框架普适性、真实生产、Docker 新集成、因果归因或自动复现已经成立；本轮 Trial 上限已用完。

建议进行 Development Architect Checkpoint Review：新增 Target/Explorer 分离与独立 wrapper 已有第一条真实框架证据，适合先审查首条协议失败、替代 SDK 来源和信任边界，再确定下一类受测 Agent。`EVIDENCE_ACCEPTED`、`STAGE_ADVANCED` 和主线合并仍由 Main 决定。
