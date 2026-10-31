# Research and emulation roadmap — dependency gates, not dates

## Project position

Astraea and NX2 Lab are independent. This project should not repeat the
mistake of accumulating a long list of isolated components without progressing
one frozen executable. The initial goal is to be useful to developers long
before a Switch 2 commercial game boots.

## Active gate — strict native-GPU qualification within #21

The Eden NRO lifecycle control in [#28](https://github.com/astraea-emu/nx2-lab/pull/28)
and the synthetic extended-ExeFS lifecycle/guest-checked service-manager control
in [#32](https://github.com/astraea-emu/nx2-lab/pull/32) have passed and merged.
The [actual combined runtime run](https://github.com/astraea-emu/nx2-lab/actions/runs/41233784596)
verified baseline status **0**, invalid-META rejection status **1**, and IPC
status **0** with all 21 observed guest fields, handle cleanup and real process
exit. All seven PR #32 checks passed at the tested head. [Live status](STATUS.md)
records the exact revisions and remaining limits. Production-engine selection
remains **HOLD**.

The active next #21 slice is strict native-GPU qualification under
[Adaptive Strategy](ADAPTIVE_STRATEGY.md). The existing test exclusion removes
31 cases in one native-GPU file: eight concern MME and 23 cover other GPU
behavior. Source review identifies **29 restoration candidates**: 24 cases
without the stale interpreter interface and five with bounded compatibility
adaptations. These are not full-runtime passes. Two DMA cases require an
explicit contract decision because their ownership and size policy changed;
preserve those unresolved expectations instead of weakening them to obtain
green CI.

Restore the declared scope with exact-source guards and preserved assertions.
Execute the actual linked target with `EDEN_NATIVE_STRICT=1`, record the case
inventory and first actual failure, and keep any remaining exclusions explicit.
A source review or temporary interpreter probe does not qualify the integrated
target. The [31-case reconciliation audit](research/eden_native_gpu_test_reconciliation_2026-10-31.md)
defines the exact source and adaptation boundaries for this implementation.

This order follows the frozen runtime's behavior: its
[QMD scheduler](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/native_qmd.h)
can otherwise skip unsupported shader work and still report completion.
Choose the next guest graphics/display workload from the measured results and
require actual image readback before claiming a frame. The observed NRO
crypto assertion and original loader bounds remain supporting robustness
repairs and production blockers; no evidence currently puts that crypto
failure on the controlled ExeFS path. Device ABI fidelity requires independent
hardware observations or authoritative public ABI evidence.

The E-lane below is the long-term dependency map. It does not authorize
rebuilding an entire CPU/HLE/GPU stack independently of the qualified-engine
comparison. HBX stage 2 remains a bounded secondary regression.

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
  Independent external homebrew has since been exercised through separate
  NeXo/Eden research builds; never substitute these mock semantics for Horizon. The
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

## Earlier portfolio time allocation proposal

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
