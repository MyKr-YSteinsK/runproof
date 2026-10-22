# RPF-65/rev-2｜真实 ConfigPort 工厂修复与独立验证

本修订从 `ddb3490543504377a2d2603ee6b088910399a723` 出发，使用独立分支 `codex/rpf-65-rev2-real-config-target-factory-repair`、独立运行根 `.local/rpf-65-rev-2/` 和全新 Source Map。rev-1 的公开诊断保持原字节；本修订未读取其本地 WAL。

## 修复与验证边界

真实生产路径现在为 `Session.execute → ConfigPort.execute → assemble_host → Host`。工厂创建同一 Journal、HTTP client、Broker 和 Business，显式调用 `Host(ct, broker, business, journal, fixture=False, api_key=...)`，并核对对象同一性。测试通过签名绑定、漏 Broker mutation、未经替换的 execute 实际到达工厂及装配异常清理验证该路径。

完整非模型集成测试保留 Session、Port、工厂、Host、Broker、Business 和 Oracle 实现，仅模拟进程、SDK 和 HTTP 边界。合成测试中的占位字符串不是有效凭据，也不读取 Provider Key。原 `fake_scene` 继续仅用于合成 Verifier 测试。

邻近修复包括：SDK 异常后的 GET-only 对账、嵌套 finally 保证收据/读回失败仍关闭 owned children、结构化 scene/cleanup 取证。固定 SDK 的 `SDK_ERROR` 报告不含 PID，Verifier 对真实 guarded failure 使用 ready/Popen 绑定并严格验证错误报告形状；成功报告仍要求 ready/report/Popen 和 usage 全部匹配。

ABI 保留 `rpf65-config-domain-port-v2`，序列化协议形状未改；新 base/branch/workspace/probe/source hash 提供修订身份。SDK、Java、三工具、业务 Effect、唯一 post-commit ACK suppression fault、预算与安全边界不变。

## 分阶段入口

入口为本目录 `probe.py` 的 `init / metadata / cold / live / verify`。阶段产物采用独占创建，不允许清空根、重命名 Run 或重置额度来重试。`live` 必须在新 Source Freeze、全套免费 Gate、固定 metadata 与唯一 cold 通过后，由绑定新 Source SHA 的 paid gate 准入。父进程读取既有 Provider Key，SDK/JVM 不持有该 Key。

离线验证模块：`runtime.runproof_runtime.effectwitness.pge_r65_verify`；原始证书 SHA 参数 `--sha256` 为必需外部锚。正确/缺失/错误锚分别退出0/2/3；合成与真实证书的来源级别严格区分。

## 结果入口

- [RESULT.md](RESULT.md)：逐 Gate 回传、执行事实与 Git 交付。
- [preflight-diagnostic.json](preflight-diagnostic.json)：G0、Source Freeze、固定环境、cold。
- [verification-diagnostic.json](verification-diagnostic.json)：工厂/单测、22类语义负控、16历史锚、Runtime、Reviewed/Public。
- [trial-summary.json](trial-summary.json)：唯一 Trial、WAL、Provider/业务用量、fault、Authority 与 cleanup。
- [capability-assessment.json](capability-assessment.json)：实际复用、工厂接口和剩余复制债。

真实 `target-witness.json` 只在完整独立验证成立时创建；运行状态和外部锚以本修订结果文件为准。没有真实 Explorer、订单真实 Target、双域真实 Agent、Web、L2 或生产发布的授权。
