# NX2 Lab / Astraea — public research and competitive checkpoints

**Snapshot:** 2026-10-29. Public source metadata and project claims are leads;
not independent local compatibility benchmark results. Preserve distinctions
between official releases, repository main, source-owned homebrew, actual
console observations, commercial game compatibility, and private videos.

## Astraea (separate PS5 repository)

https://github.com/astraea-emu/astraea

- Default branch `main`: `e94b06d48f90c9f77aa91fd8602654b92733439f`
  (2026-10-15); most recent merged change was PR #479, Landlock restriction
  for a Linux mediated research worker.
- Draft PR #480 at `a7513d849531cb21cfca43616cc283e46aaccf53` is still
  open as of review and all seven exact-head checks have passed. It records
  synthetic-context guest caller state at the unretired Breakout import.
- 573 entries in the recursive `main` tree, 162 branches (including the PR
  branch), 19 open standalone issues; no tagged releases/stars/forks.
- Supported structural profiling and bounded GPU Vulkan readback are not
  evidence of a commercial first instruction or game frame.
- The first independent Breakout imported call remains unexecuted: guest RIP
  `0x23c`, first GOT `0x68c8`, bare NID `Vo5V8KAwCmk`; module/provider and
  effects remain unauthenticated in Astraea's actual ELF.
- Critical blockers: #410 (native hostile-code containment), #461 (CPU backend
  acceptance), #334 (genuine initial process ABI), #475 (lawful commercial C0
  profile), #378 (first imported-service boundary). Do not widen to UI/feature
  catalogs until one unchanged workload moves forward.

## PS5 competition (latest public repository snapshots)

| Project | Public engineering direction as of 2026-10-29 | Important caution |
|---|---|---|
| [KytyPS5](https://github.com/KytyPS5/KytyPS5) | Main changes Oct 29: shader tessellation, indirect buffer handling, NGS2 audio. Dated Oct 29 release; about 10.1k stars. | Game reports are community-derived; in-game ≠ playable. |
| [SharpEmu](https://github.com/sharpemu/sharpemu) | GPU ray tracing, Unreal workloads, VideoOut, v0.0.6 Oct 18; about 6.5k stars. macOS removed from main Oct 24, separate `sharpemu-mac` active. | Per-game reports are build/OS dependent. |
| [AnyPS5](https://github.com/boykopovar/AnyPS5) | Relinks/ports executable into host native format, v0.1.3 Oct 20; about 49.5k stars. Oct 29 fixes include NID and libc boundaries. | Not same architecture or compatibility criterion as whole emulator. |
| [prosper](https://github.com/mattias800/prosper) | User-space PS5 compatibility layer; current Wave32 and GPU-state corrections; about 214 stars. | Source of truth is exact compatibility case, not high PR count. |
| [Prosperity](https://github.com/Force67/prosperity) | PS4/PS5 LLE project, Linux-first; small game and service milestones; about 409 stars. | No universal playable support. |

## Switch 2 public research and emulation (2026-10-29)

| Project | Reported capability | What is NOT established |
|---|---|---|
| [pepsipu/ns2jb](https://gitlab.com/pepsipu/ns2jb) | Tethered proof on Switch 2 firmware 23.0.1 using SmileBASIC 4 and filesystem-service access. Original repo commits through Oct 22. | No kernel exploit or persistent CFW. Original code license not confirmed compatible with reuse. |
| [cpypwn/mac2jb](https://github.com/cpypwn/mac2jb) | Oct 29 v0.6.0 adds MintBrew GPU/homebrew library over a held ns2jb RPC. | Tool's README requires high-risk macOS security changes for bundled USB driver; this is not a new persistent Switch 2 exploit. |
| [ravensclawx/HBLauncher](https://github.com/ravensclawx/HBLauncher) | Homebrew-style GPU experiments and SDK over SmileBASIC route; Oct 23 v0.2.0. | Not equivalent to a standard Switch 2 native `.nro` homebrew runtime or custom firmware. |
| [OunceCake](https://github.com/misshexa66/OunceCake) | Host tooling to retrieve selected unencrypted filesystem contents from authorized consoles, public Oct 25. | File access alone does not establish successful commercial game emulation. |
| [oboromi](https://github.com/0xNikilite/oboromi) | Rust ARM CPU / NVIDIA SM86 emulator foundation; actively worked on Oct 29. | Own README says commercial games and firmware cannot run. |
| [Pound](https://github.com/pound-emu/pound) | Switch-family emulator architecture and Ballistic ARM JIT track; Oct 29 thread primitives. | No reproducible public Switch 2 commercial game compatibility. |
| [NeXo 2](https://github.com/NeXoNetwork/NeXo2-emu) | Claims Switch 1-format homebrew `.nro` games and 3D paths, earlier commit Oct 12. | Switch 1 homebrew support is **not** demonstrated Switch 2 game compatibility. |

## Hardware source discipline

Nintendo states Switch 2 uses a custom NVIDIA processor and 256 GB UFS.
Community hardware documentation identifies the T239 with eight A78C cores,
12 GB LPDDR5X and an Ampere-class GPU. Treat core/SASS/SM86 claims as
independent research subject to revision, not as a validated host ABI.

- https://www.nintendo.com/en-ca/gaming-systems/switch-2/tech-specs/
- https://switchbrew.org/wiki/Switch_2%3A_Tegra_T239
- https://pepsipu.com/blog/2026-10-switch2-jailbreak-ns2jb/

## Strategic conclusion

Astraea should remain maintained while NX2 Lab occupies an under-served
public **evidence/test-infrastructure** niche. The way to earn major
contributor reputation is to upstream small, hard, well-tested findings to
existing emulator/homebrew projects, not to promise a full emulator before a
valid executable can run. Avoid copying unlicensed exploit distributions or
GPL-only emulation code into this MIT worktree.

The immediate next software step is an independently authored AArch64 process
fixture with checked virtual memory and a typed first host service boundary,
then a measured third-party CPU backend evaluation. Hardware observations
remain optional and explicitly consented, not a prerequisite for E0/E1/E2.
