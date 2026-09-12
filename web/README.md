# RPF-07 Evidence / Evaluation / Regression Control Plane

这是第一个正式 Desktop Web Control Plane，默认消费仓库内真实、脱敏、源码绑定的 `rpf-run-evidence-v2` Run Evidence、独立 `rpf-failure-case-v1` Failure Case、`rpf-regression-v1` Regression、focused result、`rpf-evaluation-suite-v1` Suite、`rpf-evaluation-result-v1` Evaluation 与 `rpf-evaluation-comparison-v1` Comparison reviewed artifacts。数据通过 `web/src/data/artifacts.ts` 的 adapter 进入 UI；presentation components 不直接依赖 artifact 文件路径的字段细节。

从仓库根目录运行：

```powershell
npm install
npm test
npm run typecheck
npm run build
npm run dev
```

稳定入口为 `/runs`，详情 route 为 `/runs/:runId`；选中的 timeline event 通过 `?event=:eventId` 恢复。Failure Case 入口为 `/failures` 与 `/failures/:failureCaseId`，可往返 source/reproduction Run、event deep-link 与 promotion Regression。Regression 入口为 `/regressions` 与 `/regressions/:regressionId`，展示 promotion gate、explicit expected behavior、历史 failure、known-bad/fixed Candidate focused reruns 及 Run deep-link。Evaluation 入口为 `/evaluations` 与 `/evaluations/:evaluationId`，展示三成员 matrix、Run outcome 与 item result 分层、quality/coverage、Recovery/Regression、raw-vs-derived usage；Comparison 入口为 `/comparisons` 与 `/comparisons/:comparisonId`，展示 Baseline/Candidate member diff、aggregate delta 与 stable refs。Web 是 read-only evidence surface，不会从页面发起 live Agent Run、evaluate、compare、reproduce、promote 或 mutate，也不引入 DB、Queue 或 backend service。
