# RPF-33 Result — Capacity and Large-Trace Investigation

Status: Complete as a disposable Investigation / Spike. Lifecycle remains `Stabilization`; no canonical schema, reviewed corpus, Release authority, Production deployment, or formal optimization was changed.

## Evidence

- Source identity: `1b68ba18e836845536d86ebaece80e7cb3b5fb8d0b6ef3b80a383c2ef7cbb0c1`
- Local Full: `.local/rpf-33/final-local-v5/run-ada0296cd7/rpf33-result.json`
- Hosted Medium: `.local/rpf-33/final-hosted-v7/run-a2fcc6c9de/rpf33-result.json`
- Both results passed `spikes/rpf-33/verify-evidence.py` with `historical_bytes_unchanged=true` and exact disposable cleanup.

## Measured boundary

| tier | Jobs | tier Events | canonical/artifact rows | `/metadata` | per-Run timeline |
| --- | ---: | ---: | ---: | --- | --- |
| Small | 100 | 1,000 | 275 | 441,533 B / 1,492 ms | 100 Events, 14,630 B / 41 ms |
| Medium | 1,000 | 10,000 | 1,700 | 2,688,980 B / 4,970 ms | 1,000 Events, 141,533 B / 56 ms |
| Large | 10,000 | 50,000 | 13,500 | 21,022,347 B / 32,425 ms | 10,000 Events, 1,409,521 B / 84 ms |

The cumulative fixture contained 10,003 Jobs and 66,100 Events. Eligible discovery was bounded to 100 returned Jobs, but the current snapshot path observed 502 SQL statements for the Medium/Large list because each returned snapshot reads related state separately. The disposable Large candidate index changed the canonical list plan from a parallel sequential scan (19.414 ms) to an index scan (2.471 ms); it was dropped after A/B measurement and is not a formal migration.

Worker concurrency 1/2/4 completed all submitted Jobs at 98.806 / 15.577 / 31.080 Jobs/minute. Claim race had one winner and three conflicts; lease reclaim produced Attempt 2. S3 direct and HTTP byte-array paths passed for 1 KiB, 1 MiB, and 16 MiB. Orphan growth was measured at 100/1,000/10,000 objects without deletion; the final count was 24,634 objects / 44,696,856 bytes and canonical reads remained available. OTel healthy exported 74 spans with zero failures; disabled exported zero; unavailable Collector produced 74 export failures while Jobs still completed. Metric labels did not contain canonical IDs.

## Decision gates

- `DB_OPTIMIZATION_REQUIRED=CONDITIONAL`
- `BROKER_REQUIRED=NOT_YET`
- `STREAMING_ARTIFACTSTORE_REQUIRED=CONDITIONAL`
- `GC_PLAN_REQUIRED=CONDITIONAL`
- `WEB_PAGINATION_REQUIRED=YES` from the separate desktop observation of the current 100-row unpaginated Execution list. The final non-hold JSON keeps this field `CONDITIONAL` because the manual hold was not embedded in that run.
- `WEB_VIRTUALIZATION_REQUIRED=CONDITIONAL`
- `RECOMMENDED_NEXT_PLAN=RPF-34`

Desktop/in-app observation confirmed 100 rendered list rows and no pagination controls. The 10,000-event timeline API was measured programmatically, but the automation frame limit prevented a trustworthy full-render assertion. Real-device verification was not executed.

## Recommended RPF-34 boundary

Introduce a bounded server-side read model/cursor contract for the Execution list and per-Run timeline, remove the measured N+1 snapshot shape, and set query/payload budgets. Re-evaluate formal indexes after that boundary; decide virtualization and artifact streaming from measured UI/heap budgets. Do not introduce a broker or real GC from this evidence alone.
