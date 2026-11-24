# RPF-115 rev-1 · 从意图到独立读回

2026-11-24，Windows。同一受控订单在两个中断点呈现不同事实：写前终止时仍是 PAID、零收据；提交且返回被宿主抑制后终止时已经 REFUNDED、有一条收据。两个 owner 都保留原预约，重新打开后的配置库均不存在。调查报告保留记录中的 RUNNING，指向人工处置。完成运行才有成功 Witness。

审查基线 `df81b1b8b6e8807dfde598446ed5d05cab9fe3b3`，实现与包源码 `126c02152c2abc0f77b6e10fe00a209206b1e38c`。执行前本地与远端 main 一致。RPF-74/RPF-96 未跟踪草稿留在工作树。正式样本的源码映射 SHA-256 为 `190483d4f4cd9b94fb2e178f0b73e2d2f6d7e2ecba9de63e53cb27060fcc1934`。使用 Edge 158.0.4370.33、Node 24.16.0、CPython 3.14.6、SQLite 3.50.4。两端在 127.0.0.1:4187/8780 运行，使用虚构订单与配置。业务代码无 Provider 调用入口，每份记录、观察和 capability 的预约均为 0。

## A01–A05 · 存储、运行和中断

基线探针在全新的空目录中拦截 SQLite 的 connect 调用。实参是普通 ledger 路径，未指定存在性模式；拦截时文件仍不存在。基线源码下一步是建表再按行数计算余额。这项证据定位到了可创建空库的路径；没有在原 owner 上删除账本或模拟额度复活。

[持久化实现](../../runtime/runproof_runtime/effectwitness/product_local_session.py) 将独占目录初始化与打开分开。初始化提交 schema 与随机实例身份后才发布 owner 标记。现有库使用 `mode=rw` 或 `mode=ro`。预约与保留标记绑定 owner、request 和 session；台账、标记、原来源或冻结操作不匹配会中止。合成副本上的缺库、损坏、schema 漂移、错误或缺失 marker、预约缺失与半初始化均得到拒绝，校验前后文件摘要相同。两个并发创建者只有一个成功；同一 request 并发两次对应一个 session，每域各一条收据。[回归与子进程检查点](../../ci/test_rpf115_recovery.py)

真实取证的四个任务尝试如下。operation ID 分别为表中完整 session ID 加 `-order` 或 `-ops`，同时也是冻结 environment ID。表中配置计数为 0 的两个运行均未创建第二个数据库。

| 正式尝试 | Owner nonce | Request | Session | 订单/配置收据 | 实际结果 |
| --- | --- | --- | --- | --- | --- |
| 仓库入口 | `7d4056eed6f840a9897d5817424d3ad7` | `99301849-e97e-4265-8814-e4dd2b4bdeb7` | `21eaaeb8f21142a880f86be6aecb3e50` | 1/1 | COMPLETED |
| 子进程写前终止 | `3980209b11aa4f8c8fdee77109e16e04` | `controlled-interruption` | `1cf3a4190c05439bb95aab716e437394` | 0/0 | 已持久化意图与写前观察 |
| 子进程提交后终止 | `60b16c827ff44b99b403ae453d2551cb` | `controlled-interruption` | `a047f256982d441d863f878e5133329a` | 1/0 | 25.00 CNY 已退，原进程未冻结 Witness |
| 解包入口 | `3bf3fab39aae441dbb6ef57ea08ebd7c` | `331160f5-e8f0-4b0a-8579-0fec4ab4aab8` | `2e3b385de5ec433b96f10ff1cf80d6fc` | 1/1 | COMPLETED |

正常任务 attempted 2、valid 2、PASS 2、FAIL 0。另有 2 次刻意终止，业务任务 INCONCLUSIVE 2，中断恢复验收通过 2/2。四次尝试合计 ERROR/INVALID/CANCELLED 均为 0；Agent 质量分母仅含两次正常任务。故障注入属于宿主本地工具返回抑制。提交前的 planned/triggered/observed/agent_exposed 为 true/false/false/false；发生响应丢失的订单为 true/true/true/false。Agent 下一次输入是由已验证读回生成的 feedback。ops 四态均为 false。缺失或错误反馈、错误工具参数、错环境、缺收据及不可读业务库另在隔离回归中检查。策略拒绝与任务完成分别计量。

