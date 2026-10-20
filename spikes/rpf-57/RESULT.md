# TASK_RESULT — RPF-57 rev-1

**Status: Complete**

执行日期：2026-10-20，Asia/Shanghai。实现、真实两轮会话、新 Witness、本地验收及指定分支 Git 交付均已完成。证据接受与阶段推进仍待 Architect 审查。

## 1. 结果与身份

本轮完成真实 Explorer→独立 Target SDK→新 Java/H2→只读业务验证→已验证覆盖反馈→第二轮探索。模型自主选择 **planned-but-inhibited → local-delivery-suppressed**，第二轮实际新增 `ack_unknown_reconciled`、`delivery_suppression_observed` 两种已验证事实。`candidate_changed=true`，`L1=TWO_REAL_ROLES_EXECUTED`，`L2=true`，只使用限定名称 `L2_OBSERVED_INFORMATION_GAIN_IN_THIS_RUN`。H1/L3 为 NOT_PROVEN；没有公平 B0、统计优势或因果证明，也没有强制改变候选。

Root=`D:/CS/runproof`；Parent=`codex/rpf-56-rev4-explorer-tool-protocol-closeout`；精确 Base/执行时 HEAD=`403ac5bf01c796602ef244cb3985043014de62eb`。新分支=`codex/rpf-57-verified-feedback-coverage-exploration`，直接从该 Base 创建。origin fetch/push=`https://github.com/MyKr-YSteinsK/runproof.git`；建分支前 fresh ls-remote 验证父 ref 和 main=`bda0cd49e50e3181f604324e94877a24b9885334`，新分支不存在。初始 tracked/index clean，仅原有 `?? docs/reviews/`；该目录未进入、列举、读取、修改或暂存。main 与父分支没有写操作。

只新增 Plan 白名单的四个 coverage 模块、一个测试和 `spikes/rpf-57/probe.py`，以及本目录 README/RESULT/四份 JSON。旧执行源码、RPF-56 v4 与全部历史证书原字节不变；AGENTS、Project State、history、Web、Java、CI 未修改。新 `.local/rpf-57/` 创建前已确认不存在、父路径非 link/junction且实际 ignored。旧 53/55/56 运行根、marker、ledger/raw 未读取。

## 2. 实现、复制与源身份

新增六个源/测试文件共 **1,039 行**：contracts 73、policy 61、session 200、verify 182、tests 194、probe 329。这里包含有意保留的既有代码，并非全部原创：

- 新合同从旧合同派生，替换 owner/schema/Base/branch/Run/任务 JAR/上限；SDK Tool schema、业务 v1→v2 和历史 Oracle 保持原语义。
- Session 账本约 170 行沿用旧 WAL/预约过程并收紧到本轮限制；采用**同一本持久账同时承担 Task 与 Session**，Target 的每个 global_attempt 映射到此账。没有额外 Probe scope 或可拆分的父预算。两份新身份构造函数共约 30 行，继承旧 `TargetHost`/`BusinessHttp` 协议、故障和 HTTP 方法；不动态替换旧模块全局合同。
- Trial Verifier 的整个函数复制自旧 v4，测试用 `inspect.getsource` 证明逐字一致，仅本模块级 validate_trial 为新合同。新的 Session Verifier 重算请求、选择、Tool/Provider 映射、覆盖、事实差集和研究边界。
- Runner 在本轮白名单内复制 SDK 元数据、冷 Fixture、Java/SDK 生命周期及两轮过程包装，重接本轮路径/合同/账本。直接复用旧 Explorer 的 body_for/strict parse/shape/request 和固定来源 SDK/JDK/JAR 身份工具；没有调用旧 probe 的 live/preflight/fixture 入口。
- 新测试复用旧纯 synthetic_trial/valid_response；新建本轮完整合成 Session，覆盖全部九种候选配对。复制与复用的代价是本轮局部代码重复，保留冻结历史的可验证性；未抽取共享层或回写旧源。

执行前冻结 source map digest=`fdca20947e045836957dce24ea95217ff40606489097e20542c0aee0344f4687`；执行与交付源码一致，Session 期间没有修执行代码或换 Oracle。

| 新执行文件 | LF 规范化 SHA-256 |
|---|---|
| `runtime/runproof_runtime/effectwitness/config_pge_coverage_contracts.py` | `faa6220e99b8537fcf665673a25296aab5a384553801ab7cf7c287d41c51fa18` |
| `runtime/runproof_runtime/effectwitness/config_pge_coverage_policy.py` | `abdaf9aee0353e34d6f2737a83dbcdf8e27f4a1c3b7adb594657bd323de90ab4` |
| `runtime/runproof_runtime/effectwitness/config_pge_coverage_session.py` | `11bc325853ed05b7fa139092dd643d20fd9971ce25d2583277cf2f8be6639196` |
| `spikes/rpf-57/probe.py` | `f36671a4104ca458d7fe90724fa505d0f40c11ead74be53356176f94fcd534a2` |

