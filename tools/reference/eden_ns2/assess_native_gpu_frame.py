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
    FIELDS as FRAME_FIELDS, HANDLE_FIELDS, assess_lifecycle, _tipc as _frame_tipc,
    CAPTURED, SUBMITTED, FRONTEND, RENDERER, CAPABILITY_FAILURE, FIELD_RECORD,
)
from assess_native_ipc import CLASSIFIED, GUEST_EXIT, GUEST_OUTPUT, LOG_PREFIX, MAX_LOG_SIZE
from assess_native_vi2 import (
    BOUNDARY, CONTROL, ERROR, FAILURE, MANAGER_DIAGNOSTIC, STARTUP_ERRORS, STUB,
)
from build_native_engine import BASELINE_SHA, CANDIDATE_SHA, EDEN_REVISIONS, EDEN_SHA

BACKGROUND = (16, 32, 48, 255)
FRAGMENT_COLOURS = ((255, 0, 255, 255), (0, 255, 0, 255))
VERTICES = ((2, 2), (14, 2), (2, 7))
# Independent FNV-1a32 of 8192 bytes containing little-endian 0xff00ffff.
# This is the CPU's uniform yellow sentinel, before GPU clear and draw.
SENTINEL_CHECKSUM = 0x402B5DC5
# FNV-1a32 of the reviewed 16-KiB original inputs, keyed by (variant, clear-only).
INPUT_CHECKSUMS = {(0, False): 0x9FD0D419, (1, False): 0x37270BE4,
                   (0, True): 0x4DBA94DD, (1, True): 0xA8667CF0}

# Animation variants keep the magenta shader and change only the vertex path.
# These logical positions are independent of the guest's upload representation.
ANIMATION_OFFSETS = (((0, 0), (1, 0), (0, 1), (-1, 0)),
                     ((0, 0), (-1, 0), (0, 1), (1, 0)))
ANIMATION_INPUT_CHECKSUMS = ((0x9FD0D419, 0xA47DD7D9, 0xD29CD296, 0x555B0019),
                             (0x9FD0D419, 0x555B0019, 0xD29CD296, 0xA47DD7D9))


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


@lru_cache(maxsize=8)
def _animation_pixels(variant: int, frame: int) -> bytes:
    dx, dy = ANIMATION_OFFSETS[variant][frame]
    vertices = tuple((x + dx, y + dy) for x, y in VERTICES)
    rows = []
    for y in range(HEIGHT):
        row = bytearray()
        for x in range(WIDTH):
            px, py = 2 * x + 1, 2 * y + 1
            inside = all((bx - ax) * (py - 2 * ay) - (by - ay) * (px - 2 * ax) > 0
                         for (ax, ay), (bx, by) in zip(vertices, vertices[1:] + vertices[:1]))
            red, green, blue, alpha = FRAGMENT_COLOURS[0] if inside else BACKGROUND
            row.extend(bytes((blue, green, red, alpha)) * SCALE)
        rows.append(bytes(row) * SCALE)
    return b"".join(rows)


def verify_animation_pixels(capture: bytes, variant: int, frame: int) -> bool:
    """Check one declared position; stale frames and reordered captures differ."""
    valid = (type(variant) is int and variant in (0, 1) and
             type(frame) is int and 0 <= frame < 4)
    envelope = len(capture) == CAPTURE_SIZE and capture[:18] == TGA_HEADER
    matches = valid and envelope and capture[18:] == _animation_pixels(variant, frame)
    print(f"NX2_NATIVE_GPU_ANIMATION_FRAME={frame}")
    print(f"NX2_NATIVE_GPU_ANIMATION_CAPTURE_SHA256={hashlib.sha256(capture).hexdigest()}")
    print(f"NX2_NATIVE_GPU_ANIMATION_CAPTURE_ENVELOPE_MATCH={int(envelope)}")
    print(f"NX2_NATIVE_GPU_ANIMATION_ALL_PIXELS_MATCH={int(matches)}")
    return bool(matches)


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

