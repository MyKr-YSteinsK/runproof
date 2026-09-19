# RPF-39 调查结果

## Result

- Plan: `RPF-39`
- Status: `Complete`
- Conclusion: `BOUNDED_DUAL_EMIT_RECOMMENDED`
- Current product behavior: unchanged。RPF-30 仍是 optional、diagnostic-only
  OTel boundary；本 Spike 没有修改正式 Runtime、Java Control Plane、数据库、
  Web、RPF-30 evidence 或 Release Gate。

结论的含义是：如果未来需要让标准 OTLP consumer 识别 RunProof 中的
Agent/model/tool telemetry，应采用显式 opt-in、bounded、可撤销的 compatibility
layer，在保留既有 `runproof.*` spans 的同时，为语义上确实对应的 Agent、model
和 tool operation 产生受限的 GenAI standard spans/metrics。不能把
`gen_ai.*` 当作 RunProof canonical identity、evidence、outcome、reconcile、
quality 或 release authority，也不建议现在直接改 RPF-30 正式 allowlist。

## Upstream identity and stability

调查固定于 2026-09-19 读取的 upstream `main`：

- Repository: <https://github.com/open-telemetry/semantic-conventions-genai>
- Branch: `main`
- Commit: `c88d504ab3d9879f8e50d3cc87e69775e11db234`
- Commit date: `2026-09-16`
- Schema identity: `docs/gen-ai@c88d504ab3d9879f8e50d3cc87e69775e11db234`
- Status: `Development`
- Read set: `README.md`, `gen-ai-agent-spans.md`, `gen-ai-spans.md`,
  `gen-ai-metrics.md`, `gen-ai-events.md`

Pinned upstream documents:

- [GenAI overview](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/c88d504ab3d9879f8e50d3cc87e69775e11db234/docs/gen-ai/README.md)
- [Agent spans](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/c88d504ab3d9879f8e50d3cc87e69775e11db234/docs/gen-ai/gen-ai-agent-spans.md)
- [Model/tool spans](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/c88d504ab3d9879f8e50d3cc87e69775e11db234/docs/gen-ai/gen-ai-spans.md)
- [GenAI metrics](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/c88d504ab3d9879f8e50d3cc87e69775e11db234/docs/gen-ai/gen-ai-metrics.md)
- [GenAI events](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/c88d504ab3d9879f8e50d3cc87e69775e11db234/docs/gen-ai/gen-ai-events.md)

The pinned material defines `invoke_agent`, `chat`, and `execute_tool` operation
names; `deepseek` is a well-known provider value; model request/response,
finish-reason and token-usage fields are available. The documents remain
`Development`, so a future implementation must pin a source identity and carry a
conformance/drift check rather than treating the current names as a stable
canonical schema.

## Current RPF-30 inventory

