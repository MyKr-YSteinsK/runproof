# RPF-53 rev-6｜TASK_RESULT

**Status: Partial（必要工程验收已通过，Git 交付待闭环）**

## 1. 身份、范围与结论

- Plan：`RPF-53 / rev-6`，Live Witness 离线修复、成功路径预演与有界自主验收。
- 精确 Parent/Base：`306ba5f49cea472a585920977c9db895626bb39f`；Parent branch：`codex/rpf-53-rev5-live-config-contract-jar-closeout`。
- 本轮分支：`codex/rpf-53-rev6-live-witness-recovery`；现场 `main`：`bda0cd49e50e3181f604324e94877a24b9885334`。
- origin fetch/push 均为公开既有仓库 `https://github.com/MyKr-YSteinsK/runproof.git`；实施前目标远端分支不存在，index 为空，唯一原有 short-status 为 `?? docs/reviews/`。
- 本轮未进入、枚举或读取 `docs/reviews/`；该状态行保持。未修改 Project State、history、UI、CI、外部 Java 仓库或任何旧结果。六个定向读取的 rev-5 输入在新 Live 后重新核对 SHA，全部相同。

本轮新真实 Trial `rpf53-live-917c3dda02fb4ad7` 完成 `inspect → create v1 → update v2`，独立 HTTP current/history/list 得到 `rpf53-v2 / version 2 / history [2,1]`。新证书通过独立锚与四类重算摘要的篡改负控；没有把 rev-5 事后改写为成功。

`EXECUTION_COMPLETE`、`CONTRACT_SATISFIED_IN_RUN`、`WITNESS_VERIFIED` 均已在本轮对应范围内建立。`ISSUER_AUTHENTICITY=NOT_ESTABLISHED`，`DATABASE_INDEPENDENCE=NOT_ESTABLISHED`，independent reproduction=`NOT_TESTED`；`EVIDENCE_ACCEPTED` 由 Architect 另行审查。

## 2. A-01～A-08

| Gate | 状态 | 实际证据 |
|---|---|---|
| A-01 Repo/权限/历史 | PASS | 精确基线、origin、main、空 index、新分支及白名单核验；旧 tracked 证据不变；定向旧输入 SHA 不变；受保护目录未触碰。 |
| A-02 Verifier 修复 | PASS | 实际复现原第 288 行 `KeyError: experiment`；修正两处同级合同访问；完整生成/封装/验证成功，缺字段、错形状、来源、PID、费用、回注和篡改均受控拒绝。 |
| A-03 无付费成功预演 | PASS | 合成成功 Envelope 独立 CLI=`0/2/3`；四类 rehashed tamper 全部 exit 4。第 1 次真实 SDK Fixture 的 63 项检查全部 true；零 Provider、业务 HTTP 和 Java。 |
| A-04 rev-5 谱系与 preflight | PASS | 必填字段矩阵见第 4 节；Live visibility 无法恢复。动态允许输出与冻结来源分开比较，仍拒绝源码/身份漂移、非法路径和 staged contamination；本轮新输出增长未再触发 source drift。 |
| A-05 真实 Provider/Effect | PASS | 新 fresh namespace，4 次真实请求、3 次 SDK 工具和回注、8 条业务 HTTP（2 POST）；task-owned JAR 实际 JVM argv、健康检查、只读 Authority 与 Oracle 通过。 |
| A-06 Live Witness | PASS | 新真实来源证书；correct/missing/wrong=`0/2/3`，四类 rehashed tamper 全部 exit 4。Verifier 身份、发行时间及来源限制已记录。 |
| A-07 回归/预算/安全 | PASS | 定向 47 项；新隔离全 Runtime 301 项、0 failures/errors、2 Docker skips；七个旧锚、Reviewed Artifacts、Public Docs 和差异检查通过；总账与清理通过。 |
| A-08 Git/TASK_RESULT | PENDING | 本报告、实现与证据仅交付授权安全分支；普通 push 后以 fresh `ls-remote` 闭环。无 PR、merge、tag、release 或 deploy。 |

