# Issue #21 — Eden-NS2 full-source runtime build qualification

**Gate status:** proposed until a green exact-head GitHub Actions run; do not conflate source-level tests with a qualified emulator.

## Objective

Move beyond the previously verified 94 source-header assertions in [PR #26](https://github.com/astraea-emu/nx2-lab/pull/26). Compile the actual upstream emulator **core, CPU, Horizon HLE, loader, video/GPU and unit-test target** from a frozen public GPL source commit. Then run its original source-owned native GPU and graphics-supervisor tests, with no game files, Nintendo keys or firmware.

## Frozen candidate

- Source: [0x2593/Eden-NS2](https://github.com/0x2593/Eden-NS2), exact SHA `e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`.
- Runner: an isolated, temporary GitHub Actions Ubuntu 26.04 VM using a normal non-privileged source checkout and read-only GitHub token. Ubuntu 26.04 is required by the candidate's own dependencies guide; it is a supported GitHub-hosted image.
- Enable `YUZU_TESTS` and build the unmodified upstream `tests` target. Disable Qt UI, web service, updater, libusb, cubeb and room networking to minimize third-party work. The graphics source must still be compiled as part of the test-linked libraries, even if no Vulkan device/game is exercised.
- Fetch only frozen public source, no proprietary binaries, keys, ROMs or firmware. Dependencies may download additional publicly hosted packages, so this test is isolated from user devices, accounts and credentials.
- This workflow is opt-in/PR-scoped; failed build experiments stay visible and do not automatically alter the main NX2 strategy.

## Required acceptance

1. Repository at verified SHA, correct core/video/test CMake files and license.
2. Clean CMake configure on the pinned Ubuntu 26.04 environment, with no vendor source edits.
3. Actual upstream `tests` executable built from the original CPU/HLE/GPU source files.
4. Original Catch2 `[native-gpu]` and `[graphics-supervisor]` test cases execute and report success.
5. Preserve the first failure precisely, including whether it is a dependency, compiler, build, crash or semantic mismatch.

Even if successful, it proves only buildable source and test-defined native behavior, **not** a lawfully accessed Switch 2 commercial guest, actual Nintendo ABI parity, first guest-produced pixel, macOS support or game compatibility.

## Next prerequisite

A genuine application must execute through that frozen loader/CPU/HLE runtime with a controlled host input and a verified first unsupported guest interface. Reusable native GPU tests can become cross-engine checks after that. Main engine decision stays **HOLD**.
