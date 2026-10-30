# Issue #21 — Eden-NS2 bounded source-authored NRO execution experiment

**Status: proposed, not yet verified. Do not claim guest execution unless the real frontend prints the original guest's diagnostic string.**

## Why this probe

The merged [PR #27](https://github.com/astraea-emu/nx2-lab/pull/27) established that Eden-NS2's integrated CPU, loader, Horizon HLE and GPU libraries build (with one narrowly documented upstream Clang cast correction), and that 33 *included* upstream graphics-related test cases pass. That does **not** establish guest execution. The original 31 stale macro-interpreter cases remain unresolved.

The next real gate is to execute a source-authored ARM64 homebrew application through the **actual integrated Eden command-line process**, instead of another isolated header test. Eden includes an NRO loader and an SDL3 null-renderer command-line frontend, so a zero-proprietary-data attempt is possible.

## Original inputs, provenance and isolation

- Frozen Eden-NS2 GPL fork: `0x2593/Eden-NS2` at commit `e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`.
- Exact one-line ephemeral upstream cast patch from PR #27, validated with source blob `94e841e8ea4e13beb547ecc1653b5088b770a166`. No GPL source is imported into MIT NX2 Lab; no proprietary firmware, console files, keys or commercial games are downloaded.
- Independently developed NeXo 2 homebrew reference input: `NeXoNetwork/NeXo2-emu`, commit `7fa73a5062e64370163a248d1a0b555272012c0f`; its source is `tests/programs/nro_hello/main.c`. The original `tests/generated/hello.nro` is 24,636 bytes, Git blob `bb0ee2a52acd303e7c800443163aa91900eabb58`. The file is fetched in a disposable runner and independently verified. Its positive execution in NeXo's interpreter was already confirmed by [PR #25](https://github.com/astraea-emu/nx2-lab/pull/25).
- This NRO is a **Switch 1-format homebrew ABI**, not an independently measured Switch 2 ABI, game or GPU workload. Even successful execution would only verify a shared foundational compatibility path.
- CI compiles Eden's original `yuzu-cmd` executable, with Qt, web/update services, libusb and cubeb disabled. The test uses `--program nx2-source-probe --null-render --singlecore` for the valid NRO: the frozen Eden NRO loader only constructs its Homebrew ABI configuration table and return-address setup when `program_args` is nonempty. The original NeXo `crt0.S` expects that table in X0, a loader marker in X1, and an SVC-exit return address in X30. This ensures the trial tests emulator behavior rather than an avoidable missing-input error. It also records which later guest-authored debug strings (data counter, heap sum, Fibonacci and return) appear, without mislabelling partial progress as full exit. The test uses SDL's dummy video/audio drivers, temporary XDG directories and an OS process timeout; no personal workstation or credentials are used.

## Acceptance evidence

1. Frozen source and original NRO hashes pass validation.
2. Real Eden CPU/HLE/GPU code and its command-line frontend build and link.
3. A valid original homebrew executes and causes the exact diagnostic `Hola desde un NRO en NeXo 2!` to appear in the **Eden process output**. The string exists in guest source, and this check must not be satisfied by a host-authored echo, metadata label or fabricated fixture.
4. A byte-corrupted NRO magic control is rejected by the frontend without being mistaken for a valid guest program. Its process must terminate rather than hang until the timeout.
5. An emulator timeout, crash, unsupported host renderer, missing firmware or guest-output absence must be reported as **failure or incomplete evidence**; it must not be re-labelled as guest execution.

A passed run proves only the original, source-authored Switch 1-style guest reached a guest-generated debug output through an Eden-derived CPU/HLE path. It would **not** prove Switch 2-native software, GPU rendering, a Nintendo game, legal device observations, Apple Silicon compatibility or readiness to select Eden-NS2 as production architecture.

## First completed build attempt (source compiled; incorrect artifact-path assertion)

[Initial run #41120419704](https://github.com/astraea-emu/nx2-lab/actions/runs/41120419704) completed the original upstream C++ compilation and linked **`bin/eden-cli` at step 1443/1443**. The CI job nevertheless failed because the NX2-authored workflow incorrectly required `bin/yuzu-cmd` despite the CMake target being named `yuzu-cmd`; no guest trial was executed in that run. The corrected workflow checks and invokes `bin/eden-cli`, without modifying the emulator source, guest binary or evidence threshold.

## First actual guest trial — bounded timeouts and masked logs

[Exact-head run #41123961589](https://github.com/astraea-emu/nx2-lab/actions/runs/41123961589) compiled the full original `bin/eden-cli` target at Ninja step **1443/1443**. It then executed the *actual* positive and corrupt-magic NRO process trials; neither met the acceptance criteria:

- Original valid NRO process returned **124**, the 22-second GNU `timeout` result. A clean natural exit was not observed.
- Mutated invalid-magic NRO returned **137**, consistent with forced termination after the bounded timeout. This **does not prove rejection** by the upstream loader.
- The shell diagnostic used `grep` on the positive log, which reported **"binary file matches"** rather than showing any matching lines. No original guest-generated output was captured in the job logs, so **guest execution remains unverified**, even if the captured binary file might have contained it.
- The first job stopped on the invalid-control exit requirement before checking or reporting the positive guest marker.

The next revision retains **both failure statuses**, uses an NX2-authored binary-safe Python assessor with local unit regressions, reports all original guest progress markers regardless of the negative result, preserves raw positive/negative log files as a short-lived GitHub Actions artifact, and requires an explicit upstream loader-error diagnostic **plus prompt non-timeout termination** for the invalid input. It does not automatically treat any nonzero exit or a crash as successful rejection. The original loader, guest binary, source revisions and test acceptance threshold remain unchanged.

**No claim of guest CPU execution or correct malformed-input rejection can be made until that exact new run has completed and the captured logs are inspected.**

## Verified guest execution and second trial (2026-10-30)

**The original guest has executed.** [Exact-head run #41129791794](https://github.com/astraea-emu/nx2-lab/actions/runs/41129791794) built `bin/eden-cli` at **1443/1443** Ninja steps and executed the exact original public NeXo NRO from its pinned blob. Original guest-authored debug messages appeared through Eden's genuine `Kernel::Svc::OutputDebugString` in about **0.49 seconds**: introductory string, loader argument table `X1=0xFFFFFFFFFFFFFFFF`, counter **42**, successful heap allocation, heap sum **499500**, QueryMemory, GetInfo and Fibonacci(50) **12586269025**, plus the final guest message. This is independently confirmed unchanged **Switch 1-format ARM64 guest execution through Eden's CPU/loader/HLE**. It is **not** a Switch 2-native, graphics or commercial-game demonstration.

**Clean exit not verified on original guest:** the runtime immediately logged `Unable to find svcExitProcess in NRO; returning from main may fault`, and after the final guest debug string Dynarmic reported `Cannot execute instruction at unmapped address` around PC 0/4. The original NeXo startup code returns through LR, whereas Eden's NRO loader searches for an existing AArch64 `svc #7` opcode to set LR. The unchanged guest has no such instruction; its process timed out (124).

**Negative control failed separately:** the corrupted-magic NRO returned 137 (forced kill after its timeout) and its log had **zero bytes**. That is neither a clean rejection nor evidence that invalid magic was accepted. The next trial runs this control **first**, using an isolated home/config/cache directory, and reports any exact loader-stop diagnostic independently of the successful original guest.

**One labeled return-thunk adaptation:** the original NRO's text is 3,760 bytes, with unused zero padding to rodata at offset 4,096. An NX2-authored tool creates a **separate** copy with exactly one four-byte AArch64 `svc #7` instruction inserted at text offset 3,760, after verifying magic, bounds, alignment, empty padding and absence of an existing exit SVC. All other bytes and the original SHA-pinned guest stay unchanged. This lets Eden's existing return-address search resolve a guest-owned exit thunk, testing a clean process exit without misrepresenting the *unaltered* guest result. Independent synthetic mutation and rejection tests run before any expensive source build.

**Research-runner hardening and efficiency:** this branch adds the NRO preflight already qualified in merged [PR #29](https://github.com/astraea-emu/nx2-lab/pull/29), tests the original and adapted NRO against page-copy bounds, runs each guest in its own temporary XDG/HOME sandbox, captures three bounded binary logs, and uses a bounded ccache across subsequent frozen-source compiler attempts. This still does not patch Eden's C++ input loader. Negative control **must** promptly exit with an actual loader error to pass; guest debug output alone cannot satisfy the full PR gate.

## Next engineering decision

If the first CI run fails, read the original launcher or guest service logs and identify the **first specific blocker**. Improve the test only if evidence establishes a safe necessary correction, documenting the entire change. If the original NRO successfully executes, retain this as the frozen Switch 1 homebrew control and proceed to a genuinely Switch 2-facing source-owned image or API contract, with hardware observations as a separate authorized evidence lane. Issue #21 stays HOLD for engine selection until that stronger gate is met.
