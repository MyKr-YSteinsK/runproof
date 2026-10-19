# RPF-55｜TASK_RESULT

**Plan ID: RPF-55 / Revision: rev-1 / Status: Partial**

## 1. 结果与范围

已实施受限 Config Experiment Adapter、严格三合同、故障 actuator、独立离线 Verifier 和测试。正常与 suppressed 两个新 Java/H2 场景取得完整业务、SDK、故障及只读读回观察；inhibited 场景在 SDK 进程启动前因冷进程解释器绑定缺失而受阻。**三个 JVM 配额已用尽，不重跑，不签发完整成功 Witness。**

[experiment-summary.json](experiment-summary.json) 为可追踪失败摘要，schema=`rpf55-config-experiment-failure-summary-v1`、`success_certificate_issued=false`，SHA-256=`e58cced6470109514bf635517ff4c5bcf8f702835c94bbc01e7995c4e94b59fa`。没有创建 `config-experiment-evidence.json`。摘要中两个单场景通过不代表三场景实验通过，也不代表新 `EVIDENCE_ACCEPTED`。

实际 root 为既有 runproof；Base/Parent=`77cef321ab95383583b4a983d667d5e2c03722d0`，父分支 `codex/rpf-54-pge-stage-closeout-extension-spike`；新分支 `codex/rpf-55-bounded-config-experiment-adapter`。origin fetch/push 均为 `https://github.com/MyKr-YSteinsK/runproof.git`。执行前 fresh远端 Parent 与Base一致，新分支不存在，main=`bda0cd49e50e3181f604324e94877a24b9885334`。起始无tracked/index修改，只有既有 `?? docs/reviews/`；该目录未进入、读取、枚举或暂存。

只新增白名单内8个文件，没有修改旧 Runtime、旧测试、旧证书、AGENTS、Project State、history、Java外部仓库、Web或workflow。固定feature push不触发main Release Gate或部署；本轮无PR/merge/tag/release/publish/deploy。

## 2. 实现与技术选择

- `config_experiment_contracts.py`：Execution/Effect/Experiment及FaultPlan独立版本，严格字段和canonical比较；冻结owner/run/namespace、三候选、三工具、目标v2/[2,1]、端口与硬预算。未知candidate、endpoint、路径、字段或惰性fault升级被拒绝。
- `config_experiment_adapter.py`：在既有Host之上使用Fixture-only子类；原 `_tool` 先验证SDK intent、参数和replay，原业务逻辑确认update HTTP200/code0/v2，再触发一次 `SUCCESS_WITHHELD`。正常与inhibited不触发；触发后锁死Tool/业务写入。`ExperimentHttp` 保留静态请求映射，逐次HTTP/Tool先写入新append-only ledger再操作。
- `config_experiment_verify.py`：独立确定性离线核对三场景、合同/source、HTTP namespace和结果、唯一POST、事件先后、Tool/Completion/Return绑定、SDK PID/RECORD、Authority、预算、清理及声明边界。接受合成数据时保留 `SYNTHETIC_TEST_ONLY` 标签。该Verifier不是Issuer签名。
- `probe.py`：固定manifest/source/JAR/SDK预检，Tier0→Tier1→三份预注册合同与不可覆盖marker；唯一真实Java Runner；SDK环境没有Provider/业务key。JAR复制到新任务目录，Java配置绑定新namespace、loopback、local/H2；无需修改Java或旧Live证书。

选择明确Tool交付错误，避免静默socket等待。业务成功返回被扣留，Handler实际返回HTTP400；既有SDK `_post` 将该HTTP错误转换为 `RuntimeError`。没有伪造成功回复，没有声称TCP丢包。Host内部计算的COMMITTED结果与SDK收到成功回执是分开的：suppressed的第三个 `returned_in_request=null`。

旧Fixture Host的兼容wire合同含历史task-JAR占位字段，只为原构造器格式校验；它没有启动JAR，也不作为本轮Experiment来源。实际执行来源、task-owned JAR路径和三合同均由新Experiment持有。业务合成名称保留旧协议要求的rpf53前缀，唯一55后缀绑定本轮Run。

## 3. 实际场景、来源与预算

三份合同先在 `.local/rpf-55/preflight/formal-reservation.json` 冻结，之后只使用原顺序/Run，没有重置marker或新分配第四JVM。

