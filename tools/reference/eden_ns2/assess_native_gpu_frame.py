#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify an original GPU triangle, its completion and the saved display image.

The image oracle uses logical pixel centres and integer edge equations. It does
not read the guest's tiled image, command stream or shader implementation.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
from pathlib import Path
import re

from assess_native_frame import (
    CAPTURE_HEIGHT, CAPTURE_SIZE, CAPTURE_WIDTH, HEIGHT, SCALE, TGA_HEADER, WIDTH,
    FIELDS as FRAME_FIELDS, HANDLE_FIELDS, assess_lifecycle,
)
from assess_native_ipc import GUEST_OUTPUT, LOG_PREFIX, MAX_LOG_SIZE

BACKGROUND = (16, 32, 48, 255)
FRAGMENT_COLOURS = ((255, 0, 255, 255), (0, 255, 0, 255))
VERTICES = ((2, 2), (14, 2), (2, 7))
# Independent FNV-1a32 of 8192 bytes containing little-endian 0xff00ffff.
# This is the CPU's uniform yellow sentinel, before GPU clear and draw.
SENTINEL_CHECKSUM = 0x402B5DC5
# FNV-1a32 of the reviewed 16-KiB original inputs, keyed by (variant, clear-only).
INPUT_CHECKSUMS = {(0, False): 0x9FD0D419, (1, False): 0x37270BE4,
                   (0, True): 0x4DBA94DD, (1, True): 0xA8667CF0}


def logical_pixel(x: int, y: int, variant: int) -> tuple[int, int, int, int]:
    """Evaluate the triangle at a pixel centre without floating-point rounding."""
    if (type(variant) is not int or variant not in (0, 1) or
            type(x) is not int or type(y) is not int or
            not 0 <= x < WIDTH or not 0 <= y < HEIGHT):
        raise ValueError("unsupported triangle variant or coordinate")
    point = (2 * x + 1, 2 * y + 1)
    edges = []
    for index, (ax, ay) in enumerate(VERTICES):
        bx, by = VERTICES[(index + 1) % len(VERTICES)]
        edges.append((bx - ax) * (point[1] - 2 * ay) -
                     (by - ay) * (point[0] - 2 * ax))
    # No edge of this triangle passes through a logical pixel centre.
    return FRAGMENT_COLOURS[variant] if all(edge > 0 for edge in edges) else BACKGROUND


@lru_cache(maxsize=4)
def _expected_pixels(variant: int, clear_only: bool) -> bytes:
    rows = []
    for y in range(HEIGHT):
        row = bytearray()
        for x in range(WIDTH):
            red, green, blue, alpha = BACKGROUND if clear_only else logical_pixel(x, y, variant)
            row.extend(bytes((blue, green, red, alpha)) * SCALE)
        rows.append(bytes(row) * SCALE)
    return b"".join(rows)


def verify_pixels(capture: bytes, variant: int, *, clear_only: bool = False) -> bool:
    """Require the exact TGA envelope and every displayed BGRA/alpha byte."""
    valid = type(variant) is int and variant in (0, 1) and type(clear_only) is bool
    size_ok = len(capture) == CAPTURE_SIZE
    header_ok = capture[:18] == TGA_HEADER
    print(f"NX2_NATIVE_GPU_FRAME_CAPTURE_BYTES={len(capture)}")
    print(f"NX2_NATIVE_GPU_FRAME_CAPTURE_SHA256={hashlib.sha256(capture).hexdigest()}")
    print(f"NX2_NATIVE_GPU_FRAME_TGA_SIZE_MATCH={int(size_ok)}")
    print(f"NX2_NATIVE_GPU_FRAME_TGA_HEADER_MATCH={int(header_ok)}")
    pixels_ok = (valid and size_ok and header_ok and
                 capture[18:] == _expected_pixels(variant, clear_only))
    print(f"NX2_NATIVE_GPU_FRAME_ALL_PIXELS_MATCH={int(pixels_ok)}")
    if valid and size_ok and header_ok and not pixels_ok:
        expected = _expected_pixels(variant, clear_only)
        mismatch = next(i for i, (actual, wanted) in enumerate(zip(capture[18:], expected))
                        if actual != wanted)
        pixel, channel = divmod(mismatch, 4)
        print(f"NX2_NATIVE_GPU_FRAME_FIRST_MISMATCH=x{pixel % CAPTURE_WIDTH},"
              f"y{pixel // CAPTURE_WIDTH},channel{'BGRA'[channel]}")
    return bool(pixels_ok)


def _tipc(name, command, words=1):
    return tuple(("gpu_" + name + "_" + suffix, value) for suffix, value in (
        ("transport", 0), ("header0", command + 16), ("header1", words), ("result", 0)))


