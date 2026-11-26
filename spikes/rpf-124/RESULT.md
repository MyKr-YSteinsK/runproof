# RPF-124 rev-1 · R72r2 本机复验工具

2026-11-27。在新的 Windows NTFS 检出中，仓库入口运行了三个冻结原方法，全部通过。两个后续进程独立复核留存的原生 WAL 和合成退款库，输出逐字节一致。三种负控均拒绝。真实 Provider 预约、发送和 token 均为 0。[任务正文](https://github.com/MyKr-YSteinsK/runproof/issues/10)

## A01 · 干净检出

开工时本地与远端均为 `be936b2ef5a6f4b34ed5700d7e814da7087e3d5b`。读取了 RPF-123 的报告、`pilot.py` 和 `run-pilot.ps1` 原件。新入口从本地 Git 对象提取固定的 76 份源码、元数据及包入口。冷启动现场未复制 RPF-123 的脚本、旧 owner、WAL、运行输出或 Actions ZIP。[RPF-123 结果](../rpf-123/RESULT.md) · [仓库入口](../../ci/rpf124_r72r2.py)

从本地验收候选 `ebf1763c55ad0c57c2ba8edbf20d430adbc41f59` 新建 detached 检出。启动前 Git 状态为空，尚无 `.local`。主工作区下本次验收目录为 `.local/rpf-124/acceptance-5258c1a9/`，其中 `caller/` 为检出。测试输入写到 `caller/` 内新的输出目录，各原方法解析的 owner 根为该输出的 `source/.local/rpf-72-rev-2/tests/`。工具拒绝重解析点、已有输出目录和已有 owner。

| 已核对的输入 | 实测身份 |
| --- | --- |
| Windows 和卷 | x64 build 26200，NTFS，PowerShell 7.6.9 |
| Git 和解释器 | Git for Windows 2.54.0，CPython 3.14.6 x64，SQLite 3.50.4 |
| CPython 可执行文件 SHA-256 | `03168c01b7b7491423350e82c26fee71f35b43694d1319d3c668bda6903a0c38` |
| 冻结测试与矩阵 LF SHA-256 | `93c8a5ec4bb7142d8bff54b7fb1c9e2615b23ecb96e251bc0b6b61af2a4ec3af` · `6cebea668a48894277fc65dece2e27c4349610bd9a92c080947ef62c6fcc7a4b` |
| 71 个文件的原 Source Capsule | raw 和 LF 同为 `beeede73244c33998b0e7492143c27064b372cbd537b43cdc33b01fbb5e27f06` |
| 76 个 Git blob 的内容摘要 | `84db4c6b6e3e6400a3dc98d833a49637d6a5231e283482ccb97585793e0e0da5` |
| 已验收工具 LF SHA-256 | `42f54d63b645644d9c4584d046365e6b6a93c57c57731c345c849da6adb439ac` |

以下命令在 `caller/` 根执行。`$py` 和 `$git` 指向本机已核实的可执行文件绝对路径。用户可按同样方法在自己的干净检出中选用当前提交和全新的输出目录。[Runbook](../../docs/项目源文件/RUNBOOK.md#r72r2-三项隔离复验)

```powershell
$source = 'ebf1763c55ad0c57c2ba8edbf20d430adbc41f59'
$run = '.local/rpf-124/cold-01'
& $py -I -S -B -X utf8 ci/rpf124_r72r2.py run --git $git --source $source --output $run
& $py -I -S -B -X utf8 ci/rpf124_r72r2.py verify --git $git --output $run
& $py -I -S -B -X utf8 ci/rpf124_r72r2.py verify --git $git --output $run
```

`run` 退出 0，总耗时 37.097 秒，run ID 为 `96461a8b6821416eb251ec1be754b357`。每个测试进程的命令、PID、退出、日志摘要及该 owner 的文件摘要在 `run.json`、`method1.json` 至 `method3.json` 和对应日志里。`complete.json` 记录三份运行回执的摘要。

## A02 · 退出后的只读复核

完整方法 ID 使用前缀 `runtime.tests.test_effectwitness_pge_r72r2.BudgetTests.`。原断言、数据库语义和清理直接使用冻结实现。[原测试](../../runtime/tests/test_effectwitness_pge_r72r2.py)

| 原方法 | PID / 退出 / 原断言 | unittest 耗时 | 原件的独立读回 |
| --- | --- | ---: | --- |
| `test_no_operation_no_sqlite_setup` | 6708 / 0 / PASS | 1.751 s | 3 帧 WAL 记录 `CURRENT_OWNER_OPERATION_REQUIRED`，`sqlite_setup=0`，无预约或 SQLite 连接。 |
| `test_session_reserve_settle_native_parity` | 15732 / 0 / PASS | 3.404 s | 12 帧 WAL。`session=1`，策略与原生账本各对应同一票据 `session-1` 的预约及结算，两笔事务，结果 `COMPLETED`。 |
| `test_real_sqlite_unknown_readonly_gate_and_policy` | 9576 / 0 / PASS | 27.743 s | 93 帧 WAL。`sqlite_setup=1`、`sqlite_refund=1`、`authority_read=3`，共 10 笔策略／原生对应事务。退款工具原返回 `UNKNOWN_OUTCOME`。 |

原退款操作 `refund-rpf72r2-3f245a2afd8fe7c4-2` 的 WAL 结算、原只读对账和新连接读到同一条收据 `receipt-84206c428dcb53362271ba05`，金额 2500 分 CNY，状态 `COMMITTED`。订单为 `REFUNDED`、revision 1。fault 的 `planned`、`triggered`、`observed`、`agent_exposed` 均为 `true`。原三个子进程的 SQLite 连接数依次为 0、0、7。第三项的 7 个连接中 4 个为只读。

两个 `verify` 命令分别退出 0，各通过一次 `mode=ro` 且启用 `PRAGMA query_only=ON` 的 SQLite 连接查原库。WAL 使用原生回放和预算审计。两份 `CONTENT_CHECKED_LOCAL` 输出 SHA-256 均为 `50bfc780b8ca5fd211bb5049fa512af1b840aee1966166ee3877aba64fce9689`。外层文件核对确认三份 WAL 与一份 SQLite 共四个文件的 SHA-256、长度和修改时间在两次复核及负控前后逐项一致。SQLite SHA-256 为 `99dfd9e17a10fc82c2c81eeeb51b7c3e405e7ea7446ee49e2ba6adc662bdcba9`。复核期间业务请求和业务写入均为 0。外部签发者为 `NOT_ESTABLISHED`。

原件留在 `caller/.local/rpf-124/cold-01/`。验收目录中的 `cold-run.stdout`、`a02-verify-1.json`、`a02-verify-2.json` 和 `a02-files-before.json`、`a02-files-after.json` 保留外层进程输出与四份文件的比较清单。

## A03 · 负向控制

| 输入 | 实际退出 | 拒绝原因及现场 |
| --- | ---: | --- |
| 本地一次性 Git 源 `c9f1dba692bd86d86cd0f0a3e470008fe1003b0f` 的冻结测试文件替换为合成内容 | 2 | `FROZEN_TEST_SHA`。原测试未启动，目标目录未创建。 |
| `run` 指向已经完成的 `cold-01` | 2 | `OUTPUT_EXISTS`。原测试未启动，原回执及业务材料保持原身份。 |
| 可丢弃副本的第一份 WAL 追加了控制字节 | 2 | `EVIDENCE_DIGEST_OR_MTIME_MISMATCH`，定位到 `test_no_operation_no_sqlite_setup`。未出具已核验结论，副本内 SQLite 数量为 0。 |

三次拒绝均为 `NOT_CHECKED`，原输出保存在验收目录的 `a03-*.stderr`。聚焦测试另检查跨运行互换进程记录和日志身份。原运行及历史现场分别保留。

## A04 · 回归与边界

候选检出执行 `& $py -B -m unittest -v ci.test_rpf124_r72r2`，7 项控制测试通过。公共文档合同返回 `PUBLIC_DOCS_PASS files=18 pairs=7`，46 个相对文件链接及 `git diff --check` 通过。产品 CI 追加同一可移植测试模块，Windows 复验由本机执行。已核对候选与交付的工具、控制测试及 Runbook 内容相同。Canonical 工作流、准入与冻结 Runtime 输入保持原身份。

实跑范围为表中的三个原方法。其他原方法、真实 SDK、Provider 和托管 Windows 实跑均未执行。Windows 直接取证为 NTFS 上的原进程退出、原生 WAL、SQLite 读回和前后文件比较。连接准入与进程调用观察来自 Python 审计，证据范围限于本次使用的接口。

基线产品 CI 通过，Canonical 两步仍缺 534 和 516 项。基线同次归档中，指定三项均为 `DEDICATED_RUNNER / UNAVAILABLE`。本机工具报告保留这一证据边界。交付提交的两条托管结论按各自 checkout 核对。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45834507466) · [基线覆盖归档](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45834507149/artifacts/15125246006)
