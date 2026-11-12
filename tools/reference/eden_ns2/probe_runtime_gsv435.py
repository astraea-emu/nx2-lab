#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One bounded original-GPU smoke against an existing modern emulator binary.

This is diagnostic evidence, not hardware ABI or pixel-correctness qualification.
Raw logs and generated original inputs remain in the private output directory.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

from run_native_frame import GPU_CONFIG, FLUSH_CONFIG

ROOT = Path(__file__).resolve().parent
MAX_LOG = 4 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", required=True, type=Path)
    parser.add_argument("--icd", required=True, type=Path, help="Lavapipe Vulkan ICD JSON")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tool-prefix", default="aarch64-linux-gnu-")
    args = parser.parse_args()
    emulator, icd, output = (p.resolve() for p in (args.emulator, args.icd, args.output))
    if not emulator.is_file() or not icd.is_file():
        parser.error("emulator and Vulkan ICD must exist")
    if output.exists():
        parser.error("output already exists; use a fresh private directory")
    output.mkdir(parents=True, mode=0o700)
    guest = output / "guest"
    fixture_log = output / "fixture.log"
    with fixture_log.open("wb") as stream:
        subprocess.run(
            [sys.executable, str(ROOT / "make_native_frame_exefs.py"),
             "--output", str(guest), "--tool-prefix", args.tool_prefix,
             "--gpu-triangle", "--runtime-gsv435-smoke"],
            check=True, stdout=stream, stderr=subprocess.STDOUT,
        )

    config = output / "sdl-config.ini"
    config.write_text(
        GPU_CONFIG + FLUSH_CONFIG +
        "[Audio]\noutput_engine\\default=false\noutput_engine=3\n",
        encoding="utf-8")
    home = output / "home"
    for name in ("config", "data", "cache", "runtime"):
        (home / name).mkdir(parents=True, exist_ok=True)
    (home / "runtime").chmod(0o700)

    env = {k: v for k, v in os.environ.items()
           if not k.startswith("EDEN_") and k not in (
               "VK_DRIVER_FILES", "VK_ICD_FILENAMES", "VK_ADD_DRIVER_FILES",
               "VK_INSTANCE_LAYERS", "SDL_VIDEODRIVER", "SDL_AUDIODRIVER")}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
               XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
               XDG_RUNTIME_DIR=str(home / "runtime"), VK_DRIVER_FILES=str(icd),
               SDL_VIDEODRIVER="x11", SDL_AUDIODRIVER="dummy")

    command = ["xvfb-run", "-a", "timeout", "--signal=TERM", "--kill-after=4s",
               "35s", str(emulator), "--config", str(config), "--singlecore",
               "--game", str(guest / "main")]
    log = output / "runtime.log"
    with log.open("wb") as stream:
        completed = subprocess.run(command, cwd=output, env=env,
                                   stdout=stream, stderr=subprocess.STDOUT)
    with log.open("rb") as stream:
        raw = stream.read(MAX_LOG + 1)
    engine_log = home / "data/lichii/log/eden_log.txt"
    if engine_log.is_file():
        with engine_log.open("rb") as stream:
            raw += stream.read(MAX_LOG + 1 - min(len(raw), MAX_LOG + 1))
    # Read only bounded, source-owned guest fields; never publish raw host logs.
    diagnostic_fields = frozenset((
        "fail_step", "connect_rc", "sm_init_result", "get_applet_result",
        "open_proxy_result", "get_window_result", "get_aruid_result",
        "get_self_result", "get_gsv_result", "bootstrap_result",
        "bind_result", "ready_result", "image_init_result",
        "image_formats_result", "open_nvdrv_transport",
        "open_nvdrv_header0", "open_nvdrv_header1",
        "open_nvdrv_descriptor", "nvdrv_handle", "open_nvdrv_result",
        "gpu_init_result", "gpu_ready_result", "size_zero_result", "size_zero_lo",
        "size_valid_result", "size_valid_lo",
    ))
    observed = {}
    for name, value in re.findall(rb"NX2_FRAME ([a-z][a-z0-9_]*)=([0-9a-f]{8})", raw):
        field = name.decode("ascii")
        if field in diagnostic_fields and field not in observed:
            observed[field] = int(value, 16)
    report = {
        "mode": "diagnostic_gsv435_only",
        "original_guest_status": observed,
        "emulator_exit": completed.returncode,
        "log_bounded": len(raw) <= MAX_LOG,
        "guest_sha256": hashlib.sha256((guest / "main").read_bytes()).hexdigest(),
        "npdm_sha256": hashlib.sha256((guest / "main.npdm").read_bytes()).hexdigest(),
        "guest_started": b"NX2_FRAME_BEGIN" in raw,
        "gpu_started": b"NX2_GPU_BEGIN" in raw,
        "gpu_submitted": b"NX2_GPU_SUBMITTED" in raw,
        "guest_complete": b"NX2_FRAME_COMPLETE" in raw,
        "guest_failed": b"NX2_FRAME_FAILURE" in raw or b"NX2_GPU_FAILURE" in raw,
        "forced_timeout": completed.returncode in (124, 137),
        "pixels_verified": False,
    }
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True), flush=True)
    return 0 if (report["log_bounded"] and report["guest_started"] and
                 report["gpu_started"] and report["gpu_submitted"] and
                 report["guest_complete"] and not report["guest_failed"] and
                 not report["forced_timeout"] and completed.returncode == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
