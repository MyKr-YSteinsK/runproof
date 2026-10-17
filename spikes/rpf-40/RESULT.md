# RPF-40 调查与 Spike 结果

## TASK_RESULT｜RPF-40 / rev-2

- Status: COMPLETE；A-01 至 A-09 已完成，A-10 在本分支聚焦提交、普通 Push 与远端 SHA 读回后完成。
- Repo / Remote / Branch / Base / Final HEAD / Protected preexisting untracked / Task-owned cleanliness: MyKr-YSteinsK/runproof（已现场核实本地 checkout，绝对路径仅保留在本地回执，不进入公共产物）；https://github.com/MyKr-YSteinsK/runproof.git；codex/rpf-40-effectwitness-spike；base bda0cd49e50e3181f604324e94877a24b9885334；本文件不包含自身所在 Commit SHA，最终本地/远端 SHA 在同一对话的回执给出；?? docs/reviews/ 保持原样且未读取其内容；提交后本任务 tracked/staged 工作树清洁。
- Plan Source: RPF-40 rev-2。rev-1 因将所有未跟踪状态都视为 dirty 而 BLOCKED；rev-2 明确允许仅 ?? docs/reviews/ 存在，且本地重新核实跟踪区、暂存区、目标目录和 remote 后创建专用分支。

### CURRENT STATE 与 Bootstrap Contract Gaps

远端 main 基线 bda0cd49e50e3181f604324e94877a24b9885334 中，RPF-00 至 RPF-39 已完成，RPF-40 尚未占号；本次结果仅属于 RPF-40 专用分支，未推进 main。EffectWitness、PGE、订单/退款与三合同均属于新目标意图，不是当前 RunProof 产品能力。

Plan 列出的 V5 Bootstrap 文件没有在当前受审 Git tree 中落地；tracked 文件名检查只找到 RunProof canonical docs/project/PROJECT_BRIEF.md。docs/project/DECISIONS.md 没有 D-COMP-01 / COMP-03 的本地 canonical 条目。后续若 Main 接受本方向，建议只做增量接入：在 docs/history/RPF_EXECUTION_INDEX.md 与 VERIFICATION_HISTORY.md 记录 RPF-40；在 docs/project/CURRENT_STATE.md 更新被接受的当前能力；仅在正式决定后为 docs/project/DECISIONS.md 分配 canonical D-###，保留 D-COMP-* 为 Bootstrap 来源身份；仅在确有长期执行规则时修订 AGENTS.md。不要把 V5 文件整包复制进旧 single source of truth，也不要将竞赛目标改写成既成能力。

### Code / SDK / Tool Investigation

