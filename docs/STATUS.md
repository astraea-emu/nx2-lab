# NX2 Lab — status

**Last verified: 2026-10-31. Production-engine decision: HOLD.**

The active milestone is [#21: qualify a mature runtime or an upstream
contribution path](https://github.com/astraea-emu/nx2-lab/issues/21).
The active qualification gate is [strict native-GPU coverage](PLAN.md).
NX2's own `nx2lab` executable remains a small correctness oracle; measured
external-runtime behavior belongs to the separately built engine.

## Latest verified workload

[PR #32](https://github.com/astraea-emu/nx2-lab/pull/32) merged after all seven
checks passed at [`6adfaada80f9afdea3175629d8f5d144d5c6cd34`](https://github.com/astraea-emu/nx2-lab/commit/6adfaada80f9afdea3175629d8f5d144d5c6cd34);
the merge is [`2d9bb0064f4d53b255805fffcb28839977e374c4`](https://github.com/astraea-emu/nx2-lab/commit/2d9bb0064f4d53b255805fffcb28839977e374c4).
[Runtime run 41233784596](https://github.com/astraea-emu/nx2-lab/actions/runs/41233784596)
executed three independent inputs in the patched frozen Eden build:

| Input | Measured result |
| --- | --- |
| Original debug/exit ExeFS | Native-classified 12 GiB layout, original guest message and `ExitProcess` in order; status **0** |
| Corrupted META | Typed Core error **4** / Frontend **0007-0004** rejection; status **1**; no guest execution |
| Original service-manager guest | All **21 observed reply fields** checked by the ARM64 guest, successful initialization and `set` acquisition, expected empty-name error `0x00000c15`, both handles closed, natural exit; status **0** |

No assertion, execution fault or unexpected stub appeared in those three logs.
The [IPC record](research/eden_native_ipc_runtime_2026-10-31.md) preserves all
observed values, source and input hashes, the raw artifact digest and limits.
The [lifecycle record](research/eden_native_exefs_runtime_2026-10-31.md)
preserves the earlier priority failure, timeout/rejection failures and the
later numeric-diagnostic checker failure. Those runs remain failed historical
experiments. The same revision also passed **112 local Python tests and 13
core CTest groups**; these are supporting checks, separate from runtime proof.

This establishes shared Horizon-style IPC in a synthetic extended-NPDM process
on Linux. It does not establish a physical Switch 2 ABI or a graphics result.

## Evidence index

Dated records retain the experiment's scope, source pins, applied changes,
failures and acceptance criteria. Their historical next steps do not override
[the current plan](PLAN.md).

| Experiment | Established result and boundary | Record / run |
| --- | --- | --- |
| NeXo original NRO | Unchanged Switch 1-format homebrew executed its calculations and exited; malformed images rejected. | [#25](https://github.com/astraea-emu/nx2-lab/pull/25) · [CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41092724871) |
| Eden source contracts | 94 assertions in GNU C++ and Clang ASan/UBSan against original native-facing headers; source-model evidence. | [Record](research/runtime_baseline_eden_ns2_2026-10-30.md) · [CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41094596650) |
| Integrated Eden libraries | Reduced original suite: **33 cases / 9,103 assertions**. One excluded native-GPU file contains **31 cases: 8 MME and 23 other**. | [Record](research/eden_ns2_full_build_gate_2026-10-30.md) · [CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41115025130) |
| Eden NRO lifecycle | Original input executes but faults on return and times out (**124**); labeled four-byte exit-thunk variant plus lifecycle repair exits (**0**); malformed magic is rejected (**1**) **with an AES-probe assertion**. | [Record](research/eden_nro_guest_probe_2026-10-30.md) · [CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41229946626) |
| NRO fixture preflight | Authentic input accepted and six mutations rejected before runtime admission; Eden's own parser remains unfixed. | [Record](research/eden_nro_input_preflight_2026-10-30.md) · [CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41127444547) |
| NPDM reuse | Actual original C++ retains stale `IsSwitch2()` state; the reproduced failure passes after an isolated one-line reset. | [Record](research/eden_ns2_npdm_reload_2026-10-30.md) · [CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41136582253) |
| Original ExeFS inputs | Deterministic ARM64 NSO0 and synthetic extended NPDM; the later priority correction and actual runtime result are separately recorded. | [Fixture](research/eden_native_exefs_fixture_2026-10-30.md) · [CI](https://github.com/astraea-emu/nx2-lab/actions/runs/41132733015) · [Runtime](research/eden_native_exefs_runtime_2026-10-31.md) |

Frozen runtime revisions: Eden-NS2
`e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`; NeXo
`7fa73a5062e64370163a248d1a0b555272012c0f`.
The original NeXo `hello.nro` blob is
`bb0ee2a52acd303e7c800443163aa91900eabb58`.
Eden results use the explicitly documented isolated build/lifecycle repairs.
GPL implementation source stays outside this MIT repository.

## What remains open

- **Native GPU:** the [31-case audit](research/eden_native_gpu_test_reconciliation_2026-10-31.md)
  identifies **29 restoration candidates**, comprising 24 unchanged cases and
  five compatibility adaptations. **Two DMA contracts remain unresolved.**
  These counts are source-review findings, not integrated test passes.
- **Loader robustness:** malformed NRO identification asserts in
  `core/crypto/aes_util.cpp:97` (`EVP_CipherInit_ex2`). Terminating rejection is
  not assertion-free parsing. Original loader bounds also need a verified fix
  and sanitizer-backed regression; preflight is not a sandbox.
- **Production qualification:** dependency/license review, host containment,
  relevant platform coverage and stronger independent interface evidence
  remain necessary before adopting an engine.

Core NX2 CI covers Linux, Windows and macOS. Full external-runtime evidence is
Linux-only. No physical-console observations, hardware ABI parity,
guest-produced frame, commercial-game compatibility or exploit is established.
The local `nx2lab` CLI accepts only NX2OWNED fixtures, not Nintendo formats.

## Earlier controls and background

| Record | Scope |
| --- | --- |
| [CPU reference baseline](research/cpu_reference_baseline_2026-10-31.md) | Generic CPU/memory, Dynarmic and external ELF controls |
| [HBX host ABI](research/hblauncher_host_abi_2026-10-29.md) and [original guest](research/hblauncher_original_guest_2026-10-29.md) | Custom HBX stage 1, original entry, write accounting and QEMU return parity; stage 2 remains a secondary regression |
| [October 30 architecture audit](COMPETITIVE_ARCHITECTURE_AUDIT_2026-10-30.md) | Dated candidate comparison and rationale for the external-runtime path |
| [October 29 strategy](STRATEGY_2026-10-29.md) and [competitive snapshot](COMPETITIVE_RESEARCH_2026-10-29.md) | Historical proposals and project claims; superseded workload status |
| [Public sources](SOURCES.md) and [compatibility evidence matrix](COMPATIBILITY_EVIDENCE_MATRIX.md) | Dated research leads and confidence categories |
| [Publication history](PUBLISH.md) | Original repository publication and evidence-byte portability |
