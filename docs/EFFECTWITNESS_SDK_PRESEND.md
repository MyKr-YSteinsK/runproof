# Local SDK pre-send conformance

RPF-102 runs a real installed SDK against a local Host and an independent loopback receiver. The Host returns scripted completion and tool-call responses. The SDK sends the next completion after the tool returns, while the Host separately counts inbound requests, durable reservations, physical forwards, and received bytes.

Run the local no-SDK controls with a verified interpreter from the repository root:

```text
<python> -B -m unittest -v ci.test_rpf102_sdk_presend
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_probe --owner <32-hex-owner> --preflight
```

The dedicated Ubuntu workflow is the authorized installation route. It uses an isolated venv, exact direct pins, a wheel-only PyPI installation, and records pip check and the resolved package versions. The physical runner admits only that task-owned SDK environment. Each formal owner accepts one NORMAL and one UNKNOWN case.

After an admitted run, inspect the owner without executing the SDK:

```text
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> NORMAL
<python> -B -m runtime.runproof_runtime.effectwitness.sdk_presend_oracle <owner> UNKNOWN --expected-sha256 <trusted-anchor>
```

NORMAL expects two forwards. UNKNOWN expects a persisted latch before the tool response and a denied second completion, with one forward total. Receiver byte equality is checked independently of the Host's send receipt. A digest supplied by the same owner provides local content comparison. Third-party Issuer identity, paid model behavior, historical repair and product integration remain separate gates.
