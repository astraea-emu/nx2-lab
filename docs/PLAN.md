# Plan

## Mission and primary engine-qualification gate

NX2 aims to become a leading Nintendo Switch 2 emulator through **verified real
software compatibility, correctness, stability, performance and cross-platform
support**. This is an engineering goal, not a current claim. Use a mature,
properly licensed emulator foundation rather than rebuilding subsystems without
a demonstrated advantage. NX2 Lab currently provides reproducible original
guest workloads, not a standalone game-capable emulator.

Investigate the pinned Eden-NS2 baseline
`b2cef0c0f2e8517673233e22c929918e2c60e654` alongside Eglantine
`78743f30c251f66bd77e6eea6c28d8632d642d6f` and Lichii
`7afad5494e650edfc169624be54e606f54b079ec`. Preserve their original
GPL notices and separately review third-party dependencies. The
[engine ExeFS qualification](../.github/workflows/p0-engine-original-exefs.yml)
first verifies exact source and executes the **same project-authored ARM64
program plus malformed-loader control** with bounded host exit. It is an
initial compatibility observation, not final engine selection or proof of
commercial-game support. Keep old engine patches unapplied until justified.

Next carry unchanged original CPU, loader, IPC, VI2, GPU, clear-only and animated
workloads across the candidates. Distinguish test-adapter incompatibility from
engine defects; require natural process exit, negative controls, independently
checked pixels, resource ownership and repeated runs. After an engine qualifies,
advance to input-driven graphics, independent homebrew and legally obtained
real-game testing. Measure compatibility tiers, crash rate, p50/p95/p99 frame
times, shader stutter and RAM/VRAM, with real Windows/Linux/Apple Silicon
runtime qualification.

Keep [PR #46](https://github.com/astraea-emu/nx2-lab/pull/46) draft and
unmerged until its post-guest-exit shutdown failure is repaired and privately
reviewed under [Security](SECURITY.md). After two focused unsuccessful
diagnostic iterations, preserve its failure evidence and make progress on the
nonconflicting engine-qualification gate; never weaken acceptance to obtain
green CI. Reassess the primary engine choice after two measured unsuccessful
iterations, keeping the existing competitive radar as leads rather than proof.

## Held reliability gate: an original animated guest

Use the development revision selected by the [engine comparison](https://github.com/astraea-emu/nx2-lab/pull/45)
and recorded in [Status](STATUS.md). Advance the original static triangle to a
bounded animation that repeatedly submits GPU work and reuses display buffers.
Keep the existing static inputs and their exact captures as regressions.

## Acceptance

- Run an original ARM64 program with a deterministic sequence of changing
  vertices. The guest must submit native commands and execute its original
  shaders through the selected engine.
- Alternate two image buffers for a fixed sequence of at least four
  presentations, reusing each buffer. Observe release before changing or
  resubmitting it; check GPU completion,
  returned fences, VI2 ownership and presentation order.
- Capture selected completed frames and compare every pixel with an independent
  expected image. Require distinct correct frame states and reject stale images,
  wrong frame order and premature buffer reuse. A counter alone is insufficient.
- Bound the workload, preserve the first failure, release every acquired resource
  and exit naturally. Repeat with verified engine reuse and fresh evidence.
- Add an animation option to the existing runner and document one command.
  Editing the original vertex sequence must change the motion and captures.
- Preserve the static triangles, clear-only, CPU images, loader/META, SM, VI2
  and strict 62-case GPU controls. Keep both DMA exclusions and the existing NRO
  return fault and malformed-input assertion explicit.

After animation passes, add one input interaction to the same program. Then
choose the next original workload from the first demonstrated limitation.
Do not expand the small CPU/memory oracle unless a concrete discrepancy needs it.

## Limits before general use

Production adoption remains **HOLD**. Fix and regression-test malformed-NRO
parser bounds, establish host containment, review dependency licenses, and
qualify the relevant host runtime platforms. Missing-service placeholders must
be treated as unsupported behavior, not evidence of working services. The
candidate's broader shader lowering also needs coverage beyond our small scene.
There are no verified commercial games or physical Switch 2 measurements.
HBX stage 2 remains a [secondary regression](https://github.com/astraea-emu/nx2-lab/issues/20).

## How decisions change

Keep one primary milestone. Review the path when it passes or after two
focused iterations fail to advance it; record the baseline, evidence, options
and decision in [#21](https://github.com/astraea-emu/nx2-lab/issues/21).
A reproduced safety or licensing conflict triggers immediate review. Revisit
allocation and outstanding evidence every four weeks without resetting the mission.

The weekly [radar](../.github/workflows/competitive-radar.yml) records selected
public GitHub metadata in one issue. Commits, stars, screenshots and upstream
claims are research leads; they do not prove compatibility. Defer unrelated
surveys and strategy documents until they inform a measured comparison.
Research follows [Security](SECURITY.md).
