# TASK_RESULT · RPF-64 / rev-2

Status: Complete

日期：2026-10-22。稳定Context/静态Port/共用Session、两域真实受控执行、新Witness、独立验收、必要回归和安全分支交付已完成。本报告不作 `EVIDENCE_ACCEPTED` 或 `STAGE_ADVANCED` 宣告。

## 1. 现场身份、权限与源冻结

实测Root=`D:/CS/runproof`；origin fetch/push=`https://github.com/MyKr-YSteinsK/runproof.git`。精确Base/父HEAD=`7896e9789015da946b5a057c620b2faa90b57318`，父分支 `codex/rpf-63-real-explorer-target-shared-config-pge`；新分支 `codex/rpf-64-stable-target-context-port-contract` 创建前fresh远端未占用。main只读=`bda0cd49e50e3181f604324e94877a24b9885334`。开始时tracked/index干净，仅原有顶层 `?? docs/reviews/` 可见，本轮未进入、枚举、读取或修改/暂存。

rev-1在G0因原 `pge_order_port.py / pge_config_port.py` 属RPF58历史源码而停止，未写入、未实验、未消耗额度。rev-2明确授权替代 `pge_portability_order.py / pge_portability_config.py`，本轮重新核实全部目标不存在、父链非link/junction、新ignored根check-ignore通过后创建分支与目录。只新增白名单15文件；旧RPF43–63源码/证书/Verifier/测试、旧尾随空格、AGENTS、Project State/history、Web/Gateway/Java/CI与用户材料保持原字节。未调用旧一次性metadata/cold/live，也未访问旧ignored账本；固定SDK安装与Java source bundle仅按既有安全身份方法读取。

Source Map为8个新文件+13个固定低层依赖，LF digest=`fd4b6b0aaf243e646df72331ce1e8da979b6c0f493694f29d215db6331ab25b6`；TaskContext SHA=`6f9d679b8c19175fedbdff4b4bc412ea767d16c9845fce395188cc65475648ed`。G2源码已逐行检查尾随空白，并精确暂存8个source/test/probe后 `git diff --cached --check` exit0，才冻结进入metadata/cold/live。冻结后源码与测试未改、未重演或重签。Verifier=`rpf64-portability-verifier-v1`，LF SHA=`5c2e0d1f963b779d46c703d8edcdd044ab7e07640e7fe8eb585ae6dd77d54a16`。

## 2. Q1–Q5、实际 ABI 与调用图

| 问题 | 结论 | 实际边界 |
|---|---|---|
| Q1 显式Context | 成立 | frozen dataclass持有不可变bytes，public()返回新JSON副本；owner/session/source/预算/合同冻结，root经授权路径与junction校验；bytearray拒绝 |
| Q2 同一DomainPort | 成立 | 静态select仅两类Port；统一validate/execute/verify/cleanup形状及领域结果projection，分别保持独立Reader/GET Oracle |
| Q3 同一共享代码/WAL | 实际观察 | 两个真实受控Trial经相同SharedSession.execute和物理ledger.jsonl，反馈同schema但领域fact前缀不同 |
| Q4 状态分类 | 矩阵与实际均可区分 | 离线NORMAL/FAULT_NOT_TRIGGERED/UNKNOWN/Authority缺席/Violation/Inconclusive；实际订单NORMAL、配置UNKNOWN且已reconcile，Effect均满足 |
| Q5 复制债 | 生命周期与owner耦合实质减少，尚非任意任务框架 | 新Port直接Popen=0/global WORK=0；Context中共用Supervisor一个Popen点；SDK/合同/授权工厂仍固定 |

实际调用链：`probe.live-controlled → SharedSession.run → SharedSession.execute(domain) → static select(domain) → Port.validate_contract → Port.execute(ctx,ct,ledger) → Port.verify → Port.cleanup → common feedback → fsync FEEDBACK_FROZEN/settle`。公共执行函数不根据SDK/SQLite状态分叉，领域选择只在静态allowlist；独立离线Verifier只调用领域verify，不调用execute/cleanup、Provider或业务服务。

两行dispatch都记录 `pge_portability_session.SharedSession.execute`，函数源码SHA=`29f4dc9fe79db6fb5c225ad0c5fa4b3b10f8d451000be05c17e10821ee2629d0`；Port callable分别为新的OrderPort.execute/ConfigPort.execute及各自source SHA。没有把两个旧任务证书或runner当作共享执行。