ANIMATION_FRAME_FIELDS = tuple(
    (name, 20 if name == "poll_count" else value) for name, value in FRAME_FIELDS
) + (
    ("animation_frame", None), ("animation_slot", None),
    ("second_memory_id", None), ("second_image_id", None),
    *_frame_tipc("second_memory_create", 111, 2),
    *_frame_tipc("second_memory_bind", 114), *_frame_tipc("second_image_create", 429, 2),
    *_frame_tipc("second_pool_create", 315), *_frame_tipc("second_pool_destroy", 314),
    *_frame_tipc("second_image_destroy", 430), *_frame_tipc("second_memory_destroy", 112),
    ("animation_target_address_lo", None), ("animation_target_address_hi", None),
)
ANIMATION_GPU_FIELDS = tuple(
    (name, 4 if name == "gpu_reserve_image_word00" else value) for name, value in GPU_FIELDS
) + _ioctl("map_second_image", (1, 0, None, 0x1000, 0, 0, 8192, 0, 0x2000, 1))
ANIMATION_FIELDS = ANIMATION_FRAME_FIELDS + ANIMATION_GPU_FIELDS
ANIMATION_CLEANUP_FIELDS = frozenset(
    name for name, _ in ANIMATION_FIELDS if name.startswith((
        "unbind_display_", "unregister_", "close_display_", "pool_destroy_",
        "image_destroy_", "memory_destroy_", "display_finalize_", "close_",
        "second_pool_destroy_", "second_image_destroy_", "second_memory_destroy_",
        "gpu_free_", "gpu_tsg_unbind_", "gpu_close_", "gpu_memory_destroy_")))


@lru_cache(maxsize=2)
def native_patterns(eden_revision: str) -> tuple:
    # Reviewed source sites: Clang attributes a multiline LOG call to its end.
    # The candidate changes the lowering diagnostic from Info to Debug.
    submit, pushbuffer, stage, draw, lowered, level = {
        BASELINE_SHA: (370, 386, 312, 320, 642, "Info"),
        CANDIDATE_SHA: (379, 395, 339, 347, 697, "Debug"),
    }[eden_revision]
    records = (
        ("submit", r"Service\.NVDRV <Debug> "
         rf"core/hle/service/nvdrv/devices/nvhost_gpu\.cpp:{submit}:SubmitGPFIFOImpl: "
         r"native submit channel=(\d+), initialized=true, entries=1, flags=0x2, fence=0:0",
         "native submit channel="),
        ("pushbuffer", r"Service\.NVDRV <Debug> "
         rf"core/hle/service/nvdrv/devices/nvhost_gpu\.cpp:{pushbuffer}:SubmitGPFIFOImpl: "
         r"native pushbuffer entry=0 raw=(0x[0-9a-f]+), address=(0x[0-9a-f]+), "
         r"words=149, mapped=true, data=([0-9a-f]{8}(?:,[0-9a-f]{8}){15})",
         "native pushbuffer entry="),
        ("tsg", r"Service\.NVDRV <Debug> "
         r"core/hle/service/nvdrv/devices/nvhost_tsg_gpu\.cpp:47:Ioctl1: "
         r"native TSG ioctl=0xc004540([12]), input=4, output=4, "
         r"words=(0x[0-9a-f]+),0x0,0x0,0x0,0x0,0x0,0x0,0x0", "native TSG ioctl="),
        ("stage", r"HW\.GPU <Info> "
         rf"video_core/engines/draw_manager\.cpp:{stage}:ProcessDraw: "
         r"Native graphics shader stage=(\d+), address=(0x[0-9a-f]+)",
         "Native graphics shader stage="),
        ("draw", r"HW\.GPU <Debug> "
         rf"video_core/engines/draw_manager\.cpp:{draw}:ProcessDraw: "
         r"Translating native graphics draw: indexed=false, vertices=3, instances=1",
         "Translating native graphics draw:"),
        ("lowered", rf"Shader <{level}> "
         rf"video_core/shader_environment\.cpp:{lowered}:InitializeNativeCode: "
         r"Lowered native shader at (0x[0-9a-f]+): (\d+) source bytes, (\d+) instructions",
         "Lowered native shader at "),
    )
    return tuple((name, re.compile(LOG_PREFIX + pattern), term) for name, pattern, term in records)


FIRST_COMMAND_WORDS = (
    0x20010000, 0xC797, 0x20010049, 2, 0x200100DF, 1, 0x200101D1, 0,
    0x200A0200, 1, 0, 16, 9, 0xD5, 0x40, 1,
)
GPU_FAILURE = re.compile(
    r"\b(?:skipp(?:ed|ing)?|unsupported|rejected|substitut\w*|placeholder\w*|override\w*)\b|"
    r"falls back|Native shader (?:paused|resumed|dumped)", re.IGNORECASE)


