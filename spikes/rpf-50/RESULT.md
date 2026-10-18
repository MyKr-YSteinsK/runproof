# RPF-50 TASK_RESULT

- **Plan:** `RPF-50/rev-1`
- **Status:** `COMPLETE`
- **Date:** 2026-10-18
- **Scope:** one fresh local SQLite normal control and one fresh local SQLite pre-registered known-defect trial; one strict offline-verifiable failure Witness.
- **Interpretation:** this proves detection of a pre-registered defect in a controlled deterministic service. It is not production vulnerability discovery, Target-Agent/Explorer behavior, independent reproduction, or issuer authentication.

## A-01 — Identity and scope: PASS

- Repository: `D:\CS\runproof`; branch `codex/rpf-50-controlled-violation-witness`; exact parent `166707838969ba907baacff501d4459497bec8e4`.
- Remote identity: `origin` → `https://github.com/MyKr-YSteinsK/runproof.git`; `main` was observed at `bda0cd49e50e3181f604324e94877a24b9885334` before work. The final fresh remote branch and `main` observations are reported in the task receipt.
- The starting tracked tree and index were clean. The pre-existing top-level `?? docs/reviews/` remained untouched; its contents were not enumerated or read.
- All tracked edits and additions stayed inside the Plan whitelist. Runtime regression copies were created under `.local/rpf-50/`, contained only `runtime/` and `spikes/`, and were removed after testing. No old `.local/rpf-48/49` data was accessed.
- No PR, merge to `main`, tag, release, deploy, public service, or competition submission was created.

## A-02 — Normal control: PASS

The existing `OrderSandbox.refund` executed once. A separate read-only `AuthorityReader` captured the actual before and after snapshots. The unchanged order Oracle returned `CONTRACT_SATISFIED_IN_RUN` with no violated rules.

| Identity | Value |
|---|---|
| Profile | `NORMAL_CONTROL_ORDER_SANDBOX_V1` |
| Run / environment | `rpf50-control-e43e778c4da947da9502b2c6429cd443` / `env-rpf50-control-e43e778c4da947da9502b2c6429cd443` |
| Order / operation | `order-rpf50-control-e43e778c4da947da9502b2c6429cd443` / `refund-rpf50-control-e43e778c4da947da9502b2c6429cd443` |
| Contract hashes (execution / effect / experiment) | `7c2cdf277762ae630cc547a4d1025797dc87f32cb353cbf6c381e47fcc945b86` / `fb3493ad0b6de4fd491bcfc01d93bc8810bf07ad0e5721054f45bf2592011f55` / `bab318b38f2051cb9c0a85bf802c21b29126bbddd5fb05719e439c32ab26edab` |
| Authority before → after | `PAID / refunded_minor=0 / revision=0 / 0 receipts` → `REFUNDED / 2500 / revision=1 / 1 committed receipt` |
| Receipt | `receipt-a31936e2b18b02848a05ba35`, amount `2500 CNY` |
| Oracle / cleanup / elapsed | `CONTRACT_SATISFIED_IN_RUN`, no violations / `RESET_AND_REMOVED` / `0.240097 s` |

## A-03 — Persisted known defect: PASS

The defect profile was frozen before either SQLite trial. Its one fixed transaction used `BEGIN IMMEDIATE`, checked the expected owner and initial order, inserted one committed full-amount receipt, and set the actual persisted order to `REFUNDED`, `refunded_minor=1250`, `revision=1`. The independent Authority readback and unchanged Oracle confirmed exactly `EXACTLY_ONE_FULL_REFUND_STATE`; evidence gaps were empty. `OrderSandbox.refund` and `evaluate_order_effect` were not modified.

| Identity | Value |
|---|---|
| Profile | `KNOWN_DEFECT_HALF_REFUND_COMMITTED_V1` |
| Run / environment | `rpf50-defect-c90f37db16ba47f99d7acdbd44a75e4c` / `env-rpf50-defect-c90f37db16ba47f99d7acdbd44a75e4c` |
| Order / operation | `order-rpf50-defect-c90f37db16ba47f99d7acdbd44a75e4c` / `refund-rpf50-defect-c90f37db16ba47f99d7acdbd44a75e4c` |
| Contract hashes (execution / effect / experiment) | `7c2cdf277762ae630cc547a4d1025797dc87f32cb353cbf6c381e47fcc945b86` / `b493e58f9955100c3035589f69fde83991604bc8ac92e979052461607e2f090b` / `79e6c62879d9e1334d70de2b03a82bac03d40dc30c01169440bab0ef977c0cb5` |
| Authority before → after | `PAID / refunded_minor=0 / revision=0 / 0 receipts` → `REFUNDED / 1250 / revision=1 / 1 committed receipt` |
| Transaction / receipt | committed; `receipt-3256311a3cd2ae07ca2d8549`, amount `2500 CNY`, revision `1` |
| Oracle / cleanup / elapsed | `VIOLATION_CONFIRMED`, `EXACTLY_ONE_FULL_REFUND_STATE`, no evidence gaps / `RESET_AND_REMOVED` / `0.077858 s` |

