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

from assess_native_frame import CAPTURED, CAPTURE_SIZE, assess, verify_pixels
from assess_native_ipc import BOUNDARY, MAX_LOG_SIZE
from build_native_engine import EDEN_REVISIONS, EDEN_SHA, build_engine, digest

ROOT = Path(__file__).resolve().parent
CONFIG = "[Renderer]\n" + "".join(
    f"{key}={value}\n{key}\\default=false\n" for key, value in (
        ("backend", 1), ("vulkan_device", 0), ("resolution_setup", 3),
        ("scaling_filter", 0), ("anti_aliasing", 0), ("aspect_ratio", 0)))
GPU_CONFIG = CONFIG + "".join(
    f"{key}={value}\n{key}\\default=false\n" for key, value in (
        ("gpu_accuracy", 1), ("gpu_fence_behavior", 3),
        ("use_asynchronous_shaders", "false"))) + (
    "[Miscellaneous]\nlog_filter=*:Info HW.GPU:Debug Service.NVDRV:Debug Shader:Debug\n"
    "log_filter\\default=false\n")
ANIMATION_CONFIG = GPU_CONFIG.replace("Service.NVDRV:Debug", "Service.NVDRV:Debug Service.AM:Debug")
FLUSH_CONFIG = "flush_line=true\nflush_line\\default=false\n"


