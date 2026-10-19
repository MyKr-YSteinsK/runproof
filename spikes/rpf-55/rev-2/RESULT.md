# RPF-55 rev-2｜TASK_RESULT

**Plan ID: RPF-55 / Revision: rev-2 / Status: Partial（必要验收通过，Git交付待闭环）**

## 1. 结果与任务身份

本轮完成新的三场景真实Java/H2实验和独立离线Witness。normal与planned-but-inhibited完成SDK正常三工具/两POST链；inhibited实际命中禁止触发gate；suppressed在update真实HTTP200后抑制一次成功Tool回复，SDK报错停止，父进程只读确认v2/history `[2,1]`。没有复用rev-1的任何Run、JVM、marker或观察。

实际仓库为已核验的runproof根；origin fetch/push=`https://github.com/MyKr-YSteinsK/runproof.git`。正式运行HEAD/Base=`65643ee38037de96f6f6d41909be4eb1ad64f3c9`，父分支 `codex/rpf-55-bounded-config-experiment-adapter`；新分支 `codex/rpf-55-rev2-config-experiment-cold-start-closeout`。执行前fresh远端Parent一致、新分支不存在、main=`bda0cd49e50e3181f604324e94877a24b9885334`。起始tracked/index clean，仅既有 `?? docs/reviews/`；该目录未进入、枚举、读取、改动或暂存。

仅修改Plan允许的三模块、对应新测试与probe共5个路径，并新增rev-2 README/RESULT/summary/Evidence/offline-verification共5文件。旧Runtime/测试/证书、rev-1三个tracked结果、AGENTS、Project State/history、Web/CI、Java外部源码均未改动。源、SDK及JAR的既有授权位置只读；旧 `.local/rpf-55/**` 默认不碰，本轮未读取其中marker/ledger。所有新运行/诊断/快照位于 `.local/rpf-55-rev2/`，已检查ignore、真实路径及link边界。

当前feature成果未合入main；本轮无PR、main merge、tag/release、publish/deploy。新分支push没有部署副作用。

## 2. 冷进程根因修复与验证

rev-1的直接解释器身份依赖旧helper模块的 `_DIRECT_SDK_PYTHON` 内存值；新Runner导入时该值为空会回到wrapper，或在门槛处提前停止。rev-2新增 `resolve_direct_python`，每次从固定SDK配置重新定位直接exe，并检查路径、链接、CPython exe/launcher hash；`sdk_identity_direct`独立校验SDK版本/核心hash/RECORD，不再设置helper缓存。`run_sdk`直接使用解析结果Popen；正式scene在marker/JVM之前再次校验。wrapper路径在执行前拒绝，未调整Windows Application Control、安装工具或执行受限wrapper。

三种检查分别使用真正的新OS进程：

| 阶段 | normal Runner PID | inhibited Runner PID | suppressed Runner PID | 实际结论 |
|---|---:|---:|---:|---|
| Tier0冷启动 | 33884 | 18228 | 21696 | 直接exe/hash/RECORD、Host listener与关闭、wrapper负控通过；helper缓存自然为空 |
| Tier1真实SDK Fixture | 34848 | 21884 | 17248 | 正常/inhibited均4 completions/3调用/3唯一回注，后者命中FAULT_INHIBITED；suppressed报错且[2,3,null]；3次诊断内完成 |
| Tier2真实Java | 35152 | 31764 | 10536 | 每次新Runner从零重校验身份；同一冻结执行source、不同JVM/H2/SDK/namespace |

Tier0/Tier1均Java=0、业务HTTP=0、Provider=0。Tier0完整合成证书独立CLI `0/2/3` 和七类rehashed tamper先通过；正常/inhibited/抑制Fixture则由实际SDK注册/调用/回注与ready/report/Popen身份核对。SDK错误report没有PID时只报告Popen/ready绑定，不捏造错误report字段。

动态README/JSON输出与固定执行source map分离；合法输出状态通过，未知路径、未授权tracked修改及staged污染负控拒绝。健康投影测试包含 `diskSpace.path`，证实原对象不改写、公开仅status与原body摘要；真实health原始响应按场景once保存。已有JDK及readiness路径没有未解释风险，因此不启动额外基础设施诊断JVM。

## 3. 三场景原始事实与预算

第一台JVM前一次性冻结 `.local/rpf-55-rev2/preflight/formal-reservation.json`，含三个独立rev-2合同、source/Verifier身份及总预算；顺序保持normal→inhibited→suppressed。Scene started/ledger/raw/verified文件均不可覆盖。

