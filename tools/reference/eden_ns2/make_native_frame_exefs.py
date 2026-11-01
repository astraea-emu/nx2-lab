#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Assemble the original CPU-image frame guest into a bounded synthetic ExeFS.

Only host GNU AArch64 binutils run here. Real presentation, capture, pixel
comparison and cleanup require the separate frozen-Eden trial. This retains
the baseline synthetic NPDM, including its source-model SVC limitations.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from make_native_exefs import NSO_HEADER, PAGE, build_extended_npdm

ROOT = Path(__file__).resolve().parent
SEGMENT_ADDRESSES = (0, 0x2000, 0x5000)
SEGMENT_SIZES = (0x2000, 0x3000, 0x3000)
IMAGE_ADDRESS = 0x6000
IMAGE_SIZE = 8192
FIELD_COUNT = 281
FIELD_SHA256 = "664380076d93df38c5755000981d65e448ce1e974fc8edf134d264f3455ae469"
REQUEST_COUNT = 35
REQUEST_BYTES = REQUEST_COUNT * 128
# Independently emitted by unchanged cmifMakeRequest/hipcMakeRequest/
# hipcMakeBuffer from libnx b156b4774fb2df7b93402169509266da7547fc4c.
# Dynamic IDs, addresses and ARUID are zero in these original input templates.
# The external headers/helper are temporary evidence, not repository contents.
REQUEST_SHA256 = "31462255f8996dc6af18b6574af2520bc4a4cbc16946251a5cc319f9eca15398"
MARKERS = tuple(f"NX2_FRAME_{name}\n".encode() for name in (
    "BEGIN", "PRESENT_BEGIN", "PRESENTED", "CLEANUP_BEGIN", "COMPLETE", "FAILURE"))


def compile_frame_segments(
    tool_prefix: str = "aarch64-linux-gnu-", *, variant: int = 0,
) -> tuple[bytes, bytes, bytes]:
    """Link original ARM64 code and validate its three bounded PT_LOAD segments."""
    if variant not in (0, 1):
        raise ValueError("frame variant must be 0 or 1")
    with tempfile.TemporaryDirectory(prefix="nx2-frame-guest-") as temporary:
        directory = Path(temporary)
        obj, elf = directory / "guest.o", directory / "guest.elf"
        subprocess.run([tool_prefix + "as", "--defsym", f"NX2_FRAME_VARIANT={variant}",
                        "-o", str(obj), str(ROOT / "native_frame_probe.S")], check=True)
        subprocess.run([tool_prefix + "ld", "--build-id=none", "-T",
                        str(ROOT / "native_frame_probe.ld"), "-o", str(elf), str(obj)],
                       check=True)
        raw = elf.read_bytes()
        if (len(raw) < 64 or raw[:7] != b"\x7fELF\x02\x01\x01" or
                struct.unpack_from("<HH", raw, 16) != (2, 183) or
                struct.unpack_from("<Q", raw, 24)[0] != 0):
            raise ValueError("expected a resolved AArch64 executable with entry zero")
        offset = struct.unpack_from("<Q", raw, 32)[0]
        entry_size, count = struct.unpack_from("<HH", raw, 54)
        if entry_size != 56 or count != 3 or offset + entry_size * count > len(raw):
            raise ValueError("expected exactly three ELF program headers")
        sections = []
        for index, (address, limit, flags) in enumerate(zip(
                SEGMENT_ADDRESSES, SEGMENT_SIZES, (5, 4, 6))):
            kind, actual_flags, start, virtual, physical, size, memory_size, _ = (
                struct.unpack_from("<IIQQQQQQ", raw, offset + index * entry_size))
            if (kind != 1 or actual_flags != flags or virtual != address or
                    physical != address or not 0 < size <= limit or
                    memory_size != size or start + size > len(raw)):
                raise ValueError("unexpected frame ELF segment mapping or permissions")
            sections.append(raw[start:start + size])
        return tuple(sections)


def build_frame_nso(sections: tuple[bytes, bytes, bytes]) -> bytes:
    """Frame-specific fixed bounds; earlier three-page NSO builders stay intact."""
    if len(sections) != 3 or any(not section or len(section) > limit
                                 for section, limit in zip(sections, SEGMENT_SIZES)):
        raise ValueError("expected three nonempty bounded frame segments")
    segments = tuple(section.ljust(limit, b"\0")
                     for section, limit in zip(sections, SEGMENT_SIZES))
    header = bytearray(NSO_HEADER)
    header[:4] = b"NSO0"
    start = NSO_HEADER
    for index, (segment, address) in enumerate(zip(segments, SEGMENT_ADDRESSES)):
        struct.pack_into("<IIII", header, 0x10 + index * 16,
                         start, address, len(segment), PAGE if index < 2 else 0)
        struct.pack_into("<I", header, 0x60 + index * 4, len(segment))
        header[0xA0 + index * 32:0xC0 + index * 32] = hashlib.sha256(segment).digest()
        start += len(segment)
    header[0x40:0x60] = hashlib.sha256(b"".join(segments)).digest()
    return bytes(header) + b"".join(segments)