The two trials had different run, environment, order, and operation identities while sharing the same frozen business semantics. Each sandbox reported reset generation `1`, zero receipts after reset, and removal of its exact SQLite file and run directory.

## A-04 — Failure Witness: PASS

- Schema: `rpf-effect-violation-witness-v1`; source level: `CONTROLLED_DETERMINISTIC_SERVICE`; logical contract owner: `rpf-48`; physical storage owner: `rpf-50`.
- Failure dimensions separately state controlled business-service defect, activated and observed, `CORRELATIONAL_ONLY`, `NOT_TESTED` reproduction, `NOT_APPLICABLE` agent exposure/failure, completed run, and `NOT_ESTABLISHED` issuer authenticity.
- Only two JSON artifacts were produced: the normal control summary and the defect Witness. No SQLite database or provider artifact was placed in Git.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `spikes/rpf-50/control-summary.json` | 8,813 | `38c9d4e95ca04d5833ebffd25c0333e8180ba5eae2100efdb97d9b8165554559` |
| `spikes/rpf-50/violation-witness.json` | 10,242 | `b8f288db5dd76a142bbfb69a04d15ce9206d2cd9dbe28ef6effdb59382f5ef4a` |

The Witness hash is intentionally passed from a separate caller path to the verifier; the file contains no self-declared claim of issuer authenticity.

## A-05 — Independent offline verification: PASS

The following fresh Python process verified the actual Witness using the independently obtained full-file hash:

```powershell
py -3.14 -B -m runtime.runproof_runtime.effectwitness.violation_witness spikes/rpf-50/violation-witness.json --expected-sha256 b8f288db5dd76a142bbfb69a04d15ce9206d2cd9dbe28ef6effdb59382f5ef4a
```

It returned `VERIFIED_ANCHORED / VIOLATION_CONFIRMED`, exit `0`. The hash was obtained separately with `Get-FileHash -Algorithm SHA256` and supplied as a command argument. The missing-anchor case returned `UNANCHORED_INCONCLUSIVE / NOT_PROVEN`, exit `2`; the all-zero wrong anchor returned `REJECTED / NOT_PROVEN`, exit `3`. A subprocess import blocker also passed while forbidding SQLite, sockets, HTTP, SDK/provider modules, and the order/lab execution modules.

## A-06 — Adversarial controls and historical compatibility: PASS

The 11 focused tests cover wrong/missing anchors; rehashed false agent-failure, uncommitted-defect, activation, attribution, run/effect/profile and event claims; missing before/after snapshots; wrong/duplicate receipt; wrong owner; deleted/forged events; cleanup claims; and an old run identity presented as the new defect run. Recomputing the internal digest did not bypass the unchanged external anchor. Four previous artifacts retained their exact bytes and passed their existing anchored verifiers:

| Historical sample | Bytes | SHA-256 | Existing verifier |
|---|---:|---|---|
| RPF-43 Witness | 9,257 | `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e` | `witness_verify`, exit `0` |
| RPF-44 Ops Witness | 10,123 | `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873` | `witness_verify`, exit `0` |
| RPF-48 Target summary | 10,257 | `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2` | `target_evidence`, exit `0` |
| RPF-49 Recovery summary | 13,399 | `04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b` | `target_recovery`, exit `0` |

`git diff` and the index check both confirmed those historical spike directories remained unchanged. `python -B runtime/verify-reviewed-artifacts.py` also passed: reviewed Runs, Evaluations, Comparison, Policy/Gates/Decisions, and RPF-28 evidence all validated.

## A-07 — Regression, budget, and cleanup: PASS