- Agent 合同：runtime/runproof_runtime/agent_contract.py 显式注册 Production Change 与 Incident Remediation 两个合同，dynamic_loading=false；它不是可任意载入第三方 Agent 的插件边界。
- Provider 与 Runner：runtime/runproof_runtime/deepseek_provider.py 是非流式 DeepSeek Chat Completions adapter，校验现有场景工具参数且没有自动 retry；runner.py 默认 MAX_AGENT_STEPS=6、MAX_PROVIDER_CALLS=12、请求超时 45 秒、总运行超时 8 分钟。runtime/runproof_runtime/scenario.py 还含 apply_change 与 reconcile 等产品工具。原 Runner 未用于本次 Live，因为其 12 次调用上限高于本 Plan 的 6 次总预算，且其工具不属于本次只读沙箱。
- Durable boundary：control-plane/src/main/java/com/runproof/controlplane/DurableExecutionController.java 的 POST /api/v1/jobs 要求 execution:submit；Job 提交本身不执行 Agent。AuthService.java 将 execution:submit 赋给 ci-service，将 execution:worker 赋给 durable-worker，agent-runtime 只有 agent:observe。runtime/runproof_runtime/durable_worker.py::_safe_contract() 仅接受 rpf-statistical-trial-execution-v1 与 rpf-evaluation-execution-v1，并严格限制 payload 字段；没有可直接使用的通用 Experiment Job contract。添加新正式 Job 仍需独立 Plan，覆盖合同版本、schema、权限、operation fencing/reconcile 与证据。
- Environment / Verifier：RPF-28 的 MultiServiceEnvironment 提供本地受控 Docker/Toxiproxy、initial-state readback、fault planned/triggered/observed/reconciled 和 cleanup/quarantine；runtime/runproof_runtime/verifier.py::verify_run() 对实际状态、mutation count、readback、UNKNOWN_OUTCOME、blind retry 与 fault 做确定性判定。本次没有启动该环境，也没有运行该业务 Verifier。
- Control Plane / Web：ControlPlaneController 提供 metadata/artifact 读取与独立写权限；web/src/data/controlPlaneApi.ts 的读取 adapter 通过 GET 载入 canonical metadata/artifact，并在 API 或 artifact 不可用时 fail closed。没有修改 Web 或启动服务。
- RPF-39：spikes/rpf-39/RESULT.md 的 GenAI signals 为 synthetic telemetry，未做真实 Provider 工具执行；不能替代本次 live 结果。
- WorkSwarm：在隔离 Python 3.12.13 venv 检查了官方 workswarm 0.2.7 wheel，SHA-256 723e8373d2288d60cad09f1aaf813f65bb2b245769c17808e0090b81ae3fb13e，Apache-2.0，requires-python >=3.11,<3.14，元数据声明 106 项依赖。包源码有应用内部 MCP config 与 Agent harness；官方资料与本次静态检查没有建立稳定、可嵌入 RunProof 的 SDK 调用合同。WorkSwarm integration = NOT_PROVEN。官方发行页已有 0.2.8.beta1，本次采用 PyPI 稳定版做检查，不追 Beta。
- DeepSeek：官方当前模型页确认 deepseek-flash 支持 Tool Calls；官方示例明确要求应用执行模型所请求的函数，并将 assistant tool call 与 role=tool/tool_call_id 结果回传。实际使用的是本 Plan 允许的显式 HTTP fallback，不冒称 WorkSwarm 或 MCP 集成。

接入推荐：首期采用受限 Experiment Orchestrator，外置于正式 Durable Worker；只接收冻结候选与预算，委托受控本地执行器，再由独立 readback/Verifier 判定。此方案不需立即扩张现有 Worker 合同，但进入正式产品前仍须定义 canonical Run/Effect/Experiment 身份、取消与 reconcile 状态机及证据存储。Worker 扩展需要新增合同/parser/schema、Job/Attempt/Operation 生命周期与迁移，当前不是最小切片。外部 Evidence 可以标为 EXTERNAL_EVIDENCE_ONLY，不能证明受控环境的业务效果或签发有效 Witness。

### Execution Evidence

