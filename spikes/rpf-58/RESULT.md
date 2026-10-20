# TASK_RESULT — RPF-58 / rev-1

**Status: Partial**

日期：2026-10-20（Asia/Shanghai）。共享实现、完整双域合成、真实订单和回归已完成；**配置真实执行与完整跨域证书未完成**。直接原因是本轮新冷 Fixture 收尾实现错误造成实际回执丢失，而非 Provider、SDK 安装或 App Control 阻断。按冷启动一次上限未补跑，配置正式 Gate 未获 PASS，因此整体不能 Complete。

## 1. 身份、范围与现场

Root=`D:/CS/runproof`；Parent=`codex/rpf-57-verified-feedback-coverage-exploration`；Base/执行时HEAD=`e05aa7a5d9e902f2d64928ff61d3280c1cefdbd0`。新分支=`codex/rpf-58-cross-domain-pge-core-portability`。origin fetch/push=`https://github.com/MyKr-YSteinsK/runproof.git`。创建前现场核对精确父ref和main=`bda0cd49e50e3181f604324e94877a24b9885334`、新分支不存在、真实Root/HEAD/index/status；仅原有 `?? docs/reviews/`，未进入、列举、读取、写入、暂存该目录。

新 `.local/rpf-58/` 先确认不存在、ignore实际生效、父路径无link/junction。所有临时文件、SQLite、任务JAR、SDK scratch、负控、来源快照和日志均在其内；未读取旧42/53/55/56/57的运行根、marker、账本/raw。固定 SDK/JDK/manifest/JAR 来源仅读。所有已有 tracked 文件保持原样，AGENTS/Project State/history/Web/CI/Java源与旧证书未变。

本轮仅新增白名单内六个Runtime模块、测试、probe、README/本报告和三份JSON，共13个tracked文件；不创建 `cross-domain-portability-evidence.json`。main/父分支没有写操作，不创建PR、不merge、不发布部署、不dispatch工作流。feature push不会触发仅main/PR的Release Gate，其余现有workflow为manual。

## 2. 共享与不共享的实际实现

真实共用入口：`pge_shared_core.py:97 SharedSession.execute_trial`，统一顺序为 input冻结 → 同一Ledger预约 → 静态DomainPort.execute → domain_verdict → shared_feedback.project → 反馈冻结 → 结算。没有按输入字符串动态import/执行进程/选择URL或DB路径。

| 新模块 | 职责与实际证据 |
|---|---|
| pge_shared_contracts.py | 两个静态域、新owner/Base/schema、Execution/Effect/Experiment三合同、预注册Run/端口/source/物理上限 |
| pge_shared_core.py | 单一Task/Session WAL、fsync、独占锁、不可返还预约、未知写入停止、hash链和不可倒退历史；两域同一执行方法 |
| pge_shared_feedback.py | 调用领域Oracle后再产事实；事实限定domain/Effect/Authority，跨域数量NOT_COMPARABLE |
| pge_shared_verify.py | 共用Envelope/source/父账/事件/反馈关系，静态分派两域专用谓词；不能绕过某一侧Oracle |
| pge_order_port.py | 新root构造桥；复用订单原始事务、Adapter和RO Reader；本轮实际验证 |
| pge_config_port.py | 新合同Host/HTTP账本封装；复用SDK协议和HTTP方法；本轮仅合成通过及冷启动收尾失败，正式Java未运行 |

接口审计见 [README](README.md)。旧 `cross_trial.run_trial` storage_task白名单只含44/45/46，旧 OrderSandbox构造器根映射只到旧任务，不支持rpf-58；未调用它们，也未修改旧owned_path。新 Sandbox/Reader仅重接构造路径，保留 `OrderSandbox.initialize/refund`、`OrderAdapter.invoke`、`AuthorityReader.read/validate` 原方法和 `evaluate_order_effect`。旧 ops SQLite 不被当作Java config。

量化结果：六个新Runtime模块共728行，非空708行；四个共用模块非空299行，占新Runtime文件行数 **42.23%**。这只是文件结构行数比例，不是通用性、复用效果或成功率。真实共享分派调用 **1域**；完整合成使用同一方法分派 **2域**。ConfigPort仍有明确复制：SDK identity 30行、run_sdk 21行、domain `_verify_scene` 147行（与旧55函数逐字对照，仅改函数名和模块级新合同校验器）。另外有新Host构造/HTTP账本和生命周期包装；未消除旧57复制债，也没再复制两份整套Session Runner。详见 [portability-assessment.json](portability-assessment.json)。

