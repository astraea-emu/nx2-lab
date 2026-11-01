#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare the pinned engine, run original image guests and verify every pixel.

Linux prerequisites are listed by build_native_engine.py --print-packages.
The first invocation fetches/builds the engine; later invocations validate and
reuse it. Every invocation creates fresh evidence. No console files or SDK
are needed, and this command does not install system packages.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from assess_native_frame import CAPTURE_SIZE, assess, verify_pixels
from assess_native_ipc import MAX_LOG_SIZE
from build_native_engine import EDEN_SHA, build_engine, digest

ROOT = Path(__file__).resolve().parent
CONFIG = "[Renderer]\n" + "".join(
    f"{key}={value}\n{key}\\default=false\n" for key, value in (
        ("backend", 1), ("vulkan_device", 0), ("resolution_setup", 3),
        ("scaling_filter", 0), ("anti_aliasing", 0), ("aspect_ratio", 0)))
GPU_CONFIG = CONFIG + "".join(
    f"{key}={value}\n{key}\\default=false\n" for key, value in (
        ("gpu_accuracy", 1), ("gpu_fence_behavior", 3),
        ("use_asynchronous_shaders", "false"))) + (
    "[Miscellaneous]\nlog_filter=*:Info HW.GPU:Debug Service.NVDRV:Debug\n"
    "log_filter\\default=false\n")


