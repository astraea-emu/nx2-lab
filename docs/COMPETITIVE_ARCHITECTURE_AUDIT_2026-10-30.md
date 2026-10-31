# NX2 Lab — Switch 2 competitive architecture audit (2026-10-30)

> **Historical snapshot.** Capability statements, allocations and target dates below describe the October 30 review. Later runtime/IPC results are in [current status](STATUS.md); [the active plan](PLAN.md) owns the next gate.

> **Snapshot / confidence:** public GitHub trees, issue and CI metadata, upstream author logs and public technical notes, checked 2026-10-30. Author screenshots and performance claims are **not** independently reproduced game compatibility. Private branches and unpublished work are outside this census.

## Verdict

NX2 is **not currently a competitive Switch 2 emulator product**. It is a legitimate source-pinned AArch64 conformance and external-homebrew research harness. The main branch `c6153f359ad6e69b8ce772fdd56b601158967517` has passed exact-head cross-platform CI and a research-only Dynarmic/QEMU route executing the *custom HBLauncher SDK* Hello CPU stage-1 original `_start` (795 guest steps, 252 app-stack plus two caller-frame writes). **Zero verified Nintendo Horizon services, native Nintendo guest images, SM86/NVN2 shaders, Switch 2 game frames or hardware observations**. Do not conflate HBX custom ABI with Nintendo's.

**Architecture decision:** Do not build a production CPU, Horizon HLE, entire GPU and UI from scratch around the 795-step test. **Maintain NX2 Lab as MIT-licensed research/conformance infrastructure; separately qualify a mature emulator implementation for a GPL-compatible downstream runtime, or contribute upstream.** No GPL code copied/linked into this MIT release by this decision. Decide the actual runtime baseline only after reproducible builds, license/provenance review, security inspection and a measurable test advantage.

## Public competitive census

