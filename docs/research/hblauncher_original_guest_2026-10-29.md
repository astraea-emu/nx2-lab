# E3 original HBLauncher Hello CPU stage 1 — checked guest execution research

**Scope:** first NX2-owned experimental ARM64 runtime to attempt the *original*
external `hbx_app_main` code. The binary is produced from the unmodified
HBLauncher source pinned at `18b4748ba98eeac7df17beb5d3418985eb74897c`.
This is HBLauncher's **custom HBX ABI v3**, not Nintendo Horizon.

## Original inputs / independent evidence
- `apps/hello-cpu/src/app.c` Git blob
  `0513fa7d0b333ffdde2ee985f65900ee7f8f7e65`.
- `sdk/tools/hbx-build.py` Git blob
  `a270514d010049dac1304cc7da25d63896e3bb99`.
- `sdk/src/crt0.S` Git blob
  `527bd97390b9ea607b4e109fa1850c580bfd2206`.
- `sdk/abi.json` Git blob
  `c143bba98182d22240bfbc692ebc2dbaa3059c9d`.
- Dynarmic `a46601580d5512d324104f985b5f0209dc980ddc`
  loaded only from exact pinned external checkout with dependency submodules.

## Execution model

The original HBX compiler emits `app.elf`, `code.bin`, `data.bin`,
and a generated manifest identifying the unchanged `hbxAppMain` entry.
NX2 verifies the source revision, report file sizes and SHA-256, then
materializes a distinct research-only Dynarmic adapter. The adapter maps
original executable code (read/execute only), original data and zero-initialized
BSS (read/write), a source-authored HBX context (read only), and a bounded
guest stack (read/write).

The adapter enters the original `hbx_app_main` rather than the original
`_start` trampoline. This is an explicit and meaningful limitation:
the test qualifies stage-1 *function* execution, **not** HBX process-entry
semantics, thread startup, ABI register-save guarantees or stack switching.

The return address is a non-executable sentinel; no native guest code,
real console syscall, host-side service callback, Nintendo firmware or
proprietary game data is admitted.

## Acceptance

- Good HBX context, `args[1]=1`: real original function returns `HBX_OK`.
- Incorrect magic/version/size: real original function returns `HBX_ERR_ABI`.
- Null/unmapped context, denied writable stack, altered/unmapped function entry,
  and a one-instruction budget: typed research rejection, no guest state
  released as a verified success.
- Two clean runs per valid and source-defined invalid context return.
- Exact source/toolchain-generated image hash retained in ephemeral CI output,
  not copied into this MIT repository.
- Existing Linux/Windows/macOS/sanitizer, E1, E2 and HBX ABI tests all remain
  green at final PR head.

This test does **not** establish real Switch 2 device ABI, official Horizon
services, general ARM64 application support, complete backend memory rollback,
HBX rendering/input stages, or an emulator reaching a guest frame. Without
independent hardware measurements, device-specific claims remain unsupported.

## Independent original-function reference (2026-10-30, verified host experiment)

The next experiment compiles a host-only QEMU AArch64 **reference**
executable from the *same original `app_c.o` object produced by the pinned
HBLauncher `hbx-build.py`*. NX2 adds only a small, separately authored
Linux harness that prepares HBX v3 context values and directly calls the
external `hbx_app_main`. The original upstream object is unchanged; CI
records its digest before and after the reference build.

The QEMU harness exercises valid stage 1, wrong magic, wrong ABI version
and wrong context size. CI parses each exact returned status and compares
the QEMU outputs with the **independent NX2 Dynarmic guest adapter**.
The verified initial run reported QEMU/NX2 0/2/2/2 return-status parity,
`NX2_HBX_STAGE1_QEMU_ORACLE_PARITY_PASS`, and **777 original NX2
instruction steps**. The QEMU harness itself is a conventional Linux
process; this does not imply identical full machine states or console
execution.
No fallback to expected-value-only testing is permitted: equality of
both actual output sets is required, plus the existing source-defined
positive and negative checks.