复用原OrderSandbox.initialize/refund/inspect、OrderAdapter.invoke和AuthorityReader.read/validate；新构造器注入ctx scoped路径与owner，不调用旧枚举owner构造器。原事务、唯一约束、只读mode=ro/query_only与临时attestation保留；离线Witness不是该内存seal的签名。配置复用原ConfigLiveHost的ready/注册/completion/tool/fixture传输、ConfigLiveHttp/Business和固定SDK子进程；新Host强制fixture=True、api_key=None，_provider_request直接拒绝，WAL Provider限额为0。

源行数：pge_port_context.py 120行、pge_domain_port.py 23行、pge_portability_order.py 51行、pge_portability_config.py 97行、pge_portability_session.py 24行、pge_portability_verify.py 53行、test_effectwitness_pge_portability.py 94行、probe.py 35行，合计497行。长行和语义重组影响计数，不能以此推导同等维护成本。旧RPF62/RPF63 Port为194/206行、公共序列167行；新Config Port97行、与RPF63精确共同序列1行，受格式与删去付费Broker影响，**不把这个数字单独当作泛化证明**。可执行调用审计显示旧Port各有2处直接Popen、5处全局WORK；新Config/Order Port两项均0，新的ProcessSupervisor仅1处Popen，实际管理cold SDK/正式SDK/JVM共3个实例，统一预约、received-before-cleanup、退出与WAL记录。SDK cold/formal复用旧版本已经存在，不计作新收益。新增Context/ABI/Verifier本身也增加源码面积，详见assessment。

当前Context授权工厂仍只准RPF64 owner与root；合成测试经显式Context使用独立 `tests/<id>` root，证明Port无全局WORK依赖。SDK身份AST检查与JDK/source bundle helper仍依赖固定旧实现；三工具schema、每域Oracle/合同仍特定。这些是明确耦合，不扩大成插件系统、scheduler、broker或任意Workflow DSL。

## 3. 免费Gate与预检

6个focused测试通过。共用Session运行模拟订单＋配置normal/inhibited/suppressed三模式；矩阵覆盖 `planned=true/triggered=false` 不提升为有效故障、已提交UNKNOWN后的GET-only恢复、Authority缺失、违规与Inconclusive。另测重复退款额度拒绝、错误operation收据、stale revision、Source/owner/Run/Port、负预算、不可变Context/路径/junction、未知写/重启/torn line、Provider直接拒绝和UNKNOWN后重复写拒绝。模拟明确为SYNTHETIC_TEST_ONLY，没有SQLite业务/SDK/JVM或Provider实际运行。各次免费迭代均通过；身份/重放/严格字段在cold之前补强，未修旧代码。