| candidate | 新Run ID | 合同SHA-256 | JVM / SDK PID | 实际结果 |
|---|---|---|---|---|
| normal | `rpf55-rev2-55r219932c47138a4ec7` | `fe26b94e157c18ad7786de098c865b4528fecddcaaf4de79abe4b632e9214eb6` | 35424 / 2336 | 4 completions、3工具、回注[2,3,4]；8 HTTP/2 POST/1health；v2/[2,1]；planned/triggered/observed=false/false/false |
| planned-but-inhibited | `rpf55-rev2-55r2e0003ca1914d47e5` | `ffed51f29c781b193b69b5a709a660cb93a35d1bada28f03ffcaac03df986e44` | 28828 / 6196 | 正常同等业务链及[2,3,4]；8 HTTP/2 POST/1health；真实update Host gate记录FAULT_INHIBITED；true/false/false |
| local-delivery-suppressed | `rpf55-rev2-55r2dcf7a356a5884223` | `fad5870fe1b27e8eea4fca5e95bbd704eccce3e857a0c00bf143c675c0cebbc5` | 33892 / 12668 | 3 completions、3调用、[2,3,null]；8 HTTP/2 POST/1health；update200后一次withheld→SDK_ERROR→只读current/history/list确认v2/[2,1]；true/true/true |

每场景都先验证ABSENT/current4041及空history，唯一create/update各一POST；相同值目标和history由独立新GET检验。suppressed的Target成功ACK保持 `UNKNOWN_OUTCOME`；Host已见200不等同SDK已收到COMMITTED。之后没有Tool或POST重试。inhibited真实走到gate，不能由“没有运行故障”替代此对照。

故障为 `LOCAL_DELIVERY_SUPPRESSION_AFTER_HTTP_200`，在Host→SDK交付边界扣留成功结果；原Handler实际返回HTTP400，旧SDK转为RuntimeError并中止。证书保留 `EXPLICIT_TOOL_DELIVERY_ERROR`，不声称TCP丢包、业务未提交或真实模型自主恢复。

**实际总量：3正式JVM，24业务HTTP，6 POST，3 health GET；额外readiness诊断JVM=0；Tier1真实SDK诊断=3；Provider HTTPS=0、tokens=0、费用=¥0。** 没有重跑任何场景或借rev-1额度。

