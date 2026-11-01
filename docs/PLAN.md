# Plan

## Milestone: render an original triangle with guest GPU commands

The CPU-drawn image and reproducible Linux setup checkpoints are complete in
[Status](STATUS.md). The [local command](../CONTRIBUTING.md#original-image-trial-linux)
builds the pinned engine on its first invocation, then validates and reuses it
while producing fresh checked images. The next sample must execute GPU shaders.

Extend the original guest's existing graphics-driver session to map command,
shader, vertex and image memory, create a native graphics channel and submit
one triangle. Reuse the verified VI2 presentation and capture path. Start with
one target, three vertices, a constant fragment colour and no textures, depth,
blending or macros. A GPU clear is an internal debugging checkpoint.

## Acceptance

- Use original guest code and original vertex/fragment shaders. Start from a
  uniform sentinel image; the CPU must not draw the expected triangle.
- Require native channel/class binding, shader execution and a completed GPU
  fence. Enable strict native execution, bind the channel to its TSG and reject
  every skipped draw, unsupported operation or substituted shader/output.
- Compare the actual saved image with independently calculated coverage and
  colours. A second fragment-colour variant must change the expected pixels;
  a clear-only control must fail the triangle reference.
- Pass the GPU completion fence into VI2, retain memory through saved capture,
  release all resources and exit naturally. Preserve raw logs and source,
  shader, input and capture hashes through the existing local/CI command.

The source exposes a plausible route, but native shader headers and complete
graphics-state setup are unverified. Record the first actual unsupported
boundary and repair it with a focused regression. A separate CPU multi-frame
milestone would introduce buffer-reuse synchronization without resolving this
shader boundary; defer it until the original GPU draw works.

Production adoption remains **HOLD** in
[#21](https://github.com/astraea-emu/nx2-lab/issues/21). Compare a maintained Eden
upstream candidate with the same original workload before changing the pin.
Physical Switch 2 ABI fidelity, games, malformed-NRO parsing, host containment,
dependency review and cross-platform runtime qualification remain open.
Resolve the two excluded DMA contracts if the sample reaches them. HBX stage 2
remains a [secondary regression](https://github.com/astraea-emu/nx2-lab/issues/20).

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
