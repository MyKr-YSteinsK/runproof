# RPF-39 — OpenTelemetry GenAI 语义约定互操作边界

RPF-39 是一个 Investigation / Spike。它调查当前 RPF-30 正式 OTel
diagnostic boundary 是否适合与 OpenTelemetry GenAI Semantic Conventions
互操作，并把结论固定为可重复的、离线 deterministic proof。

## 结论边界

- 当前 RPF-30 的 `runproof.*` span、Job/Attempt/Run/Environment/Operation
  identity、`UNKNOWN_OUTCOME` reconcile、Failure/Release authority 不迁移到
  `gen_ai.*`。
- Provider/model、Agent invocation 和 tool execution 存在可互操作的
  additive mapping；RunProof durable、environment、reconcile、verifier 和
  release semantics 没有等价的 GenAI semantic convention。
- 结论为 `BOUNDED_DUAL_EMIT_RECOMMENDED`：未来如需接入，只允许一个独立的
  opt-in compatibility layer，在保留 `runproof.*` diagnostic spans 的同时，
  为 model/agent/tool 产生受限的标准 spans/metrics。当前 RPF-30 不因本 Spike
  自动改变 allowlist、schema、canonical evidence 或默认开关。
- Prompt、private reasoning、messages、system instructions、tool definitions、
  tool arguments/results、credential、HTTP body 和路径默认不发出；不得以
  `gen_ai.conversation.id` 替代 RunProof correlation。

## Commands

依赖使用 RPF-30 已固定的 OpenTelemetry Python SDK；Collector 使用 RPF-30
已经固定的 disposable image。默认输出目录会生成新的 ignored run 目录，避免
复用旧的 Collector file。

```powershell
python spikes/rpf-39/probe.py --run
python spikes/rpf-39/verify-evidence.py .local/rpf-39/local/run-<id>/rpf39-result.json
```

也可以显式指定 ignored 输出目录：

```powershell
python spikes/rpf-39/probe.py --run --output-dir .local/rpf-39/local/<run>
python spikes/rpf-39/verify-evidence.py .local/rpf-39/local/<run>/rpf39-result.json
```

Probe 不读取 `DEEPSEEK_API_KEY`、不调用 DeepSeek、不执行 Agent Tool、不写
PostgreSQL、不修改 RPF-30 reviewed evidence，也不执行 release/deploy/cloud
操作。它复用 RPF-30 的 pinned Collector/config、当前正式 Python OTel bounded
processor，并用 deterministic synthetic Agent/model/tool path 证明标准 OTLP
span/metric 与 RunProof correlation 可以共存；Collector/container 在每次运行
后清理。

完整调查结果、mapping matrix、上游 identity、实际实验摘要和后续边界见
[`RESULT.md`](RESULT.md)。
