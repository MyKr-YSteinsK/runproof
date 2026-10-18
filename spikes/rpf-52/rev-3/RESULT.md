# TASK_RESULT｜RPF-52 / rev-3

- **Status: Complete**
- **Plan:** `RPF-52-跨域SDK错误定位与三工具预检后真实HTTP补验收 / rev-3`
- **结果范围：** 固定 Pydantic AI SDK、scripted Fixture、一次 task-owned Java/H2 config-center HTTP Scenario、独立离线 Evidence 与 Plan 指定回归。

## 必要 Gate

| Gate | 状态 | 结果 |
|---|---|---|
| A-01 来源与保护 | PASS | 在 `D:\CS\runproof` 从精确 base `7b18f091151c505071a44529246c0dbde38648bf` 建立 `codex/rpf-52-rev3-sdk-diagnostics-and-fixture-recovery`。rev-1/rev-2 历史 marker、RESULT 与本地运行目录未修改；`docs/reviews/**` 未读取或触碰。白名单、index 与远端状态在提交前后核对。 |
| A-02 SDK_ERROR 结构化诊断 | PASS | child 报告按白名单 schema 解析；缺失、超长、重复 key、非法状态/字段均 fail-closed，SDK 错误阶段/类型/guard 信息与 Host 枚举首拒绝码得到脱敏保存。定向测试 27 项通过。 |
| A-03 真实 SDK 三工具零业务预检 | PASS | Attempt 1 准确记录失败；仅在有证据的 schema 兼容修复及测试通过后执行 Attempt 2。Attempt 2 使用固定 CPython 3.12.13、Pydantic AI 2.57.0、OpenAI 3.35.1，4 completions / 3 SDK-origin calls / 3 returns，回注身份与摘要一致；未启动 Java、无业务 HTTP、无 Provider/外连，子进程、Fixture Host 与端口均关闭。 |
| A-04 真实外部 HTTP Effect | PASS | 仅在 A-03 PASS 后创建一次新 marker。Java 17.0.12 的 task-owned H2 服务 health=200；SDK/Host 完成同一三工具合同，恰好 8 条业务 HTTP（含 2 POST），Authority 读回 v2/version 2 与 history `[2,1]`，Oracle=`CONTRACT_SATISFIED_IN_RUN`。 |
| A-05 独立离线 Evidence | PASS | 新 Evidence 正确外部 SHA exit 0、缺锚 exit 2、错锚 exit 3。四项内部重算摘要的篡改负控均被拒绝。来源与 Fixture 信任边界明确记录。 |
| A-06 安全与预算 | PASS | 诊断 2 次、正式业务 Scenario 1 次；4 completions、3 tools、8 业务 HTTP、1 health GET、约 20 秒；Provider requests/tokens/cost 均为 0。未发现外连；凭据未进入 argv、SDK child 或 Evidence，秘密扫描命中 0。所有本任务子进程、Host 与端口已关闭。 |
| A-07 回归与旧证据 | PASS（2 项 Docker SKIPPED） | 定向 27 项通过；隔离镜像中的全 Runtime 254 项通过、2 项因 Docker provider 不可用而 SKIPPED；Reviewed Artifacts、Public Docs、`git diff --check` 与 RPF-43/44/48/49/50/51 rev-4 锚验证通过。 |
| A-08 Git 与唯一回传 | PASS | 仅 Plan 白名单中的 5 个已修改文件与本目录 5 个允许新文件（含诊断脚本源码）进入 focused commit，并普通 push 到指定新 feature branch；没有 PR、main merge、release 或 deploy。最终远端 feature SHA 与 `main` 状态在本 TASK_RESULT 之外的交付回执中报告，避免结果文件自指最终 commit。 |

## 诊断与来源身份

| 阶段 | Run ID | Runtime source SHA-256 | 结果 | SDK / Host 摘要 |
|---|---|---|---|---|
| Fixture-only Attempt 1 | `rpf52-diag-36768477e5444361a6a2687d3201bbc5` | `ccc62a1e6301b62ab38077c6b6b874e66146393c3007516eaf061fca4f3750f2` | FAIL；0 completions/calls/returns | `stage=sdk_run`、`error_type=ModelHTTPError`、`guard_code=null`；Host 首拒绝码 `SDK_TOOL_SCHEMA_PARAMETERS`。无 Java、无业务 HTTP，清理通过。 |
| Fixture-only Attempt 2 | `rpf52-diag-3e08197ae7b24d9b9f2b73304f8640f6` | `c9db787e29442ab993bf92f7a007fc2c915e13a759a60d296787c7c3dd67af21` | PASS；4 completions / 3 calls / 3 returns | `SDK_COMPLETED`，无 guard denial、无 Host 首拒绝码。无 Java、无业务 HTTP，清理通过。 |
| 正式 Scenario | `rpf52-4178ef6f82644b4aa02a981de50a6168` | `61840fef44b5c39e0e27f98fd4c559e61b52aab5ec5c1c7f493ac4f93dff670d` | COMPLETE；Evidence 已生成并离线验证 | 固定 SDK 同上；3 SDK calls、4 completions；8 个业务请求、2 POST；0 Provider request/token/cost。 |

Attempt 1 的已证实根因是 Pydantic 为零参数工具生成的 JSON Schema 省略空 `required` 数组，而 Fixture Host 原先要求该字段。最小修复仅在 `properties={}` 时将省略的 `required` 按语义视为空列表；非空参数工具仍逐项严格核对必需字段、额外字段和 `additionalProperties=False`。

