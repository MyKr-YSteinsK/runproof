# TASK_RESULT｜RPF-51 rev-4

**Plan ID**：RPF-51

**Plan Revision**：rev-4

**Status**：Complete

## 身份与改动范围

- 仓库：`MyKr-YSteinsK/runproof`，remote `origin=https://github.com/MyKr-YSteinsK/runproof.git`。
- 唯一父提交：`1c4c3a382808a98613b1e659dfcddbc1d5ebc67e`；工作分支：`codex/rpf-51-rev4-real-jdk-http-effect`。
- 执行前远端 `main` 为 `bda0cd49e50e3181f604324e94877a24b9885334`，rev-4 远端分支不存在。最终 main 与分支 push SHA 在本次聊天回执中独立核验；本文件不记录自身所在提交 SHA。
- 外部只读来源：`MyKr-YSteinsK/config-center@0258b9cef02ea74a40989d035c79256c776409c0`。源码 manifest 为 110 files / 393,800 bytes，SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`；JAR 为 66,981,576 bytes，SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。仅从 rev-3 的精确 task-local 副本读取 manifest 列出的源码文件与 JAR，并在 rev-4 副本中重新逐项验 hash。
- 修改的既有文件仅为：`spikes/rpf-51/probe.py`、`runtime/runproof_runtime/effectwitness/config_http_contracts.py`、`runtime/tests/test_effectwitness_config_http.py`。新建文件仅在 rev-4 白名单：本 README、此 TASK_RESULT、`readiness-diagnostic.json`、`config-http-witness.json`。
- 所有执行副本、日志、marker、合同和原始 HTTP 观察留在忽略目录 `.local/rpf-51-rev4/`。结束时该目录有 123 个文件、67,434,973 bytes；保留用于复核。两个 task-owned Java 进程均已退出，端口均已关闭。
- rev-1、rev-2、rev-3 的结果、marker、代码及历史证据未改写；`docs/reviews/` 未读取或枚举，Git 状态中的既有 `?? docs/reviews/` 保持未跟踪。

## 实施与真实诊断

Runner 现在分别记录 Java launcher、解析出的 `java.home`、direct JDK executable 和版本，并以 direct executable 作为 `Popen` 的 `argv[0]`。Readiness 必须同时满足进程仍存活、精确 `127.0.0.1` 唯一监听 PID 等于 `Popen` PID、health GET 返回 HTTP 200 且 `status=UP`、请求后监听 PID 未变；诊断与业务运行都在 finally 中回收自身进程并复核端口关闭。诊断 attempt 上限为 2，每次各自使用新的不可覆盖目录、marker 和端口。

- Java launcher：`C:\Program Files\Common Files\Oracle\Java\javapath\java.EXE`
- `java.home`：`C:\Program Files\Java\jdk-17`
- `Popen` 使用的 direct JDK：`C:\Program Files\Java\jdk-17\bin\java.exe`，版本 `17.0.12`
- 实际运行时代码摘要：`1f9beab60264d614f7faecf37809d9fd366bd36e45f80523ce8551955bc2c3a2`
- Attempt 1 / diagnostic ID：`rpf51-diag-68abf6b99b73442e8392fdf80333496b`；端口 `3923`；Popen PID / 唯一 loopback listener PID / health 后 listener PID 均为 `7128`。
- 唯一一次匿名 `GET /actuator/health`：HTTP `200`、body `status=UP`；0 业务请求、0 Provider 请求、0 tokens、费用 `¥0`；外部连接列表为空。
- 诊断结束后进程已回收、端口关闭。Windows 受控 terminate 返回码为 `1`；该 Gate 以进程不存在和端口关闭判定生命周期，不以应用自然退出码为条件。
- `readiness-diagnostic.json`：4,692 bytes，SHA-256 `b98842e65a62a68355e426cb6411a486180604fbb4d30d3daef39c3ae68e0533`；诊断本地 result SHA-256 `7c5b0825aa2afeab0ca1383c48c1c2acf69ef96e39e24cc6102db9ef492ae32d`。仅启动 1 次；未启动 attempt 2。

## 唯一真实业务 Scenario

- Run ID：`rpf51-d00d9bf8fc7343b386c4ff5a45ad1d27`；独立业务端口 `7174`；Popen PID `32556`。应用名、环境名和配置 key 均为本轮随机合成值，与诊断隔离。
- `local` profile、内存 H2、直连 JDK 17；业务进程已回收，端口关闭，外部连接列表为空。受控终止返回码 `1`。
- 共 11 个业务 HTTP 请求，另有 1 个 readiness health GET；Provider 请求、tokens、费用均为 0。无盲目重试。

| 顺序 | 观察 | 真实 HTTP 结果 | 读回事实 |
|---|---|---|---|
| 1–2 | 初始 current / history | `404 / 200` | current 不存在，history 为空 |
| 3–5 | 错误 API key POST 与 current / history 复读 | `403 / 404 / 200` | 未授权写未改变状态，history 仍为空 |
| 6 | 创建 v1 | `200` | value=`rpf51-v1`，version=`1` |
| 7 | expectedVersion=1 更新 | `200` | value=`rpf51-v2`，version=`2` |
| 8 | 使用过期 expectedVersion=1 更新 | `409` | stale write 被拒绝 |
| 9–11 | final current / history / list | `200 / 200 / 200` | current 为 v2/version 2；history 版本 `[2, 1]`；list 仅含当前 version 2 |

Oracle outcome 为 `CONTRACT_SATISFIED_IN_RUN`，violated rules 与 evidence gaps 均为空。HTTP 原始观察为 7,580 bytes，SHA-256 `d8c30c7395c63c99a14ca14ef354289493c62eb4b0ee3758c84f8fd5e2855ece`。run result 为 921 bytes，SHA-256 `3f7dc40b7160e86d13e0320aa2e9dcb918b2223775e18d6fce88d9dc09969b35`。正式 Scenario 只启动 1 次。

## 真实 Witness 与独立离线验证

- 产物：`spikes/rpf-51/rev-4/config-http-witness.json`，13,609 bytes，SHA-256 `c569bd62a6691c84e8995359578fc4ff34f0ea417158a0c0893309c029df363d`。
- 服务停止后，在三个独立 Python 子进程中运行同一离线 verifier：正确外部锚返回 exit `0 / VERIFIED_ANCHORED`；缺失锚返回 exit `2 / UNANCHORED_INCONCLUSIVE`；错误锚返回 exit `3 / REJECTED ANCHOR_MISMATCH`。
- Witness 声明 `CONTROLLED_EXTERNAL_HTTP_SERVICE` 和 same-service GET trust；`issuer_authenticity=NOT_ESTABLISHED`，不声称数据库级独立认证或生产数据真实性。Target Agent 未执行，PGE 未参与。

## Acceptance Gates

| Gate | 结果 | 证据 |
|---|---|---|
| A-01 身份、保护与 Git 边界 | PASS | 精确父提交、remote、main 与新分支已核验；来源 manifest/JAR 全量 hash 匹配；tracked 改动限定在计划白名单；旧 rev-1～3 与 `docs/reviews/` 未触碰。 |
| A-02 最小修复与负控 | PASS | direct JDK、Popen/listener PID、健康返回、PID 重查、attempt 上限与安全重试门槛有确定性回归；rev-1/2/3 合同来源仍可验证，rev-4 仅新增一个精确父 SHA。 |
| A-03 真实只读诊断 | PASS | attempt 1 实测同一 JVM PID `7128`、loopback listener、health 200/UP、外连为空、进程停止与端口关闭；health GET=1，业务 HTTP=0。 |
| A-04 真实 HTTP Effect | PASS | 一次性 Scenario 11 个业务请求；未授权/过期版本写被拒；最终 current/history/list 读回 v2 与两条历史；独立 Oracle 满足。 |
| A-05 真实离线 Witness | PASS | 真实 Scenario 生成 Witness；独立 verifier 的正确/缺失/错误锚 exit 为 `0/2/3`。 |
| A-06 安全与负控 | PASS | API key 原文仅在 task 子进程环境中保存，由受限 loopback 请求用于授权 header；argv 只含 `${CONFIG_CENTER_API_KEY}` 字面量，adapter 不记录该 header，服务日志检查未发现 key。工具不跟随 redirect、不对不确定写重试；无生产凭证、外连、Provider 或 Agent 执行。 |
| A-07 验证、预算与资源闭环 | PASS（Docker 子集 SKIPPED） | Runtime 全量 227 tests 通过、2 项因 Docker provider 不可用跳过；Reviewed Artifacts、Public Docs、Golden Demo、`git diff --check` 通过；RPF-43/44/48/49/50 锚定历史验证通过；诊断 1 次、业务 1 次，服务/PID/端口均关闭。 |
| A-08 TASK_RESULT 与远端交付 | PASS | 本文件与 README 已收口；focused commit 普通 push 到本 Plan 新分支，远端 SHA 与 main 未变在最终聊天回执中独立核验；未建 PR、未合并、未发布、未部署。 |

## 回归记录与限制

- 定向 RPF-51 测试：27 tests PASS。Runtime 全量：227 tests PASS，2 个 Docker 子集 SKIPPED；未运行 Maven、未安装依赖、未调用 Provider/LLM。
- `python -B runtime/verify-reviewed-artifacts.py`：PASS；`python -B ci/verify-public-docs.py`：`PUBLIC_DOCS_PASS files=18 pairs=7`；`python -B demo/verify-golden-demo.py --root . --json`：PASS；`git diff --check`：PASS。
- RPF-43、RPF-44、RPF-48、RPF-49、RPF-50 各自的历史完整 SHA 锚验证最终均 PASS。RPF-49 第一次调用曾返回 anchor mismatch；独立计算的文件 SHA 与历史记录相同，随后原命令复核返回 `CONTENT_VERIFIED_ANCHORED`，没有改写历史文件。
- 保留的信任限制：本证据证明受控 HTTP 服务返回的业务状态与独立 Oracle 相符；不证明 config-center 的数据库级独立权威、issuer authenticity、生产真实性、Agent 自主漏洞发现或部署授权。`ELIGIBLE` 不等于已发布。
