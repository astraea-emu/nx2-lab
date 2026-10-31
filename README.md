# nx2-lab

**Independent, clean-room Nintendo Switch 2 security research and emulation foundations.**

> **Status (2026-10-31): emulator-runtime qualification in progress.**
> NX2 has independently exercised source-authored Switch 1-format homebrew in
> external runtimes, built Eden-NS2's CPU/HLE/GPU libraries, and reproduced and
> verified an isolated repair for a native-metadata classification bug.
> Its synthetic extended-ExeFS guest has now emitted debug output and exited
> cleanly in the patched Eden runtime, with a terminating malformed-NPDM control.
> The original ARM64 service-manager IPC extension is awaiting its real runtime
> result; the corrected combined acceptance is still pending. See [measured
> results and pending gates](docs/STATUS.md). Production-engine selection remains
> HOLD. No hardware-backed Switch 2 ABI, guest-produced frame, commercial game
> support, or exploit is established.

## Current direction — one evidence-driven gate

The primary milestone is [#21: qualify a mature emulator runtime or upstream-first path](https://github.com/astraea-emu/nx2-lab/issues/21), with a reproducible, lawful source-owned workload. HBLauncher stage 2 ([#20](https://github.com/astraea-emu/nx2-lab/issues/20)) remains a bounded research regression, not the primary product milestone.

**Do not replan merely because a new competitor repo or screenshot appears.**
Follow [Adaptive Strategy: decision rules, evidence thresholds and review cadence](docs/ADAPTIVE_STRATEGY.md). The [weekly metadata-only competitive radar](.github/workflows/competitive-radar.yml) tracks selected public repositories and updates one issue; it never decides architecture or automatically changes the codebase.

See the [October 30 competitive architecture audit](docs/COMPETITIVE_ARCHITECTURE_AUDIT_2026-10-30.md) and [live status](docs/STATUS.md). The tiny interpreter is a correctness oracle; it must not grow into a new whole-console implementation without an independently measured reason.

## Why a separate project?

Astraea is a PS5 compatibility research emulator. This repository targets
Switch 2 research and eventual emulation without sharing proprietary content,
untested system-service guesses, or incompatible third-party code. The
security-research and emulator workstreams are related but **independently gated**.

## Quick start

These commands build the small **NX2-owned CPU/memory correctness oracle**.
The external runtime qualification workflows are separate and listed in
[live status](docs/STATUS.md).

CMake 3.25+ and a C++23 compiler:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/nx2lab demo
./build/nx2lab memory-demo
./build/nx2lab run-owned fixtures/owned-aarch64-demo.nx2o
./build/nx2lab run-owned fixtures/owned-aarch64-service.nx2o
python3 tools/verify_evidence.py evidence/owned-aarch64-fixture.json
```

On Windows, run the `nx2lab` executable under `build/Debug/` if using a multi-config generator.
The `run-owned` command loads and executes a **28-byte, strictly parsed,
source-owned NX2OWNED v1 program image**. This is an NX2 Lab testing format,
not a Nintendo NSO/NRO/NCA/XCI format or a Switch 2 execution route.

The `demo` command executes **two independently authored generic AArch64 instructions**
(`MOVZ x0, #42; ADD x0, x0, #1`) and stops before `BRK` is retired; `x0=43`.
A second source-owned fixture exercises 64-bit STR/LDR with a checked guest-memory region and fault tests.
A third source-owned NX2OWNED file stops at a generic AArch64 `SVC #0x1234`
request, preserving its caller state and leaving all service dispatch disabled.
Unit tests separately prove that an explicit *mock fixture* reply can
resume this stopped test program, then execute one more instruction. This is
not an observed Horizon/Switch 2 call ABI, real exception return, or host syscall.
No external console, firmware, ROM, keys or exploit are needed.

## Structure

- `include/nx2/`, `src/` — bounded, source-owned CPU instruction, guest-memory and owned-image research.
- `tests/` — positive and negative executable tests.
- `fixtures/` — source-authored tiny AArch64 words only.
- `tools/reference/` — source-pinned external-runtime probes, input generators,
  log assessors and malformed-input checks; external implementations stay outside this tree.
- `evidence/` — evidence manifests and a strict verifier.
- `docs/STATUS.md` — live established capabilities versus unknowns.
- `docs/PLAN.md` — gated research, debugger and emulator priorities.
- `docs/SOURCES.md` — public evidence, date, confidence, license boundaries.
- `docs/SECURITY.md` — safe lab policy and scope of controlled experiments.
- `docs/RESEARCH_INTAKE.md` — evidence classifications for published exploit,
  homebrew and firmware observations without unauthorized hardware actions.
- `docs/PUBLISH.md` — publish this local Git repository without discarding history.

## Principles

1. Real workload progression over PR/test counts.
2. Distinguish generic ARM ISA behavior from Switch 2 hardware facts.
3. Keep **public** evidence and **authorized local** observations separate.
4. No Nintendo firmware, keys, copyrighted binaries, decrypted games or
   device-identifying data in Git or public CI.
5. No blind import of GPL-only emulator code into this MIT-licensed repository.
   Review license provenance before depending on any external engine.
6. No false playable-game, kernel-exploit or persistent-CFW claims.
7. Guest execution uses the ordinary CI runner account, without a console.
   Build dependencies are installed separately in disposable CI environments.

## Research direction

**Track R — responsible device research:** external research inventory,
firmware/host compatibility matrices, reproducible *non-invasive* probes,
validated log/evidence formats, and analysis of already published observations.
Do not assume that the public ns2jb proof of concept gives kernel or persistent
execution. Avoid running unreviewed third-party hardware tools or weakening
host security solely to chase early demos.

**Track E — emulator foundation:** bounded AArch64 CPU state and memory,
selected user-mode HLE contracts, independent homebrew programs, Horizon IPC,
GPU command/shader evidence and ultimately presented guest frames.
Only make a Switch 2 compatibility claim after measuring the real device ABI
and independently verifying behavior.

Read `docs/PLAN.md` before expanding the implementation. Contributions are
welcome via small, independently verifiable patches.

## License

MIT for original nx2-lab code and documentation, unless marked otherwise.
No affiliation with Nintendo, NVIDIA, or any external jailbreak/emulator team.
