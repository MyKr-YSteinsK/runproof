# TASK_RESULT｜RPF-46 / rev-1

Status: Complete (`COMPLETE`)

本轮完成一次新鲜 Desktop 浏览器会话：真实 DeepSeek 两轮 Tool Calling → 新鲜订单退款 → 独立只读 Authority/Oracle → 精确反馈回注 → 第二轮选择 → 状态 Diff/证书资格/用量。交付为竞赛分支普通 push，不代表 main 接受、部署或发布。最终 Commit/Push SHA 与远端独立读回在聊天回执中给出，避免本文件 SHA 自引用。

## 1. Identity / CURRENT STATE / TARGET INTENT

- 实际 root：`D:\CS\runproof`；origin：`https://github.com/MyKr-YSteinsK/runproof.git`，公开仓库身份 `MyKr-YSteinsK/runproof`。
- Parent：`codex/rpf-45-api-backed-effectwitness-lab@4bebed83abde36feb129a737335fb1d37cf13b1a`；新分支：`codex/rpf-46-live-pge-lab`。创建前本地/远端未占用；push 前再次独立确认目标 ref 尚不存在。
- main 两次现场独立观察均为 `bda0cd49e50e3181f604324e94877a24b9885334`；未合并竞赛分支链。现有 push workflow 仅 main 自动触发；本 feature branch 不触发发布/部署；未手动启动 heavy workflow。
- 初始 tracked/index clean，只有预存 `?? docs/reviews/`。该目录始终未进入、列举内部、读取、改写、暂存或提交。没有扩大到相邻项目或更改治理/Project State/历史/CI/Java/依赖。
- RPF-45 仅通过有限账本元数据及既有服务行为核对：两个旧会话仍 COMPLETED、剩余免费额度1，旧 ledger SHA 始终为 `93ba1ed1e8e1c542023008c0f9f0f1c3b8a319c26ea51a2ffab29d8c1181deca`。未消费、重置、迁移旧额度；未读取旧 RPF-40～44 local 资源。
- 用户另行要求的 Plan 原样复制已完成：`D:\Downloads\RPF-Plan-46-实时PGE探索接入与Web证据反馈闭环-rev-1.md`，SHA-256 `0f1bc0105f6cd7ea424d2f87808984a05e3fcffe5596bb63ad9c82037147e8de`，与附件字节一致。

CURRENT STATE：订单真实 PGE 与订单/运维免费确定性模式共享本机 Gateway；新付费额度已经用完，只能读回本次会话。TARGET INTENT：这次闭环支持有限反馈驱动机制与跨域共享核心方向；未取消运维最终产品目标，也未证明 ops Live PGE、一般策略优势或生产能力。

## 2. 实现决定与范围

- 新 `lab_exploration.py` 持有 `PGE_LIVE_ORDER`、`rpf-lab-plan-v1`、`rpf-lab-exploration-v1`，新 `lab_evidence.py` 提供 `rpf-lab-trial-v1` 的离线内容核对。新 `/explorations` 路由不放宽旧 POST `/sessions` exact DTO。
- 同一 `SessionStore` OS owner lock 与同一 RLock 管理两种 mode，1 active/0 queued；跨模式 busy/未决都阻止新写者。旧最多3 trial 和新最多1 session 的账本分开。
- 新 reservation marker 独占创建并 flush/fsync，后原子保存 ledger，才启动线程；请求先记 ATTEMPTED/未知 usage，再 socket；trial 先预留7步骤、Run/Operation，再 SQLite。取消/错误/重启/换 request_id 不返还额度；已预留但遗失或损坏 ledger 拒绝启动，不自动补做。
- 复用 RPF-42 `initial_messages/tool_definitions/parse_choice` 与原 stdlib HTTPS transport；新增重复 JSON 参数键与协议身份负控。固定三候选，两轮同枚举；无 controller 指定第二项，无 B0 真实重跑，无自然语言理由/隐藏推理持久化。
- 复用共享 `cross_trial`、Budget/Orchestrator、OrderSandbox、独立只读 AuthorityReader、订单 Oracle。只增加服务端 RPF-46 存储路由和会话 deadline 检查；旧业务/Witness 合同不放宽。Ops 的 RPF-46 storage 支持仅用于隔离免费兼容夹具，无运维付费入口。
- 七个 trial 动作在会话层先消耗/预留，实际 trial 必须回报7步且 Provider=0；两次 Provider 预留各1步，共16。新限制主动收紧至2个实际请求，低于 Plan hard4；不会把异常余量用于补美观。
- Web 新入口、严格 DTO、两次选择/反馈关联、每轮 fault/状态 Diff/收据/cleanup、研究及成本；三种来源同时显示。免费 mode 文案明确自身不使用 Explorer。中英文只改变展示文字；事件深链、身份、hash不变。
- 原 `/api` 代理、canonical 页面权限不变，无新增 Java 写入口，无静态 fallback。server-only bearer、loopback、Host/Origin/Fetch-Site、JSON/大小限制保留。

