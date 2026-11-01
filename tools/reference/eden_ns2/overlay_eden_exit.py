#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Earlier MIT-licensed material retains that permission; see LICENSES/MIT.txt.
"""Apply explicitly audited GPL-side Eden process-exit/SDL lifecycle experiment.

Keep modified external Eden source in its separate, source-pinned checkout.
This applies only to the pinned GPL checkout in an ephemeral CI runner.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

ORIGINAL_BLOBS = {
    "src/core/hle/kernel/svc/svc_process.cpp": "af1bdc7807e0f2c51aeee6edf1c8436b2c892bba",
    "src/yuzu_cmd/yuzu.cpp": "76a1dcd312686059cf2399843a5dc15454f15526",
}


def patch_sources(svc: str, frontend: str) -> tuple[str, str]:
    before_svc = "    system.Exit();\n"
    after_svc = "    system.Exit();\n    current_process->Exit(system.Kernel());\n"
    if svc.count(before_svc) != 1 or "current_process->GetState() == KProcess::State::Running" not in svc:
        raise ValueError("unexpected frozen ExitProcess implementation")
    svc = svc.replace(before_svc, after_svc)

    updates = (
        ("#include <cstdio>", "#include <atomic>\n#include <cstdio>"),
        ("    Core::System system{};\n", "    Core::System system{};\n    std::atomic_bool guest_exit_requested{false};\n"),
        ("    state->system.RegisterExitCallback([] {});\n",
         "    state->system.RegisterExitCallback([state] {\n"
         "        state->guest_exit_requested.store(true, std::memory_order_release);\n"
         "    });\n"),
        ("    return state->emu_window->IsOpen() ? SDL_APP_CONTINUE : SDL_APP_SUCCESS;\n",
         "    if (state->guest_exit_requested.load(std::memory_order_acquire)) {\n"
         "        return SDL_APP_SUCCESS;\n"
         "    }\n"
         "    return state->emu_window->IsOpen() ? SDL_APP_CONTINUE : SDL_APP_SUCCESS;\n"),
        ("    void(state->system.Pause());\n    state->system.ShutdownMainProcess();\n",
         "    // A rejected image has not powered up the application process.\n"
         "    if (state->system.IsPoweredOn()) {\n"
         "        void(state->system.Pause());\n"
         "        state->system.ShutdownMainProcess();\n"
         "    }\n"),
    )
    for old, new in updates:
        if frontend.count(old) != 1:
            raise ValueError(f"unexpected frozen SDL frontend source: {old[:70]!r}")
        frontend = frontend.replace(old, new)
    return svc, frontend


def apply(root: Path) -> None:
    for relative, expected in ORIGINAL_BLOBS.items():
        actual = subprocess.check_output(
            ["git", "-C", str(root), "hash-object", relative], text=True).strip()
        if actual != expected:
            raise ValueError(f"frozen GPL source changed: {relative}: {actual}")
    svcpath, frontpath = (root / x for x in ORIGINAL_BLOBS)
    svc, frontend = patch_sources(svcpath.read_text(), frontpath.read_text())
    svcpath.write_text(svc)
    frontpath.write_text(frontend)
    subprocess.run(["git", "-C", str(root), "diff", "--check"], check=True)
    subprocess.run(["git", "-C", str(root), "diff", "--stat", "--",
                    *ORIGINAL_BLOBS], check=True)
    print("NX2_EDEN_ISOLATED_GPL_PROCESS_EXIT_OVERLAY_APPLIED")
    print("NX2_EDEN_ORIGINAL_SOURCE_IS_UNMODIFIED_IN_NX2_REPOSITORY=1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eden_checkout", type=Path)
    args = parser.parse_args()
    apply(args.eden_checkout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
