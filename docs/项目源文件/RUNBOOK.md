# RunProof 运行与恢复

## 环境

从 `MyKr-YSteinsK/runproof` 的实际 Git 根工作。动手前核对根、分支、HEAD、远端、目标路径状态和既有用户改动。Windows 上用已确认的 CPython 可执行文件运行 Python 命令。Python Install Manager 别名曾触发意外安装。

| 部件 | 安装与版本依据 | 2026-11-23 核验 |
| --- | --- | --- |
| Web | `package-lock.json`。新工作区用 `npm ci` 准备依赖，CI 配置使用 Node 22 | Node 24.16.0，本机 Vite、Vitest、TypeScript、React 与锁文件相符 |
| Python Runtime | CI 用 CPython 3.12。`runtime/requirements.txt` 是可选 OTel 路径，SDK 和 JiuwenSwarm 有各自依赖入口 | 本机 CPython 3.14.6 聚焦测试。按相应工作流判断 SDK 版本及兼容性 |
| Java Control Plane | Java 17、Maven、`control-plane/pom.xml` | Java 17.0.12、Maven 3.9.16。离线测试与打包通过。完整多服务运行沿用历史验收 |
| 本机业务环境 | Golden Demo 参照 Docker、PostgreSQL 与 lifecycle；竞赛入口使用本机 Node、CPython SQLite、PowerShell 7.2+ | 本轮审阅与静态复核。新的受控业务会话需要独立目标与资源范围 |

## 本地 Reference Agent

首次在仓库根运行 `npm ci`。设置 `$py` 和 `$node` 为实际 CPython 与 Node 可执行文件的绝对路径。PowerShell 7.2+ 下，日常启动命令为 `.\demo\competition-bundle\start.ps1 -PythonExe $py -NodeExe $node`。启动器输出 URL 和 owner nonce。复用前一次运行时，加 `-Reopen $nonce`；停机用 `.\demo\competition-bundle\stop.ps1 -Nonce $nonce`。解包后在 `app/` 运行同名脚本。入口仅监听 127.0.0.1 的 4187 和 8780。启动器按可执行文件、PID 和创建时间核对进程归属。

1. 新 owner 页面先查询 capability，用户勾选并启动后产生 request 和 session。记录两者及 owner nonce。第二轮意图里的 `input_feedback_sha256` 可回查第一轮独立效果验证。
2. 若浏览器超时，刷新原地址，或停止后按原 nonce 只读打开 `/effectwitness/agent?session=<id>&event=<seq>`。已知 request 也能从同源的 `/effectwitness-product-api/request/<id>` 读回。已有 owner 无法初始化或记录不匹配时保留目录调查。
3. 页面调查按原 environment 和 operation 重开目标 SQLite，展示收据与证据缺口。中断可能保留原 `RUNNING`，调查报告将后续动作列为人工处理。完成时下载 Witness，其余状态下载调查报告。将 `$file` 设为下载所得 JSON 的绝对路径，用 `& $py -B -m runtime.runproof_runtime.effectwitness.competition_agent_verify $file` 复核内容。有独立可信摘要时才添加 `--expected-sha256 $anchor`。历史 Witness 使用记录创建时的 verifier。
4. 持久预约及中断回归运行 `& $py -B -m unittest -v ci.test_rpf115_recovery ci.test_rpf116_investigation`。RPF-116 的检查点包含进入 `ResponseLost` 分支以后、写入 `UNKNOWN_OBSERVED` 以前的位置。[运行证据与复现](../../spikes/rpf-116/RESULT.md)

### RPF-126 离线验收命令

实跑基于 `bc8f72438677dee69b905a3ffbfe27894bc17d06`。源码启动、同 nonce 只读重开和停机使用上节命令。验收时依赖已有 npm 缓存，运行 `npm ci --offline --no-audit --no-fund --logs-dir (Join-Path $proof 'npm-logs')`，`$proof` 为新的验收根。已有 ZIP 可以用独立 verifier 检查后再按包内入口运行。以下 `$zip` 为包路径，`$freshExtraction` 为尚不存在的解包位置，`$packageWitness` 为包内会话下载的 JSON。

```powershell
# 在验收源码的仓库根核对 ZIP 和成员
& $py -I -B ci/test_rpf114_competition_bundle.py $zip $freshExtraction
# 在新解包的 app/ 中使用包内脚本
.\start.ps1 -PythonExe $py -NodeExe $node
.\verify-witness.ps1 -PythonExe $py -Witness $packageWitness
.\stop.ps1 -Nonce $packageNonce
```