## 3. 根因、修复和无付费预演

原 `validate_payload()` 在第 288、364 行分别通过 `execution["experiment"]` 取得 `runtime_source_sha256` 与 `run_id`，实际结构应为 `contracts["experiment"]`。新增合法完整合成 payload 使用生产 `_make_payload`，在修复前实际触发第一处 KeyError；修复后走完全部后续校验。

Verifier 保留严格字段与业务检查，并将错误嵌套、越界或异常 JSON 转成明确的拒绝 enum。额外绑定 SDK 与 Provider 的 usage、OpenAI source identity，并拒绝将 boolean 当版本整数。新 Envelope 记录 `REAL_PROVIDER_LIVE_RUN`、UTC 发行时间和 Verifier 的 LF 归一化来源 SHA；Issuer 真实性没有因此被提升。

Probe 的 preflight 仍逐次检查白名单和 index；冻结比较仅排除可增长的 `status_paths`，Git/remote/protected 状态与六文件内容身份继续冻结。单测覆盖允许输出增生、非法路径、protected-path 伪装、staged contamination 和源码/身份漂移。本轮 Fixture 后实际新增 README、verification diagnostic 与 summary，Live preflight 正常通过，未移动任何输出绕过检查。

Tier 0 使用三个有意义的修复/验证循环：复现 KeyError；修复并通过 46 项定向检查；加入最终离线门控与强化检查后通过 47 项。完整模拟 Envelope 仅存于 `.local/rpf-53-rev6/replay/`，明确标注 `FIXTURE_SCRIPTED`，不作为真实 Live Evidence。四类独立篡改为 Provider 来源、SDK call lineage、Authority history、cost/source contract；每份重算内部 payload digest 和外部 SHA 后仍 exit 4。

新 Live 在证书自检前将脱敏 payload candidate 存到本轮 scenario，并逐请求持久保存可见性哈希。正式证书仅在本地 candidate 的全部独立锚与负控通过后写入，便于业务效果成功后的纯离线排障。

## 4. rev-5 留存字段矩阵

| 必要字段 | 留存状态与来源 | 结论 |
|---|---|---|
| Execution/Effect/Experiment | task-local `scenario/contracts.json`，SHA 与 tracked summary 相符 | OBSERVED |
| SDK/source/PID/JAR/cleanup | tracked rev-5 Live summary 与 preflight | OBSERVED |
| Provider request/usage/response IDs/Tool Return lineage | task-local ledger，requests 与 tracked summary 相同 | OBSERVED |
| HTTP current/history/list/Oracle | tracked rev-5 Live summary | OBSERVED |
| Tool Schema hash | rev-5 ledger/summary | OBSERVED |
| `agent_contract_visibility[*].messages_sha256` | 已保存的 Live summary/contracts/ledger/marker/preflight 中均未留存 | MISSING_UNRECOVERABLE |
| Fixture visibility | 旧 Fixture 有记录，但 Run ID 与 Live 不同 | 不能填充 Live 缺口 |

不从 request hash 反推 message hash，不合成“旧模型曾见到”的记录。本轮未签发 rev-5 retrospective Witness；旧结果继续为 `PARTIAL`。因此使用 rev-6 条件授权执行一个新的独立 Trial。输入路径、字节数、SHA、原 commit 和谱系检查保存在 `verification-diagnostic.json`，未复制旧秘密或原始模型文本。

## 5. 冻结身份与 SDK Fixture

本轮 offline rehearsal、最终回归、Fixture 和 Live 使用同一 aggregate source SHA：`a60a868128dd165375af3d764f9e3f0011c8dd6310f4906f352b02cf6efbb91a`。Fixture PASS 后未修改源码。

