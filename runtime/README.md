# RPF-07 Product Runtime

这是 RunProof 的第一份正式产品形态 runtime，不是对 `spikes/` 的重命名。当前 vertical slice 覆盖 Production Change Agent、DeepSeek non-thinking、Docker Fresh-per-run Environment、版本化 Stateful Scenario、structured Trajectory、deterministic Verifier、Run Evidence、真实 FAIL/ERROR、Failure Case 复现、Historical Regression promotion/focused rerun，以及最小三成员 Evaluation Suite 的 Baseline/Candidate 聚合比较。

## Entry points

从仓库根目录运行：

```powershell
python -m unittest discover -s runtime/tests -p 'test_*.py' -v
python runtime/verify-reviewed-artifacts.py
python -m runtime.runproof_runtime --fault none
python -m runtime.runproof_runtime --fault response-lost
python -m runtime.runproof_runtime --agent-profile known-bad-unsafe-precondition-v1
python -m runtime.runproof_runtime --agent-profile production-change-agent-v1-fixed
python -m runtime.runproof_runtime --environment-failure pre-agent-readiness
python -m runtime.runproof_runtime --failure-case-source .local/rpf-05/<agent-fail-run>.json
python -m runtime.runproof_runtime --check-promotion runtime/reviewed-failure-case.json --output .local/rpf-06-check
python -m runtime.runproof_runtime --promote-failure-case runtime/reviewed-failure-case.json --output .local/rpf-06
python -m runtime.runproof_runtime --focused-regression runtime/reviewed-regression.json --agent-profile known-bad-unsafe-precondition-v1
python -m runtime.runproof_runtime --verify-regression runtime/reviewed-regression.json
python -m runtime.runproof_runtime --build-suite runtime/reviewed-regression.json --output .local/rpf-07/suite
python -m runtime.runproof_runtime --validate-suite .local/rpf-07/suite/evaluation-suite.json --regression runtime/reviewed-regression.json
python -m runtime.runproof_runtime --evaluate-suite .local/rpf-07/suite/evaluation-suite.json --agent-version 1.0.0-known-bad-unsafe-precondition --output .local/rpf-07/baseline
python -m runtime.runproof_runtime --evaluate-suite .local/rpf-07/suite/evaluation-suite.json --agent-version 1.0.1-observe-before-mutation-fix --output .local/rpf-07/candidate
python -m runtime.runproof_runtime --compare-baseline-candidate .local/rpf-07/baseline/evaluation.json .local/rpf-07/candidate/evaluation.json --output .local/rpf-07/comparison
python -m runtime.runproof_runtime --verify-evaluation .local/rpf-07/baseline/evaluation.json
python -m runtime.runproof_runtime --verify-comparison .local/rpf-07/comparison/evaluation-comparison.json
```

正常 live 命令从进程环境读取 `DEEPSEEK_API_KEY`，默认模型为 `deepseek-flash`，也可以用 `RPF_MODEL` 或 `--model` 覆盖。每次命令创建独立 Docker container，普通 Run 结果写入被忽略的 `.local/rpf-06/`，不会覆盖历史 Run。known-bad 与 fixed Candidate focused profile 均保留真实 Tool executor、guard、Scenario 和 deterministic verifier；当前两个 focused path 不需要 Provider continuation。known-bad profile 让真实 Tool guard 捕获“先写后观察”的 unsafe intent，从而以稳定方式建立 FAIL 证据；fixed Candidate 先 read state，再以 observed revision 进行唯一 mutation 并独立 read-back。Environment ERROR 使用 runtime-only readiness hook，不是业务 Tool。RPF-07 Evaluation Suite 使用 deterministic profiles 与真实 Docker Fresh-per-member execution，不调用 Provider；每次评测写入被忽略的 `.local/rpf-07/`，历史 reviewed corpus 不被覆盖。

## Contract boundary

- `scenario.py`：Scenario identity/version、Initial State、Task、Required/Acceptable/Forbidden Outcome、Invariants 与 flagship Fault Profile。
- `docker_environment.py`：Docker provider、Fresh-per-run writable-layer state、readiness、initial verification、mutation、cleanup/quarantine。
- `deepseek_provider.py`：non-streaming/non-thinking `chat/completions`、tool envelope/schema/business validation、usage/cost metadata 与 Provider ERROR 分类；无自动 retry。
- `agent.py`：Production Change Agent 的最小 tool executor，包含 response-lost → UNKNOWN_OUTCOME → reconcile 与 blind-retry guard。
- `agent.py`：Production Change Agent profiles；正常、明确隔离的 known-bad unsafe-precondition 与 observe-before-mutation fixed Candidate profile；fixed Candidate 不关闭 guard/invariant。
- `verifier.py`：expected/actual state、S0→S1 State Diff、invariants 与 Verified Result。
- `failure_case.py`：独立 `rpf-failure-case-v1`、稳定 failure signature、Fresh reproduction 与 validation。
- `regression.py`：独立 `rpf-regression-v1`、五项 promotion gate、`rpf-regression-result-v1` focused rerun result 与最小 Historical Regression collection；Regression identity 不依赖随机 source Run ID。
- `evaluation.py`：独立 `rpf-evaluation-suite-v1`、`rpf-evaluation-result-v1` 与 `rpf-evaluation-comparison-v1`；Suite 成员、Scenario/Regression/Policy oracle、source identity 与 member contract digest 冻结，Evaluation 分开统计 Run outcome、Agent quality、evidence coverage、Recovery/Regression、raw usage/cost/latency，Comparison 仅输出 member-level classification 与 aggregate delta，不输出 Release Decision。
- `evidence.py` / `runner.py`：Observed Fact / Verified Result 分层、Run identity、trajectory、redaction、归因与 artifact 写入。

