# Issue #21 — source-authored ExeFS service-manager roundtrip

**Status: actual guest IPC and both original controls passed; PR #32 merged.** This extends the
same controlled native-classified ExeFS route beyond debug output and process
exit. It does not replace the original debug/exit or malformed-NPDM controls.

## Verified real runtime result

[Run 41233784596](https://github.com/astraea-emu/nx2-lab/actions/runs/41233784596),
job `124633185031`, passed at head
`6adfaada80f9afdea3175629d8f5d144d5c6cd34`. All seven checks for that commit
passed, and [PR #32](https://github.com/astraea-emu/nx2-lab/pull/32) merged as
`2d9bb0064f4d53b255805fffcb28839977e374c4`.

The actual source-built runtime executed the original ARM64 guest. All 21
records appeared once in order through the real debug SVC. These values were
read from SVC returns and the guest's response buffer, then formatted by the
guest itself:

| Observed field | Value in this run |
| --- | --- |
| `connect_rc` | `0x00000000` |
| `sm_handle` | `0x000103fe` |
| `init_transport` | `0x00000000` |
| `init_magic` | `0x4f434653` |
| `init_result` | `0x00000000` |
| `init_header` | `0x0000000a` |
| `init_descriptor` | `0x00000000` |
| `get_transport` | `0x00000000` |
| `get_magic` | `0x4f434653` |
| `get_result` | `0x00000000` |
| `get_header` | `0x8000000a` |
| `get_descriptor` | `0x00000020` |
| `service_handle` | `0x000183fd` |
| `invalid_transport` | `0x00000000` |
| `invalid_magic` | `0x4f434653` |
| `invalid_result` | `0x00000c15` |
| `invalid_header` | `0x0000000a` |
| `invalid_descriptor` | `0x00000000` |
| `close_service` | `0x00000000` |
| `close_sm` | `0x00000000` |
| `fail_step` | `0x00000000` |

The service-manager and service handles were nonzero and distinct. Initialize
and service acquisition returned successful transport and service results;
the empty-name request returned successful transport with the expected
`0x00000c15` service error and no handle descriptor. Both handles closed
successfully. The guest emitted its completion record at log time
`0.696657`, then the real ExitProcess event at `0.696665`; host exit status
was **0**. No execution assertion, fault, stub fallback or protocol error was
observed. Handle values are observations from this run, not constants required
by future runs.

The same job independently passed the original debug/exit control with status
**0** and the corrupted-META control with typed `0007-0004` rejection and
status **1**, with no negative guest markers or execution faults/assertions.
The compiler cache was saved before those runtime trials.

All three raw logs were independently downloaded and checked against uploaded
artifact ZIP SHA-256
`fcc0fc5db1087e9816f00690db37c25f71cb4148b64fd4a6f653f33bdbc70b60`.
Their sizes were 16,644 bytes (valid), 2,367 bytes (invalid), and 19,826 bytes
(IPC). A complete scan found no assertion, execution-fault or stub markers.
The expected empty-name service error and nonfatal setup, missing-title,
network-initialization and play-time diagnostics remain visible; this is a
bounded successful workload, not a claim that every runtime subsystem is
qualified.

## Workload and acceptance

The original ARM64 guest obtains its thread IPC buffer, connects to `sm:`,
initializes the session, requests the existing `set` service, and inspects the
reply written into its own memory. It then requests an empty service name and
requires the specific service-manager error. It closes the two valid handles
and requests process exit.

Success requires all of the following in the actual source-built emulator:

1. The source-tagged 12 GiB program classification in the IPC trial's own log.
2. Successful `ConnectToNamedPort` and a nonzero service-manager handle.
3. Successful IPC transport and an `SFCO` reply with result zero for Initialize.
4. Successful GetService transport and service result, with exactly one moved
   handle, no copied handles/PID, and a nonzero service handle distinct from the
   service-manager handle.
5. An empty-name GetService request with successful transport but service result
   `0x00000c15` (SM InvalidServiceName), and no returned handle.
6. Successful CloseHandle for each acquired handle.
7. Guest-authored records of the actual observed values, followed by its
   completion marker, the real ExitProcess event, and host process status zero.
   Assertions, execution faults, timeout, unexpected stubs or a failure marker
   fail the gate.

The guest must start result fields with non-success sentinels, copy actual SVC
results and reply fields into its data page, compare them, and format those
stored values into its output. A fixed host echo or an unconditional guest
success string is insufficient. The host checker independently validates the
ordered records, expected values, handle relationships and clean lifecycle.

The negative request is **structurally valid with an invalid service name**.
This qualifies semantic rejection, not safety of malformed HIPC descriptor
counts or arbitrary packet shapes. An unknown nonempty service name is not used:
the pinned service manager defers that request while waiting for the service.

## Frozen sources and independent request-format check

- Eden-NS2: `e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`, with the existing
  explicitly recorded isolated build/lifecycle overlays.
- Independent libnx reference: `b156b4774fb2df7b93402169509266da7547fc4c`.
  Its original [SM wrapper](https://github.com/switchbrew/libnx/blob/b156b4774fb2df7b93402169509266da7547fc4c/nx/source/services/sm.c),
  [CMIF builder](https://github.com/switchbrew/libnx/blob/b156b4774fb2df7b93402169509266da7547fc4c/nx/include/switch/sf/cmif.h)
  and [HIPC builder](https://github.com/switchbrew/libnx/blob/b156b4774fb2df7b93402169509266da7547fc4c/nx/include/switch/sf/hipc.h)
  corroborate Initialize command 0 with PID, and GetService command 1 with an
  eight-byte name and a moved-handle response.

A temporary GCC C11 host probe compiled the **unchanged original libnx**
`cmifMakeRequest`, `hipcMakeRequest` and `hipcParseRequest` helpers. All 256 bytes
of each generated request matched independently authored buffers. Original
CMIF/HIPC Git blobs were respectively
`3b3fa8e25bf7344ac1c8a8fbaaa840ca9fe1c627` and
`e3836007ceb25836e2936bc5a80865d108ed1a8b`; the vendor checkout was unchanged.
This is host-side encoding evidence only: no ARM SVC, TLS accessor or emulator
guest was executed by that check.

The guest is assembled and linked from `native_sm_probe.S` and
`native_sm_probe.ld` using GNU AArch64 binutils. Its original text is 756 bytes,
rodata 514 bytes and writable data 160 bytes, in separate RX/R/RW segments with
no remaining relocations. Nine fixture tests pass, including repeat compilation,
the independent request vectors, sentinels and malformed-input controls. The
separate log assessor has 19 regression cases; neither test suite substitutes
for execution in Eden.

A separate bounded Unicorn 2.1.4 unit run executed this ARM64 guest with
**mocked SVC replies**. The success case retired 3,277 instructions, checked
all three request buffers, formatted the 21 observed records, closed both
handles and reached ExitProcess. Injecting Initialize reply magic `0x12345678`
instead produced failure step 2, retained unexecuted sentinels, closed the SM
handle and emitted no completion marker (3,057 instructions). This checks
guest control flow and readback only; no real Horizon/SM behavior ran in it.

Generated IPC `main` SHA-256:
`97361663c3468646e453632f7febe3a37bd798e6f3fc2af985b793f21d2c3905`.
Corrected baseline NPDM is reused byte-for-byte, SHA-256
`64e25a2e3e37495d75341f9564afa3e6a665f10f94b36ea7e4e3c533b4573148`.
The original debug-only guest remains unchanged and continues to run as a
separate control in the same workflow.

| Request | Raw-data offset | SFCI offset | Argument offset | Raw-data words |
| --- | --- | --- | --- | --- |
| Initialize, command 0, PID descriptor, eight zero argument bytes | `0x14` | `0x20` | `0x30` | 10 |
| GetService, command 1, eight-byte service name | `0x08` | `0x10` | `0x20` | 10 |

## Register and reply contracts

The [independent libnx SVC assembly](https://github.com/switchbrew/libnx/blob/b156b4774fb2df7b93402169509266da7547fc4c/nx/source/kernel/svc.s)
and [pinned Eden dispatcher](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/kernel/svc.cpp)
agree on these direct assembly conventions:

| Operation | Instruction | Inputs | Observations |
| --- | --- | --- | --- |
| Thread IPC buffer | `MRS xN, TPIDRRO_EL0` | None | TLS address in `xN` |
| Connect | `SVC #0x1f` | `X1` points to `sm:\0` | Result in `W0`, handle in `W1` |
| Send request | `SVC #0x21` | Session handle in `W0` | Transport result in `W0`, reply in TLS |
| Close handle | `SVC #0x16` | Handle in `W0` | Result in `W0` |
| Debug output | `SVC #0x27` | String address/length in `X0`/`X1` | Genuine guest output |
| Exit | `SVC #0x07` | None required | No further ordinary guest execution |

The [SM implementation](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/sm/sm.cpp),
[reply builder](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/ipc_helpers.h)
and [reply-memory write](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/hle_ipc.cpp)
place `SFCO` at TLS `0x10` and the service result at `0x18`. GetService returns
one moved handle at `0x0c`, described by word `0x20` at `0x08`. Response word 1
is `0x8000000a` for that handle-bearing response and `0x0000000a` for the
Initialize and empty-name responses in this pinned implementation. The guest
clears the first `0x100` bytes before every request and checks transport and
service results separately.

The [settings registration](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/set/settings.cpp)
provides `set` unconditionally. Acquiring and closing its handle does not invoke
settings operations or require console firmware/data.

## Scope and remaining decision

This is shared Horizon-style IPC in a **synthetically Switch 2-tagged process**,
not a Switch 2-specific service or physical-device ABI observation. The pinned
SM initializer does not enforce the PID argument, and the current SVC dispatcher
does not enforce the fixture's SVC permission descriptors. Success cannot prove
either property. The source model also supplies a default handle-table size
when no explicit size is present.

Production-engine selection remains HOLD. Original loader bounds and the
malformed-NRO crypto-probe assertion remain production-safety blockers; the
known ExeFS input does not traverse that failing identification path. The 31
unqualified cases in the excluded native-GPU test file (eight MME cases and
23 other GPU cases), dependency/license review, containment,
hardware-backed semantics, GPU output and relevant host-platform testing remain
separate acceptance conditions. This experiment advances one known workload;
it does not commit NX2 to a production fork or claim game compatibility.
