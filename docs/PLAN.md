# NX2 Lab — active plan

## Objective

[#21](https://github.com/astraea-emu/nx2-lab/issues/21) compares a mature,
separately licensed emulator runtime with an upstream contribution path.
Production adoption remains **HOLD**. Keep the MIT lab focused on independent
inputs, conformance tools and a small CPU/memory oracle.

The NRO lifecycle, synthetic ExeFS/service-manager controls and strict native
unit-test slice have passed within their declared limits. [Status](STATUS.md)
records the measured results. [Adaptive strategy](ADAPTIVE_STRATEGY.md) defines when the
architecture decision should change.

## Accepted baseline

[Run 41245699243](https://github.com/astraea-emu/nx2-lab/actions/runs/41245699243)
passed **62 cases / 25,395 assertions** with `EDEN_NATIVE_STRICT=1`: 29 restored
cases plus the existing 33, with no failures or skips. The
[reconciliation record](research/eden_native_gpu_test_reconciliation_2026-10-31.md)
preserves the 24 unchanged bodies, five compatibility adaptations and two
unresolved DMA cases. This accepts the declared unit-test slice; production
adoption and the full upstream suite remain unqualified.

## Now: native VI2 client lifecycle

Run a separate original ARM64 guest through
`appletOE` → `GraphicsSupervisor` → `VI2`, using the frozen
[graphics-supervisor implementation](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/am/service/graphics_supervisor.cpp).

1. Acquire real service handles and complete the required bootstrap. Check
   the distinct CMIF/TIPC reply layouts: TIPC carries a raw result without
   an `SFCO` header.
2. Register a nonzero client token with notification slots 2/3. Require
   registration success, duplicate-registration refusal, successful
   unregister, and missing-token refusal on a repeated unregister.
3. Submit a valid writable **127-byte** notification buffer and require
   size rejection without consuming the pending notification. A **128-byte**
   read must then return retirement bit 2 (`0x4`); a second 128-byte read
   must return cleared notifications.
4. The actual guest checks and reports returned values and reply memory,
   closes all acquired handles, and reaches real `ExitProcess` with status 0.
   Faults, timeouts and unexpected stub/fallback paths fail acceptance.

Record the known source-tagged `(STUBBED)` diagnostic from
[`GetManagerDisplayService`](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/vi/application_display_service.cpp)
explicitly: this getter constructs an actual container-backed manager, but
obtaining it does not qualify the display implementation. This narrow known
diagnostic does not permit unrelated fallback success.

Passing this control would establish source-model service behavior, with no
pixel claim. The following image workload is a CPU-filled checkerboard in the
supported block layout, presented through the real renderer and captured for comparison
with an independent pixel reference. Completion signals alone cannot prove a
frame or hardware ABI fidelity.

## Supporting work and boundaries

The two DMA contracts still need decisions about read ownership, failure
propagation and the changed size policy; retain their explicit exclusions.
The malformed-NRO AES assertion and original parser bounds remain production
blockers. Qualify any repair against the original C++ with negative and
sanitizer-backed regressions. No evidence places that crypto failure on the
controlled ExeFS path, so it does not replace the selected guest workload.

HBX stage 2 ([#20](https://github.com/astraea-emu/nx2-lab/issues/20)) remains a
bounded secondary regression. Device research follows the separate
[research intake](RESEARCH_INTAKE.md) and [security scope](SECURITY.md).
Hardware ABI fidelity, host-platform parity, safe redistribution and commercial
game support require their own evidence; this plan makes no delivery promise
for them. Earlier schedules and allocation proposals are preserved in the
[dated strategy records](STRATEGY_2026-10-29.md).
