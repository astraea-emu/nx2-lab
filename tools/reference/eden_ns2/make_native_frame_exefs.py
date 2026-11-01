#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Assemble an original CPU-image or GPU-triangle guest into a bounded ExeFS.

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
GPU_SEGMENT_ADDRESSES = (0, 0x4000, 0x10000)
GPU_SEGMENT_SIZES = (0x4000, 0xC000, 0x8000)
ANIMATION_SEGMENT_SIZES = (0x4000, 0xC000, 0xA000)
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
ANIMATION_MARKERS = (b"NX2_ANIMATION_FRAME_BEGIN\n", b"NX2_ANIMATION_FRAME_END\n")


def _segment_layout(gpu: bool, animation: bool):
    if type(gpu) is not bool or type(animation) is not bool or (animation and not gpu):
        raise ValueError("animation requires the GPU workload")
    return ((GPU_SEGMENT_ADDRESSES, ANIMATION_SEGMENT_SIZES if animation else GPU_SEGMENT_SIZES)
            if gpu else (SEGMENT_ADDRESSES, SEGMENT_SIZES))


def compile_frame_segments(
    tool_prefix: str = "aarch64-linux-gnu-", *, variant: int = 0,
    gpu: bool = False, clear_only: bool = False, animation: bool = False,
) -> tuple[bytes, bytes, bytes]:
    """Link original ARM64 code and validate its three bounded PT_LOAD segments."""
    if variant not in (0, 1):
        raise ValueError("frame variant must be 0 or 1")
    if type(gpu) is not bool or type(clear_only) is not bool or (clear_only and not gpu):
        raise ValueError("clear-only requires the GPU workload")
    addresses, sizes = _segment_layout(gpu, animation)
    if animation and clear_only:
        raise ValueError("animation does not accept clear-only")
    with tempfile.TemporaryDirectory(prefix="nx2-frame-guest-") as temporary:
        directory = Path(temporary)
        obj, elf = directory / "guest.o", directory / "guest.elf"
        source = "native_gpu_probe" if gpu else "native_frame_probe"
        arguments = []
        if gpu:
            from native_gpu_commands import GPFIFO_WORD_COUNT, build_animation_inputs, build_gpu_buffer
            (directory / "gpu-buffer.bin").write_bytes(build_gpu_buffer(
                variant, clear_only, animation_frame=0 if animation else None))
            if animation:
                (directory / "gpu-animation-inputs.bin").write_bytes(build_animation_inputs(variant))
            arguments = ["-I", str(ROOT), "-I", str(directory), "--defsym",
                         f"NX2_GPU_WORD_COUNT={GPFIFO_WORD_COUNT}", "--defsym",
                         f"NX2_GPU_CLEAR_ONLY={int(clear_only)}", "--defsym",
                         f"NX2_GPU_ANIMATION={int(animation)}"]
        subprocess.run([tool_prefix + "as", "--defsym", f"NX2_FRAME_VARIANT={variant}",
                        *arguments, "-o", str(obj), str(ROOT / (source + ".S"))], check=True)
        subprocess.run([tool_prefix + "ld", "--build-id=none", "--defsym",
                        f"NX2_GPU_ANIMATION={int(animation)}", "-T",
                        str(ROOT / (source + ".ld")), "-o", str(elf), str(obj)],
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
                addresses, sizes, (5, 4, 6))):
            kind, actual_flags, start, virtual, physical, size, memory_size, _ = (
                struct.unpack_from("<IIQQQQQQ", raw, offset + index * entry_size))
            if (kind != 1 or actual_flags != flags or virtual != address or
                    physical != address or not 0 < size <= limit or
                    memory_size != size or start + size > len(raw)):
                raise ValueError("unexpected frame ELF segment mapping or permissions")
            sections.append(raw[start:start + size])
        return tuple(sections)


def build_frame_nso(sections: tuple[bytes, bytes, bytes], *, gpu: bool = False,
                    animation: bool = False) -> bytes:
    """Frame-specific fixed bounds; earlier three-page NSO builders stay intact."""
    addresses, sizes = _segment_layout(gpu, animation)
    if len(sections) != 3 or any(not section or len(section) > limit
                                 for section, limit in zip(sections, sizes)):
        raise ValueError("expected three nonempty bounded frame segments")
    segments = tuple(section.ljust(limit, b"\0")
                     for section, limit in zip(sections, sizes))
    header = bytearray(NSO_HEADER)
    header[:4] = b"NSO0"
    start = NSO_HEADER
    for index, (segment, address) in enumerate(zip(segments, addresses)):
        struct.pack_into("<IIII", header, 0x10 + index * 16,
                         start, address, len(segment), PAGE if index < 2 else 0)
        struct.pack_into("<I", header, 0x60 + index * 4, len(segment))
        header[0xA0 + index * 32:0xC0 + index * 32] = hashlib.sha256(segment).digest()
        start += len(segment)
    header[0x40:0x60] = hashlib.sha256(b"".join(segments)).digest()
    return bytes(header) + b"".join(segments)


