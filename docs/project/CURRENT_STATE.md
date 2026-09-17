# CURRENT_STATE

> 当前真实快照；稳定产品意图见 `PROJECT_BRIEF`，执行政策见根目录 `AGENTS.md`，历史验证见 `docs/history/`。本文不追加过程日志。

## Current snapshot

- Lifecycle: `Stabilization`。
- Active plan: `RPF-28` formal Multi-service Controlled Environment / Network Fault Profiles is complete after the full six-profile five-repeat matrix, actual negative-control matrix, independent PostgreSQL/Control Plane/durable-worker verification, and successful focused hosted run [35195998367](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35195998367). The repository remains in `Feature Freeze / Portfolio Maintenance` for unrelated product behavior。
- Plan status: `RPF-00` through `RPF-28` are `Complete`; RPF-28 adds an additive `multi-service-toxiproxy-v1` Runtime Environment and does not replace the single-container path, rewrite historical reviewed bytes, or add Production authority。
- Branch: `main`；repository: public `MyKr-YSteinsK/runproof`；默认交付模型仍为 commit → push，未执行 release/deploy。
- Product / published version: none。`0.1.0-rc.1` remains a historical production-like probe recommendation, not a tag or release。
- Current source of truth: `PROJECT_BRIEF.md` 持有稳定产品与 UX 合同；`DECISIONS.md` 持有 canonical decisions；本文持有当前快照；`VERIFICATION_HISTORY.md` 持有重要历史证据。

## Current capabilities

- Desktop Web Control Plane is an API-backed, read-only investigation surface with explicit `en-US` / `zh-CN` presentation locale. Route, entity, raw status, identifier, hash, schema, and evidence bytes remain unchanged by locale.
- Java/Spring formal Control Plane owns PostgreSQL canonical metadata, verified immutable local artifact references, durable Job/Attempt/Operation/Event state, and append-only/superseding Decision history.
- Python Agent/Evaluation Runtime and independent durable Worker support controlled stateful evaluation, response-loss reconciliation, Failure Case/Regression, Failure Intelligence, statistical trial semantics, and HTTP/JSON Control Plane access.
- Two explicit Agent contracts are represented: `Production Change` and `Incident Remediation`。当前 reviewed corpus covers deterministic controlled scenarios, not long-term live Provider reliability。
- Golden Demo provides a local, interview-grade, API-backed path with reviewed corpus seed/read-back and ownership-aware Windows process/container lifecycle checks。
- GitHub Actions provides a hosted canonical Release Gate with fresh PostgreSQL/Control Plane execution, redacted result artifacts, Job Summary verification, and canonical Decision read-back。
- RPF-27 provides a disposable real multi-service candidate topology: an Agent-shaped client container reaches a private Docker fault boundary, which reaches an incident target and dependency; the harness independently reads target receipt/state. Local Windows Docker evidence repeats Toxiproxy and the narrow custom shim response-loss path five times each; Envoy HTTP delay/abort is exercised only as a feasibility comparison。
- RPF-28 formally integrates `multi-service-toxiproxy-v1`: each Run owns a fresh Docker `--internal` network with target, dependency, Toxiproxy, and Agent-shaped client; the client sees only the data-plane proxy, while the harness owns fault activation and target receipt/state observation. Existing `DockerEnvironment` remains supported。

## RPF-26 public documentation surface

- Root entry: `README.md` (English default) and `README.zh-CN.md`。
- Paired public docs: `docs/ARCHITECTURE.md`, `docs/RELIABILITY_MODEL.md`, `docs/DEMO.md`, `docs/GLOSSARY.md` and their `.zh-CN.md` companions。
- Historical docs: `docs/history/VERIFICATION_HISTORY.md` and `docs/history/CAPABILITY_HISTORY.md` with Chinese companions。
- Governance remains single-source: no `DECISIONS.en.md` or `CURRENT_STATE.en.md` is introduced。Module READMEs remain implementation-facing and are indexed by the public architecture map。
- `python ci/verify-public-docs.py` is the lightweight contract check for required pairs, key semantic sections, local links, command strings, path/secret boundaries, and governance duplication。
- RPF-26 local public-docs verification passed with `PUBLIC_DOCS_PASS files=18 pairs=7`。

## Verification and delivery facts