| candidate | Run ID / contract SHA-256 | 实际观察 |
|---|---|---|
| normal | `rpf55-550f73200244ba45f6` / `c9830bc0695df3cc24842b9f06ece62a475d847609c5cad0cd4e0c85b2838109` | JVM4432、SDK33432；8业务HTTP/2POST/1health；4Completion、3Tool及回注[2,3,4]；v2/[2,1]；fault=false/false/false；单场景通过 |
| planned-but-inhibited | `rpf55-5573060e6c9a314dbd` / `57698b52b943d0c3c9ad8918f9794265b62ba082673e2f2c5dc291a72481323b` | JVM12956；初始current/history两GET、1health；没有SDK子进程、Tool或POST；planned=true、triggered=false、observed=null/NOT_REACHED；合同结果INCONCLUSIVE |
| local-delivery-suppressed | `rpf55-5581aba585a0f64621` / `65697123a7b6a5283181de88008116eee44f3d18aecbc6258963a7775d0a5f6f` | JVM35528、SDK35096；8业务HTTP/2POST/1health；3Completion、3Tool、回注[2,3,null]；一次update200后withheld、SDK_ERROR，再只读GET确认v2/[2,1]；fault=true/true/true；单场景通过 |

摘要保留每份合同、HTTP status/business code、响应摘要、Tool/Completion、事件monotonic顺序、SDK report、JVM/端口和raw capture摘要。suppressed明确保留 `target_ack=UNKNOWN_OUTCOME`，独立父读回确认业务最终状态；没有将Host先见200等同SDK已收成功，没有update重试。

**总实际：3 JVM、18业务HTTP、4 POST、3 health GET、2个正式SDK进程；Tier1另2个SDK诊断。Provider HTTPS=0、tokens=0、费用=¥0。** 没有启动Docker或额外数据库、没有访问公网业务API、没有读取DeepSeek key或旧marker/ledger。

三场景的Java PID/listener、实际argv指向task-owned JAR、SHA/bytes、health与外连快照都现场核对；三个JVM与业务端口已退出/关闭，三个Host端口和线程均关闭。inhibited raw的 `sdk_exited=false` 表示该SDK从未启动，不是遗留进程。Java合成key未进入命令行、证书或日志，已从客户端引用释放，进程环境随JVM退出消失。task-owned JAR与已redact日志保留在ignored目录，未删除用户或旧任务资源。

固定Java source commit=`0258b9cef02ea74a40989d035c79256c776409c0`；manifest=`33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`，110files/393800bytes均hash核对。task-owned JAR为66981576bytes、SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。直接CPython3.12.13、Pydantic2.57.0/OpenAI3.35.1、RECORD444/2000及0mismatch、核心hash与原公开锚中的SDK身份一致；Popen/ready/report在成功场景一致，错误场景report无PID时只主张Popen/ready一致。

## 4. 失败、诊断与source差异

1. 最初预检执行旧venv wrapper遭Windows应用控制 `WinError4551`；没有SDK Tool或Java。改为从固定SDK配置定位、对照旧公开锚校验直接解释器，直接CPython/RECORD预检及Tier1正常/抑制两模式通过。没有更改系统策略或安装依赖。
2. normal完成后，离线Verifier期望health body只有status，实际Java还返回components及私有磁盘路径。保留原始body，生成明确 `STATUS_ONLY_FROM_RETAINED_RAW_HEALTH` 投影和原body/raw SHA后，单场景确定性核验通过；没有重发任何HTTP。
3. 后续ignored调度脚本重新加载Runner时，原helpers模块的直接解释器内存缓存为空。inhibited已启动JVM并完成两次初始GET，随后SDK启动路径回到旧wrapper，遭同一4551。finally退出JVM和Host，未发生业务写入。该场景额度保留，不重跑；在同一进程重新核验直接解释器身份后只执行原第三合同。
4. 第三场景取得真实故障/读回，原health全量响应通过相同的只读投影整理，不补造缺失SDK/HTTP字段。两份单场景verified capture仍不构成完整证书。
5. **执行后修复**：Runner增加JVM和SDK启动前的直接解释器缓存门；health raw与公开status投影分开保存。新增冷进程负控证明缺失绑定会在Popen前拒绝。修复仅做纯测试/回归，没有重跑正式场景。

正式执行source map digest=`5b96b0b4d4017ccf2efe5c1a074194c38f257d27fa597845f36acfc5f9ed17ca`；交付source map digest=`06b59fdaf4868b4c0e33bdd0992c56fd12166ecfea41538ab852aebb2cd08849`。完整两map在摘要，唯一差异为本轮probe修复：执行版=`d56c64c8b76631c2be5a9ddcd07c70a7490eecd4205444246771e19658de2944`，交付版=`bb073ee62557df0c628b88ee05b1b7dd00c297bae4d33fd501baa18de0abc314`。Adapter/新Verifier与旧源码身份未变；不将交付后的Runner冒充已完成三场景验收。

原始资料在 `.local/rpf-55/scenarios/<candidate>/`，包括started、ledger、raw、两份verified-scene及redacted Java日志；两次SDK诊断在fixture；预检、synthetic证书/篡改、失败摘要备份和调度脚本均在本轮目录。最初失败摘要已保留至quarantine，最终tracked摘要保留完整缺口。

