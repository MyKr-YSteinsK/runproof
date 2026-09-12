# AGENTS.md

> RunProof 仓库执行规则；稳定产品合同、决定与当前事实分别由下列 Project State 文件持有。

## 1. Project identity and context

- RunProof (`RPF`)；repository name：`runproof`；主分支：`main`。
- GitHub identity：`MyKr-YSteinsK/runproof`，visibility：`Public`（用户明确确认）；实际 remote/upstream 接入状态见 CURRENT_STATE。
- 唯一 Project State 位置：`docs/project/PROJECT_BRIEF.md`（稳定产品/UX 合同）、`DECISIONS.md`（canonical D-001～D-012 及后续决定）、`CURRENT_STATE.md`（当前阶段、能力、限制与交付事实）。
- 完整 Bootstrap 由 Architect 持有；后续 Plan 必须带入相关 MUST、Acceptance、UX invariant。当前实现或摘要遗漏不能自行废除目标需求；事实冲突核对环境/版本，产品取舍按明确决定处理。

## 2. Protected / private / external boundaries

- 保护无关用户文件和改动；不提交 secrets、私密数据、临时输出、构建/覆盖率产物或本地运行目录。
- DeepSeek API Key、未来 Provider credentials、authorization token 不得进入 Git、前端源码、Scenario、默认持久化 Trace 或普通 Evidence export；敏感字段默认 redact/mask。本地 secret 防护见 `.gitignore`。
- v1 Agent 有副作用 Tool 只操作 Controlled Production Simulation Environment，不连接真实生产 destructive credentials。产品的 Simulation 范围不自动授权执行器在任意任务中执行 destructive/live 操作。
- 关键 Release Authority 不由被测 Agent 持有；Agent/runtime 不得绕过 Approval/Quality Policy。`ELIGIBLE` 不是已发布状态，也不是 deploy/release 授权。
- 不因推荐技术栈搭建完整空壳或引入 Queue/容器编排；未知架构边界先按任务开展 Investigation/Spike。

## 3. Repository command semantics