## 3. Source Gate、冷启动失败与修复边界

初始预检实际核对原直接 CPython3.12.13、pydantic-ai-slim2.57.0/OpenAI3.35.1 的当前RECORD/core/ABI/site-root/runtime mapping，mismatches=0；固定JDK17.0.12。exe SHA=`e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f`，launcher SHA=`74e020321eb8f828f0c2cfe865082fcf94aa6e7cf488e8a744d89b9282eaeb83`。未换解释器、安装、复制exe、改系统策略或提权。

任务JAR已从固定源复制并校验，但未执行：source commit=`0258b9cef02ea74a40989d035c79256c776409c0`；manifest SHA=`33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`；JAR=66,981,576 bytes / SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。readiness-only JVM也未使用。

G1完整合成CLI与负控通过后执行 **一次** `probe.py fixture`。`run_sdk`返回后已经关闭Host；cold_fixture最终表达式却读取 `host.port`，该属性在 `_server=None` 时抛 `HOST_NOT_STARTED`，CLI exit1。结果保存位于此检查之后，所以仅留下started/source/hash，实际SDK报告、Tool轨迹与端口未被持久化，无法恢复实际PID或原始数据。由控制流可推测前面的status/ready/tool/gate条件已通过，但**本报告不以该推测补造PASS或缺失字段**。

修复：调用后立即保存SDK报告/轨迹，started保留完整合同/runner PID；清理检查使用冻结合同端口，不访问关闭对象。新增纯mock回归证明“关闭Host后仍可收尾”和“后续检查失败时capture已落盘”，零SDK/Provider/Java。这些只证明修复代码，不代表原Fixture重新验收。原执行ConfigPort SHA=`58b7e9bc7542bdfd8811ae07682050268c13070a34833de9f4b78c4ea2deff21`；交付修复版SHA=`173ee90df1606dde4f309e484167b4aebb72a917b65894d5507dca271105fd41`，二者明确区分，旧source和失败诊断保留在本轮ignored根。

未重跑cold Fixture、未签伪造result.json、未删除marker或换名规避额度。修复后再执行纯SDK身份核验，共2个metadata进程，不是2个Fixture；前后source-gated identity与offline Gate分开保存。没有读取Provider key；SDK仅接收无Provider/business key的最小环境，父进程loopback审计禁止外部连接。既有安装工具模块只使用固定只读身份方法，不调用其key-presence/preflight/live函数。

## 4. 订单真实受控执行

依Plan建议的“订单优先、配置前置独立”的顺序，在最终源码/G0/G1/订单前置全部通过后执行一次 `probe.py controlled-order`。它使用同一双域预注册Session和同一Ledger，仅运行第一域；配置入口仍必须另行通过合法同源冷Fixture Gate，未绕过该条件。此路径消耗唯一Session marker与唯一订单Trial，不能重新开始双域Run。

Session=`rpf58-session-bcfef9a0ac42493d`，order Run=`rpf58-order-2afb217f6080427a`。初始SQLite新建，订单PAID、paid=2500、refunded=0、revision=0，初始收据为空。确定性Target实际inspect后调用refund_order一次，write-ahead预约先于事务；真实提交后REFUNDED、refunded=2500、revision=1，唯一收据：`receipt-e386bb1cdbe97c962c16ee23`，operation绑定冻结退款ID。

独立AuthorityReader用另一条 `mode=ro/query_only` SQLite连接读取before/after并验证本次owner/Run/environment/source/HMAC；业务Oracle重新计算完整退款和唯一收据。订单fault planned/triggered/observed=false/false/false，未声称post-commit response loss。Agent来源=`DETERMINISTIC_ORDER_TARGET`，不是LLM Target。cleanup关闭连接并通过BEGIN EXCLUSIVE/rollback锁探针，保留合成DB作为证据，无额外业务写入；交付前另一次只读readback与原after逐字段相同，DB原始hash也一致。

