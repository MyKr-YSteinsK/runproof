# TASK_RESULT｜RPF-45 / rev-1

Status: Complete

本轮完成本机 Gateway→真实 Desktop 浏览器操作→新受控业务事务→独立 readback/oracle→真实 Witness→刷新/深链取回。所有必要 Gate 已完成；交付是独立分支 push-only，不代表 main 接受、merge、发布或阶段推进。最终 commit/ref 与 clean 观察在聊天交付回执中报告，避免本文件的 SHA 自引用。

## Identity / scope

- 实际根：`D:\CS\runproof`；origin `https://github.com/MyKr-YSteinsK/runproof.git`，公开仓库 `MyKr-YSteinsK/runproof`。
- parent/base：`codex/rpf-44-cross-domain-witness-core@1d2095bc26177b165f299e9ac1ec5edfab860983`；工作分支 `codex/rpf-45-api-backed-effectwitness-lab`，现场确认空闲后创建。
- main 观察值：`bda0cd49e50e3181f604324e94877a24b9885334`。初始 tracked/index clean，仅 `?? docs/reviews/`；未进入、列内部、读写、暂存或提交该目录。
- Git 初始 TLS 握手失败，先经 GitHub connector GET ref 独立确认 parent/main 与分支名，再创建本地分支；后续 `git -c http.proxy=http://127.0.0.1:7897 -c http.sslBackend=openssl ls-remote ...` 成功。不关闭 TLS 校验、不修改全局 Git 设置。该命令组合为本机现存代理的有界解决方式。
- push workflow 仅 main push/PR(main) 和手动入口，没有本 feature push 的部署副作用；不启动 hosted gate/手动 workflow。PR/main merge/tag/release/publish/deploy：NO。

tracked 修改：新增 `effectwitness/lab_store.py`、`lab_gateway.py`，聚焦适配 `contracts.py/cross_trial.py/orders.py/ops.py` 的存储任务与回调；新增 `test_effectwitness_lab.py`，仅重定向旧 `test_effectwitness_ops.py/witness.py` 夹具；Web Lab 模块、App 路由/AppShell、独立 Vite proxy、Web README；本目录 README/RESULT/启动器。无依赖/lock/CI/Java/项目状态/旧 spike/sample 改动，无新公开 sample。

## Gateway 与安全决定

采用 Python stdlib HTTP Gateway + OS 文件锁/RLock + canonical JSON 原子账本。仅 `127.0.0.1:8765`，Vite 显式启用后在 `127.0.0.1:4185` 服务。4173 origin 现场出现另一项目页面，改用隔离 origin；没有清除用户缓存或操作那个项目。

新 `/effectwitness-api` 与旧 `/api` 分离，原只读 token/proxy 语义保留。启动器生成随机 server-only bearer，经环境传递，未写 credential 文件；不使用 `VITE_*`，不进入 bundle、Session DTO 或普通日志。Gateway 默认不启用；Host、Origin、Sec-Fetch-Site、Content-Type、JSON 大小/字段/路径 exact allowlist 均在服务器检查。8 个 HTTP handler 上限、1 running / 0 queued、持久最多 3 预留，不开放任意路径/URL/命令/业务参数。

Session 写前先持久预留合同和唯一身份。相同 request_id+domain+mode 返回同一 Session，冲突 409；已完成同键 POST 也重新读验 Witness。取消 ACCEPTED 可 CANCELLED；运行中只记 CANCEL_REQUESTED，仍完成 reconcile 后收口。重启发现未决态转 RECONCILE_REQUIRED，禁止自动 replay/新 Session。独立 reader 能确认 owner/env/run/generation 的 task sandbox 才移到固定 quarantine，否则保留原地。损坏/缺失证书使 Session INCONCLUSIVE，清除结果与导出入口。

HTTP 提前拒绝增加最多 4096 bytes 的有界 transport 排空，修正 Windows unread POST 导致客户端 WinError 10053 的问题；JSON 接受仍 ≤1024 bytes，认证前不解释业务内容。此为受审边界内的实现修复，未降低安全断言。