- RPF-01 disposable probe 使用 Node.js 24 内置 API，无第三方依赖；不代表正式 Runtime 的语言决定。
- 本地合同测试：`node --test spikes/rpf-01/probe.test.mjs`；固定证据离线校验：`node spikes/rpf-01/verify-evidence.mjs`。两者都不调用 Provider，前者检查拒绝/故障路径，后者核对实际样本与源码身份。
- RPF-02 host reference：`node --test spikes/rpf-02/probe.test.mjs`、`node spikes/rpf-02/verify-evidence.mjs`、`node spikes/rpf-02/probe.mjs --run`；真实 Docker provider：`node --test spikes/rpf-02/docker-probe.test.mjs`、`node spikes/rpf-02/docker-probe.mjs --run`、`node spikes/rpf-02/verify-docker-evidence.mjs`。Docker probe 只使用现有 daemon/image，创建带 `rpf02` 前缀的临时 container/volume 并验证 cleanup；Docker 证据证明 Prototype-level contract，不等于 production-grade isolation/HA。
- RPF-03 product runtime deterministic tests：`python -m unittest discover -s runtime/tests -p 'test_*.py' -v`；reviewed artifact 离线核验：`python runtime/verify-reviewed-artifacts.py`；live normal：`python -m runtime.runproof_runtime --fault none`；live response-lost：`python -m runtime.runproof_runtime --fault response-lost`。live 命令从 `DEEPSEEK_API_KEY` 读取 secret、使用 Docker Fresh-per-run，并将每次独立 artifact 写入忽略的 `.local/rpf-03/`；不保存 messages、Authorization、private reasoning 或自由模型文本。
- 真实实验：`node spikes/rpf-01/probe.mjs --live`，仅在当前任务授权 API 调用与费用时运行，从进程环境读取 `DEEPSEEK_API_KEY`，绝不打印 key 或私有 continuation。
- 临时输出仅在忽略的 `.local/rpf-01/`；`spikes/rpf-01/reviewed-evidence.json` 是经过脱敏审查的验收固定样本，允许提交，不能自动以新实验覆盖。修改 probe 后需区分旧证据与新源码身份。
- RPF-02 临时输出仅在忽略的 `.local/rpf-02/`；`spikes/rpf-02/reviewed-evidence.json` 是历史 host-reference 固定样本，`spikes/rpf-02/reviewed-docker-evidence.json` 是真实 Docker provider 脱敏固定样本，允许提交，不能自动以新实验覆盖。修改任一 probe 后需重新生成并审查对应样本的 `source_sha256`；Docker 是当前证据 provider，不是永久产品身份。
- RPF-03 `.local/rpf-03/` 只保存本地 Run artifacts，不提交；runtime source identity 由正式 package 文件 hash 记录。live artifacts 必须经过 secret/private-protocol redaction，历史 Run 不得静默覆盖。
- RPF-03 `runtime/reviewed-*.json` 是经过审查的固定 live evidence 样本，允许提交；`runtime/verify-reviewed-artifacts.py` 校验 artifact schema、PASS、Docker cleanup、response-lost reconcile、secret/private-protocol 边界与 runtime source hash。修改 `runtime/runproof_runtime/` 后必须重新生成并审查样本，不能让旧样本冒充新源码证据。
- RPF-04 Web product commands：`npm test`、`npm run typecheck`、`npm run build`；Web 只从 `runtime/reviewed-*-run-v2.json` 读取 reviewed corpus，不发起 live Run，不保存 secret、Authorization 或 private reasoning。RPF-04 `.local/rpf-04/` 只保存重新生成 v2 artifacts 的本地副本，不提交；固定 v1/v2 样本身份不得静默覆盖。
- RPF-05/RPF-06 runtime：同一 `python -m unittest discover -s runtime/tests -p 'test_*.py' -v`、`python runtime/verify-reviewed-artifacts.py` 合同继续适用；RPF-06 的 `--check-promotion`、`--promote-failure-case`、`--focused-regression`、`--verify-regression` 分别覆盖 gate、显式 promotion、focused rerun 与 Regression artifact 校验。RPF-06 使用 Docker Fresh-per-run，临时输出仅在忽略的 `.local/rpf-06/`，reviewed Stability/Focused Runs、Regression、Gate、Result、Collection 与 promoted Failure Case 不得静默覆盖历史 RPF-04/RPF-05 样本。
- RPF-06 Web 继续使用 `npm test`、`npm run typecheck`、`npm run build`；`/regressions` 与 `/regressions/:regressionId` 只读消费 reviewed Regression corpus，并通过 stable refs 链接 Failure Case、source/reproduction/focused Runs 与 events，不发起 live Run、promote、rerun 或 mutate。
- RPF-07 runtime：继续使用上述 runtime tests/verifier；`--build-suite`、`--validate-suite`、`--evaluate-suite`、`--compare-baseline-candidate`、`--verify-evaluation`、`--verify-comparison` 覆盖 Suite、独立 Evaluation 与 Comparison contract。RPF-07 仅使用 deterministic profiles + Docker Fresh-per-member，临时输出仅在忽略的 `.local/rpf-07/`；reviewed Suite、6 条 member Runs、2 份 Evaluation、2 份 Regression result 与 Comparison 绑定当前 RPF-07 source hash，不得静默覆盖 RPF-01～RPF-06 历史样本；不调用 Provider。
- RPF-08 runtime：继续使用上述 runtime tests/verifier；`--validate-policy`、`--evaluate-quality-gate`、`--create-release-decision`、`--verify-quality-gate`、`--verify-release-decision` 覆盖 Quality Policy、Gate Evaluation 与 Release Decision contract。RPF-08 仅读取 RPF-07 deterministic reviewed corpus，不创建新的 Docker resource 或调用 Provider；临时输出仅在忽略的 `.local/rpf-08/`，reviewed Policy、2 份 Gate 与 2 份 Decision 绑定当前 RPF-08 source hash，不得静默覆盖 RPF-01～RPF-07 历史样本；`ELIGIBLE` 仍是 decision-only，不提供 deploy/release command。
- RPF-07 Web 继续使用 `npm test`、`npm run typecheck`、`npm run build`；`/evaluations`、`/evaluations/:evaluationId`、`/comparisons`、`/comparisons/:comparisonId` 只读消费 reviewed Suite/Evaluation/Comparison corpus，通过 stable refs 链接 Run/Regression；页面不发起 live Run、evaluate、compare、promote、rerun 或 mutate，不输出 Release Decision。
- RPF-08 Web 继续使用 `npm test`、`npm run typecheck`、`npm run build`；`/release-decisions`、`/release-decisions/:decisionId` 只读消费 reviewed Quality Policy/Gate/Decision corpus，通过 stable refs 链接 Evaluation/Comparison/Regression/Run；页面不发起 live Run、evaluate、compare、promote、rerun、release 或 mutate，不提供 Deploy now，也不把 `ELIGIBLE` 显示为 Released。
- Python runtime 当前无独立 lint/build 命令；文档/Project State 仍按语义/链接、Git diff/history/status 和 secret/ignore 边界验证。
- 真实产品命令引入后，按脚本实际语义更新本节，注明 build 已包含的检查以避免重复；不创建空洞 CI。
- 当前 runtime/CI/deployment/version 状态仅见 CURRENT_STATE。

