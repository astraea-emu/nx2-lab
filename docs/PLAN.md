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

## Next implementation: VI2 client lifecycle

Run an original ARM64 guest through `appletOE` → `GraphicsSupervisor` → `VI2`,
using the frozen [graphics-supervisor implementation](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/am/service/graphics_supervisor.cpp).

1. Acquire real handles and complete bootstrap. Parse copied/moved handle
   descriptors and distinct CMIF/TIPC replies correctly: TIPC has a raw result
   without an `SFCO` header.
2. Register a nonzero client token with notification slots 2/3. Require success,
   duplicate-registration refusal, successful unregister and missing-token
   refusal on repeated unregister.
3. A writable **127-byte** notification buffer must be rejected without
   consuming the pending notification. A **128-byte** read must return
   retirement bit 2 (`0x4`); another 128-byte read must return cleared bits.
4. The guest checks and reports actual reply values/memory, closes every
   acquired handle and reaches `ExitProcess` with status 0. Faults, timeouts
   and unexpected stub/fallback paths fail acceptance.

Record the source-tagged `(STUBBED)` diagnostic from
[`GetManagerDisplayService`](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/vi/application_display_service.cpp)
explicitly. It constructs a real container-backed manager; obtaining that
manager does not qualify display output. This known diagnostic allows no
unrelated fallback success. Passing this control establishes source-model
service behavior: the first checkpoint toward the image workload below.

## Frame acceptance

Register the native image/window pool, bind a display/layer and present a
CPU-filled checkerboard with asymmetric corner markers in the supported block
layout. Add CLI capture using the existing renderer readback path. Fix the
format, extent, orientation and scaling, then compare captured pixels against
an independently generated reference. Changing a guest-owned color or pattern must change the observed
capture; a stale or corrupted capture must fail. Close handles and exit cleanly.
Retain the source revision, commands, guest/input and capture hashes, and actual
process results. Completion signals alone cannot establish a frame.
A pass would qualify this presentation path, not GPU shader execution,
3D correctness, hardware ABI fidelity or game compatibility.

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