| Current surface | Source | Current signal and fields | Authority / sensitivity |
|---|---|---|---|
| Durable Control Plane and Worker | `control-plane/.../ObservabilityService.java`, `DurableExecutionController.java`, `runtime/.../durable_worker.py` | `runproof.job.submit`, `claim`, `execute`, `terminalize`, `completion`, `worker.poll`, `job.read`, `job.timeline.read`; allowlisted `job_id`, `attempt_id`, `run_id`, `environment_id`, `operation_id`, job/target/outcome fields | Diagnostic; canonical Job/Attempt/Event/PostgreSQL remains authoritative; IDs are bounded correlation values |
| Agent invocation | `runtime/.../durable_worker.py`, `agent.py`, `agent_contract.py` | `runproof.agent.run`, `runproof.agent.id`, Agent contract/profile/version and `runproof.agent.outcome` where the current Python allowlist permits it | Near-equivalent to an Agent invocation, but Agent contract identity and Agent `FAIL` semantics remain RunProof-specific |
| Provider/model | `runtime/.../deepseek_provider.py` and worker Agent boundary | Provider evidence already records `deepseek`, requested/returned model, finish reason, usage, latency and bounded failure code; the current formal OTel path does not emit `gen_ai.*` model spans | Provider evidence is Observed Fact/Derived Value, not telemetry authority; request body, Authorization and free model content are excluded |
| Tool execution | `runtime/.../runner.py`, `multi_service_environment.py`, `durable_worker.py` | `runproof.tool.call`, operation id, target type, fault profile, effect/mutation count | Near-equivalent to `execute_tool`; tool arguments/results are intentionally absent and remain sensitive/opt-in if ever considered |
| Environment/network | `runtime/.../multi_service_environment.py`, `runner.py` | provision/readiness/cleanup, fault activation, target/dependency request/commit, `runproof.environment.id`, fault profile, propagation boolean | Custom-only; network fault, side effect, receipt and cleanup are not GenAI semantics |
| UNKNOWN_OUTCOME/reconcile | `durable_worker.py`, `DurableExecutionController.java`, `multi_service_environment.py` | `runproof.operation.unknown`, `runproof.operation.reconcile`, response-lost, effect count, reconcile status and no-blind-retry evidence | Custom-only and authority-bearing for safe recovery; must not be inferred from span status or GenAI finish reason |
| Verifier and release decision | `runner.py`, Control Plane controllers/services | `runproof.verifier.evaluate`, evidence/decision/canonical read spans | Custom-only; verifier/evidence/Quality/Release authority is outside GenAI conventions |
| Propagation | Python/Java `ObservabilityService` and `observability.py` | W3C `traceparent`, allowlisted Baggage for the five RunProof correlation IDs | Diagnostic linkage only; canonical PostgreSQL does not depend on trace/span IDs |
| Metrics | `observability.py`, `ObservabilityService.java` | bounded label allowlists (`job_type`, `target_type`, `outcome`, `status`, `fault_profile`, `result`, `service` in Python; Java has the narrower shared set); no stable application metric name was emitted by the targeted current inventory | Diagnostic only; never use job/run/trace IDs as metric labels; GenAI token metric is future additive candidate |

## Mapping matrix

| RPF surface | GenAI relationship | Category | Safe future treatment |
|---|---|---|---|
| DeepSeek provider | `gen_ai.provider.name=deepseek` | `DIRECT` | Emit only when the provider boundary actually ran; keep RunProof provider evidence and source identity |
| Requested/returned model | `gen_ai.request.model`, `gen_ai.response.model` | `DIRECT` | Use exact model strings such as `deepseek-flash`; keep model/attempt/evaluation identity in RunProof fields |
| Agent invocation | `invoke_agent`, `gen_ai.agent.id/name/version`, request model | `ADDITIVE` | Use a stable Agent contract/profile identity, never `attempt_id`, `trace_id` or a transient in-memory instance as `gen_ai.agent.id` |
| Model inference | `chat` or another applicable operation, finish reason, usage | `ADDITIVE` | Add only to a bounded compatibility span around the actual provider call; token counts only when provider evidence is available |
| Tool execution | `execute_tool`, tool name/type/call id | `ADDITIVE` | Add only the low-cardinality operation identity; keep operation/effect/receipt in `runproof.*` |
| Job / Attempt / Run / Environment / Operation | No equivalent GenAI semantic identity | `CUSTOM_ONLY` | Keep `runproof.*` attributes and W3C context as diagnostic correlation; never substitute a GenAI attribute |
| `UNKNOWN_OUTCOME`, reconcile, fault profile, verifier, evidence, quality, release | No equivalent semantic authority | `INCOMPATIBLE` | Keep custom spans and canonical records; a transport error or model finish reason cannot decide Agent `FAIL` or release eligibility |
| Prompt/messages/system instructions/tool definitions/arguments/results | GenAI events and Opt-In attributes exist | `OPT_IN_SENSITIVE` | Forbidden by default for RunProof; require a separate privacy/data-retention decision before any opt-in experiment |
| `gen_ai.conversation.id` | Conversation/session concept | `NOT_APPLICABLE` | Do not map `run_id`, `job_id`, `attempt_id` or trace ID; if a real conversation ID is unavailable, leave it unset |