- Source / adapter: probe.py SHA-256 ee04a0d9aeadff3a0608a4adc87709624894a2e0cd288d33c218dbfd5b71bb73；adapter rpf40-deepseek-chat-completions-v1；config SHA-256 8da3bfdefce05cf50bb12f70da2c0645bc960114e119258890cb10db00fd6cf5。
- Run / Provider: run_id rpf40-d30be4c7d3754711957c3aa18aa6559c；DeepSeek API https://api.deepseek.com/chat/completions；requested/returned model deepseek-flash。仅使用进程环境中的 Key，report 仅存 api_key_present=true。
- 第一次 Provider 请求 HTTP 200，local request ID rpf40-e6155a37dee342a9bbed6d51a30f298e，response ID a33e647f-96f8-4ee9-a01c-e9c15180ecb4，finish_reason=tool_calls，usage 386 input + 44 output = 430 tokens。模型发出 tool_call_id call_00_5c2rnuXtjnGgizVViIEC5087，tool=inspect_sandbox_state，脱敏 arguments={scenario_id:rpf40-local-sandbox}；本地 schema/allowlist 校验 PASS。
- 工具注册后在本地真实执行；固定环境 revision rpf40-local-readonly-v1，readback state SHA-256 4293f92fc3f5ec59b9742740833b798af3b47445f1e3a2b93440eb4e20a0d06b，调用前后相同。结果为 health=ready、revision=7、operation_count=0、business_effect=NOT_TESTED；result ref sha256:126da37ca6657b9733af94ffd85dbaa90abb402f97954a4f7f16b991ddee5789。
- 第二次 Provider 请求 HTTP 200，local request ID rpf40-a38038c4542446dea86759258e5f7bc6，response ID 083f567c-db0a-44b4-be2a-30d17180352d，finish_reason=stop，usage 246 input + 10 output = 256 tokens。请求包含 role=tool、同一 tool_call_id 和实际工具结果；第二响应成功，Agent 收到工具结果。模型自由文本未保存，只保留其非空标记与 SHA-256。
- Tool schema SHA-256 194c14500c7794cededc5b06193f0217e513120f14b99ee1a6c835c2010267ac。模型参数校验、dispatcher、local readback 与结果回注是实际链路，不是 mock。
- 业务效果 / Effect Verifier / Witness：NOT_TESTED。此 Tool Calling PASS 不能解释为订单/退款/运维效果 PASS、有效 Run Evidence 或竞赛目标完成。

### Acceptance