同一共享入口的事件seq：input1、trial预约2、dispatch3、退款预约6/结算7、after9、cleanup10、domain returned11、domain verified12、feedback13、trial结算14。反馈fact=`order-refund:full_refund_v1:sqlite_receipt:receipt_unique`，先前事实为空；feedback SHA=`089377736091e3271df2372afb2d22716738efb21e64f28c5ef9324af832054e`。订单领域证据digest=`18f76d137dcbac360074dd780765b44889eef6fe2370be91ef94a2a3f1591329`。

完整实际订单row及账本放在 [session-summary.json](session-summary.json)，该文件是**Partial摘要**，不是完整跨域Witness；外部raw SHA=`17c0c9d64776cc5edcebc5934155ceaae6e9f9c3f5f42d4be6bfefbc04138b16`。同一领域Oracle `domain_verdict`独立重算为SATISFIED。完整证书CLI用此摘要与正确外部锚仍exit3（EVIDENCE_ENVELOPE），防止Partial被当成双域证明。

配置域：formal JVM=0、formal SDK=0、business HTTP=0、POST=0、health=0；状态NOT_RUN。未用RPF55/57旧JSON填补，也没有把冷Fixture MemoryBackend当Java/H2。完整 `BOTH_REAL_CONTROLLED` 证书不存在；结论为 **CORE_TWO_DOMAIN_EXECUTION_NOT_PROVEN**。

## 5. 验证与Gate矩阵

最终 `python -B spikes/rpf-58/probe.py offline`：11项定向测试，完整SYNTHETIC_TEST_ONLY双域Envelope，独立CLI正确/缺失/错外部锚 **0/2/3**。15类重算内部和外部摘要的语义负控全部exit3：domain-swap、authority-swap、source、budget-split、false-effect、duplicate-write、fault-overclaim、cleanup、cross-domain-fact-splice、schema-downgrade、future-feedback、empty-authority、time-reverse、mixed-source、provider。另有合法重复0新事实、未知/无效Authority不产事实、双进程只成功预约一次、损坏账/残锁/未知写入/重启/自由domain/path/参数拒绝、合成改标和旧57证书拒绝。

最终隔离Runtime：`unittest discover -s runtime/tests -t . -p test_*.py -v`，**358 tests / 0 failures / 0 errors / 2 Docker skips**。从精确Base archive runtime/spikes/ci/demo后覆盖8个新源/测试，全部在本轮快照，安全环境无Key、禁Java/Docker/外部网络；旧测试生成的历史名称目录也在快照内，没有访问实际旧运行根。快照哈希与最终树一致。初版357 tests也通过，但它不代替修复后358项结果。

11历史固定raw锚——RPF43/44/48/49/50/51r4/52r3/53r6/55r2/56r4/57v1——在**当前代码树**独立CLI全exit0，原字节/模块未改；包括57 raw SHA=`76dd7077d75e6dd8ad319bb6e17a01209faadee9fe94d276f3b85e73e88abbe7`。这只是旧证据完整性检查，不是重现旧Live。`runtime/verify-reviewed-artifacts.py`、`ci/verify-public-docs.py`均PASS。

| Gate | 状态 | 事实/缺口 |
|---|---|---|
| A-01 身份范围 | PASS | 精确Base/parent/remote/新branch，保护目录/旧源，ignore/link与push routing |
| A-02 共同执行 | FAIL（必要真实双域部分） | 同一源入口两域合成PASS、订单真实PASS；第二域现场缺失，不能宣称R-07完整实际复用 |
| A-03 订单真实 | PASS | fresh SQLite、真实事务/唯一收据、独立RO Reader、共享预约与清理 |
| A-04 配置真实 | NOT_RUN | 冷Fixture捕获失败，未获得前置PASS；正式JVM/SDK/HTTP未启动 |
| A-05 反馈Authority | PASS（已运行/离线范围） | order真实、config合成均走域Oracle与命名空间，未混级；config现场未验证 |
| A-06 共用预算恢复 | PASS（合成及订单现场） | 单WAL不可返还/未知写停止/竞争锁/重启/领域切换负控；真实第二域共用配额尚未证明 |
| A-07 完整真实Witness | NOT_RUN | 合成CLI/15篡改PASS，但无两域现场，禁止签发完整证书 |
| A-08 旧证据 | PASS | 11固定外部锚current-tree exit0，旧模块/bytes不变 |
| A-09 回归/来源费用 | PASS（测试/订单）；FAIL（冷启动记录） | 358/2skip，Provider0，订单锁清理；原SDK/PID/端口回执缺失，不补记 |
| A-10 受限交付 | NOT_RUN | 待focused commit/push/fresh远端核对；即使完成也不改变整体Partial |

