# EffectWitness controlled local product

Use this Windows opt-in profile to create a fictional, two-domain SQLite session. The rule policy consumes independently read-back order feedback before selecting the configuration experiment. Paid Real Explorer is disabled, and Provider reservations stay at zero.

Use an existing CPython 3.11+ interpreter with SQLite and the checkout's installed Node/Vite dependencies. From the repository root:

```powershell
.\demo\start-effectwitness-product.ps1 -PythonExe <absolute-python.exe> -NodeExe <absolute-node.exe>
```

1. Open `http://127.0.0.1:4187/effectwitness/live-local`. Confirm the fictional local session and choose **Start local session**.
2. Inspect the frozen candidates, order **UNKNOWN_OUTCOME**, the read-only receipt and verified feedback, then the **SELECT_OPS** decision and configuration diff. An inconclusive readback leaves **RECONCILE_REQUIRED** and blocks later writes.
3. Download the Witness after **COMPLETED**. Run the offline verifier with the same checkout and an independently trusted expected hash when available.

```text
python -B -m runtime.runproof_runtime.effectwitness.product_local_verify <witness.json> --expected-sha256 <trusted-sha256>
```

The page displays the hash observed at download for transfer comparison. Use a separately trusted channel for an external anchor. An unanchored check returns CONTENT_CHECKED_LOCAL. External Issuer and causal superiority remain unestablished.

Refresh the page or use **Refresh readback** to retrieve the previous request without replaying a write. The session and event query can be bookmarked. At most two sessions are admitted per live owner, with one write per domain and no quota renewal on restart. Stop the service using the process identity receipt:

```powershell
.\demo\stop-effectwitness-product.ps1
```

The ledger and domain databases remain in the task's live owner. Restarting the profile loads them. Interrupted sessions require readback or human review. Use the recorded delivery guide for the separate static preview on 4174. [Recorded delivery](EFFECTWITNESS_DELIVERY.md)