已验收包的源码、摘要和实跑回执见 [RPF-126](../../spikes/rpf-126/RESULT.md)。当前在阶段验收，使用 [接手索引](HANDOFF_INDEX.md) 和已有回执复核即可。需要重建时按 RPF-126 A03 的 `--complete` 命令使用新构建 nonce。

### 调查报告 v2

报告 `runproof-agent-investigation/v2` 保留原执行读回及新连接读取的当前事实。故障的 `planned` 和 `agent_exposed` 是布尔值。已记录 `UNKNOWN_OBSERVED` 时，`triggered` 与 `observed` 为 `true`。订单写入意图已落盘但该事件缺失时，两项为 JSON `null`，页面显示未知，报告标明 `FAULT_EVENT_NOT_PERSISTED`。订单在写入意图前停止或场景未计划故障时，两项为 `false`。收据用于单独核对业务效果。

CLI 返回 `CONTENT_CHECKED_LOCAL` 表示通过内容复核，`VERIFIED_ANCHORED` 还表示与提供的独立摘要一致。诊断同时给出业务读回和任务完成状态。成功任务使用 Witness 复核，外部签发者为 `NOT_ESTABLISHED`。CLI 退出 3 时输出具体拒绝原因。旧诊断 v1 返回 `INVESTIGATION_LEGACY_SCHEMA`，与当前源码不匹配的 v2 返回 `INVESTIGATION_SOURCE_MISMATCH`。保留旧字节并用匹配原 source map 的工程包或源码验证。v1 的无锚内容检查存在本轮记录的语义缺口。

## 本地策略对照

在仓库根使用已核对的 `$py`。全量评测尝试 12 个新的合成会话，聚焦命令在一个场景下为两种策略各创建一个会话。确定性策略的运行目录取 `.local/rpf-117/` 或 `.local/rpf-121/` 下的新路径。

```powershell
$evaluation = 'runtime.runproof_runtime.effectwitness.policy_evaluation'
& $py -B -m $evaluation run .local/rpf-117/comparison
& $py -B -m $evaluation verify .local/rpf-117/comparison
& $py -B -m $evaluation run .local/rpf-117/altered --case ALTERED_VALUE_KEEP_DIGEST
```

用 `comparison.json` 与 `cases/<场景>--<策略>/` 找到 owner nonce、持久 request、session、operation、原诊断及成功 Witness。可带原 nonce 用现有 `-Reopen` 入口查看某一格。评测 CLI 随仓库源码提供。演示工程包提供单会话 Runtime 与 verifier。

`verify` 以只读连接重新读取目标和台账，核对冻结场景、实际策略选择、底层报告与计数。退出 0 表示已复核的比较满足宿主安全合同。负对照的 Agent FAIL 仍计入表格。退出 2 表示测得安全失败或证据不足，退出 3 表示输入或证据集无法复核。无独立可信锚的复核状态为 `CONTENT_CHECKED_LOCAL`，签发者为 `NOT_ESTABLISHED`。保留台账、版本与导出文件以便重开。[RPF-117 实测](../../spikes/rpf-117/RESULT.md)

### 单场景对照报告

用 `explain` 复核已有的确定性策略比较并导出一个场景。输入与评测器源码身份须匹配。HTML 设在 `.local/rpf-121/` 内、评测输入目录外的新文件。使用浏览器打开即可阅读。

```powershell
& $py -B -m $evaluation run .local/rpf-121/compare-altered --case ALTERED_VALUE_KEEP_DIGEST
& $py -B -m $evaluation verify .local/rpf-121/compare-altered
& $py -B -m $evaluation explain .local/rpf-121/compare-altered --case ALTERED_VALUE_KEEP_DIGEST --html .local/rpf-121/compare-altered.html
```

复跑正常反馈时，另取新目录和 HTML 文件名，场景换为 `VALID_FEEDBACK`。报告并排展示两种策略看到的反馈、原事件序号、工具提议或停手、裁决和业务收据。按每格的诊断路径和 `session.events[].seq` 定位原件，按 `readings` 查独立业务读回。已完成会话可用报告中的摘要回查同格的 `witness.json`。退出 0 或 2 时保留当前复核与评分状态。退出 3 时保留拒绝原因。导出对输入和 SQLite 使用只读路径，接受尚不存在的 HTML 文件。[RPF-121 实测](../../spikes/rpf-121/RESULT.md)

### 模拟模型回复

使用 `--fixture-model` 运行参考与合成回复对照。选用 `.local/rpf-118/` 内的新目录。加 `--case ALTERED_VALUE_KEEP_DIGEST` 可只跑反馈内容被改动的场景。

