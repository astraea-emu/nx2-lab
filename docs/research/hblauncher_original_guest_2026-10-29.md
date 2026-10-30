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

## Independent original-function reference (2026-10-30, PR in review)

The next experiment compiles a host-only QEMU AArch64 **reference**
executable from the *same original `app_c.o` object produced by the pinned
HBLauncher `hbx-build.py`*. NX2 adds only a small, separately authored
Linux harness that prepares HBX v3 context values and directly calls the
external `hbx_app_main`. The original upstream object is unchanged; CI
records its digest before and after the reference build.

The QEMU harness exercises valid stage 1, wrong magic, wrong ABI version
and wrong context size. CI parses each exact returned status and compares
the QEMU outputs with the **independent NX2 Dynarmic guest adapter**.
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

## Next dependency

After an actual stage-1 positive result, qualify the original `_start`
trampoline and its caller SP/return contract against upstream QEMU tests, then
stage-2 input and later UI output only as original program behavior and
independent evidence demand. Keep the small project-owned CPU interpreter as an
oracle; do not expand its ISA merely to keep this demonstration working.
