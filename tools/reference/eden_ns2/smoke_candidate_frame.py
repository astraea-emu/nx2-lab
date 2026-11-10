#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Execute NX2's existing original CPU-drawn image on a pinned modern engine.

This is an exploratory graphics milestone, NOT an engine adoption/security gate.
No external games or SDK, new guest graphics implementation, or raw host logs.
The separate original malformed-loader control remains mandatory and failing.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import tempfile
import time

from assess_native_frame import logical_pixel
from make_native_frame_exefs import (
    build_frame_nso, compile_frame_segments, verify_frame_fixture,
)
from make_native_exefs import build_extended_npdm
from modern_exit_overlay import verify_applied
from smoke_candidate_exefs import built_cli, lifecycle

WIDTH, HEIGHT, SCALE = 16, 9, 80
TGA_W, TGA_H = WIDTH * SCALE, HEIGHT * SCALE
TGA_BYTES = 18 + TGA_W * TGA_H * 4
MAX_LOG = 8 * 1024 * 1024


@lru_cache(maxsize=2)
def expected_pixels(variant: int) -> bytes:
    if type(variant) is not int or variant not in (0, 1):
        raise ValueError("Original image variant must be 0 or 1")
    rows = []
    for y in range(HEIGHT):
        line = bytearray()
        for x in range(WIDTH):
            red, green, blue, alpha = logical_pixel(x, y, variant)
            line.extend(bytes((blue, green, red, alpha)) * SCALE)
        rows.append(bytes(line) * SCALE)
    return b"".join(rows)



