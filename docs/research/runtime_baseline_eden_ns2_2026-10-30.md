# Issue #21 — frozen Eden-NS2 native-interface source qualification (2026-10-30)

> **Header-contract stage.** Subsequent [integrated build](eden_ns2_full_build_gate_2026-10-30.md) and [guest IPC](eden_native_ipc_runtime_2026-10-31.md) experiments have separate evidence. See [current status](../STATUS.md) for the latest decision.

**Decision: HOLD.** This is a direct-source evaluation of Switch 2-facing **emulator implementation code**, not a production runtime build, physical console observation, complete Horizon service or guest game execution.

## Input and provenance

- Project: [0x2593/Eden-NS2](https://github.com/0x2593/Eden-NS2), an Eden/Yuzu derivative (GPL-3.0-or-later). Source frozen at commit `e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`.
- The workflow `.github/workflows/p0-eden-ns2-native-contract.yml` fetches only seven exact source headers by Git sparse checkout. It verifies every upstream file's Git blob SHA, compiles the **unchanged original header implementations** and executes a separately NX2-authored MIT-licensed C++ probe. No external runtime executables or proprietary game/firmware/keys are downloaded.
- Public upstream source contains native GPU/HLE logic and standalone Catch2 tests for graphics supervisor, shader, GPU characteristics and native semaphore. This controlled test does not compile the full upstream renderer or run those Catch2 tests.

## Independent executable assertions

1. Original graphics-supervisor TIPC bootstrap decoder: accepted packet, native shader-profile selection, truncated/mutated rejection, and local-vs-remote flag distinction.
2. Actual GPU address-space layout, 4 KiB page-only constraints, unsupported flags and misalignment.
3. Native image allocation: independently checked 1920x1080 and 65x33 input cases, multiple images, invalid pitch/block/count/overflow/unused words.
4. Versioned native video allocation: known reference geometry and negative shapes.
5. Graphics syncpoint wraparound and unallocated state.
6. Native GPU semaphore dependencies: blocked channels do not advance prematurely, and 2→1→0 dependency release order is preserved.

Runs twice with GNU C++ and Clang/ASan/UBSan. Explicit unsupported and malformed inputs are part of the acceptance, not success-by-stubbing. A **green exact-head CI execution** is necessary before describing this as measured evidence; source review alone is not enough.

## Competitive interpretation

- The tested standalone source files have no corresponding paths in the current public Eglantine default branch; therefore Eden-NS2 and Eglantine do not have identical implementation surfaces.
- This is meaningful *source-level* confirmation of actual Switch 2-facing code behavior, but it is **weaker than running an unchanged guest application in a full emulator**. The previous [NeXo qualification](https://github.com/astraea-emu/nx2-lab/pull/25) established genuine Switch 1-format guest execution through another emulator. Neither experiment independently validates commercial Switch 2 gameplay.
- A source-coded emulation contract is not a device-derived behavioral oracle. It may precisely implement the author's assumptions and still differ from a physical Switch 2.
- GPL code stays outside the MIT NX2 Lab tree and its distributed binaries. Any selected GPL engine requires license and supply-chain review.

## Follow-up proposed at this checkpoint

Configure and build the actual frozen Eden-derived loader/CPU/HLE runtime using isolated CI and vetted dependencies. Then execute a permitted source-authored guest program, checking its first unsupported interface; also investigate GPU correctness against independently authored expected pixels. The current work does **not** select Eden-NS2 as the production engine.
