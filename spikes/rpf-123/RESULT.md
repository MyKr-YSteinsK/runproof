# RPF-123 rev-1 · R72r2 三项隔离复验

2026-11-26。Windows 本机三个指定原方法各执行一次，均通过。独立进程复核了保留的原生 WAL 和合成退款 SQLite。结果用于评估专用运行器候选。[任务正文](https://github.com/MyKr-YSteinsK/runproof/issues/9)

## A01 · 归档、源码与现场

实际开工基线为本地与远端一致的 `main@3aff378241909beb4fcc623c1e07c8bb35c8709f`。Canonical run `45822843181` attempt `1` 的 checkout 日志与该提交一致。

读取 Actions artifact `15118937253`。下载的 ZIP 为 23,192 字节，SHA-256 为 `d972f28fdfb372bc4f5517dedb38aacc2a3ce20a5854c6d18f2c578a1c698425`，与元数据一致。唯一归档成员 `rpf89-coverage-45822843181-1.json` 绑定相同 run、attempt、commit，SHA-256 为 `8b742ed64836744f56fc1428ecd7eaa2508b2dc8213315dd64d457bf545af8b2`。1,232 个必需方法中 PASS 711、SKIP 5、UNAVAILABLE 516。专用运行器缺口 394 个，其中 R72r2 27 个、R72r3 33 个。三个同名方法均在 R72 的 18 项补认名单中。R72r2 的指定三项在原归档和有效口径下均为 required、`DEDICATED_RUNNER / UNAVAILABLE`。[固定归档](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45822843181/artifacts/15118937253) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45822843181)

| 身份 | 核对值 |
| --- | --- |
| 冻结 R72r2 测试 LF SHA-256 | `93c8a5ec4bb7142d8bff54b7fb1c9e2615b23ecb96e251bc0b6b61af2a4ec3af`，与矩阵相同 |
| 冻结矩阵 LF SHA-256 | `6cebea668a48894277fc65dece2e27c4349610bd9a92c080947ef62c6fcc7a4b` |
| 原 Source Capsule | 71 个文件，raw 与 LF 摘要均为 `beeede73244c33998b0e7492143c27064b372cbd537b43cdc33b01fbb5e27f06` |
| 已安装解释器 | CPython 3.14.6 x64，SQLite 3.50.4，可执行文件 SHA-256 `03168c01b7b7491423350e82c26fee71f35b43694d1319d3c668bda6903a0c38` |

Windows x64 build 26200，D 盘 NTFS，PowerShell 7.6.9。新的 detached Git 检出位于 `.local/rpf-123/a1810987f3/source/`。检出初始状态为空且无 `.local`。核对原源码实际解析的 `.local/rpf-72-rev-2/tests/`，其根、父路径和模块根均绑定新检出，现场通过 reparse 与文件链接检查。预检逐项核对 76 份文件的 Git blob 与原字节，含 Source Capsule、冻结矩阵和包入口。所需 SDK 与 JAR 信息来自仓库内固定元数据。逐文件摘要、解释器绝对路径及 owner 根见本机 `evidence/preflight.json` 与进程回执。[原测试](../../runtime/tests/test_effectwitness_pge_r72r2.py) · [冻结矩阵](../../ci/runtime-contract-test-matrix.json)

## A02 · 原测试与独立读回

三个完整 ID 均以下列前缀开始。

```text
runtime.tests.test_effectwitness_pge_r72r2.BudgetTests.
```

每次在独立 CPython 进程按完整 ID 由原生 `unittest` 加载一个原方法。原断言和清理逻辑直接执行。

