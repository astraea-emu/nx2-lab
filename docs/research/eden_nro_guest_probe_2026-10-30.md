# Issue #21 — Eden-NS2 bounded source-authored NRO execution experiment

**Status: bounded NRO lifecycle control complete; PR #28 merged. The stricter [run #41229946626](https://github.com/astraea-emu/nx2-lab/actions/runs/41229946626) passed at head `3764f74101ad87f3009e7d75d0029d66cd4b63db`, using the isolated process/SDL lifecycle overlay. The original guest still times out after its return-to-null fault; the labeled return-thunk variant exits naturally; malformed magic is rejected with an ordinary failure exit but a preceding AES-probe assertion. See the final strict-run record below for the exact scope.**

## Why this probe

The merged [PR #27](https://github.com/astraea-emu/nx2-lab/pull/27) established that Eden-NS2's integrated CPU, loader, Horizon HLE and GPU libraries build (with one narrowly documented upstream Clang cast correction), and that 33 *included* upstream graphics-related test cases pass. That does **not** establish guest execution. The 31 cases in one excluded native-GPU test translation unit remain unqualified because its MME tests use obsolete APIs; [eight are MME-related and 23 cover other GPU behavior](eden_ns2_full_build_gate_2026-10-30.md).

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
3. The unchanged original homebrew produces `Hola desde un NRO en NeXo 2!` in a log line attributed to `Debug.Emulated / core/hle/kernel/svc/svc_debug_string.cpp / OutputDebugString`. Later guest messages, its known return-to-null fault and bounded timeout are reported independently. This control proves instruction execution only; it does not qualify natural completion. A host echo cannot supply guest-output evidence.
4. The separate four-byte return-thunk variant must produce the original introduction, counter **42**, heap sum **499500**, Fibonacci(50) **12586269025** and final message in order through the genuine debug SVC. A genuine `Kernel.SVC / svc_process.cpp / ExitProcess` event must follow. Its process must return **0**, with no guest execution fault or assertion. A final message followed by timeout, crash or missing exit SVC fails this gate.
5. The corrupted-magic control must emit the frozen frontend's typed loader error, return exactly **1** (`SDL_APP_FAILURE`) and produce no guest output. Other nonzero exits, including shell-encoded signals, do not prove terminating loader rejection. Assertion/fault diagnostics in this control are reported separately; the observed crypto-probe assertion below remains an unresolved loader limitation.

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

## Adapted return-thunk result and source-pinned process/SDL lifecycle experiment (2026-10-31)

[Exact-head CI #41133494325](https://github.com/astraea-emu/nx2-lab/actions/runs/41133494325) confirmed that the four-byte **separately labeled** NRO return-thunk variant preserves all original guest output and reaches the **real Eden `Kernel::Svc::ExitProcess` handler** (`Process 81 exiting`). However, the runner returned timeout code **124**, and the emulator subsequently logged repeated invalid guest instructions, producing a **10.4 MB diagnostic file**. The malformed-magic trial remained empty-logged and force-killed (code **137**) even when executed **first** in its own sandbox. Therefore this revision failed the complete acceptance gate, notwithstanding the genuine guest SVC exit request.

The upstream source identifies a causal problem beyond the original guest: frozen [`src/core/hle/kernel/svc/svc_process.cpp`](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/kernel/svc/svc_process.cpp) logs `ExitProcess` and calls only `system.Exit()`. Frozen [`src/yuzu_cmd/yuzu.cpp`](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/yuzu_cmd/yuzu.cpp) registers `state->system.RegisterExitCallback([] {});`, an empty callback, so this standalone CLI does not actually terminate the original guest or close the window upon ExitProcess. Its unconditional `SDL_AppQuit` shutdown after an uninitialized/invalid application is an additional **hypothesis** for the empty malformed-input logs; not a confirmed cause.

To test this while preserving original source provenance, the next revision applies `tools/reference/eden_ns2/overlay_eden_exit.py` **only to the ephemeral GPL checkout**. Original Git blobs `af1bdc7807e0f2c51aeee6edf1c8436b2c892bba` (`svc_process.cpp`) and `76a1dcd312686059cf2399843a5dc15454f15526` (`yuzu.cpp`) must match before edits. The overlay makes the genuine ExitProcess path call the existing `KProcess::Exit` and exposes a thread-safe atomic guest-exit request to the SDL event loop, while conditioning frontend full shutdown on `IsPoweredOn()`. This is a *candidate repair*, not a verified fix. Original CLI behavior from the earlier unpatched run remains a separate and immutable control, not represented as passing. An NX2-owned six-test source-overlay suite must pass before the expensive source build.

**Do not claim clean exit or malformed-image rejection until the patched exact-head run demonstrates each independently.** Even a passing result would be a **patched frozen Eden fork**, and only for Switch 1-format original homebrew, never a Switch 2-native title/game.

## Verified lifecycle result and stricter regression acceptance (2026-10-31)

[Run #41223767907](https://github.com/astraea-emu/nx2-lab/actions/runs/41223767907), job `124603611364`, completed the full patched Eden build and all three independent trials at commit `09defff733d97b8e33d25714bda2019c3cac2a10`:

| Input | Observed behavior | Process result |
| --- | --- | --- |
| Exact original NeXo NRO | Original introduction, computations and final message; then the known return-to-null guest fault | **124**, bounded timeout; execution evidence only |
| Separately labeled return-thunk NRO | All original computations and final message; real `Kernel::Svc::ExitProcess`; no unmapped-PC fault | **0**, natural exit |
| Corrupted NRO magic | `Core / core.cpp:339:Load: Failed to load ROM (Error 35)!`; no guest output; preceding crypto-probe assertion | **1**, terminating loader rejection; not assertion-free parsing |

This establishes a successful bounded lifecycle experiment for the **patched frozen Eden build**. It does not establish a successful unmodified NRO return path or independently qualify every part of the overlay. Replaying the raw artifact (SHA-256 `6e1b9afbdd9982b386daee5066dbf966119bea30c2b2dc173c8a1bd8e0179fdb`) also exposed `core/crypto/aes_util.cpp:97` asserting `EVP_CipherInit_ex2` during malformed-magic identification. Frozen [`loader.cpp`](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/loader/loader.cpp) probes NCA after NRO magic fails, before filename fallback selects the NRO loader. The control therefore proves rejection and ordinary failure exit, **not assertion-free malformed-input handling**. This diagnostic remains visible and requires separate loader robustness work; it does not occur in the successfully adapted guest.

Review found that the old workflow printed the adapted return code without requiring it and accepted any positive malformed-input status except 124/137. Thus a future timeout after guest output or a crash after a loader diagnostic could have appeared green. The revised workflow uses a separately tested `assess_adapted_nro.py`, requires natural adapted exit plus the real ExitProcess event, and rejects faults/assertions. `assess_eden_guest.py` now checks genuine debug-SVC provenance and requires exact negative-control status 1. Unit regressions include the previously observed exit-then-timeout behavior, loader-error-then-crash, host marker echoes, missing ExitProcess, incorrect computation, and the native experiment's priority assertion shape. Existing source hashes, guest bytes and lifecycle overlay remain unchanged. The previous successful run remains evidence for its own commit; the stricter revision subsequently passed in the independent run recorded below.

## Final strict-run acceptance — October 31

[Run #41229946626](https://github.com/astraea-emu/nx2-lab/actions/runs/41229946626)
passed the strengthened runtime acceptance at PR head
`3764f74101ad87f3009e7d75d0029d66cd4b63db`. All seven checks for that head passed,
and [PR #28](https://github.com/astraea-emu/nx2-lab/pull/28) merged as
[`79186b80102555f7362a178d68fab7ef21e0e274`](https://github.com/astraea-emu/nx2-lab/commit/79186b80102555f7362a178d68fab7ef21e0e274).

| Control | Final measured result | Scope |
| --- | --- | --- |
| Exact original NRO | Guest computations observed; return-to-null fault; status **124** | Original instruction execution, not natural completion |
| Labeled four-byte return-thunk variant | Ordered guest computations, genuine `ExitProcess`, no execution faults/assertions, status **0** | Successful bounded lifecycle in the patched frozen runtime |
| Corrupted-magic NRO | Typed loader rejection, no guest output, status **1**, preceding AES-probe assertion | Terminating rejection, not assertion-free loader handling |

This closes the NRO lifecycle control. It does not repair the original guest's
return limitation, resolve the malformed-input AES assertion or original loader
bounds concerns, establish Switch 2-native ABI fidelity, or qualify graphics,
gameplay or a production runtime. The earlier failed experiments above remain
evidence of their own source/input revisions.

## Next engineering decision

Retain the completed NRO experiment as the frozen Switch 1-style homebrew control. The next active workload is the source-authored extended-ExeFS route in [PR #32](https://github.com/astraea-emu/nx2-lab/pull/32); its result must be measured independently. Loader robustness remains open, and hardware observations remain a separate authorized evidence lane. Issue #21 stays HOLD for production-engine selection until its stronger workload, safety and compatibility conditions are met.