合同仍采用 RPF-44 的严格 `rpf-cross-execution-v1 / rpf-cross-experiment-v1 / owner=rpf-44` 与 Witness v2；本轮只用服务端 `storage_task=rpf-45` 独立输出。旧 schema owner 未放宽。DTO、来源分类、状态/错误码与启动/复现命令见 [README](README.md)。

## 两次真实 HTTP / Browser trial

非单元测试业务 trial **2/3**，两者均由真实浏览器通过 Gateway POST 创建；不是单测、CLI 或历史 fixture。Provider requests=0、tokens=0、费用=¥0、自动重试=0；共享 Budget 各 7/8 步，900 秒上限。

| 身份/结果 | Order | Ops |
| --- | --- | --- |
| Session | `session-cd548b0a48044dc6944de230961ccacb` | `session-7142a8ccbeca4e8c87ffcc469126dfe0` |
| Run | `rpf45-50e8eef7b0e346ae852e57241e2e3b78` | `rpf45-5cc21090ab5e46f6ac1fd54814433e56` |
| Environment | `env-rpf45-50e8eef7b0e346ae852e57241e2e3b78` | `env-rpf45-5cc21090ab5e46f6ac1fd54814433e56` |
| Operation | `refund-rpf45-50e8eef7b0e346ae852e57241e2e3b78` | `apply-rpf45-5cc21090ab5e46f6ac1fd54814433e56` |
| Receipt | `receipt-5b916da27e9349154cfee83c` | `receipt-519208a05a7dec13becdc3d1` |
| 业务 before→after | PAID / refunded=0 / revision=0 → REFUNDED / refunded=2500 CNY minor / revision=1，唯一 receipt | release-v1 / revision=0 / effect_count=0 → release-v2 / revision=1 / effect_count=1，唯一 APPLIED receipt；dependency=READY |
| 执行时间 | 0.129s | 0.117s |
| Witness bytes / SHA | 9922 / `fb667ffb507cd8c137d831001f02c343c7875edcb1bde42c6e30b33893ea0d1e` | 10123 / `e5c537ecdbf9c14653f798c47f839eaed1ee6c9213a1e2cff824568a555a9abe` |

两域都是新 SQLite 事务与独立只读 reader。fault planned/triggered/observed/reconciled 全 true；真实提交后隐藏响应，再由 operation receipt 对账，没有重复 mutation。Session COMPLETED 与 Run PASS 分列，四轴均为 **CONTRACT_SATISFIED_IN_RUN / TRIGGERED / CORRELATIONAL_ONLY / NOT_TESTED**。证据在 reset 前冻结；两者均 RESET_AND_REMOVED、generation=1、receipt_count_after_reset=0，无真实业务 sandbox 残留。

事件顺序及 UTC：订单首事件 `2026-10-17T13:59:19.974376+00:00`、cleanup `13:59:20.086214`；Ops 首事件 `13:59:54.179739`、cleanup `13:59:54.284102`。两者均按 `contracts_preregistered → environment_initialized → authority_before_verified → tool_result_observed → fault_activation_observed → receipt_reconciled → authority_after_verified → effect_verified → cleanup_completed`，事件与 Session 事实逐项引用。原始 snapshots、feedback、完整事件保存在相应本轮 Session Witness，可从 API 深链取回。

来源标签 LIVE_LOCAL_SIMULATION；受测 target 是 deterministic。没有运行实时 Explorer LLM 自主选择，标 **NOT_IMPLEMENTED**；未混用 RPF-42 历史研究。

## 内容核验与源码身份

两个实际下载响应 bytes 与 Session 存储字节/SHA/Run identity 一致；各自在另一个 Python 进程中禁用 sqlite3/socket/docker/Provider/engine/executor imports 后，`witness_verify` 无外部锚得到 **UNANCHORED_INCONCLUSIVE / exit 2 / issuer_authenticity NOT_ESTABLISHED**，业务四轴可复算。Web 仅显示 CONTENT_CHECKED_LOCAL，不把本 Gateway 自报 SHA 升级为 TRUSTED_EXTERNAL_ANCHOR。