## 3. Source identity 与两次 focused commit

实际 Live 所用代码已保存在实现 checkpoint commit **`27dab792bdf7bc9e5fe60e92d2d6eb1b42d56e51`**。会话冻结及 Witness 声明的包源码摘要为：

`11daf0f8a97d35e6fb9c28fd990cdc9be5755035df2eba1d6438dd5a495570cd`

它对 effectwitness 包全部 `.py` 的文件名/hash map 求摘要，先统一 CRLF→LF。实际运行后现场读回源码摘要与冻结摘要一致。

收口审查随后修复一个失败状态文案：未决状态本已禁止启动，但 capability 的 explorer 标签可能仍为 AVAILABLE；现在降为 UNAVAILABLE，并新增断言。此后**没有重跑付费会话、没有改写既有账本/Witness/report**。最终交付包摘要为：

`1006c5c8ee816ece330fdb47c5be6c43a504e93f14eacdccd4e5ab242803657f`

因此本次真实 Provider 证据精确对应前述 checkpoint；后续两行 capability 修正由16项免费聚焦测试覆盖，未将旧 capture 的 source_digest 改成新值。最终收口 commit 包含此修正、断言与本 RESULT；完整 ref 见聊天回执。

## 4. 唯一实际 Live 会话

- ID：`exploration-a3cdf741b7e34f4f97c07228fdf9b679`。
- Plan digest：`cac5b623be53314faf0e0e8fc9ee09a8ce4f8439a6d6cb3bf9b5db0f38fb5493`。
- 冻结/创建：`2026-10-17T16:22:02.278261+00:00`；完成：`2026-10-17T16:22:04.661420+00:00`（北京时间10月18日00:22）。时钟用量2.372秒。
- Explorer=`LIVE_EXPLORER_DEEPSEEK`；Target=`DETERMINISTIC_CONTROLLED_TARGET`；Source=`LIVE_LOCAL_SIMULATION`；`RATIONALE_NOT_RECORDED`。
- 两次请求均到官方 `https://api.deepseek.com/chat/completions`，HTTP 200、RECEIVED。请求和响应 model 均为 **`deepseek-flash`**。官方文档映射 V4.1-Flash-1017；API 响应别名没有独立提供内部权重证明。HTTP x-request-id 未提供，记录 null；response_id/call_id完整保留。

| 轮次 | 模型实际选择 | response_id | tool_call_id | input/output/total tokens |
| --- | --- | --- | --- | --- |
| 1 | normal | `f426f71c-1408-46c5-99f7-c2dc87743cb7` | `call_00_ZCn0DvttlGWTJGJU3iiC7231` | 669 / 36 / 705 |
| 2 | response-lost | `8951a316-12c0-495a-ad76-c9d40044d08a` | `call_00_NV65ODes1GVOUU8JDqNA4853` | 869 / 38 / 907 |

合计：**2 attempts / 1 session / 2 physical trials / 16 steps / 1,612 tokens**；输入1,538、输出74；usage_known=true、pending reservation=0、automatic_retries=0。无未知用量、超时、Provider错误或付费补测。

