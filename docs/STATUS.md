# Status

## Current state — November 11, 2026

`main` at `b244712e092ff42d8445242425a19160944d7a38` is **NX2 Lab**,
not a standalone Switch 2 emulator. The active goal is a full game-capable
runtime built on a measured maintained foundation; see [Plan](PLAN.md) and
[issue #50](https://github.com/astraea-emu/nx2-lab/issues/50).

Later work is preserved in **draft, unmerged** pull requests:

| Work | Latest observed result | Open gate |
| --- | --- | --- |
| [#46 — GPU animation](https://github.com/astraea-emu/nx2-lab/pull/46) | Four-frame original GPU output verified in controlled runs | Intermittent post-guest-exit host failure; HOLD |
| [#47–#48 — modern engines](https://github.com/astraea-emu/nx2-lab/pulls) | Source-built Eglantine/Lichii execute original ARM64 and capture pixel-matched images | Overall native protocol and cleanup qualification |
| [#49 — NPDM and diagnostics](https://github.com/astraea-emu/nx2-lab/pull/49) | Both engines reject malformed META before guest execution; original image variants pass exact-pixel tests | Combined ExeFS run fails on two host crypto assertions at `core/crypto/aes_util.cpp:97` per run; source traced, cause not yet established |

At [PR #49 head `57575bc5`](https://github.com/astraea-emu/nx2-lab/commit/57575bc5932d9cf991a64296b1623d8dc97a31f7),
general CI passed 400 offline Python tests (16 skipped), Linux, Windows and
macOS builds, and sanitizers. The
[modern-engine runtime workflow](https://github.com/astraea-emu/nx2-lab/actions/runs/43136579956)
**failed on both engines**. A green general CI matrix does not override that
result. The modern image-size negative and true display finalization also
remain unresolved. These results do not establish game compatibility.

## Merged baseline — verified November 1, 2026

The `nx2lab` executable is a bounded CPU/memory oracle. Its reference
workloads run in separately built Eden engines: an original guest renders two
native GPU triangle colours plus a clear-only control, with independent pixel
comparison and natural exit. Animation was the next milestone at that time;
[the plan](PLAN.md) now prioritizes a complete emulator runtime.

## Measured results

| Workload | Observed result | Evidence |
| --- | --- | --- |
| Engine comparison | Both revisions passed byte-identical original inputs, all CPU/GPU captures and fresh repeats; loader/META, SM, VI2 and strict GPU controls preserved. Newer revision selected for controlled Linux workloads. | [PR #45](https://github.com/astraea-emu/nx2-lab/pull/45) · [runtime comparison](https://github.com/astraea-emu/nx2-lab/actions/runs/41332269077) · [GPU controls](https://github.com/astraea-emu/nx2-lab/actions/runs/41332269059) |
| Strict native GPU unit slice | **62 cases / 25,395 assertions**, exit 0, zero failures or skips. **29 restored + 33 existing** cases; two DMA cases remain excluded. | [PR #34](https://github.com/astraea-emu/nx2-lab/pull/34) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41245699243) |
| Original synthetic ExeFS | Guest message and real `ExitProcess`, exit 0. Malformed META separately rejected with Core error 4 / Frontend 0007-0004, exit 1, before guest execution. | [PR #32](https://github.com/astraea-emu/nx2-lab/pull/32) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41233784596) |
| Original service-manager guest | All **21 observed reply fields** checked by ARM64 guest code; initialization, `set` acquisition, expected empty-name error `0xc15`, two handles closed and natural exit 0. | [Same runtime run](https://github.com/astraea-emu/nx2-lab/actions/runs/41233784596) |
| Original VI2 lifecycle guest | **215 observed fields**; duplicate/missing-client refusals; 127-byte rejection without consumption; 128-byte notification `0x4`, then clear; all buffer guards intact, seven handles closed and natural exit 0. | [PR #39](https://github.com/astraea-emu/nx2-lab/pull/39) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41261352557) |
| Original image guest | Two CPU-drawn colour variants, **281 observed fields** each, exact **1920×1080 BGRA/alpha** capture comparisons, eight handles closed and natural exit 0. | [PR #41](https://github.com/astraea-emu/nx2-lab/pull/41) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41268515967) |
| Original GPU triangle | Native C797 commands and original vertex/fragment shaders; two colours and a clear-only control; **618 observed fields** per guest, exact captures, nine handles and three device FDs closed, natural exit 0. | [PR #44](https://github.com/astraea-emu/nx2-lab/pull/44) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41274716233) |
| Earlier baseline setup and repeat | First complete command **101.0 s**; repeat **16.1 s**, same engine executable and fresh matching captures for both variants. | [PR #43](https://github.com/astraea-emu/nx2-lab/pull/43) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41270879484) |
| Eden NRO lifecycle | Original executes but faults on return and times out (124). Labeled four-byte exit-thunk variant plus lifecycle repair exits 0. Malformed input rejects (1) **with an AES assertion**. | [PR #28](https://github.com/astraea-emu/nx2-lab/pull/28) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41229946626) |

The default development revision is
`b2cef0c0f2e8517673233e22c929918e2c60e654`; baseline
`e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c` remains an explicit comparison option.
The candidate needs the same guest-exit, frontend-lifecycle and console-record
repairs; the baseline's cast correction is already upstream. The comparison
reproduced the earlier native results on both revisions, including all 62 GPU
cases / 25,395 assertions. [NRO controls](https://github.com/astraea-emu/nx2-lab/actions/runs/41332269047)
also reproduced both known failures and the adapted program's natural exit.

GPU trials used `EDEN_NATIVE_STRICT=1`; the restored cases comprise 24 unchanged
bodies and five compatibility adaptations. Compile-time DMA exclusions are outside the
62-case result. The ExeFS, IPC and image guests produced no assertion,
execution fault or unexpected stub.

The VI2 and image runs recorded five empty-path, one missing-title and three
uninitialized-network errors before guest entry, plus the one known
manager-getter warning. Its checker bounds these exact diagnostics by source,
count and phase; unexpected errors, stubs, faults and timeouts fail acceptance.

Both graphics checkers require the real saved-capture callback before cleanup.
The triangle starts from a uniform yellow CPU sentinel, then the GPU clears
and draws into a **16×9 target**, presented at 120× nearest-neighbour scale.
The independent oracle checks all **1920×1080 BGRA/alpha pixels**. Each colour
fails the other's reference; clear-only fails both. Runtime shader-page snapshots
match the original inputs exactly. Strict execution, source-attributed shader
lowering and draw records, the TSG binding, returned fence and cleanup are required.
The observed host counter establishes ordered engine progress; the saved Vulkan
readback establishes rendered output. No new engine repair was needed for this draw.

The [local command](../CONTRIBUTING.md#original-image-trial-linux) fetches,
prepares and builds the engine through the same recipe as CI.
The first candidate invocation took **1,599.9 s**, including 1,589.3 s of engine
preparation, with **565/1,269 compiler-cache hits** from a baseline seed.
Its CPU-image repeat took **15.3 s**; GPU invocations took **20.4 s** and **20.5 s**,
each including about 6 s of validated engine reuse. These are setup and
verification timings, not cold-build or emulation-performance benchmarks.
Every invocation retains fresh evidence.
Source, dependency fingerprints, tool identities, system package versions,
configuration and executable are checked on reuse.

Earlier checker corrections and failures remain in
[PR #41](https://github.com/astraea-emu/nx2-lab/pull/41) and the
[repository audit](https://github.com/astraea-emu/nx2-lab/pull/42).
[PR #43](https://github.com/astraea-emu/nx2-lab/pull/43) retains the interleaved-log
failure, source-guarded console-record locking repair and concurrency regression.

[Evidence](SOURCES.md) preserves earlier full records, source/input hashes,
applied changes, raw-report digests and earlier failures. Dated proposals
remain historical; [Plan](PLAN.md) defines the current next step.

## Limits of the merged baseline

The following limitations describe the November 1 `main` baseline. Draft
experiments above have additional results but are not merged or release-qualified.


- **Graphics:** one untextured triangle and its colour edit are verified on
  Linux/Lavapipe. Repeated frames and buffer reuse, textures, two DMA contracts,
  production macro/JIT paths and the complete upstream suite remain unqualified.
- **Loader:** malformed NRO identification asserts in `core/crypto/aes_util.cpp`.
  Original parser bounds need a verified fix and sanitizer-backed regression;
  fixture preflight does not contain an untrusted guest.
- **Candidate coverage:** missing-service success placeholders and broader
  shader lowering remain outside the original workload's qualification.
  Unexpected placeholders still fail our positive-workload checks.
- **Production:** dependency/license review, host containment and relevant
  platform qualification remain open in [#21](https://github.com/astraea-emu/nx2-lab/issues/21).

Core CI covers Linux, Windows and macOS; full external-runtime results are
Linux-only. The synthetic extended-NPDM guests establish source-model IPC,
not physical Switch 2 ABI fidelity. There are no NX2 console measurements,
verified commercial-game results or developer SDK. The local CLI accepts
NX2OWNED fixtures, not Nintendo executable formats.