Attempt 2 PASS 后，摘要加载器检查暴露了 Runner 对失败 Attempt `sdk_tool_calls=null` 的汇总校验缺陷。正式 Scenario 前仅修改 `spikes/rpf-52/probe.py` 的结果门控校验，使其接受已记录的失败 Attempt 并要求最终 Attempt PASS。Preflight 记录唯一 source delta：`source_delta_files=["spikes/rpf-52/probe.py"]`，原因 `PROBE_DIAGNOSTIC_SUMMARY_VALIDATION_ONLY`。SDK child、Tool Host、Fixture Host、诊断脚本、合同、verifier 与测试均未在 Phase 1 PASS 后改动；因此没有消耗额外 SDK Attempt。正式 Scenario 使用新的冻结 source SHA `61840fef...`，没有把它冒充成诊断 Attempt 2 的源码身份。

固定来源身份复核通过：config-center commit `0258b9cef02ea74a40989d035c79256c776409c0`，110 files / 393,800 bytes，manifest SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`；JAR 66,981,576 bytes，SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。SDK RECORD 校验版本为 Pydantic AI 2.57.0 / OpenAI 3.35.1，记录文件 hash mismatch 均为 0。

## Scenario Evidence 与边界

- Evidence：`config-target-fixture-evidence.json`，19,042 bytes，SHA-256 `2bbc002e5a83dabc4aa9b9ddfea733532ef8b29f789181a19debb7ed9437eb27`。
- Preflight SHA-256：`8a1eaa9402889c189f4476e87905aeab28cdf30fd6601cca6b15718999d4c920`。Python 分别启动三个独立 verifier 子进程并读取实际 `returncode`：正确/缺失/错误锚分别为 `VERIFIED_ANCHORED`/exit 0、`UNANCHORED_NOT_PROVEN`/exit 2、`ANCHOR_MISMATCH`/exit 3。当前 PowerShell exec 展示层将非零值统一显示为 1，因此以上退出码以 Python 捕获到的子进程 `returncode` 为准。
- 业务 HTTP 顺序：initial current `GET 404/code 4041`；initial history `GET 200/code 0`；SDK inspect `GET 404/4041`；create 与 update 各 `POST 200/code 0`；final current/history/list 三个 `GET 200/code 0`。最终值 `rpf52-v2`、version `2`、history `[2,1]`；Oracle violations/gaps 均为空。
- 四项重新计算内部摘要的篡改控制均拒绝：伪造 SDK 执行、交换 Tool Call ID、删除 Tool Return、伪造最终 history。
- Evidence 分开记录 `run_outcome=EXECUTION_COMPLETE` 与 `effect outcome=CONTRACT_SATISFIED_IN_RUN`。`agent_failure=NOT_PROVEN`、`business_violation=NOT_PROVEN`；本次受限场景没有发现违规，也不表示证明了任何真实 Agent 失败。
- 允许的 Effect Claim 仅为 `SDK_FIXTURE_EXTERNAL_HTTP_EFFECT_OBSERVED`。`issuer_authenticity=NOT_ESTABLISHED`、`database_independent_authority=NOT_ESTABLISHED`、`real_provider_decision=NOT_PROVEN`、`workswarm=NOT_PROVEN`、`independent_reproduction=NOT_PROVEN`。Python 网络审计是 defense-in-depth，Evidence 明确 `is_os_sandbox=false`；本结果不宣称 OS sandbox 或生产隔离保证。
- Java Evidence 记录退出码 `1`；Runner 随后确认 Java process 已退出、固定端口无 listener，Tool Host/SDK child 退出且无外部连接。未把非零退出码写成成功退出码，也没有因此重跑 Scenario。

## 回归与交付记录

- 定向测试：`python -B -m unittest runtime.tests.test_effectwitness_config_target -v`，27 项通过。
- 全 Runtime：`python -B -m unittest discover -s runtime/tests -p 'test_*.py' -v`，在 `.local/rpf-52-rev3/runtime-regression/` 隔离源码镜像执行，254 项通过，2 项因 `Docker provider unavailable: RuntimeFailure` 跳过。镜像来自 Git tracked base 加本轮允许的工作树文件；固定 RPF-48 SDK site-packages 仅以只读 junction 供既有测试校验身份，避免测试写入旧 `.local` task roots。
- 全 Runtime 中 `test_missing_propagation_is_diagnostic_only` 输出 OTel exporter shutdown timeout 文本，但测试本身标记 `ok`；suite exit 0。另有 bounded telemetry queue 的诊断输出，不改变 canonical execution assertion。
- `python -B runtime/verify-reviewed-artifacts.py`：PASS；`python -B ci/verify-public-docs.py`：`PUBLIC_DOCS_PASS files=18 pairs=7`。
- 旧锚 verifier：RPF-43 `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e`；RPF-44 `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873`；RPF-48 `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2`；RPF-49 `04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b`；RPF-50 `b8f288db5dd76a142bbfb69a04d15ce9206d2cd9dbe28ef6effdb59382f5ef4a`；RPF-51 rev-4 `c569bd62a6691c84e8995359578fc4ff34f0ea417158a0c0893309c029df363d`。全部 verifier exit 0 / anchored。
- 第一次 RPF-43 命令因本地手输锚漏字符返回 `TRUSTED_ANCHOR_FORMAT`，没有修改文件；随后使用上表中的完整已知 SHA 重跑并通过。
- `git diff --check`：PASS。提交与远端状态以最终交付回执为准；本 Plan 不包含 PR、merge、release 或 deploy。