- Focused: `py -3.14 -B -m unittest runtime.tests.test_effectwitness_violation -v` — 11 tests passed.
- Full Runtime regression: `py -3.14 -B -m unittest discover -s runtime/tests -p 'test_*.py' -v` from `.local/rpf-50/regression-src-4` — 200 tests passed; 2 Docker-dependent class setups skipped because the Docker provider was unavailable. Exit `0`.
- The full-suite mirror contained only archived `runtime/` and `spikes/` files plus the exact task changes. All four task-created mirrors and their archives, task-local temporary files, and Python cache were removed afterward.
- Actual pair: exactly 2 non-test trials, 14 business steps total, 0 Provider HTTP calls, 0 LLM tokens, cost `¥0`, no secret read, network, SDK, PGE, or Agent invocation. Pair elapsed `0.365888 s`.
- Both exact order sandboxes were reset, read back, and removed. `.local/rpf-50/runs/` is empty; no unresolved/quarantined database remains. Seven task-local plan, pair, result, and progress files are retained under `.local/rpf-50/` for audit, totaling `40,392` bytes. They are ignored local evidence and are not staged.

## A-08 — Code delivery: PASS

- `git diff --check` passed. The final source and artifact checks were limited to the Plan whitelist; secret-pattern scan found no credential material. Only explicit RPF-50 paths were staged.
- Delivery follows the Plan's focused-commit, ordinary-push, and fresh remote ref verification. Final commit and remote SHA are returned in the task receipt rather than embedded here, avoiding a self-referential RESULT update.
- No PR, `main` merge, tag, release, or deployment was performed.

## Source identity and technical decisions

The preflight SHA-256 is `36f04c7f5ed9aedf5318d65331796eac32d69ec54a51a57a302f500e0b582d3c`. The eight execution/verifier source files at both trial time and final review had the following exact byte identities:

| Source file | Bytes | SHA-256 |
|---|---:|---|
| `runtime/runproof_runtime/models.py` | 2,036 | `f5b9a2e1dc17ed8f923f721c52401f44ae814726e70cc5434596f7b9c1bc55b3` |
| `runtime/runproof_runtime/effectwitness/contracts.py` | 9,346 | `dad9f0f56d0533b28b6f02ae9a6b9dfad1cbc3f53bf70825b6f0c54ffdbf6d4d` |
| `runtime/runproof_runtime/effectwitness/effect_oracle.py` | 2,615 | `066f789e9b0044378ef896bd065df7b788ef27398163bac4acb63e898bd9c73c` |
| `runtime/runproof_runtime/effectwitness/orders.py` | 14,031 | `b28a00b9b43342ac6d85693aee0a5902aa60d4060446347a6f381a7de4b6d3ef` |
| `runtime/runproof_runtime/effectwitness/target_contracts.py` | 6,684 | `f22a4b49bcda7adfcd532205457f383c27062c3b5232bece61ac0fde6274ac78` |
| `runtime/runproof_runtime/effectwitness/violation_lab.py` | 26,532 | `679cd3f64ff34f881ce1881a5b9e63ff14df76bec43469db5028de1417e3970d` |
| `runtime/runproof_runtime/effectwitness/violation_witness.py` | 19,590 | `27331505730db46a8ad25f2de186973ac5afd4ce5eb3de7aea32f716c004513f` |
| `spikes/rpf-50/probe.py` | 2,377 | `61bed6d60f5c984e42fb82a143d6fc8d3898ae001eaef20dd8ac491460d403e0` |

The reused `TargetContracts` schema requires logical owner `rpf-48`; the additive path allowlist assigns only physical storage to `rpf-50`. The offline verifier lives in one new module and imports no business execution, database, SDK, or Provider module. The known defect is fixed SQL in the new lab and is not a configurable execution surface.

The first `--prepare` attempt stopped before preflight creation or SQLite work because the path guard was asked to accept the task root itself as a child path. The guard call was narrowed to a task-owned child path, and the probe's early error handling was corrected. Focused and full Runtime tests passed again before the successful freeze and pair run. A later test-only addition expanded cleanup/old-run adversarial cases; final tests passed without changing any execution/verifier source hash or rerunning either SQLite trial.

**FROZEN:** no scope, safety, Oracle, schema, or budget deviation. **RECOMMENDED:** reused the existing deterministic-reference contracts and a single Witness/verifier module. **DELEGATED_TO_CODEX:** implemented only the authorized whitelist. This branch result does not itself accept evidence on `main` or advance project stage; those remain Main decisions.
