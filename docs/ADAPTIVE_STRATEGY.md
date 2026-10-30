# NX2 Lab — adaptive strategy and decision protocol

**Stable mission:** Produce an accurate, performant, safe, reproducible cross-platform Switch 2 emulator and independently useful verification infrastructure. A new fork, press report or screenshot does not change this mission.

**Implementation is flexible:** Runtime baseline, CPU/GPU backend, milestones and research priorities are hypotheses. We change them only in response to measured evidence. The MIT NX2 Lab stays separate from any properly licensed GPL-derived production runtime. We neither copy incompatible code nor publish proprietary firmware, keys or games.

## Current execution gate

The primary gate is [#21](https://github.com/astraea-emu/nx2-lab/issues/21): choose a qualified mature emulator runtime or an upstream-first path, based on a frozen, independently reproducible, source-owned workload. HBX stage 2 ([#20](https://github.com/astraea-emu/nx2-lab/issues/20)) is a bounded regression, not the primary milestone.

There is only **one primary engineering gate** at a time. A gate requires a runnable acceptance test, explicit unsupported boundary and a credible next vertical slice. Finish or explicitly reject/reframe it before starting another unrelated one.

## Trigger policy — adapt without chasing every headline

| Evidence class | Response | Change the main roadmap? |
| --- | --- | --- |
| New repo, star count, commit, README, self-reported FPS/screenshot | Record in radar and queue relevant source review | **No** |
| Substantial platform-specific source changes, new documented API/ABI, candidate runtime with credible build and source provenance | Open a bounded technical investigation with frozen SHA and negative test | **Not automatically** |
| Independently reproduced advance on a genuine Switch 2-facing workload, material measured speed/correctness gain, or validated alternative that reduces maintenance | Compare current path against alternatives and document migration cost | **Only after decision review** |
| Reproducible unsafe behavior, licensing conflict, irrecoverable blocker | Pause affected work, record evidence and safe alternatives | **Immediate review** |
| Primary milestone passes, or two focused iterations fail to move the same workload | Accept/reject and reconsider the next vertical slice | **Yes, at milestone review** |

No routine pivot just because a competitor has a new commit. Defer unrelated leads until the next gate review unless security or licensing requires immediate action.

## Five-field decision record (issue or PR)

1. **Baseline:** current gate, exact source revision, executable/input and first measured stop.
2. **Evidence:** dated primary source and confidence (author claim, source-inspected, independently reproduced host test, authorized device measurement).
3. **Options:** continue, fork/adopt, contribute upstream, or stop; costs, licenses, safety and platform compatibility.
4. **Falsifiable comparison:** independent positive and negative test, performance, portability, effort, uncertainty and rollback.
5. **Decision:** ACCEPT/HOLD/REJECT; milestone owner, next measurable gate, conditions for reconsideration.

A strategy document or PR count is not a compatibility milestone. Progress means a genuine unchanged workload moves through verified CPU, loader, OS and graphics paths; a third-party emulator can reuse a conformance test; or we obtain an authorized, independently checked hardware observation. Track regression rates, unsupported GPU/IPC work and host isolation too.

## Operating cadence

- **Every code PR:** describe source, observed stop, positive and negative tests, independently checked effects, and unsupported behavior. Link the primary gate.
- **Weekly:** the [metadata-only competitive radar](../.github/workflows/competitive-radar.yml) updates **one issue** using public GitHub API metadata. It never executes competitor binaries, downloads Nintendo content, changes source, modifies the roadmap or decides the engine. A commit or CI status is not proof of game compatibility.
- **At milestone acceptance, or after two blocked iterations:** compare continuing with switching against actual measurements and write a five-field decision.
- **Every four weeks:** reconsider work allocation and the evidence horizon, without resetting the project mission.

**Coverage limits:** the radar watches selected public GitHub repositories only. Original Eden's independent Git server, private forks, device measurements and non-GitHub security publications require explicit human research. Scheduled GitHub Actions may be delayed or disabled on inactive public repos; manual workflow dispatch is available. The scanner provides alerts to investigate, **not autonomous intelligence or automatic replanning**.
