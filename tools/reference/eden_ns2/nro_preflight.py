#!/usr/bin/env python3
"""Fail-closed NX2 test-fixture preflight for the frozen Eden-NS2 NRO loader.

This does not replace the emulator's own parser and is not a proof of
runtime/guest execution. It rejects untrusted lengths before handing an NRO
fixture to third-party emulation code in controlled CI.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import struct

PAGE = 0x1000
HEADER_SIZE = 0x80
MOD_HEADER_SIZE = 0x1C
ASSET_HEADER_SIZE = 0x38
MAX_IMAGE_SIZE = 128 * 1024 * 1024
MAX_PROGRAM_ALLOCATION = 256 * 1024 * 1024


class NroPreflightError(ValueError):
    """Input is unsafe or inconsistent with the bounded NRO fixture contract."""


@dataclass(frozen=True)
class NroLayout:
    image_bytes: int
    copied_bytes: int
    bss_bytes: int
    module_header_offset: int
    segments: tuple[tuple[str, int, int], ...]


def preflight_nro(image: bytes) -> NroLayout:
    """Validate byte ranges Eden's NRO loader reads before execution.

    Conservative scope: syntactically valid NRO0 files with page-bounded text,
    rodata, and data segments. Never use this as a Nintendo compatibility oracle.
    """
    if not isinstance(image, bytes):
        raise TypeError("preflight expects immutable bytes")
    if len(image) < HEADER_SIZE:
        raise NroPreflightError("truncated NRO header")
    if len(image) > MAX_IMAGE_SIZE:
        raise NroPreflightError("NRO fixture file exceeds the input limit")
    if image[0x10:0x14] != b"NRO0":
        raise NroPreflightError("invalid NRO0 magic")

    module_offset, = struct.unpack_from("<I", image, 0x04)
    image_bytes, = struct.unpack_from("<I", image, 0x18)
    bss_bytes, = struct.unpack_from("<I", image, 0x38)
    if image_bytes < HEADER_SIZE or image_bytes > MAX_IMAGE_SIZE:
        raise NroPreflightError("implausible declared NRO image length")
    copied_bytes = (image_bytes + PAGE - 1) & ~(PAGE - 1)
    if copied_bytes > len(image):
        raise NroPreflightError("Eden's page-aligned memcpy would read past file")
    if module_offset > copied_bytes - MOD_HEADER_SIZE:
        raise NroPreflightError("MOD0 metadata would read beyond allocated image")
    if module_offset % 4:
        raise NroPreflightError("unaligned MOD0 metadata offset")

    # Frozen Eden nro.cpp LoadNroImpl replaces the header BSS with the MOD0
    # end-start span when that magic is present, then page-aligns it. Bound the
    # allocation it actually performs, not only the ignored header value.
    if image[module_offset:module_offset + 4] == b"MOD0":
        bss_start, bss_end = struct.unpack_from("<II", image, module_offset + 8)
        if bss_end < bss_start:
            raise NroPreflightError("MOD0 BSS range would underflow")
        bss_bytes = bss_end - bss_start
    bss_bytes = (bss_bytes + PAGE - 1) & ~(PAGE - 1)
    if copied_bytes + bss_bytes > MAX_PROGRAM_ALLOCATION:
        raise NroPreflightError("unbounded guest image plus effective BSS allocation")

    segments = []
    for name, pos in (("text", 0x20), ("rodata", 0x28), ("data", 0x30)):
        offset, length = struct.unpack_from("<II", image, pos)
        if offset > image_bytes or length > image_bytes - offset:
            raise NroPreflightError(f"{name} exceeds declared NRO image")
        if offset % PAGE:
            raise NroPreflightError(f"{name} offset is not page-aligned")
        segments.append((name, offset, length))
    if segments[0][1] != 0:
        raise NroPreflightError("text must begin at offset zero")
    for left, right in zip(segments, segments[1:]):
        if left[1] + left[2] > right[1]:
            raise NroPreflightError("overlapping NRO load segments")

    # AppLoader_NRO also consumes an optional ASET trailer before execution.
    # Its icon path allocates the declared ReadBytes size before checking how
    # many bytes the file supplies; bound every nonempty trailer extent first.
    asset_bytes = len(image) - image_bytes
    if (asset_bytes >= ASSET_HEADER_SIZE and
            image[image_bytes:image_bytes + 4] == b"ASET"):
        for name, position in (("icon", 8), ("NACP", 24), ("RomFS", 40)):
            offset, size = struct.unpack_from("<QQ", image, image_bytes + position)
            if size and (offset > asset_bytes or size > asset_bytes - offset):
                raise NroPreflightError(f"ASET {name} exceeds the supplied file")
    return NroLayout(image_bytes, copied_bytes, bss_bytes, module_offset, tuple(segments))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nro", type=Path, help="NRO guest fixture to validate")
    args = parser.parse_args()
    try:
        if args.nro.stat().st_size > MAX_IMAGE_SIZE:
            raise NroPreflightError("NRO fixture file exceeds the input limit")
        with args.nro.open("rb") as source:
            image = source.read(MAX_IMAGE_SIZE + 1)
        layout = preflight_nro(image)
    except (NroPreflightError, OSError) as exc:
        parser.exit(1, f"NX2_NRO_PREFLIGHT_REFUSED: {exc}\n")
    print(f"NX2_NRO_PREFLIGHT_PASS image={layout.image_bytes} "
          f"rounded_copy={layout.copied_bytes} bss={layout.bss_bytes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
