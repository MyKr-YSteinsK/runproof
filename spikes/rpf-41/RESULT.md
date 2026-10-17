# TASK_RESULT｜RPF-41 / rev-1

**Status: COMPLETE**（本 Plan 交付候选；工程/live 验收及必要 Git 交付已完成）。2026-10-17 完成 Runtime 订单退款竖切片及本轮一次真实业务 live。Main 的 Evidence 接受、阶段推进、main 合并均未由执行器宣布。最终报告提交的 SHA 在同次聊天回执补录，不循环改写报告以填写自身 SHA。

## 身份、范围与技术决定

实际 repo `D:\CS\runproof`；origin `https://github.com/MyKr-YSteinsK/runproof.git`；任务分支 `codex/rpf-41-effect-contract-order-pilot` 从核实的 `origin/codex/rpf-40-effectwitness-spike@1556ab535d48661faa2c596c5bfea136c2404c68` 创建。远端 main 基线 `bda0cd49e50e3181f604324e94877a24b9885334`。启动时 tracked/staged clean，唯一预存用户状态为 `?? docs/reviews/`；未进入该目录。新路径和目标远端分支启动时均未占用。Feature branch push 不触发当前仅 main push/PR 的 Release Gate，其余历史 workflows 为 manual。

选择标准库 SQLite：相较文件 JSON，事务、operation 主键、order 唯一约束可以原子绑定订单与收据；相较独立 HTTP/Docker/PostgreSQL，Windows 上不需要新服务、依赖或凭据。代价是同进程模拟：Reader 用独立只读连接、真实持久状态和内部快照签发接口分离职责，不声称进程级安全隔离。Runner/Worker/Control Plane/CI/Web 与历史 Reviewed 全部保持原样。

共享 Core 为冻结合同入口、Budget、Orchestrator、DomainPort、AuthorityPort；订单事务、reset、订单规则 Verifier 留在领域模块。RPF-28 以后需要实现对应 Port 与运维 oracle，并扩展适用合同验证；本次仅给出接入映射，没有实现第二域。没有安装 WorkSwarm，`WORKSWARM_NOT_PROVEN`，窄 stdlib HTTPS driver 已实际贯通。

## 本轮 live 的可核查事实

运行命令：Python 3.12.13 `-m runtime.runproof_runtime.effectwitness --live`，退出码 0。无代理、无自动重试。一次 session，2 次 HTTP 200，Provider `DeepSeek`，request/returned model 均为 `deepseek-flash`；官方当日模型映射为 DeepSeek-V4.1-Flash-1017，响应自身未返回独立版本号。

| 项 | 实测值 |
|---|---|
| Run | `run-d6b7e871b0eb4f14979b1f8410c9f683` |
| Scenario / Agent | `order-full-refund` / `rpf41-refund-agent-v1` |
| Environment / revision | `env-run-d6b7e871b0eb4f14979b1f8410c9f683` / `rpf41-sqlite-orders-v1` |
| Order | `order-run-d6b7e871b0eb4f14979b1f8410c9f683` |
| Operation | `refund-run-d6b7e871b0eb4f14979b1f8410c9f683` |
| Receipt | `receipt-8517a0d77bc4620ef0b6054c` |
| Reader / Verifier | `rpf41-sqlite-authority-reader` v1 / `rpf41-order-effect-verifier` v1 |
| HTTP 1 response ID | `58f1a508-0626-4398-ab09-5fae141112d2` |
| HTTP 2 response ID | `380052ac-3065-4c92-8eb6-71e21c71ae63` |
| Tool Call ID | `call_00_63EAhff5gm1ihyquulB65761`，`refund_order` |

HTTP `x-request-id` header 未提供（null），保留实际 response ID 与本地 attempt 1/2，不伪造请求 ID。第一响应 `finish_reason=tool_calls`，冻结参数校验后实际提交 COMMITTED；第二请求包含同一 ID 的 `role=tool`，第二响应 `finish_reason=stop`，无工具调用，摘要存在。只记录摘要存在性，不保存自由文本/推理。

订单持久状态：`paid_minor=2500 CNY` 不变；`refunded_minor 0→2500`，`PAID→REFUNDED`，`revision 0→1`；收据数量 0→1，COMMITTED revision 1。独立读回与收据符合冻结合同，`run_outcome=PASS`，`contract_outcome=CONTRACT_SATISFIED_IN_RUN`，无 violated rules/evidence gaps。该结论只适用于本次约束。

