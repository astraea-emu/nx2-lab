# NX2 Lab — active plan

## Objective

[#21](https://github.com/astraea-emu/nx2-lab/issues/21) compares a mature,
separately licensed emulator runtime with an upstream contribution path.
Production adoption remains **HOLD**. Keep the MIT lab focused on independent
inputs, conformance tools and a small CPU/memory oracle.

The NRO lifecycle and synthetic ExeFS/guest-checked service-manager controls
have passed within their declared limits. [Status](STATUS.md) records the
measured results. [Adaptive strategy](ADAPTIVE_STRATEGY.md) defines when the
architecture decision should change.

## Now: restore strict native-GPU coverage

The last verified integrated run excluded one 31-case file because some MME
tests use an obsolete interpreter API. The implemented overlay prepares 29
candidates, with linked execution pending. The
[reconciliation audit](research/eden_native_gpu_test_reconciliation_2026-10-31.md)
identifies **29 restoration candidates**: 24 unchanged cases and five bounded
test adaptations. Two other cases require decisions about DMA read ownership,
failure propagation and the changed size policy. None of these 31 cases is
qualified by the existing reduced-suite pass.

Acceptance for this slice:

1. Verify the frozen commit and exact test, interpreter, caller and CMake blobs
   before applying the declared overlay in the separate GPL checkout.
2. Preserve the 24 unchanged cases and the original inputs/assertions in the
   five compatible cases. Keep both unresolved DMA expectations identifiable.
3. Build and run the actual linked Catch2 target with `EDEN_NATIVE_STRICT=1`.
   Record the registered and executed cases, applied diff, exit status and
   original output. Report omissions and failures explicitly.
4. Reconcile the measured inventory against **29 candidates + 2 unresolved**.
   Diagnose any new failure before changing the scope or expected behavior.
5. Record an ACCEPT/HOLD/REJECT decision for this slice and the next executable
   workload. A passing reduced scope does not qualify the complete suite.

## After this result: select one graphics workload

Choose one source-authored guest graphics/display path using the measured GPU
results. Require actual guest-produced image readback against an independent
reference. The frozen QMD scheduler can report completion after skipped shader
work outside strict mode, so semaphore completion alone cannot prove a frame.
The [audit](research/eden_native_gpu_test_reconciliation_2026-10-31.md#qmd-strict-mode-is-part-of-the-tested-contract)
records the exact source behavior and remaining interpreter/JIT boundary.

## Supporting work and boundaries

The malformed-NRO AES assertion and original parser bounds remain production
blockers. Qualify any repair against the original C++ with negative and
sanitizer-backed regressions. No evidence places that crypto failure on the
controlled ExeFS path, so it does not replace the selected GPU slice.

HBX stage 2 ([#20](https://github.com/astraea-emu/nx2-lab/issues/20)) remains a
bounded secondary regression. Device research follows the separate
[research intake](RESEARCH_INTAKE.md) and [security scope](SECURITY.md).
Hardware ABI fidelity, host-platform parity, safe redistribution and commercial
game support require their own evidence; this plan makes no delivery promise
for them. Earlier schedules and allocation proposals are preserved in the
[dated strategy records](STRATEGY_2026-10-29.md).
