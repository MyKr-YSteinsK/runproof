# RunProof Verification History

[English](VERIFICATION_HISTORY.md) | [简体中文](VERIFICATION_HISTORY.zh-CN.md) | [Current State](../project/CURRENT_STATE.md)

This is a compact historical ledger of material verification facts. It keeps source identities, hosted runs, milestone probes, and compatibility boundaries without copying command transcripts or `TASK_RESULT` files. The current snapshot remains in [CURRENT_STATE.md](../project/CURRENT_STATE.md).

## Milestone evidence

| Milestone | Material fact | Evidence anchor |
|---|---|---|
| RPF-01 / RPF-02 | Disposable Agent contract and Controlled Environment prototype boundaries were checked; Docker evidence is prototype-level, not Production isolation. | `spikes/rpf-01/`, `spikes/rpf-02/`, fixed reviewed evidence |
| RPF-03 / RPF-04 | First stateful Run slice connected a real DeepSeek tool loop to Docker state, response-loss reconciliation, Run Evidence, State Diff, and a read-only Web surface. | `runtime/`, `web/`, reviewed RPF-03/RPF-04 artifacts |
| RPF-05 / RPF-06 | Agent `FAIL`, platform/environment `ERROR`, Failure Case reproduction, Regression promotion, and focused rerun became separate evidence domains. | `runtime/`, reviewed Failure/Regression corpus |
| RPF-07 / RPF-08 | Deterministic Evaluation Suite, Baseline/Candidate Comparison, Quality Policy, Gate, and decision-only Release Decision were established. | RPF-07 reviewed source `c607e5e38015c99fedcbba3efbcdc20834953f2fec7543313ead3ce0211d3adf`; RPF-08 reviewed source `d6313e5849b2662d9badafa7be25d568e84ab6cc4912c9587495a5f9427bfd69` |
| RPF-09 / RPF-10 / RPF-11 | Lifecycle moved from Prototype to Stabilization; H2 and real PostgreSQL candidates established the persistence, artifact, API, service-authority, and formal Control Plane boundaries. | `spikes/rpf-09/`, `spikes/rpf-10/`, `control-plane/` probes |
| RPF-12 | Fresh PostgreSQL + formal Control Plane + durable evaluation ran on a GitHub-hosted runner with canonical Decision read-back and redacted artifacts; no release/deploy. | [hosted run 34742919966](https://github.com/MyKr-YSteinsK/runproof/actions/runs/34742919966) |
| RPF-13 / RPF-14 | PostgreSQL poll/claim/lease, fenced attempts, operation identity, response-loss reconciliation, artifact recovery, and the formal Python durable worker were verified. | RPF-14 source identity `810bf15c8ec6a34c7961ab8333fca7378534416675baf0c6eaf08ff3b3a43412`; `control-plane/` probe and evidence verifier |
| RPF-15 | Candidate A production-like replacement, PostgreSQL dump/restore, artifact backup/restore, active-job reconcile, secret rotation, and explicit-release boundary were verified; Candidate B remained a structured target comparison. | RPF-15 source identity `2cbcbc7934658009a22808c8b9e965f5395c362601a409878905c96152523f64`; `PRODUCTION_LIKE_PROBE_ONLY` |
| RPF-16 | A second explicit Incident Remediation Agent exercised local, external-dependency, response-lost, Failure Case, Regression, independent Suite/Gate, and formal durable-worker paths. | RPF-16 source identity `4569575d4a34853e5c85681dbac6576a8bf3a1252fc4cc34e8691c2378e8f494`; `spikes/rpf-16/` verifier |
| RPF-17 | Deterministic attribution, first divergence, exact/structural grouping, cross-Agent family, negative controls, and fail-closed Version Bisect were verified without LLM/embedding/ML. | RPF-17 source identity `9654c309b427de8da42192f2cda79383c257a7680b46ce4ca2098feafc19dad6`; `spikes/rpf-17/` verifier |
| RPF-18 | Controlled Stable, Flaky, Safety, and Evidence-poor statistical cohorts, Wilson intervals, denominator separation, safety precedence, Failure Intelligence links, and PostgreSQL Trial Jobs were verified. | `spikes/rpf-18/`, reviewed statistical corpus, [hosted run 34942385897](https://github.com/MyKr-YSteinsK/runproof/actions/runs/34942385897) |
| RPF-19 | Versioned Golden Demo profile, two Agents, idempotent seed, API-backed Overview, evidence deep links, and local start/stop/restart lifecycle were verified. | `demo/rpf-19-golden-demo-v1.json`, `demo/verify-golden-demo.py`, [hosted run 34947014281](https://github.com/MyKr-YSteinsK/runproof/actions/runs/34947014281) |
| RPF-21 / RPF-22 | Fresh PostgreSQL and canonical gate trust chain were restored; eligible discovery starvation, artifact containment, single-read verification, and writer/verifier authority were hardened. | [hosted run 35071819220](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35071819220), [hosted run 35077060386](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35077060386) |
| RPF-23 | Windows child environment, worker path containment, process/session identity, rollback, ownership labels, restart, and fail-closed cleanup were verified. | `demo/verify-lifecycle.ps1`; current Windows local lifecycle evidence |
| RPF-24 / RPF-25 | Web canonical truth and minimal module boundaries were preserved while presentation-only `en-US`/`zh-CN` i18n, raw-status traceability, locale persistence, and API-unavailable behavior were verified. | RPF-25 implementation `d2571754c89e50564084cafc369cccf477650133`; [hosted run 35179169378](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35179169378) |
| RPF-26 | Bilingual public docs, current/history Project-State split, public local-link/semantic/command/secret-path verifier, and CI integration were delivered without product behavior changes. | Implementation `e17745396bf58e54465d82a4b5cc0758c648bfa6`; [hosted run 35181115566](https://github.com/MyKr-YSteinsK/runproof/actions/runs/35181115566) |
| RPF-27 | A disposable Docker `--internal` multi-service topology reproduced baseline, latency/timeout, dependency-unavailable, and downstream side-effect-success + response-lost/reconcile semantics. Toxiproxy and the narrow shim passed the five-repeat core path; Envoy delay/abort was feasible but abort-before-side-effect, so formalization remains conditional on hosted evidence. | `spikes/rpf-27/`; local ignored candidate result; hosted candidate workflow pending |

## Delivery facts

- The repository identity is `MyKr-YSteinsK/runproof`, public, with `main` as the delivery branch.
- Hosted Release Gate success is CI/evidence delivery, not a Production release. Existing workflows have no release/deploy step.
- The latest historical RPF-25 gate uploaded a redacted result and Summary mirror; the artifact digest was `sha256:6a8496d4eb12136000f664b4cc90ca17b455a3e07bf4e36c5c732a050a3e0fd8`.
- No tag, product release, managed cloud account, or real Production deploy was created by these milestones.

## Compatibility and evidence rules

- Historical reviewed bytes are immutable. A new source identity requires an explicit refresh and review; it cannot silently replace an older corpus.
- Source/reproduction/focused Run refs, artifact hashes, schema identity, and verifier identity remain part of the evidence contract.
- `UNKNOWN_OUTCOME` requires reconcile evidence; `ERROR`/`INVALID`/`INCONCLUSIVE` are not silently counted as Agent quality.
- Browser evidence is desktop/in-app representative evidence where stated. Real-device verification is not implied.