def read_frame_segments(nso: bytes) -> tuple[bytes, bytes, bytes]:
    """Check every fixed mapping, stored size, digest and reserved header byte."""
    if len(nso) != NSO_HEADER + sum(SEGMENT_SIZES):
        raise ValueError("unexpected frame NSO length")
    if nso[:16] != b"NSO0" + bytes(12):
        raise ValueError("unexpected uncompressed frame NSO header")
    if nso[0x6C:0xA0] != bytes(0x34):
        raise ValueError("unexpected frame NSO reserved metadata")
    sections = []
    start = NSO_HEADER
    for index, (address, size) in enumerate(zip(SEGMENT_ADDRESSES, SEGMENT_SIZES)):
        expected = (start, address, size, PAGE if index < 2 else 0)
        if struct.unpack_from("<IIII", nso, 0x10 + index * 16) != expected:
            raise ValueError("unexpected frame segment mapping or BSS")
        if struct.unpack_from("<I", nso, 0x60 + index * 4)[0] != size:
            raise ValueError("unexpected frame stored segment size")
        section = nso[start:start + size]
        if hashlib.sha256(section).digest() != nso[0xA0 + index * 32:0xC0 + index * 32]:
            raise ValueError("frame segment hash mismatch")
        sections.append(section)
        start += size
    if hashlib.sha256(nso[NSO_HEADER:]).digest() != nso[0x40:0x60]:
        raise ValueError("frame build ID mismatch")
    return tuple(sections)


def read_field_names(rodata: bytes) -> tuple[tuple[str, ...], int]:
    """Expand the two bounded 32-word snapshots and locate aligned templates."""
    names = []
    offset = 0
    while offset < len(rodata) and len(names) <= FIELD_COUNT:
        end = rodata.find(b"\0", offset)
        if end < 0:
            raise ValueError("unterminated frame field name")
        name = rodata[offset:end].decode("ascii")
        offset = end + 1
        if not name:
            aligned = (offset + 15) & ~15
            if aligned > len(rodata) or any(rodata[offset:aligned]):
                raise ValueError("nonzero frame field alignment padding")
            return tuple(names), aligned
        if name.startswith("~"):
            if name not in ("~released_word", "~clear_word"):
                raise ValueError("unknown frame field array")
            names.extend(f"{name[1:]}{index:02d}" for index in range(32))
        else:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name):
                raise ValueError("invalid frame field name")
            names.append(name)
    raise ValueError("unterminated or oversized frame field stream")


def verify_frame_fixture(nso: bytes, npdm: bytes, variant: int) -> None:
    """Structural evidence only; no image is supplied or executed by this tool."""
    if variant not in (0, 1):
        raise ValueError("frame variant must be 0 or 1")
    _, rodata, data = read_frame_segments(nso)
    names, request_offset = read_field_names(rodata)
    name_bytes = ("\0".join(names) + "\0").encode()
    if (len(names) != FIELD_COUNT or len(set(names)) != FIELD_COUNT or
            hashlib.sha256(name_bytes).hexdigest() != FIELD_SHA256):
        raise ValueError("frame observed-field order differs from wire contract")
    requests = rodata[request_offset:request_offset + REQUEST_BYTES]
    if hashlib.sha256(requests).hexdigest() != REQUEST_SHA256:
        raise ValueError("frame requests differ from independent libnx vectors")
    config = struct.unpack_from("<9I", rodata, request_offset + REQUEST_BYTES)
    light = 0xFFE0D0C0 if variant == 0 else 0xFFA050E0
    if config != (variant, 16, 9, 0xFF302010, light,
                  0xFF0000FF, 0xFF00FF00, 0xFFFF0000, 0xFF00FFFF):
        raise ValueError("frame drawing configuration differs from selected variant")
    expected_data = bytearray(SEGMENT_SIZES[2])
    record_bytes = FIELD_COUNT * 4
    expected_data[:record_bytes] = b"\xff" * record_bytes
    notification_offset = ((record_bytes + 8 * 4 + 15) & ~15) + 12
    expected_data[notification_offset:notification_offset + 136] = b"\xa5" * 136
    if data != bytes(expected_data):
        raise ValueError("frame data must contain unobserved records and zero image backing")
    for marker in MARKERS:
        if rodata.count(marker) != 1:
            raise ValueError("frame lifecycle marker missing or duplicated")
    if npdm != build_extended_npdm():
        raise ValueError("frame probe must retain the corrected synthetic baseline NPDM")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tool-prefix", default="aarch64-linux-gnu-")
    parser.add_argument("--variant", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    sections = compile_frame_segments(args.tool_prefix, variant=args.variant)
    nso, npdm = build_frame_nso(sections), build_extended_npdm()
    verify_frame_fixture(nso, npdm, args.variant)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in (("main", nso), ("main.npdm", npdm)):
        (args.output / name).write_bytes(content)
        print(f"NX2_FRAME_FIXTURE variant={args.variant} name={name} bytes={len(content)} "
              f"sha256={hashlib.sha256(content).hexdigest()}")
    for name in ("native_frame_probe.S", "native_frame_probe.ld"):
        print(f"NX2_FRAME_SOURCE name={name} sha256={hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}")
    print("NX2_FRAME_FIXTURE_GENERATED; guest execution not attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