- 业务捕获时 package source-map：`7d27a8230cbf5b9bd6062e146ce2a7cd70836a4a7508702a50ff904a719e3c64`。
- 最终 package source-map：`1456be0d6976fc808af07ae931e7c0dbb8c54a5f24c910b8c9b9173d71b1d528`，沿用 package `.py` CRLF→LF 的逐文件 map digest。
- 捕获后仅增加 HTTP 提前拒绝的有界排空与已完成同键提交的 artifact 重新读验；冻结合同、业务执行器/Orchestrator、两个 oracle、Witness validator 未改。因此复用真实业务效果证据，并以最终 Gateway 重新启动、读取同一 Session/证书核验；没有重签、改写捕获时 source identity，也没有额外消耗 trial。
- 旧 RPF-43：9257 bytes，SHA `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e`；旧 RPF-44：10123 bytes，SHA `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873`。本轮 hash/逐字节/已知锚及无锚兼容回归通过；不重签、不覆盖。

## A-01～A-10

| Gate | 结果 | 实测依据 |
| --- | --- | --- |
| A-01 | PASS | root/remote/parent/main/目标名、初始 clean、权限及 workflow 预检；受保护目录仅 status 摘要 |
| A-02 | PASS | 显式启用 CLI 负控；Gateway Host/Origin/Fetch-Site/Auth/Content-Type/size/schema/path；Vite 默认禁用与独立 proxy middleware 测试；实际服务 401/403/400/404 负控 |
| A-03 | PASS | OS 单写者锁；同键 4 并发仅一个 Session；忙时 409；持久 quota=3；排队前取消/运行中 CANCEL_REQUESTED；重启/未知不 replay；提交后未决隔离保留 effect_count=1 / receipt=1 / generation=0 |
| A-04 | PASS | 上述两个浏览器发起的真实新 HTTP trial、独立 readback/receipt/diff、reconcile 与清理 |
| A-05 | PASS | 实际 download bytes、独立无 DB/网络 verifier；局部自有 hash 信任标注；原样本不变 |
| A-06 | PASS | Session/事件 URL GET/刷新恢复、未知 ID、坏/缺 artifact、断连清结果、busy/取消/非法 domain fail closed；无 TTL，过期态不适用 |
| A-07 | PASS | Setup→Timeline→Diff→Witness；zh-CN/en-US 同 identity/URL/hash；readonly routes/链接保留；Explorer/来源/费用准确 |
| A-08 | PASS | 真实 Codex in-app Chromium，1280×720；中文 Enter 启动 Order、英文点击 Ops；轮询见 RUNNING→COMPLETED；深链刷新、中文/英文、404、断连、重启恢复、浏览器 SHA 检查与下载链接 |
| A-09 | PASS（含清理替代） | Runtime 149 / skipped 2 Docker；Web 51；typecheck/build；0 Provider；2 trials；owned cache 删除被自动审批拒绝，按 Plan 移到固定 cache quarantine并记录 |
| A-10 | PASS（push-only） | focused allowed files、diff/secret/scope scan、普通 commit/push、独立远端 ref，最终 SHA/clean/main 在聊天回执 |

### 运行与浏览器证据