| 预执行合同 / 运行摘要 | SHA-256 |
|---|---|
| `rpf-agent-execution-v1` | `7e30909a650a769048cb0cdf8d2e03c9a27d9febaa65c0439e0b14d47070ef84` |
| `rpf-order-effect-v1` | `17c221d32611054b88b5a25a9a345ae8768a9d7b976291a8d4e5a63f7dff0375` |
| `rpf-experiment-v1` | `e19f94f146e645a19baf13d86429308d0edcd4ad6af2443629ccc6efb5b26a3b` |
| Package source digest（所有新包 `.py` 文件名→原始字节 hash 的 canonical map digest） | `c1e155c38be57a3238711d99b6cb9fa3e9999a1530f3604f111fe70b2115d619` |
| Before authority | `87a02592a6e5c606d76cd035e33eaa1dc114a30fcd93dfbd34971794b314265c` |
| After authority | `05bb64ee6a86b14d35901cf1d547992f1631aef65b03942756c2f7bc7e409393` |
| Receipts | `7095d9a8e2c391931314d75893b0af02c88dbfd327975756e9cc3952f1daeff9` |
| `.local/rpf-41/live-result.json` 原始文件 | `b60f417c005d6630d05fa5ea0352f20236dd445c946c35ad071eef29b9b02147` |

