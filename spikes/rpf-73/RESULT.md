# TASK_RESULT｜RPF-73 / rev-1

Plan ID: RPF-73

Revision: rev-1

Status: Partial

## CURRENT STATE

Config 与 Order 已通过同一个显式 `LaunchFactory.launch` 实际启动原固定 SDK child，完成4次模型请求、3次领域 ToolCall/ToolReturn和 terminal stop。Factory 自己拥有 Popen/communicate；以显式 ContextVar 核对真实 Windows audit，不查找 NativeDriver 帧，不使用 profiler。SDK 工具结果为虚构组件数据；没有运行真实配置服务、退款、Authority、PGE反馈或真实模型。

Source commit `523f6bcaf5487016ac6d3429d294bb850c33ae6a`；source identity `e4ea3cc40987e1c90aa683ec324aa33a2d9d97e1e2d713fb84fb75bc039a3db1`，17文件 raw/LF闭包。Base `a055bfa1844f1df7de459daf35107de7a3ae2d2c`；分支 `codex/rpf-73-versioned-launch-factory-cross-domain`。10项 execution/test/probe已冻结，11项事后报告不属于执行Source。只新增21路径；所有旧源/SDK/Guard/证书/报告保持原字节。源码已普通push并经Git/API核对；A10在报告生成时待最终回执push，最后聊天提供准确回执SHA与两轮远端HEAD/blob/diff，不回填本文件自身SHA。

## TARGET INTENT

Owner=`rpf-73`，ABI=`rpf73-launch-factory-v1`，source_kind=`RPF73_FIXED_SDK_LAUNCH_COMPONENT_ONLY`。边界为组件执行接缝，不改变 native Driver/Guard 或完整公共Core。BudgetView仅参照 Config250000、Order160000、11槽474000<=600000、max_slot160000；Provider预约和真实模型usage均0。SDK实际body保持原child的max_tokens512，原槽输出参照256/512，模拟响应每次20；输入上界额外保守加512后仍受槽位约束。

## PLANNING CONTEXT / 权限补充

Architect在本Plan接受RPF72R3历史证据；它不是本轮证书。旧R72R2 FAIL不回填，R70～72私有根均UNAVAILABLE_NOT_READ。用户额外明确授权“允许原有 fixture 独立计账，继续完整回归”：Factory仍最多6次；原不可修改Runtime测试的SDK/SQLite等fixture只在当前snapshot内执行并单独计账，不当作R73真实业务证据。未扩大Provider/业务权限或Source白名单，未修改canonical Project State。

## Gate

| Gate | Status | 证据 |
|---|---|---|
| G0 | PASS | Exact Base/repo/remote;21 absent local/index/Base/API; own ignored non-reparse root, SID/ACL, pinned SDK RECORD |
| R73-A01 | PASS | Canonical new owner/ABI/request/receipt; both domains use same Factory entrypoint; frozen current Source closure |
| R73-A02 | PASS | Actual direct native Popen audit/stdin/PID/READY/REPORT/exit/cleanup; no frame/profile dependency |
| R73-A03 | PASS | Config/Order real fixed SDK agent.run, distinct typed fictional tools, terminal stop, Provider0 |
| R73-A04 | PASS | 250000/160000 actual SDK limits; legal-high and real250001 SDK rejection; 11-slot arithmetic only, no provider wallet |
| R73-A05 | PASS | Same original A/B bytes+anchor CLI0/2/3;96 valid semantic controls,70 launch/env/owner/pin,4 coupled attacks; invalid fixture excluded |
| R73-A06 | PASS | Original Guard bytes; real loopback-only, explicit absent reports,5 completed getter reports,pressure error no getter report; exact PID/port/threads cleanup; dry UNKNOWN state tests |
| R73-A07 | FAIL | 30 focused PASS; full665 exit1,8 errors,0 failures,2 original Docker class skips. Exact670-ID accounting and snapshot/source bytes unchanged; required Full gate FAIL |
| R73-A08 | PASS | 24 original public/native verifiers +R69 CLI0/2/3; legacy private unavailable/not read; old Source/report bytes unchanged |
| R73-A09 | PASS | Static and actual two-domain parity; measured code/overlap, no speedup claim; alternatives/debt/actionable recommendations |
| R73-A10 | NOT_RUN | At generation: Source commit/push dual-read done; final receipt push and two Git/API HEAD/blob/diff readbacks supplied in final chat, no self-SHA rewrite |

A10为生成时事实，最终聊天补足交付状态；TASK_COMPLETE不等于Architect接受或阶段推进。

