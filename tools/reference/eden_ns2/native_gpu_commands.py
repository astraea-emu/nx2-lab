#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Original, bounded C797 clear/triangle inputs for frozen Eden e2f285ab.

These are inputs to that source model, not a physical GPU ABI claim. Its
maxwell_3d.h supplies graphics registers, dma_pusher.h supplies packet fields,
and Ampere lower_to_maxwell.h/program_capture.h consume the native instructions.
The shaders contain no SDK, compiler output, textures, or vendor implementation.
Actual shader execution and presentation require the separate runtime trial.
"""
from __future__ import annotations

import struct

EDEN_COMMIT = "e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c"
IMAGE_GPU_ADDRESS = 0x100000000
IMAGE_SIZE = 0x2000
GPU_BUFFER_ADDRESS = 0x100010000
GPU_BUFFER_SIZE = 0x4000
VS_OFFSET = 0x1000
FS_OFFSET = 0x2000
VERTEX_OFFSET = 0x3000
VS_GPU_ADDRESS = GPU_BUFFER_ADDRESS + VS_OFFSET
FS_GPU_ADDRESS = GPU_BUFFER_ADDRESS + FS_OFFSET
VERTEX_GPU_ADDRESS = GPU_BUFFER_ADDRESS + VERTEX_OFFSET
WIDTH, HEIGHT = 16, 9
BACKGROUND_RGBA = (16, 32, 48, 255)
SENTINEL_RGBA = (255, 255, 0, 255)
FRAGMENT_RGBA = ((255, 0, 255, 255), (0, 255, 0, 255))
NATIVE_HEADER_SIZE = 128
VERTEX_COUNT = 3
VERTEX_SIZE = VERTEX_COUNT * 16


def _float(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def _words(values: tuple[int, ...] | list[int]) -> bytes:
    return struct.pack("<" + "I" * len(values), *values)


def _address(value: int) -> tuple[int, int]:
    return value >> 32, value & 0xFFFFFFFF


# PT (predicate 7), scalar registers R0..R3, no indexed attributes or patches.
# ALD loads Generic0 at byte 0x80; AST writes Position at byte 0x70. Their vector
# width is four, the index/vertex operands use RZ, and EXIT is unconditional.
VERTEX_INSTRUCTIONS = (
    (0xFF007321, 0x000080FF, 0x00000C00, 0),
    (0xFF007322, 0x00007000, 0x00000CFF, 0),
    (0x0000794D, 0, 0x03800000, 0),
)


def _vertex_shader() -> bytes:
    header = bytearray(NATIVE_HEADER_SIZE)
    # Only fields consumed by this source path are set. Stage comes from the
    # pipeline slot, not from unverified hardware-header version/type bits.
    header[0x18] = 0x0F  # ProgramHeader.vtg.imap_generic_vector[0]: xyzw.
    header[0x35] = 0xF0  # ProgramHeader.vtg.omap_systemb: position xyzw.
    return bytes(header) + b"".join(_words(row) for row in VERTEX_INSTRUCTIONS)


def _fragment_shader(variant: int) -> bytes:
    header = bytearray(NATIVE_HEADER_SIZE)
    struct.pack_into("<I", header, 0x48, 0xF)  # RT0 RGBA, no depth/sample mask.
    result = bytearray(header)
    for register, byte in enumerate(FRAGMENT_RGBA[variant]):
        # Native MOV32I to R0..R3, all lanes, only exactly representable 0/1.
        result += _words((0x7802 | (register << 16),
                          _float(byte / 255), 0xF00, 0))
    result += _words((0x794D, 0, 0x03800000, 0))
    return bytes(result)


def _commands(clear_only: bool) -> tuple[int, ...]:
    words: list[int] = []

    def emit(byte_method: int, *arguments: int) -> None:
        if byte_method % 4 or not 0 <= byte_method < 0x3800:
            raise ValueError("graphics method is outside the frozen register file")
        if not 1 <= len(arguments) <= 0x1FFF:
            raise ValueError("invalid increasing packet length")
        # Increasing method packet, subchannel 0. Methods are word indices.
        words.append(0x20000000 | (len(arguments) << 16) | (byte_method // 4))
        words.extend(arguments)

    emit(0x0000, 0xC797)  # BindObject: native graphics class on this channel.
    emit(0x0124, 2)  # Shadow RAM passthrough.
    emit(0x037C, 1)  # Rasterization enabled.
    emit(0x0744, 0)  # Transform feedback disabled.
    # Native 16-GOB block height, array of one image, layer stride 8192 bytes.
    # ImageInfo interprets array_pitch in words (multiplied by four).
    # Android Rgba8888 is little-endian RGBA: RenderTargetFormat 0xD5.
    emit(0x0800, *_address(IMAGE_GPU_ADDRESS), WIDTH, HEIGHT,
         0xD5, 0x40, 1, IMAGE_SIZE // 4, 0, 0)
    emit(0x0A00, *(_float(x) for x in (8, 4.5, 1, 8, 4.5, 0)), 0x6420, 0)
    emit(0x0C00, WIDTH << 16, HEIGHT << 16, _float(0), _float(1))
    emit(0x0D7C, 1)  # Depth NDC 0..1; no depth target/test below.
    emit(0x0D80, *(_float(x / 255) for x in BACKGROUND_RGBA))
    emit(0x0E00, 1, WIDTH << 16, HEIGHT << 16)  # Bounded scissor 0.
    emit(0x0F90, 0)  # Per-target color masks.
    emit(0x0FAC, 1)  # MRT control used, with only target 0 below.
    emit(0x0FF4, WIDTH << 16, HEIGHT << 16)  # Surface clip.
    emit(0x10F8, 0)  # Clear full target, no inherited stencil/scissor mask.
    emit(0x1160, 0x38200000)  # Attribute 0: buffer 0, offset 0, float32x4.
    emit(0x121C, 1)  # One render target, identity target 0 mapping.
    emit(0x12CC, 0)  # Depth test disabled.
    emit(0x12E4, 0, 0, 0)  # Per-target blend, depth write, alpha test disabled.
    emit(0x1360, *(0 for _ in range(8)))  # Blend disabled for every target.
    emit(0x1380, 0)  # Stencil disabled.
    emit(0x13AC, 0)  # Upper-left origin; no flip.
    emit(0x1538, 0, 0)  # No depth target or alpha-to-coverage/one.
    emit(0x1558, 1)  # RenderEnable::Mode::True.
    emit(0x15B8, 0)  # Linear UNORM, no framebuffer sRGB conversion.
    emit(0x15D0, 0)  # One sample.
    emit(0x1644, 0)  # Primitive restart disabled.
    emit(0x1918, 0)  # Culling disabled.
    emit(0x1924, 0)  # Pixel centres at half integers.
    emit(0x192C, 1)  # Use the explicit viewport scale/translation.
    emit(0x1948, 0)  # Primitive topology comes from DrawBegin.
    emit(0x19BC, 0)  # No depth-bounds test.
    emit(0x19C4, 0)  # Logic operation disabled.
    emit(0x1A00, 0x1111)  # Write all RGBA channels.
    emit(0x1C00, 0x1010, *_address(VERTEX_GPU_ADDRESS), 0)  # Enabled, stride 16.
    # C797 uses a 40-bit byte COUNT at 0x600, not Maxwell's end address.
    emit(0x0600, 0, VERTEX_SIZE)
    emit(0x2000, 0)  # VertexA disabled; VertexB is the actual vertex program.
    emit(0x2040, 0x11, 0, 0, 4, 0, *_address(VS_GPU_ADDRESS), 0, 0)
    emit(0x2080, 0)  # No tessellation control.
    emit(0x20C0, 0)  # No tessellation evaluation.
    emit(0x2100, 0)  # No geometry stage.
    emit(0x2140, 0x51, 0, 0, 4, 0, *_address(FS_GPU_ADDRESS), 0, 0)
    emit(0x19D0, 0x3C)  # GPU clear all four channels of target 0/layer 0.
    # Equal packet length in all modes. Clear-only never executes DrawBegin or
    # DrawEnd; these four otherwise-executable writes become engine NOPs.
    emit(0x0100 if clear_only else 0x1618, 4)  # Triangles, first instance.
    emit(0x0100 if clear_only else 0x0D74, 0)  # First vertex.
    emit(0x0100 if clear_only else 0x0D78, VERTEX_COUNT)
    emit(0x0100 if clear_only else 0x1614, 0)  # DrawEnd submits one instance.
    emit(0x0110, 0)  # WFI ordering; actual capture still proves readback.
    if len(words) * 4 > VS_OFFSET:
        raise ValueError("commands overlap the vertex shader")
    return tuple(words)


GPFIFO_WORD_COUNT = len(_commands(False))


def build_gpu_buffer(variant: int = 0, clear_only: bool = False) -> bytes:
    """Return one zero-padded GPU allocation; no host draw or rasterization runs."""
    if type(variant) is not int or variant not in (0, 1):
        raise ValueError("variant must be 0 or 1")
    if type(clear_only) is not bool:
        raise ValueError("clear_only must be boolean")
    command_words = _commands(clear_only)
    if len(command_words) != GPFIFO_WORD_COUNT:
        raise ValueError("control changed the declared GPFIFO word count")
    # The explicit upper-left viewport maps these to (2, 2), (14, 2), (2, 7).
    vertices = struct.pack("<12f", -0.75, -5 / 9, 0.5, 1,
                           0.75, -5 / 9, 0.5, 1,
                           -0.75, 5 / 9, 0.5, 1)
    sections = ((0, _words(list(command_words))), (VS_OFFSET, _vertex_shader()),
                (FS_OFFSET, _fragment_shader(variant)), (VERTEX_OFFSET, vertices))
    result = bytearray(GPU_BUFFER_SIZE)
    for index, (offset, data) in enumerate(sections):
        end = sections[index + 1][0] if index + 1 < len(sections) else GPU_BUFFER_SIZE
        if offset + len(data) > end:
            raise ValueError("GPU inputs overlap or exceed their allocation")
        result[offset:offset + len(data)] = data
    return bytes(result)
