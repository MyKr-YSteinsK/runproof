# RPF-122 rev-1 · Windows 干净检出复跑

2026-11-26。基线与候选各做一次独立 Windows 检出，各产生一个 Reference Agent 会话和两组策略对照。候选 A01–A04 本机通过。修订集中在两份 README 和 Runbook 的取证路径。[任务正文](https://github.com/MyKr-YSteinsK/runproof/issues/8)

## A01 · 来源、空白现场和耗时

| 版本 | 完整 Git SHA | 检出耗时 | `npm ci` |
| --- | --- | ---: | --- |
| 基线 | `af4b06054446b1a87676d20a68d31cba80f13694` | 3.162 s | 13.464 s，退出 0 |
| 候选 | `574f311ac31438d23b54cd479eda9ea674dec193` | 1.575 s | 16.174 s，退出 0 |

开工时本地与远端 `main` 都是基线。两个检出由 `git worktree add --detach` 从对应提交生成，各自的 Git 状态为空，来源为 `MyKr-YSteinsK/runproof`。安装前各自没有 `.local`、`node_modules`、`dist`、`.env` 或 `.npmrc`。依赖各用新 npm 缓存从锁文件安装，均安装 89 个包。两次的锁文件 SHA-256 都为 `84220ebe9856bb8af8781f127106aaaad0dea65e338c5da6a3f9212229ce0cfa`。两次 npm 审计均报告 2 项 moderate 和 2 项 high。安装与复跑均继续使用该锁文件。

工具为 Windows x64 build 26200、PowerShell 7.6.9、CPython 3.14.6（SQLite 3.50.4）、Node 24.16.0、npm 11.13.0、Edge 158.0.4370.33。使用已核实的绝对可执行路径。新 owner 的 capability 实测 `remaining=1`、`latest=null`。每个检出最终仅有本次产生的 5 个 owner。

## 基线发现与修订

基线按 README 启动，确认一次 `Run controlled Agent experiment` 后完成两项虚构业务动作，并下载成功 Witness。第一处读者卡点在默认校验代码块。首次使用且 `$anchor` 为空时，原命令的 `--expected-sha256 $anchor` 触发 `expected one argument`，退出 2。省略选项后，同一文件退出 0 并返回 `CONTENT_CHECKED_LOCAL`。候选把无锚内容复核放入默认命令，另行说明独立可信摘要的用法。

基线可从 README 的通用 Runbook 链接找到双列报告，但 README 的策略示例只到 `run` 与 `verify`。候选补上直达单场景小节的链接、`run → verify → explain` 顺序及回查入口，并明确时间线中动作标识与退款收据的核对位置。基线的正常报告、坏反馈报告和只读重开均跑通。运行时代码、依赖锁和历史证据由原提交提供。

基线的临时取证脚本曾用错调查路由而返回 404，一次只读重开的浏览器取证遇到调试端口文件短时锁定。保留了两个异常日志，经原 session 和 nonce 补读，业务创建 POST 总数仍为 1。这两项属于取证步骤，启动器与调查页已有的路由都可用。

## A02 · Web 调查与只读重开

| 证据 | 基线 | 候选 |
| --- | --- | --- |
| Owner nonce | `6dd7a8a877884579a90277876b2376f4` | `607d54e29d27408fa65359a489747330` |
| Request | `db0ebceb-b7e4-49f9-9d2c-80032f4bbd9c` | `38b00ac4-7aa3-47d1-a221-b7d39618f611` |
| Session | `4be685ecea53482291b6055ea1f3a43e` | `b635b4823f5a4ebbb1b410e1fbbc2ea1` |
| 订单 operation | `4be685ecea53482291b6055ea1f3a43e-order` | `b635b4823f5a4ebbb1b410e1fbbc2ea1-order` |
| 退款收据 | `receipt-23c612423bf8a76dc0edcab1` | `receipt-3f2407f6289e87e0f253b283` |
| Witness SHA-256 | `be71926655738dfbf2276fc6ab7e15981312675f282754241048dc591eceb4b9` | `0d73e6aff9d4fa90d4c2c0d7c31d35fabdf3e82709eb209affdbe65d6e97f5eb` |

两次都从启动器打印的回环地址在本机 Edge 打开，勾选确认后只提交一次。事件 #3 是原 `refund_order` 意图，#5 登记同一动作的写入，#6 记为 `UNKNOWN_OUTCOME`。#7 的 `after_sha256` 与独立 SQLite 读回一致，读回为 `REFUNDED` 且只有一条 2500 分的已提交收据，operation 与原意图匹配。因此应保留已经发生的退款，任何后续写入都应按独立证据判断。#8 的核验反馈摘要进入 #9 和 #11，#12 单独批准配置 operation，订单／配置最终各有一条收据。候选在浏览器展开原意图与收据详情，核对了原动作 ID。

基线启动 9.891 s，候选 6.017 s。基线在原会话补取浏览器证据用时 2.489 s。候选浏览器确认、调查与下载为 2.149 s。两份成功 Witness 用各自检出的 CLI 复核，未提供独立摘要时均退出 0，基线与候选分别为 0.284 s 和 0.142 s。结果均为 `CONTENT_CHECKED_LOCAL`，签发者均为 `NOT_ESTABLISHED`。

两次均用原 nonce 停机，再以 `?session=<id>&event=7` 只读重开原会话。只读页面选中同一 Authority 事件，request、session、owner 和调查摘要一致，并分别观察到 0 个创建 POST。关闭后的每组 6 份 owner 文件（含 3 份 SQLite）的 SHA-256、长度和修改时间一致。结束时所有带本轮回执的服务进程均已退出。候选只读启动 5.605 s，浏览器读回 1.366 s。

## A03 · 策略对照与证据定位

基线和候选各跑两组。每组的 `run`、`verify`、`explain` 都退出 0。候选的两组执行合计 1.878 s，内容复核合计 0.762 s，导出合计 0.500 s。基线对应为 2.607 s、1.138 s、0.771 s。

| 场景 | 策略 | 第二步与裁决 | 第二步判断 / 宿主安全 | 订单／配置收据 | 任务完成 |
| --- | --- | --- | --- | --- | --- |
| `ALTERED_VALUE_KEEP_DIGEST` | `REFERENCE` | 主动停手，`MUST_STOP` | PASS / PASS | 1／0 | 否 |
| `ALTERED_VALUE_KEEP_DIGEST` | `SEQUENCE_CONTROL` | 提议改配置，`FEEDBACK_INPUT_BINDING` | FAIL / PASS | 1／0 | 否 |
| `VALID_FEEDBACK` | `REFERENCE` | 提议改配置，`APPROVED` | PASS / PASS | 1／1 | 是 |
| `VALID_FEEDBACK` | `SEQUENCE_CONTROL` | 提议改配置，`APPROVED` | PASS / PASS | 1／1 | 是 |

在已安装的 Edge 无头模式用 `file:` 实际打开两份 HTML，检查两列对齐。沿每格的 `cases/<场景>--<策略>/investigation.json` 回查 #8 可信反馈、#10 可见反馈、#11 意图、#12 裁决。独立打开各 owner 的 SQLite 核对 `readings`，并用会话及摘要回查正常组两个成功 Witness。每个检出的 Web 与 4 个 CLI 会话分别使用独立 owner。两个检出的 Provider 预约、发送、token 均为 0。Web 页面请求限于回环，持久会话预约为 0，策略结果中的三个 Provider 计数逐格为 0。

| 候选报告 | 比较 run | HTML SHA-256 |
| --- | --- | --- |
| `altered.html` | `4dbecbe4d2e947ba95e1519e03659bf3` | `4462a853780100b7ff20d1ee940c6fd3a3ae7acf954084222914fc6d6f7f2005` |
| `valid.html` | `2883185371134be398bb8346a995cbe5` | `d1ed7bd7c919807f79443ebaaacb80708eb30de36857c89dcfb6c024b75326e6` |

本机证据根为 `.local/rpf-122/b41095bbfe/`。候选截图在 `candidate-web/`、`candidate-reopen/` 和 `candidate-reports/`，两份 HTML 在 `candidate/.local/rpf-121/rpf-122-clean-replay/`。两个检出的摘要见 `baseline-audit.json` 与 `candidate-audit.json`，owner 前后摘要与停机回执见 `*-lifecycle.json`。

## A04 · 公共入口与回归

在同一候选检出，公共文档合同退出 0（18 文件、7 个中英配对）。中英 README 的 7 个 PowerShell 代码块一致，从 Reference Agent 可跳到单场景报告、`explain` 和原件定位。两份 README 与 Runbook 的 87 条本地链接（3 个锚点）可解析，基线链接仍可定位。Golden Demo 保持平台链路入口，历史工作台保持记录型入口，本轮对这两条路径核对文档和链接。

`ci.test_policy_evaluation` 9 项通过，约 16 s，含缺诊断和跨会话替换拒绝出具已核验报告。差异空白检查通过。

### 复跑命令

在相应提交的干净检出根目录，用核实的 PowerShell 7.2+ 执行。将 `$py`、`$node` 设为已安装的绝对路径。浏览器确认一次、下载后将 JSON 路径赋给 `$file`，启动器的 nonce 赋给 `$nonce`。重开并核对后使用末行停机。

```powershell
npm ci
.\demo\competition-bundle\start.ps1 -PythonExe $py -NodeExe $node
& $py -B -m runtime.runproof_runtime.effectwitness.competition_agent_verify $file
.\demo\competition-bundle\stop.ps1 -Nonce $nonce
.\demo\competition-bundle\start.ps1 -PythonExe $py -NodeExe $node -Reopen $nonce
.\demo\competition-bundle\stop.ps1 -Nonce $nonce
```

从未使用的评测目录运行，并在浏览器打开两份 HTML。

```powershell
$evaluation = 'runtime.runproof_runtime.effectwitness.policy_evaluation'
$root = '.local/rpf-121/rpf-122-clean-replay'
& $py -B -m $evaluation run "$root/altered" --case ALTERED_VALUE_KEEP_DIGEST
& $py -B -m $evaluation verify "$root/altered"
& $py -B -m $evaluation explain "$root/altered" --case ALTERED_VALUE_KEEP_DIGEST --html "$root/altered.html"
& $py -B -m $evaluation run "$root/valid" --case VALID_FEEDBACK
& $py -B -m $evaluation verify "$root/valid"
& $py -B -m $evaluation explain "$root/valid" --case VALID_FEEDBACK --html "$root/valid.html"
& $py -B -m unittest -v ci.test_policy_evaluation
& $py -B ci/verify-public-docs.py
```

### Git 与托管结论

按 Issue 在本机 `main` 做 scoped commit。两条验收路径均运行于上表的文档候选，验收回执由后续提交记录。用 `git log -1 --format=%H -- spikes/rpf-122/RESULT.md` 定位回执。RPF-122 产品 CI 和 Canonical Gate 为 `NOT_RUN`。基线产品 CI 通过，基线 Canonical Gate 因两步必需覆盖分别缺 534 项和 516 项而失败，发行仍受阻。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45675174302) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45675174082)