**Evidence boundary:** QEMU is running an ARM64 Linux process, including
normal C runtime/stdio system calls for the test harness; NX2 invokes no
host/guest service at all. Neither path is a Switch 2 Horizon emulator,
console reference observation, or a full `_start` entry test.

**Not yet established:** ABI-preserved original `_start` trampoline,
exact CPU and guest memory trace parity beyond returned statuses, and
physical Switch 2 behavior. This is a narrow but independent E3 semantic
oracle, not a device verification substitute.

## Original _start execution experiment (2026-10-30; verified pinned guest)

The same original pinned HBLauncher code/data, context, guest stack and
Dynarmic guest runner can be entered at the original `report.json.entry`
instead of `hbxAppMain`. This triggers original `crt0.S`: BTI landing,
caller frame save, context-provided stack selection, BL to `hbx_app_main`,
and caller frame/LR/SP restoration before an NX2-specified non-executable
return sentinel. The first draft test **correctly failed** with a typed
`guest_pc_outside_checked_rx` stop because the research fixture incorrectly
used an identical incoming caller SP and `ctx->stack_base`: the app overwrote
the saved caller frame after the intended switch. The corrected test maps
distinct caller and application stacks with separate permissions. This
test-harness finding is not evidence of a Nintendo vulnerability. The adapter requires exact original guest return codes
for valid and three invalid contexts, restored SP/x29/x30, safe negative
permissions and a strictly larger instruction count than direct function
entry. The independent QEMU oracle still validates the original C function
return statuses, while upstream's separate QEMU ABI suite tests its
trampoline. The test does **not** establish full machine-state trace parity
between NX2 and QEMU.

Actual pinned E3 CI passed: direct `hbx_app_main` uses **777** original
AArch64 instruction steps, full upstream `_start` uses **795**, exact
caller SP/X29/X30 are restored, and valid/bad-magic/bad-version/bad-size
return codes agree with the independent QEMU original-function oracle.
Wrong context pointers, denied stack writes, bad entry and insufficient
CPU budget remain refused.

This is **not** Nintendo process entry or Horizon ABI; the reference host
context and return sentinel are NX2-owned research fixtures. The QEMU
comparison covers stage-1 return codes, not every intermediate register or
memory effect, and no physical Switch 2 observation has been made.

## Guest write-effect accounting and binary intake (2026-10-30)

The actual original `hbx_app_main` stage-1 run executes 777 ARM64
instructions and produces **252 successful, captured stack-write
callbacks**. Entering the unchanged upstream `_start` retires 795
instructions and produces **254** writes: the same 252 app-stack writes
and two additional 8-byte caller-stack writes.

The initial one-callback expectation failed closed. Dynarmic split
the upstream source-defined STP save into **two** 8-byte callbacks.
The corrected gate checks the exact 16 saved X29/X30 bytes and
guest addresses, permits only 1x16 or 2x8 callback granularity and
rejects any other caller-stack write. All successful write addresses,
widths and bytes are compared across two independent executions.
Executable code, original data/BSS and source-defined read-only HBX
context remain byte-identical after execution.

A separate exact-source-generated image intake check verifies
`report.json`, `code.bin` and `data.bin` SHA-256, entry and
mapping extents; **19** malformed or changed synthetic cases are
rejected. These checks protect against accidental mutation, not
against an attacker who controls both upstream compiler and report.
Neither guest write events nor QEMU return parity constitute a
complete guest CPU architectural trace or console observation.

## Next dependency

Advance the same unchanged HBX Hello CPU executable to
[stage 2: zero-input callback execution](https://github.com/astraea-emu/nx2-lab/issues/20)
with `ctx.args[1]=2` and deliberately null custom input callback pointers.
Verify original execution under NX2 and QEMU, no host-service dispatch,
memory effects and repeatability. This is **not** actual Nintendo HID or
physical controller support.
