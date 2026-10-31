# NX2 Lab — Live Status (2026-10-31)

## Current objective and scope

The active milestone is [#21: qualify a mature emulator runtime or an
upstream-first contribution path](https://github.com/astraea-emu/nx2-lab/issues/21).
**Production-engine decision: HOLD.** NX2 is now evaluating actual external
CPU/loader/HLE runtime behavior. Its own portable `nx2lab` executable remains a
small correctness oracle; it is not a standalone Switch 2 game emulator.

The distinction matters: a guest executed by a source-built Eden or NeXo engine
is real guest-execution evidence, but does not mean NX2's tiny interpreter has
acquired that engine's functionality. External GPL implementation code stays in
separate, temporary source builds. NX2's original conformance tools and inputs
remain in this MIT repository.

## Established evidence

| Control | Independently measured result | Evidence |
| --- | --- | --- |
| NeXo Switch 1-format NRO | Unchanged source-authored homebrew executed through the real loader/CPU/HLE path, completed calculations and exited; malformed images rejected. | [Merged #25](https://github.com/astraea-emu/nx2-lab/pull/25), [runtime CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41092724871) |
| Eden-NS2 native-facing source contracts | 94 assertions passed in both GNU C++ and Clang with ASan/UBSan against exact original service/GPU header implementations. | [Merged #26](https://github.com/astraea-emu/nx2-lab/pull/26), [contract CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41094596650) |
| Integrated Eden-NS2 build | CPU/HLE/GPU libraries built with one isolated cast correction; the reduced original suite passed 33 cases / 9,103 assertions. **31 cases in one native-GPU test file remain unbuilt and untested: eight MME cases and 23 other GPU cases.** | [Merged #27](https://github.com/astraea-emu/nx2-lab/pull/27), [build CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41115025130) |
| NRO fixture preflight | Authentic source-owned NRO accepted and six malformed versions rejected before submission to the research runtime. This does not repair or prove safety of Eden's own loader. | [Merged #29](https://github.com/astraea-emu/nx2-lab/pull/29), [preflight CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41127444547) |
| Native metadata reload defect | Actual frozen C++ retained `IsSwitch2()` after extended-to-legacy metadata reuse; the baseline failed as expected and a one-line isolated reset passed the regression. | [Merged #30](https://github.com/astraea-emu/nx2-lab/pull/30), [original-source CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41136582253) |
| Original extended-ExeFS input | Deterministic NX2-authored ARM64 NSO0 plus synthetic extended-ACID NPDM generated without a console SDK or proprietary data. Fixture generation alone proves no execution. | [Merged #31](https://github.com/astraea-emu/nx2-lab/pull/31), [fixture CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41132733015) |

Frozen runtime sources: Eden-NS2
`e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`; NeXo
`7fa73a5062e64370163a248d1a0b555272012c0f`. The exact NeXo original
`hello.nro` Git blob is `bb0ee2a52acd303e7c800443163aa91900eabb58`.
All results above are host-side measurements, not physical Switch 2 observations.

## Active execution controls

### Eden NRO lifecycle — merged PR #28

[Stricter runtime run #41229946626](https://github.com/astraea-emu/nx2-lab/actions/runs/41229946626)
observed original guest debug output, data counter, heap sum and Fibonacci
calculation. The **unchanged** NRO still returned through a missing exit thunk,
faulted and reached timeout status **124**; it did not exit successfully.
A separately labeled four-byte exit-thunk adaptation, combined with the audited
GPL-side process/SDL lifecycle repair, produced guest output and **exit status
0**. The corrupted-magic input produced an explicit loader error and ordinary
failure status **1**, but also logged an AES-probe assertion in
`core/crypto/aes_util.cpp:97` for `EVP_CipherInit_ex2`. This proves terminating
loader rejection, **not assertion-free malformed-input handling**. The
[PR #28 lifecycle evidence](research/eden_nro_guest_probe_2026-10-30.md)
records the assertion found in that run's raw log and the source path that
probes NCA after NRO magic identification fails. The adapted positive guest
did not produce this assertion.

[PR #28](https://github.com/astraea-emu/nx2-lab/pull/28) merged as
`79186b80102555f7362a178d68fab7ef21e0e274` after **all seven checks passed**
at head `3764f74101ad87f3009e7d75d0029d66cd4b63db`. The stricter run requires
ordered guest computations, actual `ExitProcess`, status 0 and no assertions or
execution faults in the adapted guest. The malformed control requires typed
rejection, status 1 and no guest output; its incidental crypto-probe assertion
remains explicitly reported. This closes the bounded NRO lifecycle control,
not production loader safety or the original NRO's return limitation.

### Synthetic extended-ExeFS execution — PR #32

[First runtime run #41224123601](https://github.com/astraea-emu/nx2-lab/actions/runs/41224123601)
selected Eden's **12 GiB / Switch 2-classified** memory layout and recorded the
original guest's message through `OutputDebugString`. It nevertheless **failed**:
the valid input logged a thread-priority assertion and timed out with status
**124**; the invalid-META input hung with no diagnostic and was killed with
status **137**.

The synthetic metadata requested priority **0** while its capability admitted
priorities **16–63**. [PR #32](https://github.com/astraea-emu/nx2-lab/pull/32)
corrected the fixture to priority **44** and reused the isolated lifecycle
repair. [Baseline run #41229858618](https://github.com/astraea-emu/nx2-lab/actions/runs/41229858618)
at head `6c55524` then produced these actual runtime results:

| Control | Observed result |
| --- | --- |
| Corrected extended-ExeFS guest | Source-tagged 12 GiB classification, original guest debug output, genuine `ExitProcess`, status **0**, no execution faults/assertions |
| Corrupted-META input | Status **1**, Core error **4**, Frontend code **0007-0004**, numeric description **4**, no assertions or guest execution |

The workflow nevertheless **failed** because its old log assessor expected an
English NPDM error description; the frozen runtime emitted the numeric form.
That is a checker failure after the observed workload results, not a green
runtime workflow. The corrected assessor requires the complete source-tagged
error tuple and exactly one ordered classification/output/exit sequence for the
positive input. It passes the actual archived logs and **26 assessor regression
tests**. Archive replay does not replace a fresh run of the revised workflow.

Current PR head
[`6adfaada80f9afdea3175629d8f5d144d5c6cd34`](https://github.com/astraea-emu/nx2-lab/commit/6adfaada80f9afdea3175629d8f5d144d5c6cd34)
includes that correction, current main, and the original service-manager IPC
guest. It also saves the compiler cache before runtime trials so that a trial
failure does not discard the expensive build cache. **112 combined Python tests
passed locally**; those fixture/checker tests are not real emulator execution.
The actual combined runtime trial is **PENDING** in
[run #41233784596](https://github.com/astraea-emu/nx2-lab/actions/runs/41233784596).
Do not claim IPC success or complete PR acceptance from the baseline result,
archive replay or unit tests.

## Next milestone and decision

Complete the native controls under #21, then record the evidence-based decision
using [Adaptive Strategy](ADAPTIVE_STRATEGY.md). A successful synthetic
extended-ExeFS run qualifies only Eden's modeled native-facing loader/CPU path;
it does not warrant production-engine ACCEPT by itself.

An original ARM64 extension of the **same source-owned ExeFS** is now under
real service-manager trial in run #41233784596. It initializes `sm:`, obtains a
`set` service handle, checks the empty-name error, closes both handles, and
reports fields read from its own reply memory. **Actual IPC success remains
pending.** The negative service request is structurally valid with an invalid
name, not malformed HIPC data.

If that runtime gate passes, the next primary slice is **strict native-GPU
qualification**, before selecting a guest frame workload. Restore the excluded
native-GPU test translation unit with exact-source guards and preserved
assertions. Source review identifies 24 cases that do not use the stale
interpreter interface and five cases with bounded compatibility adaptations.
Those 29 cases are restoration candidates, not full-runtime passes. Two DMA
cases require a separate contract decision: DMA moved into the caller, and
its current size policy differs from the old tests. Preserve both unresolved
expectations instead of weakening them to obtain green CI.
The [reconciliation audit](research/eden_native_gpu_test_reconciliation_2026-10-31.md)
records all 31 case identities, exact source blobs, the five compatibility
adaptations, and both remaining DMA contracts.

Set `EDEN_NATIVE_STRICT=1` explicitly for that qualification. The frozen
[QMD scheduler](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/native_qmd.h)
can otherwise mark unsupported shader dispatch as completed. Neither a
completed semaphore nor an acquired service handle proves rendered pixels.
The later frame gate requires a selected guest graphics/display path and
independently checked image readback. Switch 2 ABI fidelity still requires
independent hardware observations or authoritative public ABI evidence. Keep
the small standalone interpreter as a correctness oracle.

Engine acceptance also still requires resolution of the 31 omitted GPU cases,
the malformed-NRO AES-probe assertion, original loader bounds checks with
sanitizer-backed regression, dependency and license review, containment, and
relevant host-platform qualification. A synthetic emulator-derived metadata
model is not a hardware ABI oracle.

## Capability limits

- No hardware-backed Switch 2 ABI or native device observation; no exploit,
  console-side probe or firmware acquisition has been performed by this work.
- No guest-produced graphical frame, commercial-game compatibility, or
  full Switch 2 graphics/OS implementation has been established.
- The bounded NX2 tools generate/check selected NRO/NSO/NPDM test structures;
  the `nx2lab` executable itself still accepts only NX2OWNED images. It does
  not load Nintendo games or provide a full NRO/NSO/NCA/XCI loader.
- Core NX2 CI covers Linux, Windows and macOS. The external integrated runtime
  evidence above is from Linux; it does not prove Eden works on Apple Silicon.
- NRO preflight constrains known test inputs. It is not a hostile-input sandbox
  or a substitute for correcting the original third-party parser.

## Earlier independent groundwork

The following CPU/HBX results remain useful regression evidence. They are not
the current primary product milestone. HBLauncher stage 2
([#20](https://github.com/astraea-emu/nx2-lab/issues/20)) stays a bounded secondary
regression under the current architecture decision.

### NX2-owned CPU and memory oracle

- Portable, bounded, source-owned AArch64 CPU sample: 64-bit MOVZ and ADD
  immediate (excluding unmodelled SP forms), NOP and pre-retirement BRK.
- A typed unsupported-instruction, instruction-budget and fetch-fault path.
- A generic AArch64 SVC immediate decode and typed **pre-retirement** service
  request stop. Caller registers, PC and memory stay unchanged by the SVC.
  No host syscall, service dispatch or Nintendo ABI interpretation occurs.
  Unsupported HVC/SMC and budget boundaries are regression-tested.
- A **separate, explicitly approved, fixture-only reply** can advance the
  saved SVC stop to the next source-owned instruction and supply a synthetic X0
  return, after checking original instruction bytes and matching immediate.
  This models neither a real OS exception return nor any Horizon service.
- A 64-bit, little-endian source-owned guest-memory R/W experiment, with full-range
  checks, read-only/write-only denial, refused overlapping and partial mappings,
  overflow negatives, and pre-retirement typed data-access faults.
- Generic AArch64 64-bit STR/LDR unsigned-offset fixture (offset 0 or scaled by 8)
  with checked guest-memory effects; the encodings were independently checked
  using a generic AArch64 assembler. No Switch 2 MMU/Horizon semantics.
- No host IO, syscalls or elevated privileges in the CPU interpretation sample.
  The separately bounded CLI reads only a local NX2OWNED fixture file.
- Offline, size- and path-bounded owned-fixture SHA-256 evidence verifier.
- CMake/CTest and a GitHub Actions cross-platform CI **configuration**.
- Research-only pinned Dynarmic AArch64 JIT qualification (PR #3): a separate
  Linux CI job builds exact public revision `a46601580d5512d324104f985b5f0209dc980ddc`
  with its recorded submodules and executes original MOVZ/ADD/NOP and
  MOVZ/STR/LDR prefixes. All 31 GPRs, PC and guest-memory readback match
  the tiny owned oracle; the exact SVC boundary remains unexecuted.
  A source-owned four-case denied-access matrix now checks read-only stores,
  unmapped stores, boundary-crossing stores and write-only loads. The tiny
  interpreter supplies typed reference faults; the research JIT callback
  rejects unauthorized private memory effects and discards all post-denial
  CPU state without claiming a precise JIT fault or a production sandbox.
  A separately frozen source-owned `SVC #0x1234` fixture now reaches the
  actual Dynarmic JIT callback exactly once with no host dispatch or guest
  memory effects. Post-callback JIT state is deliberately not published:
  the research callback is neither a genuine Horizon service nor an
  authenticated ARM exception-return contract. This is **not** a precise guest fault or an approved
  production CPU backend; licensing and hostile-worker containment remain
  separate acceptance gates.
- **E2 independently authored ARM64 ELF prefix:** a pinned MIT-licensed
  Linux ARM64 assembly program is compiled to ELF64 in isolated CI. Its
  original RX PT_LOAD is extracted into the bounded NX2OWNED test envelope,
  with the original PC-relative 64-bit LDR literal pointer independently
  checked against the exact message in a separate nonexecuting data PT_LOAD.
  The same external source bytes now retire **four genuine instructions**
  (MOVZ/LDR-literal/MOVZ/MOVZ), then stop before original `SVC #0`.
  Two identical runs, a pinned source blob, sixteen malformed-ELF negatives
  and source-owned signed-offset/64-bit read fault tests are required.
  No actual Linux syscall, Nintendo/Horizon service or graphical output is
  performed; this is not a general ELF loader or game/homebrew compatibility.
  **Merged research-only mock continuation (#9):** the exact pinned
  external first `SVC #0` is *not dispatched*; a source-verified, read-only,
  14-byte guest message is checked through the existing 64-bit guest-memory
  facade, and an explicitly authorized fixture reply returns 14 in X0. The
  unchanged program then retires two more original instructions and stops
  before its second `SVC #0` (`X8=93`, original Linux exit request).
  This models six original instruction retirements and zero host syscalls;
  neither the first nor second SVC is actually retired. Ten source-owned
  tamper negatives plus a changed external-message sidecar are refused.
  It is **not** a real Linux write, exit, Horizon OS service or Nintendo run.
- Three host-only demonstrations, including a 28-byte NX2OWNED v1 standalone
  executable image with strict header/count/entry validation, and four
  SHA-256 evidence manifests. Thirteen local CTest groups pass on Linux.

### Dated ecosystem context

See the [October 30 architecture audit](COMPETITIVE_ARCHITECTURE_AUDIT_2026-10-30.md)
for the source-based candidate comparison. The
[competitive radar](../.github/workflows/competitive-radar.yml) tracks selected
repository metadata; neither a new commit nor a self-reported screenshot is
independent compatibility evidence. Its scope and review triggers are defined
in [Adaptive Strategy](ADAPTIVE_STRATEGY.md).

### E3 guest write-effect accounting and binary intake (PR #19)

Original source-pinned HBLauncher code now has a **bounded, exact guest
write-callback ledger**. The direct stage-1 route records 777
instructions and 252 application-stack writes. The original `_start`
route records 795 instructions, 252 application-stack writes and
**two 8-byte caller-stack writes** forming the exact saved 16-byte
X29/X30 frame. Both fresh runs of each case have identical effect
addresses, widths and bytes. All writes remain within admitted stacks;
RX code, original data and HBX context remain unchanged.

The original-image admission verifier checks SHA-256, original
code/data size, entry and guest-mapping bounds and rejects **19**
altered/malformed cases. This is bounded source-pinned host research,
not a Nintendo Horizon ABI, complete architectural effect accounting
or cryptographic trust in a potentially compromised compiler.

### Original HBX stage-1 guest execution (PR #16 and later entry tests)

A research-only pinned Dynarmic adapter now attempts to run the original
HBLauncher `hbx_app_main` AArch64 instructions with an independently prepared,
source-defined HBX v3 context, immutable original RX code, separate RW data/BSS,
and a bounded guest stack. Only an exact `HBX_OK` stage-1 return and
source-defined `HBX_ERR_ABI` negative returns can be accepted; unauthorized
memory faults, service requests and missing returns fail closed. Stage 1
**bypasses the SDK `_start` trampoline** by directly entering the original
function. The pinned PR-head E3 CI executed **777 original AArch64 instruction steps**
before a verified `HBX_OK=0` stage-1 return, twice independently.
Three wrong source-defined context fields produced `HBX_ERR_ABI=2`;
unmapped pointers, denied writable stack, invalid entry and instruction budget
were rejected. Original code/data image SHA-256 values were checked.
No native host service, Nintendo Horizon service or console was invoked.
**This is not yet a full HBX app launch, Switch 2 Horizon implementation,
or game.** Original HBX `_start` execution has now passed the pinned E3 test:
**795 original AArch64 instructions** retired via the genuine upstream
trampoline, compared with 777 for direct function entry. Separate incoming
caller and context-provided application stacks are enforced. Original code
restored SP, X29 and X30, returned the source-defined stage-1 outcomes, and
preserved independent QEMU return parity. A prior aliasing-stack attempt
failed closed at an unsupported guest PC and was not promoted. This remains
a custom **HBX** test, not Nintendo Horizon process entry or hardware parity.
An independently compiled QEMU AArch64 reference now executes the **same
original HBLauncher app object** used by the NX2 Dynarmic guest adapter.
Exact source-defined stage-1 results matched for valid context and invalid
magic/version/size (0/2/2/2); 777 original instructions retired in NX2.
The QEMU comparison is **host-only** and directly enters the C function;
it does not prove the full `_start` trampoline or real Horizon/device ABI.

### Initial HBX host-only reference target

A pinned HBLauncher SDK v3 source revision and original host/QEMU AArch64
trampoline/runtime tests have a **reproducible opt-in CI lane**.
NX2 independently validates the frozen custom HBX context layout and
18 malformed or mutated ABI negatives. This is a *third-party host test
reproduction*, not an NX2 emulator executing HBLauncher, not Nintendo
Horizon ABI, and not a physical console observation. Accept it as a host-only result **only when** exact-head pinned CI passes;
never promote it to real Switch 2 execution. See
[research intake](research/hblauncher_host_abi_2026-10-29.md).

### Historical strategy checkpoint — October 29

The [October 29 strategy](STRATEGY_2026-10-29.md) proposed a cross-project
conformance corpus while the external executable was still a generic Linux
ARM64 fixture. The later NeXo/Eden measurements above supersede that workload
status. The independent CPU oracle and denied-access tests remain relevant,
while production backend qualification stays separate from their success.
