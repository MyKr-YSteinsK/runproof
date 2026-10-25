# TASK_RESULT｜RPF-72/rev-2

Status: Partial（重启后原件正例被 LAUNCH_ENV_BINDING 拒绝；冻结源不改，最终交付双读由聊天补充）

## CURRENT STATE

Windows 原生启动接缝在关机前已恢复并完成N/F；重启后的只读原件复验暴露新的宿主环境耦合，当前整体Partial。原 Driver/child/Guard、SDK RECORD、历史证书及旧 tracked 文件均原字节保留；本轮 24 条路径全 create-only，全部 runtime/失败证据位于新 `.local/rpf-72-rev-2/`。正常与故障双域会话、固定 SDK 压力、原件重锚 CLI 以及两次完整 Runtime 尝试均绑定同一 frozen Source；完整 Runtime 未完成。

## TARGET INTENT

Owner=`rpf-72-rev-2`，Owner ABI=`rpf72r2-owner-source-v2`，ParentChild schema=`rpf72r2-parent-child-budget-v2`。BudgetPolicy 派生250000/160000 child累计、474000可达/600000全局/160000最大槽，11个不可回收槽。native cfg仍计算原常量，但新授权 Gate 在创建 child 前要求严格一致；实际串行 bytes digest、PID、SDK ready/report 与同一 native WAL 顺序绑定。`BUDGET_PARENT_CHILD_CONTRACT_EXECUTED=NO`（关机前运行执行证据保留，但当前复验门禁未全通过），证据层级为 Controller 观察 + SDK 实际执行，child 独立确认未建立。

## PLANNING CONTEXT / Git

Repo `MyKr-YSteinsK/runproof`，Base `bae9c470f015732c0af34e2d4bacf43e4b6fcce8`，新分支 `codex/rpf-72-rev2-win-argv-key-boundary-recovery`；源码提交 `a8c7fe29cd12c9df60b5f72ef805321d11e81893`，已普通push并经Git/GitHub API双读。frozen identity SHA `79858188bd351a94cc4020d1c09d1e705d20777a290611a24bcacabd1e808938`；71条 Source raw/LF 闭包及 SDK/JAR/child pins 见 [source-identity-map.json](source-identity-map.json)。旧rev-1 public identity保持`46295f001bf0b1e9c386186fc714107e0b62c1dc98b50bc8a71b7fd0ff65b569`。未读取旧`.local/rpf-*`；固定 SDK/JAR 精确只读例外保留。父/main 的 G0 与最终双读单独记录；main 基线`bda0cd49e50e3181f604324e94877a24b9885334`，父分支保持Base。此文件不循环记录自己的最终SHA；最终回执commit、24文件API比较及Git/API双读见聊天。

## Gate

| Gate | Status | 证据与边界 |
|---|---|---|
| G0 | PASS | Exact Base and 24 paths absent in local/index/Base/API; owner SID matches; new ignored non-reparse task root; no deployment push |
| R2-A01 | PASS | 71 raw/LF source closure; current R72R2, R72 frozen reference and native reference separated; all old bytes preserved |
| R2-A02 | PASS | Frozen Policy/ParentChild250000/160000 +474000/600000/11slots; 60 strict cfg negatives and pure component |
| R2-A03 | PASS | Original Driver native accept/reject smoke + exact Windows audit, actual serialization/PID/report/WAL; eight SDK boundary components |
| R2-A04 | PASS | One native WAL; physical reserve/settle coverage, crash/orphan/UNKNOWN/direct bypass/duplicate tests; formal replay/Policy parity |
| R2-A05 | PASS | New N and F local two-domain sessions independently verified, finite writes, four states, readonly reconcile, feedback and cleanup |
| R2-A06 | FAIL | Pre-shutdown 150/93/deep4 and CLI0/2/3 valid; post-reboot original CLI unexpectedly exits3 LAUNCH_ENV_BINDING, so current positive CLI gate is not satisfied |
| R2-A07 | FAIL | Final full attempt did not meet Runtime acceptance; exact receipt retained |
| R2-A08 | PASS | Host credential reads0; sanitized absence probes explicitly scoped; runtime loopback only, Provider0/realusage0/API0; owned resource late cleanup |
| R2-A09 | FAIL | Offline verifier depends on current mutable host safe-env values instead of the original historical launch environment; unchanged valid N/F now reject |
| R2-A10 | NOT_RUN | Source commit and this receipt generation complete; final commit/push/API+Git double-read is finalized in chat after report publication |

A10为本报告写入时的最终交付状态；最终聊天在普通push和双读后给出PASS/失败实况。R2-A06/A09因重启后的正例复验失败而FAIL，其余按表中实际状态；不能将关机前的成功升格为当前全部PASS。

## 重启恢复与新的复验失败