- `python -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v`：**149 tests / 10.085s / OK (skipped=2)，exit 0**。`DockerIntegrationTests`、`Rpf05RuntimeTests` 两个 setUpClass 为 Docker provider unavailable；未运行 Docker formal/start/pull。OTel SDK 测试实际通过，测试内导出超时负控日志不当作集成通过。
- `npm test -- --cache=false`：**13 files / 51 tests，exit 0**，包括原 readonly API/routes/locale 及新增 DTO/Hash/default-proxy/Origin 测试。
- `npm run build`：**exit 0**，包含 `npm run typecheck`；Node v24.16.0 / Python 3.14.6 / Vite 7.3.6，148 modules，bundle 仍有 >500KB 的非阻塞 chunk warning。没有加依赖或下载浏览器。
- 真实服务负控：未授权直连 Gateway **401 AUTH_REQUIRED**；跨站 Origin **403 ORIGIN_REJECTED**；合法 origin+非法 domain **400 SESSION_REQUEST_REJECTED**；越权路径 **404 ROUTE_NOT_FOUND**，均未消耗业务预留。JSON duplicate/body/content-type、并发、损坏及取消负控在实际 HTTP 单测中通过。
- 实际浏览器 origin `http://127.0.0.1:4185`；Order 选中事件深链 `?event=event-rpf45-50e8eef7b0e346ae852e57241e2e3b78-06` 刷新后保持 receipt/Session；zh→en 不改 URL、Run 或 hash。Ops 浏览器取回 bytes 并 SHA 复算后显示下载链接。
- 停止已核实 task-owned Gateway，保留 Vite：浏览器显示 GATEWAY_UNAVAILABLE / INCONCLUSIVE，先前结果与证书入口清除，不回退 fixture；重启原 store 后恢复相同两证书，remaining=1，未新增 trial。未知 Session 显示 SESSION_NOT_FOUND；旧 `/runs` 在 Java 未启动时为 PLATFORM_UNAVAILABLE / HTTP500、不回退 fixture，且没有新写入口。
- 1280×720 桌面无水平溢出；键盘焦点 outline=solid。截图 `.local/rpf-45/lab-browser.jpg`；单一浏览器/HTTP身份摘要 `.local/rpf-45/browser-gate.json`。截图仅辅助视觉，真实 POST/Session/receipt/bytes 是闭环证据。未执行手机/Safari，非本 Plan 必要 Gate。

最小定向测试发现并修复的中间问题：Windows owner.lock 第二句柄读触发 PermissionError（改为锁前检查文件长度）；HTTP 提前拒绝偶发连接重置（有界 transport drain）；Vite proxy 类型用当前安装版本的 configure 参数推导；Response mock 重用已消费 body（修正夹具）。都未降低断言。额外独立 Vite 禁用态临时进程命令被自动审批拒绝，未执行；改为既有 Vitest 实际调用同一默认禁用 middleware，另有真实 Gateway 无 opt-in CLI 负控，通过。

## 资源与交付事实

业务资源已按 owner/generation reset/readback/remove；本轮 Gateway/Vite 及明确子进程已停止，4185/8765 无本任务监听，进程记录移除。两个业务 Session 的 ledger/Witness 保留，0 未决业务 quarantine。

自动审批拒绝了已确认 task-owned cache/temp 的递归删除命令，仅返回 `blocked by policy`、无具体原因；没有重复请求删除或换脚本强删。按 Plan 将 `tmp / compat-runtime / node-cache / web-build` **可逆移动**到 `.local/quarantine/rpf-45/cache-hold/`，端点均先核实在项目固定范围内。该目录是生成物保留区，不是未决业务状态：**1057 files / 18,231,257 bytes**。

`.local/rpf-45` 保留 **15 files / 267,616 bytes**，含 2 个真实 Witness、session ledger/OS lock、1 张 JPEG、1 份浏览器摘要及小体积测试/build/启动日志。低于建议 2MB；没有新浏览器 profile。没有访问或清理 `.local/rpf-40..44`、其他项目、用户 Downloads 或旧 quarantine。临时生成物的物理删除因策略未完成，明确保留以上路径；不声称已删除。

唯一正式主回传为本文件及聊天简明回执。最终普通 Push 及 ref 校验不触发合并/部署；用户 `docs/reviews/` 继续单独未跟踪，tracked/index clean 由交付后核验。

## 下一边界

**实时 Explorer LLM 自主选择：NOT_IMPLEMENTED**。正式 RPF-28 Docker、WorkSwarm、Worker/Job、可信发行者/PKI、公网或多租户安全：NOT_PROVEN。没有推断统计优势、Production readiness、发行权限或阶段接受。

下一阶段最小工作应先定义实时 Explorer 的受限 API/会话预算与实际 Provider Tool Calling 接入 Gate，再把真实选择/反馈放进同一 LIVE Session；这需要新的 Provider 请求/费用授权和相应凭据边界。当前只支持本机 deterministic capture，无自动未知状态恢复或账本清额，不能直接对外部署。未创建后续 Plan/任务，也未代替 Architect 做 EVIDENCE_ACCEPTED / STAGE_ADVANCED 决定。
