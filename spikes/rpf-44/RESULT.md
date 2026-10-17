# TASK_RESULT｜RPF-44 / rev-1

Status: Complete

## Identity 与设计决定

- 根目录：`D:\CS\runproof`；公开仓库 `MyKr-YSteinsK/runproof`，origin `https://github.com/MyKr-YSteinsK/runproof.git`。
- Reviewed parent：`codex/rpf-43-witness-offline-verifier@238037a0b7499800325a91f3beeacf9161fc4d01`，启动时本地/独立远端一致。
- 当前交付分支：`codex/rpf-44-cross-domain-witness-core`，从该 parent 创建。main 观察值 `bda0cd49e50e3181f604324e94877a24b9885334`。
- 最终 HEAD/独立 remote ref 取本文件所在 focused commit；精确 SHA 与 push 后 clean/ref 观察在聊天交付回执中报告，避免自包含 commit hash 的循环修改。
- feature branch push 无 deploy 副作用：canonical Release Gate 仅 `push(main)` / `pull_request(main)` / dispatch，其余相关 workflow 为手动入口。本任务普通 push-only；PR / merge / main 写入 / tag / release / deploy / 手动 CI：NO。

方案 **B**。现场 `docker.exe` 存在，但 `docker version --format '{{json .Server.Version}}'` 无法连接 `dockerDesktopLinuxEngine` named pipe。daemon `UNAVAILABLE`，镜像身份 `NOT_INSPECTED`，没有 pull/启动 Docker/修改宿主服务。正式对接为 **RPF28_DOCKER_INTEGRATION_NOT_PROVEN**，Docker formal runs=0。

实现复用 RPF-28 的 release-v1→release-v2、revision、唯一 operation receipt/effect count、依赖检查与提交后失答语义，使用标准库 SQLite 实际事务。运维禁止依赖未就绪或初始版本/revision 不符时变更配置；唯一性及 reset generation 与订单金额规则独立。

源码分类与入口见 [README](README.md) 的映射表。两域共用 `Budget/Orchestrator → cross_trial → cross_core`；离线共用 `witness_verify` 字节/锚/版本分发及事件/故障基础校验，再由静态注册的纯 oracle 判断业务。没有复制第二套 ops 离线 verifier。新冻结对象与 legacy `FrozenContracts` 分开：没有扩宽旧 schema 或 owner。原订单 reader 仅增加新 owner 的精确存储路由；业务状态/收据/HMAC 校验保留。Ops reader 用独立 SQLite `mode=ro`、`query_only` 连接并在事务内捕获，在线临时 HMAC 不输出。

## 版本与证据身份

| 项目 | 本地已核验值 |
| --- | --- |
| Python | CPython 3.14.6，MSC v.1944，64-bit；既有 OTel SDK 可用；无安装 |
| Witness / oracle | `rpf-effect-witness-v2` / domain=`ops` / oracle_version=`1` |
| Execution / Experiment | `rpf-cross-execution-v1` / `rpf-cross-experiment-v1`，owner=`rpf-44` |
| Ops Effect / Env | `rpf-ops-effect-v1` / `rpf44-sqlite-ops-v1` |
| EffectWitness package source-map digest | `f3f107f30b7060b5cfc4f0e3de7466ab6961f65847b2ab7620fe03c8dcaaf792` |
| 新 Ops 全文件 SHA-256 / 字节数 | `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873` / 10123 |
| 旧 RPF-43 全文件 SHA-256 / 字节数 | `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e` / 9257，逐字节保留 |

Source-map 算法沿用 `witness._package_source_digest`：对 package 内全部 `.py` 规范 CRLF→LF 后逐文件 SHA256，再对 canonical filename→hash map 摘要；不把 JSON 自报摘要当外部信任。公开仅新增一份 [Ops Witness](sample-ops-witness.json)，canonical UTF-8/ASCII JSON 无末尾换行。订单新证书只在内存及已清理的测试临时输入中存在。

## Actual Trials｜本轮实际运行

以下为本轮本地实测，不依赖历史 TASK_RESULT 证明。本轮非测试 trial 总数 **2/3**；两次均确定性 target，Provider requests=0、tokens=0、cost=¥0、automatic retries=0。

### Ops sample

