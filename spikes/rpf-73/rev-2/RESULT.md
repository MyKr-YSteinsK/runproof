# TASK_RESULT｜RPF-73 / rev-2

Plan ID: RPF-73

Revision: rev-2

Status: Complete

## CURRENT STATE

本轮仅修复新的runner环境与回归取证，不改rev1 Factory/SDK/Guard/旧测试。七项原R72R3测试实际PASS；三次原HTTP测试定向执行PASS，Win10053未复现且根因NOT_PROVEN。当前Runtime恢复标记 RPF73_RUNTIME_REGRESSION_RECOVERED=YES，由本轮真实Full门禁决定。

Base `19c5d28baab0e10b34dbf821ce07cc187bdd9c8f`；分支 `codex/rpf-73-rev2-runner-env-loopback-regression`；Source commit `c03853c4a347f6f926135d4ccd060e6a8098ec0c`；新Source identity `6fc5ec95b69953bb891f4e58d5fc1d62a89177cc099b2f0114b80203d53f9979`。旧Factory identity `e4ea3cc40987e1c90aa683ec324aa33a2d9d97e1e2d713fb84fb75bc039a3db1`保持不变。5项新Source冻结后未改，12项事后报告；最终回执SHA/Git-API双读在最后聊天补足，不回填本文件自身SHA。EVIDENCE_ACCEPTED/STAGE_ADVANCED仍由Architect裁决。

## TARGET INTENT / PLANNING CONTEXT

Owner `rpf-73-rev-2`，ABI `rpf73r2-runtime-runner-replay-v1`。runner保留原35个可信目录身份范围内的PATH项，剔除原host中未展开/不可信项，绝不追加父Python目录。解释器用核实的绝对路径和SHA启动。SYSTEMROOT/WINDIR/PATH、COMSPEC/PATHEXT按G0具体用途读取；HOME/USERPROFILE/TEMP/TMP/TMPDIR指向当前命令scratch，其他Runtime元数据键显式注入。APPDATA/LOCALAPPDATA/PROGRAMDATA/SYSTEMDRIVE未继承，无PYTHONPATH、无sys.path.insert修复、无全局env改动。Runtime16键不扩大原SDK10键。

rev1仍是组件证据PARTIAL_ACCEPTED，原Full665/8ERROR保留；本轮不读旧.local、不重跑旧6个Factory case、不重签Manifest、不以旧96负控计本轮数量。普通Runtime遗留fixture只在当前snapshot中独立计账，非新业务Witness。

## Gate

| Gate | Status | 证据 |
|---|---|---|
| G0 | PASS | Exact Base/remote/main/17 absent paths, ignored owned non-reparse root, pinned SDK/JAR/Python and immutable rev1 Source |
| R2-A01 | PASS | New runner owner/ABI/source raw/LF/Git blobs; rev1 e4ea identity preserved, separate snapshot/root |
| R2-A02 | PASS | 32 actual process negative refusals, no appended PATH, actual sanitized child/full digest matches admission, finite OS variables |
| R2-A03 | PASS | Seven actual unchanged R72R3 tests PASS; targeted env kernel raw bytes match frozen kernel; prefreeze routing-only changes versioned |
| R2-A04 | PASS | Three original loopback targeted tests and two separate contrast situations, call stages/status/port closure; root cause NOT_PROVEN |
| R2-A05 | PASS | 26 new runner + original rev1 30 focused, pins/source audit, no Factory run/case |
| R2-A06 | PASS | 24 original public/native verifiers and R69 CLI0/2/3; old private manifests unavailable/not read |
| R2-A07 | PASS | One standard full discover exit0, actual final summary, zero errors/failures, exact ID/2 Docker class skip accounting and byte-identical snapshot |
| R2-A08 | PASS | Seven rev1 PATH fixture errors recover in runner only; original HTTP case no A07 ERROR; 10053 NOT_REPRODUCED, not FIXED |
| R2-A09 | PASS | Evidence layers separated, current scoped processes/ports cleaned, old user/WAL/source preserved; no real model/business/Issuer |
| R2-A10 | NOT_RUN | Artifact generation state: Source pushed and dual-read; final receipt push and two Git/API HEAD/blob/diff readbacks are supplied in final chat, not self-amended |

