# Plan

## Milestone: edit a sample and verify its frame

A developer can modify an included original graphical guest, build and run it
with one documented command, and inspect a real captured frame checked against
an independent pixel reference. Reuse the external engine build on subsequent
runs and measure setup/repeat times.

The first presentation checkpoint is verified in [Status](STATUS.md): an
original ARM64 guest draws a checkerboard, presents it through the pinned Eden
Vulkan renderer, and exits cleanly. Both guest colour variants match every
captured pixel. The [local command](../CONTRIBUTING.md#original-image-trial-linux)
reuses an already-built engine; automatic engine setup remains incomplete.

Production adoption remains **HOLD** under
[#21](https://github.com/astraea-emu/nx2-lab/issues/21). The CPU, IPC and native
unit checks support this sample; additional coverage must resolve a measured
blocker or protect behavior the sample needs.

## Next implementation: make the sample easy to reproduce

Provide one Linux command that obtains the pinned engine, applies the existing
verified repairs, builds it and runs the image trial. Reuse the existing
workflow's build procedure without maintaining two independent configurations.
A second invocation must reuse the engine, create fresh captures and check the
same pixels. Record actual setup and repeat times, source/input/capture hashes,
and process results. Keep all generated state outside tracked source files.

Keep the existing acceptance checks: original guest-generated pixels,
independent complete-image comparison, changed-colour negative controls,
capture completion before cleanup, all resources released and natural exit.
No additional engine changes are needed unless reproduction exposes a failure.

This qualifies a presentation path. Guest GPU shader execution, 3D correctness,
physical Switch 2 ABI fidelity and game compatibility remain unverified.
The excluded DMA contracts need resolution if a sample reaches them.
Malformed-NRO parsing, host containment and cross-platform runtime coverage
remain production blockers in [Status](STATUS.md). HBX stage 2 is a
[secondary regression](https://github.com/astraea-emu/nx2-lab/issues/20).

## How decisions change

Keep one primary milestone. Review the path when it passes or after two
focused iterations fail to advance it; record the baseline, evidence, options,
falsifiable comparison and decision in the existing issue. A reproduced
safety or licensing conflict triggers immediate review. Revisit allocation
and outstanding evidence every four weeks without resetting the mission.

The weekly [radar](../.github/workflows/competitive-radar.yml) records selected
public GitHub metadata in one issue. Commits, stars, screenshots and upstream
claims are research leads; they do not change the roadmap or prove compatibility.
Defer unrelated surveys and new strategy documents until they inform a
measured comparison. Research follows [Security](SECURITY.md).
