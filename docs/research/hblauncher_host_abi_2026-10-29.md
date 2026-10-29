# First independently authored native-facing ABI intake — HBLauncher

**Snapshot date:** 2026-10-29. **Evidence category:** public original
source review, then reproducible **host/QEMU AArch64** execution only.
This is NOT a Switch 2 console observation, not Horizon IPC, and not an
emulator running HBLauncher.

## Frozen independent input

- Source: https://github.com/ravensclawx/HBLauncher
- Git revision: `18b4748ba98eeac7df17beb5d3418985eb74897c`
- License: original `LICENSE` is MIT; external dependency licenses must
  be reviewed before any future redistribution or embedding.
- SDK structure: `sdk/abi.json` original Git blob
  `c143bba98182d22240bfbc692ebc2dbaa3059c9d`
  (project-specific HBX **ABI v3**, not native Nintendo OS ABI).
- Author's test runner: `tests/abi/build.sh` blob
  `14223d3f57049a4bf40ae80f2708fcaa6fdbd1e0`
- Author's Linux-QEMU AArch64 entry: `tests/abi/entry_aarch64.S`
  blob `2bad3fdd64b8461ff521d7aaff485e7d69e30c34`
- Native-facing sample: `apps/hello-cpu/src/app.c` blob
  `0513fa7d0b333ffdde2ee985f65900ee7f8f7e65`

No external code is vendored, and no device firmware, ROM, exploit code,
proprietary SDK, keys or binaries are committed to NX2 Lab.

## What the external suite actually tests

The original `tests/abi/build.sh` compiles and runs the author's:
1. Host SDK runtime tests using GCC.
2. AArch64 freestanding runtime tests using `aarch64-linux-gnu-gcc` and
   `qemu-aarch64` for Linux host emulation.
3. AArch64 _entry trampoline tests that validate the author's stack and
   callee-saved register conventions.

NX2 adds an **independent, strict** checker for its frozen
`sdk/abi.json`: ABI version, critical context/GPU layout offsets,
field count/size consistency and 18 altered/malformed-input refusals.
It cannot establish that the actual Switch 2 matches any of these
numbers—HBX is a launcher-defined guest API.

This is meaningful external-source execution and reproducibility. The
host QEMU result does not exercise the NX2 CPU engine, Nintendo services or
actual Switch 2 hardware. Report it as a *third-party host suite reproduced*.

## Technical review finding

The author-created `apps/hello-cpu/src/app.c` includes stage-driven
`hbx_app_main` tests:
- stage 1: `hbx_ctx_check(ctx)` and an entry context check;
- stage 2: input polling;
- stage 3: UI begin + a rectangle;
- stage 4: text;
- stage 5: present.

These are *HBX-defined* APIs, not Switch 2's undocumented kernel ABI.
The app is a useful independently authored **software dependency ladder**.
It becomes an NX2 emulator workload only when our own guest loader and
chosen backend execute its original AArch64 instructions with verified
mapped context/memory and typed first unimplemented boundary.

## Next acceptance gate

1. Freeze a generated, original HBX sample binary and its source/toolchain
   manifest; inspect entry, memory layout and loader format without changing
   original bytes.
2. Implement a narrow independently testable admission route in a *separate*
   adapter to the production-candidate CPU engine, not further ad-hoc opcode
   additions to the tiny reference interpreter.
3. Compare original stage-1 returned state against the source-owned expected
   status, then progress toward stage 2 only with exact recorded semantics.
4. Preserve a negative for a wrong/malformed context, wrong ABI version,
   wrong mapped permissions and non-repeatable execution.
5. Any actual console-side observation requires independent, authorized
   firmware-specific execution evidence and cannot be inferred from QEMU.

**Source-backed test acceptance:** the opt-in CI logs must show both original
upstream AArch64 test success lines and the NX2 independent ABI contract
checker, all pinned to exactly the source revision above. The standard
cross-platform CI must remain green.

## Competing approaches considered

**Build a full ARM interpreter from scratch:** reject for now; mature ARM
backends and competitors already cover far more ISA surface.

**Implement a Horizon kernel from rumors:** reject; source-only hypotheses
are inadequate for authentic service semantics and potentially misleading.

**Only publish a compatibility-mode wiki census:** retain as a secondary
research track; Switch 1 compatibility hooks are not the native Switch 2
runtime.

**Immediately pursue a console exploit:** not required for host-side
emulator progress. Responsible security research remains a separate
authorized track with Nintendo's disclosure scope.

**Reproduce original, reusable native-facing tests:** accept as the highest
value first step because it yields real external code/ABI evidence without a
console or fabricated platform behavior.
