#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source-guarded, isolated guest-exit and NPDM signature experiment.

This is NOT a general loader or shutdown qualification. Exactly three
source-reviewed GPL files may change in a pinned, ephemeral Eglantine/Lichii
checkout. Keep upstream attribution; do not vendor engine source into NX2.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from engine_source_preflight import CANDIDATES, inspect, oid, git

SVC_PATH = "src/core/hle/kernel/svc/svc_process.cpp"
CLI_PATH = "src/yuzu_cmd/yuzu.cpp"
META_PATH = "src/core/file_sys/program_metadata.cpp"
META_BLOB = "464e496ea393aa31700ada21bd1409e5c770db0f"
PATCH_PATHS = (SVC_PATH, CLI_PATH, META_PATH)


class OverlayError(ValueError):
    pass


def exactly_one(source: str, old: str, new: str) -> str:
    if source.count(old) != 1 or new in source:
        raise OverlayError("Unexpected source shape or previously applied adapter")
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


def patch_metadata_magic(metadata: str) -> str:
    """Reject a non-META NPDM before reading variable header offsets."""
    original = (
        "    if (sizeof(Header) != file->ReadObject(&npdm_header)) {\n"
        "        return Loader::ResultStatus::ErrorBadNPDMHeader;\n"
        "    }\n"
    )
    checked = original + (
        "\n"
        "    if (std::memcmp(npdm_header.magic.data(), \"META\", 4) != 0) {\n"
        "        return Loader::ResultStatus::ErrorBadNPDMHeader;\n"
        "    }\n"
    )
    return exactly_one(metadata, original, checked)


def verify_applied(checkout: Path, candidate: str) -> dict:
    """Require exactly three source-pinned GPL edits and no other changes."""
    if candidate not in ("eglantine", "lichii"):
        raise OverlayError("Unsupported reviewed source revision")
    checkout = checkout.absolute()
    if not checkout.is_dir() or checkout.is_symlink():
        raise OverlayError("Expected an ordinary source checkout")
    repo, commit, blobs = CANDIDATES[candidate]
    actual_head = git(checkout, "rev-parse", "HEAD").decode().strip()
    if actual_head != commit:
        raise OverlayError("Patched checkout does not match reviewed Git commit")
    top = Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip())
    if top.resolve() != checkout.resolve():
        raise OverlayError("Expected repository root")
    origin = git(checkout, "remote", "get-url", "origin").decode().strip().removesuffix(".git")
    if origin not in (f"https://github.com/{repo}", f"git@github.com:{repo}"):
        raise OverlayError("Patched source repository origin changed")
    status = set(git(checkout, "status", "--porcelain=v1", "-z",
                     "--untracked-files=all", "--ignore-submodules=none").split(b"\0")) - {b""}
    expected_status = {b" M " + path.encode() for path in PATCH_PATHS}
    if status != expected_status:
        raise OverlayError("Patched source differs beyond the three approved files")
    original = {}
    for path, blob in ((SVC_PATH, blobs[0]), (CLI_PATH, blobs[1]),
                       (META_PATH, META_BLOB)):
        original_bytes = git(checkout, "show", f"{commit}:{path}")
        if oid(original_bytes) != blob:
            raise OverlayError("Committed source differs from reviewed Git blob")
        original[path] = original_bytes.decode("utf-8")
    expected_svc, expected_cli = patch_sources(original[SVC_PATH], original[CLI_PATH])
    expected_meta = patch_metadata_magic(original[META_PATH])
    for path, expected in ((SVC_PATH, expected_svc), (CLI_PATH, expected_cli),
                           (META_PATH, expected_meta)):
        file = checkout / path
        if file.is_symlink() or not file.is_file() or file.read_bytes() != expected.encode("utf-8"):
            raise OverlayError("Applied exit overlay bytes differ from reviewed transform")
    return {
        "kind": "nx2-reviewed-isolated-exit-and-npdm-v1",
        "repository": repo, "commit": commit,
        "source_identity_verified": True, "exactly_three_modified_source_files": True,
        "reviewed_exit_adapter_applied": True,
        "reviewed_npdm_signature_guard_applied": True,
        "emulator_runtime_qualified": False,
    }

def apply(checkout: Path, candidate: str) -> None:
    if candidate not in ("eglantine", "lichii"):
        raise OverlayError("Adapter is not reviewed for this engine")
    checkout = checkout.absolute()
    spec = CANDIDATES[candidate]
    inspect(checkout, spec)
    expected = {SVC_PATH: spec[2][0], CLI_PATH: spec[2][1],
                META_PATH: META_BLOB}
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
    meta = patch_metadata_magic(files[META_PATH])
    (checkout / SVC_PATH).write_text(svc, encoding="utf-8")
    (checkout / CLI_PATH).write_text(cli, encoding="utf-8")
    (checkout / META_PATH).write_text(meta, encoding="utf-8")
    subprocess.run(["git", "-C", str(checkout), "diff", "--check",
                    "--", *PATCH_PATHS], check=True,
                   stdout=subprocess.DEVNULL)
    verify_applied(checkout, candidate)
    print("NX2_ISOLATED_GPL_EXIT_AND_NPDM_EXPERIMENT_APPLIED candidate=" + candidate)
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