A10是文件生成时状态，最终交付由最后聊天补全。

## 七项环境恢复与实际进程

`targeted-01`以未修改旧源/测试在新快照执行7个指定方法，exit0、真实Ran7/OK、29.881s。每个ID见命令/日志与environment-contract。该命令在freeze前完成，Source版本 `8945581d886bf192cb8130aaf4cb55f8a13476fb1ab5e931bc2c0adceab562a6`；其environment_contract.py原字节与最终冻结kernel相同=True，后续仅增加受控命令路由/私有诊断校验范围，未改变PATH修复语义。Full则以最终冻结Source重验全部旧方法。

实际子进程观察与admission env SHA匹配，Full PID=23004的环境由新测试在该真实进程内核对，非仅打印预期config。未新增旧TRUSTED_PATH_SHA256条目；rev1不受信Python附加目录不再出现。公开仅摘要/键名，不包含完整PATH/HOME/SID/token。

冻结前环境观察命令曾被新收据校验误要求unittest summary；真实观察child输出PASS，但父收据校验失败。原started/log/actual-env与快照保留，未启动定向七项；冻结前修正为仅unittest模式需OK总结。两版Source清楚分列，没有覆盖旧失败或消耗Factory额度。

本轮32项实际CLI/进程拒绝覆盖未知Python目录、relative/UNC/junction/%/..及引号命令、未知binary/hash、错owner/ABI、Key名注入、错env hash/SDK reference、过滤Full、复制测试改动、LF/raw错误、重复claim、stdout篡改、缺summary及失败伪装成功、wrong cwd。原CLI exit3的原始receipt状态FAIL指进程非零退出；负控row PASS是预期语义拒绝，不把真实unittest失败改成成功。没有TEST_INVALID计数。


七项具体ID（各阶段均原测试执行，无新helper替代）：

- `runtime.tests.test_effectwitness_pge_r72r3.BudgetTests.test_env_reanchored_relative_untrusted_and_key_rejected`
- `runtime.tests.test_effectwitness_pge_r72r3.BudgetTests.test_frozen_env_snapshot_independent_of_input_mutation`
- `runtime.tests.test_effectwitness_pge_r72r3.BudgetTests.test_historical_env_A_accepts_when_host_B_and_native_helper_disabled`
- `runtime.tests.test_effectwitness_pge_r72r3.BudgetTests.test_launch_command_owner_and_cross_domain_reanchor_rejected`
- `runtime.tests.test_effectwitness_pge_r72r3.BudgetTests.test_launch_missing_mapping_and_noncanonical_reject`
- `runtime.tests.test_effectwitness_pge_r72r3.BudgetTests.test_live_actual_env_mismatch_rejects_before_spawn`
- `runtime.tests.test_effectwitness_pge_r72r3.BudgetTests.test_windows_native_serialized_argv_and_sanitized_env`

源码定位：`spikes/rpf-73/rev-2/environment_contract.py:55` PATH过滤、`:63`冻结合同、`:93`实际环境观察；`runner.py:53`启动。定向与Full的PATH值SHA均为 `c283c0b7b93e9eb68baa0de6d1eca61e3387331f6a4e54513a9f25a0e5375c2b`；旧失败PATH只引用rev1公开归因，旧私有日志不读取。

## Win10053 有界鉴别

原测试位于`runtime/tests/test_effectwitness_target_agent.py:234`，旧认证拒绝位于`runtime/runproof_runtime/effectwitness/target_driver.py:321`，新只读诊断入口为`loopback_probe.py:8`和`:32`。三次原测试各独立快照/fixture根、同一严格环境，原代码不改，实际均Ran1/OK；记录request/getresponse/read/close、旧Handler do_POST、send_response/end_headers/finish、状态码、端口及异常类型。没有socket/http.client monkeypatch、吞异常或无证据sleep。trace只读取阶段元数据，观察时序效应仍是限制。