## 4. Git / delivery / release model

- 默认政策：`push-only`（commit → push）；实际 upstream 与交付结果见 CURRENT_STATE。新增可信 deployment workflow/endpoint 时通过后续 Plan 更新模型及授权。
- 对已授权的实施任务，coherent change 在必要验证后默认 focused commit；实现、必要验证和适用 Project State 更新完成后，默认提交剩余改动，并普通 push 到已存在且身份明确的既定 upstream，不逐次请求确认。
- 审查、解释、诊断类请求本身不授权 commit/push 或其他写操作；当前明确任务限制优先。
- remote 尚未建立时，不猜测 owner/name/visibility。仅在身份、可用认证与创建/连接授权明确后操作；不擅自改变仓库身份或可见性。
- 禁止 force push、擅自 rebase/history rewrite；不得 amend/rewrite `efb0101` 掩盖 bootstrap 转换错误。
- 已 commit 不等于已交付；push、CI、deployment 的成功、失败或未执行分别如实报告。部署授权不得从普通 push 授权推导。
- deploy/release/publish 仅在仓库规则或当前明确授权下执行；RPF-00 不授权这些操作。未来 push 会触发部署时须先核对对应 workflow 与授权。
- 产品版本、CHANGELOG、tag 与 release 验证按真实发布流程定义，不把 bootstrap commit 当产品版本。

## 5. Product checks and skill routing

- 关键 Reliability 不变量以 PROJECT_BRIEF 为准，特别是状态有效性、证据身份/覆盖率、UNKNOWN_OUTCOME reconcile、Regression 质量门槛与不可静默改写历史。
- Desktop Web 是 portfolio-critical Primary surface。相关 UI Plan 必须把 canonical UX 合同纳入正式验收，不延期为末期美化。
- 普通工程执行：`frugal-dev-runner`；Web UI/浏览器体验：`ui-real-device-qa`。技能提供通用执行方法，不扩大当前任务权限。
- 正式 Plan/Handoff 和唯一主结果 `TASK_RESULT` 默认中文；保留 Plan ID、`Status: Complete / Partial / Blocked`。Optional USER CHECK 仅为非阻塞建议，不替代正式 Acceptance。

## 6. Stop conditions

缺少必要产品决定、远端身份/访问条件、操作权限，或下一步需突破产品/任务安全边界时，完成可独立进行的本地工作后报告具体缺口；不得猜测授权或凭据。技术未知本身应先在当前任务范围内调查。