## 5. 验证与验收

| Gate | 结果 | 实际证据 / 缺口 |
|---|---|---|
| A-01 身份/权限保护 | PASS | exact Base、origin、远端Parent/main/newref、AGENTS与push副作用；8个新文件，无旧tracked修改；reviews保持原untracked状态 |
| A-02 三合同/FaultPlan | PASS | 严格canonical freeze/身份/白名单与未知参数负控；3份新合同先注册 |
| A-03 actuator | PARTIAL | normal未触发、suppressed实际一次HTTP200后扣留并停止；inhibited只完成注册，未到达Tool gate |
| A-04 真实SDK/旧行为 | PASS（限定） | T1两模式完成真实SDK/Tool/Return/PID及guard检查；旧Runtime零修改且完整回归；T2第二场景失败单列 |
| A-05 三个真实Java场景 | PARTIAL | normal/suppressed完整；inhibited没有SDK Tool Loop，未满足正常等价对照；不增加JVM或POST |
| A-06 新独立完整Evidence | NOT_MET | synthetic完整证书0/2/3与7类rehashed tamper通过；真实三场景缺口，未签成功证书；两个单场景核验不替代此Gate |
| A-07 权限/回归/预算 | PASS（限定） | 309 tests、0failures/errors、2 Docker skip；8历史锚、Reviewed/PublicDocs通过；正式预算内、进程/端口清理；修复未补真实场景 |
| A-08 调查与差异 | PASS | 明确复用点、交付抑制通道、真实event/Authority及两次工具/证据整理问题、初始/交付source与未完成项 |
| A-09 Git交付 | PENDING | 8个新文件与单一中文主结果已准备，待focused commit、普通push与fresh refs核验 |

实际命令及结果：

- `python -B -m unittest runtime.tests.test_effectwitness_config_experiment -v`：最终8 tests通过，包含三种actuator/单次触发/replay、冷进程、完整synthetic、严格合同/source及rehashed负控。
- 新Verifier以独立Python CLI跑完整合成Envelope：correct/missing/wrong=`0/2/3`；false_trigger、namespace_splice、duplicate_post、authority、cleanup、sdk_callbacks、false_ack七类重新计算内外摘要后均exit3。Tier0正式运行前通过，交付修复后再次纯离线通过。它们都是 `SYNTHETIC_TEST_ONLY`，没有冒充真实实验。
- 完整Runtime在新 `.local/rpf-55/tests/snapshot/` 隔离快照执行，最后**309 tests / 23.321s / 0 failures / 0 errors / 2 skipped**；Docker/Java进程在回归中明确拒绝，外连限制loopback，未继承key。两个Docker unavailable class skip如实保留。
- 首次完整回归308 tests中，既有config-target HTTP4xx测试发生一次WinError10053连接中止；同一隔离测试重跑通过，随后完整309测试通过。旧生产源码/测试未修改，没有以skip隐藏该错误。
- 8个历史anchored verifier（43/44/48/49/50/51rev4/52rev3/53rev6）用固定公开外部SHA重新运行均exit0，旧artifact字节未变。`runtime/verify-reviewed-artifacts.py`、`ci/verify-public-docs.py`均exit0；diff/白名单/secret/私有绝对路径检查交付前完成。

Maven/Web/GUI、真实Provider、真实Explorer、完整三场景重跑均NOT_RUN；当前Plan不需要前者，也不授权超配额重跑。新完整成功证书的真实CLI验收是缺口，不能以synthetic PASS替代。

## 6. 后续与交付

当前分支新增了受限Adapter实现，并观察到一次正常控制与一次预期Host交付故障；planned-but-inhibited缺失，不能主张完整三方对照、统计因果或稳定恢复能力。

下一步需新的受控补验收Plan：新工作区、新Run和JVM额度；先验证当前Runner的完整冷进程启动路径、health投影和场景/证书整理，再运行缺失对照及所需配对场景。当前不得继续复用或删除本轮marker。真实Explorer×真实Target仍须后续明确授权、双角色总预算、配置session/candidate/selection lineage与完整离线证书，本轮不自动授权RPF-56。

`TASK_COMPLETE=FALSE`，`EVIDENCE_ACCEPTED=PENDING_ARCHITECT_REVIEW`，`STAGE_ADVANCED=NOT_DECIDED`。Issuer真实性、数据库独立Authority未建立；独立复现未测试；真实模型与Explorer未执行；PGE/WorkSwarm均NOT_PROVEN。同一证书或capture的离线核验不算独立复现。

Git最终SHA、普通push与fresh远端/main核验在同次聊天回执提供。本文件不循环填写自身SHA。