def read_frame_segments(nso: bytes, *, gpu: bool = False,
                        animation: bool = False) -> tuple[bytes, bytes, bytes]:
    """Check every fixed mapping, stored size, digest and reserved header byte."""
    addresses, sizes = _segment_layout(gpu, animation)
    if len(nso) != NSO_HEADER + sum(sizes):
        raise ValueError("unexpected frame NSO length")
    if nso[:16] != b"NSO0" + bytes(12):
        raise ValueError("unexpected uncompressed frame NSO header")
    if nso[0x6C:0xA0] != bytes(0x34):
        raise ValueError("unexpected frame NSO reserved metadata")
    sections = []
    start = NSO_HEADER
    for index, (address, size) in enumerate(zip(addresses, sizes)):
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


def read_field_names(rodata: bytes, *, animation: bool = False) -> tuple[tuple[str, ...], int]:
    """Expand the two bounded 32-word snapshots and locate aligned templates."""
    names = []
    offset = 0
    limit = FIELD_COUNT + (34 if animation else 0)
    while offset < len(rodata) and len(names) <= limit:
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


def verify_frame_fixture(nso: bytes, npdm: bytes, variant: int, *,
                         gpu: bool = False, clear_only: bool = False,
                         animation: bool = False) -> None:
    """Structural evidence only; no image is supplied or executed by this tool."""
    if variant not in (0, 1):
        raise ValueError("frame variant must be 0 or 1")
    if clear_only and not gpu:
        raise ValueError("clear-only requires the GPU workload")
    if animation and clear_only:
        raise ValueError("animation does not accept clear-only")
    _, rodata, data = read_frame_segments(nso, gpu=gpu, animation=animation)
    names, request_offset = read_field_names(rodata, animation=animation)
    name_bytes = ("\0".join(names[:FIELD_COUNT]) + "\0").encode()
    field_count = FIELD_COUNT + (34 if animation else 0)
    if (len(names) != field_count or len(set(names)) != field_count or
            hashlib.sha256(name_bytes).hexdigest() != FIELD_SHA256):
        raise ValueError("frame observed-field order differs from wire contract")
    if animation:
        from assess_native_gpu_frame import ANIMATION_FRAME_FIELDS
        if names != tuple(name for name, _ in ANIMATION_FRAME_FIELDS):
            raise ValueError("animation fields differ from the wire contract")
    requests = rodata[request_offset:request_offset + REQUEST_BYTES]
    if hashlib.sha256(requests).hexdigest() != REQUEST_SHA256:
        raise ValueError("frame requests differ from independent libnx vectors")
    config = struct.unpack_from("<9I", rodata, request_offset + REQUEST_BYTES)
    light = 0xFFE0D0C0 if gpu or variant == 0 else 0xFFA050E0
    if config != (variant, 16, 9, 0xFF302010, light,
                  0xFF0000FF, 0xFF00FF00, 0xFFFF0000, 0xFF00FFFF):
        raise ValueError("frame drawing configuration differs from selected variant")
    expected_data = bytearray(_segment_layout(gpu, animation)[1][2])
    record_bytes = field_count * 4
    expected_data[:record_bytes] = b"\xff" * record_bytes
    notification_offset = ((record_bytes + 8 * 4 + 15) & ~15) + 12
    expected_data[notification_offset:notification_offset + 136] = b"\xa5" * 136
    if gpu:
        _verify_gpu_inputs(rodata, expected_data, variant, clear_only, animation=animation)
    if data != bytes(expected_data):
        raise ValueError("frame data must contain unobserved records and zero image backing")
    for marker in MARKERS + (ANIMATION_MARKERS if animation else ()):
        if rodata.count(marker) != 1:
            raise ValueError("frame lifecycle marker missing or duplicated")
    if npdm != build_extended_npdm():
        raise ValueError("frame probe must retain the corrected synthetic baseline NPDM")