| 原方法 | Windows PID | 退出 / 状态 | unittest 耗时 | 原断言与事后只读证据 |
| --- | ---: | --- | ---: | --- |
| `test_no_operation_no_sqlite_setup` | 40248 | 0 / PASS | 1.583 s | 原断言确认 `CURRENT_OWNER_OPERATION_REQUIRED`。复查 3 帧原生 WAL 得到同一拒绝原因、`sqlite_setup=0`，无预约票据或 SQLite 目标。 |
| `test_session_reserve_settle_native_parity` | 25812 | 0 / PASS | 4.160 s | 原断言确认一次会话及两笔策略／原生对应事务。复查 12 帧 WAL 得到 `session=1`、`session-1=COMPLETED`，两笔事务为同一票据的预约和结算。 |
| `test_real_sqlite_unknown_readonly_gate_and_policy` | 18336 | 0 / PASS | 51.883 s | 原断言确认 `UNKNOWN_OUTCOME` 后只读对账、单条收据、2500 分和原生清理。复查 93 帧 WAL 得到 `sqlite_setup=1`、`sqlite_refund=1`、`authority_read=3` 和 10 笔策略／原生对应事务。 |

第三项的 `TOOL_RETURN` 与 `FAULT` 原记录确认工具响应为 `UNKNOWN_OUTCOME`，故障的 planned、triggered、observed、agent_exposed 均为 true。原清理结束后保留一个 SQLite 目标。独立进程 PID 38744 使用 `mode=ro` 和 `PRAGMA query_only=ON` 直接读取该库。订单为 `REFUNDED`、revision 1，原 operation `refund-rpf72r2-715ab2fd562121af-2` 只有一条收据 `receipt-06b8ee3c829715d82d770195`，状态 `COMMITTED`、金额 2500 分。它与原只读对账返回的收据及 WAL 结算匹配。三份 WAL 与 SQLite 共四份文件的字节摘要、长度和修改时间在复核前后逐项一致。SQLite 的 SHA-256 为 `115433a6845657939aab9d352ab693d47548ac021ace6c9be986102a968fa797`。

测试子进程的审计把文件写入限定在新 owner 或其创建所需的父目录，且只允许第三项使用一个 `orders.sqlite3`。前两项 SQLite 连接为 0，第三项观察到 3 个普通连接和 4 个只读连接，事后复核另有 1 个只读连接。原清理按其合同保留数据库。测试期与复核期的网络、SDK 或子进程准入事件均为 0，三个原生 WAL 的真实 Provider 预约、发送和 token 均为 0。合成会话与退款预约按上表单列。

### 复现与证据位置

本机任务根为 `.local/rpf-123/a1810987f3/`。保留的 `run-pilot.ps1` 与 `pilot.py` 位于该根。另建新现场时，先按相同 Git SHA 生成无换行转换的 `source/`，用固定 Actions ZIP 和元数据完成预检，从 PowerShell 7.2+ 使用已核实的 `$py`、`$git` 绝对路径。

```powershell
& (Join-Path $task 'run-pilot.ps1') -Phase preflight -PythonExe $py -GitExe $git
& (Join-Path $task 'run-pilot.ps1') -Phase tests -PythonExe $py -GitExe $git
& (Join-Path $task 'run-pilot.ps1') -Phase recheck -PythonExe $py -GitExe $git
```

预检、三项测试和只读复核均退出 0。实际测试参数为 `-I -S -B -X utf8 pilot.py run <完整方法 ID>`。各进程原退出、参数、起始时刻和日志摘要见 `evidence/*-process.json`。逐方法输出见 `method1.log` 至 `method3.log`，独立业务事实与 WAL 摘要见 `evidence/recheck.json`。

## A03–A04 · 路线判断与交付边界

建议下一轮只评审扩大到其他具有同样隔离条件的 R72r2 方法。扩大前仍需逐项核对冻结源码、可保留的读回证据、owner 隔离和真实资源权限。若需要旧 owner、未知预算、受限材料、真实 SDK 或额外权限，停在对应预检项。此次实际执行范围是表内三项。

复验后核对了 76 份源码及矩阵文件和 ZIP 摘要。公共文档合同与 `git diff --check` 通过。三项本机 PASS 独立记录，Canonical 中原三项仍为 `UNAVAILABLE`。基线产品 CI 通过，Canonical 两步 required coverage 分别缺 534 项和 516 项。交付 SHA 的 hosted 结论按实际 checkout 单独核对。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45822843098) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45822843181)
