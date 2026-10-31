# Issue #21 — Original native ExeFS/NPDM runtime qualification (2026-10-31)

**Native lifecycle and real service-manager IPC controls passed; PR #32 merged.** This workflow tests the wholly NX2-authored `main` NSO0 plus synthetic extended-ACID `main.npdm` created in merged PR #31 through the **actual pinned Eden command-line executable**. Its first run reached the guest's own SVC output on the native-classified path, then failed lifecycle acceptance. A later runtime produced natural valid exit and typed invalid rejection but exposed a diagnostic-format mistake in the checker. The final run passed the corrected controls and the new IPC guest, as recorded below. This does not establish physical Switch 2 ABI compatibility.

Pinned source: GPL `0x2593/Eden-NS2` SHA `e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`, with the measured one-line Clang cast correction and the explicit, original-blob-checked process-exit/SDL cleanup overlay from PR #28 in an isolated runner. This is a patched reference build, not unmodified Eden. No GPL implementation files, device SDK, game, keys or firmware data are vendored into MIT NX2. Input `main` SHA-256 `508edcf6870546ed2f67c6ed11f0df3deb0242427ea2b9d7562ae6d015084ed5`; corrected synthetic `main.npdm` SHA-256 `64e25a2e3e37495d75341f9564afa3e6a665f10f94b36ea7e4e3c533b4573148`. Original guest uses ARM64 instructions to request output of `NX2 original extended ExeFS guest reached debug SVC`.

**Acceptance:** actual source-tagged Eden log records must show, in order, native ExeFS 12 GiB classification, the specific **guest-authored** message from `Kernel::Svc::OutputDebugString`, and the real `ExitProcess` SVC. The valid process must return **0** without assertions or guest-execution faults. Independently, an invalid-`META` negative fixture must produce the specific bad-NPDM-header loader error and return **1**, without executing guest output/exit, assertion, crash or timeout. A diagnostic followed by signal exit 139 is a failure. Each input gets an isolated temporary home/config, dummy SDL, null renderer and a 15-second timeout. Failure preserves original binary-safe diagnostics and a short-lived raw log artifact. Fixture, assessor and overlay source changes all trigger this runtime gate.

## First trial and focused correction

[Run 41224123601](https://github.com/astraea-emu/nx2-lab/actions/runs/41224123601) built all 1443 CLI steps and observed native classification, the guest's own debug message, and its ExitProcess request. It nevertheless failed: valid status **124**, invalid status **137** with an empty log. A `k_thread.cpp:140` priority-mask assertion preceded guest execution.

The assertion came from NX2's fixture: main-thread priority byte `0x0E` was zero, while the supplied capability admits priorities 16–63. Set this byte to **44**, the frozen emulator's existing default; the NSO and guest instructions remain byte-for-byte unchanged. See the [fixture correction](eden_native_exefs_fixture_2026-10-30.md). Reuse the source-pinned lifecycle overlay already observed to produce adapted-NRO status 0 and malformed-NRO status 1 in [run 41223767907](https://github.com/astraea-emu/nx2-lab/actions/runs/41223767907). The next section records the fresh native-runtime result for both changes.

The previous assessor reported assertions/timeouts without rejecting all of them. Its replacement rejects the historical positive failure even if malformed-input cleanup is repaired, rejects missing or reordered source-tagged exit evidence, and rejects unexpected statuses in either control. Unit tests exercise those false-positive paths; only the full emulator run establishes runtime success.

## Corrected runtime outcomes and diagnostic-format correction

[Run 41229858618](https://github.com/astraea-emu/nx2-lab/actions/runs/41229858618)
at head `6c55524cb00377d1953266624dffd9d9b77870e3` built all 1,443 CLI
steps and executed both inputs. The source-built processes independently gave:

| Input | Actual observations | Exit status |
| --- | --- | --- |
| Corrected original ExeFS | Source-tagged 12 GiB classification, original guest debug output, real ExitProcess in order; no assertions or execution faults | **0** |
| Corrupted META | Source-tagged Core Load error **4**, Frontend SDL_AppInit error **0007-0004**, description **4**; no guest execution, assertions or execution faults | **1** |

The workflow itself **failed** because the checker expected the English text
`The NPDM file has a bad header.`. Frozen
[`loader.h`](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/loader/loader.h)
(blob `d3c0230cb0637bbd227ba30b703960f0b50ecbb6`) defines
`ErrorBadNPDMHeader` as enum value **4**. The
[CLI](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/yuzu_cmd/yuzu.cpp)
prints that enum directly, and its
[generic enum formatter](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/common/logging.h)
uses the underlying integer. The English lookup function is not used here.
This was a checker mistake, not a new runtime failure or a reason to relax
exit-status, provenance or fault requirements.

The corrected checker requires one genuine Core Load error 4 followed by one
genuine Frontend SDL_AppInit loader-error block, including its immediate
`Error Code: 0007-0004` and matching numeric or exact English description.
Generic error 4, host echoes, mismatched codes, incomplete/reordered/duplicate
blocks, crashes and timeouts fail. Positive classification, output and exit
also require unique full source-tagged lines in order; host-prefixed echoes
and embedded NUL corruption fail. Its **26 regression tests pass**. Two
independent replays of the preserved actual logs, using their observed statuses
0 and 1, pass the corrected gate. Raw artifact ZIP SHA-256:
`ffeaf07fda13c16ce5d5fa2e3e8c6cdd29a8f02619605f93fd9a5b6814c087df`.
This does not turn the original failed CI run green; the final record below
documents the separate successful run of the revised head.

The failed checker also skipped the old cache post-save. The workflow now
saves compiler objects explicitly before runtime acceptance, while preserving
job failure when any test fails. Build parallelism is capped at four workers
only when the runner reports at least four CPUs, 14 GiB total and 12 GiB
available memory; otherwise it uses at most two. These changes affect build
cost, not emulator acceptance. The final run retained both controls and added the
[original reply-checking service-manager guest](eden_native_ipc_runtime_2026-10-31.md).

## Final workflow acceptance

[Run 41233784596](https://github.com/astraea-emu/nx2-lab/actions/runs/41233784596)
passed at head `6adfaada80f9afdea3175629d8f5d144d5c6cd34`. The original
valid control exited **0**, malformed META exited **1** with the exact typed
NPDM diagnostic, and the IPC guest exited **0** after verifying all 21
observed fields and closing its two distinct handles. The valid and invalid
controls retained their required source provenance and fault checks; no
execution assertion, fault or unexpected stub was observed in the raw logs.

All seven checks for the commit passed before
[PR #32](https://github.com/astraea-emu/nx2-lab/pull/32) merged as
`2d9bb0064f4d53b255805fffcb28839977e374c4`. The source tree matches the tested
tree `d29a2c05297a6e4e2115428ad90097a84bc60c98`. The
[IPC record](eden_native_ipc_runtime_2026-10-31.md) preserves every observed
reply field and the three-log artifact digest. These results close the bounded
CPU/HLE lifecycle and service-manager workload; production adoption remains
HOLD.

**Limitations:** even passing this check proves only synthetic guest execution through Eden's experimental *modeled* native program pathway. It is not hardware-backed Switch 2 ABI fidelity, 3D rendering, firmware emulation, commercial game compatibility, host platform parity or production-engine acceptance. Continue #21's HOLD until stricter Switch 2 evidence is obtained. The independently confirmed original-source metadata stale-state bug/isolated repair from merged PR #30 is a separate prerequisite. The excluded upstream native-GPU test file still leaves 31 cases unqualified: eight MME cases and 23 other GPU cases.