- run：`rpf44-4c926b4438c64442a41509fd4fee968c`；environment：`env-rpf44-4c926b4438c64442a41509fd4fee968c`；owner=`rpf-44`，generation=0。
- config：`config-rpf44-4c926b4438c64442a41509fd4fee968c`；operation：`apply-rpf44-4c926b4438c64442a41509fd4fee968c`。
- before：release-v1 / revision=0 / effect_count=0 / operation_id=null / dependency=READY / receipts=[]。
- after：release-v2 / revision=1 / effect_count=1 / 冻结 operation_id / dependency=READY / 唯一 APPLIED receipt。
- receipt：`receipt-f3eca5bdb6141d0d91a19805`；receipt list hash `a14e0b613b4dee66e5146b3fec99a568a73270e210cfcc84897332ba60dcb27c`。
- authority before hash：`10f3b5cb16b7852c251e57cca0af80e588a0898969668260e66ba71c5c667019`；after：`c1efa42af839f8661653f6069f5e817d38e19900bf84391b9e09bc42e48cb5b4`。
- 真正提交后 adapter 隐去成功响应，产生 UNKNOWN_OUTCOME；Orchestrator pending 阻止工具再执行，独立 reader receipt reconcile 后放行。fault planned/triggered/observed/reconciled 全为 true。
- 来源 `CONTROLLED_OPS_LOCAL_SIMULATION`；四轴 `CONTRACT_SATISFIED_IN_RUN / TRIGGERED / CORRELATIONAL_ONLY / NOT_TESTED`；Run outcome=`PASS` 独立保存。白名单 feedback 包含 oracle 的 state_diff/receipt_hash，可离线复算。
- 7/8 预算步，0.121 秒。证据在 reset 前冻结；reset generation=1、receipt_count_after_reset=0，`RESET_AND_REMOVED`，DB 与 run 目录移除。

### Fresh order compatibility

- run：`rpf44-03fea99a32074ee1a888cae363b99c51`；environment：`env-rpf44-03fea99a32074ee1a888cae363b99c51`；operation：`refund-rpf44-03fea99a32074ee1a888cae363b99c51`。
- 同一个新冻结 schema / dispatcher / Budget / Orchestrator / 反馈投影：PAID→REFUNDED，2500 CNY minor units，一次退款、revision=1、唯一收据；response-lost 后独立 reconcile，四轴同上。
- 内存证书 SHA `0edacad8dece29bc93100945118e42e0bd221e2e2a85b53df8d6776243907709`；receipt list hash `1dabd95ffd4377c27ed849be158fd05bc4e9aae3e744784146ff5c4f0107d81c`。未持久化新订单证书。
- 7/8 步，0.117 秒，`RESET_AND_REMOVED` / generation=1 / receipt_count=0。

首轮预留 `2026-10-17T13:30:30.325297+00:00`，第二轮 `13:30:36.124263+00:00`；实际业务运行累计 0.238 秒，整个受控窗口不足 7 秒，分别低于每轮 900 秒 / 总窗口 2700 秒。

## 验收与负控

| Gate | 状态 | 证据 |
| --- | --- | --- |
| A-01 | PASS | 根目录、parent、remote、空闲分支/路径及 workflow 预检；`docs/reviews/` 仅 status 汇总 |
| A-02 | PASS | README 源码映射；`CrossWitnessTests.test_two_actual_domains_same_dispatch_and_recomputable_feedback` |
| A-03 | PASS（B） | Ops sample 真事务、独立 before/after、唯一 receipt/effect_count；Docker 正式集成 NOT_PROVEN |
| A-04 | PASS | `ops_oracle.evaluate_ops_effect`；依赖/revision 前提、坏状态/收据、伪 Tool 成功测试 |
| A-05 | PASS | UNKNOWN 阻断/reconcile、same-op 幂等、different-op/越权拒绝、依赖无写、NOT_TRIGGERED、缺权威 INCONCLUSIVE |
| A-06 | PASS | sample 九事件及 pre-cleanup 只读捕获；真实 reset/readback/remove；四轴保守 |
| A-07 | PASS | 原样本变更前/后已知锚验证；两域 fresh SQLite fixture 共用入口；禁用数据库/网络/Provider/执行器的独立进程；旧 v1 样本不变 |
| A-08 | PASS | `test_effectwitness_ops`、原 Witness 安全测试；下述拒绝码矩阵 |
| A-09 | PASS | 完整 Runtime 141 tests / 2 Docker group skips；0 Provider、2 trials；临时夹具已清理、无未决隔离 |
| A-10 | PASS（push-only） | focused commit、本文件与单个新样本在许可路径内；最终远端 ref/clean/main 核验随聊天交付回执 |

实际命令与结果：

- `python -m unittest runtime.tests.test_effectwitness_ops runtime.tests.test_effectwitness_witness runtime.tests.test_effectwitness_pilot runtime.tests.test_effectwitness_pge -v`：首轮 58 tests，exit 0；随后增加隔离/严格类型/伪成功测试并纳入全套。
- `python -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v`：最终 **141 tests，9.184s，OK (skipped=2)，exit 0**。`test_docker_integration.DockerIntegrationTests` 与 `test_rpf05_runtime.Rpf05RuntimeTests` setUpClass 均因 `Docker provider unavailable: RuntimeFailure` 跳过。OTel 负控的队列/导出 timeout 日志不等于测试失败；OTel 测试已运行通过。
- `python -m runtime.runproof_runtime.effectwitness.cross_trial --domain ops --output spikes/rpf-44/sample-ops-witness.json`：exit 0；`--domain order`：exit 0。
- 实际新/旧公开样本在独立 Python 进程内，import guard 阻止 sqlite3/socket/docker/provider/pge_provider/engine/orders/ops/cross_trial；对两个文件分别执行 CLI 有锚/无锚/错误锚，预期 exits 0/2/3，矩阵断言 exit 0。测试亦对两域 fresh fixture 执行同样子进程矩阵。
- source-map 与 sample 内 issuer.source_digest 一致；`git diff --check` exit 0。未运行 Web/Maven/Cloud/Golden Demo/Hosted Gate；可选 reviewed-artifact verifier `NOT_RUN`，本轮证据不依赖刷新旧 Reviewed Artifact。