| 文件 | SHA-256 |
|---|---|
| `config_live_contracts.py` | `4a2e111c643d20e2873f4b46c665c58bce3b2b4fa27f5e55fe6467a00ee5443f` |
| `config_live_runtime.py` | `b973698450a42be8f74838f5aa8377bb45010694a2aa555819caa48ceb1c86a9` |
| `config_live_external.py`（未修改） | `0d977965f72d2a8ade8d02d0ce4963742cb8952976f012459c58423aefe9bdfe` |
| `config_live_verify.py` | `75fa9329f8773279801b6e5c3165fe0bd8fc22ead60f7001f6c885827f8d0282` |
| `test_effectwitness_config_live.py` | `94817ee440b17124cbaa80627bc110ecf5fcf95a3386e92194786ccfc75cbc82` |
| `spikes/rpf-53/probe.py` | `b877325e833c6170148e73fd2b290ab0a4165033668570744067cee24ef2210e` |

固定 config-center commit 为 `0258b9cef02ea74a40989d035c79256c776409c0`；manifest SHA=`33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`，110 文件/393,800 bytes。本轮 JAR 为 `.local/rpf-53-rev6/jar/config-center-server-1.0.0.jar`，66,981,576 bytes，来源/副本 SHA 均为 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。task-root containment、无链接组件、Popen 与实际 JVM `-jar` 路径均通过；没有启动额外 `java -version` 诊断进程。

真实 SDK Fixture Attempt 1：`rpf53-diag-f457aad0e3a64dbe`；4 completions、3 SDK-origin Tool Calls、3 unique Returns、回注位置 `[2,3,4]`。Popen/Host-ready/report PID 均为 `28684`，exit 0，63/63 checks true；Provider/业务 HTTP/Java 计数为 0，外连为空、Host/port/child 清理通过。SDK 为 Pydantic AI slim `2.57.0`、OpenAI `3.35.1`、直接 Python `3.12.13`，RECORD mismatches 为 0。Tool Schema SHA=`58bcb979a92486b7371153a5d3d098bcf0f2cae30f78004e09af5ff901bf3174`。

Fixture result SHA=`d65d2896cacc96ca9079d5b11e04ef34d1ed0a4d4d2345cc195b53a0267f32bd`；marker SHA=`c5c14af7f291ec18ed596fa846519cabf98da46294ec0b0d31c560b99ce87fcd`。

## 6. 新真实 Trial、费用与证书

