# CURRENT_STATE

> 当前真实快照；稳定产品意图见 `PROJECT_BRIEF`，长期决定见 `DECISIONS`，执行规则见根目录 `AGENTS.md`，历史验证见 `docs/history/`。本文不追加过程日志。

## Current snapshot

- Lifecycle: `Stabilization / Portfolio Maintenance`。
- Plan status: `RPF-00` through `RPF-39` are `Complete`。RPF-38 只完成 workflow/governance/history/spike lifecycle 的低风险收束；RPF-39 完成 GenAI semantic-convention 互操作调查，结论为未来可采用受限 opt-in bounded dual emit，但不改变 RPF-30 正式 boundary、产品行为、Release authority 或 Production topology。
- Branch/repository: `main` / public `MyKr-YSteinsK/runproof`。默认交付模型为 commit → push；当前 HEAD 与 upstream 关系以 Git 状态和本次 `TASK_RESULT` 为准。
- Product/published version: none。`0.1.0-rc.1` remains a historical production-like probe recommendation, not a tag or release。
- Production Cloud: `Deferred`。AWS `ap-southeast-1` 只是 RPF-36 的 candidate topology；未创建 cloud account、paid resource 或执行 Production deploy/release。
- Project-State source of truth: `PROJECT_BRIEF.md` 持有稳定产品/UX 合同；`DECISIONS.md` 持有 canonical decisions；本文持有当前快照；`docs/history/` 持有重要历史证据；`AGENTS.md` 只持有当前执行规则。

## Current capabilities

- Desktop Web Control Plane 是 API-backed、read-only 的双语调查面；locale 只改变 presentation，route/entity/status/identifier/hash/schema/evidence bytes 不随语言改变。API/artifact 不可用或未 verified 时 fail closed。
- Java/Spring formal Control Plane 持有 PostgreSQL canonical metadata、显式 local/S3 ArtifactStore、durable Job/Attempt/Operation/Event、verified artifact resolution 和 append-only/superseding Decision history。
- Python Runtime、独立 durable Worker 与两个显式 Agent contract 支持 controlled stateful evaluation、response-loss reconcile、Failure Case/Regression、Failure Intelligence、statistical trial semantics 与 HTTP/JSON Control Plane access。
- Golden Demo 提供本机 API-backed、read-only、interview-grade 路径，包含 reviewed corpus seed/read-back 与 Windows process/container lifecycle boundary。
- RPF-28 formal multi-service Environment 保留单容器路径，同时提供 fresh Docker internal network、target/dependency/Toxiproxy/Agent-shaped client、fault provenance、receipt/effect-count reconcile 与 no-blind-retry 证据。
- RPF-30 提供 optional OpenTelemetry diagnostic boundary，传播 W3C `traceparent` 与 allowlisted Baggage；OTel 不是 canonical identity、Release authority 或启动依赖。RPF-39 已证明 selected GenAI Agent/model/tool signals 可 additive 互操作，但当前不启用 standard mapping，prompt/messages/tool payload 默认禁止。
- RPF-32 提供 provider-neutral S3-compatible ArtifactStore；`LocalFileArtifactStore` 仍为默认，历史 reviewed bytes 未迁移。RPF-34/35 提供 bounded Execution/Canonical read models 与 opaque keyset cursors，Overview 使用固定 Golden Demo refs，不爬取完整 corpus。
- RPF-36 只保留 dated provider/topology comparison 与 managed-operations candidate evidence。RPF-27/29/31 等 historical candidate source、workflow、README、reviewed corpus 与原路径均保留；`ARCHIVE != DELETE`。

## Public and execution documentation

- Public docs: `README.md` / `README.zh-CN.md`，`docs/ARCHITECTURE*`、`RELIABILITY_MODEL*`、`DEMO*`、`GLOSSARY*`；`python ci/verify-public-docs.py` 是配对、语义、本地链接、命令与 secret-path contract check。
- Historical docs: `docs/history/VERIFICATION_HISTORY.md`、`.zh-CN.md`；RPF-00 至 RPF-39 的执行导航为 [`RPF_EXECUTION_INDEX.md`](../history/RPF_EXECUTION_INDEX.md)。具体命令仍以各 Spike/模块 README 与脚本为准。
- Fast path: ordinary push/PR 只触发 `.github/workflows/release-gate.yml`，覆盖 repository checks、fresh PostgreSQL/Control Plane、durable evaluation、canonical Decision read-back、redacted artifact 与 Job Summary。
- Manual path: RPF-27/29/31/36 historical candidates 与 RPF-28/30/32/33/34/35 formal/heavyweight proofs 保留 `workflow_dispatch`；它们不再对普通 push/PR 自动扇出，仍可 fresh-checkout 复现。
- Workflow permissions: 当前 workflow 只声明 `contents: read`；没有新增 `actions`、`id-token`、云 secret、release 或 deploy 权限。