metadata实际1/上限2；CPython3.12.13/SHA=`e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f`，Pydantic AI2.57.0/OpenAI3.35.1，RECORD hashed entries443/1999（总444/2000），mismatches0；Launcher、site/runtime映射绑定与原pin相符。Java17.0.12通过release/exe实际hash核验，不启动额外身份JVM。JAR66981576 bytes/SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`，source commit=`0258b9cef02ea74a40989d035c79256c776409c0`、manifest=`33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`，源文件110/393800bytes核验；运行新task-owned JAR副本。无安装/下载/价格核查。

唯一cold SDK PID9104；Popen/ready/report一致，三工具注册、4次scripted回调、5次completions、returns `[2,3,4,5]`、UNKNOWN→inspect、stderr0、guard空、SDK/Host退出通过。Provider=0、JVM=0、业务HTTP=0；此冷运行不算正式Config Trial。第二cold/第二Session/额外业务重跑均NOT_RUN。

## 4. 唯一真实双域受控Session

Session=`rpf64-session-ece87fc00af7497f`；外层source_kind=`BOTH_REAL_CONTROLLED`。执行器PID21700，配置SDK PID21144、Java PID15492；SDK Popen/ready/report相等。订单Run=`rpf64-order-ece87fc00af7497f`，配置Run=`rpf64-config-ece87fc00af7497f`。源、三合同、每域Agent/Scenario/Environment/Run、端口、工具与预算在业务前冻结。

### 4.1 Order · DETERMINISTIC / REAL_LOCAL_SQLITE

fresh订单初始paid=2500/refunded=0 CNY minor units、status PAID/revision0、receipts=[]；inspect与只读AuthorityBefore一致。唯一refund操作 `refund-rpf64-order-ece87fc00af7497f` 提交后 refunded=2500/status REFUNDED/revision1，独立只读Reader确认唯一receipt `receipt-89ffb0aa1c5d7138dd1668d9`、status COMMITTED、committed_revision1。Oracle=`CONTRACT_SATISFIED_IN_RUN`。所有金额为本地虚构数据，不连接支付系统。

actual init1/refund1，先WAL预约再SQLite业务I/O。fault四维均false，write_ack=CONFIRMED、state=NORMAL。只读Authority与工具结果分开，不用Tool字典自证。cleanup保留数据库，所有连接关闭且BEGIN EXCLUSIVE/rollback探针通过；独立mode=ro审计再次确认唯一收据和目标state，物理数据库SHA=`fd95bde94d53a6ecb0acb4a29c736f5ee40579b657adef2aa27a5b40aaea4ffb`与Witness相同。

### 4.2 Config · FIXTURE_SCRIPTED / REAL_JAVA_H2_HTTP

fresh Java/H2 初始GET current=4041、history=[]；固定SDK scripted inspect→create v1→update v2→inspect。call IDs为 `call_rpf53_fixture_1/2/3` 与 `call_rpf64_scripted_reconcile`，这些是固定Fixture ID，按Run/SDK绑定，不冒充Provider生成的ToolCall。HTTP observation序号3/4/5/6，回注request2/3/4/5，5个completions且usage全0。

update真实HTTP200/code0/item版本2后才保存COMMITTED、stop_writes，局部抑制Tool成功为固定UNKNOWN；同Call ID被回注后scripted inspect只读GET确认PRESENT/v2。父控制器另做GET-only current/history/list，最终value=`rpf53-v2`/v2/history `[2,1]`。planned/triggered/observed/agent_exposed均true，其中exposed指本次真实SDK Fixture收到受控Tool结果；**没有真实模型选择证据**，不声称Agent自主恢复或网络丢包。

实际9业务HTTP/2 POST/1 health，无重复create/update；Oracle=`CONTRACT_SATISFIED_IN_RUN`，state=UNKNOWN_OUTCOME、write_ack=UNKNOWN_OUTCOME、reconciled=true，保留原未知ACK与业务Effect已满足的区别。Authority=`SAME_SERVICE_READ_ONLY_HTTP`，不是数据库外部审计。正常/inhibited只做离线协议测试，未另开正式JVM。

## 5. 单一物理账本、反馈与资源安全

物理 `.local/rpf-64/account/ledger.jsonl` 共80个frame，exclusive lock、append/hash-chain/fsync、torn-line拒绝。OWNER绑定Context SHA；冷/正式SDK、JVM、SQLite setup/refund、HTTP/POST/health、Source/Run、域事件、Oracle/cleanup/feedback与结算都来自同一文件。无Provider子账本；SDK fixture指标只作协议事实。新Session从预约到末次结算 **25.3255064秒≤1200**。

actual metadata1/cold1/session1/trial2/order1/config1/sqlite_setup1/sqlite_refund1/JVM1/正式SDK1/HTTP9/POST2/health1；Provider=0、tokens=0、费用=¥0。冷+正式SDK共2个child；统一Supervisor还管理1个Java，共3个owned child。Provider Key从未获取/读取，官方价格核对NOT_APPLICABLE。所有SDK子进程均无Provider/业务Key，环境只显式传系统项与受限scratch；父控制器只生成合成业务Key。

未知写/未结算写阻止新写和新业务机会，限授权GET-only核查；永久预约不可返还、不能删除WAL/marker重启whole run。SDK失败或Authority缺失不改记Agent FAIL，无法形成成功证书；本次没有平台/SDK错误、未知用量或未决写。

两个domain通过同一feedback函数生成 `rpf64-domain-feedback-v1`，包含同Session、各自domain/run/authority/outcome、domain-prefixed verified facts及evidence/verdict摘要，WAL先DOMAIN_VERIFIED与cleanup再FEEDBACK_FROZEN。第二域PORT_ENTERED绑定第一域已冻结反馈SHA。它证明共享反馈协议与事实时序；本轮没有Explorer，不声称反馈改变选择、跨域信息增益或因果优势，`cross_domain_information_gain=NOT_COMPARABLE`。

独立PID读回9104/21144/15492/21700均退出；cold Host1048、Java1045、正式Host1046端口全关闭。只读数据库审计与文件hash确认一致。Java日志按本地业务Key脱敏，服务终止后client引用释放；公开包无Bearer/Key模式或私人用户路径。不读取Provider Key来做“精确Key扫描”，使用固定字段、源码调用审计与模式检查。JAR、原WAL、预清理收据、DB、正负控与隔离快照保留在新ignored根，未删额度标记。

## 6. 新Witness、负控与回归

[portability-witness.json](portability-witness.json) 原字节84779 bytes，schema=`rpf64-portability-witness-v1`，rawSHA：

`d5798bfa82ef9523039a1461c82842aa9f265703ada492cef3cf068208e5ff19`

独立CLI正确/缺失/错误外部锚=**0/2/3**。合成和真实原件各22类重算Envelope/外部SHA的负控均exit3；budget omission和WAL倒置控制还重连内部hash chain。覆盖角色升级/降级、错operation收据（同时重锚snapshot）、stale revision、缺Authority、owner/Run混源、负预算、Port source、未知SDK、cleanup、假故障、假Explorer/Target、假跨域增益、预算遗漏、WAL倒序、缺readback、Call ID、Source缺失、cold PID、重复POST和假数据库外部Authority。

验证程序无Provider/业务写，只读公开原件和tracked Source，既不依赖旧ignored根也不调用旧runner。完整性hash与程序Verifier不提供Issuer签名、独立复现或生产真实性。真实等级只描述本机SQLite/Java-H2业务，订单仍确定性、配置仍Fixture。

focused6项与16个历史证书的原字节/原Verifier逐一exit0已完成；全Runtime在隔离快照首轮运行412项，2项Docker因不可用skipped，其余通过；测试耗时561.300秒，进程耗时563.087秒。本轮无Runtime重试、Windows loopback错误或业务复跑；最终Reviewed/Public检查均通过。完整历史输入路径/锚、CLI/耗时、源身份和日志引用见[verification-diagnostic.json](verification-diagnostic.json)。未改Web/Maven/CI，本轮不机械重跑Web/Maven或Hosted CI；部署NOT_RUN。

## 7. A-01～A-10与交付

| Gate | 当前状态 | 事实／剩余 |
|---|---|---|
| A-01 | PASS | 精确root/base/新分支/remote/CI/owner/用户保护与rev-2占号核对 |
| A-02 | PASS | 显式immutable TaskContext/静态ABI、低层组合、一个进程Supervisor；复制/耦合审计 |
| A-03 | PASS | 两域同一个具体execute source与单物理WAL，统一域反馈 |
| A-04 | PASS | SQLite唯一退款+RO收据；SDK Fixture+Java-H2真实HTTP/独立GET Oracle |
| A-05 | PASS | 固定source/SDK/JDK/JAR/owner/工具、有限资源、Provider0/不读Key、进程端口清理 |
| A-06 | PASS | 三合同/状态矩阵/未知停写、22重锚语义负控 |
| A-07 | PASS | 仅完整真实双域后生成新Wit，原件SHA与0/2/3，等级无升级 |
| A-08 | PASS；Docker UNAVAILABLE | focused6、Runtime412/skip2、16历史锚、Reviewed/Public、清理与source一致 |
| A-09 | PASS | freeze前及最终新文件diff check通过；精确15文件、保密扫描、focused commit/push与fresh远端读回 |
| A-10 | PASS | 唯一中文结果、Source/费用0、复用变化/剩余债、限制和Git事实分别记录 |

命令：`python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_portability -v`；新probe按metadata→cold→live-controlled各一次；Witness直接CLI见README。全Runtime为 `python -X utf8 -B -m unittest discover -s runtime/tests -p test_*.py -v`，在新task-owned tracked-only源码/证据+8新文件隔离快照内执行；不复制用户目录或旧local。16原Verifier命令及外部锚见diagnostic，Repo checks为 `runtime/verify-reviewed-artifacts.py` 和 `ci/verify-public-docs.py`。

Git交付为精确15文件focused commit、普通push到授权新分支，fresh ls-remote与GitHub commit readback核对同一SHA。main/父分支和旧RPF58 Port/旧RPF63格式行保持不变，不做PR/merge/amend/tag/release/workflow_dispatch/部署/比赛提交。RESULT不循环填自身最终SHA；聊天回执给出精确提交。RPF61 PPTX/ZIP/门户义务不变。

## 8. 下一受限边界与限制

本次证明两域通过显式Context与同一具体协议实际受控执行，可以供Architect决定RPF65是否把新ABI接入新的有限Explorer×Target Session/Web，或先加入订单真实Target。但需新任务owner/预算/候选与反馈合同，不能直接升级旧Live证书或复用本轮已消费额度。本轮未创建或施工RPF65。

当前owner授权工厂仍任务限定、固定SDK/三工具与metadata inspector耦合尚存；领域Oracle与合同本来就需分别维护。没有新真实Explorer/Target、跨域自主PGE、Issuer独立身份、外部数据库Authority、外部独立复现、任意工作流/第三方框架互操作、因果/统计优势或生产部署的证明。本轮完成只限共享内核泛化切片，不代替全部产品MUST验收；研究接受与阶段推进由Architect后审。
