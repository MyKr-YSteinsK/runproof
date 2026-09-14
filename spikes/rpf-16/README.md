# RPF-16 Incident Remediation Agent probe

This probe verifies the second real Agent adapter without live production
access. The Incident Remediation Agent uses a fresh process-local controlled
simulation and the same redacted `rpf-run-evidence-v2` boundary as the
Production Change Agent.

```powershell
python spikes/rpf-16/probe.py --build-reviewed
python spikes/rpf-16/probe.py --run
python spikes/rpf-16/verify-evidence.py
```

`--run` creates temporary PostgreSQL/Control Plane resources with the `rpf16`
prefix, submits one Incident Candidate Evaluation, executes the formal
PostgreSQL-polling durable worker, checks canonical job completion, and removes
the temporary resources. It does not perform release or deployment.
