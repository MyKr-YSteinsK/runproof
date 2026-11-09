# RPF-102 rev-5 — Fresh Checkout Owner Bootstrap

This revision repairs the offline/manual preflight when a clean checkout has no `.local` directory. The fix retains the existing path and owner checks, creates only one verified directory level at a time, and keeps admission exclusive to a new owner and ledger.

## Validation

The hosted workflow runs `FreshCheckoutBootstrapTests` first, before the existing offline suite can create `.local`. It then runs both RPF-102 offline suites and the existing public-document check. The smoke creates only an ignored rev-5 test owner and admission ledger; it does not install the SDK or invoke a provider.

Local command:

```powershell
C:/msys64/ucrt64/bin/python.exe -B -m unittest -v ci.test_rpf102_sdk_presend ci.test_rpf102_rev3_capsule
```

The Windows run cannot enforce POSIX directory modes or create symlinks in the current user context. Those cases are reported as skipped locally and are covered by the hosted Linux run when available.

## Evidence boundary

The smoke proves owner bootstrap and ledger readback only. It does not prove SDK installation, NORMAL/UNKNOWN execution, receiver delivery, or a physical capsule. The manual workflow's approval checks and physical resource limits remain unchanged.
