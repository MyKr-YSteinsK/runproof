# Local SDK pre-send conformance

RPF-102 defines a conformance experiment with a local Host, a real SDK, and an independent loopback Receiver. The Host serves scripted completions and tracks inbound requests, durable reservations, physical forwards, and received bytes separately. The first formal NORMAL attempt failed. UNKNOWN still awaits execution.

Run the local no-SDK controls with a verified interpreter from the repository root:

```text
<python> -B -m unittest -v ci.test_rpf102_sdk_presend
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_probe --owner <32-hex-owner> --preflight
```

The automatic Ubuntu workflow runs offline tests and documentation checks and records `SDK_PHYSICAL_NOT_RUN_BY_PLAN`. Any future formal attempt requires separate approval for its commit, isolated runner, and physical budget.

After a future approved run, read its public diagnostic and validate it before upload:

```text
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_probe --owner <new-owner> --diagnostic NORMAL > diagnostic.json
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_diagnostic < diagnostic.json
```

Use a separate file for each started case. An unavailable diagnostic leaves stdout empty and exits nonzero. In a future approved CI job, make collection run after failure with `always()` and allow upload only for JSON that passes validation. The envelope contains allowlisted fields and explicit `null` counts when evidence is missing. Keep the underlying WAL, stdout, requests, and Receiver bytes private.

Use the independent Oracle to check complete case evidence:

```text
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> NORMAL
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> UNKNOWN --expected-sha256 <trusted-anchor>
```

NORMAL expects two forwards. UNKNOWN expects a persisted latch before the tool response and a denied second completion, with one forward total. Receiver byte equality is checked independently of the Host's send receipt. A digest supplied by the same owner provides local content comparison. Third-party Issuer identity, paid model behavior, historical repair and product integration remain separate gates.