计价按执行时核验的官方峰值 cache-miss 输入 USD0.30/M、输出 USD1.20/M，USD/CNY保守上界10。估计上界 **¥0.005502**，不是实际账单/市场汇率证明；硬上限仍¥1.50。原 RPF-42 历史结果没有参与本次用量或研究计算。

第一轮实际反馈 hash：`5cc9789a5034104ee1627e2afc9919dc77dce39d6026b20cb690ec9873714912`。事件14 `AUTHORITY_FEEDBACK_VALIDATED` 先于事件15第二轮 `PROVIDER_INPUT_FROZEN`；后者记录原 call_id、相同反馈hash及 messages hash `9f9b450347e8a4356c9d0ffe3eb70444b40d11023991b9b5e686f4f029cfe921`。Provider请求2的 `tool_results_submitted` 正是第一轮call_id。免费协议测试直接比较请求2的 role=tool/canonical内容与真实 trial反馈，检查两轮候选完全相同及未来/B0结果不泄漏。

## 5. 新鲜业务、四轴与证书

所有业务标识均为本轮随机生成的虚构订单。单份脱敏详细记录为 [session-report.json](session-report.json)，没有 raw Prompt、自由文本、隐藏推理或凭据。

| 项目 | 第一轮 | 第二轮 |
| --- | --- | --- |
| Run | `rpf46-2c7a40d4c4a94fe692e1d82443dcf22a` | `rpf46-b4e1ac6d14cb445fa3e9116c1f46c1f9` |
| Order | `order-rpf46-2c7a40d4c4a94fe692e1d82443dcf22a` | `order-rpf46-b4e1ac6d14cb445fa3e9116c1f46c1f9` |
| Operation | `refund-rpf46-2c7a40d4c4a94fe692e1d82443dcf22a` | `refund-rpf46-b4e1ac6d14cb445fa3e9116c1f46c1f9` |
| Receipt | `receipt-4d2fa30dd5a1d952f9f19744` | `receipt-b38e318e44ffbf765eb36d63` |
| 独立 before SHA | `1bdcb83b9ce39f66c54195ead2e8a92ff5de048e88aa217feafbdfd576d91556` | `48b7d73003cd6198df98e8f6e8cf823a269a8cbee36610435ea8b0de9249282b` |
| 独立 after SHA | `100c147fee2e0b3218cba0efed9ae9f9e075455921af60406bddaab8e10a3e81` | `a1469c9260472688f0fe22f78770ecbb6f1f9401cab56bb2ab6ae12e4edab259` |
| Fault planned/triggered/observed/reconciled | false / false / false / false | true / true / true / true |
| 激活 | NOT_PLANNED | TRIGGERED；UNKNOWN_OUTCOME→RECONCILED_COMMITTED |
| Witness | NOT_ISSUED_PROFILE_NOT_ELIGIBLE | rpf-effect-witness-v2 / CONTENT_CHECKED_LOCAL |

两轮均真实 `PAID→REFUNDED`、`refunded_minor 0→2500 CNY`、`revision 0→1`，独立 reader各读到唯一 committed receipt。Run=PASS、Effect=`CONTRACT_SATISFIED_IN_RUN`、Attribution=`CORRELATIONAL_ONLY`、Reproduction=`NOT_TESTED`；触发受控故障不等于退款合同违规。normal轮未被伪签为故障证书。

第二轮 Witness 为9,922 bytes，SHA-256 `aca81bd9fa12494171fcf95d7f75393f99b0bca0af9ce6027a2311e417818220`；经实际下载路由取回同一bytes、浏览器SHA核对，再独立离线 verifier 得到 `UNANCHORED_INCONCLUSIVE`、exit2，原因 `TRUSTED_EXTERNAL_SHA256_REQUIRED`。没有把自报SHA当外部锚；issuer authenticity始终 `NOT_ESTABLISHED`。

Session包装离线检查重算快照/Oracle/fault/feedback及轮次关联，返回 `CONTENT_CHECKED_LOCAL`、exit0；实际Witness另走原严格verifier，二者信任边界分开。免费隔离子进程禁用 socket/HTTP/SQLite/Provider/执行器导入也通过；篡改归因拒绝。两份旧样本原bytes/hash不变，分别用已审外部SHA验证exit0。