关机前N/F、SDK压力和全部负控已经完成；首次full没有结束回执，保留INTERRUPTED_NO_EXIT_RECEIPT，不推断exit/elapsed。第二次full使用新raw快照和独立fixture根，正式业务不重跑。

重启后N/F原始SHA、71条源码、SDK/RECORD、冻结helper与index原字节均一致，但重新执行两份原件CLI均exit3：LAUNCH_ENV_BINDING。四个领域的旧/当前env键集合相同，aggregate摘要不同。原validator的verify_proof从当前宿主SYSTEMROOT/WINDIR/PATH重建old._sdk_env，再与历史launch.env_sha256比对；原件只保存整体hash，无旧safe变量值/逐变量hash，因此不能确定具体哪一变量变化。此处没有读取宿主Key，没有恢复/猜测旧环境，也没有修改Source或旧原件。

当前复验不通过是离线验证依赖可变宿主环境的缺陷；原N/F历史完成事实、Reader与SDK证据不抹除，但无法据此声称当前原件正例门禁PASS。Source Freeze禁止原地修该执行源，需下一授权修订明确历史LaunchEnvironment/LaunchSpec的稳定验证语义。全部诊断见verification-diagnostic.json.recovery_environment。

## Windows Popen Audit

G0实际观察`(NoneType, str, str, dict)`；Windows 先list2cmdline再audit。新校验要求`executable is None`与完整受信argv的`subprocess.list2cmdline`精确相等，固定Python二进制SHA、完整child路径/原字节pin、标志顺序、cwd与原净化env逐项一致，不解析不可信命令、不做contains匹配。成功smoke PID `13792`；独立拒绝smoke PID为空，受控新validator观测参数追加flag后，在原Popen创建child前拒绝。旧Popen/Driver/sys.audit/child均未patch。

原native Driver的`canonical(cfg)`真实返回 bytes被scoped profile观察；同一SHA进入cfg证明、SERIALIZED_INPUT、PID、SDK结果和RESULT_BOUND。hook仅接受精确NativeDriver.run code/self调用帧，ContextVar仅当前父线程活动；两个smoke证实成功/异常均恢复profile并reset context。audit hook无法卸载但活动域外立即返回，不影响其他进程。POSIX未测试，代码fail closed。

## 净化 Key 边界

HOST_PROVIDER_KEY_READ=0，HOST_BUSINESS_KEY_READ=0，CHILD_KEY_PRESENT=false，EXTERNAL_CREDENTIAL_DISCLOSURE=0。原`_sdk_env`仅从宿主取SYSTEMROOT/WINDIR/PATH，再加入任务HOME/temp和遥测/pyc控制；Popen前比较实际env，未查询父环境的Key值或存在性。Java/H2所用内部鉴权票据为任务本地新生成，SDK child不继承该变量。

允许并明确记录`SANITIZED_CHILD_ABSENCE_PROBE`：原child完成report构造中的两处`os.environ.get`保留。本轮R68 smoke/压力/NF共11个已完成child，至少Provider缺失检查11次、业务Key缺失检查11次；全部report false。库层及完整Runtime旧fixture getter总数未动态instrument，NOT_INSTRUMENTED；`ALL_KEY_VARIABLE_LOOKUPS_ZERO=FALSE/NOT_PROVEN`。新manifest兼容字段`key_lookup=0`只按rev-2协议解释为HOST凭据读取0，不能当成child全局getter0。rev-1 A08仍FAIL，未追溯修改。

## 固定 SDK 组件

| Domain | Case | PID | synthetic total hint | SDK结果 |
|---|---|---:|---:|---|
| config-java-http | limit-equal | 15480 | 250000 | COMPLETED |
| config-java-http | legal-high | 12452 | 84600 | COMPLETED |
| config-java-http | limit-minus-one | 24696 | 249999 | COMPLETED |
| config-java-http | limit-plus-one | 13360 | 250001 | UsageLimitExceeded |
| order-sqlite | limit-equal | 20724 | 160000 | COMPLETED |
| order-sqlite | legal-high | 19880 | 54580 | COMPLETED |
| order-sqlite | limit-minus-one | 8020 | 159999 | COMPLETED |
| order-sqlite | limit-plus-one | 23296 | 160001 | UsageLimitExceeded |

legal-high遵守输入上界与保守512输出界，跨过35000。limit−1/等于/加1的最终usage hint刻意超出单槽/input边界，仅验证SDK累计阈值，不称合法Provider预约。成功样本为SYNTHETIC_VALIDATED_USAGE，超额样本只有不可信hint和真实UsageLimitExceeded，无伪造final RunUsage。8组件全部原固定child，业务效果0，Provider0。原SDK固定Python3.12.13/PydanticAI2.57.0/OpenAI3.35.1，JAR原pin与记录匹配。