task-owned JAR只从Plan固定来源复制，66981576bytes/SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`；source commit=`0258b9cef02ea74a40989d035c79256c776409c0`、manifest=`33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`，110文件/393800bytes逐项核对。三个实际Java argv均指向新task-owned JAR，Java17.0.12、PID/listener/loopback/health及外联检查通过。直接CPython3.12.13、SDK2.57.0/OpenAI3.35.1及RECORD444/2000、0mismatch与既有公开pin一致。

三个JVM/SDK已退出，Java/Host端口及Host线程均关闭；local合成key仅在Java环境提供，不进argv/SDK环境/证书，客户端引用已释放，Java环境随进程退出。保留新task-owned JAR、已redact日志、raw health和不可覆盖场景证据；未清理旧或用户-owned文件。回归进程另设loopback、禁Java/Docker及无key环境。

## 4. 新证书、来源版本与离线修复

[正式Witness](config-experiment-evidence.json) 为56041bytes，外部SHA-256：

`e5caa1a4578262132a7e779efdf481c1e9c4649cd8bbd7adfbd4c747575ca2c8`

schema=`rpf55-config-experiment-evidence-v2`、revision=`rev-2`、source_kind=`FIXTURE_TARGET_CONTROLLED_JAVA_HTTP`。三合同严格版本化，run/task-JAR/Base/branch与rev-1不同；旧rev-1合同负控拒绝，原失败摘要没有被重解释或覆盖。三份新capture的HTTP/事件/Tool/SDK/Authority与证书字段逐项对应。

### 执行身份与验证器身份分别保留

- 三个Scene正式冻结执行map digest：`cd81bda5b6ec1f61268fc4ee681ca97c9b675ffc4cf633c06d8c822132f63e18`。其中probe SHA=`5e2a2a0fca438769d6371d843c8aacf249e7f5672f69d7e96dae413d09486ebd`。三份started中的map完全一致。
- 为使执行版可从Git独立读取，**运行后**以 `67da2e49f08687f930323af8b6b999b14dd0e0de` 保存了五个实际执行/测试源码的字节；这不是正式运行时HEAD。运行时HEAD仍是本Plan Base。
- 初始Verifier v2 SHA=`c87b9c26ace5dedcd040ea3f8791b98b4da7b2c99866550fb2fd80761844fea5`；所有真实单Scene和初始三场景候选/七类负控已通过。
- 收尾导出 `offline-verification.json` 时，`once()` 的输出范围遗漏该已授权文件，报 `OUTPUT_SCOPE`；此时三Scene均已结束并清理。初始失败摘要保留至本轮quarantine。**没有重跑Java/SDK或任何业务请求。**
- 纯离线修复只增加此导出文件的精确允许路径，并为实际执行版登记精确probe哈希；其他七个执行source仍须与本地身份相同，任意source替换负控拒绝。Verifier业务/故障/Authority/SDK判据没有放宽。
- 新Verifier **v2.1** SHA=`41fc05e3da0b3b89da5cad0a63fa8f0f7017d7d63cddfb8aabf8fd24343f5db3`。原candidate SHA=`d88260c782dd022598d07513ccd197fdd7112633d22d6d60c3380c1c0d52d3c6` 保留；仅新建带v2.1身份的Envelope，payload逐字段不变。独立CLI明确返回 `RPF55_REV2_INITIAL_FROZEN`。
- 交付probe SHA=`a5c9745409531cb71632c236ce5e3a09c86b0d3c776ca35ebdf76eed9dc77f5c`，交付执行source map digest=`cbf30b0007ce2e4755e96fee74357b76d3924eaa3db11a6a413a0b6d01fb2033`；该差异是离线导出修复，没有冒称新源码重新执行过三场景。

[offline-verification.json](offline-verification.json) 记录初始/最终验证器、candidate与证书hash、执行/导出map、payload_unchanged=true，以及最终独立CLI退出码。correct/missing/wrong=`0/2/3`；false_trigger、namespace_splice、duplicate_post、authority、cleanup、sdk_callbacks、false_ack七类重新计算内部digest及外部SHA后均exit3。纯错锚不计入语义负控。

原Scene、started、ledger和SDK/HTTP字段均未改写。raw与health原响应保存在 `.local/rpf-55-rev2/scenarios/<candidate>/`，公开health只含status-only投影和原body摘要；源码/日志/合成控制位于同轮preflight、fixture、tests、diagnostics、replay、quarantine。没有将旧rev-1证据混入新证书。

## 5. 验收、回归与边界

| Gate | 状态 | 证据 |
|---|---|---|
| A-01 身份/保护 | PASS | exact Base/Parent/main/origin/newref、AGENTS/ignore/workflow；5个允许修改及5个新输出；旧证据/reviews未触碰 |
| A-02 冷进程修复 | PASS | 三个独立冷进程+三个真实SDK诊断进程；直接exe pin/RECORD、wrapper拒绝、helper缓存自然为空；source/output及staged负控 |
| A-03 FaultPlan/候选 | PASS | rev-2三合同先注册、唯一namespace；false/false/false、true/false/false及真实一次true/true/true；inhibited gate时序核验 |
| A-04 SDK与旧行为 | PASS | 正常/inhibited4/3/3，suppressed真实RuntimeError及缺第三回注；SDK/Tool/Return/ready/PID/guard检查；旧Runtime未改 |
| A-05 三个真实Java | PASS | 三个新Runner/JVM/H2/SDK、task-JAR/health/readback、0重复POST；全部清理，正式预算内，无诊断JVM |
| A-06 新真实Witness | PASS | 完整同源三Scene、独立外部SHA0/2/3、七类rehashed负控；仅离线导出修复，保留执行版与v2.1身份 |
| A-07 回归/费用/安全 | PASS | 最终313 tests/0failures/errors/2 Docker skip；8历史锚、Reviewed/PublicDocs；source快照与工作树一致；预算/清理与内容检查 |
| A-08 根因/差异/报告 | PASS | 冷缓存根因、精确直接启动、健康披露、三Scene事实、离线导出错误及source版本区别清楚记录 |
| A-09 Git交付 | PENDING | 唯一中文主结果及5个rev-2输出已准备；执行版已本地保存，待修复/报告commit、普通push与fresh远端核验 |

最终定向 suite **12 tests通过**。第一次冻结源码的完整隔离Runtime为312 tests、0failures/errors、2skip；导出/Verifier修复后，以新 `tests/snapshot-final/` 再跑**313 tests / 19.408s / 0failures / 0errors / 2skip**。五个允许源码与工作树逐个normalized SHA相同，结果记录在 `.local/rpf-55-rev2/tests/regression-summary-final.json`；原执行版快照也保留。未借旧测试快照冒充当前版本。

8份历史固定外部SHA（RPF43/44/48/49/50/51rev4/52rev3/53rev6）重新调用各自Verifier均exit0，前后两次回归检查均保持；Reviewed Artifacts与Public Docs均exit0。两个Docker integration class因本轮禁止启动Docker/依赖不可用而明确skip，没有把skip计为PASS。diff/精确白名单、私有绝对路径/secret、原始字段不变及端口清理在交付前检查。

Maven/Web/GUI、额外readiness JVM、真实模型/Explorer、生产API、第三域、双Agent、独立重放均NOT_RUN或本轮不适用。采用原推荐顺序，没有增加场景/配额或改Oracle；唯一执行策略调整为每次重建显式ProcessStart绑定，纯离线导出修复按Plan Phase3完成。

## 6. 解释与交付责任

证书支持的是受控配置域Fixture与本地Host成功交付故障的有限机制。readback虽是独立GET，仍来自同一Java服务信任域；`issuer_authenticity`与`database_independent_authority`为NOT_ESTABLISHED，`independent_reproduction=NOT_TESTED`。真实Target模型与Explorer未执行，PGE闭环/WorkSwarm为NOT_PROVEN。再次核验此文件不是独立复现，也不证明生产长期安全或统计因果。

`EVIDENCE_ACCEPTED=PENDING_ARCHITECT_REVIEW`，`STAGE_ADVANCED=NOT_DECIDED`。本轮不授权真实Explorer×Target或第四场景，不修改main的canonical Project State。Git最终SHA、普通push和fresh远端/main观察在同次聊天回执提供，不循环填写包含自身的SHA。
