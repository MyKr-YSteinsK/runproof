# AGENTS.md

> RunProof 仓库执行规则；稳定产品合同、决定与当前事实分别由下列 Project State 文件持有。

## 1. Project identity and context

- RunProof (`RPF`)；repository name：`runproof`；主分支：`main`。
- GitHub identity：`MyKr-YSteinsK/runproof`，visibility：`Public`（用户明确确认）；实际 remote/upstream 接入状态见 `docs/project/CURRENT_STATE.md`。
- 唯一 Project State 位置：`docs/project/PROJECT_BRIEF.md`（稳定产品/UX 合同）、`docs/project/DECISIONS.md`（canonical decisions）、`docs/project/CURRENT_STATE.md`（当前阶段、能力、限制与交付事实）。
- 历史验证事实保存在 `docs/history/`；RPF-00 至 RPF-39 的执行入口和生命周期导航见 [`docs/history/RPF_EXECUTION_INDEX.md`](docs/history/RPF_EXECUTION_INDEX.md)。具体参数仍以对应 Spike/模块 README 与脚本为准。
- 完整 Bootstrap 由 Architect 持有；后续 Plan 必须带入相关 MUST、Acceptance、UX invariant。当前实现或摘要遗漏不能自行废除目标需求；事实冲突核对环境/版本，产品取舍按明确决定处理。

## 2. Protected / private / external boundaries

- 保护无关用户文件和改动；不提交 secrets、私密数据、临时输出、构建/覆盖率产物或本地运行目录。
- DeepSeek API Key、未来 Provider credentials、authorization token 不得进入 Git、前端源码、Scenario、默认持久化 Trace 或普通 Evidence export；敏感字段默认 redact/mask。本地 secret 防护见 `.gitignore`。
- v1 Agent 有副作用 Tool 只操作 Controlled Production Simulation Environment，不连接真实生产 destructive credentials。产品的 Simulation 范围不自动授权执行器在任意任务中执行 destructive/live 操作。
- 关键 Release Authority 不由被测 Agent 持有；Agent/runtime 不得绕过 Approval/Quality Policy。`ELIGIBLE` 不是已发布状态，也不是 deploy/release 授权。
- 不因推荐技术栈搭建完整空壳或引入 Queue/容器编排；未知架构边界先按任务开展 Investigation/Spike。
- 本轮及后续任务不得读取、修改、移动、暂存或提交用户-owned `docs/reviews/` 内容；该目录如未跟踪必须保持未跟踪。

## 3. Current command routing

### Fast path — ordinary maintenance and focused product changes

普通 push/PR 的自动验证只有 `.github/workflows/release-gate.yml` 的 canonical Release Gate；它保留 `push(main)`、`pull_request(main)` 和 `workflow_dispatch`，并执行 repository contract checks、fresh PostgreSQL/Control Plane、durable evaluation、canonical Decision read-back、redacted artifact 与 Job Summary。它不执行 release/deploy。

本地 fast path 按实际影响选择以下核心命令；不要把所有历史 Plan 的命令机械拼成 CI：

```powershell
python -m unittest discover -s runtime/tests -p 'test_*.py' -v
python runtime/verify-reviewed-artifacts.py
python ci/verify-public-docs.py
python demo/verify-golden-demo.py --root . --json
mvn -q test package -f control-plane/pom.xml
npm test
npm run typecheck
npm run build
```

Canonical decision/evidence changes additionally use the reviewed RPF-16/RPF-17/RPF-18 verifiers and the local equivalent of `python ci/run_release_gate.py`; hosted evidence 以 `CURRENT_STATE` 与 `docs/history/` 为准。

### Risk-expanded path — manual formal boundaries

RPF-28、RPF-30、RPF-32、RPF-34、RPF-35 跨多个共享层，workflow 保留 fresh-checkout、显式依赖、source identity、artifact/verifier 入口，但采用 `workflow_dispatch` only。需要修改其直接 contract 时，先读对应 README，再运行对应 `probe.py` 与 `verify-evidence.py`；不要把这些 heavyweight proof 作为普通文档或通用 Runtime 改动的自动 fan-out。

```powershell
python spikes/rpf-28/probe.py --run
python spikes/rpf-28/verify-evidence.py .local/rpf-28/rpf28-formal-result.json
python spikes/rpf-30/probe.py --run
python spikes/rpf-30/verify-evidence.py .local/rpf-30/<run>/rpf30-result.json
python spikes/rpf-32/probe.py --run --output-dir .local/rpf-32/<run>
python spikes/rpf-32/verify-evidence.py --result <rpf32-result.json>
python spikes/rpf-34/probe.py --run --output-dir .local/rpf-34/<run>
python spikes/rpf-34/verify-evidence.py <rpf34-result.json>
python spikes/rpf-35/probe.py --run --output-dir .local/rpf-35/<run>
python spikes/rpf-35/verify-evidence.py <rpf35-result.json>
```

### Checkpoint and historical reproduction

