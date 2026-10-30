# Issue #21 — original native ExeFS/extended-NPDM future guest fixture

**Status:** independent source-owned binary-input generation; **not executed inside Eden or on Nintendo hardware**.

## Why

The Switch 1-style NRO control in [PR #28](https://github.com/astraea-emu/nx2-lab/pull/28) exercises a shared homebrew loader, not the Switch 2-specific runtime surface. Eden-NS2's frozen source has a distinct ExeFS `main` + `main.npdm` loader path and detects an extended NPDM ACID position. The native process path uses a 12 GiB layout and Dynarmic compatibility handling. This does not establish that those choices are faithful to hardware.

## Original test input

`tools/reference/eden_ns2/make_native_exefs.py` generates **only two deterministic, NX2-authored files**:

- `main`: uncompressed NSO0 container with 0x100-byte header, page-aligned text/rodata/data records, deterministic per-segment SHA-256 and build ID, and **original ARM64 machine instructions**. Code uses PC-relative address formation to load a source-owned debug message from rodata, invokes `SVC 0x27` (debug output), then `SVC 0x7` (exit), with an explicit bounded branch if exit unexpectedly returns. No devkit, keys, firmware, title executable, copyrighted assets or external compiler are needed to generate it.
- `main.npdm`: original synthetic 0x600-byte META/ACI0/extended-ACID structure at the offset used by Eden's own source-authored `MakeMetadata(true)` tests, with synthetic permissions and title ID. This is **not a captured Nintendo NPDM**. Its classification and semantics must still be independently verified in the full original C++ loader, not inferred from the generator.

The generated source-owned NSO0 deliberately stores uncompressed 0x1000-byte segments with matching stored lengths, ensuring every file range is bounded and independently hashed. Nine Python unit tests verify deterministic bytes, original ARM64 opcodes, segment mappings/hashes, extended metadata identification and fail-closed mutations. Fast CI generates twice and compares exact bytes.

## Scope and future acceptance

A passing CI result means only that we can reproducibly generate structurally consistent **candidate input** under the public fork's interpretation of NSO and extended NPDM. It does **not** demonstrate that the actual Eden loader accepts the files, that guest ARM64 instructions execute, that a debug syscall succeeds, or that this is Switch 2 ABI-compatible.

After the NRO control's real CPU/loader logs are resolved, run this exact fixture through a separately built, bounded Eden ExeFS guest trial. Reject any unsupported interface explicitly; compare original guest outputs and malformed-header controls. The native NPDM reload regression in [PR #30](https://github.com/astraea-emu/nx2-lab/pull/30) tests a different source-level correctness condition.

No GPL source is copied into the MIT repository; only technical-format facts inspected from the frozen [Eden-NS2 NSO loader](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/loader/nso.h) and the fork's original [synthetic metadata tests](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/tests/core/program_metadata.cpp) informed these new fixtures.
