# RPF-17 Failure Intelligence probe

This disposable probe derives a deterministic, versioned Failure Intelligence
index from the reviewed RPF-05/RPF-06/RPF-16 corpus. It does not call an LLM,
does not mutate historical Run/Failure Case/Regression files, and does not
perform production remediation.

```text
python spikes/rpf-17/probe.py --build-reviewed
python spikes/rpf-17/probe.py --build-reviewed --refresh-reviewed  # only after reviewed source changes
python spikes/rpf-17/probe.py --verify
python spikes/rpf-17/verify-evidence.py
python spikes/rpf-17/probe.py --run
```

`--run` creates temporary `rpf17` PostgreSQL/Java resources and proves that
Failure Intelligence, Failure Cluster, and Version Bisect artifacts are
persisted and read through the formal Control Plane. Local output is limited
to the ignored `.local/rpf-17/` directory. The reviewed corpus is immutable
and contains five `rpf-failure-intelligence-v1` records, three
`rpf-failure-cluster-v1` records, and one `rpf-version-bisect-v1` record.