- RPF-33 capacity/Large-Trace proof is manual checkpoint only；保留 Small/Medium/Full 入口，不把它当作 Production SLA。
- RPF-27、RPF-29、RPF-31、RPF-36 是保留原路径的 historical/manual workflows；它们可以从 GitHub `workflow_dispatch` 或 README 的本地入口复现。
- RPF-37 audit：`python spikes/rpf-37/audit.py --root . --output .local/rpf-37/audit.json`。它只盘点 tracked tree/workflows/spikes/reference/hash/Git hygiene，不删除任何内容。
- RPF-38 的触发矩阵、权限变化、审计前后对比和剩余候选以 `docs/history/RPF_EXECUTION_INDEX.md`、`docs/history/VERIFICATION_HISTORY.md` 与 `CURRENT_STATE.md` 为准。
- RPF-39 的 GenAI semantic-convention 结论以 `spikes/rpf-39/RESULT.md` 和其 disposable probe/verifier 为准；它不改变 RPF-30 正式 boundary、canonical evidence 或 Release authority。

### Evidence and runtime boundaries

- reviewed artifact 是不可变历史证据；不得静默覆盖、rename、move、format、regenerate、normalize、merge 或 delete。源码改变时必须显式刷新、审查并记录新的 source identity。
- `.local/`、`ci-results/`、构建/覆盖率输出和 provider 临时资源只属于 ignored local/CI runtime；不要提交。
- RPF-01/RPF-02 的 disposable probes 不代表正式 Runtime；RPF-27/RPF-29/RPF-31 的 candidate probes 不代表正式 Environment/OTel/ArtifactStore；RPF-39 的 compatibility probe 不代表正式 GenAI schema mapping。RPF-28/RPF-30/RPF-32/RPF-34/RPF-35 的正式边界仍不自动推导 Production HA、managed cloud、broker、scheduler、GC、真实 destructive remediation 或 release/deploy authorization。
- Runtime live/provider 命令只有在当前任务明确授权 API 调用、费用与副作用时运行；从 `DEEPSEEK_API_KEY` 读取 secret，绝不打印 key、Authorization、private reasoning 或自由模型文本。
- `python -m runtime.runproof_runtime`、正式 worker、Control Plane client 及 Web read model 必须保持 secret/private-protocol redaction、UNKNOWN_OUTCOME reconcile、fail-closed artifact verification 和 Agent/Release authority 分离。
- Python runtime 当前无独立 lint/build 命令；Web `npm run build` 已包含 TypeScript/build 检查。验证应按真实 failure mode 选择，不用重复命令制造“证据数量”。

## 4. Git / delivery / release model

- 默认政策：`push-only`（commit → push）；实际 upstream 与交付结果见 `docs/project/CURRENT_STATE.md`。新增可信 deployment workflow/endpoint 时通过后续 Plan 更新模型及授权。
- 对已授权的实施任务，coherent change 在必要验证后默认 focused commit；实现、必要验证和适用 Project State 更新完成后，默认提交剩余改动，并普通 push 到已存在且身份明确的既定 upstream，不逐次请求确认。
- 审查、解释、诊断类请求本身不授权 commit/push 或其他写操作；当前明确任务限制优先。
- remote 尚未建立时，不猜测 owner/name/visibility。仅在身份、可用认证与创建/连接授权明确后操作；不擅自改变仓库身份或可见性。
- 禁止 force push、擅自 rebase/history rewrite；不得 amend/rewrite 已 push history 掩盖 bootstrap 转换错误。
- 已 commit 不等于已交付；push、CI、deployment 的成功、失败或未执行分别如实报告。部署授权不得从普通 push 授权推导。
- deploy/release/publish 仅在仓库规则或当前明确授权下执行。未来 push 会触发部署时须先核对对应 workflow 与授权。
- 产品版本、CHANGELOG、tag 与 release 验证按真实发布流程定义，不把 bootstrap commit 当产品版本。
- 当前 workflow 默认只请求 `contents: read`；新增 `actions`、`id-token`、云 secret 或部署权限必须有独立授权和后续 Plan 证明。

## 5. Product checks and skill routing

- 关键 Reliability 不变量以 `docs/project/PROJECT_BRIEF.md` 为准，特别是状态有效性、证据身份/覆盖率、UNKNOWN_OUTCOME reconcile、Regression 质量门槛与不可静默改写历史。
- Desktop Web 是 portfolio-critical Primary surface。相关 UI Plan 必须把 canonical UX 合同纳入正式验收，不延期为末期美化。
- 普通工程执行：`frugal-dev-runner`；Web UI/浏览器体验：`ui-real-device-qa`。技能提供通用执行方法，不扩大当前任务权限。
- 正式 Plan/Handoff 和唯一主结果 `TASK_RESULT` 默认中文；保留 Plan ID、`Status: Complete / Partial / Blocked`。Optional USER CHECK 仅为非阻塞建议，不替代正式 Acceptance。

## 6. Stop conditions

缺少必要产品决定、远端身份/访问条件、操作权限，或下一步需突破产品/任务安全边界时，完成可独立进行的本地工作后报告具体缺口；不得猜测授权或凭据。技术未知本身应先在当前任务范围内调查。
