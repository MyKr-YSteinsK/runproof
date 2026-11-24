# RPF-116 rev-1 · 诊断报告校验

2026-11-24。诊断 v2 拒绝互相矛盾的批准、反馈和执行事件。订单已退款但故障事件来不及写入时，报告确认退款收据，把故障触发和观察标为未知。计划见 [Issue #2](https://github.com/MyKr-YSteinsK/runproof/issues/2)。

## 源码与格式

| 复验环境 | Git 来源 | 报告 | Source map SHA-256 | Verifier 文件 LF SHA-256 |
| --- | --- | --- | --- | --- |
| 基线独立源码目录 | `93f2151cdeadec8e106603ad54b882f5b383f82b` | `runproof-agent-investigation/v1` | `190483d4f4cd9b94fb2e178f0b73e2d2f6d7e2ecba9de63e53cb27060fcc1934` | `93cf6ded8a6ad2299cb7b3be3e1873deb3b030ef2c075c396afbe2311b9568b5` |
| 候选 checkout 与完整包内 app | `783e82cf15a674906452f6ee215725452ec6da91` | `runproof-agent-investigation/v2` | `9d28f354d37a7f808e2d17f5112a3f6e536a3d385f2c6b6e4130a0cc36b4aedc` | `59f97715a1999d5eb6b86bcb1bf2bc64bb369f8cdaf8b2ebbd4db5e7ecb4b4e6` |

主工作树和远端 main 的开始位置相同。每个环境分别创建新的 SQLite owner，使用确定性策略与虚构订单。Provider 调用和预约均为 0。AgentPolicy 与运行端写入合同沿用现有实现；改动集中在诊断检查和展示。[诊断校验](../../runtime/runproof_runtime/effectwitness/competition_agent_investigation.py) · [CLI](../../runtime/runproof_runtime/effectwitness/competition_agent_verify.py) · [测试入口](../../ci/test_rpf116_investigation.py)

## A01–A03、A07 · 同一反例的前后结果

驱动先产生合法 `STOPPED` 会话，用缺失的第二轮反馈让 Agent 停止。每份检测样本只修改表中字段，按原序重算事件链、派生摘要与报告 `content_sha256`。基线与候选各用自己的报告格式、source map 和 verifier。从未修改的报告先取得摘要，再用它做固定锚对照。

| 用例 | 预期合同 | 基线 CLI 无锚 | 候选 CLI 无锚 | 固定原报告锚 |
| --- | --- | --- | --- | --- |
| 原始合法停止报告 | 允许检查合法停止 | 0 · `CONTENT_CHECKED_LOCAL` | 0 · `CONTENT_CHECKED_LOCAL` | 两版 0 · `VERIFIED_ANCHORED` |
| 已批准意图的工具改为 `ungranted_tool` | Controller 对同一意图判 `INTENT_REJECTED` | 0 · `CONTENT_CHECKED_LOCAL` | 3 · `APPROVED_INTENT_CONTRACT` | 两版退出 3，锚不匹配 |
| 只改 `VERIFIED_FEEDBACK.sha256` | 摘要必须等于原 value 的计算值 | 0 · `CONTENT_CHECKED_LOCAL` | 3 · `FEEDBACK_DIGEST` | 两版退出 3，锚不匹配 |

基线/候选原始停止报告的 SHA-256 分别为 `ee5d0ed702e92553f9f97bca2fd024a3b63990dca0601246342932bb961d6ed9` 和 `863fc5b08c37305b89c4a03ecdf9b233a452e7788e69ceab7aebf3f8b8088790`。完整变更样本、实际 CLI 输出和摘要在每组 `comparison.json` 中。无锚负控由对应语义合同拒绝，固定锚负控仍由 `WITNESS_DIGEST` 拒绝。

聚焦回归进一步覆盖工具参数、候选或动作身份、step、观察和反馈绑定、跨轮/跨来源反馈、原读回摘要、轮次与已落盘写前观察、提前或重复的写入事件和错误 origin。合规双域执行及 Witness 通过，无效意图被 Controller 拒绝的诊断、缺失或错误的 Agent 反馈视图引发的安全停止也通过。当前调查读回发现目标缺失、不可读或收据缺失时保留明确缺口。原执行当时因缺收据而停止的记录可以与稍后的 `COMMITTED` 同时成立，任务完成仍未证实。

## A04–A06 · 提交后、故障事件落盘前的中断

测试子类在 `emit(UNKNOWN_OBSERVED)` 调父类前验证当前异常为 `ResponseLost`，通过 stdout 通知父进程，再等待。父进程收到 session ID 后终止子进程。另起进程只读打开同一 owner，并用独立 SQLite 连接核对状态和收据。三个正式样本均保留 `RUNNING`、原 request `rpf116-interruption`、0 条持久化 UNKNOWN 事件、1 条绑定到原订单 operation 的退款收据、0 次配置写入（配置库缺失）。逐文件 SHA-256 在只读调查前后相同。

| 环境 | Owner nonce | Session | 终止 / 独立读回 PID | 故障触发 / 观察 | 报告 SHA-256 |
| --- | --- | --- | --- | --- | --- |
| 基线 | `a5442d2ec0d04fec95a98b6462a83ffb` | `6708dfbf12c64451b721bd405aecfe5c` | 14820 / 20952 | v1 的 false / false | `521e2ab2f0e243b71f30729693f0603c28b3d364d87b04fa40bd813b50892a1b` |
| 候选 | `b34d5b90f77942abad2ee47e5d3e37f7` | `2b2097094cda4680b25364574329aa7b` | 26144 / 30568 | null / null | `2d6977e85e89ed840c225e0b5436df76521e677d309a4e03e2fe3ef5fa3292bc` |
| 解包 | `dabfb1dc676c4f2aa791101aa9cf0785` | `4680855d835947209c2a87a0951420a7` | 34128 / 32440 | null / null | `79d996b2bb44552fdbdd1e9bcd8826107c3f7fc61b8f8ef1d37eedba90a54d69` |

订单 operation ID 和 environment ID 均为各行 session ID 加 `-order`。修复版在已登记写入但故障事件缺失时加 `FAULT_EVENT_NOT_PERSISTED`，保留 `planned=true` 与 `agent_exposed=false`。回归也逐项终止在批准后、写入意图后、UNKNOWN 事件已保存后与 Authority 事件已保存但 round 尚未保存的位置。已有事件形成合法前缀时继续可查。配置域未计划该故障；订单在写前审批阶段停止时，业务调用尚无已持久化的写入意图，触发和观察为 false。

基线 v1 的输出保留原字节。新版 CLI 读原 v1 退出 3，原因是 `INVESTIGATION_LEGACY_SCHEMA`。需要历史复核时用上表中的原版本，并按本报告理解 v1 的已知语义缺口。无锚 `CONTENT_CHECKED_LOCAL` 表示报告内容及记录约束通过。提供独立锚后 `VERIFIED_ANCHORED` 还确认字节与该锚相符。任务完成由成功 Witness 核验，签发者为 `NOT_ESTABLISHED`。

## A08 · 工程包及集成

在候选实现提交构建并独立解包。完整 ZIP 的 SHA-256 为 `161fadd543ef4227c573bb47005e34ef18a603255700ce2c05c3860ea1833238`，1,108,670 字节，320 个成员。验证器核对 manifest、成员摘要、source_commit、app 和 source 的 Runtime 字节。解包 app 下加载的 verifier 与候选 source map 完全一致。外部测试入口以脚本文件加载，从解包根导入 Runtime，7 项聚焦测试及对照驱动均通过。

经解包启动器从浏览器确认并运行一次。Session `d452f39dcfe14dd5ac7077dba697f507`，request `3c75228d-4b02-4a8b-b2fa-c4b7c5e00e29`，owner nonce `53ac475440c34a2f9927b07e6d135eb6`。两域各一条真实收据；下载的 Witness 与独立 ledger BLOB SHA-256 `aad3997203ea0950493cbce3ca942ff68b04008a9725a308338c1fca73f971e0` 一致，包内 CLI 退出 0。

随后用解包中断样本的原 nonce 启动只读 Gateway，浏览器看到 `COMMITTED`、触发/观察 `Unknown` 与 Agent 原始故障 `No`。刷新、重新查询和下载阶段发送 0 次 POST，服务停止后 owner 摘要与接管前一致。下载的诊断与启动 Gateway 前保存的独立报告锚一致，包内 CLI 退出 0。正常会话的页面显示 `Yes`，并单列已记录完成和 issuer 状态。两次浏览器实测只使用 127.0.0.1 的 4187 与 8780，服务进程分别为 19148/32656 和 19708/12024，均已停止。浏览器及子进程回执保存在本地证据目录。

本机为 CPython 3.14.6、SQLite 3.50.4、Node 24.16.0 和 Edge 158。产品命令的 Python 36 项、Node 1 项、Web 78 项及构建、文档、reviewed artifacts、Golden Demo profile 均通过。产品 workflow 接入 RPF-116 聚焦套件与本文路径。发布资格继续由 Canonical Gate 判定。审查基线的合同检查通过，required coverage 两步分别缺 534、516。最终文档提交、远端校验和两个 CI 的实际 checkout 与结论见交付回执。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45387631184) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45387780159)

