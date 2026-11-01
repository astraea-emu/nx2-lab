# Plan

## Milestone: an original animated guest

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
