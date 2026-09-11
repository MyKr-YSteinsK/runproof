# RPF-05 Evidence Control Plane

这是第一个正式 Desktop Web Control Plane，默认消费仓库内真实、脱敏、源码绑定的 `rpf-run-evidence-v2` Run Evidence 与独立 `rpf-failure-case-v1` Failure Case reviewed artifacts。数据通过 `web/src/data/artifacts.ts` 的 adapter 进入 UI；presentation components 不直接依赖 artifact 文件路径的字段细节。

从仓库根目录运行：

```powershell
npm install
npm test
npm run typecheck
npm run build
npm run dev
```

稳定入口为 `/runs`，详情 route 为 `/runs/:runId`；选中的 timeline event 通过 `?event=:eventId` 恢复。Failure Case 入口为 `/failures` 与 `/failures/:failureCaseId`，可往返 source/reproduction Run 与 event deep-link。Web 是 read-only evidence surface，不会从页面发起 live Agent Run、reproduce、promote 或 mutate，也不引入 DB、Queue 或 backend service。