def _cmif(name, opened=False):
    values = (("transport", 0), ("header0", 0), ("header1", 14 if opened else 12),
              ("pad0", 0), ("pad1", 0), ("magic", 0x4F434653), ("version", 0),
              ("result_lo", 0), ("result_hi", 0))
    if opened:
        values += (("fd", None),)
    return tuple(("gpu_" + name + "_" + suffix, value)
                 for suffix, value in values + (("nv_result", 0),))


def _ioctl(name, words):
    prefix = "gpu_" + name
    return (_cmif(name) + ((prefix + "_guard_before", 0xA5A5A5A5),) +
            tuple((f"{prefix}_word{index:02d}", value) for index, value in enumerate(words)) +
            ((prefix + "_guard_after", 0xA5A5A5A5),))


def _counter(name, value):
    return _tipc(name, 103, 4) + tuple(("gpu_" + name + "_" + suffix, expected)
                                     for suffix, expected in (("lo", value), ("hi", 0), ("width", 0)))


# Frozen NVDRV response words and graphics-supervisor TIPC replies. Input-only
# ioctls leave the guarded output descriptor untouched; IOWR returns its words.
GPU_FIELDS = (
    ("gpu_clear_only", None), ("gpu_buffer_address_lo", None), ("gpu_buffer_address_hi", None),
    ("gpu_buffer_size", 0x4000), ("gpu_buffer_checksum", None), ("gpu_command_words", 149),
    ("gpu_entry_lo", 0x10000), ("gpu_entry_hi", 0x25401),
    *_tipc("memory_create", 111, 2), ("gpu_memory_id", None),
    *_tipc("memory_bind", 114), *_tipc("sync_init", 201),
    ("gpu_sync_open_transport", 0), ("gpu_sync_open_header0", 218),
    ("gpu_sync_open_header1", 0x80000001), ("gpu_sync_open_descriptor", 0x20),
    ("gpu_sync_handle", None), ("gpu_sync_open_result", 0),
    *_cmif("open_as", True), *_cmif("open_channel", True), *_cmif("open_tsg", True),
    *_ioctl("as_init", (0xA5A5A5A5,) * 10), *_ioctl("as_bind", (0xA5A5A5A5,)),
    *_ioctl("tsg_bind", (None,)), *_ioctl("fifo", (1, 1, 0, None, 0, 0, 0, 0)),
    *_ioctl("object", (0xC797, 0, 0, 0)),
    *_ioctl("reserve_image", (2, 0x1000, 1, 0, 0, 1)),
    *_ioctl("map_image", (1, 0, None, 0x1000, 0, 0, 8192, 0, 0, 1)),
    *_ioctl("reserve_buffer", (4, 0x1000, 1, 0, 0x10000, 1)),
    *_ioctl("map_buffer", (1, 0, None, 0x1000, 0, 0, 16384, 0, 0x10000, 1)),
    *_counter("counter_before", 0), *_ioctl("submit", (0, 0, 1, 0, None, 2)),
    *_counter("counter_after", 2), ("gpu_counter_poll_count", None),
    *_ioctl("free_buffer", (0xA5A5A5A5,) * 4), *_ioctl("free_image", (0xA5A5A5A5,) * 4),
    *_ioctl("tsg_unbind", (None,)), *_cmif("close_channel"), *_cmif("close_tsg"),
    *_cmif("close_as"), *_tipc("memory_destroy", 112), ("gpu_close_sync", 0),
)
GPU_MARKERS = ("BEGIN", "SUBMITTED", "FENCE_OBSERVED", "CLEANUP")
NATIVE_SUBMIT = re.compile(LOG_PREFIX + r"Service\.NVDRV <Debug> "
    r"core/hle/service/nvdrv/devices/nvhost_gpu\.cpp:370:SubmitGPFIFOImpl: "
    r"native submit channel=(\d+), initialized=true, entries=1, flags=0x2, fence=0:0")
PUSHBUFFER = re.compile(LOG_PREFIX + r"Service\.NVDRV <Debug> "
    r"core/hle/service/nvdrv/devices/nvhost_gpu\.cpp:386:SubmitGPFIFOImpl: "
    r"native pushbuffer entry=0 raw=(0x[0-9a-f]+), address=(0x[0-9a-f]+), "
    r"words=149, mapped=true, data=([0-9a-f]{8}(?:,[0-9a-f]{8}){15})")
TSG = re.compile(LOG_PREFIX + r"Service\.NVDRV <Debug> "
    r"core/hle/service/nvdrv/devices/nvhost_tsg_gpu\.cpp:47:Ioctl1: "
    r"native TSG ioctl=0xc004540([12]), input=4, output=4, "
    r"words=(0x[0-9a-f]+),0x0,0x0,0x0,0x0,0x0,0x0,0x0")
