# RPF-65｜版本化配置 Target Port 接入

**Status: Partial** — metadata 与 cold SDK 通过；正式 ConfigPort 在 Host 装配时发生参数绑定错误，尚未启动正式 JVM/SDK，也未发送 Provider 或业务 HTTP 请求。没有生成真实 Witness。

## 范围与接口

本 Spike 从 RPF-64 固定基线新增 `rpf65-config-domain-port-v2`：不可变 TaskContext、静态单域 Session、TARGET 专用 Provider Broker、单一 fsync/hash-chain WAL、配置 DomainPort 和离线 Verifier。来源、角色、三合同、预算、反馈、进程生命周期均绑定新任务身份。

配置链路计划为：真实 Pydantic AI/DeepSeek Tool Calls → Java17/H2 回环 HTTP → update v2 已提交后抑制成功 ACK → 显式 UNKNOWN → 停写/一次只读 inspect → 父进程独立 GET current/history/list。Authority 为同服务只读 HTTP。

实际复用的 RPF-64 `ProcessSupervisor.start/received/close` 已管理本轮 cold SDK。旧 Context、selector、Session 和真实来源拒绝规则保持原字节。配置生命周期仍包含显式适配代码；复制债与本次装配缺陷见 [capability-assessment.json](capability-assessment.json)。

## 已执行与失败位置

- 6 项 focused synthetic tests 通过；22 类重锚语义负控均拒绝，CLI 正确/缺/错锚为 `0/2/3`。
- metadata inspector 1 次，固定 SDK RECORD/JDK/JAR/source 检查通过。
- cold SDK 1 次，五轮 fixture completion、四次工具回调、UNKNOWN 后只读回注与 cleanup 通过；Provider/JVM/业务 HTTP 为零。
- 正式入口预约了 `session-1`、`trial-1`。`pge_r65_target_config.py:119` 调用 `Host(ct,business,journal,...)` 漏传 Broker；实际签名为 `(contracts, ledger, business, journal, *, fixture=False, api_key=None)`。发生 `TypeError: missing a required argument: 'journal'`。
- Source Freeze 后未改源码，未重试。两个预约保持未结算，不退款、不清空、不另建 root 续额。真实 Provider、正式 SDK/JVM、HTTP/POST 均为零；业务效果与 Agent 恢复未证明。

## 入口与证据

`probe.py` 提供 `init/metadata/cold/live/verify` 分阶段入口。**本轮 `.local/rpf-65` 和分支已占用，不能重跑这些阶段。** `live` 需要同源 metadata/cold、显式 paid gate、父进程既有凭据；凭据不传给 SDK/JVM。本轮已进入凭据 Gate，但没有发出 Provider 请求。

离线 Verifier 模块为 `runtime.runproof_runtime.effectwitness.pge_r65_verify`，外部原始 SHA 锚为必需参数 `--sha256`。本轮没有真实 `target-witness.json`；已执行的 `0/2/3` 与攻击验证仅针对明确标记的合成证书。

结果入口：[RESULT.md](RESULT.md)、[preflight-diagnostic.json](preflight-diagnostic.json)、[verification-diagnostic.json](verification-diagnostic.json)、[trial-summary.json](trial-summary.json)。本地 WAL 和失败现场保留于 ignored 任务根，不进入 Git。

## 后续最小修复建议

rev-2 应明确允许修正冻结源码，补充真实 Port 的 Host factory 参数绑定测试，并指定新的 Source Identity、运行根与额度；不能沿用本轮已占用根假装首次执行。最小未实施修复为向 Host 显式传入 `broker`，然后重新完成免费 Gate 和唯一真实 Trial。合成 `fake_scene` 替换执行体的测试不能覆盖实际装配边界。

Explorer、订单真实 Target、跨域双真实 Agent、L2 和 Web 的限定见结果文件。没有主线合并、部署、比赛报名或发布。