Live budget：2/4 requests，3/8 steps（2 Provider+1 Tool），897 input+208 output=1105/10000 tokens，2.328/1200 秒，0 retries，0/3 非单元测试故障试验。两次 usage 分别 576+117=693、321+91=412。按 [当日官方 peak 价格](https://api-docs.deepseek.com/quick_start/pricing/)及全部 input cache-miss、USD→CNY=10 保守上界估算 **¥0.005187/¥1**，非账单。此前免费 demo 为 1 Tool step；本 Plan 非单元测试累计 4 steps、2 Provider requests。RPF-40 的 2 requests/686 tokens 独立列账，跨两 Plan 合计 4 requests/1791 tokens，未拿旧会话充当本次业务证据。

本次 live fault=none：planned/triggered/observed/reconciled 全 false，activation=NOT_PLANNED。response-lost 与无法 reconcile 的事实由下列确定性测试建立，不声称 live 注入过故障。

## 验证与必要验收

| Gate | 结论 | 实际证据与限制 |
|---|---|---|
| A-01 Git/范围 | PASS | 根目录、remote/base/branch/目标路径、AGENTS、状态及触发器预检；仅新增授权文件，保留 `?? docs/reviews/` |
| A-02 三合同/预算 | PASS | 严格字段/version/identity/digest 冻结；非法工具/金额/路径/预算、usage unknown、request/step/token/cost/time/fault cap 测试 |
| A-03 可变沙箱 | PASS | 免费 fresh demo 与 live 各自真实 SQLite 事务、独立收据；reset 后读回零收据并移除 |
| A-04 Authority | PASS | 独立只读连接、before/after hash；伪造 Tool 成功/失败和 Agent 文本不改变实际 oracle |
| A-05 Verifier | PASS | 正常满足；TEST-ONLY refunded_minor=5000 注入确认 VIOLATION；缺失、错 owner、坏 hash、错签发者 INCONCLUSIVE；Run/Effect 分维度 |
| A-06 Fault | PASS | post-commit response-lost → pending 阻止重放 → 独立 receipt reconcile；不可读时 ERROR/INCONCLUSIVE且单收据；planned-not-triggered 单列；幂等与不同 operation 第二笔拒绝 |
| A-07 Live Agent | PASS | 本轮2次200；真实模型工具调用、实际退款、同 ID 回注、独立效果判定；1105 tokens |
| A-08 Runtime 复用 | PASS | 新 Runtime 包/root CLI；Core ports 和 RPF-28 映射见 README；第二域实现仍 NOT_RUN |
| A-09 回归/安全/清理 | PASS（有环境限制） | 19 新测试通过；完整99项在现有 OTel 环境通过、2 Docker组跳过；旧 tracked 零变动，单份脱敏结果；重型边界未验证 |
| A-10 Git 交付 | PASS | 实现提交 `ad29de64f3f293f819fd77afbb0e8fdd074eca06` 已普通 push，同名远端独立 ls-remote 相等；main 不变。报告收口提交的最终 SHA 见聊天回执；没有 PR/main merge/release/deploy |

实际命令/环境（均从仓库根；`PYTHONDONTWRITEBYTECODE=1`，完整回归 TEMP/TMP 指向 `.local/rpf-41/`）：

- Python 3.12.13：新增 `unittest discover -s runtime/tests -p 'test_effectwitness_*.py' -v` / 最后一次 `-q`，19 tests OK，exit 0；`--help`、`--self-check`、`--demo`、`--live` 均 exit 0。
- Python 3.12.13：完整 `unittest discover -s runtime/tests -p 'test_*.py' -v` 首次 exit 1，99 tests / 1 error / 2 skipped；旧 `test_enabled_export_is_bounded_and_not_per_span_blocking` 因此解释器没有 OTel SDK、缺少 traceparent 而失败。未修改旧测试或依赖锁。
- 改用已有 Python 3.14.6 + `opentelemetry-sdk`/`opentelemetry-exporter-otlp-proto-http` 1.44.0 重跑相同完整命令：99 tests，OK (skipped=2)，exit 0。DockerIntegrationTests、Rpf05RuntimeTests 因 Docker provider unavailable 跳过，不能写成 Docker 已通过。
- live 后最终完整回归 `-q`：99 tests，OK (skipped=2)，测试命令成功；旧 OTel 负向端点的 bounded queue drop/export timeout 为预期诊断。再次 `--live` 在已有账本处拒绝，未联网，结果文件 hash 保持不变。独立检查重新计算三合同、before/after、receipts、source 和结果文件 hash，校验请求计数/usage/Tool Call ID 回注关联，并扫描实际 key 未出现在本次源/测试/文档/结果中：PASS。
- 本轮没有修改旧领域/evidence/CI，因此未追加 Reviewed verifier、Golden Demo、Java/Web、RPF-28/30/32/34/35 heavyweight proof；这些是 NOT_RUN，不代表正式平台端到端验收。

非法预算/路径/工具是安全拒绝；无权威证据是 INCONCLUSIVE/平台错误；故意错误实际业务状态是业务 VIOLATION。这些结论未混为同一种 Agent FAIL。单元测试中的 transport error 为 mock，零真实请求。

## 文件与清理

唯一新增 tracked 文件：

```text
runtime/runproof_runtime/effectwitness/__init__.py
runtime/runproof_runtime/effectwitness/__main__.py
runtime/runproof_runtime/effectwitness/contracts.py
runtime/runproof_runtime/effectwitness/engine.py
runtime/runproof_runtime/effectwitness/orders.py
runtime/runproof_runtime/effectwitness/provider.py
runtime/runproof_runtime/effectwitness/verifier.py
runtime/tests/test_effectwitness_pilot.py
spikes/rpf-41/README.md
spikes/rpf-41/RESULT.md
```

本任务 `.local/rpf-41/` 最后仅保留 `live-result.json`（5352 bytes），包含三合同、请求/usage IDs、工具和状态/receipt 摘要；未提交。正常资源 cleanup 为 `RESET_AND_REMOVED`、generation 1、receipt_count_after_reset 0。任务临时数据库/测试目录已删除。工具自动审批审查以 `blocked by policy` 拒绝解释器缓存清理命令（没有给出更具体原因，命令未执行）；随后按 Plan 将确认属于本任务的缓存移入以下固定隔离位置，原新增包缓存路径已移空，后续运行禁用 bytecode 写入：

```text
.local/quarantine/rpf-41/python-package-cache/       # 本次新包的7个Python 3.12 .pyc
.local/quarantine/rpf-41/test_effectwitness_pilot.cpython-312.pyc
```

没有安装包/venv/wheel、构建产物或截图。未创建或修改 `D:\CS\temp\Red-Repeat`、其他仓库或父目录，未触动 RPF-40 本地产物。仅残留上述8个解释器缓存，不涉及未确认的业务副作用或数据库。

范围/secret/大小与 staging 精确文件核验通过；7个源码文件暂存字节与 live source digest 完全相同，最大源码文件13152 bytes；新代码自行编写，没有复制第三方包或新增依赖/license。实现 commit/push 后 `git diff --quiet` 与 `git diff --cached --quiet` 均 exit 0，状态仅 `?? docs/reviews/`；同名远端独立读回 `ad29de64f3f293f819fd77afbb0e8fdd074eca06`，main 仍为 `bda0cd49e50e3181f604324e94877a24b9885334`。报告收口再次普通 commit/push，最终 HEAD/远端/clean 核验在聊天补录。密钥只从进程环境读取；未保存 Authorization、私有推理或模型自由文本。Authority 临时 seal 不入结果；最小 JSON 不是可离线公证的 Witness。

## 下一边界

当前有真实订单状态反馈、规则违规、证据不足与 UNKNOWN reconcile 的确定性种子，可供 RPF-42 定义有界 PGE 选择；尚未实现多轮自适应/B0 同预算对照、Witness Certificate/离线 Verifier、运维域实装、Lab、WorkSwarm SDK、正式 Worker Job、生产可用性。没有重大范围偏差需要本轮追加批准；Main 应独立复核本次交付后决定后续 Plan。
