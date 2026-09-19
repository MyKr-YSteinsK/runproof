# RPF-37 — Repository Closure Audit

RPF-37 is an audit-only checkpoint. It inventories the tracked tree, current
workflow surface, spike lifecycle, reference signals, duplicate bytes, and
generated-file hygiene so that a later RPF-38 cleanup can be small and
reversible. It does not delete, move, format, or regenerate reviewed evidence
and it does not change product behavior.

Run the standard-library-only inventory from the repository root:

```powershell
python spikes/rpf-37/audit.py --root . --output .local/rpf-37/audit.json
```

The output is local and ignored. The reviewed conclusion is recorded in
`RESULT.md`; it is not a replacement for the canonical Project State or for
the existing product verifiers.

RPF-37 deliberately does not add another GitHub Actions workflow. Existing
focused workflows are classified in `RESULT.md` for a later, explicit RPF-38
decision.
