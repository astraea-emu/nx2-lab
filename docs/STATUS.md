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
- Three host-only demonstrations, including a 28-byte NX2OWNED v1 standalone
  executable image with strict header/count/entry validation, and four
  SHA-256 evidence manifests. Thirteen local CTest groups pass on Linux.

## Not implemented

- Any Nintendo format parser (NSO/NRO/NCA/XCI), Switch 2 memory manager,
  CPU extensions, real ABI, Horizon process loader,
  kernel/Horizon implementation, HIPC, GPU, graphics, input, sound, saves,
  game compatibility, console-side probe, any jailbreak or firmware handling.
- No external CI run until a hosted GitHub repository is created.

## Current public landscape

- Original ns2jb: https://gitlab.com/pepsipu/ns2jb — research-only,
  tethered; no kernel access/persistent CFW demonstrated.
- oboromi: https://github.com/0xNikilite/oboromi — Rust Switch 2 emulator
  foundation; publicly says no commercial games or firmware run.
- Pound: https://github.com/pound-emu/pound — Switch-family architecture
  research and Ballistic CPU JIT effort; no published Switch 2 game run.

## Next accepted work

1. Establish a clean public repository with required tests and MIT license.
2. Accept a generic ARM64 CPU backend **only** after independent instruction
   correctness and license verification. Do not hand-code the whole ISA.
3. The source-owned executable-image path now reaches an unretired SVC stop
   and a separately allowed **mock fixture** can continue to a subsequent BRK.
   Next, qualify a maintained ARMv8 CPU backend against these frozen register,
   service/fault and guest-memory examples. Do not expand this tiny interpreter
   into a general ARM CPU or claim Nintendo service compatibility.
4. Add real Switch 2 compatibility claims **only** when supported by separately
   attributable hardware/public evidence and legally acceptable tests.