def read_capped(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        return stream.read(maximum + 1)


def verify_shader_inputs(directory: Path, variant: int, clear_only: bool, *,
                         animation: bool = False) -> bool:
    """Bind the engine's observed native shader pages to the original inputs."""
    from native_gpu_commands import FS_OFFSET, VERTEX_OFFSET, VS_OFFSET, build_gpu_buffer
    snapshots = {p.name: p for p in directory.glob("native-graphics-shader-*.bin")}
    if clear_only:
        return not snapshots
    # The animation edit changes vertices while keeping the original shaders.
    inputs = build_gpu_buffer(0 if animation else variant)
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


class AnimationCaptures:
    """Archive completed readbacks before arming the next on-demand capture."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.offset = 0
        self.pending = b""
        self.events: list[dict] = []
        self.error: str | None = None

    def poll(self) -> None:
        if self.error is not None:
            return
        try:
            with (self.directory / "runtime.log").open("rb") as stream:
                stream.seek(self.offset)
                raw = stream.read(MAX_LOG_SIZE + 1 - self.offset)
            self.offset += len(raw)
            if self.offset > MAX_LOG_SIZE:
                raise ValueError("animation runtime log exceeds the input limit")
            lines = (self.pending + raw).split(b"\n")
            self.pending = lines.pop()
            for raw_line in lines:
                line = BOUNDARY.sub("", raw_line.decode("utf-8", "replace").removesuffix("\r"))
                if not CAPTURED.fullmatch(line):
                    continue
                frame = len(self.events)
                if frame >= 4:
                    raise ValueError("animation produced more than four capture callbacks")
                source = self.directory / "native-latest-frame.tga"
                if source.is_symlink() or not source.is_file():
                    raise ValueError("saved animation capture is missing or is a symlink")
                pixels = read_capped(source, CAPTURE_SIZE)
                if len(pixels) != CAPTURE_SIZE:
                    raise ValueError("saved animation capture has an unexpected size")
                destination = self.directory / f"frame-{frame}.tga"
                with destination.open("xb") as output:
                    output.write(pixels)
                self.events.append({"frame": frame, "capture": destination.name,
                                    "sha256": digest(destination), "callback": line})
                if frame < 3:
                    # The callback follows file close; no further capture can
                    # overwrite it until this newly armed request is consumed.
                    with (self.directory / "native-frame.request").open("x") as request:
                        request.write(f"NX2 original animation frame {frame + 1}\n")
        except (OSError, ValueError) as error:
            self.error = str(error)


def run_x11(command: list[str], directory: Path, env: dict[str, str],
            log_name: str, seconds: int, *, captures: AnimationCaptures | None = None) -> tuple[int, float]:
    """Run one bounded process and preserve its complete output and return code."""
    started = time.monotonic()
    argv = ["xvfb-run", "-a", "-e", str(directory / (log_name + ".xvfb")),
            "-s", "-screen 0 1920x1080x24 -nolisten tcp", "timeout",
            "--signal=TERM", "--kill-after=4s", str(seconds) + "s", *command]
    with (directory / log_name).open("wb") as output:
        with subprocess.Popen(argv, cwd=directory, env=env, stdout=output,
                              stderr=subprocess.STDOUT) as process:
            while process.poll() is None:
                if captures is not None:
                    captures.poll()
                try:
                    process.wait(timeout=0.02 if captures is not None else 1)
                except subprocess.TimeoutExpired:
                    pass
            if captures is not None:
                captures.poll()
    return process.returncode, time.monotonic() - started


def trial(cli: Path, output: Path, icd: Path, prefix: str, variant: int, *,
          gpu: bool = False, clear_only: bool = False, animation: bool = False,
          eden_revision: str = EDEN_SHA) -> dict:
    if animation and (not gpu or clear_only):
        raise ValueError("animation requires GPU work and cannot be clear-only")
    directory = output / ("clear-only" if clear_only else f"variant-{variant}")
    directory.mkdir()
    guest = directory / "guest"
    assembled = time.monotonic()
    arguments = (["--gpu-animation"] if animation else ["--gpu-triangle"] if gpu else [])
    arguments += ["--clear-only"] if clear_only else []
    with (directory / "fixture.log").open("wb") as log:
        subprocess.run([sys.executable, str(ROOT / "make_native_frame_exefs.py"),
                        "--output", str(guest), "--tool-prefix", prefix,
                        "--variant", str(variant), *arguments], stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    assemble_seconds = time.monotonic() - assembled
    config = directory / "config.ini"
    config.write_text((ANIMATION_CONFIG if animation else GPU_CONFIG if gpu else
                       CONFIG + "[Miscellaneous]\n") + FLUSH_CONFIG)
    capture = directory / "native-latest-frame.tga"
    request = directory / "native-frame.request"
    if capture.exists() or request.exists():
        raise ValueError("frame trial must start without a capture or request")
    # The compositor only captures newly acquired buffers. Arm before the single
    # presentation; real saved-capture ordering and every pixel are checked below.
    request.write_text("NX2 original image capture\n")
    captures = AnimationCaptures(directory) if animation else None
    command = ["stdbuf", "-oL", "-eL", str(cli), "--config", str(config),
               "--singlecore", "--game", str(guest / "main")]
    with tempfile.TemporaryDirectory(prefix="nx2-frame-home-") as temporary:
        env = vulkan_environment(Path(temporary), icd, gpu=gpu)
        rc, runtime_seconds = run_x11(
            command, directory, env, "runtime.log", 60 if animation else 30, captures=captures)
        engine_log = Path(temporary) / "data/eden/log/eden_log.txt"
        if engine_log.is_file() and not engine_log.is_symlink():
            (directory / "engine.log").write_bytes(read_capped(engine_log, MAX_LOG_SIZE))
    raw = read_capped(directory / "runtime.log", MAX_LOG_SIZE)
    pixels = (read_capped(capture, CAPTURE_SIZE) if capture.is_file() and not capture.is_symlink()
              and capture.stat().st_size == CAPTURE_SIZE else b"")
    report = io.StringIO()
    with contextlib.redirect_stdout(report):
        if animation:
            from assess_native_gpu_frame import assess_animation
            frames = tuple(read_capped(directory / f"frame-{i}.tga", CAPTURE_SIZE)
                           for i in range(len(captures.events)))
            verified = assess_animation(raw, rc, frames, variant, eden_revision=eden_revision)
            shaders_match = verify_shader_inputs(directory, variant, False, animation=True)
            print(f"NX2_GPU_OBSERVED_SHADER_INPUTS_MATCH={int(shaders_match)}")
            print(f"NX2_ANIMATION_CAPTURE_ARCHIVE_OK={int(captures.error is None and len(frames) == 4)}")
            if captures.error is not None:
                print(f"NX2_ANIMATION_CAPTURE_ERROR={captures.error}")
            verified = verified and shaders_match and captures.error is None and len(frames) == 4
        elif gpu:
            from assess_native_gpu_frame import assess as assess_gpu
            verified = assess_gpu(raw, rc, pixels, variant, clear_only=clear_only,
                                  eden_revision=eden_revision)
            shaders_match = verify_shader_inputs(directory, variant, clear_only)
            print(f"NX2_GPU_OBSERVED_SHADER_INPUTS_MATCH={int(shaders_match)}")
            verified = verified and shaders_match
        else:
            verified = assess(raw, rc, pixels, variant)
    (directory / "assessment.log").write_text(report.getvalue())
    print(report.getvalue(), end="", flush=True)
    consumed = not request.exists()
    files = (guest / "main", guest / "main.npdm", directory / "runtime.log",
             directory / "assessment.log", directory / "engine.log", config, capture)
    if animation:
        archive = directory / "capture-events.json"
        archive.write_text(json.dumps({"events": captures.events, "error": captures.error}, indent=2) + "\n")
        files += (archive, *(directory / event["capture"] for event in captures.events))
    if gpu:
        files += tuple(directory / name for name in ("native-graphics-registers.bin",
                       "native-graphics-shader-1.bin", "native-graphics-shader-5.bin"))
    result = {"eden_revision": eden_revision, "variant": variant,
              "process_rc": rc, "verified": verified and consumed,
              "workload": "gpu-animation" if animation else "gpu-clear" if clear_only else "gpu-triangle" if gpu else "cpu-image",
              "command": command,
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
    parser.add_argument("--eden-revision", choices=EDEN_REVISIONS, default=EDEN_SHA)
    parser.add_argument("--output", type=Path, default=Path("build/native-frame"))
    parser.add_argument("--icd", type=Path, help="Lavapipe ICD JSON; otherwise discover installed lvp manifest")
    parser.add_argument("--tool-prefix", default=os.environ.get("NX2_AARCH64_PREFIX", "aarch64-linux-gnu-"))
    parser.add_argument("--variant", type=int, choices=(0, 1), default=0)
    parser.add_argument("--both", action="store_true", help="also prove that the changed guest produces its different image")
    workload = parser.add_mutually_exclusive_group()
    workload.add_argument("--gpu-triangle", action="store_true",
                          help="render original guest shaders and include a clear-only negative control")
    workload.add_argument("--gpu-animation", action="store_true",
                          help="render four original frames with two reused display buffers")
    args = parser.parse_args()
    gpu = args.gpu_triangle or args.gpu_animation
    label = ("NX2_ORIGINAL_GPU_ANIMATION" if args.gpu_animation else
             "NX2_ORIGINAL_GPU_TRIANGLE" if gpu else "NX2_ORIGINAL_FRAME")
    try:
        for name in ("git", "xvfb-run", "xauth", "timeout", "stdbuf", "vulkaninfo",
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
        source, cli, engine = build_engine(args.engine_dir, eden_revision=args.eden_revision)
        prepare_seconds = time.monotonic() - preparing
        sources = (ROOT / "native_frame_probe.S", ROOT / "native_frame_probe.ld",
                   ROOT / "make_native_frame_exefs.py", Path(__file__),
                   ROOT / "assess_native_frame.py", ROOT / "build_native_engine.py")
        if gpu:
            sources += tuple(ROOT / name for name in ("native_gpu_probe.S", "native_gpu_probe.ld",
                             "native_gpu_commands.py", "assess_native_gpu_frame.py"))
        provenance = {"eden_revision": args.eden_revision, "eden_cli_sha256": digest(cli),
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
        results = [trial(cli, output, icd, args.tool_prefix, variant, gpu=gpu,
                         animation=args.gpu_animation,
                         eden_revision=args.eden_revision)
                   for variant in variants]
        if args.gpu_triangle:
            results.append(trial(cli, output, icd, args.tool_prefix, 0, gpu=True, clear_only=True,
                                 eden_revision=args.eden_revision))
        passed = all(result["verified"] for result in results)
        pixel_check = verify_pixels
        if args.gpu_triangle:
            from assess_native_gpu_frame import verify_pixels as pixel_check
        if args.gpu_animation and args.both and passed:
            from assess_native_gpu_frame import verify_animation_pixels
            a = tuple(read_capped(output / "variant-0" / f"frame-{i}.tga", CAPTURE_SIZE)
                      for i in range(4))
            b = tuple(read_capped(output / "variant-1" / f"frame-{i}.tga", CAPTURE_SIZE)
                      for i in range(4))
            with contextlib.redirect_stdout(io.StringIO()):
                changed = (a != b and
                           not all(verify_animation_pixels(frame, 0, i) for i, frame in enumerate(b)) and
                           not all(verify_animation_pixels(frame, 1, i) for i, frame in enumerate(a)))
            print(f"NX2_ANIMATION_VERTEX_EDIT_CHANGES_MOTION={int(changed)}")
            passed = passed and changed
        elif args.both and passed:
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
                   "eden_revision": args.eden_revision,
                   "workload": "gpu-animation" if args.gpu_animation else "gpu-triangle" if gpu else "cpu-image",
                   "eden_cli_sha256": provenance["eden_cli_sha256"],
                   "engine_reused": engine["reused"],
                   "engine_prepare_seconds": round(prepare_seconds, 3),
                   "total_seconds": round(time.monotonic() - started, 3),
                   "variants": [{"variant": result["variant"],
                                 "workload": result["workload"],
                                 "process_rc": result["process_rc"],
                                 "main_sha256": result["files"]["main"],
                                 "npdm_sha256": result["files"]["main.npdm"],
                                 "capture_sha256": result["files"].get("native-latest-frame.tga"),
                                 **({"frame_sha256": [result["files"].get(f"frame-{i}.tga")
                                                     for i in range(4)]} if args.gpu_animation else {})}
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