## 实际 SDK / 启动 / 预算

| Case | Domain | PID | State | usage |
|---|---|---:|---|---:|
| development-smoke | config-java-http | 11744 | COMPLETED | 30049 |
| corrective-config | config-java-http | 11176 | COMPLETED | 36049 |
| corrective-order | order-sqlite | 19292 | COMPLETED | 37365 |
| formal-config | config-java-http | 10600 | COMPLETED | 36049 |
| formal-order | order-sqlite | 11340 | COMPLETED | 37365 |
| limit-plus-one | config-java-http | 6572 | EXPECTED_REJECTION | 250001 hint / UsageLimitExceeded |

首次development真实SDK/协议/cleanup完成，但30049未达到高累计样本要求。源码冻结前将固定padding6000→7500，并使用每域一次的已授权纠错，原件和不足均保留；两纠错及两正式样本累计36049/37365。最后limit子样本由原UsageLimits实际抛出UsageLimitExceeded，exit1；250001仅为输入合成hint，不冒充可信最终RunUsage。总Factory child6，纠错额度已耗尽；无追加/重置/删除marker或WAL。六次均有原始Popen audit、serialized cfg SHA、PID/start/exit、READY、report/raw stdout摘要和清理；压力SDK_ERROR没有缺失getter报告，不伪造。

每个正式域使用独立loopback Host，3个不同领域schema工具和唯一Call/Response ID，实际SDK原始请求字节、追加消息、ToolReturn字节及SDK RunUsage逐项复验。两个正式域共8次请求，少于5/4及11总参照上界。`launch-parity-matrix.json`列实际PIDs、cfg/env/argv/cwd/pin摘要、Source、调用链和清理。原始10字段环境、token、绝对路径仅在当前私有Manifest/WAL，公开不含完整PATH/HOME/token。公开digest-only信息不足以独立验证完整env语义，标INCONCLUSIVE；本地原始bytes/anchor才用于完整CLI。

NATIVE_R68_DRIVER_MIGRATED=NO、SDK_GUARD_MIGRATED=NO、FULL_COMMON_CORE_MIGRATED=NO。新局部component WAL仅记录ADMITTED→HOST→实际Popen→出站字节→SDK交互→EXIT/CLEANUP→RESULT_BOUND；没有shadow Provider钱包或真实业务Witness。失败/UNKNOWN保留case与PID claims，不返还额度。实际异常证据是SDK累计阈值拒绝；取消/UNKNOWN回调关闭另为纯dry-run，真实业务故障四态/L2本轮NOT_TESTED。

## CLI / 负控 / 历史 / Runtime

正式Config/Order和限额拒绝原件各在A/B独立进程保持同一raw bytes及anchor，均exit0。仅验证进程SYSTEMROOT/WINDIR大小写与安全PATH顺序局部改变；系统环境未改。两正式原件无anchor→2、错误anchor→3。实际96项语义负控拒绝，含70启动/env/owner/pin类和4项深层联动：relative PATH、foreign HOME、cumulative bool、SDK input usage。内层cfg/env/receipt/event/WAL链和raw anchor联动后，仍因独立语义被拒绝。

一个stdout-hash负控生成器把拟破坏字段恢复为与stdout一致，仅剩合法CRLF/LF重序列化；其exit0样本保存为TEST_INVALID_NOT_COUNTED，不计PASS。仅私有生成器修复，Verifier/Source未改；纠正后的真实CLI返回STDOUT_RAW_BYTES。其余已执行拒绝按原日志/源SHA复用，未重跑SDK。

聚焦测试30项，exit0，wall 0.690s，实际最终summary存在。历史24个原生公开验证入口及R69 CLI0/2/3全部原anchor、原verifier通过；RPF72R3公开源码/报告无变，旧私有证书未读取。完整Runtime仅1次，单一当前source-identical snapshot，标准discover无过滤、无动态替换runner、无拼接缓存结果；原始日志最终为：

```text
Ran 665 tests in 2225.926s
FAILED (errors=8, skipped=2)
```

实际exit=1，errors=8、failures=0，receipt wall 2228.247s。发现670项；实际665项加两个原Docker类级skip覆盖5方法，精确multiset还原发现清单，诊断拆行的终值按原起止行记录，ERROR不算PASS。919个实际snapshot源字节在结束后与原copy SHA/当前源比对；Source drift=False。本次Full完整结束但失败，不符合仅环境平台中断才允许第二次的条件，且续接时已接近全任务210分钟上限；没有重跑、改源码/旧测试或拼接PASS。parent3.12完整suite和HostedCI均NOT_RUN，未触发workflow。

