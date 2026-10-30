# NX2 Lab — Live Status (2026-10-29)

## Implemented and tested

- Portable, bounded, source-owned AArch64 CPU sample: 64-bit MOVZ and ADD
  immediate (excluding unmodelled SP forms), NOP and pre-retirement BRK.
- A typed unsupported-instruction, instruction-budget and fetch-fault path.
- A generic AArch64 SVC immediate decode and typed **pre-retirement** service
  request stop. Caller registers, PC and memory stay unchanged by the SVC.
  No host syscall, service dispatch or Nintendo ABI interpretation occurs.
  Unsupported HVC/SMC and budget boundaries are regression-tested.
- A **separate, explicitly approved, fixture-only reply** can advance the
  saved SVC stop to the next source-owned instruction and supply a synthetic X0
  return, after checking original instruction bytes and matching immediate.
  This models neither a real OS exception return nor any Horizon service.
- A 64-bit, little-endian source-owned guest-memory R/W experiment, with full-range
  checks, read-only/write-only denial, refused overlapping and partial mappings,
  overflow negatives, and pre-retirement typed data-access faults.
- Generic AArch64 64-bit STR/LDR unsigned-offset fixture (offset 0 or scaled by 8)
  with checked guest-memory effects; the encodings were independently checked
  using a generic AArch64 assembler. No Switch 2 MMU/Horizon semantics.
- No host IO, syscalls or elevated privileges in the CPU interpretation sample.
  The separately bounded CLI reads only a local NX2OWNED fixture file.