Web/Maven/UI、Docker正式场景、Hosted CI/dispatch、发布部署均NOT_RUN，未改其边界。不能把单元测试或SDK源码推断替代配置正式现场。

## 6. 来源、费用、残留和交付

最终订单执行/交付source map（23项）一致，摘要内可见全部依赖；Verifier v1自身SHA=`c9ad122900358ec6af0992085ba7e8a1704629c0498f7cab92abf74c3b0d36cf`。源SHA使用LF规范化，外部摘要hash对原始字节计算。新执行文件如下：

| 文件 | SHA-256 |
|---|---|
| `runtime/runproof_runtime/effectwitness/pge_config_port.py` | `173ee90df1606dde4f309e484167b4aebb72a917b65894d5507dca271105fd41` |
| `runtime/runproof_runtime/effectwitness/pge_order_port.py` | `987df133767ae9e0f1c81839027008f3b4a9170cad89609c29d3366883d8ad9e` |
| `runtime/runproof_runtime/effectwitness/pge_shared_contracts.py` | `1a26014ad923ed204e6435d26699481873de1757317cec7c2c99ef9fb6241282` |
| `runtime/runproof_runtime/effectwitness/pge_shared_core.py` | `420feb5977bbdb78b53b2f87afab8c566634ab8c9b63ac4d32f70d6c0c36e71c` |
| `runtime/runproof_runtime/effectwitness/pge_shared_feedback.py` | `3079c450dfff2d6e0ee3587c1835b75dbc113d68a6875cb2c0f577031b2e4561` |
| `runtime/runproof_runtime/effectwitness/pge_shared_verify.py` | `c9ad122900358ec6af0992085ba7e8a1704629c0498f7cab92abf74c3b0d36cf` |
| `spikes/rpf-58/probe.py` | `86c0fe3ad67bf85e45b86b321b27fd3c64e1d8281f632f3bb32fa723c54366de` |

Provider **0请求/0 tokens/¥0**；真实Explorer未执行，selection_source=DETERMINISTIC_PORTABILITY_DRIVER。1个冷SDK Fixture尝试（未取得保留的PASS回执）、2个零业务metadata进程；正式SDK/JVM/readiness-only JVM=0；真实订单Trial1/SQLite mutation1；正式配置HTTP/POST/health=0。失败后没有第二次SDK或Java业务尝试。不存在Provider usage/pending；订单账两项均DONE，计数不返还。原用户环境Key未读取或改写，无生产凭据、支付或外部业务请求。

本轮保留task-owned JAR、原cold started及执行版source、失败原因、SDK scratch空目录、原/修复后纯Gate、SQLite及只读证据、WAL、负控和快照；不提交DB/JAR/日志/缓存。订单无连接/锁残留。冷SDK父调用已返回且本进程结束，run_sdk的finally关闭Host；**未保留原始PID/端口，独立cleanup回执不足**，如实留为缺口。不会清理不明用户资源。

不宣称真实跨域LLM自主选择、H1/H3统计优势、任意第三方MCP兼容或WorkSwarm；Issuer/数据库独立认证NOT_ESTABLISHED，独立复现NOT_TESTED，attribution=CORRELATIONAL_ONLY。未改旧57观察性L2。

后续最小需求：明确新增一次修复后冷Fixture复验授权，并明确是否允许在原订单现场/当前Session基础上补配置Trial或采用新的独立双域Run；需继续保护已消耗的SQLite、SDK、JVM/POST额度和source身份。不能靠删除marker或换名重试。未自行创建后续Plan、修改canonical状态或推进阶段；证据接受待Architect。

实现与Partial结果按本Plan聚焦交付；首次提交/Push/fresh remote事实在完成后补入，最终完整SHA在聊天回执，不循环amend。

交付扫描：只暂存13个白名单新文件，逐个核对Git暂存blob与工作文件同字节；`git diff --cached --check`通过。新文件secret/private-path pattern与link范围检查PASS，原tracked diff为空。Partial摘要正确锚的完整Verifier拒绝退出码已实际捕获为3；当前ledger无pending/锁，订单只读复查与源码快照保持一致。没有将缓存/JAR/DB/原始日志或用户目录加入Git。