def _verify_gpu_inputs(rodata: bytes, expected_data: bytearray,
                       variant: int, clear_only: bool, *, animation: bool = False) -> None:
    """Check GPU storage bounds, unobserved records and original input bytes."""
    from assess_native_gpu_frame import GPU_FIELDS
    from native_gpu_commands import GPU_BUFFER_SIZE, build_animation_inputs, build_gpu_buffer
    fields = GPU_FIELDS
    if animation:
        from assess_native_gpu_frame import ANIMATION_GPU_FIELDS
        fields = ANIMATION_GPU_FIELDS
    magic = b"NX2GPUv1"
    if rodata.count(magic) != 1:
        raise ValueError("missing or duplicated GPU fixture layout")
    offset = rodata.index(magic) + len(magic)
    if offset + 28 > len(rodata):
        raise ValueError("truncated GPU fixture layout")
    names_offset, count, record, state, state_size, buffer, inputs = struct.unpack_from(
        "<7I", rodata, offset)
    if (count != len(fields) or not 0 < count <= 512 or
            record < (0x5000 if animation else SEGMENT_SIZES[2]) or record + 4 * count > state or
            state_size < 12 or state + state_size > buffer or buffer % PAGE or
            buffer + GPU_BUFFER_SIZE > len(expected_data) or inputs % 16 or
            inputs + GPU_BUFFER_SIZE > len(rodata)):
        raise ValueError("GPU records, state and command storage overlap or exceed bounds")
    names = ("\0".join(name for name, _ in fields) + "\0\0").encode()
    if rodata[names_offset:names_offset + len(names)] != names:
        raise ValueError("GPU observed-field order differs from its wire contract")
    if rodata[inputs:inputs + GPU_BUFFER_SIZE] != build_gpu_buffer(
            variant, clear_only, animation_frame=0 if animation else None):
        raise ValueError("GPU commands, shaders or vertices differ from original inputs")
    expected_data[record:record + 4 * count] = b"\xff" * (4 * count)
    expected_data[state:state + 12] = b"\xff" * 12  # Three unopened device FDs.
    if animation:
        magic = b"NX2ANIM1"
        if rodata.count(magic) != 1:
            raise ValueError("missing or duplicated animation fixture layout")
        offset = rodata.index(magic) + len(magic)
        if offset + 16 > len(rodata):
            raise ValueError("truncated animation fixture layout")
        uploads, frames, stride, target = struct.unpack_from("<4I", rodata, offset)
        if ((frames, stride, target) != (4, 64, 36) or uploads % 16 or
                uploads != inputs + GPU_BUFFER_SIZE or uploads + frames * stride != offset - 8):
            raise ValueError("animation uploads overlap or differ from the bounded layout")
        if rodata[uploads:uploads + frames * stride] != build_animation_inputs(variant):
            raise ValueError("animation target or vertex uploads differ from original inputs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tool-prefix", default="aarch64-linux-gnu-")
    parser.add_argument("--variant", type=int, choices=(0, 1), default=0)
    parser.add_argument("--gpu-triangle", action="store_true")
    parser.add_argument("--gpu-animation", action="store_true")
    parser.add_argument("--clear-only", action="store_true",
                        help="GPU clear control; requires --gpu-triangle")
    args = parser.parse_args()
    if args.gpu_triangle and args.gpu_animation:
        parser.error("select one GPU workload")
    gpu = args.gpu_triangle or args.gpu_animation
    sections = compile_frame_segments(args.tool_prefix, variant=args.variant,
                                      gpu=gpu, clear_only=args.clear_only, animation=args.gpu_animation)
    nso = build_frame_nso(sections, gpu=gpu, animation=args.gpu_animation)
    npdm = build_extended_npdm()
    verify_frame_fixture(nso, npdm, args.variant, gpu=gpu,
                         clear_only=args.clear_only, animation=args.gpu_animation)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in (("main", nso), ("main.npdm", npdm)):
        (args.output / name).write_bytes(content)
        print(f"NX2_FRAME_FIXTURE variant={args.variant} name={name} bytes={len(content)} "
              f"sha256={hashlib.sha256(content).hexdigest()}")
    names = ("native_frame_probe.S", "native_frame_probe.ld")
    if gpu:
        names += ("native_gpu_probe.S", "native_gpu_probe.ld", "native_gpu_commands.py")
        from native_gpu_commands import (
            FS_OFFSET, GPFIFO_WORD_COUNT, VERTEX_OFFSET, VERTEX_SIZE, VS_OFFSET, build_gpu_buffer,
        )
        inputs = build_gpu_buffer(args.variant, args.clear_only,
                                  animation_frame=0 if args.gpu_animation else None)
        regions = (("allocation", 0, len(inputs)), ("commands", 0, GPFIFO_WORD_COUNT * 4),
                   ("vertex-shader-page", VS_OFFSET, FS_OFFSET),
                   ("fragment-shader-page", FS_OFFSET, VERTEX_OFFSET),
                   ("vertices", VERTEX_OFFSET, VERTEX_OFFSET + VERTEX_SIZE))
        for name, start, end in regions:
            content = inputs[start:end]
            print(f"NX2_GPU_INPUT name={name} bytes={len(content)} "
                  f"sha256={hashlib.sha256(content).hexdigest()}")
        if args.gpu_animation:
            for frame in range(4):
                content = build_gpu_buffer(args.variant, animation_frame=frame)
                print(f"NX2_GPU_ANIMATION_INPUT frame={frame} slot={frame % 2} "
                      f"sha256={hashlib.sha256(content).hexdigest()}")
    for name in names:
        print(f"NX2_FRAME_SOURCE name={name} sha256={hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}")
    print("NX2_FRAME_FIXTURE_GENERATED; guest execution not attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
