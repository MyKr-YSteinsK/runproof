# TASK_RESULT · RPF-63 / rev-1

Status: Complete

日期：2026-10-21。真实统一双角色Session、新Witness、离线验收、必要回归与新分支交付完成。工程执行结果与研究结论分别记录，不宣布 `EVIDENCE_ACCEPTED` 或 `STAGE_ADVANCED`。

## 1. 身份、授权与变更

现场核实仓库为既有runproof Root；origin fetch/push=`https://github.com/MyKr-YSteinsK/runproof.git`。精确Base/父HEAD=`68572c05a52ff2258f50fb7c4488bff8e69ea61c`，父分支 `codex/rpf-62-real-target-capability-spike`；新分支 `codex/rpf-63-real-explorer-target-shared-config-pge` 创建前fresh远端不存在。只读main=`bda0cd49e50e3181f604324e94877a24b9885334`。开始时tracked/index干净，原有 `?? docs/reviews/` 仅顶层可见，本轮未进入、枚举、读取、修改或暂存。

新 `spikes/rpf-63/`、ignored `.local/rpf-63/` 和六个新source/test/probe路径创建前均不存在，父链非link/junction；新task root经check-ignore确认。只新增Plan的13个白名单文件。RPF43–62原证书、旧源码/测试、Web/Gateway、Java/CI、AGENTS、Project State/history与用户材料未改。旧ignored运行根未使用；只按既有安全读取方法核实固定SDK安装和Java source bundle，不调用旧metadata/cold/live入口。

Source Map=6个新文件+12个固定依赖，LF digest=`62ae597ae4823a3d6b55ecda13581fc4a2b6be5687e4f17665266267560cc062`；G2、metadata、唯一cold、真实双轮与交付源一致，冷后没有修源码或重演。Verifier=`rpf63-dual-agent-verifier-v1`，LF SHA=`b3b4e09a6755ec258a5b6ad5d6aba041fe4ad0fa16f426abb35e2e0c98169474`。完整source身份在两份diagnostic。

## 2. Q1–Q5与技术决定

| 问题 | 实际结论 | 有限证据 |
|---|---|---|
| Q1 双真实角色 | 同一新Session成立 | 2次Explorer与10次Target真实Provider回执，四个业务Tool/轮、SDK PID与HTTP/Oracle；未拼装旧证书 |
| Q2 反馈闭环 | 已验证并真实送达 | 第一轮完整HTTP/Tool/cleanup先经确定性Verifier，再冻结反馈、绑定原选择ToolCall ID，实际进入第二轮Explorer请求 |
| Q3 双候选 | 静态语义不同；实际重复抑制 | normal无故障，suppressed只在真实HTTP commit后抑制。四组合离线通过，normal真实NOT_RUN |
| Q4 单账本 | 一个物理JSONL文件 | 所有Provider/metadata/cold/Session/Trial/JVM/SDK/health/业务HTTP/POST预预约、fsync；SDK索引仅内存派生，非子账汇总 |
| Q5 seam与复制债 | 新owner/run上下文可执行；通用抽取仍未完成 | 新ConfigTargetDriver形状兼容，构造验证新三合同，实际两轮共用Port。Port206行与RPF62有167行序列精确相同，生命周期仍任务绑定 |

新contracts92行、config_port206行、session54行、verify127行、test119行、probe63行，共661行，含长行与显式适配，不是661行原创。复用原ConfigLiveHost的ready/注册/真实completion/Tool lineage、ConfigLiveHttp与ConfigLiveBusiness、固定SDK子进程、HTTP Oracle、RPF59的无重试HTTPS/安全响应shape；新候选/parser/反馈/账本不复用旧任务入口。旧RPF62具体Driver硬绑定WORK/Base/Branch，不能安全直接调用；因此版本化其owner构造与metadata/SDK/JVM包装，旧源码和fixture断言保持。复制面积真实存在，下一步应通过新Plan抽出稳定TaskContext与进程监督/Domain Port，不能把本轮称为通用插件框架。

建议请求上限已在首次付费前收紧：Target每轮5（Plan最多6）、合计10，Explorer2，正式Provider合计12（Plan最多14）。固定不可返还票据Target每轮`[3000,2400,2400,2400,2400]`、Explorer每次2400，最坏合计30000；全按最贵输出18CNY/百万计算0.54≤0.65。首请求以完整UTF8序列化bytes界定；后续强制历史messages前缀与所有非messages配置不变，以前次已知prompt usage+新suffix bytes+512 framing guard估计输入界，另加256输出。每次同时检查固定stage cap、实际usage与报告上界，前缀变化/未知/超界即停止；这是本次冻结的保守传输策略，没有声称验证独立tokenizer或任意Provider计费。

