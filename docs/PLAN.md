# Research and emulation roadmap — dependency gates, not dates

## Project position

Astraea and NX2 Lab are independent. This project should not repeat the
mistake of accumulating a long list of isolated components without progressing
one frozen executable. The initial goal is to be useful to developers long
before a Switch 2 commercial game boots.

## R-lane: console security research (opt-in and controlled)

- **R0 — provenance and threat model:** inventory original research sources,
  distinguish firmware-specific results from rumors; audit tool licenses,
  host privileges and device effects. No device changes required.
- **R1 — safe observation protocol:** fixed JSON schema for authorized local
  measurements, source hashes, firmware and environment; avoid publishing
  identifying material or private binary captures.
- **R2 — userland/homebrew evidence:** independently authored, minimal
  non-destructive device probes only after obtaining informed hardware consent
  and reviewing risks. No third-party kernel extension or SIP change by default.
- **R3 — disclosure and repeatability:** report bounded failures and negative
  tests to upstream researchers; protect discoveries appropriately.

## E-lane: emulator foundation

- **E0 — deterministic owned ARM64:** a tiny source-authored interpreter,
  explicit guest-memory permissions, typed stops and negative tests (implemented
  generic proof; NOT a Switch 2 emulator). Keep this small as a semantic oracle.
- **E1 — qualified CPU backend:** evaluate a maintained ARMv8/AArch64 JIT for
  correct guest memory, interrupts, faults and portability; use independent
  tests and ensure license compatibility. Preserve E0 as a tiny oracle.
- **E2 — source-owned process/IPC:** strict owned test-image parsing and
  checked guest memory are implemented as generic exercises; the source-owned SVC instruction now stops before retirement; a **mock-only**
  continuation contract checks the immutable word/immediate, supplies an
  explicitly selected fixture return, and advances to the next instruction.
  Next evaluate a maintained AArch64 backend and eventually independently
  authored external homebrew; never substitute mock semantics for Horizon. The
  NX2OWNED envelope is NOT a Nintendo executable format.
- **E3 — homebrew runtime:** only observed Horizon semantics/IPC, real homebrew
  memory/events/filesystem/input, scoped to an exact source revision.
- **E4 — graphics:** validated GPU command and shader evidence -> typed IR ->
  SPIR-V/Vulkan; source-owned deterministic readback before presentation.
- **E5 — guest-produced frame:** owned homebrew executes CPU, dispatches
  necessary services and generates a presentable image. No host-drawn oracle.
- **E6 — commercial C0/C1:** lawfully accessible, authorized local executable
  read-only profile; first instruction only after verified ABI, source
  provenance and containment. Game/render claims are separate evidence gates.

## Portfolio time allocation proposal

For the next focused sprint, NX2 Lab 70%, Astraea 20%, ecosystem contribution/
communication 10%, with an explicit re-evaluation when an objective milestone
is reached. Never interpret this allocation as forecast delivery dates.

## Every PR must answer

1. Which exact observed stop is being removed?
2. What source evidence justifies the behavior?
3. What positive and negative tests prove it?
4. Does a real source-owned workload advance further?
5. What still remains unsupported?

No gameplay or persistent jailbreak promotion without a reproducible artifact
and independent evidence. Screenshots alone do not count.
