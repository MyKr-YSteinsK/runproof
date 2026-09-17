# RunProof 架构

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md) | [README](../README.zh-CN.md)

本文描述当前有证据支持的架构边界。它是产品地图，不是对所有推荐 Production 组件已经部署的承诺。

## 架构一览

```text
User / CI
    → Desktop Web Control Plane
    → Java / Spring Control Plane
    → PostgreSQL canonical metadata
    → Durable Job
    → Python Worker
    → Controlled Simulation Environment
    → Run / Trajectory / State Diff / Evidence
    → Quality Policy 与 Release Gate
    → Release Decision（只读决策）

Provider boundary ── Agent run 的可选输入；Golden Demo 不依赖它
Immutable Artifact Store ── 由 Control Plane 引用的经验证据字节
```

主路径通过正式 Control Plane 使用 HTTP/JSON。浏览器不连接 PostgreSQL，不持有 worker 或 decision credential；canonical API 不可用时也不会静默回退到 fixture data。

## 组件与 ownership

| 组件 | 当前职责 | 权限边界 |
|---|---|---|
| Desktop Web Control Plane | 只读 Overview、调查、比较、执行和决策页面 | 仅 presentation；不发起 live Agent、worker、promotion、release 或 deploy mutation |
| Java/Spring Control Plane | canonical metadata、经验证 artifact 注册/回读、durable Job API 和 decision history | service principal 有范围；decision writer 与 Agent/worker 执行分离 |
| PostgreSQL | canonical metadata 与 durable Job/Attempt/Operation/Event 状态 | 当前正式 transport 是有界 poll/claim/lease；不等于 broker 或 HA 结论 |
| Immutable Artifact Store | 保存经过 schema、kind、identity、source、hash 验证的 evidence bytes | candidate writer 不能创建 canonical verified/release authority |
| Python Agent/Evaluation Runtime | Agent contract、受控评测、evidence、regression、统计和 HTTP client | 不把 Provider credential 或 release authority 暴露给 Web |
| Durable Worker | claim、heartbeat、reconcile、执行显式 profile、报告 evidence | `UNKNOWN_OUTCOME` 必须先 reconcile；worker 不能写 Release Decision |
| Controlled Simulation Environment | 为副作用 Tool 和 fault scenario 提供 fresh、可观察的有状态环境；RPF-28 正式路径可在 private network 组合 target、dependency、Toxiproxy 和 Agent-shaped client | 不连接真实 Production destructive credential；Agent 只能看到 data-plane boundary |
| Provider boundary | 可选的模型/provider 调用边界；DeepSeek 是首个参考 Provider | credential 不进入 Git、浏览器、evidence 或默认 trace |
| GitHub Actions Release Gate | fresh CI 检查、durable evaluation、canonical Decision read-back 和脱敏 artifact | CI 记录 evidence，不执行 release/deployment |

## Canonical 数据流

1. Agent、Scenario、Environment、Verifier 和 Evaluation identity 共同定义候选版本。
2. Control Plane 提交 durable Job；worker 使用 lease 和 fencing identity claim。
3. Agent 只在 Controlled Simulation Environment 内操作。既有单容器路径继续支持；RPF-28 正式路径使用 fresh Docker `--internal` network，并把 fault activation/observation 保留在 Environment adapter 内。可观察 action、transition、receipt、fault provenance 和 verification fact 成为 Run/Evidence 记录。
4. Control Plane 保存 canonical metadata，只接受经过验证的 immutable artifact 引用。
5. Failure investigation 可以派生 Failure Case、Regression、Failure Intelligence、Statistical Evaluation 和 Comparison，但不能改写源 evidence。
6. Quality Policy 产生 Gate 和 Release Decision。`ELIGIBLE` 是只读决策结果，不是 release command。

## Authority 与恢复边界

- Agent 和 worker 的 authority 小于 decision-writer authority。
- `PASS`、`FAIL`、`ERROR`、`INVALID`、`INCONCLUSIVE`、`CANCELLED` 是执行结果；Release Decision 属于独立状态域。
- 可能发生副作用后丢失响应时进入 `UNKNOWN_OUTCOME`，随后进入 `RECONCILE_REQUIRED`；必须先用 environment receipt/state 证明，再决定是否 retry。
- 历史 Run、Evidence、Regression 和 Decision 采用 append-only 或 superseding；后续解释不能静默改写旧字节。
- Web/API 故障采用 fail-closed；缺失或未验证 artifact 不会被静态成功 fixture 替代。

