# RPF-34 Result

The result is produced by `probe.py` into ignored `.local/rpf-34/` or hosted
`ci-results/rpf34/` output and must be checked by `verify-evidence.py`.

The committed implementation contract is:

- History summary default/max: `50 / 100`;
- History keyset order: `created_at,job_id:asc`;
- Timeline default/max: `200 / 500`;
- Timeline keyset order: `event_id:asc`;
- cursor envelope: opaque, versioned `rpf-execution-cursor-v1`, bound to
  discovery mode/filter/order/page size;
- detail reads Attempts/Operations/Evidence but advertises a partial,
  independently paged Timeline;
- Worker eligible discovery remains a bounded candidate summary and fetches
  canonical detail only for reconcile handling.

RPF-34 is a Stabilization read-path change. It does not make a Production
capacity/SLA claim, promote the RPF-33 candidate index, or authorize release or
deploy.

The final local full proof passed with source identity
`41e006832931d362ef2c9fe7da95ca019a3b4ab76cc8db42eb0e53ae407a30e5` at
`.local/rpf-34/final-local/run-8e1c3bf960/rpf34-result.json`: 10,001 Jobs,
60,000 Events, 2 SQL statements for History pages 1/50/100, 36,896 bytes for
the 100-row summary page, 2 SQL statements and 66,795 bytes for the largest
Timeline page, zero duplicate/omitted rows under concurrent insertion, and
exact disposable cleanup. The offline verifier also enforced the redacted
security boundary.

Desktop browser observation used the disposable `--hold-web` mode and confirmed
History page 2/Previous, direct detail deep-link, 200-event Timeline first
page, incremental loading to 400 events, and locale switching. Real-device
verification was not executed.