## A06–A09 · 调查、兼容性和浏览器

完成链路可由事件深链查看 AGENT_INTENT、GATE_DECISION、UNKNOWN_OBSERVED、AUTHORITY_READBACK、VERIFIED_FEEDBACK、AGENT_REPLAN 及第二轮意图的 input_feedback_sha256。每次调查都从新的只读连接检查 environment、operation、状态与收据；未持久化的 before 在报告中是缺口。缺收据时不会从当前状态推断成功。[诊断形成与复核](../../runtime/runproof_runtime/effectwitness/competition_agent_investigation.py)

| 输出 | 实际 SHA-256（SQLite Witness 或独立只读调查取得的锚） |
| --- | --- |
| 仓库 Witness | `d73c033072eb9df0cb7fd2295b757103e2d7063af2bd73c629d52dde39d052cd` |
| 写前中断诊断 | `230f894d73119ed031ffbfb83b0579dd58c884e5cc36bc0cd55806a99a65fac2` |
| 写后中断诊断 | `b4d3a787247828f04b9c69dedca35eca0f407a2bc6b82735887ec08f9c2b3967` |
| 解包 Witness | `e1cd5e929d613025d98201a38ad99b7f19a34387bd0a22aa494c33a5d52ca190` |

四份输出按对应运行身份通过 CLI 的 `VERIFIED_ANCHORED`。成功锚直接取自 SQLite ledger 的 BLOB，与下载字节比对。中断锚在启动调查 Gateway 前由只读进程保存，浏览器导出与其吻合。对照每个数据库、owner 与预约标记的逐文件摘要，重开前后相同。无锚检查仅建立内部一致性，issuer 为 NOT_ESTABLISHED。固定锚下的变更、重算内容摘要后与冻结 operation 不同的读回均被拒绝。

RPF-100、RPF-112 和 Reference Agent 各在本轮隔离目录从基线源码生成一个兼容样本；均使用原 verifier 加锚验证。当前 reader 只读找回其 session，剩余额度为 0。三个原生 Witness 摘要依次为 `45bf094c8fef47cb4ed5548df9fd3075cf4bab9b3a6650fff1cbf997b074830c`、`fc9c758833f012fa6d69eb9dd7c96b481e3e39d23c1c71e2de2b3b91da3f8689`、`b7843cd661a76052fc39cb31126e6b329d2911e07e73528d645a84725d258226`。原历史 owner 未参与实验。

Edge 使用同源请求记录核对旧 pending、显式 session、缺失身份 404、切换、网络断开及恢复、禁止读取 localStorage、键盘 Enter、焦点、事件书签、中文和英文切换。分别从两个中断点和完成运行下载与当前 session 相同的文件。完成页面中的新建按钮经用户确认产生 1 次 POST；刷新、重开和下载产生 0 次。解包后额外延迟一个旧 session 的 GET，再切回正确 session；迟到的 404 没有覆写当前结果。历史页从 Agent 列表继续打开真实详情深链。

同机、相同 production build 参数、独立新浏览器配置、关闭 HTTP 缓存、同一个返回 503 的 capability 条件。以下是 HTTP 请求清单及首次加载的资源文件原始字节数，不含压缩。

| | 基线 | 本轮 |
| --- | --- | --- |
| 初次加载 JS | 1,428,782 B | 290,277 B |
| 初次加载 CSS | 125,044 B | 106,084 B |
| GET 总数 | 5 | 9 |
| JS/CSS 资源 | index-CHbsofnc.js、index-D1HcTjoQ.css | index-7KtopY4N.js、index-Ch4k-w1-.css、CompetitionAgentPage-rWHDLOnI.js、AppShell-Czh3n_nv.js、productLocalApi-BFvaTQCr.js、CompetitionAgentPage-D3bpHrMM.css |

两份清单另外都包括 `/effectwitness/agent`、`/effectwitness-product-api/capability`、`/favicon.ico`。原 App 静态导入 artifacts、canonicalSnapshot 与各页面，原 AppShell 直接导入 artifacts/statistical 的计数。现在入口按路由加载，本地页与共享导航不导入 reviewed corpus。只访问历史路线时才请求 CanonicalApp。历史大 chunk 仍有 Vite 体积提示。工程包一次浏览器完整演示实测 3.887 秒，从独立浏览器验证脚本开始，到新建、观察、刷新、下载及历史导航结束；不含安装、构建和启动器就绪等待。