```powershell
& $py -B -m $evaluation run .local/rpf-118/comparison --fixture-model
& $py -B -m $evaluation verify .local/rpf-118/comparison
```

用该格的 `selection.json` 取得 owner nonce，到 `.local/rpf-100-product/competition-rpf114-<nonce>/fixture-exchanges/` 查每步尝试与回复。核对同格 `result.json` 的两步评分、`investigation.json` 的原事件和只读收据，以及成功时的 `witness.json`。回复丢失、超时、未完成的尝试保留未知状态。复核重新解析已保存回复，无模型请求和业务工具重放。比较 v1 与 v2 使用各自产出时的源码身份。工程包的入口仍为离线单会话。[RPF-118 实测](../../spikes/rpf-118/RESULT.md)

### RPF-119 的真实模型与离线复核

RPF-119 的一次性授权已消费。正式证据位于 `.local/rpf-119/experiment/`，原启动命令与 manifest 摘要保存在 `.local/rpf-119/live-launch-rev2.json`。继续调查使用 `verify`，保留原 grant、claim 和账本。验证器无需凭据或账户币种。

```powershell
$live = 'runtime.runproof_runtime.effectwitness.rpf119_live'
& $py -B -m $live verify
& $py -B -m $live verify --local-stub .local/rpf-119/stub-acceptance/experiment
```

在 `provider-journal/` 查持久预约、可能发送、POST 写出、响应头及结束证据。按 `cases/<场景>--<策略>/result.json` 找 request、session、owner nonce 和 SQLite 诊断。单会话 Witness 使用本地业务合同，真实消耗以外层比较和 Provider ledger 为准。复核只读取原件及脱敏投影。试验状态与已观察的成本见验收报告。[RPF-119 结果](../../spikes/rpf-119/RESULT.md)

## R72r2 三项隔离复验

在 Windows 的本地 NTFS 检出中使用 CPython 3.12+ 和 Git。设置 `$py`、`$git` 为已核对的可执行文件绝对路径。从仓库根执行，`$source` 是本地已有的完整 Git 提交 SHA，`$run` 是 `.local/rpf-124/` 下尚不存在的一级目录。两条命令分别执行原测试和事后只读复核。

```powershell
$source = (& $git rev-parse HEAD).Trim()
$run = '.local/rpf-124/recheck-001'
& $py -I -S -B -X utf8 ci/rpf124_r72r2.py run --git $git --source $source --output $run
& $py -I -S -B -X utf8 ci/rpf124_r72r2.py verify --git $git --output $run
```

`run` 从 Git 对象创建新的 `source/` 检出树。预检核对 76 个 Git blob、冻结测试与覆盖矩阵的摘要、三项方法和源依赖。每项在新的 CPython 进程中执行一次，写入 `source/.local/rpf-72-rev-2/tests/` 下各自的新 owner。第三项使用一个合成退款 SQLite。`run.json` 记录版本与解释器，`method1.log` 至 `method3.log` 和对应 JSON 保留原输出、进程退出与文件摘要，`complete.json` 记录完成时的三份进程回执摘要。Git 读取和测试可全部在本地完成，输入仅用指定提交的冻结文件和仓库清单。

`verify` 接受保留同次源码、进程回执和业务文件的目录，在退出 0 时报告 `CONTENT_CHECKED_LOCAL`。它回放原生 WAL，并使用 `mode=ro` 和 `PRAGMA query_only=ON` 读回原退款库。复核前后核对文件摘要、长度与修改时间。对同一证据重复执行时业务结论一致。退出 2 时查看 JSON 的 `reason` 以及保留的日志。`OUTPUT_EXISTS` 要求新目录，`FROZEN_*` 表示输入身份不符，`PROCESS_RUN_BINDING`、`LOG_DIGEST_MISMATCH` 或 `EVIDENCE_*` 表示对应记录或材料无法复核。保留失败现场可供调查，复核操作仅从现有材料读回。

Python 审计记录覆盖本次原方法涉及的接口，Windows 文件系统和 SQLite 读回另有实测。复核报告的外部签发者为 `NOT_ESTABLISHED`。Canonical 覆盖按相应 Actions run、attempt 和 checkout 独立核对。[工具](../../ci/rpf124_r72r2.py) · [Windows 实测](../../spikes/rpf-124/RESULT.md)

## 快速校验

按修改选取，在仓库根运行。`python` 表示已核对的解释器。在当前 Windows 终端可用 `& $runproofPython` 调用其确切路径。