两类独立最小对照为“直接400后关闭”与“读完body再400”，各一次；本轮两者均未出现异常，port/thread清理均完成。对照不是旧Host。结论是 WIN10053_NOT_REPRODUCED_IN_THIS_REVISION；历史10053具体节点和关闭因果仍NOT_PROVEN，不称FIXED，不以三次成功证明以后不再发生。Full中的该原测试结果另行纳入A07/A08。

## focused / history / Full

新26项加原rev1 30项focused，实际56项、exit0、0.810s；没有Factory调用。24个原公开入口和R69 CLI0/2/3均按原Verifier/anchor通过，旧R73/R72 Source/报告原字节保持；私有证书UNAVAILABLE_NOT_READ。

Full只有一次，标准命令为`$PINNED_ABSOLUTE_PYTHON -X utf8 -B -m unittest discover -s runtime/tests -p test_*.py -v`，在单一新source-identical snapshot中执行。原始最终总结：

```text
Ran 691 tests in 3515.980s
OK (skipped=2)
```

exit=0；errors=0、failures=0；wall 3518.005s。discovery=696、实际testsRun=691，原两个Docker class-level skip覆盖5方法不计入testsRun；实际终值ID+5方法精确multiset相等=True，无额外skip或遗漏。诊断把测试名与ok拆行时按原行跨度关联，不用进度行造PASS。实际snapshot 927个文件字节与copy记录/当前源一致；Source未漂移。OK和FAILED均能记录final_summary_present，不再混淆失败汇总与缺汇总。

所有有界执行argv/cwd/env摘要/PID/parentPID/start/elapsed/exit/timeout/python/log原SHA/source前后见verification-diagnostic。初始只读G0部分PID细节未捕获明确UNAVAILABLE；不伪造。每个任务root/marker/log保留，不读取或复制旧.local；docs/reviews仅顶层status自然可见并保持untracked。只复制标准suite所需公开路径和精确已知合同文件，未递归复制docs/project/history/reviews。非循环重试、无test过滤/替换/Source热修。

## 凭据 / 进程 / 能力边界

宿主Provider/业务Key值和存在性查询0；本轮Factory child0，外部Provider/真实模型token/费用均0。Runtime旧SDK净化子进程的absence getter保留，未动态instrument全部getter；ALL_KEY_LOOKUPS_ZERO=FALSE/NOT_PROVEN。原SDK/Guard/依赖RECORD及JAR仅只读核验，不升级。三个原HTTP和两个对照端口均晚次closed、对照thread gone；只清理自己明确拥有的服务，不探测/终止陌生PID，无提权/ACL/power policy改变。

本轮最多建立Runtime兼容恢复；Factory组件真实执行仅引用rev1历史，BUSINESS_TARGET_REAL_THIS_TASK/REAL_EXPLORER_AUTONOMY=NOT_RUN；FULL_COMMON_CORE_MIGRATED/SDK_GUARD_MIGRATED/NATIVE_R68_DRIVER_MIGRATED=NO；child独立attestation/Issuer/L2未建立。无PR/merge/tag/release/deploy/CI dispatch/比赛提交或新Plan。

## VERIFIED_FINDINGS

- R2-F01 / CURRENT_STATE：environment_contract.filtered_path/SuiteEnvironmentContract 与 runner.run，支持为7项原测试+32进程负控+Full实际环境摘要。七项恢复是RUNNER_ONLY，旧35目录hash和ABI未改；源码raw/LF/Git blob见SourceMap。反例：未知Python目录仍拒绝，不能据此允许任意工具。
- R2-F02 / CURRENT_STATE：loopback_probe.original/control、原target_driver.Handler.do_POST和FakeProcess.communicate。三定向+两对照+Full均单列；10053不因未复现而变为已修复。原Host在认证拒绝前未读body是静态事实，但关闭因果未证；观察器可改变时序。
- R2-F03 / CURRENT_STATE：runner.run、environment_contract.parse_summary/verify_receipt，真实标准汇总/exit/ID/Docker映射和snapshot字节核对；原rev1失败不覆盖。局限：这不是新Factory或真实业务执行。
- R2-F04 / PLANNING_CONTEXT：冻结pge_r73_launch_factory及独立runner可维护边界，现有组件证据支持显式启动接缝可行，但不能覆盖Factory→DomainPort/Authority，且无性能因果实验。