## 正式 N / F 与唯一 WAL

N Run `rpf72r2-c6a130b872764ddf`，manifest raw `f470e86cf529851031f75b4f8e456db7373e1334051c6ba5980cb969f5e1b24d`，WAL raw `7ad53246ddbdc26bb759e07ab99eeacf444f0a716255cb8e8520f403bea05f87`，430.35s。F Run `rpf72r2-5d697908faa86b74`，manifest raw `0de5e81c9c5cc517ffad8d02587219b8a474373540da148757130b0be0db9a6e`，WAL raw `c961e8f982c6c6bce831a8266d94be51f2dfa1133ea963b1b7791ab8bafc316c`，462.60s。原件仅保留私有根，公开[父子矩阵](parent-child-contract-matrix.json)提供去敏SHA/ID/Oracle/计数。

每场景配置POST2、SQLite虚拟2500 minor全额退款1、JVM1、SDK/Host各2、scripted Explorer2；独立Authority读回计数N=4、F=5。配置独立GET/history证实ABSENT→v1→v2；SQLite mode=ro Reader证实唯一收据与2500退款。N两域四态全false；F两域planned/triggered/observed/agent_exposed全true，实际commit后抑制响应并只读reconcile，不重复写。DomainVerified/cleanup/冻结反馈先于下一域选择。ToolCall/response IDs、args/result SHA、精确回注、父子capsule/PID/usage与Policy全部由CLI核验。

只有一个native fsynced WAL；Policy在reserve/settle前CHECK/GRANTED，随后native RESERVE/RESULT，再CONFIRMED/SETTLED；独立auditor逐笔与native replay投影一致，没有第二账户。正常/故障票全部结算。拒绝smoke故意保留未结SDK/Host票，不补账、不续跑该Root；crash/orphan/UNKNOWN/direct bypass/duplicate负控保留各新fixture。正式N=1/F=1，纠错0；Runtime disposable unit fixtures不计入正式场景配额且均位于新任务snapshot。

## 测试、负控、历史和清理

最终focused 29项，292.88s，0错误/失败；第一次240秒超时未产最终汇总，原日志和WAL保留。第二次600秒上限、同一Source独立fresh fixtures完成；未使用第三次聚焦。完整Runtime汇总tests=None，2701.50s，exit=1、errors=0、failures=0，原Docker skips见回执；首次全量被意外关机中断，无最终exit/elapsed回执；原日志与快照保留。第二次独立full-02触及2700秒等待上限而停止；2701.50秒包含终止及回执开销。日志有432条完成/跳过记录，无unittest最终数量，不满足完整≥571项验收；两次full不拼接日志。全量cwd是本任务raw snapshot，旧测试`.local`路径物理上均在本轮新根内，固定SDK/JAR只读桥接。parent3.12 full和Hosted CI为NOT_RUN。

实际CLI manifest负控150项，其中预算/父子面93项，另4项联动重锚：两域SDKusage各1、cfg limit各1，修复SDK外层摘要、prelaunch/RESULT_BOUND/driver完成/Domainevidence和全WAL链/rawSHA后仍被SDK_TOKEN_USAGE或SDK_USAGE_SUM/PARENT_CONFIG_BINDING拒绝；最初脚本只允许SDK_USAGE_SUM而误记一项TEST_INVALID，原FAIL文件和首次复核路径错误均保留，随后同一篡改raw锚的CLI复核及pge_r68_verify.py原生usage求和条件证实为真实独立拒绝。纯CFG60和Windows15另计。原件CLI0、无anchor2、坏anchor3；每件original/mutatedSHA、argv/cwd/PID/exit/reason/source/logSHA完整保存，TEST_INVALID不算PASS。

24个历史原入口原SHA/原Verifier通过；R69原CLI0/2/3通过。R70/R71/rev-1私有Manifest/WAL均UNAVAILABLE_NOT_READ。旧rev-1只有public源码/身份回归，不冒称复验旧私有件。每条完整命令证据见[verification-diagnostic.json](verification-diagnostic.json)，包括初次超时和所有成功；Source始终未漂移。

晚次只读OS观察15个当前R2主路径PID/端口：PASS。创建时间/SID hash退出前未采集则UNAVAILABLE，不用模拟补齐，不杀陌生或复用PID。physical symlink结果`UNAVAILABLE`，WinError=`1314`；真实junction在focused创建且被拒绝。新根owner SID摘要见preflight，所有者与当前用户一致。旧账本与docs/reviews完全保护；所有失败/成功现场保留，不删除、重置或重命名。仅status自然显示用户`?? docs/reviews/`。

Provider calls0、真实token0、API费用¥0、宿主凭据读取0；474000与历史价格只为纯预算演算，NOT_INVOICE。实际SDK/HTTP/SQL≠真实模型自主决策。无PR、main merge、force push、tag、release、部署、workflow dispatch、赛事提交。

