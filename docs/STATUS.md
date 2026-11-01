# Status

**Verified 2026-11-01. Production-engine adoption: HOLD.**

NX2 is useful as a regression lab. Its own `nx2lab` executable is a bounded
CPU/memory oracle; the guest results below belong to separately built engines.
An original graphical guest produces independently verified pixels through
one reproducible Linux command. The [active milestone](PLAN.md) advances from
CPU-drawn presentation to an original guest GPU draw and shader execution.

## Measured results

| Workload | Observed result | Evidence |
| --- | --- | --- |
| Strict native GPU unit slice | **62 cases / 25,395 assertions**, exit 0, zero failures or skips. **29 restored + 33 existing** cases; two DMA cases remain excluded. | [PR #34](https://github.com/astraea-emu/nx2-lab/pull/34) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41245699243) |
| Original synthetic ExeFS | Guest message and real `ExitProcess`, exit 0. Malformed META separately rejected with Core error 4 / Frontend 0007-0004, exit 1, before guest execution. | [PR #32](https://github.com/astraea-emu/nx2-lab/pull/32) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41233784596) |
| Original service-manager guest | All **21 observed reply fields** checked by ARM64 guest code; initialization, `set` acquisition, expected empty-name error `0xc15`, two handles closed and natural exit 0. | [Same runtime run](https://github.com/astraea-emu/nx2-lab/actions/runs/41233784596) |
| Original VI2 lifecycle guest | **215 observed fields**; duplicate/missing-client refusals; 127-byte rejection without consumption; 128-byte notification `0x4`, then clear; all buffer guards intact, seven handles closed and natural exit 0. | [PR #39](https://github.com/astraea-emu/nx2-lab/pull/39) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41261352557) |
| Original image guest | Two CPU-drawn colour variants, **281 observed fields** each, exact **1920×1080 BGRA/alpha** capture comparisons, eight handles closed and natural exit 0. | [PR #41](https://github.com/astraea-emu/nx2-lab/pull/41) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41268515967) |
| Shared Linux setup and repeat | First complete command **101.0 s**; repeat **16.1 s**, same engine executable and fresh matching captures for both variants. | [PR #43](https://github.com/astraea-emu/nx2-lab/pull/43) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41270879484) |
| Eden NRO lifecycle | Original executes but faults on return and times out (124). Labeled four-byte exit-thunk variant plus lifecycle repair exits 0. Malformed input rejects (1) **with an AES assertion**. | [PR #28](https://github.com/astraea-emu/nx2-lab/pull/28) · [actual run](https://github.com/astraea-emu/nx2-lab/actions/runs/41229946626) |

Eden results use revision `e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c` with
explicitly recorded build/lifecycle repairs. The GPU run used
`EDEN_NATIVE_STRICT=1`; the restored cases comprise 24 unchanged bodies and
five compatibility adaptations. Compile-time DMA exclusions are outside the
62-case result. The ExeFS, IPC and image guests produced no assertion,
execution fault or unexpected stub.

The VI2 and image runs recorded five empty-path, one missing-title and three
uninitialized-network errors before guest entry, plus the one known
manager-getter warning. Its checker bounds these exact diagnostics by source,
count and phase; unexpected errors, stubs, faults and timeouts fail acceptance.

The image checker requires the real saved-capture callback before guest
cleanup and checks every pixel against a logical reference independent of
the guest's block layout. Each changed-colour capture fails the other variant's
reference. The first runtime trial exposed two checker source-line mistakes;
[PR #41](https://github.com/astraea-emu/nx2-lab/pull/41) retains that failure and
the exact corrections. The [local command](../CONTRIBUTING.md#original-image-trial-linux)
now fetches, prepares and builds the engine through the same recipe as CI.
The measured first run used **1,268/1,269 compiler-cache hits**, after system
prerequisites were installed; it is not a cold-build benchmark. Engine preparation
took 90.1 s initially and 6.2 s on reuse. Both invocations retain fresh evidence.
Source, dependency fingerprints, tool identities, system package versions,
configuration and executable are checked on reuse.

The [repository review](https://github.com/astraea-emu/nx2-lab/pull/42) corrected
false-positive fixture/runtime checks, incomplete NRO allocation checks and
unbounded input reads. These improve acceptance evidence, not engine capability.
One later [runtime trial](https://github.com/astraea-emu/nx2-lab/actions/runs/41272036375)
failed because concurrent startup messages interleaved in Eden's console log.
The shared recipe now locks each complete POSIX console record; the strict
evidence checker remains unchanged. [PR #43](https://github.com/astraea-emu/nx2-lab/pull/43)
retains that failure, the source-guarded repair and its concurrency regression.

[Evidence](SOURCES.md) preserves earlier full records, source/input hashes,
applied changes, raw-report digests and earlier failures. Dated proposals
remain historical; [Plan](PLAN.md) defines the current next step.

## Limits and blockers

- **Graphics:** the verified path presents a CPU-drawn image through Vulkan
  on Linux/Lavapipe. Guest GPU shader execution, two DMA contracts, production
  macro/JIT paths and the complete upstream suite remain unqualified.
- **Loader:** malformed NRO identification asserts in `core/crypto/aes_util.cpp`.
  Original parser bounds need a verified fix and sanitizer-backed regression;
  fixture preflight does not contain an untrusted guest.
- **Production:** dependency/license review, host containment and relevant
  platform qualification remain open in [#21](https://github.com/astraea-emu/nx2-lab/issues/21).

Core CI covers Linux, Windows and macOS; full external-runtime results are
Linux-only. The synthetic extended-NPDM guests establish source-model IPC,
not physical Switch 2 ABI fidelity. There are no NX2 console measurements,
verified commercial-game results or developer SDK. The local CLI accepts
NX2OWNED fixtures, not Nintendo executable formats.
