# Issue #21 — Reconcile the excluded native GPU tests

**Audit date:** 2026-10-31

**Status:** implementation proposal supported by frozen-source inspection and a bounded local interpreter check. No restored full Catch2 run is claimed.

The excluded `native_gpu_characteristics.cpp` translation unit contains **31 cases: 8 about MME and 23 about other native GPU behavior**. Seven cases use a stale interpreter interface. Source review identifies **24 unchanged candidates and 5 compatibility candidates**, giving **29 candidates for restoration**. The remaining **2 cases mix interpreter checks with DMA contracts that changed in the production caller**. Those two require a semantic decision; an API rename is insufficient.

These counts describe the scope of the next qualification change. They are **not a claim that 29 cases have passed**. The full frozen upstream test suite remains unqualified. This audit neither adopts the engine for production nor establishes GPU hardware parity, a rendered frame, or game compatibility.

## Context and evidence boundaries

The earlier full-build experiment failed while compiling this file after the isolated texture-cache cast correction. The current reduced-suite workflow removes the file's single CMake entry, which removes all 31 cases together. The [full-build qualification record](eden_ns2_full_build_gate_2026-10-30.md) preserves that failure and exclusion.

The work described here has three distinct evidence levels:

| Evidence | What it establishes | Limit |
|---|---|---|
| Exact frozen-source inspection | Case inventory, public API differences, ownership of DMA operations, and current control flow | Does not establish that the complete test target compiles or passes |
| Temporary host execution of the unchanged frozen interpreter header | Five adapted test bodies retained their original assertion expectations and completed 131 assertion evaluations | A local supporting observation, outside Catch2 and the integrated emulator |
| Future restored Catch2 execution | Would establish which explicitly included cases compile and pass in the frozen linked test target | Has not occurred as part of this audit |

The local helper and its build artifacts were temporary and are not persisted in this repository. The local observation therefore has no repository reproduction command or durable regression gate. A subsequent implementation must preserve its own reviewable adaptation, source guards, and execution evidence before promoting the result.

## Frozen sources

All upstream links below refer to **`0x2593/Eden-NS2@e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c`**. Git blob identities identify exact source contents, independently of line references.

| Source | Git blob |
|---|---|
| [Test translation unit](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/tests/core/native_gpu_characteristics.cpp) | `b54bd36ee35d433263f0bed967ca111391c03ea2` |
| [Tests CMake manifest](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/tests/CMakeLists.txt) | `ff1168471c5eb45aa54b78892b5f65e03391688f` |
| [Turing interpreter header](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro_turing.h) | `600db481198f1834ef0f83c3670727c427adebc2` |
| [Macro engine declarations](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro.h) | `b1b1a6095532c3c641170df70f0da128f693de39` |
| [Macro engine implementation](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro.cpp) | `48fa89a01e71c6348126bab13da67a6d8b36c989` |
| [QMD scheduler](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/native_qmd.h) | `3a985919e5684fcb076db5d6f702c84a4e3ff01f` |
| [GPU characteristics and profiles](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/nvdrv/devices/native_gpu_characteristics.h) | `4c8c16b1c5ebe2e46e861b9ad769b7bbad6380cd` |
| [GPU address-space layout](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/nvdrv/devices/gpu_address_space_layout.h) | `8be7ab173cbde493b40b0781b9c0f63c20396f9d` |
| [Native memory kinds](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/nvdrv/devices/native_gpu_kind.h) | `e0a36a139951171bdaca244fc82cb6465c5fd588` |
| [Native engine and TSG metadata](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/nvdrv/devices/native_gpu_context.h) | `c6d11880d57c54c394ea5ad5c75d55114fed9e3d` |
| [Sparse mappings](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/service/nvdrv/devices/native_sparse_remap.h) | `6fb10b069d0f1760b8d05eb14a99a3ac37db0d33` |
| [Root tables](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/native_root_table.h) | `89cb4ae0ef141c7e04045bc35b8836770e90ca0e` |
| [Vertex dirty flags](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/dirty_flags.cpp) | `e6856aaca33a2b8b4e7df882615b5d737944d248` |
| [Maxwell register definitions](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/engines/maxwell_3d.h) | `84c2a84fe3cd2fcd4a9d3ab1a4b7594681c45c48` |
| [Kernel memory blocks](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/hle/kernel/k_memory_block.h) | `2abca31d8737d7cb7276e170b7e2d8418549b588` |

