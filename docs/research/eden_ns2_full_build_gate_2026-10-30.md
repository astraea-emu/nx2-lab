# Issue #21 — Eden-NS2 full-source runtime build qualification

**Gate status:** full upstream test-suite build **FAILED** at the frozen revision even after an isolated one-line cast fix. A narrower evidence gate now separately builds original core/GPU libraries and a reduced explicitly annotated test subset. No complete upstream test-suite success is claimed.

## Objective

Move beyond the previously verified 94 source-header assertions in [PR #26](https://github.com/astraea-emu/nx2-lab/pull/26). Compile the actual upstream emulator **core, CPU, Horizon HLE, loader, video/GPU and unit-test target** from a frozen public GPL source commit. Then run its original source-owned native GPU and graphics-supervisor tests, with no game files, Nintendo keys or firmware.

## Frozen candidate

- Source: [0x2593/Eden-NS2](https://github.com/0x2593/Eden-NS2), exact SHA `e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`.
- Runner: an isolated, temporary GitHub Actions Ubuntu 26.04 VM using a normal non-privileged source checkout and read-only GitHub token. Ubuntu 26.04 is required by the candidate's own dependencies guide; it is a supported GitHub-hosted image.
- Enable `YUZU_TESTS` and build the upstream `tests` target with **one documented build-only source correction applied in ephemeral CI**. Disable Qt UI, web service, updater, libusb, cubeb and room networking to minimize third-party work. The graphics source must still be compiled as part of the test-linked libraries, even if no Vulkan device/game is exercised.
- Fetch only frozen public source, no proprietary binaries, keys, ROMs or firmware. Dependencies may download additional publicly hosted packages, so this test is isolated from user devices, accounts and credentials.
- This workflow is opt-in/PR-scoped; failed build experiments stay visible and do not automatically alter the main NX2 strategy.

## Observed first full-build result

[GitHub Actions run #41095182827](https://github.com/astraea-emu/nx2-lab/actions/runs/41095182827) configured Ubuntu 26.04 and the frozen real Eden-NS2 source successfully, compiled approximately 750 of 1459 Ninja steps, then failed in upstream `src/video_core/texture_cache/util.cpp:985`. Clang rejected narrowing `s32 layer` into `u64{layer}`. The enclosing loop starts at zero and increments `layer` while below `info.resources.layers`. This is an **upstream compile defect**, not guest execution, graphics correctness or host security evidence.

The follow-up workflow verifies that source file's original Git blob `94e841e8ea4e13beb547ecc1653b5088b770a166` before making exactly one local replacement: `u64{layer}` to `static_cast<u64>(layer)` in the segment-begin calculation. It also requires the expected loop and exactly one added/deleted line, then prints the diff. **This intentionally creates a local patched build, not a pristine upstream build.** The GPL source remains in the ephemeral worker; no upstream source file is imported into the MIT project.

## Second failure: upstream native macro test/API drift

[PR #27 exact-head run #41099519858](https://github.com/astraea-emu/nx2-lab/actions/runs/41099519858) advanced to **1450/1459** Ninja steps after the verified narrow cast correction, then failed compiling the untouched upstream `src/tests/core/native_gpu_characteristics.cpp`. The file calls `TuringMacroInterpreter::Execute` with obsolete argument forms, references nonexistent `Instruction` and `ExecuteDecoded` APIs, and expects parameter types incompatible with the current `macro_turing.h` definition. This is an independently reproduced upstream test-to-runtime API mismatch; it must not be promoted as a successfully built full upstream test suite.

The next run **first builds the real `core` and `video_core` targets without suppressing any production source file** (apart from the previously documented cast correction). Only after that succeeds, it verifies exact upstream `src/tests/CMakeLists.txt` blob `ff1168471c5eb45aa54b78892b5f65e03391688f` and omits its single `core/native_gpu_characteristics.cpp` entry in the ephemeral checkout. The reconfigured `tests` target is therefore an explicitly **reduced upstream suite**, not the complete test suite. Other native GPU/graphics supervisor tests remain in their original source form.

If the reduced suite passes, the evidence proves the original integrated libraries build on this toolchain (with one cast patch) and **only the included** native tests pass. The 31 native-GPU cases in the excluded translation unit remain unqualified and block production-engine ACCEPT; the MME API mismatch must be reconciled so that the complete file can run, not kept as an indefinite exclusion. If further source/test mismatches arise, preserve the failure and review maintenance costs rather than repeatedly excluding more files.

## Verified reduced-suite result

[Run 41115025130](https://github.com/astraea-emu/nx2-lab/actions/runs/41115025130)
built the actual core and GPU libraries with the declared cast correction,
linked the reduced test target, and passed **33 cases / 9,103 assertions**.
[PR #27](https://github.com/astraea-emu/nx2-lab/pull/27) merged with that bounded
result. The excluded translation unit remains outside this pass; the result
does not repair the full-suite build failure or qualify its omitted cases.

## Coverage clarification — October 31

The exclusion is **one complete test translation unit**, not 31 MME-only cases.
The exact frozen
[`src/tests/core/native_gpu_characteristics.cpp`](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/tests/core/native_gpu_characteristics.cpp)
(Git blob `b54bd36ee35d433263f0bed967ca111391c03ea2`) contains **31 `TEST_CASE`
definitions**. Eight explicitly concern MME; the other 23 cover native GPU
characteristics, memory/layout/kind handling, QMD dependency and dispatch
behavior, vertex-stream state, sparse remapping and root-table handling.
They were excluded together because MME cases in the same file call obsolete
interpreter APIs. The remaining 23 were not independently proved incompatible,
and none of the 31 counts as passed.

The [full-build workflow](../../.github/workflows/p0-eden-ns2-full-build.yml)
verifies the original `src/tests/CMakeLists.txt` Git blob
`ff1168471c5eb45aa54b78892b5f65e03391688f` and removes exactly its single
`core/native_gpu_characteristics.cpp` entry. The
[NPDM-regression workflow](../../.github/workflows/p0-eden-ns2-npdm-reload.yml)
reuses that exclusion. No production translation unit is removed. The excluded
source also sets `EDEN_NATIVE_STRICT=1` in its own static initializer; restoring
and executing these tests must preserve their strict-mode assumptions. This
source observation does not establish which environment settings were active
in other test translation units.

## Required acceptance

1. Repository at verified SHA, correct core/video/test CMake files and license.
2. Clean CMake configure on the pinned Ubuntu 26.04 environment, with no undeclared source changes. The original compile must retain its failed-build evidence; a subsequent isolated build may apply only the explicitly audited one-line cast.
3. Actual upstream `core` and `video_core` libraries build from frozen GPU/HLE/CPU source (plus one documented cast), and the explicitly reduced `tests` executable links successfully.
4. The **remaining** original Catch2 `[native-gpu]` and `[graphics-supervisor]` cases execute successfully; the omitted `native_gpu_characteristics.cpp` cases are explicitly untested.
5. Preserve the first failure precisely, including whether it is a dependency, compiler, build, crash or semantic mismatch.

Even if successful, it proves only buildable source and test-defined native behavior, **not** a lawfully accessed Switch 2 commercial guest, actual Nintendo ABI parity, first guest-produced pixel, macOS support or game compatibility.

## Current continuation — October 31

The separate guest-execution prerequisites have since passed: [PR #28](https://github.com/astraea-emu/nx2-lab/pull/28) qualifies the labeled NRO lifecycle control, and [PR #32](https://github.com/astraea-emu/nx2-lab/pull/32) qualifies synthetic native-classified ExeFS lifecycle and an actual guest-checked service-manager roundtrip. Their [live status](../STATUS.md) preserves the precise input changes and limits.

The active next slice returns to the omitted file. The [31-case reconciliation audit](eden_native_gpu_test_reconciliation_2026-10-31.md) identifies 24 unchanged candidates, five bounded compatibility adaptations, and two DMA contracts requiring explicit review. Restore and execute the declared scope under strict mode with preserved assertions; source review does not count as an integrated test pass. Main engine decision stays **HOLD**, and no guest-produced frame or hardware ABI parity is established.
