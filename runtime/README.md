# RPF-03 Product Runtime

这是 RunProof 的第一份正式产品形态 runtime，不是对 `spikes/` 的重命名。当前 vertical slice 只覆盖 Production Change Agent、DeepSeek non-thinking、Docker Fresh-per-run Environment、一个版本化 Stateful Scenario、structured Trajectory、deterministic Verifier 与独立 Run Evidence artifact。

## Entry points

从仓库根目录运行：

```powershell
python -m unittest discover -s runtime/tests -p 'test_*.py' -v
python runtime/verify-reviewed-artifacts.py
python -m runtime.runproof_runtime --fault none
python -m runtime.runproof_runtime --fault response-lost
```

live 命令从进程环境读取 `DEEPSEEK_API_KEY`，默认模型为 `deepseek-flash`，也可以用 `RPF_MODEL` 或 `--model` 覆盖。每次命令创建独立 Docker container，结果写入被忽略的 `.local/rpf-03/`，不会覆盖历史 Run。

## Contract boundary

- `scenario.py`：Scenario identity/version、Initial State、Task、Required/Acceptable/Forbidden Outcome、Invariants 与 flagship Fault Profile。
- `docker_environment.py`：Docker provider、Fresh-per-run writable-layer state、readiness、initial verification、mutation、cleanup/quarantine。
- `deepseek_provider.py`：non-streaming/non-thinking `chat/completions`、tool envelope/schema/business validation、usage/cost metadata 与 Provider ERROR 分类；无自动 retry。
- `agent.py`：Production Change Agent 的最小 tool executor，包含 response-lost → UNKNOWN_OUTCOME → reconcile 与 blind-retry guard。
- `verifier.py`：expected/actual state、S0→S1 State Diff、invariants 与 Verified Result。
- `evidence.py` / `runner.py`：Observed Fact / Verified Result 分层、Run identity、trajectory、redaction 和 artifact 写入。

Artifact 不保存 request messages、Authorization、secret、private reasoning 或自由模型文本；只保存可观察的 tool intent/result、fault、environment transition、usage、identity 与确定性验证结果。

## Evidence schema evolution

- `rpf-run-evidence-v1`：RPF-03 历史样本，原样保留，只能作为 legacy evidence 读取；其中旧的顶层 `provider` 语义不会被静默重写。
- `rpf-run-evidence-v2`：RPF-04 当前正式样本。`llm_provider` 只承载 DeepSeek/model/calls/usage/cost；`environment_provider` 只承载 Docker implementation/context/image facts；`environment` 承载 run identity、seed、state ownership、receipt 与 lifecycle contract。
- `rpf-trajectory-event-v1`：每个 event 都有 run-scoped `event_id`、显式整数 `sequence`、`event_type`、`evidence_layer` 和 `entity_refs`。顺序与 identity 写入 artifact，不依赖数组位置解释。

`reviewed-normal-run.json` 与 `reviewed-response-lost-run.json` 是 v1 历史证据；`reviewed-normal-run-v2.json` 与 `reviewed-response-lost-run-v2.json` 是 RPF-04 重新执行并审查后的 v2 evidence。`verify-reviewed-artifacts.py` 同时验证两代身份边界、源码 hash 和 secret/private-protocol 边界。

仓库内的 `reviewed-normal-run.json` 与 `reviewed-response-lost-run.json` 是两份已审查、脱敏且绑定当前 runtime source hash 的 live evidence 样本；`verify-reviewed-artifacts.py` 只做离线校验，不调用 Provider。新的 live Run 仍写入 `.local/rpf-03/`，不会覆盖这些样本。

## Scope boundary

这是单 Run vertical slice，不包含 Java Control Plane、Web、DB、Queue、scheduler、durable worker、lease/checkpoint、streaming、thinking continuation、通用 Agent SDK 或真实生产 destructive operation。Docker 是当前 evidence/provider 实现，不是永久产品身份。
