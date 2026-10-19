# RPF-53 rev-4 执行结果

**Plan ID:** `RPF-53`
**Plan Revision:** `rev-4`
**Status:** `PARTIAL`
**执行日期：** 2026-10-19
**仓库：** `D:\CS\runproof`
**基线：** `28f301916772ff7f6314b18fa1154e8aa22a3958`
**分支：** `codex/rpf-53-rev4-sdk-report-identity-live-closeout`

## 结论

Attempt-02 通过了真实 Pydantic AI SDK Fixture 与三方 PID 验收，目标测试、完整隔离 Runtime、七个历史 Witness 锚、Reviewed Artifacts、Public Docs 和差异空白检查均通过。唯一获准的真实 DeepSeek + Java/H2 Scenario 已执行一次，未重试；Provider 正常回了两轮，但 Agent 的配置创建参数被业务合同拒绝，未发出配置 POST，未形成 v1/v2 效果，也没有签发 Live Evidence。

另外，执行实现把 Java 指向既有 `.local/rpf-51-rev4/...` 中的固定 JAR，而 rev-4 Phase 3 要求在本轮 `.local/rpf-53-rev4/**` 内使用 task-owned 固定副本。该执行路径偏差降低了本次 Live 结果的验收资格。JAR 与 manifest 的 hash 在运行后仍与 Plan 固定值一致；未修改旧源仓库或旧 JAR。源码已在 Attempt-02 PASS 后冻结，本轮未再改源码；不在本 Plan 内补做或重试。

## Acceptance

| Gate | 结果 | 证据与说明 |
|---|---|---|
| A-01 来源与保护 | `PASS` | 仓库根、基线、分支、origin 和 `origin/main` 身份匹配；固定 SDK/JAR/manifest hash 匹配；`docs/reviews/` 未读取或触碰。task-owned JAR 副本缺失作为 Phase 3 执行偏差单列，详见“偏差与边界”。 |
| A-02 报告/PID 安全合同 | `PASS` | `runtime.tests.test_effectwitness_config_live`：32 PASS。逐字段报告、Popen/ready/report PID、跨 run 和字段负向检查通过。 |
| A-03 真实 SDK Fixture | `PASS` | 新 Attempt-02 完整通过：4 completions、3 SDK-origin calls、3 个唯一 Tool Return、回注位置 `[2,3,4]`；Provider/Java/业务 HTTP 均为 0；子进程、Host、端口及外联检查通过。 |
| A-04 真实 Provider | `PARTIAL` | 一次 Trial 已消费；2 次 HTTPS 请求、1,121 tokens；所有请求、token、费用和 SDK tools 均在预算内，零自动重试。Agent 创建参数被 `CREATE_ARGUMENTS_REJECTED` 拒绝，未完成冻结工具链。 |
| A-05 独立 HTTP Effect | `INCONCLUSIVE` | Java/H2 ready；只观察到初始 current `GET 404`、初始 history `GET 200`、`inspect_config GET 404`，无业务 POST。v1/v2、最终 history/list 均未证明。 |
| A-06 新 Live Evidence | `NOT_RUN` | 真实效果不成立；`config-live-evidence.json` 不存在，未制造成功证书或离线 PASS。 |
| A-07 回归/预算/安全 | `PASS` | 32 定向 PASS；可信基线加六个白名单源文件的隔离快照完整 Runtime：286 PASS、2 Docker SKIPPED、0 failures/errors；七历史锚、Reviewed/Public Docs、diff check、预算与清理检查通过。 |
| A-08 Git/唯一 TASK_RESULT | `PASS` | 本文件为唯一 rev-4 TASK_RESULT；仅白名单源码与 rev-4 新结果文件进入 focused commit，普通 push 到既定安全分支，并以 fresh `ls-remote` 核验。Push SHA 在本次执行回执中报告；未建 PR、未合并、未发布或部署。 |

## Fixture 诊断

| Attempt | Run ID | Popen / Host ready / SDK report PID | 结果 |
|---|---|---|---|
| 01 | `rpf53-diag-658e1177bde04c53` | `30644 / 7832 / 7832` | `FAIL`。只有 Popen 与另外两个 PID 不等；发现 `Scripts/python.exe` 是启动包装器。SDK 完成 4/3/3，零 Provider、Java、业务 HTTP；清理通过。 |
| 02 | `rpf53-diag-c73a2b3c24bb4749` | `13508 / 13508 / 13508` | `PASS`。直接 CPython 3.12.13 SHA-256 `e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f`；launcher SHA-256 `74e020321eb8f828f0c2cfe865082fcf94aa6e7cf488e8a744d89b9282eaeb83`。 |

Attempt-02 使用 `pydantic-ai-slim==2.57.0`、`openai==3.35.1`。Pydantic RECORD 444 entries / 0 mismatches；OpenAI RECORD 2,000 entries / 0 mismatches；SDK 主源码 SHA-256 `70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa`。报告 `COMPLETED`、exit 0，usage 为 `pydantic_ai.usage.RunUsage`，guard denials 为空，标准输出/错误不含密钥或最终模型文本。Runtime source SHA-256：`ab1c7aa371bc50bd2a9bde04268d739e8ce046d29e9c2c30041324cd12fb5840`。

## 唯一真实 Scenario

