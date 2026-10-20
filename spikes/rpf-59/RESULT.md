# TASK_RESULT — RPF-59 / rev-1

Status: Partial

2026-10-20；免费合同、四种合成序列、真实cold、正式Session及Witness已完成，等待Git交付。`EVIDENCE_ACCEPTED=PENDING_ARCHITECT_REVIEW`，`STAGE_ADVANCED=NOT_DECIDED`。

## 1. 工作区、来源与边界

Root：`D:/CS/runproof`。Base/Parent：`03d13513ad958cf01455a39bede4f873ed474e21`；新分支：`codex/rpf-59-cross-domain-real-explorer-selection`；origin fetch/push 均为公开 `MyKr-YSteinsK/runproof`。远端新分支最初不存在；父分支与main快照经现场核对相符，main为 `bda0cd49e50e3181f604324e94877a24b9885334`。

起始tracked/index干净，仅顶层 `?? docs/reviews/`。该用户目录未进入、枚举、读取或变更。新 `.local/rpf-59/` 创建前不存在且被ignore，父路径无link/reparse。未读取旧RPF58/57/56/55/53私有运行根；固定SDK安装与Java来源仅按授权只读。全部新增代码与交付限定Plan白名单，不修改任何历史源码、测试、证书、Project State或CI。

执行Source Map包含25个文件（含本轮测试）；canonical digest：`8eec55aea999d88f6cc2fe060a6ca6411a93182a01d9384e0cab55d1d533effa`。Verifier：`rpf59-selection-verifier-v1`，SHA `51f796b75ec7c7dea2a1513d2f0e18dc626b059245eb9449decb2c0d52802433`。详细Map随验证诊断保存。所有执行源须与offline/preflight/cold/正式执行/签发相同，cold后不修改执行源码或测试。Host/Verifier为CPython 3.14.6；SDK child为固定CPython 3.12.13。运行时callable指纹包含Python字节码，离线重验应保持兼容的Host字节码版本；未证明任意Python版本/平台通用重验。

## 2. 技术决定与复制债

旧RPF58的 `pge_shared_contracts.plan` 与 `Ledger.reserve` 固定order→config、每域一次，旧Port冻结旧WORK，不能直接接收动态选择。采用新增 `pge_select_*` 版本；未monkeypatch旧模块全局，也未将新合同投影为假旧合同来绕过原Verifier。

- `pge_select_contracts`：静态两个candidate映射，预注册2Round×2候选合同、四个唯一Run及不同端口。候选ID不参与import/路径/URL/OS命令构造。
- `pge_select_session.SharedSession.execute_trial`：唯一编排入口。`RoundAccount`只是同一物理Ledger的round视图；Explorer请求与所有正式业务资源都在这一WAL先预约再执行，不创建域子账本。
- 每个Provider请求预留3000tokens与54000微元保守费用，两个请求总预留6000tokens/¥0.108；已知usage仍不返还预约，未知usage保留占额并停止。任意UNKNOWN写停止，不重发退款或POST。
- `pge_select_explorer`：具名唯一工具、non-thinking、非并行调用；先fsync安全响应形状/usage/ID/请求SHA，再严格parse。只保存结构指纹与合法选择，不保存自由正文或reasoning。第二轮输入只从已验证反馈、原始合法Tool Call ID和coverage构造，不删除已测候选。
- 订单Adapter保留真实SQLite事务、独立mode=ro/query_only Reader与HMAC/业务Oracle；配置Adapter保留pinned SDK scripted Fixture、Java17/H2、HTTP readback和SDK回执先写后检查。两域Authority分别为独立SQLite Reader与同服务只读GET。
- 独立Verifier重算领域Oracle、choice/shape/Tool ID/usage、整条WAL快照链、预算事件、真实函数指纹、反馈时序与研究标签，拒绝跨源和合成升级。

复制来源为Parent下RPF58v2的订单Port、配置Port、合同/反馈、WAL及TaskGuard生命周期片段；Explorer安全投影/请求逻辑来自RPF56v4/RPF57已验证实现。配置场景Oracle与原RPF55 `verify_scene`逐字对照测试通过。最主要重复面积是完整版本化配置Adapter（409行，含独立场景Oracle）和订单Adapter（83行）；新合同84行、反馈22行，生命周期与TaskGuard在229行新版Session中组合并改造，Explorer135行沿用安全投影与请求协议。共享预算/选择语义在新模块实现。没有新第三方依赖或外部代码供应链。该版本保留复制维护债，未来抽取需单独授权；不宣称零复制通用Agent框架。

