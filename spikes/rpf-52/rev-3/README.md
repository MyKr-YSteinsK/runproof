# RPF-52 rev-3｜跨域 SDK 错误定位与三工具预检后真实 HTTP 补验收

本轮用固定版本的真实 Pydantic AI SDK 先完成零业务副作用的三工具 Fixture 预检，再运行一次新的本地 Java/H2 config-center 场景。预检首轮定位到 no-argument tool 的 JSON Schema 兼容问题；受限修复后第二轮通过，随后正式 HTTP 场景、离线 Evidence 与回归均完成。

## 边界

- 目标是验证 `Pydantic AI 2.57.0` + scripted Fixture + 本地 config-center HTTP 的工具闭环。
- Fixture completion 不代表真实 Provider 或模型自主决策；本轮不验证 WorkSwarm、生产环境真实性、独立数据库权威或独立复现。
- 已消费本轮唯一正式 Scenario marker；**禁止重跑** `probe.py --run-scenario`。诊断额度也已用完。
- rev-1/rev-2 的 marker、运行目录、RESULT 和证据均保持历史原样。

## 产物

- [RESULT.md](RESULT.md)：本轮唯一主 TASK_RESULT、必要 Gate 和证据边界。
- [sdk-diagnostic.json](sdk-diagnostic.json)：两次 fixture-only SDK Attempt 的脱敏摘要；不启动 Java、不执行业务 HTTP。
- [config-target-fixture-evidence.json](config-target-fixture-evidence.json)：唯一一次真实本地 HTTP Scenario 的 Evidence。
- `diagnose.py`：受限的两次诊断编排入口。

离线 verifier 示例（SHA 必须通过独立可信渠道固定；从待验文件本身计算 SHA 不构成信任锚）：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.config_target_verify `
  spikes/rpf-52/rev-3/config-target-fixture-evidence.json `
  --expected-sha256 2bbc002e5a83dabc4aa9b9ddfea733532ef8b29f789181a19debb7ed9437eb27
```

要复核本轮执行事实及信任限制，请以 `RESULT.md` 和 Evidence 中记录的来源身份为准。该命令只做离线验证，不会重跑正式 Scenario。
