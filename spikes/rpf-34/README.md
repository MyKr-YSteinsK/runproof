# RPF-34 — bounded Execution read model

This disposable proof validates the RPF-34 read-path contract against a fresh
formal PostgreSQL Control Plane:

- 10,000 history Jobs plus a 10,000-event Timeline Job;
- 50,000+ fixture Events;
- one SQL-backed summary page for History instead of per-row full snapshots;
- opaque versioned keyset cursors bound to filters, ordering and page size;
- an independent bounded Event Timeline endpoint;
- concurrent insert, malformed/incompatible cursor, empty/end/not-found,
  payload, SQL-count and EXPLAIN evidence.

It does not refresh reviewed corpus, add the RPF-33 candidate index, run a
broker, stream artifacts, or perform Production/release/deploy actions.

## Local proof

```powershell
mvn.cmd -q test package -f control-plane/pom.xml
python spikes/rpf-34/probe.py --run --output-dir .local/rpf-34/local
python spikes/rpf-34/verify-evidence.py .local/rpf-34/local/run-<id>/rpf34-result.json
```

The probe owns only `rpf34-*` PostgreSQL resources and writes ignored output.
Generated credentials never enter the result. Real-device verification is not
claimed; desktop/browser observation is a separate QA oracle.

For a disposable API-backed desktop observation, add `--hold-web`. The probe
prints a local `/executions` URL and waits for Enter before exact cleanup:

```powershell
python spikes/rpf-34/probe.py --run --hold-web --output-dir .local/rpf-34/browser
```