## 6. L1 / L2 / H1

- L1=true：两次真实合法模型选择，真实反馈与第二轮输入存在精确身份链。
- L2=true：本次候选确实改变，第二轮新增 `fault_activation=TRIGGERED`。冻结指标为 `rpf46-activation-fact-set-v1`；新随机 Run/Receipt ID 不计信息增益。
- H1=`LIMITED_MECHANISM_EVIDENCE_ONLY`。没有去反馈反事实、B0重跑或统计对照，不能据此声称反馈导致改选、一般策略优势或统计显著性。
- 免费测试包含 planned-untriggered重复与response-lost重复，均合法完成、L2=false/H1=NOT_PROVEN；未强制模型改变选择，也未重开paid session追求观感。

## 7. A-01～A-10

| Gate | Status | 实际证据 |
| --- | --- | --- |
| A-01 身份/范围 | PASS | root/parent/main/origin/branch/AGENTS/ignore/workflows核对；无冲突用户修改；Plan副本已字节验证；reviews保持未跟踪 |
| A-02 严格合同 | PASS | 新版本DTO、预冻结两轮全部候选合同/预算/身份；旧endpoint拒绝新mode；额外参数/非法工具/候选/重复键/错模型均拒绝 |
| A-03 写者/持久额度 | PASS | 同一OS锁/RLock；双向跨模式busy；同键返回同session；请求/物理trial写前预留；取消、重启、缺usage、坏/遗失ledger、存储失败负控；实际重启后余额仍0且请求仍2 |
| A-04 Authority | PASS | 三种profile由真实SQLite免费夹具覆盖，实际Live两轮读回唯一收据；UNKNOWN先reconcile；中断已提交DB隔离不reset，夹具确认后才恢复清理 |
| A-05 反馈链 | PASS | mock直接比较第二请求role/tool_call_id/canonical反馈及messages hash；真实事件14→15、Provider提交call_id与hash相合；无未来/B0值 |
| A-06 Witness | PASS | normal/未触发不签发，response-lost原v2验证；缺Authority、错hash/issuer/session/归因拒绝；旧v1/v2样本hash/anchored验证通过；本轮不冒称anchored |
| A-07 实际Explorer | PASS | 新会话两次真实HTTP200 Tool Calls、两个fresh trial；具体response/call/model/usage如上 |
| A-08 研究诚实 | PASS | 本次L1/L2机制证据成立；仅CORRELATIONAL_ONLY；合法重复负结果测试通过，无额外付费实验 |
| A-09 Web/回归 | PASS | Runtime165项：163通过、Docker2组SKIPPED；Web57/57、typecheck/build exit0；capability修正后16项免费聚焦通过；实际Chromium入口/刷新/双语/event深链/证书核对/断连/只读恢复完成 |
| A-10 Git/交付 | PASS | 白名单文件、凭据扫描0命中、唯一RESULT与一份脱敏report；两次focused commit、普通分支push和独立ref核验；最终SHA见聊天回执 |

实际命令与返回：

```text
python -B -m unittest discover -s runtime/tests -p 'test_*.py' -v
  exit 0; Ran 165 tests in 15.033s; OK (skipped=2)
python -B -m unittest runtime.tests.test_effectwitness_live_pge -v
  capability修正后 exit 0; 16/16; 4.884s
npm test
  exit 0; 14 files / 57 tests
npm run typecheck
  exit 0
npm run build
  exit 0; 内含typecheck; Vite7.3.6; 150 modules
  保留现有大chunk提示（约1.306MB未压缩），无build error
witness_verify 旧v1/v2 --expected-sha256 <既定外部摘要>
  各exit 0 / VERIFIED_ANCHORED；issuer仍NOT_ESTABLISHED
witness_verify 新下载Witness（无external anchor）
  exit 2 / UNANCHORED_INCONCLUSIVE（预期降级）
lab_evidence 新Session导出
  exit 0 / CONTENT_CHECKED_LOCAL
git diff --cached --check
  exit 0
```