## Latest verification and delivery facts

- RPF-38 local core matrix passed: Runtime unit tests, reviewed-artifact verifier, public-doc verifier, Golden Demo verifier, Control Plane Maven test/package, Web tests, Web typecheck and Web build。Build retains the known shared-bundle warning；real-device verification was not executed。
- RPF-38 post-cleanup audit is the current maintenance evidence；its tracked-tree counts, before/after bytes, workflow fan-out and exact Git hygiene comparison are reported in the final `TASK_RESULT` and verification history, with no source/evidence deletion used。
- Reviewed evidence manifest before/after has identical paths, bytes and SHA-256 values；no reviewed JSON was renamed, moved, formatted, regenerated, normalized, merged or deleted。
- Selected manual workflow verification passed for one historical workflow and one formal heavyweight workflow after the trigger change; exact run IDs, artifact/verifier result and commit are recorded in `docs/history/VERIFICATION_HISTORY.md` after delivery。
- The final hosted canonical Release Gate is the required final delivery check for the resulting `main` HEAD；its run and artifact are reported in the final `TASK_RESULT`。It produces evidence only; no release/deploy/cloud operation is authorized or executed。
- RPF-37 audit baseline before RPF-38 was `379` tracked files / `5,273,659` bytes / `20` spikes / `11` workflows / zero generated files / zero duplicate hash groups. RPF-38 reduced automatic push/PR fan-out to one workflow and intentionally did not delete historical source or evidence。
- RPF-39 local disposable proof passed with source identity `88caa57a3cb17360b973104cc0bb0a4a9451fc2414d3ae1304d5e8ea03b72dbb`：pinned GenAI upstream `c88d504ab3d9879f8e50d3cc87e69775e11db234` remained `Development`; healthy Collector accepted 8 spans / 3 standard Agent-model-tool spans and `gen_ai.client.token.usage`; disabled/unavailable modes preserved the same canonical projection。无 live Provider、API key、RPF-30 evidence mutation、release/deploy/cloud operation。

## Known limits and risks

- No Production HA or managed cloud resource is deployed; multi-host supervision, human Approval configuration, OAuth/OIDC/SSO, tenant/RBAC, broker, scheduler, autoscaling, real destructive Production remediation and release/deploy endpoint remain unimplemented or unauthorized。`ELIGIBLE` remains decision-only。
- `LocalFileArtifactStore` remains the default local backend；S3 evidence is single-node compatibility proof, not a managed Production durability/HA/replication/lifecycle/restore-SLA/capacity conclusion. Orphan cleanup and retention remain future boundaries。
- Statistical and Agent corpora are deterministic/controlled and small；they do not establish live Provider probability, Production-scale significance or long-term cost/latency distribution。
- Desktop/in-app browser evidence is representative where recorded；real-device/iOS/mobile/PWA verification was not executed。The Web build may report a shared chunk-size warning。
- RPF-33 remains directional capacity evidence, not a Production QPS/SLA claim。RPF-35 cross-type EXPLAIN still has a sequential scan；formal index migration, artifact streaming, Web virtualization and GC remain deferred until a repeatable benefit and separate Plan exist。
- RPF-28/30/32/34/35 formal proofs remain manual risk boundaries, not automatic Production readiness. RPF-30 OTel is diagnostic-only；trace/span identity never becomes canonical Run/Job/Attempt/evidence identity or Release authority。GenAI semantic conventions remain upstream `Development` and do not supply RunProof reconcile/verifier/release semantics。
- Hosted action annotations still include existing Node.js 20 action-runtime, setup-java v4 and `ubuntu-latest` migration warnings；RPF-38 records them but does not perform a broad toolchain upgrade。

## Active work

RPF-38 cleanup、Project-State layering、lifecycle index、local regression、selected manual workflow proof 与 RPF-39 GenAI 互操作调查均已完成。No unrelated product feature implementation is active；the repository is ready for maintenance-only work or a new focused Plan。

## Next likely boundary

Stop at the portfolio-maintenance boundary unless a new focused product or toolchain Plan is authorized。未来如需实现 RPF-39 的 bounded dual emit，应以独立授权的 compatibility Plan 固定 SDK/schema drift、Python/Java symmetry、privacy/cardinality 与 hosted evidence；Production Cloud remains Deferred and AWS `ap-southeast-1` remains candidate-only。

## Update rule

Only material current facts, lifecycle, capability, limitation, verification or delivery changes belong here. Do not append task transcripts, full command output or `TASK_RESULT` dumps. Move no-longer-current but still useful facts to `docs/history/` instead of duplicating them here.
