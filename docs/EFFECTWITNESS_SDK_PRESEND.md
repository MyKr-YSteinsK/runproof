# Local SDK pre-send conformance

RPF-102 defines a conformance experiment with a local Host, a real SDK, and an independent loopback Receiver. The Host serves scripted completions and tracks inbound requests, durable reservations, physical forwards, and received bytes separately. The first formal NORMAL attempt failed. UNKNOWN still awaits execution.

Run the local no-SDK controls with a verified interpreter from the repository root:

```text
<python> -B -m unittest -v ci.test_rpf102_sdk_presend ci.test_rpf102_rev3_capsule
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_probe --owner <32-hex-owner> --preflight
```

The automatic Ubuntu workflow runs both offline suites, checks the documentation, and records `SDK_PHYSICAL_NOT_RUN_BY_PLAN`. Before dispatch, verify both suites passed on the frozen commit and confirm that GitHub actually enforces required reviewers and prevents self-approval for `rpf-102-physical`. A formal attempt requires approval for its frozen commit, isolated runner, and physical budget. The manual workflow checks the approved source SHA, the exact GitHub run ID, and attempt 1 before it creates the owner. It verifies NORMAL with the independent Oracle and checks that its evidence can be published before starting UNKNOWN. See the [rev-3 operator and verifier guide](../spikes/rpf-102/rev-3/README.md).

After a future approved run, read its public diagnostic and validate it before upload:

```text
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_probe --owner <new-owner> --diagnostic NORMAL > diagnostic.json
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_diagnostic < diagnostic.json
```

Use a separate file for each started case. An unavailable diagnostic leaves stdout empty and exits nonzero. The manual workflow checks the capsule before upload, even when the experiment fails. The diagnostic contains allowlisted fields and explicit `null` counts when evidence is missing. The capsule publishes only admitted evidence and keeps SDK stdout logs, environment files, handshake credentials and unapproved bytes in the owner.

The automatic Ubuntu workflow also runs `SDK_IMPORT_ONLY_NO_PHYSICAL` with the pinned SDKs in a disposable venv. It checks the isolated imports and the package source and RECORD hashes. An audit refusal reports a fixed operation code and logical target category. A library exception has a separate origin and carries no audit target. On Linux, SDK imports can read the exact `/etc/mime.types` file during `SDK_IMPORT`. Physical NORMAL and UNKNOWN still require their own approval and evidence.

Use the independent Oracle to check complete case evidence:

```text
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> NORMAL
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> UNKNOWN --expected-sha256 <trusted-anchor>
```

NORMAL expects two forwards. UNKNOWN expects a persisted latch before the tool response and a denied second completion, with one forward total. Receiver byte equality is checked independently of the Host's send receipt. A digest supplied by the same owner provides local content comparison. Third-party Issuer identity, paid model behavior, historical repair and product integration remain separate gates.
