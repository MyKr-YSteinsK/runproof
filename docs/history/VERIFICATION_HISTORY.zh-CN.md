# RunProof 验证历史

[English](VERIFICATION_HISTORY.md) | [简体中文](VERIFICATION_HISTORY.zh-CN.md) | [Current State](../project/CURRENT_STATE.md)

本文是重要验证事实的精简历史 ledger。它保留 source identity、hosted run、里程碑 probe 和兼容性边界，不复制命令流水或 `TASK_RESULT` 文件。当前快照仍在 [CURRENT_STATE.md](../project/CURRENT_STATE.md)。

## 里程碑证据

| 里程碑 | 重要事实 | Evidence anchor |
|---|---|---|
| RPF-01 / RPF-02 | 验证了 disposable Agent contract 与 Controlled Environment prototype 边界；Docker evidence 是 prototype-level，不是 Production isolation。 | `spikes/rpf-01/`、`spikes/rpf-02/`、固定 reviewed evidence |
| RPF-03 / RPF-04 | 首个有状态 Run slice 将真实 DeepSeek tool loop 连接到 Docker state、response-loss reconciliation、Run Evidence、State Diff 和只读 Web surface。 | `runtime/`、`web/`、reviewed RPF-03/RPF-04 artifacts |
| RPF-05 / RPF-06 | Agent `FAIL`、platform/environment `ERROR`、Failure Case reproduction、Regression promotion 和 focused rerun 成为独立 evidence domain。 | `runtime/`、reviewed Failure/Regression corpus |
| RPF-07 / RPF-08 | 建立了 deterministic Evaluation Suite、Baseline/Candidate Comparison、Quality Policy、Gate 和只读 Release Decision。 | RPF-07 reviewed source `c607e5e38015c99fedcbba3efbcdc20834953f2fec7543313ead3ce0211d3adf`；RPF-08 reviewed source `d6313e5849b2662d9badafa7be25d568e84ab6cc4912c9587495a5f9427bfd69` |
| RPF-09 / RPF-10 / RPF-11 | Lifecycle 从 Prototype 进入 Stabilization；H2 与真实 PostgreSQL candidate 建立了 persistence、artifact、API、service-authority 和正式 Control Plane 边界。 | `spikes/rpf-09/`、`spikes/rpf-10/`、`control-plane/` probes |
| RPF-12 | GitHub-hosted runner 上 fresh PostgreSQL + 正式 Control Plane + durable evaluation 成功完成 canonical Decision read-back 与脱敏 artifact；没有 release/deploy。 | [hosted run 34742919966](https://github.com/MyKr-YSteinsK/runproof/actions/runs/34742919966) |
| RPF-13 / RPF-14 | 验证了 PostgreSQL poll/claim/lease、fenced attempt、operation identity、response-loss reconciliation、artifact recovery 和正式 Python durable worker。 | RPF-14 source identity `810bf15c8ec6a34c7961ab8333fca7378534416675baf0c6eaf08ff3b3a43412`；`control-plane/` probe 与 evidence verifier |
| RPF-15 | 验证了 Candidate A production-like replacement、PostgreSQL dump/restore、artifact backup/restore、active-job reconcile、secret rotation 和 explicit-release 边界；Candidate B 仍是结构化目标比较。 | RPF-15 source identity `2cbcbc7934658009a22808c8b9e965f5395c362601a409878905c96152523f64`；`PRODUCTION_LIKE_PROBE_ONLY` |
| RPF-16 | 第二个显式 Incident Remediation Agent 覆盖了 local、external-dependency、response-lost、Failure Case、Regression、独立 Suite/Gate 和正式 durable-worker path。 | RPF-16 source identity `4569575d4a34853e5c85681dbac6576a8bf3a1252fc4cc34e8691c2378e8f494`；`spikes/rpf-16/` verifier |
| RPF-17 | 在不使用 LLM/embedding/ML 的前提下，验证了确定性 attribution、first divergence、exact/structural grouping、cross-Agent family、negative controls 和 fail-closed Version Bisect。 | RPF-17 source identity `9654c309b427de8da42192f2cda79383c257a7680b46ce4ca2098feafc19dad6`；`spikes/rpf-17/` verifier |
| RPF-18 | 验证了受控 Stable、Flaky、Safety、Evidence-poor statistical cohort、Wilson interval、denominator separation、safety precedence、Failure Intelligence link 和 PostgreSQL Trial Job。 | `spikes/rpf-18/`、reviewed statistical corpus、[hosted run 34942385897](https://github.com/MyKr-YSteinsK/runproof/actions/runs/34942385897) |
| RPF-19 | 验证了 versioned Golden Demo profile、两个 Agent、幂等 seed、API-backed Overview、evidence deep link 和本地 start/stop/restart lifecycle。 | `demo/rpf-19-golden-demo-v1.json`、`demo/verify-golden-demo.py`、[hosted run 34947014281](https://github.com/MyKr-YSteinsK/runproof/actions/runs/34947014281) |
| RPF-21 / RPF-22 | 恢复了 fresh PostgreSQL 与 canonical gate trust chain，并硬化 eligible discovery starvation、artifact containment、single-read verification 和 writer/verifier authority。 | [hosted run 35071819220](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35071819220)、[hosted run 35077060386](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35077060386) |
| RPF-23 | 验证了 Windows child environment、worker path containment、process/session identity、rollback、ownership label、restart 和 fail-closed cleanup。 | `demo/verify-lifecycle.ps1`；当前 Windows 本机 lifecycle evidence |
| RPF-24 / RPF-25 | 在保留 Web canonical truth 和最小模块边界的同时，验证了 presentation-only `en-US`/`zh-CN` i18n、raw-status traceability、locale persistence 和 API-unavailable 行为。 | RPF-25 implementation `d2571754c89e50564084cafc369cccf477650133`；[hosted run 35179169378](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35179169378) |
| RPF-26 | 在不改变产品行为的前提下交付了双语公共文档、current/history Project-State 分离、公共本地链接/语义/命令/secret-path verifier 与 CI 集成。 | Implementation `e17745396bf58e54465d82a4b5cc0758c648bfa6`；[hosted run 35181115566](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35181115566) |
| RPF-27 | Disposable Docker `--internal` 多服务拓扑复现了 baseline、latency/timeout、dependency-unavailable，以及下游 side-effect-success + response-lost/reconcile 语义。Toxiproxy 与窄 custom shim 的核心路径均五次通过；Envoy delay/abort 可行但结果是 commit 前 abort。首次全候选 hosted 尝试在 disposable verifier 失败；将 hosted workflow 明确收敛到选定的 Toxiproxy 路径后，完整场景合同与三次 response-loss 在 [run 35186899267](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35186899267) 通过。 | `spikes/rpf-27/`；本地 ignored candidate result；[首次 hosted run 35185942172](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35185942172)；[成功 hosted run 35186899267](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35186899267) |
| RPF-28 | 在不替换单容器路径的前提下，正式接入 `multi-service-toxiproxy-v1` Environment。fresh internal network 中的 target/dependency/Toxiproxy/Agent-shaped client 通过 baseline、latency/timeout、dependency-unavailable、side-effect 前失败和真实 response-lost-after-side-effect，证明 receipt/effect-count reconcile 与 no blind retry；8 项 negative control 覆盖错误 activation、proxy 丢失、receipt 缺失、effect count 重复、blind retry、reconcile 不可用和 cleanup quarantine；独立 PostgreSQL/Control Plane/durable-worker smoke 也完成 canonical completion；最终 focused hosted baseline/response-loss/cleanup workflow 与 negative-control verifier 也已通过。 | `spikes/rpf-28/`；三份 RPF-28 reviewed Run artifact；本地完整重复与 negative-control 结果；[hosted run 35195998367](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35195998367) |
| RPF-29 | Disposable OpenTelemetry candidate 将 Java durable Job/Attempt、Python worker/Agent/tool、RPF-28 Toxiproxy target/dependency 与 reconcile 通过 W3C propagation 和 allowlisted canonical-ID baggage 关联。Windows fresh evidence 覆盖 baseline、response-lost、missing propagation、Collector failure、敏感字段/cardinality 检查、定向 overhead 与 cleanup；canonical evidence 保持独立。当前快照时 focused hosted verification 尚待交付后运行。 | `spikes/rpf-29/`；本地 source identity `2acfb4d544fbd1dfdf3a8fbcb9dab3aaa74a76dbc5a51e7f9ed1150551dc9a6a`；hosted workflow `.github/workflows/rpf-29-otel-spike.yml` |

## 交付事实

- 仓库身份是公开的 `MyKr-YSteinsK/runproof`，交付分支为 `main`。
- Hosted Release Gate 成功代表 CI/evidence delivery，不是 Production release；现有 workflow 没有 release/deploy 步骤。
- 历史 RPF-25 gate 上传了脱敏 result 和 Summary mirror；artifact digest 为 `sha256:6a8496d4eb12136000f664b4cc90ca17b455a3e07bf4e36c5c732a050a3e0fd8`。
- 这些里程碑没有创建 tag、产品 release、托管云账号，也没有执行真实 Production deploy。

## 兼容性与证据规则

- 历史 reviewed bytes 不可变。新的 source identity 必须显式 refresh 并审查，不能静默替换旧 corpus。
- source/reproduction/focused Run ref、artifact hash、schema identity 和 verifier identity 仍是 evidence contract 的一部分。
- `UNKNOWN_OUTCOME` 必须有 reconcile evidence；`ERROR`/`INVALID`/`INCONCLUSIVE` 不能静默计入 Agent quality。
- 浏览器证据在有说明时是 desktop/in-app representative evidence；不能据此推断真实设备验证。
