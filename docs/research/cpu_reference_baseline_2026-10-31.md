# CPU reference baseline — October 31, 2026

**Historical host-only record.** Preserved from [the October 31 status snapshot](https://github.com/astraea-emu/nx2-lab/blob/1b2259be4816306c8fa14a22a6255b54b6004f0a/docs/STATUS.md).
These controls underpin the small NX2 correctness oracle and separate external
CPU experiments. They do not select a production CPU backend or establish
Nintendo device behavior. See [current status](../STATUS.md) and the
[active plan](../PLAN.md) for later runtime work.

## Recorded CPU and memory controls

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

## Reproduction sources

- [Core build and CTest definitions](../../CMakeLists.txt), [original fixtures](../../fixtures/) and [evidence manifests](../../evidence/).
- [Pinned Dynarmic qualification](../../.github/workflows/e1-dynarmic-research.yml) and its [original adapter](../../tools/reference/dynarmic/).
- [External ELF qualification](../../.github/workflows/e2-external-aarch64.yml) and its [profiling and continuation tools](../../tools/reference/external_arm64/).
- Later custom-ABI guest work: [HBX original execution record](hblauncher_original_guest_2026-10-29.md).