```powershell
npm test
npm run build
python -B -m unittest -v ci.test_control_plane_client_transport runtime.tests.test_control_plane_client runtime.tests.test_durable_worker
python -B ci/verify-public-docs.py
python -B runtime/verify-reviewed-artifacts.py
python -B demo/verify-golden-demo.py --root . --json
mvn -q -B test package -f control-plane/pom.xml
```

`npm run build` 包含 TypeScript 检查。Web 构建可通过 `npm run build -- --outDir .local/<task>/web-dist` 写入隔离目录。测试临时文件可将 `TEMP`、`TMP`、`TMPDIR` 导向任务的 `.local/<task>/tmp`。Maven 缓存充足时可用 `-o` 离线复验。本轮 Web、聚焦 Python、Java 与静态证据核查结果见 [CURRENT_STATE](../project/CURRENT_STATE.md)。

## 启动和取证入口

| 目的 | 使用的入口 | 输出及边界 |
| --- | --- | --- |
| Golden Demo | [Demo 指南](../DEMO.zh-CN.md)，`demo/start-demo.ps1` 与 `demo/stop-demo.ps1` | Web `127.0.0.1:4173`，使用 reviewed corpus 和受控服务。仅对本次 owner 使用停止入口。 |
| 记录工作台 | [交付指南](../EFFECTWITNESS_DELIVERY.zh-CN.md)，`demo/effectwitness-delivery.ps1` | 记录型 `/effectwitness/workbench`，独立历史 Evidence。预览服务只读。 |
| 离线参考 Agent | [完整项目包启动](../../demo/competition-bundle/README-COMPLETE.zh-CN.md) · [本地产品指南](../EFFECTWITNESS_LOCAL_PRODUCT.zh-CN.md) | 单会话受控写入和独立 Witness 验证。使用新、受限 owner，记录端口与进程归属。RPF-114 的实际封存见 [RESULT](../../spikes/rpf-114/RESULT.md)。 |
| Live Explorer 或新的物理预算实验 | 对应任务授权、源和 active gate；先读 [当前风险](../project/CURRENT_STATE.md#安全ci-与本地现场) | 观察真实用量、停止条件和能独立核验的回执。旧 UNKNOWN 或预算缺失时保留现场。 |

## 数据和产物

- `runtime/reviewed-*.json` 是已审阅的 synthetic / controlled corpus，供 Web、verifier 和 Demo 使用。按当次运行的 source identity 查源，保留原字节、编码与换行。历史 ZIP 和 PPT 等索引见 [归档](../history/MAINTENANCE_ARCHIVE.md)。
- `spikes/` 同时含实验入口与冻结证据。CI 和 Demo 仍引用其中一部分。`ci-results/` 与 `.local/` 的旧输出按来源、owner、证据身份保留。新增产物按本次任务的隔离路径记录。
- `docs/delete/` 为用户手工清理区。复用旧生成物前核对依赖版本与身份，通常按锁文件重建更可控。凭据、原始账本、私密日志与真实业务数据留在授权环境。
- 外部 `config-center` 只进行了源码审阅。未来联动采用明确版本的新本地实例、独立环境与合成配置，具体执行待用户审批。[联动方案](UPGRADE_REVIEW.md)

## CI 和交付

普通授权交付沿用 `main` 及 scoped commit/push。检查 GitHub 身份和目标远端，核对推送可能触发的工作流，推送后读回 SHA、关键文件和运行状态。Canonical Gate 是发行证据，失败时保留状态与 required coverage。旧手动 Provider 或 conformance workflow 有独立授权和预算，任何一轮的旧配置不自动续用。

Runtime Router 按 `ci/runtime-contract-test-matrix.json` 检验 `runtime/tests/test_*.py` 的清单及 LF SHA-256，coverage handoff 也绑定整个 matrix。`SOURCE_DRIFT` 表示输入身份校验失败，可能在 Router 生成账本前终止。接管新增的 HTTP transport 负控在 `ci/test_control_plane_client_transport.py` 聚焦执行，已有封存测试与覆盖条件仍可独立核验。

### 归档覆盖对账

从同一 Canonical run 与 attempt 取 RPF-85、RPF-87、RPF-89 JSON，可加对应 RPF-90 观察。回查 Actions 的 ZIP 摘要和 checkout，使用 `python -B -m ci.rpf120_reconcile --handoff $handoff --rpf87 $rpf87 --rpf89 $rpf89 --rpf90 $router`。退出 0 表示证据对账成功，发行覆盖结论见 JSON 的 `coverage_gate`。退出 2 保留具体的证据冲突。原 Windows 测试从新 NTFS 隔离根运行，保留 junction 及原进程证据，清单不遍历链接。[正式原件、命令和实测](../../spikes/rpf-120/RESULT.md)