## Repeatable compatibility experiment

Command executed:

```powershell
python spikes/rpf-39/probe.py --run
python spikes/rpf-39/verify-evidence.py .local/rpf-39/local/run-17d86b1b6e/rpf39-result.json
```

The probe used the RPF-30 pinned `otel/opentelemetry-collector-contrib:0.157.0`
file Collector and current Python SDK/bounded processor. It emitted a
deterministic synthetic path only; no DeepSeek request, API key read, Agent Tool
side effect, PostgreSQL write, release, deploy or cloud operation occurred.

Observed result:

- Source identity: `88caa57a3cb17360b973104cc0bb0a4a9451fc2414d3ae1304d5e8ea03b72dbb`
- Healthy Collector: 8 spans, export failures `0`
- Standard spans: `invoke_agent production-change-agent`, `chat deepseek-flash`,
  `execute_tool apply_change`
- Standard metric: `gen_ai.client.token.usage`, 2 points with only operation,
  provider, model and input/output token-type labels
- Disabled mode: no exporter created
- Unavailable mode: 8 diagnostic export failures, caller did not fail or change
  canonical projection
- Canonical projection: disabled/healthy/unavailable were byte-equivalent;
  final outcome `PASS`, effect count `1`, mutation requests `1`, and
  `unknown_outcome_reconciled=true`
- Negative controls: `UNKNOWN_OUTCOME` target transport span and reconciled span
  remained distinct; no `gen_ai.conversation.id`, messages, instructions, tool
  definitions, tool arguments/results, credentials, body or private reasoning
  appeared
- Cleanup: Collector container removed; `formal_rpf30_evidence_touched=false`

The result directory is ignored disposable evidence, not a reviewed artifact.
RPF-30 reviewed evidence and the canonical corpus were not refreshed.

## Interoperability decision

Standard OTLP consumers can decode the candidate GenAI Agent/model/tool span
names and attributes, and the pinned Collector accepted them beside RunProof
correlation attributes. This is only signal-level interoperability: a generic
consumer cannot infer RunProof outcome validity, receipt/effect count,
`UNKNOWN_OUTCOME` reconciliation, Failure Case promotion, Quality Gate or
Release Decision from those standard signals. The standard consumer therefore
does not replace the canonical evidence read-back or failure-isolation model.

The chosen strategy is bounded dual emit rather than migration:

1. Keep existing `runproof.*` spans, allowlists, canonical IDs and outcome
   contracts unchanged.
2. In a future explicitly authorized compatibility boundary, emit only selected
   standard Agent/model/tool spans as children or adjacent diagnostic spans.
3. Gate the feature opt-in; keep disabled and exporter-unavailable paths
   product-equivalent; bound queue, export timeout, attributes and metrics.
4. Pin SDK/source/schema identity and verify Python/Java symmetry, standard
   attribute allowlists and Development-semantic drift before delivery.

No formal RPF-30 schema migration or next Plan file is created by this result.

## Remaining risks and next boundary

- The upstream GenAI repository is still `Development`; names, fields and
  requirement levels may drift.
- RPF-30 Java/Python allowlists are intentionally strict and not identical in
  every auxiliary field. A future compatibility implementation must define one
  shared mapping contract and a conformance verifier before changing either
  language.
- The experiment proves SDK/Collector acceptance and failure isolation with a
  deterministic fixture, not live DeepSeek latency/cost behavior, a production
  trace-retention policy, a Web trace view or a managed observability backend.
- The next boundary, if separately authorized, is a narrow opt-in mapping Plan
  covering source/version pinning, Python/Java dual emit, standard span naming,
  token metric truthfulness, privacy/cardinality gates and hosted evidence. It
  must not add canonical trace schema, replace RunProof IDs, import Production
  traces, add SaaS/retention, or grant Agent/Release authority.