def read_capped(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        return stream.read(maximum + 1)


def verify_shader_inputs(directory: Path, variant: int, clear_only: bool) -> bool:
    """Bind the engine's observed native shader pages to the original inputs."""
    from native_gpu_commands import FS_OFFSET, VERTEX_OFFSET, VS_OFFSET, build_gpu_buffer
    snapshots = {p.name: p for p in directory.glob("native-graphics-shader-*.bin")}
    if clear_only:
        return not snapshots
    inputs = build_gpu_buffer(variant)
    expected = {"native-graphics-shader-1.bin": inputs[VS_OFFSET:FS_OFFSET],
                "native-graphics-shader-5.bin": inputs[FS_OFFSET:VERTEX_OFFSET]}
    return snapshots.keys() == expected.keys() and all(
        path.is_file() and not path.is_symlink() and read_capped(path, 4096) == expected[name]
        for name, path in snapshots.items())


def vulkan_environment(trial_home: Path, icd: Path, *, gpu: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    # Frozen Eden has shader overrides, skipped-stage and forced-clear switches.
    # Only the explicitly recorded experiment settings may reach the child.
    for key in tuple(env):
        if key.startswith("EDEN_") or key in (
                "VK_ICD_FILENAMES", "VK_ADD_DRIVER_FILES", "VK_INSTANCE_LAYERS",
                "SDL_VIDEODRIVER", "SDL_AUDIODRIVER"):
            del env[key]
    for child in ("config", "data/eden/play_time", "cache", "runtime"):
        (trial_home / child).mkdir(parents=True, exist_ok=True)
    (trial_home / "runtime").chmod(0o700)
    env.update(HOME=str(trial_home), XDG_CONFIG_HOME=str(trial_home / "config"),
               XDG_DATA_HOME=str(trial_home / "data"), XDG_CACHE_HOME=str(trial_home / "cache"),
               XDG_RUNTIME_DIR=str(trial_home / "runtime"), SDL_VIDEO_DRIVER="x11",
               SDL_AUDIO_DRIVER="dummy", VK_DRIVER_FILES=str(icd),
               EDEN_NX2_HIDE_WINDOW="0", EDEN_NATIVE_FRAME_ON_DEMAND="1")
    if gpu:
        env.update(EDEN_NATIVE_STRICT="1", EDEN_NATIVE_FRONTEND="lower",
                   EDEN_NATIVE_DRAW_DIAGNOSTICS="1")
    return env


def run_x11(command: list[str], directory: Path, env: dict[str, str],
            log_name: str, seconds: int) -> tuple[int, float]:
    """Run one bounded process and preserve its complete output and return code."""
    started = time.monotonic()
    argv = ["xvfb-run", "-a", "-e", str(directory / (log_name + ".xvfb")),
            "-s", "-screen 0 1920x1080x24 -nolisten tcp", "timeout",
            "--signal=TERM", "--kill-after=4s", str(seconds) + "s", *command]
    with (directory / log_name).open("wb") as output:
        result = subprocess.run(argv, cwd=directory, env=env, stdout=output,
                                stderr=subprocess.STDOUT, check=False)
    return result.returncode, time.monotonic() - started


def trial(cli: Path, output: Path, icd: Path, prefix: str, variant: int, *,
          gpu: bool = False, clear_only: bool = False) -> dict:
    directory = output / ("clear-only" if clear_only else f"variant-{variant}")
    directory.mkdir()
    guest = directory / "guest"
    assembled = time.monotonic()
    arguments = (["--gpu-triangle"] if gpu else []) + (["--clear-only"] if clear_only else [])
    with (directory / "fixture.log").open("wb") as log:
        subprocess.run([sys.executable, str(ROOT / "make_native_frame_exefs.py"),
                        "--output", str(guest), "--tool-prefix", prefix,
                        "--variant", str(variant), *arguments], stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    assemble_seconds = time.monotonic() - assembled
    config = directory / "config.ini"
    config.write_text(GPU_CONFIG if gpu else CONFIG)
    capture = directory / "native-latest-frame.tga"
    request = directory / "native-frame.request"
    if capture.exists() or request.exists():
        raise ValueError("frame trial must start without a capture or request")
    # The compositor only captures newly acquired buffers. Arm before the single
    # presentation; real saved-capture ordering and every pixel are checked below.
    request.write_text("NX2 original image capture\n")
    with tempfile.TemporaryDirectory(prefix="nx2-frame-home-") as temporary:
        env = vulkan_environment(Path(temporary), icd, gpu=gpu)
        rc, runtime_seconds = run_x11(
            [str(cli), "--config", str(config), "--singlecore", "--game", str(guest / "main")],
            directory, env, "runtime.log", 30)
    raw = read_capped(directory / "runtime.log", MAX_LOG_SIZE)
    pixels = (read_capped(capture, CAPTURE_SIZE) if capture.is_file() and not capture.is_symlink()
              and capture.stat().st_size == CAPTURE_SIZE else b"")
    report = io.StringIO()
    with contextlib.redirect_stdout(report):
        if gpu:
            from assess_native_gpu_frame import assess as assess_gpu
            verified = assess_gpu(raw, rc, pixels, variant, clear_only=clear_only)
            shaders_match = verify_shader_inputs(directory, variant, clear_only)
            print(f"NX2_GPU_OBSERVED_SHADER_INPUTS_MATCH={int(shaders_match)}")
            verified = verified and shaders_match
        else:
            verified = assess(raw, rc, pixels, variant)
    (directory / "assessment.log").write_text(report.getvalue())
    print(report.getvalue(), end="", flush=True)
    consumed = not request.exists()
    files = (guest / "main", guest / "main.npdm", directory / "runtime.log",
             directory / "assessment.log", config, capture)
    if gpu:
        files += tuple(directory / name for name in ("native-graphics-registers.bin",
                       "native-graphics-shader-1.bin", "native-graphics-shader-5.bin"))
    result = {"variant": variant, "process_rc": rc, "verified": verified and consumed,
              "workload": "gpu-clear" if clear_only else "gpu-triangle" if gpu else "cpu-image",
              "request_consumed": consumed, "assemble_seconds": round(assemble_seconds, 3),
              "runtime_seconds": round(runtime_seconds, 3),
              "eden_environment": {key: value for key, value in env.items() if key.startswith("EDEN_")},
              "files": {p.name: digest(p) for p in files if p.is_file()}}
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("NX2_FRAME_TRIAL " + json.dumps(result, sort_keys=True), flush=True)
    return result


def main() -> int:
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, default=Path("build/native-engine"))
    parser.add_argument("--output", type=Path, default=Path("build/native-frame"))
    parser.add_argument("--icd", type=Path, help="Lavapipe ICD JSON; otherwise discover installed lvp manifest")
    parser.add_argument("--tool-prefix", default=os.environ.get("NX2_AARCH64_PREFIX", "aarch64-linux-gnu-"))
    parser.add_argument("--variant", type=int, choices=(0, 1), default=0)
    parser.add_argument("--both", action="store_true", help="also prove that the changed guest produces its different image")
    parser.add_argument("--gpu-triangle", action="store_true",
                        help="render original guest shaders and include a clear-only negative control")
    args = parser.parse_args()
    label = "NX2_ORIGINAL_GPU_TRIANGLE" if args.gpu_triangle else "NX2_ORIGINAL_FRAME"
    try:
        for name in ("git", "xvfb-run", "xauth", "timeout", "vulkaninfo",
                     *(args.tool_prefix + x for x in ("as", "ld", "objcopy"))):
            if shutil.which(name) is None:
                raise ValueError(f"missing prerequisite: {name}")
        choices = [args.icd] if args.icd else sorted(Path("/usr/share/vulkan/icd.d").glob("lvp*.json"))
        if len(choices) != 1:
            raise ValueError("select exactly one installed Lavapipe manifest with --icd")
        icd = choices[0].resolve(strict=True)
        icd_bytes = read_capped(icd, 64 * 1024)
        if len(icd_bytes) > 64 * 1024:
            raise ValueError("Vulkan manifest exceeds the input limit")
        if "lvp" not in json.loads(icd_bytes)["ICD"]["library_path"]:
            raise ValueError("selected manifest does not identify Lavapipe")
        args.output.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix="run-", dir=args.output.resolve()))
        print(f"NX2_FRAME_OUTPUT={output}", flush=True)
        preparing = time.monotonic()
        source, cli, engine = build_engine(args.engine_dir)
        prepare_seconds = time.monotonic() - preparing
        sources = (ROOT / "native_frame_probe.S", ROOT / "native_frame_probe.ld",
                   ROOT / "make_native_frame_exefs.py", Path(__file__),
                   ROOT / "assess_native_frame.py", ROOT / "build_native_engine.py")
        if args.gpu_triangle:
            sources += tuple(ROOT / name for name in ("native_gpu_probe.S", "native_gpu_probe.ld",
                             "native_gpu_commands.py", "assess_native_gpu_frame.py"))
        provenance = {"eden_revision": EDEN_SHA, "eden_cli_sha256": digest(cli),
                      "engine": engine, "eden_source": str(source), "icd": str(icd),
                      "icd_sha256": digest(icd),
                      "source_sha256": {p.name: digest(p) for p in sources}}
        (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        with tempfile.TemporaryDirectory(prefix="nx2-vulkan-home-") as temporary:
            rc, _ = run_x11(["vulkaninfo"], output,
                           vulkan_environment(Path(temporary), icd), "vulkan.log", 20)
        capability_bytes = read_capped(output / "vulkan.log", MAX_LOG_SIZE)
        if len(capability_bytes) > MAX_LOG_SIZE:
            raise ValueError("Vulkan capability log exceeds the input limit")
        capabilities = capability_bytes.decode("utf-8", "replace")
        if rc != 0 or any(value not in capabilities for value in
                          ("llvmpipe", "VK_KHR_xlib_surface", "VK_KHR_swapchain")):
            raise ValueError("Lavapipe/X11 capabilities not established; inspect vulkan.log")
        variants = (0, 1) if args.both else (args.variant,)
        results = [trial(cli, output, icd, args.tool_prefix, variant, gpu=args.gpu_triangle)
                   for variant in variants]
        if args.gpu_triangle:
            results.append(trial(cli, output, icd, args.tool_prefix, 0, gpu=True, clear_only=True))
        passed = all(result["verified"] for result in results)
        pixel_check = verify_pixels
        if args.gpu_triangle:
            from assess_native_gpu_frame import verify_pixels as pixel_check
        if args.both and passed:
            a = read_capped(output / "variant-0/native-latest-frame.tga", CAPTURE_SIZE)
            b = read_capped(output / "variant-1/native-latest-frame.tga", CAPTURE_SIZE)
            with contextlib.redirect_stdout(io.StringIO()):
                changed = a != b and not pixel_check(b, 0) and not pixel_check(a, 1)
            print(f"NX2_FRAME_EDIT_CHANGES_PIXELS={int(changed)}")
            passed = passed and changed
        if args.gpu_triangle and passed:
            clear = read_capped(output / "clear-only/native-latest-frame.tga", CAPTURE_SIZE)
            with contextlib.redirect_stdout(io.StringIO()):
                negative = not pixel_check(clear, 0) and not pixel_check(clear, 1)
            print(f"NX2_GPU_CLEAR_REJECTED_AS_TRIANGLE={int(negative)}")
            passed = passed and negative
        summary = {"verified": passed, "output_directory": str(output),
                   "workload": "gpu-triangle" if args.gpu_triangle else "cpu-image",
                   "eden_cli_sha256": provenance["eden_cli_sha256"],
                   "engine_reused": engine["reused"],
                   "engine_prepare_seconds": round(prepare_seconds, 3),
                   "total_seconds": round(time.monotonic() - started, 3),
                   "variants": [{"variant": result["variant"],
                                 "workload": result["workload"],
                                 "process_rc": result["process_rc"],
                                 "capture_sha256": result["files"].get("native-latest-frame.tga")}
                                for result in results]}
        (output / "run-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print("NX2_FRAME_RUN " + json.dumps(summary, sort_keys=True), flush=True)
        print(label + ("_PASS" if passed else "_NOT_VERIFIED"))
        return 0 if passed else 1
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"{label}_NOT_VERIFIED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
