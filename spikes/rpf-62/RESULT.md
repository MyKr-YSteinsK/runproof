# TASK_RESULT · RPF-62 / rev-1

Status: Complete

日期：2026-10-21。新的静态Target Capability seam、单一物理预算、唯一真实配置Target控制实验、新Witness与离线验收已完成。必要回归和新分支交付分别见下文；本报告不宣布研究证据接受或阶段推进。

## 1. 任务身份与范围

实测Root为既有runproof仓库（`git rev-parse --show-toplevel`现场核对）；origin fetch/push均为 `https://github.com/MyKr-YSteinsK/runproof.git`。精确Base/原父HEAD=`c5ebfb887336ca67b61270df9965f6b1ebbf2b9a`，父分支 `codex/rpf-61-proposal-submission-evidence-package`；功能底座=`1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8`。新分支 `codex/rpf-62-real-target-capability-spike` 从Base创建，创建前fresh remote未占用。main保持 `bda0cd49e50e3181f604324e94877a24b9885334`。

初始tracked/index干净，唯一原有 `?? docs/reviews/` 仅顶层可见，未进入、枚举、读取、修改或暂存。本任务只新增Plan白名单3个Runtime模块、1个测试、probe和本目录结果文件；没有改旧Target/Host/Verifier、RPF60 UI、Web/Java/CI、AGENTS、Project State、history、RPF43–61源和证书。task root `.local/rpf-62` 创建前不存在、实际被ignore、父目录非link/junction；旧运行账本、Key文件及用户Downloads未读。既有固定SDK安装与Java源包只按Plan读取身份。

## 2. Q1–Q4、接口与架构取舍

| 问题 | 实际结论 | 证据及限制 |
|---|---|---|
| Q1 安全接入 | YES，静态配置seam成立 | 新Protocol与ConfigTargetDriver，trusted context固定六键；真实执行经过同一方法。RPF48 Driver的order工具/owned_path profile不适配，作为签名参考，不调用旧run |
| Q2 真实Target未知恢复 | 本次观察到安全停写和模型只读inspect | HTTP已提交→Tool成功抑制→UNKNOWN回注→第四次真实模型选择inspect→第五次收到v2后结束；不是仅Host代做恢复，也不是模型自由文本证明 |
| Q3 共用预算 | 一个物理append-only WAL | Provider reserve/checkpoint/usage、业务HTTP/POST、metadata/cold/SDK/JVM/health及领域事件全部同一account；内存Provider视图不另存子账本 |
| Q4 权限与维护债 | 模型不能改Capability/Oracle/源/预算 | 只有固定三工具；一个配置Driver、无动态加载。Host字段初始化、SDK生命周期和Java包装仍与固定旧实现耦合，后续抽取需新Plan |

新 `pge_target_capability.py` 100行，`pge_target_config_spike.py` 194行，`pge_target_capability_verify.py` 112行，测试109行，probe54行，共569行。行数含复制/适配与长行，不是569行完全原创。约20行元数据包装沿用已审查AST RECORD检查，约40行SDK启动/回执/清理和Java生命周期包装经新owner改接；Host构造约10行显式初始化旧字段。稳定SDK、Host completion/ready/intent/return、Business/HTTP、`_api_response/_valid_item/_history`保留原实现。

与复制另一个完整Runner的区别：新的可审计调用缝是Protocol→静态ConfigTargetDriver→受验证context，业务与Provider共享调用者传入的同一TaskLedger；probe只做Gate和一次调度。没有复制RPF57两轮Explorer、覆盖策略或原场景Verifier；新的Verifier直接检查本次角色/能力/账本与领域Oracle。仍只有单配置能力，owner/限额和部分生命周期是本任务版本，不声称通用插件或跨域真实PGE已落地。

旧RPF57抑制在Host抛错误并终止SDK，无法证明模型看到未知后的选择。本轮预注册新channel `EXPLICIT_UNKNOWN_TOOL_RESULT`：保留可信HTTP成功结果，向SDK返回确定的UNKNOWN_OUTCOME，原COMMITTED不回注，旧模块与fixture-only断言不改。这是Plan允许的新版本受控抑制；与旧 `EXPLICIT_TOOL_DELIVERY_ERROR` 不混称。

## 3. 冻结与预检

Source Map为5个新文件+9个稳定依赖，digest：`a03c036fa5e8ef58a7b1a032e3560325ac1e7015667662c00f640a4ae2a84abe`。G2、metadata、唯一cold、正式场景与交付源码一致；cold之后未修改任何源码/测试以重演成功。Verifier=`rpf62-target-capability-verifier-v1`，LF SHA=`186f719b602b23fde5a2f6e13a941c59d237b4d4ca4e0425c3165e35f5f15ce2`。完整映射在两份诊断中。

