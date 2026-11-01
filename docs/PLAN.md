# Plan

## Milestone: qualify the original graphics workload on a newer engine

The original guest GPU triangle is complete in [Status](STATUS.md): native
commands, original shaders, both fragment colours, an independent pixel oracle,
clear-only rejection, saved capture and natural exit. Use that workload to
check whether the development base can advance without losing verified behaviour.

Compare baseline `e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c` with recorded Eden-NS2
candidate `b2cef0c0f2e8517673233e22c929918e2c60e654`. Verify its provenance and
relevant source/dependency changes before building; this is an exact comparison,
not a claim that the candidate is the latest revision. Retain the baseline
until the comparison passes and its evidence is reviewed in
[#21](https://github.com/astraea-emu/nx2-lab/issues/21).

## Acceptance

- Build both revisions in separate directories. Record source, dependency,
  tool and executable identities, and the exact repairs each revision needs.
- Run byte-identical original ExeFS, NPDM, command, shader and vertex inputs.
  Both triangles must match every expected pixel, their runtime shader pages
  must match the originals, and clear-only must fail both triangle references.
- Preserve native channel/TSG execution, ordered fence processing, the fence
  passed to VI2, saved capture before cleanup, complete release and natural
  exit. Unsupported, skipped, substituted or faulting positive work fails.
- Retain the loader/META, SM, VI2, CPU-image and strict 62-case GPU controls,
  with the two DMA exclusions explicit. Report the existing NRO return fault
  and malformed-input AES assertion separately; neither is a passing result.
- Repeat through the shared command with verified engine reuse and fresh
  evidence. Review any changed source-log binding against the candidate code;
  preserve the meaning of every check. If a gate fails, keep the baseline and
  record the first failing boundary. Change the pin only after qualification.

After this comparison, the next capability target is an original animated
guest with repeated submission and checked buffer reuse. Production adoption
remains **HOLD**: malformed-NRO parsing, host containment, dependency/license
review and relevant platform qualification remain open. There are no verified
commercial games or physical Switch 2 measurements. HBX stage 2 remains a
[secondary regression](https://github.com/astraea-emu/nx2-lab/issues/20).

## How decisions change

Keep one primary milestone. Review the path when it passes or after two
focused iterations fail to advance it; record the baseline, evidence, options,
falsifiable comparison and decision in the existing issue. A reproduced
safety or licensing conflict triggers immediate review. Revisit allocation
and outstanding evidence every four weeks without resetting the mission.

The weekly [radar](../.github/workflows/competitive-radar.yml) records selected
public GitHub metadata in one issue. Commits, stars, screenshots and upstream
claims are research leads; they do not prove compatibility. Defer unrelated
surveys and strategy documents until they inform a measured comparison.
Research follows [Security](SECURITY.md).
