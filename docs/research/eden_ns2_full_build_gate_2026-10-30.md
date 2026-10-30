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

If the reduced suite passes, the evidence proves the original integrated libraries build on this toolchain (with one cast patch) and **only the included** native tests pass. The omitted macro-interpreter tests remain a release blocker for a production engine ACCEPT; they need upstream reconciliation against the current API, not an indefinite workaround. If further source/test mismatches arise, preserve the failure and review maintenance costs rather than repeatedly excluding more files.

## Required acceptance

1. Repository at verified SHA, correct core/video/test CMake files and license.
2. Clean CMake configure on the pinned Ubuntu 26.04 environment, with no undeclared source changes. The original compile must retain its failed-build evidence; a subsequent isolated build may apply only the explicitly audited one-line cast.
3. Actual upstream `core` and `video_core` libraries build from frozen GPU/HLE/CPU source (plus one documented cast), and the explicitly reduced `tests` executable links successfully.
4. The **remaining** original Catch2 `[native-gpu]` and `[graphics-supervisor]` cases execute successfully; the omitted `native_gpu_characteristics.cpp` cases are explicitly untested.
5. Preserve the first failure precisely, including whether it is a dependency, compiler, build, crash or semantic mismatch.

Even if successful, it proves only buildable source and test-defined native behavior, **not** a lawfully accessed Switch 2 commercial guest, actual Nintendo ABI parity, first guest-produced pixel, macOS support or game compatibility.

## Next prerequisite

A genuine application must execute through that frozen loader/CPU/HLE runtime with a controlled host input and a verified first unsupported guest interface. Reusable native GPU tests can become cross-engine checks after that. Main engine decision stays **HOLD**.
