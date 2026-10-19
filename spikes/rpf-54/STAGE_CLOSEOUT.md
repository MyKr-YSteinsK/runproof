# RPF-54｜阶段证据收口

## 范围与接受来源

本报告审计的 feature 链基线为 `05b8c324fab376a23926b97a73e0fde6523ae373`。RPF-54 Plan 声明 Main/Development Architect 已接受下述历史成果的限定证据，尤其明确接受 RPF-53 rev-6。本报告将其标作 `ACCEPTED_LIMITED（既往接受由当前 Plan 转述）`；本轮重新验证的是可取得的内容、来源和边界，不重新授予产品证书。

RPF-54 这份新收口包的 `EVIDENCE_ACCEPTED=PENDING_ARCHITECT_REVIEW`，`STAGE_ADVANCED=NOT_DECIDED`。远端 main 仍为 `bda0cd49e50e3181f604324e94877a24b9885334`，其 Project State 主要记录 RPF-00～39；后续竞赛 feature 链未合并。本轮没有修改这些 canonical 文件。

| CURRENT STATE（本轮核验） | TARGET INTENT | PLANNING CONTEXT |
|---|---|---|
| 订单真实 Explorer→确定性 Target 的反馈选择已有特定证据；配置真实 Target→Java HTTP→Witness 已完成；两个主体未联合运行 | PGE×真实跨域 Target，冻结三合同、真实 fault activation、可核验反馈与有限对照 | 本地可读 RPF-54 Plan 自包含授权；历史 Plan/Result 说明当时意图，不能代替本轮实际文件或运行 |
| 公开 Witness 可离线核验；RPF-42 原会话和 RPF-46 完整会话未在允许的 tracked 入口取得 | 独立复现、可信 Issuer/数据库权威、受控真实 Lab | 不读取旧 `.local` 填补缺口；不将聊天或摘要提升为完整轨迹 |

**阶段判断：真实 Provider Target 跨域证据这一有限环节已完成。** 这不等于全部 EffectWitness CORE/MUST 完成；仍缺少 PGE 与真实外部 Target 的联合故障探索、配置侧激活证据、干预归因、独立复现及生产认证。

## 固定证据索引

以下字节数与 SHA 均来自当前工作树，并与上述精确 Parent 的 Git blob 核对。`commit` 是文件最后修改提交，非所有实验的运行源码版本；运行版本区别见后文。8 个有独立入口的证据 verifier 在本轮实际运行，全部 exit 0。报告/研究摘要的哈希核对不冒充完整会话验证。

| 成果 / tracked artifact | bytes | SHA-256 | commit / 本轮检查 |
|---|---:|---|---|
| [RPF-42 RESULT](../rpf-42/RESULT.md) | 16171 | `1c20893315a66041b1f9bf7091d548acf320febe724d99621f95264c659a32b9` | `6370775dd`；报告与源码核对，原会话未重验 |
| [RPF-43 Witness](../rpf-43/sample-witness.json) | 9257 | `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e` | `238037a0b`；`witness_verify` exit 0 |
| [RPF-44 ops Witness](../rpf-44/sample-ops-witness.json) | 10123 | `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873` | `1d2095bc2`；`witness_verify` exit 0 |
| [RPF-46 research summary](../rpf-46/session-report.json) | 21394 | `8a72de3458089a9c71a5aa244e8425f5fb625538ee99dd3de71b5a21c44919db` | `27dab792b`；摘要结构/来源核对，完整 session 不可派生 |
| [RPF-48 Target summary](../rpf-48/target-agent-summary.json) | 10257 | `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2` | `8241ebb1a`；`target_evidence` exit 0 |
| [RPF-49 recovery summary](../rpf-49/recovery-summary.json) | 13399 | `04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b` | `e0d1c805a`；`target_recovery` exit 0 |
| [RPF-50 failure Witness](../rpf-50/violation-witness.json) | 10242 | `b8f288db5dd76a142bbfb69a04d15ce9206d2cd9dbe28ef6effdb59382f5ef4a` | `b3271eaaf`；`violation_witness` exit 0 |
| [RPF-51 rev-4 HTTP Witness](../rpf-51/rev-4/config-http-witness.json) | 13609 | `c569bd62a6691c84e8995359578fc4ff34f0ea417158a0c0893309c029df363d` | `151922a9b`；`config_http_witness` exit 0 |
| [RPF-52 rev-3 Fixture Evidence](../rpf-52/rev-3/config-target-fixture-evidence.json) | 19042 | `2bbc002e5a83dabc4aa9b9ddfea733532ef8b29f789181a19debb7ed9437eb27` | `3dfafb7fc`；`config_target_verify` exit 0 |
| [RPF-53 rev-6 Live Witness](../rpf-53/rev-6/config-live-evidence.json) | 21170 | `f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43` | `6fb77e53a`；当前 offline CLI=`0/2/3` |

RPF-53 的新鲜 CLI 使用 Plan 已固定的外部锚，correct/missing/wrong=`0/2/3`。Envelope 的 Verifier LF 身份 `75fa9329f8773279801b6e5c3165fe0bd8fc22ead60f7001f6c885827f8d0282` 与本轮未修改源码一致；四类 rehashed tamper 的历史 exit 4 记录在 [rev-6 diagnostic](../rpf-53/rev-6/verification-diagnostic.json)。本轮另有跨 namespace/rehashed 负控，不重跑业务。

## 五个证明维度与来源等级

每行的接受状态仅为上述既往 `ACCEPTED_LIMITED`。未建立项保持 `NOT_ESTABLISHED`；未取得的完整原轨迹标为 `UNAVAILABLE_FOR_THIS_AUDIT`，不因此否定历史运行。

