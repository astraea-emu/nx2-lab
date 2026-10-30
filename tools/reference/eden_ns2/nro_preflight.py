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
    if copied_bytes + bss_bytes > MAX_PROGRAM_ALLOCATION:
        raise NroPreflightError("unbounded guest image plus BSS allocation")
    if module_offset > copied_bytes - MOD_HEADER_SIZE:
        raise NroPreflightError("MOD0 metadata would read beyond allocated image")
    if module_offset % 4:
        raise NroPreflightError("unaligned MOD0 metadata offset")

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
    return NroLayout(image_bytes, copied_bytes, bss_bytes, module_offset, tuple(segments))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nro", type=Path, help="NRO guest fixture to validate")
    args = parser.parse_args()
    try:
        layout = preflight_nro(args.nro.read_bytes())
    except (NroPreflightError, OSError) as exc:
        parser.exit(1, f"NX2_NRO_PREFLIGHT_REFUSED: {exc}\n")
    print(f"NX2_NRO_PREFLIGHT_PASS image={layout.image_bytes} "
          f"rounded_copy={layout.copied_bytes} bss={layout.bss_bytes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