## A10 · 工程包、回归与复查

新完整 ZIP 1,101,742 B，320 个成员。SHA-256 为 `82bf12d14bda74cc8cb6d4ab5bdfecdcff436364b2dc171de14d9a8899363c00`。独立 verifier 核对成员、源码与内外层 site manifest 后解到全新目录，解包出的 app 自身完成启动、停止、只读重开及 CLI 复核。对同一真实 ZIP 各构造 mode、issuer、release_eligible 缺失、错误类型或改值，保留成员摘要并重算外部 sidecar。9/9 在 MANIFEST_BOUNDARY 被拒绝。[包 verifier](../../ci/test_rpf114_competition_bundle.py)

以下命令均在仓库根运行；`$py` 与 `$node` 指已核对的可执行文件。新实验使用新 nonce 和新解包目录。本轮本地 Python 29/29、Node 1/1、Web 77/77，构建含一次 typecheck。public docs 18 files/7 pairs、reviewed artifacts 和 Golden Demo（15 个 reviewed 引用、14 个选定引用）均通过。Java 和冻结的 Runtime matrix 未变更。

```powershell
& $py -B -m unittest -v ci.test_control_plane_client_transport runtime.tests.test_control_plane_client runtime.tests.test_durable_worker ci.test_rpf100_product ci.test_rpf112_competition ci.test_rpf114_competition_agent ci.test_rpf113_competition_bundle ci.test_rpf114_competition_bundle ci.test_rpf115_recovery
& $node --test ci/test_rpf113_competition_server.mjs
npm test
npm run build -- --outDir .local/rpf-115/web-dist
& $py -B ci/verify-public-docs.py
& $py -B runtime/verify-reviewed-artifacts.py
& $py -B demo/verify-golden-demo.py --root . --json
& $node demo/competition-bundle/build-bundle.mjs $newNonce $py --complete
& $py -B ci/test_rpf114_competition_bundle.py $zip $freshExtraction
```

面试复查可从 [README](../../README.zh-CN.md) 启动，先沿成功会话看两域收据，再按上表提交后中断的 nonce 只读重开，从订单实物回查第二个库的缺失。将诊断导出与独立摘要交给 CLI；改用错误的固定摘要可重现 REJECTED、退出 3。正式结果以候选源码取证。最后文档提交的远端 SHA、产品 CI checkout 和 Canonical Gate 由交付回执记录。原基线的两个 required coverage 步骤分别剩 534、516；此前 Source Drift 已修复。新产品回归不会补记为冻结覆盖。[基线 Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45161996447)

首轮托管回归在 Golden Demo 的历史源码身份检查处失败。Hosted checkout 只取了当前提交，本地完整历史通过。产品 workflow 现在获取完整历史，保留 Golden Demo 原验证规则。后续托管修正仅涉及 CI 取源与本文，工程包和运行源码仍绑定上述实现提交。[首次产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45387408337)

### 本地证据索引

- `.local/rpf-115/formal-126c021/{WRITE_INTENT,UNKNOWN_OBSERVED}/` 保存各自的 report.json、receipt.json、子进程 PID 和停止后的全部文件摘要。终止 PID 为 5364、9996。回归子进程仅在指明事件落盘后通知父进程终止。
- `.local/rpf-115/` 的 `checkout*`、`interrupt-*`、`bundle-*` 中的 independent.json、Witness、诊断、浏览器 GET/POST 清单和验收日志来自本次运行。正式启动和重开收据在同目录的 `launch/<nonce>/<launch-id>/processes.json`；包内在解包目录的 `app/.local/launch/`。启动器按收据关闭对应两个 PID。所有历史 owner、WAL 与此前的封存结果继续保留。
- `.local/rpf-114-complete/2f5835ba54d44da6b3eafc9be487b729/deliverables/` 保存完整 ZIP 和 sidecar。`.local/rpf-115/extracted/` 是本次独立解包，`package-negatives-verified/` 位于本次 rpf-115 目录。旧验证文件及 Router pins 保留原始身份。