## 3. 免费Gate与真实cold

四种组合order→order、order→config、config→order、config→config均通过完整合成Session。最终16项定向测试通过；每个组合独立CLI外部锚0/2/3、25类重算摘要篡改均拒绝。额外16项（4组合×假故障激活/缺失Authority/cold PID拼接/非loopback合同）重算摘要后拒绝。正控与拒绝样本只留本轮ignored目录。

负控覆盖非法/空/多项工具、错误函数与candidate、Tool Call ID伪造/复用、未来反馈、slot/namespace重用、跨域事实/Authority、假effect、旧owner/证书/schema、混源/假cold、重复写、未知usage归零、超额/拆账、时序倒置、清理及研究过度宣称。实际两个子进程竞争仅一个Provider预约成功；未知usage/业务写、损坏快照、锁竞争、deadline、source漂移均fail closed。SDK生命周期Mock覆盖Host已关闭、畸形报告、保存回执失败与失败额度保留。

metadata实际1进程PASS；Pydantic AI 2.57.0 / OpenAI SDK 3.35.1，固定RECORD/core/CPython身份通过；Java17/JAR来源manifest与字节SHA通过。未安装、修改或改名解释器/SDK/Java，也未调整系统安全策略。

cold尝试1：**ACTUAL PASS**，Popen/ready/report PID均38008；4completions、3唯一工具、回注[2,3,4]；实际FAULT_INHIBITED；stderr0，COMPLETED/exit0；SDK退出、Host线程停止、端口关闭均true。capture canonical SHA `5946e126ece883faf000d925ba8af945108a689a12d7856fe70c17fca41068fc`。尝试2 **NOT_RUN**；cold的Provider/JVM/正式业务计数均0。capture及started/received/cleanup原始结构保存在新任务根，成功证书中包含脱敏capture。