7项ERROR的直接原因是本轮私有ops.environment额外追加父Python目录，而其SHA不属于旧R72R3冻结的TRUSTED_PATH_SHA256；旧测试在构造有效fixture时便报LAUNCH_PATH_TRUSTED_DIRECTORY。该目录来自runner构造，不能把错误归咎于旧Verifier，未放宽旧许可集合。第8项为原target_agent回环fixture的WinError10053，具体原因NOT_PROVEN。原ops receipt的unittest_final_summary只识别OK，所以字段false；原日志确有FAILED汇总，事后核对保留原字段并另记actual_final_summary_present，不伪装为缺少汇总或成功。A07=FAIL决定本轮Partial；组件与历史CLI通过不能覆盖此失败。

全部已记账SDK/CLI/unittest命令的argv/cwd/PID/start/elapsed/exit/python/log raw SHA/source前后见verification-diagnostic。初始只读Git/文件/API/SDK RECORD检查保留工具轨迹和早期G0诊断，部分初始shell/metadata probe的PID/单调start未捕获，标UNAVAILABLE而不伪造；它们不是SDK Agent运行。SDK固定Python3.12.13、PydanticAI-slim2.57.0、OpenAI3.35.1；RECORD443/1999 hashed条目均零不匹配。SourceMap记录raw/LF、Git/SDK/bin/launcher/cfg/child pins及CURRENT/NATIVE_READ_ONLY/HISTORICAL_REFERENCE_ONLY分类。

## Key / 清理 / 外部边界

宿主Provider/业务Key查询0，Controller只读SYSTEMROOT/WINDIR/PATH。child环境固定10键，无真实Key；5份COMPLETED原报告provider/business_key_present均false，两处SANITIZED_CHILD_ABSENCE_PROBE各至少5次。压力error没有该报告；所有库/原Runtime fixture getter总数未动态instrument，ALL_KEY_LOOKUPS_ZERO=FALSE/NOT_PROVEN。生成的token只用于本地回环，不导出。费用¥0、外部Provider0、真实模型token0。

六个Factory PID/port晚次检查PASS，原thread/process/port清理均true；未捕获创建时间/SID则明确UNAVAILABLE，不杀陌生或复用PID。真实junction已被拒绝，无提权/ACL/power policy改变。docs/reviews仅顶层status自然可见并保持未跟踪；旧.local原件不读、不清、不复制。原unit fixture全部在当前snapshot；没有Factory业务DB/JVM。未PR/merge/tag/release/deploy/CI dispatch/比赛提交。

## VERIFIED_FINDINGS

- F73-01 / CURRENT_STATE：`pge_r73_launch_factory.py:29 LaunchFactory.launch`及`:13 _audit`；当前Source raw见SourceMap，formal-config/formal-order真Popen/PID/字节及A/B原件CLI通过。消除的是新组件路径的frame/profile依赖，旧Driver/Wrapper仍未迁移。
- F73-02 / CURRENT_STATE：`pge_r73_launch_contract.py:48 LaunchRequest.check`、`:17 env_summary`；70纯准入+真实junction、96实际CLI反例与4联动通过。反例只证明具体语义边界，不证明共同重签不可伪造。
- F73-03 / CURRENT_STATE：`pge_r73_sdk_harness.py:28 completion/:57 callback`与BudgetView；实际两域RunUsage/stop及limit+1证明同Factory和预算确有执行。限制：结果全为SIMULATED_ONLY，不是业务/Authority证明。
- F73-04 / PLANNING_CONTEXT：architecture-audit对新387 runtime行、共518行及旧Driver124行、精确非平凡行重合做静态账本。不能由行数推导性能或零语义重复。

## CODEX_ENGINEERING_JUDGMENT

显式Request在调用入口消费Owner/Source、可信SDK pin和只读BudgetView，Factory拥有syscall与stdin；ContextVar只补充真实audit核对，不再猜旧方法栈。可信本地Controller组件范围内置信度HIGH，支持为两域真SDK、同方法、字节与usage回放及具体攻击反例。反证/限制为未接真实业务/Provider/故障反馈、旧Core未迁移、child不回显capsule、无外部签名。最便宜鉴别实验是下一Plan受限的真实Target+Fault接入，保留既有DomainPort/独立Reader并比较正常与提交后抑制返回；本轮不自动授权。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

