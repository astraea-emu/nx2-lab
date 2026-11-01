#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check one original guest image, real Vulkan readback and complete teardown.

The pixel oracle uses logical row-major colours, never the guest's tiled backing.
The runner owns freshness: a new working directory, no prior capture, and one
on-demand request. This checker binds that capture to source-attributed execution
and requires the completed file callback before guest teardown. A complete old
log and its old matching file cannot establish freshness by themselves.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
from pathlib import Path
import re
import struct

from assess_native_ipc import CLASSIFIED, GUEST_EXIT, GUEST_OUTPUT, LOG_PREFIX, MAX_LOG_SIZE
from assess_native_vi2 import (
    BOUNDARY, CONTROL, ERROR, FAILURE, MANAGER_DIAGNOSTIC, STARTUP_ERRORS, STUB,
)

WIDTH, HEIGHT, SCALE = 16, 9, 120
CAPTURE_WIDTH, CAPTURE_HEIGHT = WIDTH * SCALE, HEIGHT * SCALE
CAPTURE_SIZE = 18 + CAPTURE_WIDTH * CAPTURE_HEIGHT * 4
TGA_HEADER = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0,
                         CAPTURE_WIDTH, CAPTURE_HEIGHT, 32, 0x28)
# Independently checked FNV-1a32 of 8192 zero-initialized backing bytes with
# 144 RGBA pixels in the frozen native block layout. These are guest observation
# checks only; the displayed-pixel oracle below contains no tiling operations.
BACKING_CHECKSUMS = (0xB78A03D5, 0x0A9DFBD5)