官方文档于 2026-10-19 核验：`deepseek-flash / DeepSeek-V4.1-Flash-1017` 支持本轮非 thinking Tool Calls，OpenAI-compatible origin 为 `https://api.deepseek.com`。Peak cache-miss input/output 价格为每百万 tokens `$0.30/$1.20`；计划固定 15 CNY/USD 用于保守预算，非实际汇率。参见 [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) 与 [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。

| 请求 | Provider response ID | 工具 | input/output/total tokens |
|---|---|---|---|
| 1 | `c21edd2b-56aa-49b3-830e-c1509d658e95` | inspect | 648 / 33 / 681 |
| 2 | `1f9c8b71-1140-484d-87d6-8685e28b40ad` | create v1 | 699 / 58 / 757 |
| 3 | `a6d66215-a160-4ed3-b03b-aff57abb0dcc` | update v2 | 787 / 84 / 871 |
| 4 | `1dd62962-7e42-456c-88bb-4f251184fc48` | final response，无新工具 | 901 / 123 / 1024 |

SDK/Provider usage 一致：3,035 input + 298 output = 3,333 tokens；4 HTTPS requests，1 Trial，0 automatic retries，usage known。估算上界 `¥0.0190215`，不代表账户实际扣款。父 Host 的持久 total-budget 与 per-Trial ledger 在每次网络请求前预留；本轮选择只启用一个 Trial，严于 Plan 允许的最多两个。总请求≤12、tokens≤24,000、费用≤¥1，以及每 Trial 的 6 requests/12k tokens/8 tools/12 HTTP/2 POST/3 health GET/1200s 均满足。

四条模型可见性记录及 messages SHA 已保存在 ledger、summary 和证书；三次工具结果在后续请求 2、3、4 回注。真实 HTTP 总计 8 条：initial current 404/4041、initial history 空、inspect 404/4041、create 200/code0/v1、update 200/code0/v2、final current/history/list 三条独立 GET 均通过。另有一个 health GET=`200/UP`。Oracle gaps/violations 均为空；业务违规和 Agent failure 均为 `NOT_PROVEN`。

新证书 `config-live-evidence.json` 为 21,170 bytes，外部 SHA-256：

`f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43`

发行时间：`2026-10-19T10:11:14.539276+00:00`；Verifier 来源为第 5 节 hash，Envelope 明确 `REAL_PROVIDER_LIVE_RUN`。独立 CLI correct/missing/wrong anchor=`0/2/3`；四个内部/外部摘要均重算的负控 exit 均为 4。

Java PID/listener PID=`24524`，SDK Popen/ready/report PID=`20280`。SDK exit 0；Java 受控停止记录 exit 1；两者均已停止、相关端口关闭、外连为空、Host 已关闭，`cleanup_ok=true`。交付前只读复查两个端口关闭及 Fixture/Live 三个 PID 不存在。SDK child 的 Provider/business key absent、guard denials 为空；未保存 Provider 原始自由文本或 private reasoning。

公开 Live summary 仅保留 health 总状态；包含本机绝对路径的组件细节留在本轮 task-local 原始快照，其 SHA=`44945d57c070c16d76e9392bab68c17aa2d10421a5091815bb07dc50c65da300`。公开 summary 的 export-redaction 元信息说明此转换；公开副本为 18,274 bytes、SHA=`34e0a7fbb0fa8ff90a7deac3d36db2dbf9b60b06930536738764086ca4b7d2a0`。证书本身未作此转换，外部锚保持不变。

## 7. 回归、历史锚和交付边界

- 定向：`python -B -m unittest runtime.tests.test_effectwitness_config_live -v`，47 tests，exit 0。
- 隔离全量：从精确 Parent 的 `runtime/` 和 `spikes/` 建立快照，覆盖六个冻结源文件，不含 `docs/`；运行 `python -B -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v`。最终 301 tests，24.177s，exit 0，0 errors/failures，2 skips（Docker provider unavailable）。普通回归 Python 为 `3.14.6`，真实 SDK child 为独立固定 `3.12.13`。
- 首轮全量失败记录保留：旧 config-target 测试一次 Windows loopback `WinError 10053`；OTel 测试被回归 harness 错设的 `OTEL_SDK_DISABLED=true` 干扰，缺少 traceparent。移除该 harness 环境变量后，在 fresh 隔离快照复跑一次全量成功；没有修改旧测试或产品源码来规避失败。
- `runtime/verify-reviewed-artifacts.py`、`ci/verify-public-docs.py`（`files=18/pairs=7`）均 exit 0。七个固定外部 SHA 的 RPF-43/44/48/49/50/51-rev4/52-rev3 verifier 均 exit 0，具体锚与日志 SHA 在 diagnostic 中。
- 全部本轮源码/文档差异检查、输出 JSON 解析和秘密/绝对路径扫描通过。`.local/rpf-53-rev6/` 的 JAR、模拟证书、失败日志、原始 task-local 健康快照和运行记录保持 ignored；未删除或重置历史 marker。

本轮剩余限制为 Issuer/数据库独立权威、独立复现和总体 Agent 泛化能力；PGE 未执行、WorkSwarm 未证明。Python audit hook 是 defense-in-depth，未建立 OS sandbox。现有代码仍会先采集健康组件细节，本轮公开导出已显式最小化；未在 Fixture 后修改冻结源码。

Git 交付待完成：仅允许本分支 focused commit、普通 push、fresh remote SHA。最终提交 SHA 与 main/工作区核验在聊天回执提供；本报告不引用自身最终 SHA。