At this revision the interpreter is implemented in `macro_turing.h`; there is no separate `macro_turing.cpp`. The production caller that performs DMA reads is in `macro.cpp`.

## Complete 31-case map

Topics below are paraphrased inventory labels, not copied test bodies. Start lines refer to the frozen test translation unit linked above.

- **U — unchanged candidate:** referenced APIs match the frozen implementation by inspection.
- **C — compatibility candidate:** input representation or entry-point adaptation can preserve the original assertions.
- **D — DMA contract dispute:** part of the original expectation no longer corresponds to the current ownership or behavior.

| # | Area | Case topic | Start line | Assessment |
|---:|---|---|---:|:---:|
| 1 | Other | Characteristics layout and interface-level fields | 33 | U |
| 2 | Other | Extended characteristics and shader profile | 90 | U |
| 3 | Other | Native virtual-address reservation size | 111 | U |
| 4 | Other | Validation of both small-page view formats | 124 | U |
| 5 | Other | Page-address arithmetic retaining upper bits | 143 | U |
| 6 | Other | GPU eligibility across kernel memory-block splitting | 150 | U |
| 7 | Other | Small-page preference and a separate large-page pool | 171 | U |
| 8 | Other | Uncompressed native memory-kind translation | 179 | U |
| 9 | Other | Reporting the selected fallback memory kind | 190 | U |
| 10 | Other | Classification of explicit engine identities | 231 | U |
| 11 | MME | Upload addressing and separation from legacy code storage | 244 | U |
| 12 | MME | Parameter consumption in zero-count and nonzero loops | 264 | C |
| 13 | MME | Carry propagation and incrementing method outputs | 294 | C |
| 14 | Other | Empty QMD release after its dependencies arrive | 309 | U |
| 15 | Other | Rejecting shader work without reporting completion | 334 | U |
| 16 | Other | Retaining child signals before QMD upload | 348 | U |
| 17 | Other | QMD sharing within a TSG and isolation across groups | 377 | U |
| 18 | MME | Both ALUs reading before either register writeback | 418 | C |
| 19 | MME | Taken back edges suppressing fallthrough termination | 435 | C |
| 20 | Other | Dispatch-before-release ordering and reduction flags | 456 | U |
| 21 | Other | Vertex byte counts and per-stream dirty state | 482 | U |
| 22 | Other | Shader profile independent of characteristics reply size | 504 | U |
| 23 | Other | TSG subcontext bounds and reserved-byte validation | 535 | U |
| 24 | MME | FIFO barrier, DMA-fed comparison, and read failure | 563 | D |
| 25 | MME | Oversized FIFO DMA and unsupported extended operations | 607 | D |
| 26 | MME | Persistent data-RAM isolation across interpreter instances | 629 | C |
| 27 | Other | Wide sparse-remap page fields and input validation | 684 | U |
| 28 | Other | Sparse replacement, source offsets, and live handles | 724 | U |
| 29 | Other | Overlapping remaps checked against a per-page model | 746 | U |
| 30 | Other | Root-table FIFO values and partial replacement | 780 | U |
| 31 | Other | Root-table byte alignment and bounds | 802 | U |

The **23 non-MME cases plus the MME upload case** make up the 24 unchanged candidates. The **four raw-program interpreter cases plus the persistent-data-RAM case** make up the five compatibility candidates. The two disputed cases are both MME-related. The accounting is therefore **24 + 5 + 2 = 31**, with **8 MME + 23 other = 31**.

An unchanged API does not guarantee a passing assertion or a successful integrated link. Those outcomes remain part of the next run.

## Compatibility adaptations that preserve the assertions

### Four raw-program cases: mutable parameter FIFO