def logical_pixel(x: int, y: int, variant: int) -> tuple[int, int, int, int]:
    """The original 16x9 image specification, in RGBA logical coordinates."""
    if variant not in (0, 1) or not 0 <= x < WIDTH or not 0 <= y < HEIGHT:
        raise ValueError("unsupported image variant or coordinate")
    if x < 2 and y < 2:
        return 255, 0, 0, 255
    if x >= WIDTH - 2 and y < 2:
        return 0, 255, 0, 255
    if x < 2 and y >= HEIGHT - 2:
        return 0, 0, 255, 255
    if x >= WIDTH - 2 and y >= HEIGHT - 2:
        return 255, 255, 0, 255
    light = (192, 208, 224) if variant == 0 else (224, 80, 160)
    rgb = light if ((x // 2) + (y // 2)) % 2 else (16, 32, 48)
    return (*rgb, 255)


@lru_cache(maxsize=2)
def _expected_pixels(variant: int) -> bytes:
    rows = []
    for y in range(HEIGHT):
        row = bytearray()
        for x in range(WIDTH):
            red, green, blue, alpha = logical_pixel(x, y, variant)
            row.extend(bytes((blue, green, red, alpha)) * SCALE)
        rows.append(bytes(row) * SCALE)
    return b"".join(rows)


def verify_pixels(capture: bytes, variant: int) -> bool:
    """Validate the exact pinned TGA header and every BGRA/alpha byte."""
    valid_variant = type(variant) is int and variant in (0, 1)
    size_ok = len(capture) == CAPTURE_SIZE
    header_ok = capture[:18] == TGA_HEADER
    print(f"NX2_NATIVE_FRAME_CAPTURE_BYTES={len(capture)}")
    print(f"NX2_NATIVE_FRAME_CAPTURE_SHA256={hashlib.sha256(capture).hexdigest()}")
    print(f"NX2_NATIVE_FRAME_TGA_SIZE_MATCH={int(size_ok)}")
    print(f"NX2_NATIVE_FRAME_TGA_HEADER_MATCH={int(header_ok)}")
    pixels_ok = (valid_variant and size_ok and header_ok and
                 capture[18:] == _expected_pixels(variant))
    print(f"NX2_NATIVE_FRAME_ALL_PIXELS_MATCH={int(pixels_ok)}")
    if valid_variant and size_ok and header_ok and not pixels_ok:
        expected = _expected_pixels(variant)
        mismatch = next(i for i, (a, b) in enumerate(zip(capture[18:], expected)) if a != b)
        pixel, channel = divmod(mismatch, 4)
        print(f"NX2_NATIVE_FRAME_FIRST_MISMATCH=x{pixel % CAPTURE_WIDTH},"
              f"y{pixel // CAPTURE_WIDTH},channel{'BGRA'[channel]}")
    return bool(pixels_ok)


def _cmif(name: str, header: int = 10, descriptor: int = 0):
    return tuple((name + "_" + suffix, value) for suffix, value in (
        ("transport", 0), ("header0", 0), ("header1", header),
        ("descriptor", descriptor), ("magic", 0x4F434653), ("result", 0)))


def _tipc(name: str, command: int, words: int = 1, result: int = 0, handle: str = ""):
    fields = [(name + "_transport", 0), (name + "_header0", command + 16),
              (name + "_header1", 0x80000001 if handle else words)]
    if handle:
        fields.extend(((name + "_descriptor", 0x20), (handle, None)))
    return tuple(fields + [(name + "_result", result)])


def _notifications(name: str, first: int):
    return (_tipc(name, 21) + ((name + "_guard_before", 0xA5A5A5A5),) +
            tuple((f"{name}_word{i:02d}", first if i == 0 else 0) for i in range(32)) +
            ((name + "_guard_after", 0xA5A5A5A5),))


# graphics_supervisor.cpp + ipc_helpers.h at Eden e2f285ab: CMIF carries SFCO;
# TIPC carries command+16 and raw result/payload words, with no invented SFCO.
FIELDS = (
    ("variant", None), ("image_width", WIDTH), ("image_height", HEIGHT),
    ("image_address_lo", None), ("image_address_hi", None), ("image_checksum", None),
    ("connect_rc", 0), ("sm_handle", None),
    *_cmif("sm_init"),
    *_cmif("get_applet", 0x8000000A, 0x20), ("applet_handle", None),
    *_cmif("open_proxy", 0x8000000A, 0x20), ("proxy_handle", None),
    *_cmif("get_window", 0x8000000A, 0x20), ("window_handle", None),
    *_cmif("get_aruid", 14), ("aruid_lo", None), ("aruid_hi", None),
    *_cmif("get_self", 0x8000000A, 0x20), ("self_handle", None),
    *_cmif("get_gsv", 0x8000000A, 2), ("gsv_handle", None),
    *_tipc("bootstrap", 4), *_tipc("bind", 11), *_tipc("ready", 101),
    *_tipc("image_init", 1501), *_tipc("image_formats", 1502),
    *_tipc("open_nvdrv", 1402, handle="nvdrv_handle"),
    *_tipc("gpu_init", 401), *_tipc("gpu_ready", 402),
    *_tipc("size_zero", 435, 3, 0x100F3), ("size_zero_lo", 0), ("size_zero_hi", 0),
    *_tipc("size_valid", 435, 3), ("size_valid_lo", 8192), ("size_valid_hi", 0),
    *_tipc("memory_create", 111, 2), ("memory_id", None),
    *_tipc("memory_bind", 114), *_tipc("image_create", 429, 2), ("image_id", None),
    *_tipc("pool_create", 315), *_tipc("display_init", 301),
    *_tipc("open_vi2", 305, handle="vi2_handle"),
    *_tipc("register", 201), *_tipc("open_display", 101), *_tipc("bind_display", 251),
    *_tipc("available_before", 212, 3),
    ("available_before_lo", 0x7FFF), ("available_before_hi", 0),
    *_tipc("present", 229, 7), ("present_lo", 0x7FFE), ("present_hi", 0),
    *((f"present_tail{i:02d}", 0) for i in range(4)),
    *_tipc("poll", 212, 3), ("poll_lo", 0x7FFF), ("poll_hi", 0),
    ("poll_count", 100), ("poll_queued_count", None), ("poll_released_count", None),
    *_notifications("released", 8), *_notifications("clear", 0),
    *_tipc("unbind_display", 252), *_tipc("unregister", 202), *_tipc("close_display", 102),
    *_tipc("pool_destroy", 314), *_tipc("image_destroy", 430), *_tipc("memory_destroy", 112),
    *_tipc("display_finalize", 303),
    *(("close_" + name, 0) for name in
      ("vi2", "nvdrv", "gsv", "self", "window", "proxy", "applet", "sm")),
    ("fail_step", 0),
)
HANDLE_FIELDS = tuple(name + "_handle" for name in
                      ("sm", "applet", "proxy", "window", "self", "gsv", "nvdrv", "vi2"))
FIELD_RECORD = re.compile(r"NX2_FRAME ([a-z][a-z0-9_]*)=([0-9a-f]{8})")
MARKERS = ("BEGIN", "PRESENT_BEGIN", "PRESENTED", "CLEANUP_BEGIN", "COMPLETE")
# The frozen Clang CI reports the closing lines of these two multiline LOG_INFO
# invocations (948 and 92), confirmed by the first actual frame artifact. Keep
# exact file/function/line attribution; the invocation's first line is not a log.
QUEUED = re.compile(LOG_PREFIX + r"Service\.AM <Info> "
    r"core/hle/service/am/service/graphics_supervisor\.cpp:948:QueueNativeImage: "
    r"Native image queued for display: image=(\d+), slot=0, fence=4294967295/0, dimensions=16x9")
SUBMITTED = re.compile(LOG_PREFIX + r"Service\.NVDRV <Info> "
    r"core/hle/service/nvdrv/devices/nvdisp_disp0\.cpp:116:Composite: "
    r"Native composite submitted: layers=1, address=(0x[0-9a-f]+)")
CAPTURED = re.compile(LOG_PREFIX + r"Service\.NVDRV <Info> "
    r"core/hle/service/nvdrv/devices/nvdisp_disp0\.cpp:147:operator\(\): "
    r"Captured composited frame: 1920x1080, saved=true, nonblack=true")
FRONTEND = re.compile(LOG_PREFIX + r"Frontend <Info> "
    r"yuzu_cmd/emu_window/emu_window_sdl3_vk\.cpp:92:EmuWindow_SDL3_VK: "
    r"Eden Version: .+ \(Vulkan\)")
RENDERER = re.compile(LOG_PREFIX + r"Render\.Vulkan <Info> "
    r"video_core/renderer_vulkan/renderer_vulkan\.cpp:(278|279|280):Report: "
    r"(Driver|Device|Vulkan): (.+)")
CAPABILITY_FAILURE = re.compile(
    r"Unsuitable driver|Skipping composite while the swapchain has no format|"
    r"Vulkan initialization (?:failed|error)|Presentation not supported|VK_ERROR_[A-Z_]+",
    re.IGNORECASE)


def assess(raw: bytes, process_rc: int, capture: bytes, variant: int) -> bool:
    print(f"NX2_NATIVE_FRAME_PROCESS_RC={process_rc}")
    print(f"NX2_NATIVE_FRAME_VARIANT={variant}")
    print(f"NX2_NATIVE_FRAME_LOG_BYTES={len(raw)}")
    print(f"NX2_NATIVE_FRAME_LOG_NUL_COUNT={raw.count(bytes([0]))}")
    if len(raw) > MAX_LOG_SIZE or type(variant) is not int or variant not in (0, 1):
        print("NX2_NATIVE_FRAME_INPUT_NOT_VALID")
        return False
    lines = [BOUNDARY.sub("", line.removesuffix("\r"))
             for line in raw.decode("utf-8", "replace").split("\n")]
    events = {name: [] for name in MARKERS}
    classified, exits, managers, records, queued, submitted, captured, frontends = (
        [], [], [], [], [], [], [], [])
    renderer = {name: [] for name in ("Driver", "Device", "Vulkan")}
    errors = []
    for index, line in enumerate(lines):
        if CONTROL.search(line):
            errors.append(f"corrupted record at line {index}")
        if CLASSIFIED.fullmatch(line):
            classified.append(index)
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
            expected_line = {"Driver": "278", "Device": "279", "Vulkan": "280"}[report[2]]
            if report[1] != expected_line or not report[3].strip():
                errors.append(f"invalid renderer report at line {index}")
            renderer[report[2]].append((index, report[3]))
        for pattern, term, target in (
            (QUEUED, "Native image queued for display:", queued),
            (SUBMITTED, "Native composite submitted:", submitted),
            (CAPTURED, "Captured composited frame:", captured),
        ):
            match = pattern.fullmatch(line)
            if match:
                target.append((index, match[1] if match.lastindex else None))
            elif term in line:
                errors.append(f"malformed or unattributed {term} at line {index}")
        if "NX2_FRAME" not in line:
            continue
        output = GUEST_OUTPUT.fullmatch(line)
        if output is None:
            errors.append(f"unattributed guest record at line {index}")
            continue
        payload = output[1]
        if payload in ("NX2_FRAME_" + name for name in MARKERS):
            events[payload[len("NX2_FRAME_"):]].append(index)
        else:
            record = FIELD_RECORD.fullmatch(payload)
            if record:
                records.append((index, record[1], int(record[2], 16)))
            else:
                errors.append(f"malformed or failure guest record at line {index}")

    startup_counts = {name: 0 for name, _, _ in STARTUP_ERRORS}
    diagnostics, unexpected_errors, unexpected_stubs = [], [], []
    for index, line in enumerate(lines):
        if ERROR.search(line):
            allowed = next((name for name, _, pattern in STARTUP_ERRORS
                            if pattern.fullmatch(line) and len(events["BEGIN"]) == 1 and
                            index < events["BEGIN"][0]), None)
            if allowed is None:
                unexpected_errors.append(index)
            else:
                startup_counts[allowed] += 1
            diagnostics.append(index)
        if STUB.search(line) and index not in managers:
            unexpected_stubs.append(index)
    startup_bounded = all(startup_counts[name] <= limit for name, limit, _ in STARTUP_ERRORS)
    fields_in_order = [name for _, name, _ in records] == [name for name, _ in FIELDS]
    values = {name: value for _, name, value in records}
    values_match = (all(expected is None or values.get(name) == expected
                        for name, expected in FIELDS) and
                    all(value != 0xFFFFFFFF for value in values.values()))
    handles = [values.get(name, 0) for name in HANDLE_FIELDS]
    valid_handles = (len(set(handles)) == 8 and all(
        handle >> 30 == 0 and (handle & 0x7FFF) < 1024 and
        ((handle >> 15) & 0x7FFF) != 0 for handle in handles))
    aruid = values.get("aruid_lo", 0) | (values.get("aruid_hi", 0) << 32)
    aruid_matches = len(exits) == 1 and aruid != 0 and aruid == exits[0][1]
    image_address = values.get("image_address_lo", 0) | (values.get("image_address_hi", 0) << 32)
    image_observed = (values.get("variant") == variant and
                      values.get("image_checksum") == BACKING_CHECKSUMS[variant] and
                      image_address > 0 and image_address % 4096 == 0 and
                      image_address + 8192 <= 1 << 39 and
                      all(0 < values.get(name, 0) < 0xFFFFFFFF for name in ("memory_id", "image_id")))
    queued_count, released_count = values.get("poll_queued_count", -1), values.get("poll_released_count", -1)
    polls_match = (0 <= queued_count < 100 and 1 <= released_count <= 100 and
                   queued_count + released_count == 100)
    unique_events = (all(len(events[name]) == 1 for name in MARKERS) and
                     len(classified) == len(exits) == len(managers) == len(queued) ==
                     len(submitted) == len(captured) == len(frontends) == 1 and bool(records) and
                     all(len(renderer[name]) == 1 for name in renderer))
    events_in_order = renderer_valid = queue_matches = False
    if unique_events:
        begin, present_begin, presented, cleanup, complete = (events[name][0] for name in MARKERS)
        events_in_order = (
            classified[0] < begin < managers[0] < present_begin < presented < cleanup <
            records[0][0] <= records[-1][0] < complete < exits[0][0] and
            present_begin < queued[0][0] < presented and
            present_begin < submitted[0][0] < captured[0][0] < cleanup)
        # A successful QueueBuffer can race HWC before its SVC returns. Neither
        # the queue diagnostic nor PRESENTED is ordered against the capture.
        queue_matches = (int(queued[0][1]) == values.get("image_id") and
                         0 < int(submitted[0][1], 16) < 1 << 64)
        version = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", renderer["Vulkan"][0][1])
        renderer_valid = (version is not None and tuple(map(int, version.groups())) >= (1, 1, 0) and
                          frontends[0] < begin and
                          renderer["Driver"][0][0] < renderer["Device"][0][0] <
                          renderer["Vulkan"][0][0] < begin)
    failed = any(FAILURE.search(line) or CAPABILITY_FAILURE.search(line) or
                 "NX2_FRAME_FAILURE" in line for line in lines)
    for name, _ in FIELDS:
        value = values.get(name)
        print(f"NX2_NATIVE_FRAME_OBSERVED_{name.upper()}=" +
              (f"{value:08x}" if value is not None else "MISSING"))
    for name, _, _ in STARTUP_ERRORS:
        print(f"NX2_NATIVE_FRAME_ALLOWED_STARTUP_{name}_ERRORS={startup_counts[name]}")
    for name, entries in renderer.items():
        print(f"NX2_NATIVE_FRAME_RENDERER_{name.upper()}=" +
              (entries[0][1] if len(entries) == 1 else "NOT_UNIQUE"))
    checks = (
        ("FIELD_COUNT", len(records)), ("FIELDS_IN_ORDER", fields_in_order),
        ("VALUES_MATCH", values_match), ("DISTINCT_HANDLES_OBSERVED", valid_handles),
        ("ARUID_MATCHES_EXIT_PROCESS", aruid_matches), ("IMAGE_OBSERVED", image_observed),
        ("POLL_COUNTS_MATCH", polls_match), ("EVENTS_IN_ORDER", events_in_order),
        ("QUEUE_MATCHES_IMAGE", queue_matches), ("RENDERER_VALID", renderer_valid),
        ("KNOWN_MANAGER_STUB_COUNT", len(managers)), ("STARTUP_ERROR_COUNTS_BOUNDED", startup_bounded),
        ("UNEXPECTED_ERROR_COUNT", len(unexpected_errors)), ("UNEXPECTED_STUB_COUNT", len(unexpected_stubs)),
        ("FAILURE_SEEN", failed), ("PROTOCOL_ERRORS", len(errors)),
    )
    for name, value in checks:
        print(f"NX2_NATIVE_FRAME_{name}={int(value)}")
    for index in sorted(set(diagnostics + managers + unexpected_stubs))[:20]:
        safe = "".join(c if c.isprintable() else "?" for c in lines[index])
        print(f"NX2_NATIVE_FRAME_DIAGNOSTIC[{index}]={safe[:500]}")
    for error in errors[:10]:
        print(f"NX2_NATIVE_FRAME_PROTOCOL_ERROR={error}")
    lifecycle_ok = (process_rc == 0 and fields_in_order and values_match and valid_handles and
                    aruid_matches and image_observed and polls_match and events_in_order and
                    queue_matches and renderer_valid and startup_bounded and not failed and
                    not unexpected_errors and not unexpected_stubs and not errors)
    # Avoid repeatedly comparing 8 MiB for a log which already failed closed.
    pixels_ok = verify_pixels(capture, variant) if lifecycle_ok else False
    ok = lifecycle_ok and pixels_ok
    print("NX2_NATIVE_FRAME_GUEST_PIXELS_PASS" if ok else "NX2_NATIVE_FRAME_GUEST_PIXELS_NOT_VERIFIED")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--exit", required=True, type=int, dest="process_rc")
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--variant", required=True, type=int, choices=(0, 1))
    args = parser.parse_args()
    try:
        if args.log.stat().st_size > MAX_LOG_SIZE or args.capture.stat().st_size != CAPTURE_SIZE:
            parser.exit(1, "NX2_NATIVE_FRAME_INPUT_SIZE_NOT_VALID\n")
        return 0 if assess(args.log.read_bytes(), args.process_rc,
                           args.capture.read_bytes(), args.variant) else 1
    except OSError as error:
        parser.exit(1, f"NX2_NATIVE_FRAME_INPUT_UNAVAILABLE: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