| 负控 | 明示结果 / reason code |
| --- | --- |
| 未注册 domain / 未知版本 / 非法 tool / 额外字段 | `DOMAIN_NOT_REGISTERED` / `WITNESS_SCHEMA_VERSION` / `EXECUTION_CONTRACT` / `EFFECT_FIELDS` 等 REJECTED |
| 内部重算摘要但沿用旧可信锚 | `FILE_SHA256_MISMATCH` |
| wrong owner/env/reader | `EXPERIMENT_IDENTITY` / `AUTHORITY_ENVIRONMENT_IDENTITY` / `AUTHORITY_READER_IDENTITY` |
| 缺失/复制/错误 operation receipt、错误 effect_count | 不能冒充原成功：`LIVE_ORACLE_MISMATCH`；在线已验证坏状态由 oracle 给 `VIOLATION_CONFIRMED` |
| 缺 authority / malformed shape | `AUTHORITY_SNAPSHOT_FIELDS` 或 `WITNESS_STRUCTURE_INVALID`；在线 unavailable 为 `INCONCLUSIVE` |
| Tool 与 authority 矛盾 | `TOOL_RESULT_MISMATCH`；伪 APPLIED 而无真实效果的在线 oracle 给违规，不签发业务成功 |
| 逆序/重复事件或时间回退 | `EVENT_ORDER` / `EVENT_IDENTITY` / `EVENT_TIME_ORDER` |
| 夸大归因/再现、外部来源伪装 | `CLAIM_OVERREACH_OR_MISMATCH` / `CAPTURE_SOURCE_LEVEL` |
| planned 但未触发 | 实测确定性夹具 `NOT_TRIGGERED`，不能重标为 TRIGGERED |
| dependency 不健康 / revision 前提错误 | `CONFIG_PRECONDITION_OR_DEPENDENCY`，真实 DB 前后字节摘要无变化 |
| UNKNOWN 再调用 / 无法读回 | `RECONCILE_REQUIRED_BEFORE_TOOL`；保持 pending，失败 trial 保留 receipt/effect_count=1/generation=0 到 task quarantine |

最后一项隔离由测试制造并检查后恢复到本任务原路径，经正常 reset/remove 清理；无未决 quarantine。单测的时序及 fault 证据不充当额外研究 trial 或生产故障证据。

## Git、资源与剩余边界

许可 tracked 变更仅 `runtime/runproof_runtime/effectwitness/{contracts,orders,witness_verify,cross_contracts,cross_core,cross_trial,ops,ops_oracle}.py`、`runtime/tests/test_effectwitness_{ops,pilot,pge,witness}.py` 和本目录 README/RESULT/单份 Ops sample。旧三组测试只做 task-owned fixture 路径兼容。未修改项目状态、history、AGENTS、CI、Web、Control Plane、依赖或旧 sample。

所有命令先设 `PYTHONDONTWRITEBYTECODE=1` 和 TEMP/TMP/TMPDIR 到 `.local/rpf-44/tmp`。本轮 DB、测试临时 JSON、测试 sandbox 与空临时目录已清理；仅在 ignored `.local/rpf-44` 保留小体积回归日志、两次 trial 摘要和持久预算预留作为本轮本地审计记录。`.local/quarantine/rpf-44` 无残留业务文件。未读写旧任务 local。用户 `?? docs/reviews/` 保持未跟踪且未进入/暂存。

结果只证明受限本地跨域复用与内容一致性；即便 `VERIFIED_ANCHORED`，issuer authenticity 仍 `NOT_ESTABLISHED`，单次运行只有 `CORRELATIONAL_ONLY / NOT_TESTED`。Docker 正式接入、运维真实 LLM PGE、PKI、Live Lab/Web/API、正式 Worker/Control Plane 权限均未实施。

后续 API-backed Lab 已具备可复用的冻结合同、ports、白名单 feedback、离线证书版本分发。真正开放 API 前仍需决定鉴权/隔离、并发与原子会话预算、失败隔离与查询生命周期、路径/输出所有权、Web 的事实/结果/分析分层和只读证据取回。当前串行 CLI 不具备并发调度或多租户安全保证；不应直接暴露为公共服务。本轮未创建 RPF-45，TASK_COMPLETE 不等于 EVIDENCE_ACCEPTED 或 STAGE_ADVANCED，后续由 Architect/Main 独立审查。