Artifact 不保存 request messages、Authorization、secret、private reasoning 或自由模型文本；只保存可观察的 tool intent/result、fault、environment transition、usage、identity 与确定性验证结果。

## Evidence schema evolution

- `rpf-run-evidence-v1`：RPF-03 历史样本，原样保留，只能作为 legacy evidence 读取；其中旧的顶层 `provider` 语义不会被静默重写。
- `rpf-run-evidence-v2`：RPF-04 当前正式样本。`llm_provider` 只承载 DeepSeek/model/calls/usage/cost；`environment_provider` 只承载 Docker implementation/context/image facts；`environment` 承载 run identity、seed、state ownership、receipt 与 lifecycle contract。
- `rpf-run-evidence-v2`：RPF-05 继续兼容 RPF-04；新 FAIL/ERROR Run 以可选 `failure_attribution`、`health_context` 和 outcome attribution 字段表达 Agent 与 Platform/Environment 分界，不重定义旧 PASS 语义。
- `rpf-trajectory-event-v1`：每个 event 都有 run-scoped `event_id`、显式整数 `sequence`、`event_type`、`evidence_layer` 和 `entity_refs`。顺序与 identity 写入 artifact，不依赖数组位置解释。
- `rpf-failure-case-v1` / `rpf-failure-signature-v1`：Failure Case 不复制完整 Run；通过 source/reproduction Run 与 event refs 关联，只有 signature/evidence pattern 匹配才进入 `validated`。promotion 后以 additive superseding link 指向独立 Regression，原始 validated / `NOT_A_REGRESSION` 历史不被覆盖。
- `rpf-regression-v1` / `rpf-regression-result-v1` / `rpf-regression-collection-v1`：Regression 独立承载 initial state、expected/forbidden outcome、invariants、failure/pass oracle、promotion gate 与 focused rerun refs；底层 Run outcome 与 Regression result 分层，`ERROR` 不转成 Regression `FAIL`，`PASS` 始终为单条 Regression 结果，不代表 Suite、Quality 或 Release。

`reviewed-normal-run.json` 与 `reviewed-response-lost-run.json` 是 v1 历史证据；`reviewed-normal-run-v2.json` 与 `reviewed-response-lost-run-v2.json` 是 RPF-04 重新执行并审查后的 v2 evidence。`verify-reviewed-artifacts.py` 同时验证两代身份边界、源码 hash 和 secret/private-protocol 边界。

仓库内另有 RPF-05 的 `reviewed-agent-fail-run.json`、`reviewed-environment-error-run.json`、`reviewed-agent-fail-reproduction-run.json` 与 `reviewed-failure-case.json`；它们均由正式 runtime 产生、脱敏并绑定 RPF-05 source hash。RPF-06 新增 stability/focused Run、Regression、promotion gate、collection、result 与 promoted Failure Case reviewed artifacts，并绑定历史 RPF-06 source hash。RPF-07 新增三成员 Suite、Baseline/Candidate 各三条 member Run、两份 Evaluation、两份 Regression result 与 Comparison reviewed artifacts，并绑定当前 RPF-07 source hash。`verify-reviewed-artifacts.py` 只做离线校验，不调用 Provider；新的 live Run/Evaluation 写入对应 `.local/`，不会覆盖这些样本。

## Evaluation Suite contract

RPF-07 的固定最小 Suite 是 `rpf-minimal-reliability-suite@1.0.0`，包含 Normal / Functional、Recovery / Fault、Historical Regression 三个 required member。每个 member 都在独立 Fresh-per-member Docker 环境中执行，并保留 readiness、initial-state、cleanup 与 Run/Evidence stable refs。Baseline `1.0.0-known-bad-unsafe-precondition` 与 Candidate `1.0.1-observe-before-mutation-fix` 使用同一 Suite/member/scenario/regression/policy contract，但拥有独立 Evaluation、Run 与 Environment identity。

Quality 只以有效 Agent `PASS/FAIL` evidence 为分母；`ERROR`、`INVALID`、`INCONCLUSIVE`、`CANCELLED` 不被冒充 Agent FAIL，同时会降低 evidence coverage。reported tokens、derived cost、observed latency 分别聚合；缺失 usage/cost 是 `UNKNOWN`，不是零，derived cost 不是 Provider invoice。Comparison 对每个 member 输出 `IMPROVED`、`REGRESSED`、`UNCHANGED` 或 `INCOMPARABLE`，candidate evidence gap 不能成为 improvement；结果边界固定为 `COMPARISON_ONLY_NO_RELEASE_DECISION`。

## Scope boundary

这是单 Run + Failure Case + 单条 Historical Regression + 最小 Evaluation Suite vertical slice，不包含 Java Control Plane、API/backend、DB、Queue、scheduler、durable worker、lease/checkpoint、streaming、thinking continuation、通用 Agent SDK、Quality Policy、Release Gate、SLA/统计显著性或真实生产 destructive operation。RPF-07 Evaluation 是确定性 reviewed prototype，不证明长期 Provider 成本/性能稳定性。Docker 是当前 evidence/provider 实现，不是永久产品身份。