Verifier=`rpf57-config-pge-verifier-v1`，自身 SHA=`4bee4479145222f7c5707a85343c06f9d27946fa1cbe6833e3b4714f9ff31272`，单独绑定于 Envelope。完整 19 项 source map 在 [verification-diagnostic.json](verification-diagnostic.json)。测试源码不参与运行 source map，但隔离回归快照记录其 SHA 并与本树一致。

## 3. 前置、真实两轮与覆盖

固定直接 CPython 3.12.13、pydantic-ai-slim 2.57.0、OpenAI 3.35.1 的当前 RECORD/core/site-root/ABI/runtime mapping 已实际核验，mismatches=0。原 exe SHA=`e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f`，launcher SHA=`74e020321eb8f828f0c2cfe865082fcf94aa6e7cf488e8a744d89b9282eaeb83`。元数据首轮由于新包装缺少 oldc import，在纯检查结束后 NameError；离线修复后重新检查通过，共两次零 Provider 元数据进程。另一个构造函数缺少 validate_trial import 由单元测试捕获并在冻结前修复。没有付费重试、安装、解释器 fallback 或系统策略调整。

三个新 source 的真实冷进程 Fixture 各一次，runner PID=27436/31924/10928：normal、planned-but-inhibited、local-delivery-suppressed 均 PASS，Provider/Java/业务 HTTP=0。正常和 inhibited 回注 [2,3,4]；suppressed 为 [2,3,null]，实际 SDK_ERROR/RuntimeError，显式 withholding 一次。gate、ready/Popen、stderr、端口和线程清理均核对。初期纯检查的 Source 与最终 source gate 分别保留，正式会话只接受最终同源 Gate。