| 成果 / 来源 | EXECUTION / EXPERIMENT | EFFECT | FAULT ACTIVATION | ATTRIBUTION | REPRODUCTION / 未证明 |
|---|---|---|---|---|---|
| 42：REAL_PROVIDER Explorer + DETERMINISTIC_TARGET | 报告记载真实 DeepSeek normal→response-lost、精确反馈回注，PGE/B0 先预注册 | 四个 SQLite trial 均满足 CNY2500 全额退款及唯一收据 | PGE response-lost 触发/观察/调和；B0 有 planned-untriggered 负控 | `CORRELATIONAL_ONLY`；案例 L2，B0/ PGE 物理上限相同、Provider 费用不同 | 原 live-result 仅有报告哈希，不读旧 local；无普遍优势、统计显著或无反馈反事实 |
| 43：REVIEWED anchored / DETERMINISTIC_TARGET | 独立捕获的订单 Witness v1，session_reference=`DETERMINISTIC_CAPTURE` | 只读 SQLite Reader before/after、收据、Oracle | 受控 post-commit response-loss=`TRIGGERED` | `CORRELATIONAL_ONLY`，不是 Explorer 再运行 | `NOT_TESTED`；签发者无签名，无原 Provider 会话 |
| 44：REVIEWED anchored / DETERMINISTIC_TARGET | SQLite order/ops 的共享源码/Orchestrator/feedback；本次公开 ops 样本 v2 | Ops apply 持久化与 Reader/receipt 核验 | 同类受控丢回复及 reconcile | `CORRELATIONAL_ONLY` | 无任意 HTTP backend registry；未新增两域业务试验 |
| 46：REAL_PROVIDER Explorer + DETERMINISTIC_TARGET / REPORT | 新订单 PGE 的服务器/浏览器切片，normal→response-lost；报告对应 checkpoint `27dab792b` | 摘要含状态、收据摘要、feedback、事件关联 | 摘要报告第二轮 `TRIGGERED` | 有限机制证据，无 B0 反事实 | 发布的是 `rpf46-research-summary-v1`，缺完整 plan/contracts/events；不能交给完整 `verify_session` 当原 Envelope |
| 48：REAL_PROVIDER Target / anchored content | 真实 Pydantic AI Tool loop，inspect→refund，来源为 Target 而非 Explorer | 订单 SQLite 读回、唯一收据 | 正常运行，无故障触发主张 | 单次已观察业务过程 | 内容锚不证明 OS 级进程认证、Issuer 或一般可靠性 |
| 49：REAL_PROVIDER Target + CONTROLLED_FAULT | 真实模型收到 UNKNOWN 后自行 reconcile_order，call/return lineage 可核验 | 单笔退款/收据满足，无重复 mutation | response-lost planned/triggered/observed/reconciled | `AGENT_RECOVERY_VERIFIED` 的限定内容核验；非通用因果优势 | 独立复现未测试；物理 owner 与逻辑合同 owner 分别保存 |
| 50：CONTROLLED_FAULT / DETERMINISTIC | 预注册正常控制与已知缺陷注入，非模型探索 | failure Witness 确认受控退款规则违规 | 具体已知缺陷生效，由 before/after/receipt 支持 | 限定已知干预与控制，不推导真实模型自主发现未知漏洞 | 独立复现、生产真实性未建立 |
| 51 rev-4：独立 Java 服务 / 无 Target Agent | Java17/H2 的真实 HTTP 操作 | 11 条业务 HTTP；未授权 403、stale version 409、最终 v2/[2,1] | API 预期拒绝已观察；不等于 PGE fault intervention | 同服务 GET + 独立确定性 Oracle；不是数据库级独立认证 | 无 LLM Target、Explorer、生产凭据或独立复现 |
| 52 rev-3：真实 SDK + FIXTURE / Java HTTP | scripted SDK 三工具，4 completions；无 Provider | 8 条 HTTP、2 POST、v2/[2,1] | 没有新 fault activation 证明 | Fixture 的协议与 HTTP Effect 证据 | 不能标成模型自主决策 |
| 53 rev-6：REAL_PROVIDER Target / Java HTTP | DeepSeek+固定 SDK，3工具、4请求、完整可见性/回注/来源 | 8条 HTTP、2 POST，`rpf53-v2/version 2/history [2,1]` | 合同和 Witness 无 fault/session/candidate 激活链；投影保守为 `UNKNOWN` | `CONTRACT_SATISFIED_IN_RUN` 的限定事实，不引入干预归因 | Issuer/数据库独立权威未建立；独立复现 `NOT_TESTED`，配置 PGE 未证明 |

RPF-43 的订单 v1 与 RPF-44 的 ops v2 由同一离线入口分派，但不是同一 schema。RPF-44 `cross_core` 的双域能力由源码及历史已接受结果支持；本轮不从 RPF-46 摘要重造缺失的 v2 order Witness。

RPF-42 报告引用的原运行源码/会话摘要与 RPF-46 checkpoint 都是历史身份；当前代码通过纯协议测试不表示重新执行过对应真实 Provider。重新验证同一份 Witness 也不属于独立 reproduction。

## 下一边界

共同可提取的最小事实为：合同/运行身份、经验证的业务 outcome、authority 摘要引用、来源级别、已记录 fault flags 及不可越级的研究限制。订单 Receipt 与 HTTP history 不应归并成同一种权威；Config 缺 receipt 时保持 null，缺 fault/session 时保持未知或不可派生。

现有 evidence 不支持直接声明 `PGE×REAL_PROVIDER_CONFIG_TARGET` 已联动，也不能从两个相互独立的旧成功运行拼出新的实验。下一项推荐及边界见 [EXTENSION_ASSESSMENT.md](EXTENSION_ASSESSMENT.md)。
