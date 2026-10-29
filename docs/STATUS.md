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

## Next accepted work

1. Main's four CI jobs have passed. Protect main with required checks via repository administration when available; do not block useful research on a missing admin action.
2. Accept a generic ARM64 CPU backend **only** after independent instruction
   correctness and license verification. Do not hand-code the whole ISA.
3. The source-owned executable-image path now reaches an unretired SVC stop
   and a separately allowed **mock fixture** can continue to a subsequent BRK.
   Next, qualify a maintained ARMv8 CPU backend against these frozen register,
   service/fault and guest-memory examples. Do not expand this tiny interpreter
   into a general ARM CPU or claim Nintendo service compatibility.
4. Add real Switch 2 compatibility claims **only** when supported by separately
   attributable hardware/public evidence and legally acceptable tests.