官方模型/工具支持与价格于执行日核实：[价格](https://api-docs.deepseek.com/quick_start/pricing/)、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。请求模型固定deepseek-flash，允许返回DeepSeek-V4.1-Flash-1017；美元峰值input0.30/output1.20每百万token×15作为人民币保守守卫（4.5/18），不是汇率或账单。最多2请求/6000tokens/估算¥0.15，没有付费协议探针/备用模型/自动付费重试。

## 4. 正式Session与Witness

**ACTUAL PASS**：唯一Session `rpf59-session-966ab13e1fdf471d`；共享Host PID 3908；WAL 83个不可变快照，业务资源/反馈事件跨度约47.369秒（上限2400秒）。

| Round | 真实Explorer选择 | Tool Call ID | prompt/completion/total tokens |
|---|---|---|---|
| 1 | `order-refund/normal` | `call_00_f2uoTIqhy8tmq2rUqpQE6955` | 466/40/506 |
| 2 | `config-java-http/planned-but-inhibited` | `call_00_G8yBJ2vcstWDOHmqnIgT1590` | 780/46/826 |

合计2请求、1332tokens，按冻结保守单价估算¥0.007155；实际扣款未查询。两个返回model均为deepseek-flash，与固定请求模型一致。请求/响应ID及脱敏形状见 `protocol-diagnostic.json`。没有探针、付费重试或人工替选。

- Round1：Run `rpf59-order-3a0d4487c31d494f`，request SHA `67464c9b12e5d1dcdef43cf249e16f20471a700e50e44d32429c3f6e33bea3f4`，response ID `3b64fff9-891b-4ef3-85f2-60cdeb8c948b`；反馈SHA `08a83e12070865dac7eed421e95ed240837ec1aea112548e1b5db4c5e4cc501b`。
- Round2：Run `rpf59-config-6afc3df120e449e2`，request SHA `b07efa5eed802536191dc422a0aea47d8200e76668d7485ffd228f7c5766a0e9`，response ID `28c30e17-b5ad-4d4b-994d-3f430c9982e1`；反馈SHA `2b6ca24679b96cab06b33a8a55af17b8d11b589a06318710043a373ed12204cf`。

### 实际业务与Authority

订单：fresh SQLite PAID2500/refunded0/revision0 → REFUNDED2500/revision1，唯一COMMITTED receipt `receipt-1098f97c50b457326e26fece`。一次退款mutation，独立mode=ro/query_only Reader/HMAC与effect Oracle通过。DB原始SHA `6d1be5cea88a73dbb23eb7888079b3af2514fd35137b71264ac4934157edaebb`；连接关闭/exclusive-lock probe均通过，DB保留证据。planned/triggered/observed=false/false/false。

配置：fresh Java17/H2，Java PID 31980，SDK Popen/ready/report PID均35296。初始ABSENT，最终rpf53-v2/version2/history[2,1]；四completions/三工具/回注[2,3,4]，8业务HTTP、2POST、1实际health UP。health预留3槽，另2槽UNUSED_RESERVED_NO_IO，不假称3次GET。实际FAULT_INHIBITED，planned/triggered/observed=true/false/false。SAME_SERVICE_READ_ONLY_HTTP Authority与纯函数Oracle通过；JAR argv/listener所有权/无外联与六项cleanup均通过。

### 反馈与同一账本

- Round1：PROVIDER_REQUEST_FROZEN=2 → CHOICE_FROZEN=4 → SHARED_PORT_DISPATCH=6 → DOMAIN_CALL_ENTERED=7 → DOMAIN_CALL_RETURNED=15 → DOMAIN_VERIFIED=16 → FEEDBACK_FROZEN=17。
- Round2：PROVIDER_REQUEST_FROZEN=20 → CHOICE_FROZEN=22 → SHARED_PORT_DISPATCH=24 → DOMAIN_CALL_ENTERED=25 → DOMAIN_CALL_RETURNED=79 → DOMAIN_VERIFIED=80 → FEEDBACK_FROZEN=81。

Round1 feedback与Trial结算均在Round2 Provider预约/请求冻结之前；独立Verifier重建两轮精确请求body，第二轮保留两候选和原合法Tool Call ID，只含已验证事实，不包含未来数据。两个Port的实际callable指纹与同一SharedSession入口绑定。

| 正式资源 | 实际 | 硬上限/预留 |
|---|---:|---|
| Session/Trial | 1/2 | 1/2 |
| Provider/tokens | 2/1332 | 2/6000；预约6000不返还 |
| 费用估算 | ¥0.007155 | ¥0.15；预约¥0.108不返还 |
| SQLite/退款mutation | 1/1 | 2/2 |
| JVM/SDK Fixture | 1/1 | 2/2 |
| 业务HTTP/POST | 8/2 | 16/4 |
| health | 1 | 最多6，本次预留3、未用2 |

全部正式资源DONE，无UNKNOWN、返还、拆账、重启或额外Trial。metadata1/cold1均有独立append-only任务预约，cold02未用。

### 新Witness与限定结论

`cross-domain-selection-evidence.json`：1,071,675 bytes，schema=`rpf59-cross-domain-selection-evidence-v1`，source_kind=`REAL_EXPLORER_CONTROLLED_TARGETS`。

**外部原始字节SHA-256：**

`0bb359ca78c7c0415afef30ff959d41112da3f5155e5ae18e68be28735f9996a`

真实证书独立CLI correct/missing/wrong anchor=0/2/3；25类重算内外摘要的CLI负控全部退出3，额外4类语义负控亦拒绝。Source、冷回执、两轮业务、账本和签发身份一致。

实际order→config，candidate_changed/domain_changed=true，TWO_DISTINCT_DOMAINS_IN_THIS_SESSION=YES，CROSS_DOMAIN_ADAPTIVE_SELECTION_OBSERVED=YES_OBSERVATIONAL_ONLY。领域内新增事实分别为1和2；不相加为跨域信息增益或统计优势。真实的是Explorer选择，Target仍为确定性订单/SDK scripted配置；本次结果不升级为两个真实LLM Target、因果适应优势、数据库外部Authority或独立复现。

## 5. 回归、历史锚与验收

首次隔离全量发现381项：1个旧路径守卫测试因隔离环境缺少home导致ERROR，2Docker skip；Runtime未修改。仅修正本轮ignored回归helper，将HOME/USERPROFILE指向task-owned测试home；原失败日志/诊断保留。最终完整重跑381项，379成功、2Docker skip、0失败/0错误，463.254秒；最终隔离快照与交付源码相同。该环境失败不属于cold/业务/Provider重试。

12件历史外部固定锚经当前工作树原始CLI全部退出0：RPF43/44/48/49/50/51r4/52r3/53r6/55r2/56r4/57v1/58r2；旧原字节与Verifier未改。Reviewed Artifacts和Public Docs通过。Web/Maven/UI/Docker正式边界/Hosted CI **NOT_RUN**。

实际主要命令（`python`为Host CPython 3.14.6）：

```powershell
python -B spikes/rpf-59/probe.py offline
python -B spikes/rpf-59/probe.py preflight
python -B spikes/rpf-59/probe.py fixture
python -B .local/rpf-59/regression.py full
python -B .local/rpf-59/regression.py anchors
python -B .local/rpf-59/extra_controls.py synthetic
python -B spikes/rpf-59/probe.py live
python -B .local/rpf-59/extra_controls.py real
python -B .local/rpf-59/final_audit.py
python -B runtime/verify-reviewed-artifacts.py
python -B ci/verify-public-docs.py
python -B -m runtime.runproof_runtime.effectwitness.pge_select_verify spikes/rpf-59/cross-domain-selection-evidence.json --sha256 0bb359ca78c7c0415afef30ff959d41112da3f5155e5ae18e68be28735f9996a
```

`offline`实际执行 `python -B -m unittest runtime.tests.test_effectwitness_pge_select -v`；完整回归在新任务根的隔离源码快照执行 `python -B -m unittest discover -s runtime/tests -p 'test_*.py' -v`，所有缓存/home/temp仅在新root。没有读取原历史运行根。上述live/fixture是已消耗的一次性入口，不是再次运行授权。

完整全量日志与9个本轮文件的实际快照SHA位于 `.local/rpf-59/diagnostics/full-runtime.{log,json}`；cold与源码冻结在新root的preflight目录；正式request/shape/两轮Oracle结果位于replay；全账83帧在ledger；未删除初次全量环境错误日志。12件锚的原路径、精确SHA、原始CLI module/flag和退出码，以及Source Map、完整25类CLI负控与4类额外负控，公开于 `verification-diagnostic.json`。

| Acceptance | 状态 | 依据 |
|---|---|---|
| A-01 | PASS | 精确Root/Base/remote、新分支与task root、用户目录保护 |
| A-02 | PASS | 新schema、静态候选映射、独立namespace，历史源不改 |
| A-03 | PASS | 四种组合、同一WAL/入口、锁/未知/恢复拒绝 |
| A-04 | PASS | 两个实际新Port均执行，SQLite与Java/H2各自Authority/Oracle通过 |
| A-05 | PASS | cold01真实PID/工具/gate/cleanup；cold02未使用 |
| A-06 | PASS | 唯一Session两次真实工具选择、用量/来源/全账绑定 |
| A-07 | PASS | 两轮真实业务通过，Round1反馈先于Round2请求冻结 |
| A-08 | PASS | 新限定Witness、0/2/3、25类CLI及4类额外语义负控 |
| A-09 | PASS | 定向16、全量381/2skip、12锚/Reviewed/Public、预算与清理通过 |
| A-10 | NOT_RUN | 等待focused commit/push及远端SHA核对 |

## 6. 残留、限制与交付

本轮metadata/cold/WAL/原始结构回执、固定JAR副本、隔离快照、失败和负控样本仅在 `.local/rpf-59/`；无需的生成器在收口清理。Provider Key不会进入Git、SDK child、公开证据或日志。旧运行目录与来源安装保持原状。

交付前实际只读复核订单Reader/DB原始字节与证书相同，三个owned端口7138/7139/12152均关闭；秘密与私有路径扫描无非预期命中（报告内明确授权的仓库Root单列）。15个暂存文件原始字节与已验证工作树一致，`git diff --cached --check`通过；原tracked源码/12证书均与Base字节一致。一次性版本/测试/报告生成器已删除，复现helper及必要成功/失败证据保留在新ignored root。

只有Explorer是真实LLM；订单确定性Target与配置SDK scripted Target的等级不升级。重复领域是合法研究结果；未选择领域不得记为本次实际执行。跨域信息增益不可比，H1/H3/因果优势/WorkSwarm未证明，Issuer与数据库外部独立Authority未建立，独立复现未测试。单次切换至多记观察性结果。

Git：尚未commit/push；仅本轮新安全分支允许交付，无PR、main写入、merge、tag、release、deploy或workflow dispatch。最终SHA由聊天回执提供，不循环amend报告自身。不自动开始RPF60。