### 复跑命令与证据位置

在仓库根以已核对的 `$py`、`$node` 执行。对照命令使用新的输出子目录。

```powershell
& $py -B -m unittest -v ci.test_rpf115_recovery ci.test_rpf116_investigation
& $node --test ci/test_rpf113_competition_server.mjs
npm test
npm run build -- --outDir .local/rpf-116/web-dist
& $py -B ci/verify-public-docs.py
& $py -B runtime/verify-reviewed-artifacts.py
& $py -B demo/verify-golden-demo.py --root . --json

$repo = (Get-Location).Path
$driver = Join-Path $repo 'ci/test_rpf116_investigation.py'
$probe = "import runpy,sys; runpy.run_path(sys.argv.pop(1), run_name='__main__')"
$base = '93f2151cdeadec8e106603ad54b882f5b383f82b'
git archive --format=zip -o .local/rpf-116/base-recheck.zip $base -- runtime/__init__.py runtime/runproof_runtime/__init__.py runtime/runproof_runtime/models.py runtime/runproof_runtime/effectwitness
Expand-Archive -LiteralPath .local/rpf-116/base-recheck.zip -DestinationPath .local/rpf-116/base-recheck
Push-Location .local/rpf-116/base-recheck
try { & $py -E -B -c $probe $driver --capture (Join-Path $repo '.local/rpf-116/base-recheck-evidence') }
finally { Pop-Location }
& $py -E -B -c $probe $driver --capture .local/rpf-116/current-recheck-evidence

& $node demo/competition-bundle/build-bundle.mjs $freshNonce $py --complete
& $py -B ci/test_rpf114_competition_bundle.py $zip $freshExtraction
Push-Location (Join-Path $freshExtraction 'app')
try { & $py -E -B -c $probe $driver -v } finally { Pop-Location }
```

实测 ZIP 与 sidecar 位于 `.local/rpf-114-complete/d23ad058da024f61a7d07e789a681302/deliverables/`。本轮 `.local/rpf-116/` 保存 `{baseline,candidate,package}-evidence/`、独立解包、`package-surface.log`、两个浏览器导出和 SQLite/PID/请求记录。基线、候选与包内的合成 owner 各自位于对应 Runtime 根的 `.local/rpf-100-product/`。两枚浏览器临时配置可随本轮手工清理目录处理。用户未跟踪的 RPF-74/rev-4 与 RPF-96 文件和旧实验现场保留。
