# RPF-102 rev-3 manual conformance

[RESULT](RESULT.md) records the offline handoff. [Acceptance](acceptance.json), [verification](verification-diagnostic.json), and the [source map](source-map.json) bind the seal.

Phase B requires separate user approval of the full frozen SHA, one hosted run, one NORMAL followed by at most one UNKNOWN, and the specified budgets. After approval, an authorized operator must verify the `rpf-102-physical` GitHub environment has required reviewers and self-approval disabled. For the single pending manual run, record the approved commit and that run's ID in the environment variables `RPF102_APPROVED_SOURCE_SHA` and `RPF102_APPROVED_RUN_ID` before releasing the job. Verify both values resolve in the admission step. The dispatch input only repeats the approved SHA. The job uses `deployment: false`. [GitHub environment protection and deployment records](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)

For an approved artifact, check out its frozen commit and extract the capsule into an isolated directory. Use the owner and run ID from the admission receipt and compare the manifest SHA-256 with the run's independently retained value.

```text
python -B -m ci.rpf102_rev3_capsule verify --folder <extracted-directory> --owner <32-hex-owner> --expected-sha <frozen-40-hex-sha> --run-id <run-id> --expected-manifest-sha256 <manifest-sha256>
```

The verifier rechecks the file set and hashes before passing complete cases to the existing Oracle. `--require-complete` exits nonzero unless both cases verify. `FAILURE_DIAGNOSTIC` means the diagnostic is available and complete case evidence is unavailable for publication. In a complete case, SDK POST and Receiver payload bytes are original. Receipts containing a handshake nonce carry a consistent one-way substitution. The manifest records both original and public hashes for those receipts. Extraction can recompute the public hash, while checking the original receipt hash requires access to the original. Content verification does not establish a third-party issuer or reproduce a physical run.