## CODEX_ENGINEERING_JUDGMENT

PATH错配修复置信度HIGH：绝对解释器不依赖其目录进入PATH，新进程只继承旧信任集合，旧7真实测试与Full可区分修复有效性；actual env不是期望值自称。10053根因置信度LOW/NOT_PROVEN：当前样本无异常不证明历史条件，两个独立对照也不能替旧Host作因果证明。最便宜下一步鉴别是出现复现时，另授权一个局部原fixture的客户端/服务端body/close阶段追踪，再决定是否改最窄旧路径。组件PASS不足以提供真实业务权限或独立Reader证据。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

| 路径 | 成本 | 安全/证据 | 范围 |
|---|---|---|---|
| A仅新Runner修复（当前） | 5新源和受控env收据 | 不加旧hash，不碰凭据；7项+Full证据 | Runtime兼容 |
| B旧HTTP时序隔离 | 3原测试+2对照；trace有观察效应 | 未改旧Host；阶段与未复现，不是修复 | 旧源码变更需新白名单 |
| C未来Factory接真实Port | 真实业务/费用/故障和独立Reader成本 | 需受控权限与UNKNOWN/Authority验证 | 当前不授权 |

## NEXT_DECISION_RECOMMENDATION

若A07真PASS，建议Architect先核实Runtime恢复，再考虑RPF74真实业务受控Factory接缝；不是自动推进。若10053持续复现，下一授权最窄候选是runtime/tests/test_effectwitness_target_agent.py及/或runtime/runproof_runtime/effectwitness/target_driver.py，先只读定位close/body-drain条件，不擅改旧文件。本轮未重启旧Factory case，不把Suite PASS当业务Core迁移。

## POTENTIAL_GENERALIZATION_DEBT

已证：Launcher Windows-only、Parent3.14/SDK3.12 pins；Source/Owner版本闭包重复；Runtime/SDK净化键集合层级不同；旧Factory全局inactive audit仍存；组件与业务Port/Authority隔离；无child独立attestation。推测：HTTP未读body/关闭次序可能影响10053，尚未证明；显式Factory性能与长期维护收益未测。原产品R01～R10/MUST/SHOULD目标不因本轮缩减。

## 精确17项 CREATE_ONLY

- `spikes/rpf-73/rev-2/environment_contract.py`
- `spikes/rpf-73/rev-2/runner.py`
- `spikes/rpf-73/rev-2/loopback_probe.py`
- `spikes/rpf-73/rev-2/probe.py`
- `runtime/tests/test_effectwitness_pge_r73r2.py`
- `spikes/rpf-73/rev-2/README.md`
- `spikes/rpf-73/rev-2/RESULT.md`
- `spikes/rpf-73/rev-2/preflight-diagnostic.json`
- `spikes/rpf-73/rev-2/verification-diagnostic.json`
- `spikes/rpf-73/rev-2/runtime-diagnostic.json`
- `spikes/rpf-73/rev-2/environment-contract.json`
- `spikes/rpf-73/rev-2/loopback-forensic.json`
- `spikes/rpf-73/rev-2/history-regression.json`
- `spikes/rpf-73/rev-2/source-identity-map.json`
- `spikes/rpf-73/rev-2/architecture-decision.json`
- `spikes/rpf-73/rev-2/capability-assessment.json`
- `spikes/rpf-73/rev-2/negative-controls.json`

最终receipt SHA与可访问GitHub URL由最后聊天双读补全；本文件不amend自身SHA。Codex自报TASK_COMPLETE与Architect EVIDENCE_ACCEPTED/STAGE_ADVANCED分离。