## VERIFIED_FINDINGS

Windows实际audit形状与精确比较、native cfg实际串行化/PID/SDK/WAL绑定、8阈值组件、N/F独立读回、实际完成的测试和负控有本轮证据；完整回归未完成，重启后的原件正例复验失败。具体函数为`pge_r72r2_sdk_contract.validate_launch/_audit/_profile/verify_proof`与新版`BudgetLedger._perform`；逐文件raw/LF SHA见SourceMap。旧Driver/child/Guard原字节不变。Controller观察不等于child独立确认。

## CODEX_ENGINEERING_JUDGMENT

机制是固定原生启动外的严格父级gate及串行化观察；在受信Windows Controller内置信度HIGH。支持为真实accept/reject、SDK阈值、正式N/F及深层篡改拒绝。反证/边界为child不回显cfg digest，不建立独立签名，其他平台故意fail closed。重启复验已确认verify_proof把当前SYSTEMROOT/WINDIR/PATH重建结果当作旧env声明；具体变化变量因旧值未采集而未知。最小后续试验是在新授权兼容路由中验证：无害宿主safe-variable漂移后旧有效证据仍可重放、恶意env/Key/二进制注入仍拒绝；保留实际启动前的严格净化比较，旧运行不可标为新Source执行。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

| 路线 | 安全/历史 | 成本/限制 |
|---|---|---|
| 薄父级hook（本轮） | 原Driver/child不变，严格source/pin/argv/env | 范围小；frame/profile/Windows耦合 |
| 未来版本化child | 新capsule/digest echo需独立Guard审查，旧原件保留 | 审查和回归更大；echo仍不是外部签名 |
| 保持task-owned不提升公共ABI | 共享变更爆炸半径小，原证据独立 | wrapper重复与Source闭包增长 |

## NEXT_DECISION_RECOMMENDATION

1. 下一RPF-72修订先授权稳定的历史LaunchEnvironment/LaunchSpec接口、独立Source/私有根与复验预算；移除“历史env必须等于当前宿主env”的隐式假设，同时保留严格启动前净化和binary/child/cwd约束。此次不修改冻结Source，不重跑已提交N/F。
2. 若要公共化，另开明确授权的LaunchSpec/factory接口与最小共享层Plan，列出可写路径、历史回归和资源预算；保持旧Guard/证据不变。
3. 真实Provider故障/因果反馈是独立方向，需新API/Key/费用/副作用授权，不自动创建RPF73，也不并入此次零费用验收。

## POTENTIAL_GENERALIZATION_DEBT

已证：历史env哈希依赖当前宿主值造成重启后的有效证据误拒；71源闭包与task-owned wrapper重复、精确调用帧/profile耦合、legacy `key_lookup`需HOST-only协议注释；migration描述性`VERSIONED_V1_2_R72`标签仍为继承拼写，实际Owner/Source v2以冻结字段独立校验。推测：profile/Source扫描可能影响性能，当前时长不是受控性能对照，不给性能提升结论。SDK_GUARD_MIGRATED=NO、FULL_COMMON_CORE_MIGRATED=NO、CHILD_INDEPENDENT_ATTESTATION=NOT_ESTABLISHED；真实双Agent/Provider fault/Issuer/L2/第三域/Web均未建立或NOT_RUN。

## 24条 create-only 路径

- `runtime/runproof_runtime/effectwitness/pge_r72r2_contracts.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r2_owner_source.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r2_capability.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r2_budget_policy.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r2_budget_ledger.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r2_sdk_contract.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r2_ports.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r2_session.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r2_verify.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r2_migration.py`
- `runtime/tests/test_effectwitness_pge_r72r2.py`
- `spikes/rpf-72/rev-2/probe.py`
- `spikes/rpf-72/rev-2/README.md`
- `spikes/rpf-72/rev-2/RESULT.md`
- `spikes/rpf-72/rev-2/preflight-diagnostic.json`
- `spikes/rpf-72/rev-2/verification-diagnostic.json`
- `spikes/rpf-72/rev-2/parent-child-contract-matrix.json`
- `spikes/rpf-72/rev-2/budget-negative-controls.json`
- `spikes/rpf-72/rev-2/history-regression.json`
- `spikes/rpf-72/rev-2/source-identity-map.json`
- `spikes/rpf-72/rev-2/architecture-decision.json`
- `spikes/rpf-72/rev-2/capability-assessment.json`
- `spikes/rpf-72/rev-2/windows-argv-diagnostic.json`
- `spikes/rpf-72/rev-2/key-boundary-diagnostic.json`

公开结果的最终GitHub commit URL由最后push及双读后的聊天给出；私有D盘路径不当作Architect可访问URL。最终回执不回写自身SHA、不amend历史。