- Run ID：`rpf53-live-b5962bfebce24162`；不可覆盖 marker SHA-256：`04c73fbee5f0f2520044d227477b105deab5c5b7bb06e19a6a2a700e38578d59`。
- Provider 返回 model alias `deepseek-flash`。两轮 response ID 分别为 `a7b2e11d-0118-465e-b5db-dfa6361c2580` 与 `451df266-1fbc-4cb1-a227-2fd955a376d5`；usage 分别为 508、613 tokens。成本上界估算为 `¥0.006678`，不是账户实际扣款。两轮均为 `DeepSeek-HTTPS-no-retry`。官方文档说明 `deepseek-flash` 当前服务于 DeepSeek-V4.1-Flash-1017，Chat Completions 示例也以 `deepseek-flash` 回传 model 字段；本次 alias 符合冻结 verifier。来源：[Agent integrations](https://api-docs.deepseek.com/quick_start/agent_integrations/)、[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)。
- 第一轮 SDK `inspect_config` 调用收到 `ABSENT`，其 Tool Return 在第二轮请求中回注。随后一次创建尝试被确定性参数合同以 `CREATE_ARGUMENTS_REJECTED`（domain `AGENT`）拒绝；拒绝发生在业务 POST 前。未保存被拒绝的原始参数或自由 Provider 文本。未证明业务违规；Oracle 为 `INCONCLUSIVE`，`business_violation=NOT_PROVEN`、`agent_failure=NOT_PROVEN`。
- Java PID 与 listener PID 均为 `11504`，随机 loopback port `4631`，health `200/UP`；SDK child PID `18912`。Scenario 结束后 `cleanup_ok=true`、Host closed、listener closed、SDK/Java 均停止且无外联；进程退出码记录为 1。事后只读核验确认 PID 不存在、port 不监听。
- 运行后只读核验：JAR SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`，manifest SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`，均与 Plan 固定值一致。
- `live-summary.json` 原始 SHA-256 `45ec8c9c71f5c5d1778d392045f1ccce312fd8cba58d78d146bbf8d0affb1296` 中 health detail 带本地绝对路径；已在新 summary 中只将该字段替换为 `[REDACTED_LOCAL_PATH]`。脱敏后 SHA-256 `43fb863a39715f67f0dcff03ff84e63dbf1f0772c39c5d5cec8ae73cd6a61c33`，复查无残余绝对路径。

## 验证记录

- 隔离 Runtime 快照基于可信 HEAD `28f301916772ff7f6314b18fa1154e8aa22a3958`，叠加六个白名单源文件；快照与工作树源文件 SHA 匹配。
- 完整命令：`python -B -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v`。286 PASS；仅 `test_docker_integration`、`test_rpf05_runtime` 因 Docker provider 不可用而 SKIPPED。
- 七个历史锚均 `VERIFIED_ANCHORED`：RPF-43 `witness_verify` `ff4870c3…0b43391e`；RPF-44 `witness_verify` `21b5ded6…3f4f8873`；RPF-48 `target_evidence` `c00eb35f…732af4a2`；RPF-49 `target_recovery` `04ac629b…c7d4bc9b`；RPF-50 `violation_witness` `b8f288db…82f5ef4a`；RPF-51 rev-4 `config_http_witness` `c569bd62…29df363d`；RPF-52 rev-3 `config_target_verify` `2bbc002e…9437eb27`。
- `runtime/verify-reviewed-artifacts.py` PASS；`ci/verify-public-docs.py` PASS（18 files / 7 pairs）；`git diff --check` PASS。

## 偏差与边界

`spikes/rpf-53/probe.py` 的 `SOURCE_JAR` 指向预存的 `.local/rpf-51-rev4/upstream-config-center/config-center-server/target/config-center-server-1.0.0.jar`，Scenario 将该路径直接传给 `java -jar`。rev-4 Phase 3 要求在 `.local/rpf-53-rev4/**` 使用 task-owned 固定副本。该副本步骤没有发生；因此即便 JAR 本身 hash 匹配、只观察到读请求，本次真实 HTTP Scenario 也不作为 A-05/A-06 成功验收。此发现不追溯改写 Fixture 或 Provider 观察，不追加请求，不改冻结源码。

## Git 与保护状态

- 仅六个授权源文件：`runtime/runproof_runtime/effectwitness/config_live_contracts.py`、`config_live_external.py`、`config_live_runtime.py`、`config_live_verify.py`、`runtime/tests/test_effectwitness_config_live.py`、`spikes/rpf-53/probe.py`；以及新增 `spikes/rpf-53/rev-4/{sdk-fixture-diagnostic.json,live-summary.json,RESULT.md}`。
- 既有 `origin/main` 为 `bda0cd49e50e3181f604324e94877a24b9885334`，未变化。push 前 rev-4 远端分支不存在。`release-gate.yml` 的 push 触发仅限 `main`；本次仅向安全功能分支 push。
- `docs/reviews/` 保持原有未跟踪状态，未读取、枚举、修改、暂存或提交；旧 rev-1/2/3 结果、旧 `.local/rpf-53*` 与 Project State 未改。
- 未执行 PR、merge、release、publish 或 deploy；`.local/rpf-53-rev4/**` 的场景及测试产物为 ignored task-local 数据，不提交。
