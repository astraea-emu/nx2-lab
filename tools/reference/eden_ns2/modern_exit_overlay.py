#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source-guarded, isolated experiment for original ARM64 guest ExitProcess.

This is NOT a fix for modern-engine loader failures or a qualified shutdown.
Only the two reviewed files of an exact, clean Eglantine/Lichii checkout
may be altered; retain all upstream GPL notices and do not vendor engine code.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from engine_source_preflight import CANDIDATES, inspect, oid

SVC_PATH = "src/core/hle/kernel/svc/svc_process.cpp"
CLI_PATH = "src/yuzu_cmd/yuzu.cpp"


class OverlayError(ValueError):
    pass


def exactly_one(source: str, old: str, new: str) -> str:
    if source.count(old) != 1 or new in source:
        raise OverlayError("Unexpected source shape or previously applied exit adapter")
    return source.replace(old, new)


def patch_sources(svc: str, frontend: str) -> tuple[str, str]:
    """Patch only shared, source-reviewed guest-exit and SDL loop sites."""
    if "current_process->GetState() == KProcess::State::Running" not in svc:
        raise OverlayError("ExitProcess state guard differs from reviewed source")
    if frontend.count("#include <atomic>") != 1 or (
        frontend.count("    if (state->system.IsPoweredOn()) {") != 1
    ):
        raise OverlayError("Modern frontend atomic support or shutdown guard differs")
    if "guest_exit_requested" in svc or "guest_exit_requested" in frontend:
        raise OverlayError("An exit adapter may already be present")
    svc = exactly_one(
        svc, "    system.Exit();\n",
        "    system.Exit();\n    current_process->Exit(system.Kernel());\n")
    frontend = exactly_one(
        frontend, "    Core::System system{};\n",
        "    Core::System system{};\n"
        "    std::atomic_bool guest_exit_requested{false};\n")
    frontend = exactly_one(
        frontend, "    state->system.RegisterExitCallback([] {});\n",
        "    state->system.RegisterExitCallback([state] {\n"
        "        state->guest_exit_requested.store(true, std::memory_order_release);\n"
        "    });\n")
    frontend = exactly_one(
        frontend,
        "    return state->emu_window && state->emu_window->IsOpen() ? SDL_APP_CONTINUE : SDL_APP_SUCCESS;\n",
        "    if (state->guest_exit_requested.load(std::memory_order_acquire)) {\n"
        "        return SDL_APP_SUCCESS;\n"
        "    }\n"
        "    return state->emu_window && state->emu_window->IsOpen() ? SDL_APP_CONTINUE : SDL_APP_SUCCESS;\n")
    return svc, frontend


def apply(checkout: Path, candidate: str) -> None:
    if candidate not in ("eglantine", "lichii"):
        raise OverlayError("Adapter is not reviewed for this engine")
    checkout = checkout.absolute()
    spec = CANDIDATES[candidate]
    inspect(checkout, spec)
    expected = dict(zip((
        SVC_PATH, CLI_PATH,
    ), (spec[2][0], spec[2][1])))
    files = {}
    for path, blob in expected.items():
        file = checkout / path
        if file.is_symlink() or not file.is_file():
            raise OverlayError("Unsafe source file type")
        raw = file.read_bytes()
        if oid(raw) != blob:
            raise OverlayError("Checked-out source differs from the reviewed blob")
        files[path] = raw.decode("utf-8")
    svc, cli = patch_sources(files[SVC_PATH], files[CLI_PATH])
    (checkout / SVC_PATH).write_text(svc, encoding="utf-8")
    (checkout / CLI_PATH).write_text(cli, encoding="utf-8")
    subprocess.run(["git", "-C", str(checkout), "diff", "--check",
                    "--", SVC_PATH, CLI_PATH], check=True,
                   stdout=subprocess.DEVNULL)
    print("NX2_ISOLATED_GPL_GUEST_EXIT_EXPERIMENT_APPLIED candidate=" + candidate)
    print("NX2_ADAPTER_IS_NOT_RUNTIME_OR_SHUTDOWN_QUALIFICATION")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", choices=("eglantine", "lichii"))
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    try:
        apply(args.checkout, args.candidate)
        return 0
    except (OverlayError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("NX2_MODERN_EXIT_EXPERIMENT_REFUSED: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