The [current execution entry point](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro_turing.h#L78-L105) accepts a mutable `std::vector<Word>&` as its parameter FIFO. The obsolete tests pass constant arrays or an empty span. The mutable container is intentional: the caller may append DMA-read words while execution consumes the FIFO.

For cases 12, 13, 18, and 19, the minimal change is to supply mutable vectors with the same values and use a named empty vector where the test supplies an empty span. Preserve the raw program words, start offsets, result checks, consumed counts, method/value assertions, iteration counts, and failure expectations.

The local host check compiled the exact frozen header and ran these four original test bodies with only that container adaptation. All **53 original assertion evaluations** completed successfully. This supports the narrow compatibility diagnosis; it does not replace execution in the integrated Catch2 target.

### Persistent data RAM: raw instruction encoding

Case 26 constructs a removed `Instruction` type and invokes the removed `ExecuteDecoded` entry point. The current `Decoded` structure is used by the interpreter's cache. It has an `end` field, while load requirements are derived from encoded register and output selectors. The former independently set `load_mask` and `end_next` fields are not current execution inputs.

A test-only adaptation can encode the same store/load operations into raw 96-bit instructions and call the existing `Execute` entry point. The encoding must respect the uploaded-word order: the interpreter reverses each uploaded three-word group before decoding its fields. Simply renaming the old structure is insufficient. [Decoder and cache behavior](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro_turing.h#L28-L105)

Preserve both interpreter instances, the three tested data-RAM indices, distinct stored values, repeat count, exact output method/value checks, and success assertions. A temporary raw-encoding adapter exercised that original behavior through the frozen header. Combined with the four cases above, the five bodies completed **131 assertion evaluations with the original expectations preserved**. Calls inside the data-RAM success assertions used the adapted entry point. This number includes repeated evaluations inside loops; it is not a count of 131 distinct assertion expressions or Catch2 cases.

The current production caller can also redirect `active_dram` to channel-owned memory while using shared macro code. The original two-instance test does not establish that production sharing arrangement. If that behavior is qualified later, add a separately identified ownership test rather than describing the existing assertion set as broader coverage. [Data-RAM ownership fields](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro_turing.h#L256-L271)

## Two DMA cases require a contract decision

### Case 24: memory-read ownership and failure reporting

The old test passes a memory-read callback into the interpreter, tests both raw and decoded execution paths, expects six DMA words to feed the comparison program, and expects a specific failure when that callback fails.

The current interpreter has neither the separate decoded execution entry point nor the memory callback. The [production emit callback](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro.cpp#L1413-L1469) handles memory-address registers, data-RAM addressing, DMA reads, and FIFO append operations. The relevant method indices are `0x154`/`0x155` for the source address, `0x156` for the data-RAM address, `0x157` for data-RAM DMA, and `0x158` for FIFO DMA.

The positive comparison behavior can be exercised through the current interpreter with an explicit caller-side adapter that tracks those methods and supplies the six words. The adapter must check the requested address and count, FIFO consumption, and final method/value output. Such a helper would test that modeled boundary; it would not automatically test the production `MemoryManager` read path.

The old failed-memory-read expectation cannot be preserved by substituting the interpreter's generic emitted-method rejection. The [current interpreter](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro_turing.h#L234-L253) reports a different boundary when an emit callback returns false. The eventual test must state where memory-read failure is detected and propagated in the actual production caller.

### Case 25: the DMA count policy changed

The original test expects a FIFO DMA request of **1025 words** to be rejected. The frozen production callback instead reads up to **`0x1000` words (4096)**, clamping the requested count in its read loop. A 1025-word request is below that clamp. This is a semantic difference, not a parameter-container incompatibility. [DMA count handling](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro.cpp#L1427-L1455)

The unsupported-extended-operation portion of the case still corresponds to current interpreter behavior: the load-barrier operation accepts its particular selector and rejects unsupported selectors. That independent assertion should be retained even if the DMA policy test needs a separate caller-level location. [Extended-operation handling](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro_turing.h#L162-L166)

This audit does not establish which DMA limit matches hardware. Restoring the old 1024-word policy in production solely to satisfy this test would require separate justification. Equally, accepting the newer behavior by deleting the old failure assertion would conceal the unresolved contract.

## QMD strict mode is part of the tested contract

The excluded test file sets `EDEN_NATIVE_STRICT=1` in a static initializer before its cases execute. Preserve that assumption when restoring the translation unit. [Test setup](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/tests/core/native_gpu_characteristics.cpp#L21-L31)

The [QMD scheduler](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/native_qmd.h#L32-L118) has two relevant paths:

- Its overload without a supplied dispatch callback rejects nonempty shader work during validation.
- When a supplied dispatch callback returns false for nonempty work, strict mode returns a dispatch-required error before completion. Without the strict environment variable, the scheduler records skipped dispatch, marks the QMD completed, processes releases and dependent work, and returns a skipped-dispatch status.

Thus a release, dependency signal, or completion flag alone is insufficient evidence that shader work executed. The five restored QMD cases would qualify their stated strict-mode assertions. They would not establish correct default fallback behavior or successful GPU dispatch.

The scheduler checks the presence of the environment variable and caches the result within the instantiated function. The qualification setup should establish the environment before executing the relevant code and record it in the run. This source observation does not retroactively establish the environment used by other translation units or earlier runs.

## Proposed next implementation scope

The next change should reconcile the tests against the exact candidate source in an ephemeral checkout. Keep the GPL implementation and test bodies in that checkout; this MIT repository should contain original tooling, the source identities, and the research/acceptance record.

1. **Guard the input.** Verify the exact upstream commit and the test, interpreter, macro-caller, and CMake blobs before applying a compatibility overlay. Fail on a mismatch or an unexpected number of replacement sites.
2. **Restore unchanged coverage.** Preserve the 23 non-MME cases and the upload/storage case, including their assertions and strict-mode setup. Replace the current whole-file CMake exclusion with an explicitly documented reconciliation.
3. **Adapt only the five compatible cases.** Use mutable FIFO containers for the four raw programs and a reviewable raw encoding for the persistent-data-RAM case. Preserve every existing assertion and tested input value. Do not add removed interpreter APIs back into production solely to accommodate the tests.
4. **Make the two unresolved contracts visible.** If the first implementation isolates the two DMA cases so that the other 29 can build, identify those two by exact case identity and retain their original expectations in the audit trail. The run must continue to report two unresolved cases and a reduced qualification scope. Do not relabel the remaining run as the complete original suite.
5. **Run the actual linked target.** Build the frozen `tests` executable with the already documented source corrections and the declared test overlay. Export the registered and executed case list, the applied diff, strict-mode setting, exit status, and test output. Confirm the inventory matches the declared scope.
6. **Report new failures faithfully.** Distinguish compile/link failure, an original assertion failure, and a mismatch in the declared inventory. An unexpected failure warrants diagnosis, not another broad exclusion.

A later change can reconcile the DMA cases at the current production ownership boundary. That work should make the memory-read failure behavior and count policy explicit before deciding whether a test adaptation, a factored caller helper, or a production correction is justified.

## Acceptance and remaining qualification limits

Acceptance for the first restoration slice requires all of the following:

- The 31-case accounting is preserved, including any two specifically unresolved DMA cases.
- The 24 unchanged cases retain their original bodies and assertions.
- The five compatibility adaptations retain the original assertion set and input semantics.
- The actual linked Catch2 target builds and executes the declared cases under the documented strict-mode setting.
- Test failures, host faults, skipped cases, and omitted cases are visible in the resulting evidence.
- The reported result distinguishes the original frozen source from the explicitly patched test checkout.

Until that execution occurs, **29 remains a candidate count**. The temporary five-body result is only supporting evidence for the proposed adaptation.

The native macro engine also has a separate x86 JIT path enabled by default when available. Interpreter-only checks do not qualify that implementation. [JIT selection](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/video_core/macro.cpp#L1470-L1495)

A successful restored unit-test slice would improve confidence in the behavior those cases assert. It would still leave actual graphics service use, GPU command execution, shader execution, guest-produced frame output, and broader engine adoption as separate evidence gates.
