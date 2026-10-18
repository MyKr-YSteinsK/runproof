# RPF-51 rev-3：就绪探针可靠性修复与真实 HTTP-Witness 补验收

本轮沿用 rev-1、rev-2 的 config-center 受限业务合同，单独修复服务就绪识别，并用新的 task root、端口、身份和 one-shot marker 执行一轮真实验证。rev-1、rev-2 的 `RESULT.md`、Witness、运行目录和 marker 均为历史证据，不重跑、不改写。

## 执行顺序

仅在 `D:\CS\runproof` 的 `codex/rpf-51-rev3-readiness-http-effect` 分支、精确父提交 `68ac08de12048856fe38aa7e8548ad5bb3516a9b` 上执行：

```powershell
py -3.14 -B spikes/rpf-51/probe.py --prepare-diagnostic
py -3.14 -B spikes/rpf-51/probe.py --diagnose
py -3.14 -B spikes/rpf-51/probe.py --prepare-scenario
py -3.14 -B spikes/rpf-51/probe.py --run-scenario
```

诊断与业务 Scenario 使用 `.local/rpf-51-rev3/diagnostic/` 和 `.local/rpf-51-rev3/scenario/` 两套独立状态。诊断只启动一次 Java 17、`local` profile、内存 H2 服务，只请求 `/actuator/health`，业务 POST 数必须为 0。只有 PID、精确 loopback listener、健康 HTTP `200` 且 JSON `status=UP` 同时成立，并确认进程和端口关闭后，才可冻结业务 Scenario。

就绪轮询对每次观察记录进程存活、TCP、listener 所有权/PID 匹配、健康请求状态、耗时和失败分类。TCP 成功但 PID 尚未匹配时也会有界 sleep；任意业务步骤失败都在 `finally` 中结束本次 `Popen` 子进程并核对端口关闭。端口竞争、身份变化、超时或健康响应不明确均停止；不得重启或重复 POST。

正式 Scenario 最多 12 个业务 HTTP 请求，健康 GET 最多 5 次，Provider/LLM 请求、tokens 与费用均为 0。随机 API Key 只通过 Java 子进程环境传入，argv 仅保留 `${CONFIG_CENTER_API_KEY}` 字面占位符。JAR 和源码从 rev-2 已验证副本复制并逐文件核验，不构建、不下载依赖、不触碰 config-center 仓库或真实服务。

Witness 只在真实 HTTP 观察满足既有 Oracle、来源和关闭条件后生成。服务停止后用独立 Python 进程进行正确、缺失和错误锚验证。`issuer_authenticity` 仍为 `NOT_ESTABLISHED`，Authority 仍位于同一个 config-center 服务信任域。

执行事实和各 Gate 以 [`RESULT.md`](RESULT.md) 为准；诊断 readiness 摘要为 `readiness-diagnostic.json`，真实 Witness 仅在正式合同观察完整且成功时出现。

## 本轮收口状态

本轮唯一只读诊断已启动并失败，诊断 one-shot 已消费。Windows 进程树取证确认：探针的 `Popen` PID 29916 是 Oracle `javapath` 启动器，实际监听 `127.0.0.1:2018` 的 JDK 子进程 PID 为 3856。探针因 PID 不一致拒绝向该端口发送健康 GET；A-03 未通过，端口和两个进程均已关闭。修复已改为从启动器报告的 `java.home` 直接选择并校验 JDK 可执行文件，并有单元测试覆盖；该代码修复没有重跑真实 Java 诊断。

按授权停止条件，本轮不准备或启动业务 Scenario；A-04/A-05 为 `NOT_RUN`，scenario one-shot marker 未创建。若要对修复后的真实 PID 归属和 HTTP 健康检查补验收，需由新的 Plan 授权新的诊断身份与一次启动。