Python3.14.6、Node24.16.0、Vite7.3.6；无依赖安装。Docker daemon/provider不可用，两组既有测试明确跳过，不声称正式Docker能力已验收。

## 8. 实机与恢复观察

本机 IAB Chromium实操，不以静态截图代替验收：默认无paid flag时 DISABLED/按钮禁用；显式启用后 AVAILABLE、余额1，浏览器只点击一次创建。真实两轮结果展示正确；Enter键可执行证书字节核对并出现已核对下载链接。下载路由实际bytes在本任务临时目录取回并离线验证，未让浏览器另写宿主Downloads。

选择事件15，切换英文并刷新，URL `?event=pge-event-15`、session/plan/hash/两轮事实不变；切回中文仍同身份。只停止记录中本轮Gateway，页面自动变为 `GATEWAY_UNAVAILABLE / INCONCLUSIVE / SNAPSHOT`、保留只读已加载事实、撤掉下载链接并禁用证书动作。停止余下本轮Vite、重启原服务后仅读回相同Session，COMPLETED、2请求/2trial、余额0；未自动重跑。

免费设置仍有order/ops，Provider=0、旧余额1；`/runs` 实机显示 canonical API `PLATFORM_UNAVAILABLE / HTTP500`，明确不回退fixture。未为此启动Java服务；其余旧只读路由/代理由既有Web回归保护。

本机截图：`.local/rpf-46/live-browser.jpg`（完整证据页）、`live-overview.jpg`（可读反馈链）。最终服务均停止，4185/8765无listener，process record已移除。

## 9. 清理、自动审批与留存

两个实际trial均先按owner/generation reset、读回零收据并删除精确SQLite/空目录；cleanup=`RESET_AND_REMOVED`、generation1、receipt_count_after_reset0。任务结束扫描没有业务SQLite、没有本轮未决mutation/receipt。

自动审批曾拒绝“测试后启动服务”的组合命令，只返回 `blocked by policy`；后续把免费测试与已审启动器分开，单独测试通过后启动成功，拒绝没有消耗Provider次数。另拒绝本轮临时目录递归删除，同样无更具体理由；没有通过其他语言/工具绕过删除。

按Plan允许的可逆路径，独立检查绝对源/目的端点与无SQLite后，移动4个本轮生成目录至唯一 `.local/quarantine/rpf-46/cache-hold/`：

| 分类 | 文件数 | bytes |
| --- | --- | --- |
| tmp：测试/构建临时产物与临时Session/Witness导出副本 | 806 | 10,691,280 |
| compat-runtime：已清空夹具目录 | 0 | 0 |
| node-cache | 16 | 2,514,311 |
| web-build | 3 | 1,413,619 |
| 合计 | 825 | 14,619,210 |

无未决DB，隔离物主要为缓存/测试输出；这是尚未删除的14.62MB，不宣称已释放磁盘。后续标签测试只创建临时夹具并正常清理，空tmp根已移除。旧 RPF-45 的18.2MB cache-hold始终未触碰，也不计入本轮清理成果。

本轮 `.local/rpf-46` 最终保留11文件/489,818 bytes：不可重置的付费reservation/ledger、唯一合格Witness、2张浏览器图、Runtime/Web/build/聚焦测试日志及短服务启动日志。没有持久化secret、freeform prompt/response或隐藏推理。Git只含一份中文RESULT/README和一份脱敏小型研究report，无新公开Witness样本、无大量阶段报告。

## 10. 交付与下一边界

交付仅 `codex/rpf-46-live-pge-lab` 的focused commits→普通push→独立远端ref读回；无PR、merge、tag、release、publish、deploy、云服务或公网监听。Git使用现场既有代理与OpenSSL backend，不关闭TLS校验或修改全局配置。最终远端main观察与源/分支SHA以聊天回执核验为准。

尚未证明：ops Live PGE、WorkSwarm、RPF-28 Docker正式接入、Durable Worker/Java Job、PKI签名、外部issuer真实性、真实支付/生产、统计策略优势。没有创建下一Plan或自动扩大这些边界。
