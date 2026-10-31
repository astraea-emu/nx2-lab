# Issue #21 — bounded NRO preflight (2026-10-30)

**Purpose:** original, small, standalone NX2-authored fail-closed test-fixture validation before submitting an NRO to an untrusted third-party emulator research runner. This is **not** a replacement for fixing Eden's loader or a validation of Switch 2-native software.

## Reason

Source inspection of frozen [Eden-NS2 NRO loader](https://github.com/0x2593/Eden-NS2/blob/e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c/src/core/loader/nro.cpp) found that `LoadNroImpl` computes a 4 KiB-aligned allocation from the untrusted NRO `file_size`, then copies that many bytes from `data.data()` without independently checking `data.size()`. It also reads a MOD0 structure at the declared module-header offset. No exploitation, crash or severity is claimed; the observed source code is sufficient justification for a conservative preflight and a later original-code ASan test.

## Tests

- `tools/reference/eden_ns2/nro_preflight.py` validates header magic and minimum length; sane declared image and BSS limits; full source byte availability for the **page-rounded copy Eden actually performs**; module-header range/alignment; all three loadable segment bounds, alignment and non-overlap.
- `test_nro_preflight.py`: independent synthesized NRO0-format inputs and nine tests covering acceptable images, truncated headers, malformed magic, huge lengths, invalid module offsets, overlaps, overlong segments, missing page padding and incorrect caller type.
- `.github/workflows/p0-nro-preflight.yml`: pin `NeXoNetwork/NeXo2-emu` commit `7fa73a5062e64370163a248d1a0b555272012c0f`, original source-owned NRO `tests/generated/hello.nro` Git blob `bb0ee2a52acd303e7c800443163aa91900eabb58`, 24,636 bytes. Check the authentic fixture is accepted, then reject six independently modified examples, including declared image size, BSS, module offset, data segment and shortened page-rounded read.
- This runs in a few seconds and needs no proprietary Nintendo content or platform SDK. No GPL Eden/NeXo source is copied into MIT NX2.

## Limits

A passing preflight does **not** guarantee that Eden safely handles every syntactically valid or malicious image; it does not validate guest CPU execution or Switch 2 software. It is an intentionally **conservative gate for a known, source-authored test fixture**, and may reject harmless NROs that other loaders accept. The original Eden input path still needs an independently verified bounds fix and sanitizer-backed regression before production use. The separately completed [NRO execution control](eden_nro_guest_probe_2026-10-30.md) records its own runtime limits. See [current status](../STATUS.md) for the remaining loader blockers under issue #21.
