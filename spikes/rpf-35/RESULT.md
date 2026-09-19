# RPF-35 Result — bounded Canonical Metadata read model

Status: Local proof complete; hosted focused proof and canonical gate pending.
Lifecycle remains `Stabilization`; no Release authority, historical reviewed
artifact bytes, Production deployment, or release/deploy action changed.

Local result: `.local/rpf-35/final-local-v2/run-2a2efebe5a/rpf35-result.json`
with source identity `ad829f15de5e513d6c9278cbfa390ae27ab2d580761f6fe435bc5d2444d05cf0`.
The offline verifier passed with 13,502 metadata rows, 2 SQL statements and
139,940 bytes for the 100-row page, zero list artifact-body reads, one verified
15,202-byte detail artifact read, and 10,002 concurrent rows without duplicate
cursor results. Hosted run and gate links will be added after remote delivery.

This file summarizes the current delivery rather than acting as a second
mutable evidence corpus; the JSON result and offline verifier are authoritative.

## Boundary

- `/metadata` is bounded to default 50 and hard maximum 100.
- The `rpf-metadata-cursor-v1` cursor is opaque, versioned, and bound to
  entity type, ordering, and page size; it uses keyset predicates rather than
  `OFFSET`.
- List DTOs return registered metadata and ArtifactRef identity only.
  `verify=false` is explicit for metadata-first detail loading; the artifact
  endpoint remains the verified full-body authority.
- API-mode Web pages use route-scoped first-page/detail loaders. Overview uses
  fixed Golden Demo references and does not crawl metadata history.

## Limits

This is a current-repository regression budget, not a Production SLA. The
probe records SQL count, payload bytes, artifact-body reads, cursor traversal,
and EXPLAIN plans. Local/S3 detail compatibility and hosted evidence must be
reported from the actual verification runs; no unperformed browser or
real-device check is promoted to PASS.