- Offline, size- and path-bounded owned-fixture SHA-256 evidence verifier.
- CMake/CTest and a GitHub Actions cross-platform CI **configuration**.
- Research-only pinned Dynarmic AArch64 JIT qualification (PR #3): a separate
  Linux CI job builds exact public revision `a46601580d5512d324104f985b5f0209dc980ddc`
  with its recorded submodules and executes original MOVZ/ADD/NOP and
  MOVZ/STR/LDR prefixes. All 31 GPRs, PC and guest-memory readback match
  the tiny owned oracle; the exact SVC boundary remains unexecuted.
  A source-owned four-case denied-access matrix now checks read-only stores,
  unmapped stores, boundary-crossing stores and write-only loads. The tiny
  interpreter supplies typed reference faults; the research JIT callback
  rejects unauthorized private memory effects and discards all post-denial
  CPU state without claiming a precise JIT fault or a production sandbox.
  A separately frozen source-owned `SVC #0x1234` fixture now reaches the
  actual Dynarmic JIT callback exactly once with no host dispatch or guest
  memory effects. Post-callback JIT state is deliberately not published:
  the research callback is neither a genuine Horizon service nor an
  authenticated ARM exception-return contract. This is **not** a precise guest fault or an approved
  production CPU backend; licensing and hostile-worker containment remain
  separate acceptance gates.
- **E2 independently authored ARM64 ELF prefix:** a pinned MIT-licensed
  Linux ARM64 assembly program is compiled to ELF64 in isolated CI. Its
  original RX PT_LOAD is extracted into the bounded NX2OWNED test envelope,
  with the original PC-relative 64-bit LDR literal pointer independently
  checked against the exact message in a separate nonexecuting data PT_LOAD.
  The same external source bytes now retire **four genuine instructions**
  (MOVZ/LDR-literal/MOVZ/MOVZ), then stop before original `SVC #0`.
  Two identical runs, a pinned source blob, sixteen malformed-ELF negatives
  and source-owned signed-offset/64-bit read fault tests are required.
  No actual Linux syscall, Nintendo/Horizon service or graphical output is
  performed; this is not a general ELF loader or game/homebrew compatibility.
  **Merged research-only mock continuation (#9):** the exact pinned
  external first `SVC #0` is *not dispatched*; a source-verified, read-only,
  14-byte guest message is checked through the existing 64-bit guest-memory
  facade, and an explicitly authorized fixture reply returns 14 in X0. The
  unchanged program then retires two more original instructions and stops
  before its second `SVC #0` (`X8=93`, original Linux exit request).
  This models six original instruction retirements and zero host syscalls;
  neither the first nor second SVC is actually retired. Ten source-owned
  tamper negatives plus a changed external-message sidecar are refused.
  It is **not** a real Linux write, exit, Horizon OS service or Nintendo run.
- Three host-only demonstrations, including a 28-byte NX2OWNED v1 standalone
  executable image with strict header/count/entry validation, and four
  SHA-256 evidence manifests. Thirteen local CTest groups pass on Linux.

## Not implemented

- Any Nintendo format parser (NSO/NRO/NCA/XCI), Switch 2 memory manager,
  CPU extensions, real ABI, Horizon process loader,
  kernel/Horizon implementation, HIPC, GPU, graphics, input, sound, saves,
  game compatibility, console-side probe, any jailbreak or firmware handling.
- Full Switch 2 / Horizon device ABI, runtime and commercial compatibility still require independent evidence. GitHub's core Linux/Windows/macOS/sanitizer CI was repaired and passed on main (PR #1).

## Current public landscape

- Original ns2jb: https://gitlab.com/pepsipu/ns2jb — research-only,
  tethered; no kernel access/persistent CFW demonstrated.
- oboromi: https://github.com/0xNikilite/oboromi — Rust Switch 2 emulator
  foundation; publicly says no commercial games or firmware run.
- Pound: https://github.com/pound-emu/pound — Switch-family architecture
  research and Ballistic CPU JIT effort; no published Switch 2 game run.

## Original HBX stage-1 guest execution (verified PR #16 exact-head research)

A research-only pinned Dynarmic adapter now attempts to run the original
HBLauncher `hbx_app_main` AArch64 instructions with an independently prepared,
source-defined HBX v3 context, immutable original RX code, separate RW data/BSS,
and a bounded guest stack. Only an exact `HBX_OK` stage-1 return and
source-defined `HBX_ERR_ABI` negative returns can be accepted; unauthorized
memory faults, service requests and missing returns fail closed. Stage 1
**bypasses the SDK `_start` trampoline** by directly entering the original
function. The pinned PR-head E3 CI executed **777 original AArch64 instruction steps**
before a verified `HBX_OK=0` stage-1 return, twice independently.
Three wrong source-defined context fields produced `HBX_ERR_ABI=2`;
unmapped pointers, denied writable stack, invalid entry and instruction budget
were rejected. Original code/data image SHA-256 values were checked.
No native host service, Nintendo Horizon service or console was invoked.
**This is not yet a full HBX app launch, Switch 2 Horizon implementation,
or game.** Full original `_start` entry/return semantics remain unproven.
An independently compiled QEMU AArch64 reference now executes the **same
original HBLauncher app object** used by the NX2 Dynarmic guest adapter.
Exact source-defined stage-1 results matched for valid context and invalid
magic/version/size (0/2/2/2); 777 original instructions retired in NX2.
The QEMU comparison is **host-only** and directly enters the C function;
it does not prove the full `_start` trampoline or real Horizon/device ABI.

## First native-facing independent research target (host-only)

A pinned HBLauncher SDK v3 source revision and original host/QEMU AArch64
trampoline/runtime tests have a **reproducible opt-in CI lane**.
NX2 independently validates the frozen custom HBX context layout and
18 malformed or mutated ABI negatives. This is a *third-party host test
reproduction*, not an NX2 emulator executing HBLauncher, not Nintendo
Horizon ABI, and not a physical console observation. Accept it as a host-only result **only when** exact-head pinned CI passes;
never promote it to real Switch 2 execution. See
[research intake](research/hblauncher_host_abi_2026-10-29.md).

## Strategic direction (October 29)

[Evidence-first strategy](STRATEGY_2026-10-29.md) makes a cross-project
compatibility/conformance corpus the next critical deliverable. The present
external executable is **Linux ARM64**, not Switch 2 homebrew. No Nintendo
system service, real hardware ABI, exploit, or game has been reproduced.
Preserve current CPU tests as an independent correctness oracle and keep
Dynarmic on HOLD until faults, licensing and host constraints are qualified.

## Next accepted work

1. Freeze a public source/claim matrix for Switch 2 compatibility mode and
   select one independently reproducible native-facing homebrew input.
2. Produce a versioned cross-backend trace and conformance runner with
   positive/negative tests; seek one external contribution or reproducibility
   review, instead of extending the tiny ARM64 interpreter by default.
3. Complete the Dynarmic ACCEPT/HOLD/REJECT evidence gate (#2) without
   publishing untrusted post-fault JIT state.
4. Keep the six-instruction Linux ELF/mock route as generic research only;
   do not promote its service returns as Horizon semantics.
5. Any device/vulnerability experiments require explicit authorization,
   controlled non-destructive scope and private coordinated disclosure.
6. Protect main with checks when repository administration permits.

