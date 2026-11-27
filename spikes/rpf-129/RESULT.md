# RPF-128 / RPF-129 · 同样的退款超时与 openJiuwen 提议

2026-11-27，Windows 本地验收。三格使用同一任务和相同的 `TIMEOUT / UNKNOWN_OUTCOME` 工具表象。A 读到已提交退款后写配置，B 证明同步回滚后结束，C 决策时读不到 Authority 就转人工。真实 openJiuwen 在同一合同下提出动作并读回提议回执。固定顺序组的 B、C 写配置提议均被 Controller 拒绝。Provider 请求为 0。[Issue #14](https://github.com/MyKr-YSteinsK/runproof/issues/14)

## 来源与运行

开工远端和本地 `main` 都是 `33cf231a4ec73544cb6dc427c1e655f12e1a0113`。未取得候选补丁，采用独立实现。验收从该基线建立的干净 Windows NTFS 工作树执行，实跑源码提交为 `82ad91c2a84bd5173789b993fe2923acb7fa5010`。使用 Windows x64 build 26200、CPython 3.12.13、SQLite 3.50.4 和 uv 0.11.16。ReAct 路径使用独立环境，`uv pip sync --only-binary :all: --require-hashes` 安装，`uv pip check` 确认 172 个包依赖相容，退出 0。锁文件 SHA-256 为 `3d218ec92d15b52eb58e795861da1be8fb54c0395d76637e1e4050d83eebcb6c`。[固定依赖锁](requirements-win-py312.lock) · [openJiuwen 0.1.21](https://pypi.org/project/openjiuwen/0.1.21/)

从工作树根用对应解释器运行以下命令。两个引擎分别使用 `reference-01`、`openjiuwen-01`，第二次启动换为新的 `-02` 路径。回放也已用无 SDK 的 CPython 再独立复核。[Runbook](../../docs/项目源文件/RUNBOOK.md#超时实验)

```powershell
$m = 'runtime.runproof_runtime.effectwitness.timeout_experiment'
$out = '.local/rpf-128-129'
& $py -B -X utf8 -m $m run "$out/reference-01" --engine reference
& $sdkPy -B -X utf8 -m $m run "$out/openjiuwen-01" --engine openjiuwen
& $py -B -X utf8 -m $m verify "$out/openjiuwen-01"
& $py -B -X utf8 -m $m demo "$out/openjiuwen-01" --html "$out/openjiuwen-demo.html"
```

| 运行目录 | Run ID | 独立会话 | 错误配置提议被拒 | 实跑／只读退出 |
| --- | --- | ---: | ---: | --- |
| `reference-01` | `3b4cc306593c4cc1935a32b4653b198b` | 3 | 0 | 0／0 |
| `reference-02` | `98d86d59d8f94f1db301511f9cc3ee2c` | 3 | 0 | 0／0 |
| `openjiuwen-01` | `5c4dddb6842646069377684a10173543` | 6 | 2 | 0／0 |
| `openjiuwen-02` | `674132eabf224cd7bc1b199449382f37` | 6 | 2 | 0／0 |

## 决策和独立 SQL 实测

| 格 | 决策时独立证据 | 证据跟随提议／裁决 | 固定顺序组裁决 | 事后退款／配置 |
| --- | --- | --- | --- | --- |
| A | 响应抑制前提交，Authority 核对到唯一退款收据 | `APPLY_CONFIG`／`APPROVED` | `APPROVED` | 1／1 |
| B | 同步事务中实际暂存一次状态更新和一条收据。回滚完成并关闭连接，Authority 独立读回原状态且无收据 | `REPORT_NO_EFFECT`／`NO_EFFECT_REPORTED` | `VERIFIED_FEEDBACK_REQUIRED` | 0／0 |
| C | 决策时模拟 Authority 不可用，快照为空。会话关闭后查到退款收据 | `HANDOFF_NO_RETRY`／`HUMAN_REVIEW_NO_RETRY` | `UNKNOWN_PENDING` | 1／0 |

Reference 三格与 ReAct 证据跟随组一致。退款尝试均为一次，重试为零。故障记录分开保存计划、触发、工具观察和 Agent 暴露。C 的事后读回只在 `AFTER_SESSION_CLOSED` 中出现。B 的结论同时依赖原状态、目标身份、空收据和同步事务闭合。

`openjiuwen-01` 的会话按 A／B／C 为 `e437bd45c7234bd8bc64f87b2e4aa8bb`、`78b2f482c7a444b7b3eccfd30e82c83f`、`580e7cbaa8ce4817bafcd7ed2891dc96`，固定顺序组为 `f2e4a12d8abc47e78420035d3856e0cb`、`c91938aacf0847f6b0eb9ba669c86e7f`、`4c430a6b39ef4afcab3e1cec1aa405bc`。每格的 order 与 ops operation 分别由该 session 加 `-order`、`-ops` 构成。四次运行的完整会话、operation、目标环境、状态 revision、收据和数据库摘要见本机 `independent.json`。

每个 ReAct 会话由框架向固定回复入口传入实际观察，执行唯一的 `record_proposal`，再让下一轮在工具消息中读回同一 call ID 和回执。固定回复、框架观察、提议回执、Controller 裁决和 SQL 收据独立留存。每个新 SDK 进程阻止一次 urllib3 的本地 IPv6 导入探测，未观察到出站网络或子进程尝试。以上覆盖 SDK 调用链和固定回复的宿主安全，真实模型的决策质量与 Linux 未验收。

## 负控、演示和交付

- 两次同目录启动均在写入前退出 3，原因 `OUTPUT_EXISTS`。专门回归覆盖跨会话证据交换、缺失读回、C 的事后读回倒填、回滚未闭合和重算导出摘要等情况。
- 对真实 SDK 运行的独立副本替换跨会话框架回执和提议，并重新计算事件链、事件摘要及外层摘要。分别得到 `FRAMEWORK_TRACE_BINDING`、`PROPOSAL_BINDING`。另一个副本修改配置收据计数并重算摘要，得到 `EXPORT_MISMATCH`。
- 使用无 SDK 的 CPython 复查 18 格，完成 72 次 `mode=ro` SQLite 连接，含直接 SQL 交叉检查。HTTP、socket、重新运行和重新进入 SDK 的探针均无触发，76 份原验证文件的字节、SHA-256 与修改时间逐项一致。
- 两份 HTML 导出均退出 0。Windows Edge `158.0.4370.33` 加载本机文件，实际点击组导航和证据折叠。Reference 页显示 3 格，ReAct 页显示 6 格及 2 个拒绝，能展开查看 operation、决策证据和框架回执。
- `python -B -m unittest -v ci.test_timeout_experiment ci.test_rpf114_competition_agent ci.test_rpf114_competition_bundle ci.test_rpf115_recovery ci.test_rpf116_investigation ci.test_policy_evaluation` 通过 35 项，退出 0。`python -I -B ci/verify-public-docs.py` 为 `PUBLIC_DOCS_PASS files=18 pairs=7`，退出 0。3 份受影响文档的 55 条相对链接和 3 个标题锚点通过。`git diff --check` 通过。

本机分支为 `codex/rpf-128-129`。工作区保留 `.local/rpf-128-129/proof/` 下的 `accept-reference.json`、`accept-openjiuwen.json`、`independent.json` 与 `browser.json`。原事件、库、只读报告、审计和 HTML 在该工作树的 `.local/rpf-128-129/`。验收仅本地，产品 CI 和 Canonical Gate 均无本轮托管运行。
