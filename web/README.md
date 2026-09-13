# RPF-08 Evidence / Evaluation / Release Decision Control Plane

这是第一个正式 Desktop Web Control Plane，默认通过 `web/src/data/controlPlaneApi.ts` 从 RPF-11/RPF-14 API 读取 canonical metadata，再从 verified immutable artifact endpoint 解析真实、脱敏、源码绑定的 `rpf-run-evidence-v2` Run Evidence、独立 `rpf-failure-case-v1` Failure Case、`rpf-regression-v1` Regression、focused result、`rpf-evaluation-suite-v1` Suite、`rpf-evaluation-result-v1` Evaluation、`rpf-evaluation-comparison-v1` Comparison、`rpf-quality-policy-v1` Quality Policy、`rpf-quality-gate-evaluation-v1` Gate Evaluation 与 `rpf-release-decision-v1` Release Decision。RPF-14 的 `web/src/data/executions.ts` 只读消费 `/api/v1/jobs`、`/execution-metrics` 的 Execution Job/Attempt/Operation/Event/Evidence DTO。DTO 到 view-model 的边界仍由 `web/src/data/artifacts.ts` 维护；presentation components 不直接依赖数据库字段或本地 artifact 路径。

从仓库根目录运行：

```powershell
npm install
npm test
npm run typecheck
npm run build
npm run dev
```

开发服务器默认把 `/api` 代理到 `http://127.0.0.1:8081`，并从 Vite 进程环境注入 `RPF_CONTROL_PLANE_READ_TOKEN`（或 `RPF_AUTH_READ_TOKEN`）到代理请求；token 不进入前端 bundle。可用 `RPF_CONTROL_PLANE_PROXY_TARGET` 覆盖 API 地址。正式浏览器路径在 API 不可用、artifact 缺失或 snapshot 不完整时显示明确不可用状态，不回退到静态 fixture；fixture 仅能通过显式 `VITE_CONTROL_PLANE_DATA_SOURCE=fixture` 启用测试模式。

稳定入口为 `/runs`，详情 route 为 `/runs/:runId`；选中的 timeline event 通过 `?event=:eventId` 恢复。Failure Case 入口为 `/failures` 与 `/failures/:failureCaseId`，可往返 source/reproduction Run、event deep-link 与 promotion Regression。Regression 入口为 `/regressions` 与 `/regressions/:regressionId`，展示 promotion gate、explicit expected behavior、历史 failure、known-bad/fixed Candidate focused reruns 及 Run deep-link。Evaluation 入口为 `/evaluations` 与 `/evaluations/:evaluationId`，展示三成员 matrix、Run outcome 与 item result 分层、quality/coverage、Recovery/Regression、raw-vs-derived usage；Comparison 入口为 `/comparisons` 与 `/comparisons/:comparisonId`，展示 Baseline/Candidate member diff、aggregate delta 与 stable refs。Release Decision 入口为 `/release-decisions` 与 `/release-decisions/:decisionId`，展示 active Policy identity、Hard/Soft/Review Gate matrix、blocking/review/warning evidence、coverage/Regression/Recovery signals、stable refs 与 immutable history；页面明确显示 `No release executed / No deployment authorization`，不提供 Deploy 操作。Execution 入口为 `/executions` 与 `/executions/:jobId`，展示 state/outcome 分层、current attempt/lease、append-only attempt/event、operation/reconcile、immutable evidence refs 与 raw JSON；`RECONCILE_REQUIRED` 明确禁止 blind retry。Web 是 read-only evidence surface，不会从页面发起 live Agent Run、evaluate、compare、reproduce、promote、rerun、claim、cancel、release 或 mutate，也不引入 DB、Queue 或 backend service。

RPF-09 的 `web/src/data/controlPlaneReadModel.ts` 仍保留为 API migration compatibility probe；RPF-11 的 `controlPlaneApi.ts` 将 `canonical_metadata` + verified `artifact_resolution` DTO 和 artifact payload 组成完整 snapshot，再交给既有 view-model adapter。API/artifact unavailable 不会被 static fallback 掩盖；页面仍只读，不发起 live Run、evaluate、compare、promote、rerun、release 或 mutate。
