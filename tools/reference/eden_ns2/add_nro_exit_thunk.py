#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Create a clearly labeled, four-byte original-homebrew return-thunk variant.

This does not modify or replace the exact-hash original NeXo NRO used as the
positive CPU/HLE control. Eden's NRO loader explicitly searches page-rounded
text for AArch64 SVC #7 to construct its optional Homebrew return address.
The unchanged original guest has no such instruction and returns to null.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct

from nro_preflight import MAX_IMAGE_SIZE

NRO_HEADER_SIZE = 0x80
SVC_EXIT = 0xD40000E1
PAGE = 0x1000


def add_exit_thunk(original: bytes) -> tuple[bytes, int]:
    if len(original) > MAX_IMAGE_SIZE:
        raise ValueError("NRO fixture file exceeds the input limit")
    if len(original) < NRO_HEADER_SIZE or original[0x10:0x14] != b"NRO0":
        raise ValueError("missing NRO header/magic")
    text_offset, text_size = struct.unpack_from("<II", original, 0x20)
    rodata_offset, _ = struct.unpack_from("<II", original, 0x28)
    if text_offset != 0 or text_size == 0:
        raise ValueError("unexpected guest text segment")
    insertion = text_offset + text_size
    if insertion % 4 or insertion < NRO_HEADER_SIZE:
        raise ValueError("cannot place an aligned SVC thunk")
    if insertion + 4 > rodata_offset or rodata_offset > len(original):
        raise ValueError("no free text padding before rodata")
    if original[insertion:insertion + 4] != b"\0\0\0\0":
        raise ValueError("text padding is not empty")
    if struct.pack("<I", SVC_EXIT) in original[text_offset:insertion]:
        raise ValueError("guest already contains an exit-service instruction")
    out = bytearray(original)
    struct.pack_into("<I", out, insertion, SVC_EXIT)
    assert len(out) == len(original)
    return bytes(out), insertion


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.output.exists() and args.output.samefile(args.original):
            raise ValueError("output must not alias the original NRO")
        if args.original.stat().st_size > MAX_IMAGE_SIZE:
            raise ValueError("NRO fixture file exceeds the input limit")
        with args.original.open("rb") as source:
            original = source.read(MAX_IMAGE_SIZE + 1)
        adapted, offset = add_exit_thunk(original)
    except (OSError, ValueError) as error:
        parser.exit(1, f"NX2_NRO_RETURN_THUNK_REFUSED: {error}\n")
    args.output.write_bytes(adapted)
    print(f"NX2_EDEN_OWNED_RETURN_THUNK_BUILT offset={offset} bytes_modified=4")
    print("NX2_EDEN_ORIGINAL_NRO_UNMODIFIED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
