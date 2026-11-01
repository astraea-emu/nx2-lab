#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
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
APPLET_BLOBS = {
    "src/core/hle/service/am/event_observer.h": "c66eb711c8c898241cabc1e0b401c9a272948ddd",
    "src/core/hle/service/am/event_observer.cpp": "520000b64f224c1ca0de4e23910e94b84e524929",
    "src/core/hle/service/am/window_system.cpp": "fbb1a57efd94d01641e09079ae568e3192a4a01d",
}


def patch_sources(svc: str, frontend: str) -> tuple[str, str]:
    before_svc = "    system.Exit();\n"
    # AM requests frontend exit after the last process has terminated.
    after_svc = "    current_process->Exit(system.Kernel());\n"
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


def patch_applet_sources(header: str, observer: str, window: str) -> tuple[str, str, str]:
    """Retire process waits before pruning/restarting an applet or destroying AM."""
    updates = (
        (header, (
            ("    void TrackAppletProcess(Applet& applet);\n",
             "    void TrackAppletProcess(Applet& applet);\n"
             "    // Call on the observer thread while holding the applet lock.\n"
             "    void UntrackAppletProcess(Applet& applet);\n"),
        )),
        (observer, (
            ("    // Free remaining owned sessions.\n"
             "    auto it = m_process_holder_list.begin();\n"
             "    while (it != m_process_holder_list.end()) {\n"
             "        // Get the holder.\n"
             "        auto* const holder = std::addressof(*it);\n\n"
             "        // Remove from the list.\n"
             "        it = m_process_holder_list.erase(it);\n\n"
             "        // Free the holder.\n"
             "        delete holder;\n"
             "    }\n",
             "    // Unlink and free remaining holders after processing has stopped.\n"
             "    std::scoped_lock lk{m_lock};\n"
             "    m_wakeup_holder.UnlinkFromMultiWait();\n"
             "    while (!m_process_holder_list.empty()) {\n"
             "        this->DestroyAppletProcessHolderLocked(std::addressof(m_process_holder_list.front()));\n"
             "    }\n"),
            ("void EventObserver::RequestUpdate() {\n",
             "void EventObserver::UntrackAppletProcess(Applet& applet) {\n"
             "    std::scoped_lock lk{m_lock};\n"
             "    for (auto it = m_process_holder_list.begin(); it != m_process_holder_list.end();) {\n"
             "        auto* const holder = std::addressof(*it++);\n"
             "        if (std::addressof(holder->GetApplet()) == std::addressof(applet)) {\n"
             "            this->DestroyAppletProcessHolderLocked(holder);\n"
             "        }\n"
             "    }\n"
             "}\n\n"
             "void EventObserver::RequestUpdate() {\n"),
            ("void EventObserver::DestroyAppletProcessHolderLocked(ProcessHolder* holder) {\n",
             "void EventObserver::DestroyAppletProcessHolderLocked(ProcessHolder* holder) {\n"
             "    holder->UnlinkFromMultiWait();\n"),
        )),
        (window, (
            ("        const auto& [aruid, applet] = *it;\n",
             "        const auto [aruid, applet] = *it;\n"),
            ("        // A winding applet has had its own process killed but is kept alive as a transparent slot\n",
             "        // Retire old wait handles before removing or restarting this process.\n"
             "        m_event_observer->UntrackAppletProcess(*applet);\n"
             "        applet->is_process_running = false;\n\n"
             "        // A winding applet has had its own process killed but is kept alive as a transparent slot\n"),
        )),
    )
    patched = []
    for source, edits in updates:
        for old, new in edits:
            if source.count(old) != 1:
                raise ValueError(f"unexpected frozen AM source: {old[:70]!r}")
            source = source.replace(old, new)
        patched.append(source)
    return tuple(patched)


def apply(root: Path) -> None:
    for relative, expected in {**ORIGINAL_BLOBS, **APPLET_BLOBS}.items():
        actual = subprocess.check_output(
            ["git", "-C", str(root), "hash-object", relative], text=True).strip()
        if actual != expected:
            raise ValueError(f"frozen GPL source changed: {relative}: {actual}")
    sources = dict(zip(ORIGINAL_BLOBS, patch_sources(
        *((root / name).read_text() for name in ORIGINAL_BLOBS))))
    sources.update(zip(APPLET_BLOBS, patch_applet_sources(
        *((root / name).read_text() for name in APPLET_BLOBS))))
    for name, source in sources.items():
        (root / name).write_text(source)
    subprocess.run(["git", "-C", str(root), "diff", "--check"], check=True)
    subprocess.run(["git", "-C", str(root), "diff", "--stat", "--",
                    *ORIGINAL_BLOBS, *APPLET_BLOBS], check=True)
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