2026-10-20 再查官方 [价格](https://api-docs.deepseek.com/quick_start/pricing/) 与 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 后才读取进程环境中的已有 Key。峰值 cache-miss input $0.30、output $1.20 每百万 tokens；乘15采用 4.5/18 CNY guard。具名 select_experiment、thinking disabled、parallel=false、max_tokens128，仍严格只接受单个合法真实 Tool Call。**本 Plan 付费协议 Probe=0**。

Session=`rpf57-session-3ee4ca3412394b0a`，两轮三候选均预注册，全目录始终开放，normal 与重复候选均合法。

| 轮 | 真实选择 | Java PID / SDK PID | Target 请求 | 业务 HTTP / POST / health |
|---|---|---|---:|---|
| Round1 | planned-but-inhibited | 7060 / 20600 | 4 | 8 / 2 / 1 |
| Round2 | local-delivery-suppressed | 3356 / 25020 | 3 | 8 / 2 / 1 |

Round1 Run=`rpf57-57bdacde5aebb44338`，Call ID=`call_00_Mv9AC9iCW9G4jC7dd3Hd7475`；facts=`effect_satisfied_v2, fault_planned_inhibited`，此前集合为空。planned/triggered/observed=true/false/false；实际命中禁用 gate，业务 v2、history[2,1]，Target ACK RECEIVED。未执行目录是 local-delivery-suppressed 与 normal，没有为它们预写结果。

Round1 独立 verify_trial 成功后，feedback SHA=`5e4f1cd6c3e95409d3f10ffaf5dec254ee41534fb175070b67ab17e526acfbb0`，coverage digest=`d51e2ce972eedcf3120a19441ed9acf7534c9aa5a47ff9e3882c2ee7dfb27335`；反馈事件 seq=3，随后 Round2 input frozen seq=4，单调时间严格先后。第二轮请求确实包含首轮真实 Call ID、Tool 原反馈、显式同一 feedback hash、seen/tested/unseen 目录和全部合法 catalog；request SHA=`692bfc366e3b6e502c62a1d23166672b3a51d8c4ef668f61f7c7d6163a75f65e`。不是事后填写的反馈快照。

Round2 Run=`rpf57-576d8d4fe1651e4553`，Call ID=`call_00_Q5bPjwW5EUyJp9rzJYbD8670`，feedback SHA=`350c09fa1873c66718f4611b0ea5b1d7acc26c99a32b9c4b21f689e3f54a8442`。新事实恰为 `ack_unknown_reconciled, delivery_suppression_observed`；重复的 effect_satisfied_v2 不再计分。最终已见事实四种，normal 仍未测试，绝不写成“normal未触发”。完整两轮覆盖见 [coverage-analysis.json](coverage-analysis.json)。

每轮真实 Target 自主发出 inspect_config/create_config_v1/update_config_v2；参数和实际业务 HTTP 对应。第二轮 update 实际 HTTP200/业务code0且 v2 已提交之后，Host 才 withholding，一次显式 Tool delivery error。Target ACK 保留 UNKNOWN_OUTCOME；停止写入并 GET-only reconcile current/history/list，确认 v2/history[2,1]、没有第三次 POST。它不是 TCP 丢包，也不判 Agent FAIL；platform_error=EXPECTED_TOOL_DELIVERY_ERROR，business_violation=NOT_PROVEN。

Java17.0.12，固定 source commit=`0258b9cef02ea74a40989d035c79256c776409c0`；manifest SHA=`33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`；本轮复制 JAR=66,981,576 bytes / SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。两轮均核对实际 argv 的任务副本、listener归属、无外连、独立 namespace、新 H2、初始 ABSENT 和只读 Authority；不是复用旧状态。Authority 是 SAME_SERVICE_READ_ONLY_HTTP，不声称数据库独立。

## 4. 全任务预算与终态

| attempt | 角色/轮 | prompt / completion / total | 实际 returned model | 状态 |
|---:|---|---|---|---|
| 1 | EXPLORER/1 | 455 / 40 / 495 | deepseek-flash | RECEIVED |
| 2 | TARGET/1 | 648 / 29 / 677 | deepseek-flash | RECEIVED |
| 3 | TARGET/1 | 695 / 55 / 750 | deepseek-flash | RECEIVED |
| 4 | TARGET/1 | 780 / 74 / 854 | deepseek-flash | RECEIVED |
| 5 | TARGET/1 | 884 / 111 / 995 | deepseek-flash | RECEIVED |
| 6 | EXPLORER/2 | 978 / 40 / 1018 | deepseek-flash | RECEIVED |
| 7 | TARGET/2 | 648 / 30 / 678 | deepseek-flash | RECEIVED |
| 8 | TARGET/2 | 696 / 55 / 751 | deepseek-flash | RECEIVED |
| 9 | TARGET/2 | 781 / 78 / 859 | deepseek-flash | RECEIVED |

Explorer=2、Target=7、总 HTTPS=9/10；总 tokens=7,077/20,000，保守估算费用上界 **¥0.0387585 / ¥0.50**，并非实际账单。全部 usage 已知，pending/未知预约=0，无退款或新 Session。模型返回 alias deepseek-flash，不声称能独立识别唯一后端构建。每个预约在 Provider/JVM/POST I/O 前 fsync；未知 usage 非零占位并阻止后续。

JVM=2/2、POST=4/4、业务 HTTP=16/24、health=2/6。正式两轮均在 1,200s/轮与2,400s会话限额内。两个 Java/SDK 已退出、两组端口关闭、Host线程停止、本地临时 key 引用释放；两个 Provider worker 进程结束。SDK 无 Provider/business secret，Java 只接收本地合成 key；未修改原环境提供的 Key。清理值六项每轮均 true，Witness 保留逐项证据。

## 5. 独立证书、测试与验收

新证书 [config-pge-coverage-evidence.json](config-pge-coverage-evidence.json)：schema=`rpf57-config-pge-evidence-v1`；source_kind=`REAL_EXPLORER_REAL_TARGET_CONFIG_JAVA_HTTP`，原始 **88,960 bytes**，外部 raw SHA-256：

`76dd7077d75e6dd8ad319bb6e17a01209faadee9fe94d276f3b85e73e88abbe7`

真实完整链验证通过后才签发；同一冻结源码的独立 CLI 正确/缺失/错误外部锚为 **0/2/3**。18 类重新计算内部和外部哈希的语义篡改全部 exit3：forged_selection、feedback_hash/order、split_role_budget、duplicate_post、false_trigger/ack、namespace_splice、source、sdk_pid、cleanup、future_fact、unknown_fact、missing_readback、wrong_authority、novelty_overclaim、pending_usage、parent_split。合成正控和合法重复负控均先得到完整 CLI 验证，九组候选配对都跑全部负控（162次拒绝），不会把错锚当语义拒绝。

| Gate | 状态 | 证据 |
|---|---|---|
| A-01 身份与保护 | PASS | 精确 Base/新 branch/远端/ignore/link/status；禁止目录未触及 |
| A-02 additive/旧证据 | PASS | 六个新源/测试；旧 tracked diff为空；旧 v4/verifier及固定锚未变 |
| A-03 覆盖与可见性 | PASS | 9候选对，合法重复0新事实；无效/缺读回/错误Authority不产事实；请求快照精确重建 |
| A-04 账本与Verifier | PASS | 18类负控、CLI0/2/3、跨进程竞争只成功预约一次、损坏/锁/未知usage/重启与重复POST拒绝 |
| A-05 真实SDK前置 | PASS | 三种新source冷Fixture，零Provider/Java |
| A-06 真实Explorer | PASS | 两个真实Call ID/usage；具名唯一选择，无Fallback |
| A-07 Target/业务/Fault | PASS | 2真实Target、2新Java；抑制实际激活并只读对账；normal本次Live NOT_RUN |
| A-08 实际覆盖增益 | PASS | 验证反馈seq3先于第二轮请求seq4；candidate_changed=true，新增2条实际事实 |
| A-09 Witness/回归 | PASS | 新Witness；347 Runtime tests/2 Docker skip；10历史锚current-tree CLI exit0；Reviewed/Public Docs PASS |
| A-10 交付 | PASS | 首次聚焦实现提交已push；fresh ls-remote与GitHub commit读回匹配；tracked/index clean，仅保留原用户条目 |

命令：`python -B spikes/rpf-57/probe.py offline`（12项定向测试+正负完整CLI）；三个 fixture 命令与唯一一次 live 命令；完整 `unittest discover -s runtime/tests -t . -p test_*.py -v` 在本轮 ignored 快照运行，**347 tests / 0 failures / 0 errors / skipped=2**。快照取自精确 Base 的 runtime/spikes/ci/demo 并覆盖新六文件，禁用 Java/Docker与外部网络，无Key；旧测试自建的旧名称目录也完全在本轮快照内部，未触及实际历史运行根。Source SHA 对照一致。两个 Docker 环境测试明确 skip，不算Docker验收。

`python -B runtime/verify-reviewed-artifacts.py` 与 `python -B ci/verify-public-docs.py` 均 PASS。10个历史固定原始SHA Witness CLI：RPF43/44/48/49/50/51r4/52r3/53r6/55r2/56r4，在**当前工作树源码**全部exit0，未用历史checkout替代，也没有重新签发。55r2 verifier按既有显式逻辑报告其历史初始执行版本；此规则本轮未改。

Maven、Web build/typecheck、浏览器/UI、Docker正式边界和Hosted CI/workflow dispatch **NOT_RUN**，本轮未改变其边界。新分支push不触发仅main/PR的Release Gate；其余workflows为manual，无release/deploy。后续结果不推导主线接受。

## 6. 研究限制、产物与交付

本轮支持“已验证反馈实际暴露后，下一次真实选择不同，随后得到两条新事实”的观察链。无法由一次会话证明该反馈的因果影响、模型选择理由、跨域泛化、统计优势、同预算B0优势或WorkSwarm。`issuer_authenticity=NOT_ESTABLISHED`、`database_independent_authority=NOT_ESTABLISHED`、`independent_reproduction=NOT_TESTED`、`WorkSwarm=NOT_PROVEN`、`attribution=CORRELATIONAL_ONLY`。重验同证书不是独立复现；UUID/lineage检查拒绝已知合成重标，不提供密码学签发者认证。RPF-56原L2=false保持原事实，不被新结果覆盖。

本轮 ignored 根保留任务JAR、三Fixture、两Trial、fsync账/事件、redacted Java日志、raw health、来源/回归快照及CLI负控以供复查；不进入Git。无生产凭据、用户数据、外部原仓库或系统设置修改。执行源码冻结后只写报告/摘要/证书和本轮诊断；生成用临时脚本在清理时移除，必要运行证据保留。没有创建RPF58–60计划。

本次主结果为本文件，README为复现/边界入口。首次实现交付 SHA=`c5aeef8fe4def95cac0fd1f9dec23908821d3b54`，普通push后fresh ls-remote与GitHub commit API均确认一致；main及父分支保持原SHA。本次收口只更新本报告状态，运行源码与证书不变；最终完整commit SHA在聊天回执，避免循环回填自身SHA。Push不等于Merge/Deploy，证据接受和阶段推进待Architect审查。

交付前逐文件核对暂存 Git blob 与工作文件完全同字节，证书 raw SHA 未变化，运行源码与隔离回归快照一致。新文件 private-path/secret pattern 扫描通过，任务端口再次确认关闭。普通 `git diff --cached --check` 仅报告 session.py 末尾额外空行；为保留已执行源码哈希未修饰该空行，显式 `git -c core.whitespace=-blank-at-eof diff --cached --check` 其余项通过。Git autocrlf 警告不代表当前证书已被转换；实际暂存原字节已核对。