SHADER_STAGE = re.compile(LOG_PREFIX + r"HW\.GPU <Info> "
    r"video_core/engines/draw_manager\.cpp:312:ProcessDraw: "
    r"Native graphics shader stage=(\d+), address=(0x[0-9a-f]+)")
DRAW = re.compile(LOG_PREFIX + r"HW\.GPU <Debug> "
    r"video_core/engines/draw_manager\.cpp:320:ProcessDraw: "
    r"Translating native graphics draw: indexed=false, vertices=3, instances=1")
LOWERED = re.compile(LOG_PREFIX + r"Shader <Info> "
    r"video_core/shader_environment\.cpp:642:InitializeNativeCode: "
    r"Lowered native shader at (0x[0-9a-f]+): (\d+) source bytes, (\d+) instructions")
FIRST_COMMAND_WORDS = (
    0x20010000, 0xC797, 0x20010049, 2, 0x200100DF, 1, 0x200101D1, 0,
    0x200A0200, 1, 0, 16, 9, 0xD5, 0x40, 1,
)
GPU_FAILURE = re.compile(
    r"\b(?:skipp(?:ed|ing)?|unsupported|rejected|substitut\w*|placeholder\w*|override\w*)\b|"
    r"falls back|Native shader (?:paused|resumed|dumped)", re.IGNORECASE)