def assess(raw: bytes, process_rc: int, capture: bytes, variant: int, *, clear_only=False,
           eden_revision: str | None = None) -> bool:
    eden_revision = EDEN_SHA if eden_revision is None else eden_revision
    if type(clear_only) is not bool or eden_revision not in EDEN_REVISIONS:
        print("NX2_NATIVE_GPU_FRAME_INPUT_NOT_VALID")
        return False
    print(f"NX2_NATIVE_GPU_FRAME_EDEN_REVISION={eden_revision}")
    patterns = native_patterns(eden_revision)
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
        for name, pattern, term in patterns:
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


@lru_cache(maxsize=2)
def animation_patterns(eden_revision: str) -> tuple:
    """The reviewed presentation/retirement sites are identical on both revisions."""
    records = (
        ("queued", r"Service\.AM <Info> "
         r"core/hle/service/am/service/graphics_supervisor\.cpp:948:QueueNativeImage: "
         r"Native image queued for display: image=(\d+), slot=(\d+), fence=(\d+)/(\d+), dimensions=16x9",
         "Native image queued for display:"),
        ("retired", r"Service\.AM <Debug> "
         r"core/hle/service/am/service/graphics_supervisor\.cpp:858:RefreshReleasedBuffers: "
         r"Native display buffer retired: slot=(\d+), mask=(0x[0-9a-f]+)",
         "Native display buffer retired:"),
        ("availability", r"Service\.AM <Debug> "
         r"core/hle/service/am/service/graphics_supervisor\.cpp:808:GetClientAvailability: "
         r"VI2 client availability token=(0x[0-9a-f]+), layer=(\d+), mask=(0x[0-9a-f]+), result=(0x[0-9a-f]+)",
         "VI2 client availability token="),
        ("present", r"Service\.AM <Debug> "
         r"core/hle/service/am/service/graphics_supervisor\.cpp:965:PresentClientBuffer: "
         r"VI2 present token=(0x[0-9a-f]+), image=(\d+), slot=(\d+), mask=(0x[0-9a-f]+), result=(0x[0-9a-f]+)",
         "VI2 present token="),
        ("composite_fence", r"Service\.NVDRV <Info> "
         r"core/hle/service/nvdrv/devices/nvdisp_disp0\.cpp:112:Composite: "
         r"Native composite waits for syncpoint=(\d+)/(\d+), current=(\d+)",
         "Native composite waits for syncpoint="),
    )
    return (native_patterns(eden_revision) +
            tuple((name, re.compile(LOG_PREFIX + pattern), term) for name, pattern, term in records) +
            (("composite", SUBMITTED, "Native composite submitted:"),
             ("captured", CAPTURED, "Captured composited frame:")))