- RPF-25 local verification passed Web tests/typecheck/build, runtime 77-test suite, reviewed-artifact and Golden Demo verifiers, formal Control Plane Maven package, RPF-16/RPF-17/RPF-18 evidence verifiers, and the local canonical gate. The Web build retained a shared-bundle warning; real-device verification was not executed。
- RPF-26 local verification passed the public-docs contract, runtime `77/77`, Web `11` files/`40` tests, `npm run build` (including typecheck), formal Control Plane Maven package, reviewed-artifact verifier, Golden Demo verifier, and RPF-16/RPF-17/RPF-18 evidence verifiers. The build retained the known shared-bundle warning; no product runtime behavior changed。
- RPF-27 local verification passed `python spikes/rpf-27/verify-evidence.py` after a fresh three-candidate Windows Docker matrix: Toxiproxy response-lost `5/5`, custom shim response-lost `5/5`, Envoy response-lost `0/5` with deterministic `ABORT_BEFORE_SIDE_EFFECT` limitation; all baseline/latency/dependency scenarios and all trial cleanup checks passed. The ignored result records source identity, per-run environment/network/container identity, target receipt/effect count, reconcile, no-blind-retry, fault provenance, timings, and security boundary; it is not a reviewed corpus artifact。Hosted selected-candidate verification passed in [run `35186899267`](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35186899267) after the initial all-candidate hosted attempt [run `35185942172`](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35185942172) failed at the disposable evidence verifier; the hosted workflow was then explicitly scoped to Toxiproxy, while the full comparison remained local。
- RPF-28 local verification passed the full `6 profiles × 5 repeats` Docker matrix (`none`, `latency`, `timeout`, `dependency-unavailable`, `response-lost`, `pre-side-effect-failure`), 8 actual negative controls, lifecycle/fault/effect-count/cleanup checks, independent PostgreSQL + formal Control Plane + durable worker canonical completion, `python spikes/rpf-28/verify-evidence.py`, and `python runtime/verify-reviewed-artifacts.py`. Current RPF-28 source identity is `b5f2c22fce21d0c14455a2ee076d1d12df31f5dbc10c9fe8aef9ea97d7fcfaa6`; reviewed baseline/dependency/response-loss artifacts are bound to `rpf-28.v1` and remain separate from RPF-27。
- RPF-28 hosted focused verification succeeded in [run `35195998367`](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35195998367) for final probe commit `6d50332`: GitHub-hosted Ubuntu executed the baseline and response-loss transport paths, all 8 negative controls, cleanup checks, evidence verifier, and uploaded artifact `rpf-28-multi-service-35195998367-1` with digest `sha256:4676e9d93212df3109f8d163224a74940aa41bed7b4493ec05def603ac9ffba8`。The focused workflow did not execute release/deploy; GitHub reported only the existing action Node.js 20 deprecation warning。
- RPF-28 commit `6d50332` also passed the existing hosted canonical Release Gate in [run `35195998252`](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35195998252): fresh PostgreSQL/Control Plane durable evaluation, canonical Decision read-back, and redacted artifact upload completed in `1m18s`; artifact `rpf-12-release-gate-35195998252-1` has digest `sha256:a8cda002d69e1098828e8e10766891b701015c40562c94d6fa3ed945f9dbd596c`。It did not execute release/deploy; GitHub reported the existing action Node.js 20 and setup-java v4 deprecation warnings。
- RPF-26 hosted delivery: GitHub Actions [run `35181115566`](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35181115566) for commit `e177453` succeeded in `1m21s`; the fresh canonical gate job succeeded in `1m17s` and uploaded redacted artifact `rpf-12-release-gate-35181115566-1` with digest `sha256:e6c29d3af1d5ac582f92bec47199695404b0a0c367305235592aca00dcab1762`。The workflow did not execute release/deploy; GitHub reported only existing Node.js 20/setup-java v4 deprecation warnings。
- The RPF-25 implementation and state commits were pushed to `origin/main`; hosted Release Gate run [35179169378](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35179169378) succeeded and uploaded the redacted artifact `rpf-12-release-gate-35179169378-1`。It did not execute release/deploy。
- RPF-14/RPF-15/RPF-16/RPF-17 source identities, RPF-19 lifecycle measurements, RPF-21/RPF-22/RPF-23 hosted/local evidence, and older compatibility facts are preserved in [VERIFICATION_HISTORY.md](../history/VERIFICATION_HISTORY.md)。They are not duplicated here as command logs。
- This RPF-28 task preserves historical reviewed bytes, runtime/web/control-plane implementation, and the user-owned untracked `docs/reviews/` material。

## Known limits and risks

- No Production HA, managed PostgreSQL/object storage deployment, multi-host supervisor, human Approval, OAuth/OIDC/SSO, tenant/RBAC, broker, scheduler, autoscaling, real destructive Production remediation, or release/deploy endpoint is implemented or authorized。
- Current artifact storage is local filesystem and current service credentials are scoped bearer candidates; neither is a Production security/durability conclusion。
- Statistical corpus and Agent corpus are deterministic/controlled and small. They do not establish live Provider probability, Production-scale significance, or long-term cost/latency distribution。
- Desktop/in-app browser evidence is representative where recorded; real device/iOS/mobile/PWA verification was not executed。The Web build may report a shared chunk-size warning。
- `ELIGIBLE` remains decision-only. `Agent FAIL` is not `Platform ERROR`; `UNKNOWN_OUTCOME` requires reconcile before retry。
- RPF-28 still does not establish Production isolation/HA, OTel instrumentation, S3/MinIO artifact storage, capacity behavior, cross-platform equivalence, broker/scheduler/autoscaling, human Approval, tenant/RBAC, real destructive remediation, or release/deploy authorization. Toxiproxy is the formal RPF-28 provider boundary, not a general Production chaos framework; the Agent-shaped client is not a live Provider reliability claim。

## Active work

RPF-28 implementation, local evidence, and focused hosted confirmation are complete. No unrelated product feature implementation is active. Existing Golden Demo and hosted gate maintenance remains available, but does not expand authority or deployment scope。

## Next likely boundary

The next evidence-led boundary is OpenTelemetry-compatible observability, persistent/object-backed artifact durability, or capacity/large-trace behavior only if measured need justifies it. This state does not infer Production HA, Approval, broker, scheduler, autoscaling, or release authority。

## Update rule

Only material current facts, lifecycle, capability, limitation, verification, or delivery changes belong here. Do not append task transcripts, full command output, or `TASK_RESULT` dumps. Update the historical ledger instead when a fact is no longer current but remains useful evidence。
