# Plan

## Milestone: edit a sample and verify its frame

A developer can modify an included original graphical guest, build and run it
with one documented command, and inspect a real captured frame checked against
an independent pixel reference. Reuse the external engine build on subsequent
runs and measure setup/repeat times. This milestone is not yet implemented.

The provisional path uses the pinned external Eden runtime in
[Status](STATUS.md). Production adoption remains **HOLD** under
[#21](https://github.com/astraea-emu/nx2-lab/issues/21). The existing CPU, IPC
and native unit checks support this sample; additional coverage must resolve a
measured blocker or protect behavior the sample needs.

## Next implementation: verify a guest-produced frame

The original VI2 guest has passed the lifecycle and notification checks in
[Status](STATUS.md). Next, register a native image/window pool, bind a display
layer and present a CPU-filled checkerboard with asymmetric corner markers in
the supported block layout.

Use the pinned engine's existing [on-demand renderer capture](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/nvdrv/devices/nvdisp_disp0.cpp)
with a working Vulkan surface. Fix format, extent, orientation and scaling,
then compare the fresh capture against an independently generated pixel
reference. Keep the image backing alive until capture completes, and require
that completion before guest cleanup and natural exit. Buffer retirement or
a timed wait alone is not completion evidence.

Changing a guest-owned color or pattern must change the observed capture;
a stale or corrupted capture must fail. Retain source revision, commands,
guest/input and capture hashes, and actual process results. This qualifies a
presentation path, not GPU shader execution, 3D correctness, hardware ABI
fidelity or game compatibility.

The excluded DMA contracts need resolution if the sample reaches them.
Malformed-NRO parsing, host containment and cross-platform runtime coverage
remain production blockers; their current limits stay visible in
[Status](STATUS.md). HBX stage 2 is a [secondary regression](https://github.com/astraea-emu/nx2-lab/issues/20).

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