def original_pixel_difference(actual: bytes, expected: bytes) -> dict:
    """Lossy evidence from the project-authored pattern, not a captured image.

    The independent exact-byte equality remains the sole positive-pixel gate.
    Never upload captured pixels, raw host logs, or unbounded histograms.
    """
    if len(actual) != len(expected) or len(actual) != TGA_W * TGA_H * 4:
        raise ValueError("Original pixel diagnostics require exact frame byte count")
    first = next((i for i, (a, b) in enumerate(zip(actual, expected))
                  if a != b), None)
    different = sum(actual[i:i + 4] != expected[i:i + 4]
                    for i in range(0, len(actual), 4))
    probes = (
        ("top_left", 0, 0),
        ("top_right", TGA_W - 1, 0),
        ("bottom_left", 0, TGA_H - 1),
        ("bottom_right", TGA_W - 1, TGA_H - 1),
        ("center", TGA_W // 2, TGA_H // 2),
        ("inner", SCALE * 5 + SCALE // 2, SCALE * 3 + SCALE // 2),
    )
    samples = []
    for label, x, y in probes:
        offset = (y * TGA_W + x) * 4
        samples.append({"position": label, "expected_bgra": list(expected[offset:offset + 4]),
                        "actual_bgra": list(actual[offset:offset + 4])})
    if first is None:
        mismatch = None
    else:
        pixel, channel = divmod(first, 4)
        start = pixel * 4
        mismatch = {
            "x": pixel % TGA_W, "y": pixel // TGA_W,
            "channel": "BGRA"[channel],
            "expected_bgra": list(expected[start:start + 4]),
            "actual_bgra": list(actual[start:start + 4]),
        }
    return {
        "mismatched_pixel_count": different,
        "total_pixel_count": TGA_W * TGA_H,
        "first_mismatch": mismatch,
        "fixed_original_pattern_probes": samples,
        "red_blue_swapped_exact_match": all(
            actual[i] == expected[i + 2] and actual[i + 1] == expected[i + 1]
            and actual[i + 2] == expected[i] and actual[i + 3] == expected[i + 3]
            for i in range(0, len(actual), 4)),
        "raw_capture_preserved": False,
    }


def check_capture(capture: bytes, variant: int) -> dict:
    """Exact 1280x720 BGRA pixels; honor TGA top/bottom row-order bit."""
    expected = expected_pixels(variant)
    size_ok = len(capture) == TGA_BYTES
    header_ok = (
        size_ok and capture[0:12] == bytes(12)[:2] + b"\x02" + bytes(9)
        and capture[12:16] == struct.pack("<HH", TGA_W, TGA_H)
        and capture[16] == 32 and capture[17] in (0x28, 0x08)
    )
    pixels_ok = False
    differences = None
    if header_ok:
        actual = capture[18:]
        if capture[17] == 0x08:
            stride = TGA_W * 4
            actual = b"".join(actual[i:i + stride]
                              for i in range(len(actual) - stride, -1, -stride))
        pixels_ok = actual == expected
        if not pixels_ok:
            differences = original_pixel_difference(actual, expected)
    return {
        "capture_present": bool(capture),
        "capture_bytes": len(capture),
        "capture_sha256": hashlib.sha256(capture).hexdigest() if capture else None,
        "original_tga_header_match": bool(header_ok),
        "every_original_pixel_match": bool(pixels_ok),
        "bounded_mismatch_diagnostics": differences,
    }



FAIL_STEP = re.compile(rb"NX2_FRAME fail_step=([0-9a-f]{8})")


def original_guest_failure_step(raw: bytes) -> dict:
    """Extract one authored failure-stage integer, never diagnostic log text."""
    seen = FAIL_STEP.findall(raw)
    if len(seen) != 1:
        return {"step_observed_once": False, "step": None,
                "stage": "unclassified"}
    step = int(seen[0], 16)
    # Original cleanup release checks are numbered 34..40; do not conflate
    # those authored failures with invalid/corrupted record values.
    if not 0 <= step <= 41:
        return {"step_observed_once": False, "step": None,
                "stage": "out_of_contract"}
    stage = ("completed" if step == 0 else "setup" if step <= 19 else
             "resource_registration" if step <= 29 else
             "present" if step == 30 else
             "retirement" if step <= 33 else
             "gpu_address_space_close" if step == 41 else "cleanup_release")
    return {"step_observed_once": True, "step": step, "stage": stage}




def original_graphics_device_mapping_observation(raw: bytes) -> dict:
    """Count fixed known upstream categories; do not retain host messages."""
    return {
        "native_image_missing_device_mapping_count":
            min(raw.count(b"has no device mapping"), 1000),
        "gpu_mapping_missing_address_space_count":
            min(raw.count(b"no address space or session"), 1000),
        "native_vi2_present_request_count":
            min(raw.count(b"nx2:vi2 229 present #"), 1000),
        "raw_host_log_retained": False,
    }


ORIGINAL_SIZE_FIELDS = ("transport", "header0", "header1", "result", "lo", "hi")
SIZE_FIELD = re.compile(
    rb"NX2_FRAME size_zero_(transport|header0|header1|result|lo|hi)=([0-9a-f]{8})"
)


def original_invalid_size_observation(raw: bytes) -> dict:
    """Read only the six original guest-owned numeric fields; never log text."""
    captures = {key: [] for key in ORIGINAL_SIZE_FIELDS}
    for name, hex_value in SIZE_FIELD.findall(raw):
        captures[name.decode()].append(int(hex_value, 16))
    if any(len(captures[name]) != 1 for name in ORIGINAL_SIZE_FIELDS):
        return {"fields_observed_once": False, "original_rejection_observed": False,
                "returned_code": None, "returned_size": None}
    values = {key: captures[key][0] for key in ORIGINAL_SIZE_FIELDS}
    rejection = (values["transport"] == 0 and values["header0"] == 16 + 435 and
                 values["header1"] == 3 and values["result"] == 0x100F3 and
                 values["lo"] == 0 and values["hi"] == 0)
    return {
        "fields_observed_once": True,
        "original_rejection_observed": bool(rejection),
        "returned_code": f"0x{values['result']:08x}",
        "returned_size": values["lo"] | (values["hi"] << 32),
    }



FINALIZE_FIELDS = ("transport", "header0", "header1", "result")
FINALIZE_FIELD = re.compile(
    rb"NX2_FRAME display_finalize_(transport|header0|header1|result)=([0-9a-f]{8})"
)


def original_finalize_observation(raw: bytes) -> dict:
    """Only four original guest-owned response words; no raw messages or URLs."""
    fields = {name: [] for name in FINALIZE_FIELDS}
    for name, value in FINALIZE_FIELD.findall(raw):
        fields[name.decode()].append(int(value, 16))
    if any(len(fields[name]) != 1 for name in FINALIZE_FIELDS):
        return {"fields_observed_once": False}
    values = {name: fields[name][0] for name in FINALIZE_FIELDS}
    return {
        "fields_observed_once": True,
        "transport": values["transport"],
        "header0": values["header0"],
        "header1": values["header1"],
        "result_code": f"0x{values['result']:08x}",
        "legacy_reply_shape_match": (
            values["transport"] == 0 and values["header0"] == 16 + 303
            and values["header1"] == 1 and values["result"] == 0),
    }



def original_exact_pixel_renderer_config() -> str:
    """Request a non-filtered screenshot; never change original image or oracle.

    Pinned Eglantine/Lichii use ScaleForce and FXAA defaults; screenshot
    blit_capture uses PresentFiltersForDisplay. The enum's first entries
    are NearestNeighbor and None (both 0), and the INI reader requires
    each setting's \default=false to override those defaults.
    """
    return (
        "[Renderer]\n"
        "backend=1\nbackend\\default=false\n"
        "vulkan_device=0\nvulkan_device\\default=false\n"
        "scaling_filter=0\nscaling_filter\\default=false\n"
        "anti_aliasing=0\nanti_aliasing\\default=false\n"
    )

def run_one(cli: Path, variant: int, root: Path, icd: Path, seconds: int) -> dict:
    work = root / f"variant-{variant}"
    work.mkdir()
    guest = work / "guest"
    guest.mkdir()
    # Eglantine/Lichii return copied GSV session handles, unlike frozen Eden.
    parts = compile_frame_segments("aarch64-linux-gnu-", variant=variant,
                                   copy_tipc_handles=True, observe_invalid_size=True,
                                   modern_direct_vi2=True, modern_gpu_image_map=True)
    main, npdm = build_frame_nso(parts), build_extended_npdm()
    verify_frame_fixture(main, npdm, variant)
    (guest / "main").write_bytes(main)
    (guest / "main.npdm").write_bytes(npdm)
    cfg = work / "config.ini"
    cfg.write_text(original_exact_pixel_renderer_config())
    captures = work / "captures"
    captures.mkdir()
    home = work / "home"
    for dir in ("config", "data", "cache", "runtime"):
        (home / dir).mkdir(parents=True, exist_ok=True)
    (home / "runtime").chmod(0o700)
    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH")}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
               XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
               XDG_RUNTIME_DIR=str(home / "runtime"), SDL_VIDEODRIVER="x11",
               SDL_AUDIODRIVER="dummy", VK_DRIVER_FILES=str(icd),
               EDEN_NX2_FRAME_CAPTURE=str(captures), EDEN_NX2_HIDE_WINDOW="0")
    logfile = work / "raw-runtime.log"  # ephemeral only: never in the output receipt/artifact
    command = ["xvfb-run", "-a", "-e", str(work / "xvfb.log"),
               "-s", "-screen 0 1280x720x24 -nolisten tcp",
               "timeout", "--signal=TERM", "--kill-after=4s", f"{seconds}s",
               str(cli), "--config", str(cfg), "--singlecore",
               "--game", str(guest / "main")]
    begin = time.monotonic()
    with logfile.open("wb") as output:
        proc = subprocess.Popen(command, cwd=work, env=env, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = proc.wait(timeout=seconds + 12)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            rc = proc.wait()
    elapsed = round(time.monotonic() - begin, 3)
    if logfile.stat().st_size > MAX_LOG:
        raise ValueError("Graphics host log exceeded maximum inspection size")
    raw = logfile.read_bytes()
    cap_files = tuple(captures.glob("nx2-frame-*.tga"))
    if len(cap_files) > 4 or any(f.is_symlink() or not f.is_file() or
                                f.stat().st_size > TGA_BYTES for f in cap_files):
        raise ValueError("Invalid bounded original capture set")
    expected_name = captures / "nx2-frame-00001.tga"
    captured = (expected_name.read_bytes() if len(cap_files) == 1 and
                expected_name in cap_files else b"")
    pixel = check_capture(captured, variant)
    markers = {name: raw.count(f"NX2_FRAME_{name}\n".encode())
               for name in ("BEGIN", "PRESENT_BEGIN", "PRESENTED", "CLEANUP_BEGIN", "COMPLETE",
                            "MODERN_AS_OPENED", "MODERN_AS_INITIALIZED",
                            "MODERN_IMAGE_REGISTERED", "MODERN_AS_CLOSED",
                            "MODERN_CTRL_OPENED", "MODERN_CTRL_CHARACTERIZED",
                            "MODERN_CTRL_CLOSED")}
    positive = rc == 0 and pixel["every_original_pixel_match"] and all(
        count == 1 for count in markers.values())
    size_observation = original_invalid_size_observation(raw)
    return {
        "variant": variant,
        "source_authored_main_sha256": hashlib.sha256(main).hexdigest(),
        "source_authored_npdm_sha256": hashlib.sha256(npdm).hexdigest(),
        "natural_exit": rc == 0, "process_rc": rc, "elapsed_seconds": elapsed,
        "original_guest_markers": markers,
        "original_guest_failure_stage": original_guest_failure_step(raw),
        "original_finalize_reply": original_finalize_observation(raw),
        "host_graphics_mapping_categories": original_graphics_device_mapping_observation(raw),
        "original_invalid_image_size_control": size_observation,
        "capture_count": len(cap_files),
        "capture": pixel, "lifecycle": lifecycle(raw),
        "positive_graphics_controls_passed": bool(positive),
        "full_original_contract_passed": bool(
            positive and size_observation["original_rejection_observed"]),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("candidate", choices=("eglantine", "lichii"))
    p.add_argument("checkout", type=Path)
    p.add_argument("build", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--seconds", type=int, default=30)
    a = p.parse_args()
    try:
        if not 5 <= a.seconds <= 60 or a.output.exists():
            raise ValueError("Require bounded execution and a fresh receipt")
        if a.output.resolve().is_relative_to(a.checkout.resolve()):
            raise ValueError("Receipt must not modify engine source")
        source = verify_applied(a.checkout, a.candidate)
        cli, sha = built_cli(a.checkout, a.build)
        manifests = tuple(sorted(Path("/usr/share/vulkan/icd.d").glob("lvp_icd*.json")))
        if len(manifests) != 1:
            raise ValueError("Require exactly one Mesa Lavapipe Vulkan ICD")
        with tempfile.TemporaryDirectory(prefix="nx2-modern-original-graphics-") as temp:
            root = Path(temp)
            records = [run_one(cli, variant, root, manifests[0], a.seconds)
                       for variant in (0, 1)]
        if verify_applied(a.checkout, a.candidate) != source:
            raise ValueError("Engine source changed during graphics experiment")
        different = records[0]["capture"]["capture_sha256"] != records[1]["capture"]["capture_sha256"]
        success = all(r["positive_graphics_controls_passed"] for r in records) and different
        receipt = {
            "kind": "nx2-original-modern-cpu-image-v1",
            "candidate": a.candidate, "revision": source["commit"],
            "approved_exit_adapter": True,
            "original_guest_tipc_copy_handle_adapter": True,
            "invalid_image_size_input_preserved_as_observation": True,
            "modern_direct_vi2_positive_adapter": True,
            "source_authored_modern_gpu_image_map": True,
            "legacy_vi2_registration_and_notifications_omitted": True,
            "source_built_cli_sha256": sha,
            "software_vulkan_icd": manifests[0].name,
            "renderer_nearest_no_aa_requested": True,
            "two_variants_produce_different_captures": bool(different),
            "original_positive_graphics_pass": bool(success),
            # The positive-only modern guest does not execute legacy VI2
            # registration/notification negatives, regardless of size result.
            "full_original_native_frame_contract_qualified": False,
            "loader_negative_control_qualified": False,
            "game_compatibility_qualified": False,
            "raw_runtime_logs_retained": False,
            "trials": records,
        }
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print("NX2_MODERN_ORIGINAL_CPU_IMAGE_POSITIVE=" +
              ("PASS" if success else "NOT_VERIFIED") + " candidate=" + a.candidate)
        return 0 if success else 1
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        print("NX2_MODERN_ORIGINAL_CPU_IMAGE_UNAVAILABLE: " + str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