## 仓库地图与 README 审计

| 区域 | 其 README 的用途 | 公共架构入口 |
|---|---|---|
| `control-plane/README.md` | Java 构建、服务启动、API 与 worker 实现细节 | 本文和 [DEMO.zh-CN.md](DEMO.zh-CN.md) |
| `runtime/README.md` | Python runtime/evidence/evaluation 入口与合同 | [RELIABILITY_MODEL.zh-CN.md](RELIABILITY_MODEL.zh-CN.md) 和 [GLOSSARY.zh-CN.md](GLOSSARY.zh-CN.md) |
| `web/README.md` | Web adapter、read model 和 presentation 实现 | 本文和 [DEMO.zh-CN.md](DEMO.zh-CN.md) |
| `spikes/*/README.md` | disposable 调查与历史 probe 边界 | [VERIFICATION_HISTORY.zh-CN.md](history/VERIFICATION_HISTORY.zh-CN.md) |
| `demo/` | Golden Demo profile、seed、生命周期和 verifier | [DEMO.zh-CN.md](DEMO.zh-CN.md) |
| `docs/project/` | canonical governance 和当前 Project State | [README](../README.zh-CN.md) |

模块 README 保持 implementation-facing。公共声明集中在本文及配对公共文档中；没有任何模块 README 被提升为第二个 Project-State authority。

## Claim → evidence 映射

| 声明 | 证据位置 | 验证入口 |
|---|---|---|
| Durable execution 与 response-loss reconciliation | `control-plane/`、RPF-14 reviewed execution artifacts、response-lost Run | `python control-plane/probe.py`；RPF-14 evidence verifier |
| 两个显式 Agent contract | RPF-16 reviewed Agent-bearing corpus 与 `runtime/` contracts | `python spikes/rpf-16/probe.py --verify` |
| 确定性 Failure Intelligence 与 Version Bisect | RPF-17 reviewed artifacts 与 `spikes/rpf-17/` | `python spikes/rpf-17/verify-evidence.py` |
| Statistical Reliability 边界 | RPF-18 reviewed statistical artifacts | `python spikes/rpf-18/verify-evidence.py` |
| API-backed、只读 Web | `web/src/data/`、`control-plane/`、reviewed corpus adapters | `npm test`；`npm run typecheck`；`npm run build` |
| 双语 Control Plane presentation | `web/src/i18n/`、locale-aware view model 与 RPF-25 compatibility tests | Web tests/typecheck/build；locale/API-unavailable checks |
| Hosted canonical Release Gate | `.github/workflows/release-gate.yml`、`ci/run_release_gate.py` | GitHub-hosted workflow 和 Job Summary contract |
| Golden Demo integrity 与生命周期 | `demo/rpf-19-golden-demo-v1.json`、`demo/verify-golden-demo.py`、lifecycle verifier | `python demo/verify-golden-demo.py --root . --json` |
| 正式多服务网络故障 | RPF-28 reviewed baseline/dependency/response-loss Run、`multi-service-toxiproxy-v1` 与 durable-worker focused result | `python spikes/rpf-28/probe.py --run`；`python spikes/rpf-28/verify-evidence.py .local/rpf-28/rpf28-formal-result.json` |

source identity、hosted run 和历史兼容性事实统一保存在 [VERIFICATION_HISTORY.zh-CN.md](history/VERIFICATION_HISTORY.zh-CN.md)，不重复塞入 current snapshot。

## Production 边界

当前仓库证明了 Controlled Simulation、正式 fresh 多服务网络故障 Environment、本地 production-like persistence/recovery、显式 PostgreSQL durable workflow、immutable evidence、hosted CI 检查和 Windows 本地 Golden Demo 生命周期。但它没有证明或授权 Production HA、托管云部署、object-storage durability、多主机 supervisor、human Approval、tenant/RBAC identity 或真实破坏性 remediation。

下一架构边界应从测量需要中选择：OpenTelemetry-compatible observability、托管或 S3-compatible artifact storage、capacity/large-trace evidence。这些是调查方向，不是自动加入当前架构的组件。
