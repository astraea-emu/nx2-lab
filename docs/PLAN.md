# Plan

## Objective

Build an NX2 emulator that earns its place through reproducible compatibility,
visual correctness, stability, performance and cross-platform support.
[Issue #50](https://github.com/astraea-emu/nx2-lab/issues/50) is the primary
delivery tracker.

This repository remains **NX2 Lab**: original guest fixtures, a small
CPU/memory oracle and external-engine regression tests. The eventual full
emulator belongs in a separate repository with its upstream Git history,
copyright notices and compatible licenses preserved.

## Active milestone: establish the full runtime

**First candidate:** a pinned, maintained Lichii revision. Compare Eglantine
and Orchid against it; use Fritchii as an additional game/performance reference.
This is a starting hypothesis, not an engine-selection verdict.

Acceptance:

1. Establish a reproducible full-engine checkout/build with documented source
   revision, dependencies, license review, host toolchain and working executable.
   Preserve the upstream implementation; do not copy selected files into this lab.
2. Run equivalent original ARM64 and graphics regressions on the candidate and
   an alternative. Record actual pass/fail, host exit, source revision, inputs,
   graphics driver and hardware. Keep loader negatives and cleanup failures visible.
3. Run one original multi-subsystem homebrew application with input, successive
   frames, audio, filesystem access and clean exit. Distinguish untested features
   from failures.
4. Record a justified engine decision and a reproducible first software defect.
   The next milestone is a measured compatibility or performance improvement
   over that exact upstream revision, without regressions.

No full NX2 emulator build, game-compatibility result or public release is
qualified yet. Do not call this milestone complete based on source inspection,
a renamed binary, green unit tests or a screenshot alone.

## Existing work

- [PR #46](https://github.com/astraea-emu/nx2-lab/pull/46): original GPU animation;
  **HOLD** for intermittent host shutdown despite successful frames.
- [PRs #47–#49](https://github.com/astraea-emu/nx2-lab/pulls): pinned modern-engine
  execution, graphics, loader and assertion diagnostics. Draft/unmerged;
  preserve the strict failed gates and reuse useful checks.
- [Issue #21](https://github.com/astraea-emu/nx2-lab/issues/21): animation and
  shutdown qualification, no longer the primary development objective.
- [Status](STATUS.md) separates merged evidence from the draft experiments.

## Working rules

Prefer one measured software problem and a small justified change over broad
feature work. Keep tests proportional to risk. After two focused attempts
without new evidence, reassess the blocker rather than adding more diagnostics.

Run inexpensive offline checks before expensive source-built engine trials.
Avoid cancelling long-running builds for documentation or diagnostic edits.
State exactly what passed, failed and was not tested; link the tested commit.
Do not merge work solely to clear a branch backlog.

Maintain one active delivery milestone. Update this plan only when evidence
changes the direction; put routine findings in the relevant issue. Source pins
and earlier failures remain in [Evidence](SOURCES.md). Follow
[Security](SECURITY.md) for authorized inputs and private data.