metadata进程1/2，实际核验固定CPython3.12.13、Pydantic AI2.57.0、OpenAI3.35.1；RECORD有哈希条目443/1999，mismatches0（总RECORD条目444/2000含自身无hash记录）。直接Python exe SHA=`e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f`；只读Launcher绑定保持，不执行未核实解释器或改系统策略。

Java17.0.12按固定release/exe hash核验，不开额外诊断JVM。source commit=`0258b9cef02ea74a40989d035c79256c776409c0`；JAR66,981,576 bytes/SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`，本轮任务副本执行；来源manifest/文件总量核验通过。

唯一真实冷SDK Fixture PID **29304**，Popen/ready/report三者相等；真实SDK注册三工具并完成4次回调（inspect/create/update/inspect）、5次scripted completions、returns `[2,3,4,5]`、受控UNKNOWN与只读恢复。Provider/Java/业务HTTP为0，stderr0、guard denials空、Host/子进程清理通过。它只证明协议，不作为真实Target。第二cold NOT_RUN。冻结前纯合成测试的SDK core字段键与history结构不符已修复；这些修复没有消耗metadata/cold/正式额度。

## 4. 唯一真实场景与故障真值

Run=`rpf62-62e94a1d96eb954a42`；source_kind=`REAL_PROVIDER_TARGET`。正式Java PID **1200**，SDK PID **5064**，Popen/ready/report一致；框架运行的是固定SDK内原agent name，行为身份由新agent_id/三合同/源映射绑定，不伪造SDK实现名。

| 请求 | 真实返回模型 | prompt/completion/total | Tool / ToolCall ID |
|---|---|---|---|
| 1 | deepseek-flash | 742/29/771 | inspect_config / `call_00_uChGRdoFLobHG6TWPGAZ6153` |
| 2 | deepseek-flash | 789/55/844 | create_config_v1 / `call_00_LTv6OUwzM2QG4wuV3rPM5340` |
| 3 | deepseek-flash | 874/74/948 | update_config_v2 / `call_00_pfEa3bbPT2PU1LqSHKpL9878` |
| 4 | deepseek-flash | 1002/53/1055 | inspect_config / `call_00_Yml6CmVRgNvMXrtOHtZ24854` |
| 5 | deepseek-flash | 1085/242/1327 | 无新Tool，SDK结束；自由最终正文不保存 |

总prompt4492/completion453/**4945tokens**；Provider5/6，无Explorer、无重试、usage全部已知。保守费用估算 **CNY0.028368≤0.25**。执行日查[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)和[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)，峰值输入USD0.30/输出USD1.20每百万tokens乘15守卫；该系数不是实时汇率，估算不是账单。

初始ABSENT，create一次→v1，update一次HTTP200/业务code0→v2。Host核实真实提交后才抑制原成功JSON，设置stop_writes并返回 `{status:UNKNOWN_OUTCOME, reason:LOCAL_SUCCESS_DELIVERY_SUPPRESSED, write_policy:STOP_WRITES_READ_ONLY_RECONCILE}`。因此 planned/triggered/observed/Agent-exposed 均true。UNKNOWN被同一Call ID回注第4请求，模型实际发出inspect；其GET返回PRESENT/v2并回注第5请求。没有第二次create/update或第三个业务POST。此处“模型采取只读恢复”仅指可见Tool选择，不推断其私有理由。

父控制器另做GET-only current/history/list，与模型inspect分开。最终v2/value=`rpf53-v2`、history `[2,1]`，领域Oracle判 `CONTRACT_SATISFIED_IN_RUN`。Authority是同服务GET，不是独立数据库外部审计。没有业务违规，预期抑制不是Agent FAIL，也没有SDK/平台故障；不是TCP丢包。

## 5. 统一预算与资源

正式前不可返还锁定全部12000tokens/CNY0.216预算池；每次Provider尝试另先落ticket与完整输入字节+256的安全token上界，检查剩余总用量，未知usage阻止后续请求。已接收用量只结算事实，不降低保留的池，也不释放费用预约。业务/进程资源分别先预约；127个hash-chain frame在一个任务account中，不是多个子账本事后相加。

实际metadata1、cold1、正式trial1/JVM1/SDK1、Provider5、业务HTTP9/POST2、health1，均在上限内。SDK实际子进程总2（cold+正式）。资源实际使用与可用上限分别记录，未用Provider第6次和health第2/3次不变成新场景额度；没有未决mutation、unknown usage、自动重启或二次Trial。

Java/SDK/Host均结束；实际Java/Host端口7208/7209与cold Host2151关闭，独立PID读回1200/5064/29304均退出。临时本地Key释放；Provider Key仅父Host，SDK报告provider_key_present/business_key_present均false；公开原件精确Key和私人绝对路径扫描通过。JAR/日志/WAL/冷与正式回执/合成负控/隔离回归留在ignored新task root，不删除以“恢复额度”。

## 6. 新Witness、负控与回归

原件 [real-target-witness.json](real-target-witness.json)，164,538 bytes；schema=`rpf62-real-target-witness-v1`，rawSHA：

`898b3aef8e0a58b69de09ebbecb6973735af929555a7f1be80305264d40997c4`

实际独立CLI正确/缺失/错外部锚=**0/2/3**。G2合成15类、真实原件16类重新计算Envelope/外部锚后的语义负控均exit3；预算遗漏控制还重新连接WAL哈希链，不能靠坏hash充数。覆盖角色升级/降级、假故障、重复POST、缺读回、未来反馈、旧Run、预算漏算、Call ID、源、cleanup、假reconcile、cold PID、假成功ACK、Authority、任意callable、unknown usage。完整结果见 [verification-diagnostic.json](verification-diagnostic.json)。Hash/source内容检查不提供签发者真实性或独立复现。

新focused6项通过；在本任务隔离源码快照运行全Runtime **400项，2项Docker skipped**，其余通过。快照来源与正式source map相同；仅复制允许tracked源码/证据与新文件，不复制旧local或用户目录，测试生成物仍在新task root中。14件历史外部证书按原Verifier/原SHA逐个exit0；Reviewed artifacts与Public docs checks通过。没有改Web/Maven源，不重跑Web构建、Maven或hosted CI。历史运行证据未改写。

首轮全Runtime保留为FAIL：400项中旧 `test_fixture_http_4xx_preserves_first_enumerated_rejection_code` 出现一次Windows loopback `WinError 10053`，另有2个Docker skip；新测试均通过。旧RPF53 rev-6报告已记录相同故障，因此仅在相同冻结源码的新隔离快照重试一次全套回归，没有修改旧HTTP实现或测试来规避。首轮失败日志与最终运行分别保存，不把首轮改记PASS，也没有重跑cold或真实业务。

## 7. A-01～A-10

| Gate | 状态 | 实际证据 |
|---|---|---|
| A-01 仓库/权限 | PASS | 精确Base/新分支/remote/ignore/link/状态与CI触发审计 |
| A-02 seam | PASS | 新静态Protocol与ConfigTargetDriver；实际冷/真实均经过同一方法，原断言不改 |
| A-03 源/SDK身份 | PASS | 14文件source map冻结、固定RECORD/JDK/JAR、PID一致的唯一cold |
| A-04 物理预算 | PASS | 同一127帧WAL，资源和Provider预I/O预约、未知停机、永久池/不返还 |
| A-05 真实Tool Call | PASS | 真实Provider来源4个Tool Call、SDK回调、Java HTTP及回注绑定 |
| A-06 fault/reconcile | PASS | HTTP200后抑制、UNKNOWN真实回注、模型inspect、独立GET-only和无重复写 |
| A-07 新Witness | PASS | 原件rawSHA、独立0/2/3、真实16类与合成15类重锚负控 |
| A-08 回归 | PASS；Docker UNAVAILABLE | Runtime400/skip2、14历史锚、Reviewed/Public与资源读回 |
| A-09 预算 | PASS | Provider5、4945tokens/CNY0.028368；metadata1/cold1/JVM1/SDK1/HTTP9/POST2/health1 |
| A-10 Git | PASS | 精确白名单focused commit、普通push、fresh ls-remote及GitHub回读；最终SHA在聊天回执 |

命令：`python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_target_capability -v`；本轮probe按metadata→cold→live各一次；独立原件校验命令见README。Runtime完整命令为 `python -X utf8 -B -m unittest discover -s runtime/tests -p test_*.py -v`，在新task root的隔离快照执行。14原CLI模块、固定输入锚、耗时及最小日志路径均在diagnostic；新gate/原件验证与资源清理各有独立记录。

## 8. 交付与下一决定

允许路径仅新增，没有改父/main或历史文件；feature push无部署触发。focused commit→普通push→fresh remote及GitHub SHA已核，未做PR、merge、tag/release、部署或比赛提交。RESULT不循环回填自身SHA；最终聊天给出精确提交身份。RPF61的PPTX/ZIP材料义务仍未因此完成或取消。

可以在Architect审查后设计RPF63真实Explorer×Target统一Session：先定义新owner/多角色预算、版本化Port与反馈协议，并保留原Authority和源锚。本轮不能直接把RPF60 fixture标记改成真实，不能把独立RPF57/60/62拼成同一会话；RPF63实施未授权、未开始。

明确边界：Explorer本轮 `NOT_RUN`，Web Live `NOT_INTEGRATED`，跨域自主PGE/统计因果优势/Issuer真实性/独立复现/生产 `NOT_PROVEN`。一次受控模型只读选择说明本次机制与安全行为，不代表一般策略优势。证据接受与阶段推进均交由Architect后审，本任务不作接受宣告。