def assess(raw: bytes, process_rc: int, capture: bytes, variant: int, *, clear_only=False) -> bool:
    if type(clear_only) is not bool:
        print("NX2_NATIVE_GPU_FRAME_INPUT_NOT_VALID")
        return False
    lifecycle = assess_lifecycle(raw, process_rc, variant, fields=FRAME_FIELDS + GPU_FIELDS,
        backing_checksums=(SENTINEL_CHECKSUM,) * 2,
        fence_fields=("gpu_fifo_word03", "gpu_submit_word05"))
    if lifecycle is None:
        print("NX2_NATIVE_GPU_FRAME_NOT_VERIFIED")
        return False
    values, lines, frame = lifecycle
    sync_handle = values["gpu_sync_handle"]
    handles_ok = (sync_handle not in (values[name] for name in HANDLE_FIELDS) and
                  sync_handle >> 30 == 0 and (sync_handle & 0x7FFF) < 1024 and
                  ((sync_handle >> 15) & 0x7FFF) != 0)
    fds = [values[f"gpu_open_{name}_fd"] for name in ("as", "channel", "tsg")]
    objects_ok = (len(set(fds)) == 3 and all(0 <= fd < 1 << 31 for fd in fds) and
                  0 < values["gpu_memory_id"] < 0xFFFFFFFF and
                  values["gpu_memory_id"] != values["memory_id"] and
                  values["gpu_map_image_word02"] == values["memory_id"] and
                  values["gpu_map_buffer_word02"] == values["gpu_memory_id"] and
                  values["gpu_tsg_bind_word00"] == values["gpu_tsg_unbind_word00"] == fds[1])
    address = values["gpu_buffer_address_lo"] | (values["gpu_buffer_address_hi"] << 32)
    image_address = values["image_address_lo"] | (values["image_address_hi"] << 32)
    inputs_ok = (values["gpu_clear_only"] == int(clear_only) and
                 values["gpu_buffer_checksum"] == INPUT_CHECKSUMS[variant, clear_only] and
                 address > 0 and address % 4096 == 0 and address + 16384 <= 1 << 39 and
                 (address + 16384 <= image_address or image_address + 8192 <= address))
    fence_ok = (0 < values["gpu_fifo_word03"] < 192 and
                values["gpu_submit_word04"] == values["gpu_fifo_word03"] and
                1 <= values["gpu_counter_poll_count"] <= 1000)
    markers = {name: [] for name in GPU_MARKERS}
    proof = {name: [] for name in ("submit", "pushbuffer", "tsg", "stage", "draw", "lowered")}
    errors = []
    for index, line in enumerate(lines):
        if GPU_FAILURE.search(line):
            errors.append(f"unsupported or substituted GPU work at line {index}")
        if "NX2_GPU" in line:
            record = GUEST_OUTPUT.fullmatch(line)
            name = record[1].removeprefix("NX2_GPU_") if record else ""
            if name not in markers or record[1] != "NX2_GPU_" + name:
                errors.append(f"unattributed or unknown GPU marker at line {index}")
            else:
                markers[name].append(index)
        for name, pattern, term in (
            ("submit", NATIVE_SUBMIT, "native submit channel="),
            ("pushbuffer", PUSHBUFFER, "native pushbuffer entry="),
            ("tsg", TSG, "native TSG ioctl="),
            ("stage", SHADER_STAGE, "Native graphics shader stage="),
            ("draw", DRAW, "Translating native graphics draw:"),
            ("lowered", LOWERED, "Lowered native shader at "),
        ):
            match = pattern.fullmatch(line)
            if match:
                proof[name].append((index, match.groups()))
            elif term in line:
                errors.append(f"unattributed or malformed {name} at line {index}")
    order_ok = proof_ok = False
    if (all(len(indices) == 1 for indices in markers.values()) and
            len(proof["submit"]) == len(proof["pushbuffer"]) == 1 and len(proof["tsg"]) == 2):
        begin, submitted, fence, cleanup = (markers[name][0] for name in GPU_MARKERS)
        bind, unbind = proof["tsg"]
        order_ok = (frame["BEGIN"] < begin < bind[0] < proof["submit"][0][0] <
                    proof["pushbuffer"][0][0] < submitted < fence < frame["PRESENT_BEGIN"] and
                    frame["CAPTURED"] < frame["CLEANUP_BEGIN"] < cleanup < unbind[0] < frame["COMPLETE"])
        entry, gpu_address, words = proof["pushbuffer"][0][1]
        proof_ok = (bind[1] == ("1", hex(fds[1])) and unbind[1] == ("2", hex(fds[1])) and
                    0 <= int(proof["submit"][0][1][0]) < 1 << 32 and
                    int(entry, 16) == 0x2540100010000 and int(gpu_address, 16) == 0x100010000 and
                    tuple(int(word, 16) for word in words.split(",")) == FIRST_COMMAND_WORDS)
        if clear_only:
            proof_ok = proof_ok and not any(proof[name] for name in ("stage", "draw", "lowered"))
        else:
            stages = [groups for _, groups in proof["stage"]]
            lowered = [groups for _, groups in proof["lowered"]]
            # With an empty per-trial pipeline cache, RefreshStages constructs
            # both GraphicsEnvironments, then CreateGraphicsPipeline constructs
            # both again. Each constructor lowers and reports its original code.
            proof_ok = (proof_ok and stages == [("1", "0x100011000"), ("5", "0x100012000")] and
                        lowered == [("0x100011000", "176", "3"), ("0x100012000", "208", "5")] * 2 and
                        len(proof["draw"]) == 1 and
                        proof["pushbuffer"][0][0] < proof["stage"][0][0] < proof["stage"][1][0] <
                        proof["draw"][0][0] < proof["lowered"][0][0] < proof["lowered"][1][0] <
                        proof["lowered"][2][0] < proof["lowered"][3][0] < fence)
    checks = (("SYNC_HANDLE_VALID", handles_ok), ("OBJECTS_BOUND", objects_ok),
              ("INPUTS_MATCH", inputs_ok), ("ORDERED_FENCE_OBSERVED", fence_ok),
              ("LIFETIME_ORDER", order_ok), ("NATIVE_EXECUTION_PROOF", proof_ok))
    for name, value in checks:
        print(f"NX2_NATIVE_GPU_FRAME_{name}={int(value)}")
    for error in errors[:10]:
        print(f"NX2_NATIVE_GPU_FRAME_PROTOCOL_ERROR={error}")
    passed = all(value for _, value in checks) and not errors
    if passed:
        passed = verify_pixels(capture, variant, clear_only=clear_only)
        if clear_only and passed:
            rejected = all(capture[18:] != _expected_pixels(colour, False) for colour in (0, 1))
            print(f"NX2_NATIVE_GPU_FRAME_CLEAR_REJECTS_BOTH_TRIANGLES={int(rejected)}")
            passed = passed and rejected
    print("NX2_NATIVE_GPU_FRAME_PASS" if passed else "NX2_NATIVE_GPU_FRAME_NOT_VERIFIED")
    return bool(passed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--exit", required=True, type=int, dest="process_rc")
    parser.add_argument("--variant", required=True, type=int, choices=(0, 1))
    parser.add_argument("--clear-only", action="store_true")
    args = parser.parse_args()
    try:
        with args.log.open("rb") as stream:
            raw = stream.read(MAX_LOG_SIZE + 1)
        with args.capture.open("rb") as stream:
            capture = stream.read(CAPTURE_SIZE + 1)
    except OSError as error:
        parser.exit(1, f"NX2_NATIVE_GPU_FRAME_INPUT_UNAVAILABLE: {error}\n")
    return 0 if assess(raw, args.process_rc, capture, args.variant, clear_only=args.clear_only) else 1


if __name__ == "__main__":
    raise SystemExit(main())