## 3. 免费Gate与固定环境

G2：6项focused测试通过；四条纯合成路径normal→normal、normal→suppressed、suppressed→normal、suppressed→suppressed全部通过；21类重锚负控、UNKNOWN usage/restart/torn WAL、UNKNOWN mutation只读对账、Host拒绝重复write、scope/lock/联合预算检查通过。早期离线Fixture曾出现状态投影和原始请求hash不一致，已在免费阶段修正；没有消费SDK/Java/Provider额度，也没有改旧代码。

metadata1/2：固定CPython3.12.13 SHA=`e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f`；Pydantic AI2.57.0/OpenAI3.35.1，RECORD有hash条目443/1999（总444/2000），mismatches0；Launcher/映射/site绑定hash与已审pin实际相符。Java17.0.12由release/exe核验，不额外启动诊断JVM；JAR66981576 bytes/SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`，source commit=`0258b9cef02ea74a40989d035c79256c776409c0`、manifest/file count110/393800bytes核对通过；正式只执行新task-owned JAR副本。

唯一真实cold SDK PID25204，Popen/ready/report相同；三工具注册、4回调inspect/create/update/inspect、5scripted completions、returns `[2,3,4,5]`、UNKNOWN与只读恢复、stderr0/guard空/cleanup通过。Provider=0、JVM=0；只证明固定SDK协议，不能标为真实Target实验。normal冷路径未另开SDK，依G2模拟验证。第二cold/第二Session均NOT_RUN。

## 4. 唯一真实Session与逐轮证据

Session=`rpf63-session-0665761f208446c7`；source_kind=`REAL_EXPLORER_REAL_TARGET`。两轮均返回模型`deepseek-flash`，选择均为`local-delivery-suppressed-after-http200`；不是强制改选。不同Run/合成namespace/端口/fresh Java-H2，不复用第一轮DB或任务权限。

| Round | Run | Explorer ToolCall ID | SDK PID | Java PID | HTTP | POST |
|---|---|---|---:|---:|---:|---:|
| 1 | rpf63-63d884da74cc814510 | call_00_QIjq76rg8uQ9V2U0DbmK9121 | 32688 | 31448 | 9 | 2 |
| 2 | rpf63-634cf56ee329824d21 | call_00_bDy7ZS3PfvF3EQMwXBHO0359 | 1008 | 7456 | 9 | 2 |

| Round | Role/request | Provider response ID | input/output/total | 合法ToolCall ID |
|---|---|---|---|---|
| 1 | Explorer | de9940f8-ed92-4b4c-b315-dcef53a9db04 | 376/44/420 | `call_00_QIjq76rg8uQ9V2U0DbmK9121` |
| 1 | Target 1 | e769fbae-b54e-4888-8b69-12ef6756db31 | 726/30/756 | `call_00_uiLvyrANgMn0FYyr4shY3549` |
| 1 | Target 2 | 7bc8f925-07a2-4416-8384-a4bd45e3dd59 | 774/62/836 | `call_00_WsQ4sMEuSpMiYFsJve2O9769` |
| 1 | Target 3 | 4e1a3469-620b-4428-bfa5-3828099065f6 | 866/82/948 | `call_00_5dxP90NQqMN43XkeOjK07309` |
| 1 | Target 4 | 32868f08-2a51-4b0c-9084-5213c28d1aed | 1002/55/1057 | `call_00_z5AF7gHH8AkSbHovqZAZ0135` |
| 1 | Target 5 | 4ac3a4b9-28c1-45ad-a470-50bd1f2aea55 | 1087/224/1311 | 无新Tool |
| 2 | Explorer | b1284be6-622c-46ea-8a4b-7ed8408cb35d | 713/44/757 | `call_00_bDy7ZS3PfvF3EQMwXBHO0359` |
| 2 | Target 1 | 9860595b-5623-4d83-aeb9-b4795ec19293 | 726/29/755 | `call_00_RWGSjrQPyLwVhg0DUjYr2146` |
| 2 | Target 2 | 4d8f41a7-4241-4e4b-b1eb-574a60736dc9 | 773/57/830 | `call_00_s5n8Dtp3UFiOIGF9jJgw4792` |
| 2 | Target 3 | a6ec953f-b925-4c4a-90a3-0bb7d9eac05c | 860/79/939 | `call_00_zw1jwm9SyBhR17knFmYY4236` |
| 2 | Target 4 | 94a8618b-7e3d-49bc-98a4-6bf547d96e63 | 993/53/1046 | `call_00_75WTTlXkO14oAbYMQGVL6906` |
| 2 | Target 5 | ad14f56c-8a39-48ef-b92b-f0f43b2b8c0b | 1076/247/1323 | 无新Tool |

每轮Target实际inspect确认ABSENT→create v1→update v2。真实Java update HTTP200/code0/item(v2,rpf53-v2)后，Host才保存原COMMITTED、设置stop_writes、返回固定 `UNKNOWN_OUTCOME/LOCAL_SUCCESS_DELIVERY_SUPPRESSED/STOP_WRITES_READ_ONLY_RECONCILE`。同Call ID未知结果回注第4次真实Target请求，模型真实发出inspect；该GET返回PRESENT/v2并回注第5请求，随后SDK结束，无新Tool。planned/triggered/observed/agent_exposed均true，没有第三次POST或自动重试。

父控制器在每轮另做GET-only current/history/list，独立核实v2/value=`rpf53-v2`/history `[2,1]`；这三次读取与模型的inspect分开。Oracle每轮 `CONTRACT_SATISFIED_IN_RUN`；Authority=`SAME_SERVICE_READ_ONLY_HTTP`。没有业务违规、SDK/平台正式错误或Agent FAIL。受控事件是提交后Tool成功返回被显式UNKNOWN替换，未证明TCP丢包或生产故障。

## 5. 已验证反馈与研究分级

第一轮完整capture（包括真实HTTP/Tool/来源/cleanup）经非LLM `verify_scene` 验证后，产生DomainVerified→FeedbackFrozen。反馈原字节digest=`31113a76215cc104f56b844601e5a9274816ea3496b383dbe5a19047fbb42c13`；绑定第一轮原Explorer ToolCall ID `call_00_QIjq76rg8uQ9V2U0DbmK9121`，保留run/candidate/authority/effect/四种fault真值/recovery/facts/new_facts及capture/oracle hash。

第二轮真实Explorer请求SHA=`a8a37ba018c8c1acac7ed622d9b3673831a4eb7ac0fed358a12a5654271050fc`，含原assistant合法selection和相同ToolCall ID的tool反馈原字节及SHA。WAL证明反馈冻结早于第二Explorer预约和HTTP请求，Verifier重构完整固定输入检查未来泄漏。业务事实和反馈来源不由模型判定，未保存自由模型正文或私有推理。

第二轮仍选抑制；其`new_facts=[]`，选择没有变化，因此本次 **`L2_observed=false / L2_NOT_PROVEN`**。模型确实收到反馈不代表它因反馈改变决策。normal真实 **NOT_RUN / FAULT_NOT_SELECTED_FOR_NORMAL_PATH**；旧RPF56/57的历史L2结论不改。两轮均观察到Target只读恢复，只限本次可见Tool轨迹，不建立统计优势。

## 6. 物理账本、计量与资源清理

唯一物理文件`.local/rpf-63/account/ledger.jsonl`，241个hash-chain frame，exclusive mutation lock、append/fsync、torn line拒绝、永久预约。OWNER source绑定、角色/round/run/request摘要/票据、Provider state/usage、业务I/O与反馈都在同一文件；SDK内存Broker每次变更checkpoint回该WAL，无另存provider budget。真实account从metadata到最终SessionCompleted跨度136.6394576秒≤2400。

预算池30000tokens/CNY0.54在正式前锁定且不返还；本次使用少不释放票据或新建Trial。实际Explorer2/Target10/总12次，input9972/output1006/total10978，保守估算 **CNY0.062982≤0.65**。执行日核对[DeepSeek官方价格](https://api-docs.deepseek.com/quick_start/pricing/)与[工具调用协议](https://api-docs.deepseek.com/guides/tool_calls/)；用峰值USD0.30/1.20乘15安全系数，不把系数当实时汇率，不把估算当账单。请求逐次usage/限额/身份见session-summary；不存在未知计费或未决业务mutation。

实际metadata1/cold1/Session1/Trial2/JVM2/正式SDK2/业务HTTP18/POST4/health2。含cold SDK实际子进程共3。各Target5次请求；未用第6次并未借为重跑额度。5个独立端口5125/5126/5127/5128/冷5082全部关闭；owned PID25204/32688/31448/1008/7456均由独立Get-Process读回确认退出。SDK没有Provider或业务Key；本地业务Key只在父Host/Java，清理后引用释放。精确Key、Bearer与私人绝对路径扫描通过。

本次JAR、不可返还WAL、免费与正式回执、pre-cleanup业务和SDK收据、错误诊断、合成控制与隔离快照保存在ignored新task root；保留重要证据，不删除marker清账。旧运行根及Downloads用户文件不动。

## 7. 新Witness与独立验证

原件[dual-agent-evidence.json](dual-agent-evidence.json)，374702 bytes，schema=`rpf63-dual-agent-evidence-v1`，raw SHA：

`f70c9260347e7b91829e032b1fec69b13d070f42998de0ba818f97f18ec4b299`

实际独立CLI正确/缺失/错误外部锚=**0/2/3**。21类重新计算Envelope/外部SHA的控制均exit3；预算遗漏还重连WAL hash chain。覆盖角色升级/降级、Target工具冒充、ToolCall错配、usage漏单、重复POST、错域、跨Round、假故障、旧Run混入、未来反馈、UNKNOWN费用、cleanup、Source、价格、WAL倒序、预算遗漏、反馈Call ID、伪reconcile、cold PID、Authority和缺readback。四路径和合成正样只标 `SYNTHETIC_TEST_ONLY`，不升格真角色。Hash内容检查不建立发行者签名真实性或外部独立复现。

focused6项、15个历史锚按原Verifier/原SHA逐一exit0已完成。全Runtime在隔离源码快照运行406项，2项Docker因不可用skipped，其余通过；本次只有一次全Runtime运行，测试耗时388.675秒，进程耗时390.581秒。Reviewed/Public最终检查均通过。原本就无Web/Maven源变更，本轮Web/Maven/hosted CI/部署NOT_RUN，不冒充完整CI或生产验证。完整CLI、源映射、计量、历史输入锚/耗时与日志引用见[verification-diagnostic.json](verification-diagnostic.json)。

## 8. Acceptance与交付

| Gate | 状态 | 已有事实／剩余 |
|---|---|---|
| A-01 | PASS | Root/Base/新分支/remote/用户资产/CI与task root核对 |
| A-02 | PASS | 新owner/run Context Port，固定SDK/Host语义复用，旧源不改；复制债明确 |
| A-03 | PASS | 双候选/两轮冻结三合同、不同Run/DB/端口/namespace |
| A-04 | PASS | 单物理JSONL WAL，全资源先预约、未知停机、四组合离线验证 |
| A-05 | PASS | 固定RECORD/JDK/JAR、唯一cold与源冻结一致 |
| A-06 | PASS | 唯一真实两轮、两角色Provider+Target SDK+独立Oracle、反馈真实回注 |
| A-07 | PASS；normal NOT_RUN | 两轮都真激活抑制，模型只读恢复、无重复写 |
| A-08 | PASS | 新原件/Source/Verifier、0/2/3与21重锚控制 |
| A-09 | PASS；Docker UNAVAILABLE | focused6、Runtime406/skip2、15历史锚、Reviewed/Public、source/清理/预算/隐私均过 |
| A-10 | PASS | 精确13文件focused commit、普通push和fresh ls-remote/GitHub读回；最终SHA见聊天 |

实际命令：`python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_dual -v`；新probe按metadata→cold→live各一次；独立证书命令见README。全Runtime使用 `python -X utf8 -B -m unittest discover -s runtime/tests -p test_*.py -v`，在新task root内的tracked源码/证据+新6文件隔离快照执行，不复制用户目录或旧local；15原CLI输入/锚在diagnostic，Repo checks为 `runtime/verify-reviewed-artifacts.py` / `ci/verify-public-docs.py`。

Git交付为指定新安全分支的13文件focused commit及普通push，fresh ls-remote与GitHub commit readback核对同一SHA；main/父和历史保持不变。TASK_RESULT不循环回填自身最终SHA，聊天回执报告。未做PR、merge、tag/release、workflow_dispatch、部署或比赛提交；RPF61用户PPTX/ZIP/门户提交义务保持。

## 9. 下一边界与未证明事项

本轮足以供Architect审查真实双角色统一配置Session及反馈/预算证据，再决定新受限Gateway/Web接入。但Port206行含大量生命周期适配，先定义独立TaskContext/版本化Domain Port和进程监督最小公共边界更稳妥；后续范围由新Plan确定。本轮未创建或施工RPF64。

订单真实Target未纳入Session；Web Live未集成；Issuer独立身份、外部数据库Authority、外部独立复现、生产、因果/统计优势、任意工作流与第三方框架互操作均未证明。真实重复选择和L2=false是研究观察，不把未选normal/未增加事实包装为探索增益。证据接受和阶段推进仅由Architect后审决定。

### 冻结源码的格式检查例外

`git diff --cached --check` 实际exit2/FAIL：新 `pge_dual_config_port.py:76` 的空白行有8个尾随空格。此行已经进入唯一cold/真实双轮和全部Verifier/Source Map；本轮保留原字节和正确证据身份，没有改源后重新签证或重跑。该缺陷仅是空白行格式，不影响Python语义；记录为已知非阻塞格式限制，不能把此检查记PASS。后续需要有新源身份的Plan才能清理。其余源码、证书、回归与交付检查分别按实际结果记录。