| Project | What source/CI establishes | Claim or gap that remains |
| --- | --- | --- |
| [Eden-NS2 / 0x2593](https://github.com/0x2593/Eden-NS2) (GPL-3.0) | Created Oct 29, descendant of Eden/Yuzu with **real, substantial Nintendo-facing GPU/runtime patches**, `docs/ns2/NOTES.md` engineering log; Oct 30 changes include guest GPU texture streaming, channel scheduling and mapping. | README *claims* Donkey Kong Bananza, Mario Kart World, Pokémon Pokopia and others enter gameplay. These are **author reports**, not independently reproduced by NX2; zero GitHub Actions runs or releases found in the inspected fork. Some auto-stub/failure-skipping can favor forward progress over fidelity. Code provenance, patched dependencies and secure builds need review before adoption. |
| [Eglantine](https://github.com/Djihads80/Eglantine) (GPL-3.0) | New Oct 29; several thousand source files inherited from Eden; active patches, GitHub automated release builds and macOS/Vulkan fixes on Oct 30. | Its broad commercial-game compatibility paragraph is inherited Eden/Switch-1 wording, **not independent Switch 2 gameplay evidence**. Switch 2 effect of each patch and actual compatibility remain to be measured. |
| [oboromi](https://github.com/0xNikilite/oboromi) (GPL-3.0) | Rust core, CPU work, memory, HIPC and experimental NVIDIA SM86 shader path; active CI and public sources. | Its own README explicitly excludes commercial-game and firmware support. ARMv9 work underway; no independently reproducible retail compatibility shown. |
| [Pound](https://github.com/pound-emu/pound) + [Ballistic](https://github.com/pound-emu/ballistic) (GPL family) | Wider legacy Switch architecture and separate native ARM recompiler source. | Authors explicitly prioritize Ballistic; GPU SM86-to-SPIR-V, JIT integration and full emulator completeness are still unfinished. New JIT is a high-risk parallel R&D investment. |
| [NeXo 2](https://github.com/NeXoNetwork/NeXo2-emu) (GPL-3.0) | Substantial actual NRO loader, Dynarmic integration, memory, service, Maxwell GPU and UI code; successful release workflow. | README claims numerous **Switch 1-format homebrew** titles and tests, not verified commercial Switch 2 program compatibility. Performance/compatibility claims unverified outside author reports. |
| [nxnative](https://github.com/seedds/nxnative) (MIT) | Active, large-scale original ARM64-on-Apple native-execution pipeline, Switch 1 NSO rewriting, HLE and Maxwell/NVN to Metal, CI, many tested Switch 1 profiles. | Private Oct 27/28 reports show Mario Kart World on Mac/iPhone with an unreleased **NVN2** fork. No reviewed public patch or third-party reproduction. Not a ready Switch 2 emulator. Strong architecture/performance lessons for Apple Silicon. |
| [HBLauncher](https://github.com/ravensclawx/HBLauncher) (MIT; third-party component notices) | Source-owned native homebrew SDK, console-facing route via ns2jb, staged source-authored CPU/UI tests; NX2 independently ran source-pinned HBX stage 1. | HBX custom ABI and display borrow from launcher; not itself a PC emulator or official Horizon ABI reference. |
| [ns2jb](https://gitlab.com/pepsipu/ns2jb) | Original author and contemporary reporting describe tethered userland/filesystem-sysmodule execution via SmileBASIC, firmware 23.0.1. | Not kernel, CFW or persistent exploit; device risk and licence/provenance boundaries. Neither jailbreak discovery nor installation is a prerequisite for software-first emulation. |
| [Hassaku](https://github.com/Hassaku-Emulator/Hassaku-Emulator), [Aurae](https://github.com/ProjectAurae/Aurae), [Pragma](https://github.com/pragma-emu/pragma) and newer naming forks | Public repositories/claims exist. | Hassaku/Aurae have effectively no emulator source; Pragma is not demonstrated as usable, and several newcomers are rebrands/forks. No independent gameplay evidence from a README title. |
| Switch 1 ecosystem: [Eden](https://git.eden-emu.dev/eden-emu/eden), Citron, Ryujinx/Yuzu descendants | Mature loader/HLE/GPU technology and established cross-platform behavior worth testing as candidate foundations. | Switch 1 software compatibility, even on Switch 2 hardware, **must not** be reported as native Switch 2 compatibility. |

This census is **not a guarantee all public/private projects were found**, nor a ranking by popularity or reported screenshots.

## Hard product gap: NX2 vs a credible emulator

| Subsystem | Current NX2 | Necessary leading-product gate |
| --- | --- | --- |
| CPU | Tiny owned interpreter; pinned Dynarmic research adapter with partial fault verification | Production-qualify AArch64 incl. PAC-relevant semantics, exceptions, atomics, deterministic frame stepping and host isolation; compare to an independent reference |
| Process and memory | HBX stage-1 guest mappings, checked write callbacks, source-generated image | Legitimate Switch 2-facing loader/process startup, permissions, TLS, threads, scheduling, IPC and observed Horizon contracts |
| Graphics | **None in NX2** | NVIDIA T239/Ampere SM86/NVN2 command, shader, texture and presentation path with authored reference output and Vulkan/Metal benchmarks |
| Audio, input, FS | None for actual Nintendo device | Precisely scoped native API fixtures, stateful services, save integrity and multi-controller tests |
| Operating systems | CI tests generic source on Win/Linux/macOS; guest E3 proved in Linux CI | Native app experience, reproducible install/build, macOS ARM JIT/permissions, backend checks on all three platforms |
| Compatibility and UX | Zero native Switch 2 game tests, no game UI | Public versioned lawful per-title evidence, reproducible screenshots / play logs, crash and performance profiles, keyboard/controller/saves/accessibility |
| Safety / licensing | Source-pinned and fail-closed experiments; no production hostile guest sandbox | Host isolation and memory safety, package/signature verification, provenance, crash triage, correct GPL obligations for any adopted code |

## Strategic allocation — next verification cycle

1. **40% — baseline engine selection / vertical integration.** Compare original Eden, Eden-NS2, Eglantine, oboromi, NeXo 2, and nxnative *source architectures*. Decision is ACCEPT/HOLD/REJECT for a separately licenced runtime or **upstream-first contribution**, with a reasoned security/provenance and long-term maintenance assessment. Do not blindly import fresh or unverified game patches.
2. **30% — original Switch 2 hardware/software evidence.** Select one narrow source-owned native **platform-specific** ABI or GPU/IPC workload and corroborate public interface claims independently. Source-owned HBX stage-2 zero-input remains a **bounded regression task**, not our commercial-game breakthrough.
3. **20% — reusable conformance and correctness tooling.** Versioned ARM64, memory, IPC, shader and graphics-event tests with an adapter for at least one *external emulator*, and a concrete upstream issue/PR. Count independently usable artifacts, not our own PR count.
4. **10% — authorized vulnerability research.** Public-source fuzzing and threat models first, actual owned/authorized hardware later with explicit consent and responsible disclosure. No claimed or promised exploit.

### Next critical decision (before expanding HBX input/graphics)

**Engine baseline gate — target 2026-11-07:** Review provenance/license and source contributions of the Eden fork family; reproduce a clean build and *source-owned* workload in an isolated CI runner on a frozen revision; compare one real supported userland/loader path against independently authored reference; run an offline negative test; record cross-platform host feasibility. If red, select the next candidate. Do not rely on author's screenshots or public keys/ROM downloads.

**First platform-native evidence gate — target 2026-11-20:** For one permitted, independently authored **Switch 2-facing** sample, freeze exact input, identify genuine Nintendo-facing versus HBX-only calls, collect a source-backed stop and a repeatable negative. If no legal native ABI observations exist, explicitly report that blocker and contribute a reusable verification test upstream.

**First guest-produced frame gate — stretch, no promised date:** Produce an original guest-generated image through an actual guest CPU + explicit verified display/graphics pathway, read back its checksum/pixels and compare to a source-owned reference. Host-drawn rectangles, mocked SVC replies and QEMU host apps **do not** qualify.

**Public software leadership gate — long term:** Safe cross-platform binary downloads, measurable compatibility with lawful independent samples, quantified CPU/GPU performance, no regression on reference tests, supported input/audio/saves, clear error messages and accessible UX. A playable commercial title is a separate, later evidence gate.

## Operational constraints / exit conditions

- **Do not** create another full ARM emulator, random HLE stubs, cosmetic frontend or feature list before the engine baseline gate. Stop counting generic instruction steps as platform capability.
- Preserve this MIT lab and independent test data. An integrated Eden/Yuzu or other GPL-based runtime will need its own appropriately GPL-compliant licensing/repository/release practices. Source copied between projects requires provenance and a full dependency licence check. Obtain specialist legal review if redistribution plans are ambiguous.
- Avoid executing newly emerged unreviewed emulator release binaries on a personal workstation. Prefer pinned source, ephemeral isolated build, dependency audit and no host privileges or credentials.
- Report **known / author claim / self-reproduced / independent physical observation** separately. If an emulator merely skips unknown work yet draws a screenshot, report the skipped operations and missing shaders.
- Re-evaluate after **one accepted upstream contribution or one externally reproducible Switch 2-specific conformance artifact**, whichever happens first; otherwise pivot more resources to mature upstream projects.

## Source references / frozen audit

- https://github.com/0x2593/Eden-NS2 and https://github.com/0x2593/Eden-NS2/blob/main/docs/ns2/NOTES.md (source log and GPL code, snapshot Oct 30; no matching public CI found in inspected fork)
- https://github.com/Djihads80/Eglantine (Eden-derived source and automated release CI, snapshot Oct 30)
- https://github.com/0xNikilite/oboromi
- https://github.com/pound-emu/pound and https://github.com/pound-emu/ballistic
- https://github.com/NeXoNetwork/NeXo2-emu
- https://github.com/seedds/nxnative
- https://github.com/ravensclawx/HBLauncher
- https://www.switchbrew.org/wiki/Switch_2%3A_Tegra_T239 (public T239 Cortex-A78C / PAC / Ampere architecture)
- https://www.gnu.org/licenses/gpl-faq.en.html (GPL-combination obligations)
- https://gitlab.com/pepsipu/ns2jb
