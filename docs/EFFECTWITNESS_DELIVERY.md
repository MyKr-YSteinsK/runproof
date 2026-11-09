# EffectWitness recorded delivery

Unzip the bundle into a new folder. From that folder, use Node.js to check the manifest and start the preview:

```powershell
node .\effectwitness-preview.cjs verify
node .\effectwitness-preview.cjs
```

Open `http://127.0.0.1:4174/effectwitness/workbench`. Keep the command in the foreground and press Ctrl+C to exit. If the port is occupied, choose a free loopback port and run `node .\effectwitness-preview.cjs serve . 4175`, then open the same path on 4175. Compare the ZIP SHA-256 against the separately supplied receipt before extraction. The manifest records the build commit and member hashes. Obtain the receipt through a trusted channel when transferring the package.

## Three-minute walkthrough

1. **0:00–0:40** Choose **Orders & refunds**. Compare EXPECTED, FORBIDDEN, and UNKNOWN OUTCOME. An unknown write calls for read-only reconciliation.
2. **0:40–1:45** Follow **Investigate recorded facts**. Open an event to see its recorded context, then use **Return to workbench**. The URL carries the domain and event. Review the feedback chain and state differences. Switch languages in the sidebar and refresh to revisit the same event.
3. **1:45–2:50** Open **Verify the Witness & limitations**, then choose **Operations configuration**. This domain has an independent historical Witness sample. Its same-session timeline and state diff are unavailable. Use **View sources and offline verification** to inspect the recorded materials. The workbench separates Recorded Evidence from Controlled Local and Live Provider availability.

If a saved event cannot be located, open the workbench at `?domain=order` and select an event from the verified list. If a source fails verification, the app marks it UNAVAILABLE. Use the fixed checkout and CLI below to investigate the source.

## Build and check from a checkout

Use the existing Node/npm dependencies in a clean checkout of the build inputs, with no Vite environment files. In PowerShell from the repository root:

```powershell
.\demo\effectwitness-delivery.ps1 Build
.\demo\effectwitness-delivery.ps1 Package -RunRoot <RunRoot>
.\demo\effectwitness-delivery.ps1 Verify -BundleRoot <independently-extracted-directory>
.\demo\effectwitness-delivery.ps1 Preview -BundleRoot <independently-extracted-directory>
```

Substitute the paths printed by Build and use `-NodeExe` to select an existing absolute Node path. Verify briefly binds the local port for HTTP checks, then releases it.

The optional checkout evidence CLI requires Python. Use the repository's verified interpreter:

```text
python -B spikes/rpf-47/verify_evidence.py --root .
python -B -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-43/sample-witness.json --expected-sha256 ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e
python -B -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-44/sample-ops-witness.json --expected-sha256 21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873
```

This package presents recorded evidence only. The order research summary and the two Witness samples have distinct historical identities. Issuer authenticity remains unestablished. New Explorer sessions, cross-domain authority, Release eligibility and competition submission are outside this demonstration.