| 路线 | 复制量/维护 | 攻击面/历史审查 | 性能证据 |
|---|---|---|---|
| 保持task-owned hook | 重复wrapper、依赖Native code frame | 旧路线不动；每次新closure仍需审查 | 没有隔离interception/scanning因果成本 |
| 当前显式Factory | 387 runtime行，单一launch+Adapter；小量协议/验证重复仍在 | 显式参数/本地HTTP/原Guard；可信Controller，旧证书保留 | 只记录本样本wall，不与旧业务N/F做加速比较 |
| 新child echo/强common core | 潜在收敛契约，短期最高开发维护成本 | 新Guard/pin/ABI和兼容矩阵；echo本身非独立签名 | 未测，不假定更快 |

可操作改进至少三项：①针对30049开发样本不足，在freeze前按首槽校准fixture并保留纠错来源；②针对无效stdout负控，关联修复后先核对目标字段确仍非法，保留原始换行与失败样本；③后续若接真实业务，先明确Port/UNKNOWN/Authority能力合同，避免再复制全Core或先扩Web/第三域/Issuer。

## NEXT_DECISION_RECOMMENDATION

首选研发决策：先以新的受限授权修复任务自有runner的PATH合同、定位旧回环fixture，并用冻结Factory源码取得完整Runtime通过。备选是在HTTP异常可独立复现时，先研究服务端拒绝/读取body/关闭与客户端getresponse的时序，不放宽旧env策略。组件证据支持后续评估真实跨域Target+Fault接入，但A07未通过时不先扩业务；恢复门禁后再沿用既有DomainPort/独立Reader验证真实UNKNOWN与反馈，早于Web/第三域/Issuer。需新runner/snapshot/time及必要旧fixture修改权限；真实Provider/故障/Authority另授权，不自动开启RPF74。

## POTENTIAL_GENERALIZATION_DEBT

Owner/Source：contracts.sources/source_identity新增17文件版本闭包，外部Issuer未建立。Factory：Windows-only、全局inactive-by-default audit、可信Python父进程，非OS隔离。Adapter：domain_adapters中两套固定fixture，真实业务Authority缺失。Verifier：verify_bytes复用Harness语义核，可读性好但独立实现多样性有限。Guard：原child不改，未回显Source/capsule。跨平台：contracts.windows fail-closed，没有POSIX证明。性能和长期维护节省只是推测，未profiling/因果benchmark。原产品R01～R10/MUST/SHOULD目标保留，未因本轮范围减少。

FACTORY_COMPONENT_EXECUTED=YES；TWO_FIXED_SDK_DOMAINS=PASS；BUSINESS_TARGET_REAL_THIS_TASK/REAL_EXPLORER_THIS_TASK/AUTHORITY_READBACK/PGE_FEEDBACK=NOT_RUN；CHILD_INDEPENDENT_ATTESTATION/ISSUER/L2=NOT_ESTABLISHED；SDK_GUARD_MIGRATED/NATIVE_R68_DRIVER_MIGRATED/FULL_COMMON_CORE_MIGRATED=NO；MAIN_MERGED/DEPLOYED=NO。Architect EVIDENCE_ACCEPTED/STAGE_ADVANCED仍PENDING。

## 21条 CREATE_ONLY

- `runtime/runproof_runtime/effectwitness/pge_r73_contracts.py`
- `runtime/runproof_runtime/effectwitness/pge_r73_launch_contract.py`
- `runtime/runproof_runtime/effectwitness/pge_r73_launch_factory.py`
- `runtime/runproof_runtime/effectwitness/pge_r73_budget_view.py`
- `runtime/runproof_runtime/effectwitness/pge_r73_sdk_harness.py`
- `runtime/runproof_runtime/effectwitness/pge_r73_domain_adapters.py`
- `runtime/runproof_runtime/effectwitness/pge_r73_verify.py`
- `runtime/runproof_runtime/effectwitness/pge_r73_compat.py`
- `runtime/tests/test_effectwitness_pge_r73.py`
- `spikes/rpf-73/probe.py`
- `spikes/rpf-73/README.md`
- `spikes/rpf-73/RESULT.md`
- `spikes/rpf-73/preflight-diagnostic.json`
- `spikes/rpf-73/verification-diagnostic.json`
- `spikes/rpf-73/launch-parity-matrix.json`
- `spikes/rpf-73/architecture-decision.json`
- `spikes/rpf-73/capability-assessment.json`
- `spikes/rpf-73/source-identity-map.json`
- `spikes/rpf-73/history-regression.json`
- `spikes/rpf-73/launch-negative-controls.json`
- `spikes/rpf-73/runtime-diagnostic.json`

最终回执SHA、GitHub URL和交付双读由最后聊天补足，私有D盘路径不当作外部可访问证据。
