# RPF-102 rev-6 SDK import audit

The automatic Ubuntu workflow runs `SDK_IMPORT_ONLY_NO_PHYSICAL` on ordinary main pushes. It installs the pinned wheels in a disposable venv, verifies PyPI wheel provenance and runs the physical client's exact import set in a child started with `-I -S -B`, an explicit site path, a scrubbed environment and a new task directory. The child stops after checking package identity.

Run the local controls from the repository root with a verified interpreter:

```text
python -B -m ci.test_rpf102_rev6_sdk_import ci.test_rpf102_sdk_presend ci.test_rpf102_rev3_capsule
python -B -m unittest -v ci.test_rpf102_rev6_sdk_import
```

The pinned positive requires the hosted venv and its pip install report. Inspect the final commit's automatic CI before any future physical approval. Do not reuse the failed Run or its owner. Import readiness covers imports and package identity, with client construction, NORMAL and UNKNOWN left to separate acceptance.