def assess_animation(raw: bytes, process_rc: int, captures: tuple[bytes, ...], variant: int, *,
                     eden_revision: str | None = None) -> bool:
    """Verify four real submissions/readbacks and two safely reused display buffers.

    VI2 retirement proves ownership only: this engine releases with NoFence.
    Each saved Vulkan capture must also precede the next guest frame's writes.
    The runner separately archives each callback's file before arming another.
    """
    eden_revision = EDEN_SHA if eden_revision is None else eden_revision
    errors = []

    def finish(passed: bool) -> bool:
        for error in errors[:10]:
            print(f"NX2_NATIVE_GPU_ANIMATION_PROTOCOL_ERROR={error}")
        print("NX2_NATIVE_GPU_ANIMATION_PASS" if passed else
              "NX2_NATIVE_GPU_ANIMATION_NOT_VERIFIED")
        return passed

    print(f"NX2_NATIVE_GPU_ANIMATION_EDEN_REVISION={eden_revision}")
    print(f"NX2_NATIVE_GPU_ANIMATION_PROCESS_RC={process_rc}")
    if (not isinstance(raw, bytes) or len(raw) > MAX_LOG_SIZE or type(process_rc) is not int or
            type(variant) is not int or variant not in (0, 1) or eden_revision not in EDEN_REVISIONS or
            not isinstance(captures, (tuple, list)) or len(captures) != 4 or
            any(not isinstance(capture, bytes) for capture in captures)):
        errors.append("invalid bounded animation input")
        return finish(False)
    lines = [BOUNDARY.sub("", line.removesuffix("\r"))
             for line in raw.decode("utf-8", "replace").split("\n")]
    event_counts = {"NX2_FRAME_BEGIN": 1, "NX2_FRAME_PRESENT_BEGIN": 4,
                    "NX2_FRAME_PRESENTED": 4, "NX2_FRAME_CLEANUP_BEGIN": 1,
                    "NX2_FRAME_COMPLETE": 1, "NX2_GPU_BEGIN": 1,
                    "NX2_GPU_SUBMITTED": 4, "NX2_GPU_FENCE_OBSERVED": 4,
                    "NX2_GPU_CLEANUP": 1, "NX2_ANIMATION_FRAME_BEGIN": 4,
                    "NX2_ANIMATION_FRAME_END": 4}
    events = {name: [] for name in event_counts}
    patterns = animation_patterns(eden_revision)
    proof = {name: [] for name, _, _ in patterns}
    records, classifications, exits, managers, frontends = [], [], [], [], []
    renderer = {name: [] for name in ("Driver", "Device", "Vulkan")}
    for index, line in enumerate(lines):
        if CONTROL.search(line) or FAILURE.search(line) or CAPABILITY_FAILURE.search(line) or GPU_FAILURE.search(line):
            errors.append(f"corruption, failure or substituted execution at line {index}")
        if CLASSIFIED.fullmatch(line):
            classifications.append(index)
        elif "Switch 2 program: using the 12 GiB memory layout" in line:
            errors.append(f"unattributed classification at line {index}")
        if GUEST_EXIT.fullmatch(line):
            exits.append((index, int(line.rsplit(" ", 2)[1])))
        elif "ExitProcess:" in line:
            errors.append(f"unattributed exit at line {index}")
        if MANAGER_DIAGNOSTIC.fullmatch(line):
            managers.append(index)
        if FRONTEND.fullmatch(line):
            frontends.append(index)
        report = RENDERER.fullmatch(line)
        if report:
            if report[1] != {"Driver": "278", "Device": "279", "Vulkan": "280"}[report[2]] or not report[3].strip():
                errors.append(f"invalid renderer report at line {index}")
            renderer[report[2]].append((index, report[3]))
        for name, pattern, term in patterns:
            match = pattern.fullmatch(line)
            if match:
                proof[name].append((index, match.groups()))
            elif term in line:
                errors.append(f"malformed or unattributed {name} at line {index}")
        if not any(term in line for term in ("NX2_FRAME", "NX2_GPU", "NX2_ANIMATION")):
            continue
        output = GUEST_OUTPUT.fullmatch(line)
        if output is None or "svc_debug_string.cpp:25:OutputDebugString: " not in line:
            errors.append(f"unattributed guest record at line {index}")
        elif output[1] in events:
            events[output[1]].append(index)
        else:
            record = FIELD_RECORD.fullmatch(output[1])
            if record:
                records.append((index, record[1], int(record[2], 16)))
            else:
                errors.append(f"unknown or failed guest record at line {index}")
    counts_ok = (all(len(events[name]) == count for name, count in event_counts.items()) and
                 len(classifications) == len(exits) == len(managers) == len(frontends) == 1 and
                 all(len(renderer[name]) == 1 for name in renderer))
    source_counts = {"submit": 4, "pushbuffer": 4, "tsg": 2, "stage": 2, "draw": 1,
                     "lowered": 4, "queued": 4, "retired": 4, "availability": 84,
                     "present": 4, "composite_fence": 4, "composite": 4, "captured": 4}
    counts_ok = counts_ok and all(len(proof[name]) == count for name, count in source_counts.items())
    field_names = [name for name, _ in ANIMATION_FIELDS]
    fields_ok = [name for _, name, _ in records] == field_names * 5
    print(f"NX2_NATIVE_GPU_ANIMATION_FIELD_COUNT={len(records)}")
    print(f"NX2_NATIVE_GPU_ANIMATION_FIELDS_IN_ORDER={int(fields_ok)}")
    print(f"NX2_NATIVE_GPU_ANIMATION_EVENT_COUNTS_MATCH={int(counts_ok)}")
    if not counts_ok or not fields_ok:
        errors.append("incomplete, duplicated or reordered animation evidence")
        return finish(False)
    blocks = [records[offset:offset + len(field_names)]
              for offset in range(0, len(records), len(field_names))]
    values = [{name: value for _, name, value in block} for block in blocks]
    begins, ends = events["NX2_ANIMATION_FRAME_BEGIN"], events["NX2_ANIMATION_FRAME_END"]
    begin, cleanup, complete = (events[name][0] for name in
        ("NX2_FRAME_BEGIN", "NX2_FRAME_CLEANUP_BEGIN", "NX2_FRAME_COMPLETE"))
    startup_counts = {name: 0 for name, _, _ in STARTUP_ERRORS}
    for index, line in enumerate(lines):
        if ERROR.search(line):
            allowed = next((name for name, _, pattern in STARTUP_ERRORS
                            if index < begin and pattern.fullmatch(line)), None)
            if allowed is None:
                errors.append(f"unexpected error at line {index}")
            else:
                startup_counts[allowed] += 1
        if STUB.search(line) and index not in managers:
            errors.append(f"unexpected stub at line {index}")
    startup_ok = all(startup_counts[name] <= limit for name, limit, _ in STARTUP_ERRORS)
    version = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", renderer["Vulkan"][0][1])
    renderer_ok = (version is not None and tuple(map(int, version.groups())) >= (1, 1, 0) and
                   frontends[0] < begin and
                   renderer["Driver"][0][0] < renderer["Device"][0][0] <
                   renderer["Vulkan"][0][0] < begin)
    handles = [values[0][name] for name in (*HANDLE_FIELDS, "gpu_sync_handle")]
    handles_ok = len(set(handles)) == 9 and all(
        handle >> 30 == 0 and (handle & 0x7FFF) < 1024 and ((handle >> 15) & 0x7FFF) != 0
        for handle in handles)
    initial = values[0]
    aruid = initial["aruid_lo"] | (initial["aruid_hi"] << 32)
    image_address = initial["image_address_lo"] | (initial["image_address_hi"] << 32)
    gpu_address = initial["gpu_buffer_address_lo"] | (initial["gpu_buffer_address_hi"] << 32)
    ids = [initial[name] for name in ("memory_id", "second_memory_id", "gpu_memory_id")]
    images = (initial["image_id"], initial["second_image_id"])
    fds = [initial[f"gpu_open_{name}_fd"] for name in ("as", "channel", "tsg")]
    objects_ok = (len(set(ids)) == 3 and all(0 < value < 0xFFFFFFFF for value in ids) and
                  len(set(images)) == 2 and all(0 < value < 0xFFFFFFFF for value in images) and
                  len(set(fds)) == 3 and all(0 <= fd < 1 << 31 for fd in fds) and
                  initial["gpu_map_image_word02"] == ids[0] and
                  initial["gpu_map_second_image_word02"] == ids[1] and
                  initial["gpu_map_buffer_word02"] == ids[2] and
                  initial["gpu_tsg_bind_word00"] == values[-1]["gpu_tsg_unbind_word00"] == fds[1] and
                  proof["tsg"][0][1] == ("1", hex(fds[1])) and
                  proof["tsg"][1][1] == ("2", hex(fds[1])))
    addresses_ok = (image_address > 0 and image_address % 4096 == 0 and
                    image_address + 16384 <= 1 << 39 and gpu_address > 0 and
                    gpu_address % 4096 == 0 and gpu_address + 16384 <= 1 << 39 and
                    (gpu_address + 16384 <= image_address or image_address + 16384 <= gpu_address))
    overall_order = (classifications[0] < begin < managers[0] < begins[0] <
                     events["NX2_GPU_BEGIN"][0] < proof["tsg"][0][0] and
                     ends[3] < cleanup < events["NX2_GPU_CLEANUP"][0] < proof["tsg"][1][0] <
                     blocks[4][0][0] <= blocks[4][-1][0] < complete < exits[0][0] and
                     aruid != 0 and aruid == exits[0][1])
    # Unchanged shader pages are first translated once, then reused for all draws.
    shaders_ok = ([groups for _, groups in proof["stage"]] ==
                   [("1", "0x100011000"), ("5", "0x100012000")] and
                   [groups for _, groups in proof["lowered"]] ==
                   [("0x100011000", "176", "3"), ("0x100012000", "208", "5")] * 2 and
                   proof["pushbuffer"][0][0] < proof["stage"][0][0] < proof["stage"][1][0] <
                   proof["draw"][0][0] < proof["lowered"][0][0] < proof["lowered"][1][0] <
                   proof["lowered"][2][0] < proof["lowered"][3][0] < events["NX2_GPU_FENCE_OBSERVED"][0])
    changing = {"animation_frame", "animation_slot", "animation_target_address_lo",
                "animation_target_address_hi", "present_lo", "poll_queued_count",
                "poll_released_count", "gpu_buffer_checksum", "gpu_counter_before_lo",
                "gpu_submit_word05", "gpu_counter_after_lo", "gpu_counter_poll_count"}
    stable = set(field_names) - changing - ANIMATION_CLEANUP_FIELDS
    stable_ok = all(all(value[name] == initial[name] for name in stable) for value in values[1:])
    final_ok = all(values[4][name] == values[3][name]
                   for name in field_names if name not in ANIMATION_CLEANUP_FIELDS)
    layers = {groups[1] for _, groups in proof["availability"]}
    availability_ok = len(layers) == 1 and int(next(iter(layers))) > 0
    composite_addresses = [int(groups[0], 16) for _, groups in proof["composite"]]
    buffers_ok = (0 < composite_addresses[0] < 1 << 64 and
                  0 < composite_addresses[1] < 1 << 64 and
                  composite_addresses[0] != composite_addresses[1] and
                  composite_addresses[:2] == composite_addresses[2:])
    frame_results = []
    for index, value in enumerate(values):
        frame = min(index, 3)
        slot, target = frame % 2, 2 * (frame + 1)
        overrides = {"variant": variant, "image_checksum": SENTINEL_CHECKSUM,
                     "animation_frame": frame, "animation_slot": slot,
                     "animation_target_address_lo": (image_address + slot * 8192) & 0xFFFFFFFF,
                     "animation_target_address_hi": (image_address + slot * 8192) >> 32,
                     "present_lo": 0x7FFF ^ (1 << slot), "gpu_clear_only": 0,
                     "gpu_buffer_checksum": ANIMATION_INPUT_CHECKSUMS[variant][frame],
                     "gpu_counter_before_lo": target - 2, "gpu_counter_after_lo": target,
                     "gpu_submit_word05": target}
        expected = {name: overrides.get(name, wanted) for name, wanted in ANIMATION_FIELDS}
        if index < 4:
            expected.update((name, 0xFFFFFFFF) for name in ANIMATION_CLEANUP_FIELDS)
        fields_match = all(wanted is None or value[name] == wanted for name, wanted in expected.items())
        observed = all(number != 0xFFFFFFFF or (index < 4 and name in ANIMATION_CLEANUP_FIELDS)
                       for name, number in value.items())
        fence = value["gpu_fifo_word03"]
        poll_counts = (0 <= value["poll_queued_count"] < 20 and
                       1 <= value["poll_released_count"] <= 20 and
                       value["poll_queued_count"] + value["poll_released_count"] == 20)
        fence_ok = (0 < fence < 192 and value["gpu_submit_word04"] == fence and
                    1 <= value["gpu_counter_poll_count"] <= 1000)
        if index == 4:
            final_ok = final_ok and fields_match and observed and poll_counts and fence_ok
            continue
        queued_mask = 0x7FFF ^ (1 << slot)
        first, last = begins[frame], ends[frame]
        ordered = (first < proof["submit"][frame][0] < proof["pushbuffer"][frame][0] <
                    events["NX2_GPU_SUBMITTED"][frame] < events["NX2_GPU_FENCE_OBSERVED"][frame] <
                    events["NX2_FRAME_PRESENT_BEGIN"][frame] < proof["queued"][frame][0] <
                    proof["present"][frame][0] < events["NX2_FRAME_PRESENTED"][frame] <
                    blocks[frame][0][0] <= blocks[frame][-1][0] < last and
                    events["NX2_FRAME_PRESENT_BEGIN"][frame] < proof["composite_fence"][frame][0] <
                    proof["composite"][frame][0] < proof["captured"][frame][0] < last and
                    proof["queued"][frame][0] < proof["retired"][frame][0] < blocks[frame][0][0] and
                    (frame == 3 or last < begins[frame + 1]))
        if frame == 0:
            ordered = ordered and first < proof["tsg"][0][0] < proof["submit"][0][0]
        entry, address, words = proof["pushbuffer"][frame][1]
        first_words = list(FIRST_COMMAND_WORDS)
        first_words[10] = slot * 8192
        stream_ok = (int(entry, 16) == 0x2540100010000 and int(address, 16) == 0x100010000 and
                     tuple(int(word, 16) for word in words.split(",")) == tuple(first_words) and
                     proof["submit"][frame][1] == proof["submit"][0][1] and
                     0 <= int(proof["submit"][frame][1][0]) < 1 << 32)
        presentation_ok = (tuple(map(int, proof["queued"][frame][1])) == (images[slot], slot, fence, target) and
                           proof["retired"][frame][1] == (str(slot), "0x7fff") and
                           proof["present"][frame][1] ==
                           ("0x32495632584e0001", str(images[slot]), str(slot), hex(queued_mask), "0x0") and
                           tuple(map(int, proof["composite_fence"][frame][1])) == (fence, target, target))
        available = [item for item in proof["availability"] if first < item[0] < last]
        ownership_ok = len(available) == 21 and poll_counts
        if ownership_ok:
            masks = [int(groups[2], 16) for _, groups in available]
            ownership_ok = (all(groups[0] == "0x32495632584e0001" and groups[3] == "0x0"
                                for _, groups in available) and
                            available[0][0] < proof["submit"][frame][0] and masks[0] == 0x7FFF and
                            events["NX2_FRAME_PRESENTED"][frame] < available[1][0] and
                            masks[1:] == [queued_mask] * value["poll_queued_count"] +
                            [0x7FFF] * value["poll_released_count"] and
                            proof["retired"][frame][0] < available[1 + value["poll_queued_count"]][0])
        passed = (fields_match and observed and poll_counts and fence_ok and ordered and
                  stream_ok and presentation_ok and ownership_ok)
        frame_results.append(passed)
        print(f"NX2_NATIVE_GPU_ANIMATION_FRAME_{frame}_FIELDS_MATCH={int(fields_match and observed)}")
        print(f"NX2_NATIVE_GPU_ANIMATION_FRAME_{frame}_ORDER_MATCH={int(ordered)}")
        print(f"NX2_NATIVE_GPU_ANIMATION_FRAME_{frame}_SUBMISSION_MATCH={int(stream_ok and fence_ok)}")
        print(f"NX2_NATIVE_GPU_ANIMATION_FRAME_{frame}_OWNERSHIP_MATCH={int(presentation_ok and ownership_ok and poll_counts)}")
    checks = (("RENDERER_VALID", renderer_ok), ("STARTUP_ERRORS_BOUNDED", startup_ok),
              ("DISTINCT_HANDLES", handles_ok), ("OBJECTS_BOUND", objects_ok),
              ("ADDRESSES_VALID", addresses_ok), ("LIFETIME_ORDER", overall_order),
              ("ORIGINAL_SHADERS", shaders_ok), ("STABLE_OBJECTS", stable_ok),
              ("TWO_BUFFERS_REUSED", buffers_ok), ("AVAILABILITY_LAYER", availability_ok),
              ("CLEANUP_OBSERVED", final_ok))
    for name, passed in checks:
        print(f"NX2_NATIVE_GPU_ANIMATION_{name}={int(passed)}")
    passed = (process_rc == 0 and all(value for _, value in checks) and all(frame_results) and not errors)
    if passed:
        passed = all(verify_animation_pixels(capture, variant, frame)
                     for frame, capture in enumerate(captures))
    return finish(bool(passed))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--exit", required=True, type=int, dest="process_rc")
    parser.add_argument("--variant", required=True, type=int, choices=(0, 1))
    parser.add_argument("--clear-only", action="store_true")
    parser.add_argument("--eden-revision", choices=EDEN_REVISIONS, default=EDEN_SHA)
    args = parser.parse_args()
    try:
        with args.log.open("rb") as stream:
            raw = stream.read(MAX_LOG_SIZE + 1)
        with args.capture.open("rb") as stream:
            capture = stream.read(CAPTURE_SIZE + 1)
    except OSError as error:
        parser.exit(1, f"NX2_NATIVE_GPU_FRAME_INPUT_UNAVAILABLE: {error}\n")
    return 0 if assess(raw, args.process_rc, capture, args.variant, clear_only=args.clear_only,
                       eden_revision=args.eden_revision) else 1


if __name__ == "__main__":
    raise SystemExit(main())
