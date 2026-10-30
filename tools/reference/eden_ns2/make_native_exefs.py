#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate a deterministic, original ARM64 ExeFS/extended-NPDM test fixture.

The guest only emits one source-authored debug message and invokes ExitProcess.
This does NOT establish physical Switch 2 ABI correctness, emulator loading,
guest execution, or game compatibility. No proprietary files or SDK are used.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct

PAGE = 0x1000
NSO_HEADER = 0x100
NSO_MAGIC = b"NSO0"
NPDM_SIZE = 0x600
MESSAGE = b"NX2 original extended ExeFS guest reached debug SVC\n"
TITLE_ID = 0x0100123456780000


def words(*values: int) -> bytes:
    return struct.pack("<" + "I" * len(values), *values)


def build_guest_text() -> bytes:
    """AArch64 instructions at guest page zero, message at guest page one.

    adrp x0, +1 page; add x0, x0, #0; movz x1, #length;
    svc #0x27 (OutputDebugString); movz x0, #0; svc #0x7 (ExitProcess);
    b . (a defined stop if the service unexpectedly returns).
    """
    assert 1 <= len(MESSAGE) <= 0xFFFF
    insns = (
        0xB0000000,  # adrp x0, +0x1000 when executing at PC zero
        0x91000000,  # add x0, x0, #0
        0xD2800001 | (len(MESSAGE) << 5),  # movz x1, #message_length
        0xD4000001 | (0x27 << 5),  # svc #0x27
        0xD2800000,  # movz x0, #0
        0xD4000001 | (0x7 << 5),  # svc #0x7
        0x14000000,  # b .
    )
    return words(*insns).ljust(PAGE, b"\0")


def build_nso() -> bytes:
    """Uncompressed, self-authored NSO0 container for the frozen loader."""
    text = build_guest_text()
    rodata = MESSAGE.ljust(PAGE, b"\0")
    data = bytes(PAGE)
    segments = (text, rodata, data)
    header = bytearray(NSO_HEADER)
    struct.pack_into("<4sIII", header, 0, NSO_MAGIC, 0, 0, 0)
    for i, segment in enumerate(segments):
        assert len(segment) == PAGE
        file_offset = NSO_HEADER + i * PAGE
        memory_location = i * PAGE
        final_field = PAGE if i < 2 else PAGE  # alignment or BSS size
        struct.pack_into("<IIII", header, 0x10 + i * 0x10,
                         file_offset, memory_location, PAGE, final_field)
        struct.pack_into("<I", header, 0x60 + i * 4, len(segment))
        header[0xA0 + i * 0x20:0xC0 + i * 0x20] = hashlib.sha256(segment).digest()
    header[0x40:0x60] = hashlib.sha256(text + rodata + data).digest()
    return bytes(header) + b"".join(segments)


def build_extended_npdm() -> bytes:
    """Synthetic META layout matching Eden's existing author-owned fixture.

    Extended ACID is detected at ACID-base + 0x300 instead of the legacy
    0x200 placement. The bytes are original test input, NOT a real title NPDM.
    """
    out = bytearray(NPDM_SIZE)
    out[0:4] = b"META"
    out[0xC] = 7  # 64-bit ISA, 39-bit address space
    struct.pack_into("<I", out, 0x1C, 0x100000)  # main stack
    struct.pack_into("<IIII", out, 0x70, 0x500, 0x100, 0x80, 0x380)
    out[0x380:0x384] = b"ACID"
    struct.pack_into("<II", out, 0x3A0, 0x340, 0x2C)  # relative FAC
    struct.pack_into("<Q", out, 0x3C4, 0x1234)
    out[0x500:0x504] = b"ACI0"
    struct.pack_into("<Q", out, 0x510, TITLE_ID)
    struct.pack_into("<II", out, 0x520, 0x40, 0x1C)
    struct.pack_into("<II", out, 0x530, 0x80, 4)
    struct.pack_into("<Q", out, 0x544, 0x5678)
    struct.pack_into("<I", out, 0x580, 0x030043F7)
    return bytes(out)


def verify_self_authored_fixture(nso: bytes, npdm: bytes) -> None:
    """Independent structural check before allowing the two blobs into CI."""
    if len(nso) != NSO_HEADER + PAGE * 3 or nso[:4] != NSO_MAGIC:
        raise ValueError("unexpected NSO magic or length")
    if struct.unpack_from("<I", nso, 0x0C)[0] != 0:
        raise ValueError("source-owned NSO must not use compression")
    for i in range(3):
        offset, location, size, extra = struct.unpack_from("<IIII", nso, 0x10 + i * 16)
        if (offset, location, size) != (NSO_HEADER + i * PAGE, i * PAGE, PAGE):
            raise ValueError("unexpected NSO segment mapping")
        if extra != PAGE:
            raise ValueError("unexpected page alignment or BSS")
        raw = nso[offset:offset + size]
        if len(raw) != size:
            raise ValueError("segment extends past file")
        if hashlib.sha256(raw).digest() != nso[0xA0 + i * 32:0xC0 + i * 32]:
            raise ValueError("NSO segment hash mismatch")
    if not nso[NSO_HEADER + PAGE:NSO_HEADER + PAGE + len(MESSAGE)] == MESSAGE:
        raise ValueError("guest-owned message missing from rodata")
    if len(npdm) != NPDM_SIZE or npdm[:4] != b"META":
        raise ValueError("unexpected NPDM")
    if npdm[0x380:0x384] != b"ACID" or npdm[0x280:0x284] == b"ACID":
        raise ValueError("not extended-only ACID")
    if npdm[0x500:0x504] != b"ACI0":
        raise ValueError("missing ACI0")
    if struct.unpack_from("<Q", npdm, 0x510)[0] != TITLE_ID:
        raise ValueError("wrong synthetic title ID")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="Destination directory; creates main and main.npdm")
    args = parser.parse_args()
    nso = build_nso()
    npdm = build_extended_npdm()
    verify_self_authored_fixture(nso, npdm)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "main").write_bytes(nso)
    (args.output / "main.npdm").write_bytes(npdm)
    print("NX2_ORIGINAL_EXTENDED_EXEFS_FIXTURE_PASS")
    for name, data in (("main", nso), ("main.npdm", npdm)):
        print(f"NX2_ORIGINAL_FIXTURE name={name} bytes={len(data)} "
              f"sha256={hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
