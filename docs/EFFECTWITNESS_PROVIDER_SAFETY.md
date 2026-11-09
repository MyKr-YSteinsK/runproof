# EffectWitness local pre-send safety

RPF-101 exercises a durable Host Barrier and independently observed TCP delivery. It uses a new task owner and a fixed synthetic payload. The local receiver is a separate Python process with a nonce challenge. The Host records SEND_BEGIN durably before entering the transport, and the receiver records bytes separately.

Use a verified absolute CPython path from the repository root. Replace `<python>` with that path.

```text
<python> -B demo/probe-rpf101-provider-barrier.py --preflight
<python> -B -m unittest -v ci.test_rpf101_provider_barrier
<python> -B demo/probe-rpf101-provider-barrier.py --inspect unknown-restart
<python> -B -m runtime.runproof_runtime.effectwitness.provider_receipt_verify ready-restart --expected-sha256 <trusted-evidence-anchor>
<python> -I -B runtime/runproof_runtime/effectwitness/provider_sdk_probe.py
```

The unittest and the probe's `--run` option are alternative formal entry points. Each checkout owner admits one registered matrix. Use offline inspection after the run. All evidence stays under `.local/rpf-101-provider-presend`.

A write result that is unknown closes admission across both domains and both roles. Reconciliation reads existing evidence. NO_BYTES_OBSERVED describes only the local receiver's observations. A completed send that won the lock first is classified as pre-UNKNOWN. Normal restart with a clean READY chain can send the previously reserved ticket once.

The Host retains an active marker after unclean exit or durability errors. Process recovery and injected failures are covered. Power-loss durability on Windows and protection from a privileged local actor controlling the entire owner remain unverified. The verifier independently recomputes the evidence chain and requires an independently trusted digest for external anchoring. Issuer authenticity remains unestablished.

The installed SDK probe is metadata-only and reports SDK_UNAVAILABLE when the interpreter lacks an admitted package. RPF-100 remains a separate product path. Future Explorer integration requires an admitted SDK and a bounded send path that calls the Host before transport.