| ID | 状态 | 证据 / 边界 |
|---|---|---|
| A-01 | PASS | 根目录、origin、基线 SHA、分支、tracked/staged clean、目标目录空闲及专用分支已核实；仅 ?? docs/reviews/ 作为预先识别的 protected untracked 状态保留，未进入或读取。 |
| A-02 | PASS | 见本节 Code / SDK / Tool Investigation 的 Java、Runtime、Agent contract、Worker、Provider、Environment、Verifier、Web 源码地图。 |
| A-03 | PASS | 官方 WorkSwarm 包名/版本/Python/许可/wheel hash 及安装元数据已检；官方 DeepSeek 当前模型、Chat Completions tool-call envelope、tool result 回注与价格已查；WorkSwarm SDK 集成明确为 NOT_PROVEN。 |
| A-04 | PASS | 两次真实 DeepSeek Provider 请求完成 Provider → tool call → 参数 allowlist → 本地只读函数 → authoritative fixture readback → role=tool 结果回注 → 第二次模型响应。 |
| A-05 | PASS | 本地硬限 2 次（Plan 上限 6）；实际 2 请求、3 steps、686 tokens、0 fault trials、无 retry、2.125 秒。非法 scenario_id 被拒，状态 SHA 未改变；结果未存 Secret/原始模型自由文本。 |
| A-06 | PASS | 推荐受限 Orchestrator；说明 Worker 扩展的合同/schema/状态机成本，并拒绝把 EXTERNAL_EVIDENCE_ONLY 提升为 Managed 业务效果证明。 |
| A-07 | PASS | 只新增 spikes/rpf-40/**；未改旧 Runtime、Java、Web、Workflow、Project State 或 Reviewed Artifact。运行本地 deterministic self-check；旧模块完整测试和 RPF-28 heavyweight proof 未运行，因为本任务没有触碰对应模块且本工具不使用该 Docker 边界。 |
| A-08 | PASS | V5 Bootstrap 当前不在 Git tree；未修改 AGENTS.md、DECISIONS.md 或 CURRENT_STATE.md。给出未来最小历史/状态接入路径，保留 D-COMP-* 与 canonical D-### 区分。 |
| A-09 | PASS | tracked 产物仅 README.md、RESULT.md、probe.py；.local/rpf-40/ 仅保留 state/result 与 quarantine 内由本任务创建的 WorkSwarm wheel、venv、临时目录。没有仓库外父目录或临时目录产物；docs/reviews/ 未动。 |
| A-10 | PASS | 已按 Plan 聚焦提交并普通 Push 到专用分支，远端 refs/heads/codex/rpf-40-effectwitness-spike SHA 与最终本地 HEAD 一致；最终 SHA 与工作树摘要在同一对话的回执给出。main merge=NO，PR=NO，release=NO，deploy=NO。 |

### Budget / Commands / Cleanup

- Hard budget: Provider requests ≤6，Agent/tool steps ≤8，tokens ≤15,000，estimated provider cost ≤¥3.00，live window ≤20 分钟，无盲重试。
- Actual: Provider 请求总数 2（失败 0、重试 0），3 steps，686 tokens，0 fault trials，2.125 秒。按峰值输入 cache-miss 与峰值输出费率估算 USD 0.0002544；按 ¥10/USD 的保守换算，上界 CNY ¥0.002544。官方计费页面提示价格可能调整；此值是依据响应 usage 的估算，不是账单回执。
- Commands: 隔离 Python 3.12.13 venv 的 Scripts/python.exe -X utf8 spikes/rpf-40/probe.py --self-check — exit 0；同一解释器执行 --live — exit 0 / PASS_TOOL_CALL_CHAIN；git diff --quiet 与 git diff --cached --quiet 的启动前检查均 exit 0。额外检查发现 py -3.12 启动器没有解析到该 uv 管理的解释器，故 README 使用通用 python 命令；这不影响实际 3.12.13 调用。没有运行产品全量测试、Maven、Web build、RPF-28 或 Docker。
- Side effects: 仅 DeepSeek 官方端点的 2 次计费 API 请求；本地创建固定 JSON fixture 并只读一次；无业务状态变化、数据库写入、Docker/容器/云资源、Release/Decision 写入。
- Cleanup: 执行环境拒绝对任务生成的 venv 目录进行递归删除。没有发生删除；已将 packages、venv、tmp 移入 .local/rpf-40/quarantine/，并保留 live-result.json 与 sandbox-state.json 作为最小可核验证据。没有在仓库外父目录或其他临时目录生成文件。
- Protected user files: docs/reviews/ 全程仅通过 Git status 的汇总状态识别，未读取目录内部、未修改、未暂存。

### Files / Git / Remaining Risk

- Files changed: spikes/rpf-40/README.md、spikes/rpf-40/RESULT.md、spikes/rpf-40/probe.py。探针、工具 schema、adapter config、sandbox state、工具结果均记录 SHA-256；本文件不包含自身所在 Commit SHA，避免自引用。
- Git: Repo MyKr-YSteinsK/runproof；remote origin https://github.com/MyKr-YSteinsK/runproof.git；branch codex/rpf-40-effectwitness-spike；base bda0cd49e50e3181f604324e94877a24b9885334。专用分支普通 Push 成功；最终 commit/remote SHA 在本对话 TASK_RESULT 回执中核验。没有 PR、main merge、release 或 deploy。
- Known limitations: WorkSwarm 真正 Agent/MCP SDK 执行未证明；Probe 是 stdlib HTTP fallback。沙箱状态为只读合成 fixture；未证明任何业务 Effect、正式 Worker Job、三合同落地、Verifier、Witness、Web Lab、PGE 或两领域验收。最终报告内容须由 Development Architect/Main 独立接受。
- Recommended deviation: 用受限本地 Orchestrator 做下一阶段主路径，不先扩 Durable Worker。建议第一项 Effect 设计为受控订单/退款状态的独立 authority readback；把现有 RPF-28 运维环境保留为第二领域，不从目标中删除。实际实现仍需新的有界 Plan。
- Next Decision: Development Architect 是否接受“本地受限 Orchestrator + 订单/退款 authority readback 作为首个 Effect pilot，同时保留 RPF-28 运维作为第二领域”的 RPF-41 任务输入？本次未创建 RPF-41。
