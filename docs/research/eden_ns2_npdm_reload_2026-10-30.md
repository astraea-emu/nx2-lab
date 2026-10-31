# Issue #21 — native ExeFS / NPDM Switch 2 reload-state qualification (2026-10-30)

**Scope:** direct original Eden-NS2 C++ metadata implementation, not a Switch 2 game, commercial firmware or hardware reference.

## Source evidence and hypothesis

The frozen Eden-NS2 `src/core/file_sys/program_metadata.cpp` starts `ProgramMetadata::Load` by clearing `uses_extended_acid`, but not the independent object field `is_switch2`. Its extended ACID branch (`0x300` layout) explicitly sets `is_switch2 = true`. The existing original upstream Catch2 tests load both synthetic legacy and extended NPDM metadata, and test `UsesExtendedAcid` resets upon reuse, but do not separately check the Switch 2 flag.

Source revision: `0x2593/Eden-NS2` commit `e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`. Exact upstream implementation Git blob `4682cf7ab52e7509802885d63dfc2498613e305f`. Exact original C++ upstream test-translation unit blob `b5af9953f448e2880a6eff0f2a063e4ea77de1fa`.

## Executable test

1. Check out the exact original GPL source and apply the *already documented* Clang cast correction in an isolated runner. Build unmodified `core` and `video_core` libraries; exclude the *separate* native-GPU translation unit containing 31 Catch2 cases because its MME cases target obsolete APIs, exactly as PR #27 documented. The [coverage clarification](eden_ns2_full_build_gate_2026-10-30.md) distinguishes its eight MME-related cases from the other 23 excluded GPU cases.
2. Append a single **NX2-authored** Catch2 case to the original `src/tests/core/program_metadata.cpp` in the isolated checkout. It loads synthetic `MakeMetadata(true)`, confirms `UsesExtendedAcid()` and `IsSwitch2()`, reuses the **same object** with `MakeMetadata(false)`, and asserts both classifications clear.
3. Run the real original emulator metadata implementation with the added case **before** any metadata fix. If it passes, report the original source is already correct; do not fabricate a failure. If it fails, require the case and `IsSwitch2` assertion in the error output; preserve the log.
4. Only on a reproduced failure, verify the exact `src/core/file_sys/program_metadata.cpp` blob, insert exactly one `is_switch2 = false;` at the beginning of `Load`, show the one-line diff, rebuild the real test target and run both original `[loader][npdm]` and newly added reload regressions. If no failure occurred, do not patch.
5. Keep upstream C++ entirely in the temporary GPL-side build; do not import proprietary or GPL-licensed source into the MIT NX2 Lab.

This checks **internal implementation correctness**, not the Switch 2 NPDM format against physical hardware. A passing patched variant cannot be represented as a pristine original upstream build. Production-engine ACCEPT also requires stronger native-facing workload evidence and qualification of the 31 excluded native-GPU cases; they are not all MME tests.

## Verified result and current continuation — October 31

[Run 41136582253](https://github.com/astraea-emu/nx2-lab/actions/runs/41136582253)
reproduced the stale `IsSwitch2()` state in the original implementation, then
passed the regression after the isolated one-line reset. [PR #30](https://github.com/astraea-emu/nx2-lab/pull/30)
merged that original-source experiment. This result remains separate from the
later NRO lifecycle and synthetic extended-ExeFS/service-manager execution
controls in merged [#28](https://github.com/astraea-emu/nx2-lab/pull/28) and
[#32](https://github.com/astraea-emu/nx2-lab/pull/32).

The active next gate is [strict native-GPU qualification](eden_native_gpu_test_reconciliation_2026-10-31.md),
with 29 restoration candidates and two unresolved DMA contracts. Production
adoption remains **HOLD**; hardware ABI fidelity, graphics, loader robustness
and relevant host-platform coverage remain separate conditions. See
[live status](../STATUS.md) for the measured results and current decision.
