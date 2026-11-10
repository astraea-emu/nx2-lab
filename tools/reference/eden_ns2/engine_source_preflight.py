#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only exact-source gate for pinned external emulator experiments.

A pass proves only Git source identity and selected license files. It does not
audit dependency licenses, prove runtime correctness, or authorize old overlays.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

PATHS = (
    "src/core/hle/kernel/svc/svc_process.cpp",
    "src/yuzu_cmd/yuzu.cpp",
    "src/core/loader/loader.h",
    "src/common/logging.cpp",
    "src/video_core/texture_cache/util.cpp",
)
LICENSES = {
    "LICENSE.txt": "f288702d2fa16d3cdf0035b15a9fcbc552cd88e7",
    "LICENSES/GPL-3.0-or-later.txt": "d41c0bd98feb776ef7d81efbc1b5447e0284a187",
}
CANDIDATES = {
    "eden": ("0x2593/Eden-NS2", "b2cef0c0f2e8517673233e22c929918e2c60e654", (
        "af1bdc7807e0f2c51aeee6edf1c8436b2c892bba",
        "76a1dcd312686059cf2399843a5dc15454f15526",
        "431aeace7395da49739d468dc65a76958db7865d",
        "ed12d5253244c1cd464c0a3703e62e412aeda8b6",
        "cb197563386f76c031d17382ac516fcad73196da",
    )),
    "eglantine": ("Eglantine-Community/Eglantine",
                  "78743f30c251f66bd77e6eea6c28d8632d642d6f", (
        "af1bdc7807e0f2c51aeee6edf1c8436b2c892bba",
        "bbf2776d5ead72574e3fb4f34931423ad547d1f9",
        "23be3597f5ff2bed8da7c6dd518a4973664b2a6d",
        "6815c778076cf166caac5e440587d825d1abecf5",
        "09e9513a5bb0d491fc540e3596f85244f8f8896b",
    )),
    "lichii": ("zortos293/Lichii", "7afad5494e650edfc169624be54e606f54b079ec", (
        "af1bdc7807e0f2c51aeee6edf1c8436b2c892bba",
        "e4c8a135901865bdf159d9b4e22bc29be4b8f533",
        "6bb4546cca9fcd8bb61cea836bf0b00a26b720a8",
        "994de6aefa2055a18f9ba89a29e78ebda516864d",
        "43cee9e0cef7d9d966eb49512710331b0f90ce6d",
    )),
}
SHA = re.compile(r"[a-f0-9]{40}\Z")


class PreflightError(ValueError):
    pass


def git(root: Path, *args: str) -> bytes:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "-c", "core.fsmonitor=false", *args],
            env=env, stderr=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise PreflightError("Unable to verify Git source identity") from None


def oid(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def inspect(root: Path, spec: tuple, *, license_blobs: dict | None = None) -> dict:
    repository, revision, blobs = spec
    root = root.absolute()
    if not root.is_dir() or root.is_symlink():
        raise PreflightError("Expected a non-symlink checkout")
    top = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel").strip()))
    if top.resolve() != root.resolve():
        raise PreflightError("Expected top-level Git checkout")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    if not SHA.fullmatch(head) or head != revision:
        raise PreflightError("Checkout does not match frozen commit")
    remote = git(root, "remote", "get-url", "origin").decode().strip().removesuffix(".git")
    if remote not in (f"https://github.com/{repository}", f"git@github.com:{repository}"):
        raise PreflightError("Unexpected Git remote origin")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all",
           "--ignore-submodules=none").strip():
        raise PreflightError("Source checkout is not clean")
    if len(blobs) != len(PATHS):
        raise PreflightError("Incomplete source pins")
    expected = dict(zip(PATHS, blobs))
    expected.update(LICENSES if license_blobs is None else license_blobs)
    evidence = {}
    for path, wanted in expected.items():
        if not SHA.fullmatch(wanted):
            raise PreflightError("Malformed expected blob identity")
        record = git(root, "ls-tree", "-z", "--full-tree", "HEAD", "--", path)
        parts = record.rstrip(b"\0").split(b"\t", 1)
        if len(parts) != 2 or parts[1] != path.encode():
            raise PreflightError("Missing source/license file: " + path)
        metadata = parts[0].decode().split(" ")
        if metadata != ["100644", "blob", wanted]:
            raise PreflightError("Source blob does not match reviewed pin: " + path)
        raw = git(root, "show", f"{head}:{path}")
        if len(raw) > 2_000_000 or oid(raw) != wanted:
            raise PreflightError("Source bytes do not match Git identity: " + path)
        if path in PATHS and b"SPDX-License-Identifier: GPL-3.0-or-later" not in raw[:512]:
            raise PreflightError("Critical source GPL marker absent: " + path)
        if path == "LICENSE.txt" and not raw.lstrip().startswith(b"GNU GENERAL PUBLIC LICENSE"):
            raise PreflightError("Unexpected root license")
        evidence[path] = wanted
    cli = git(root, "show", f"{head}:src/yuzu_cmd/CMakeLists.txt")
    if b"add_executable(yuzu-cmd" not in cli:
        raise PreflightError("Expected headless CLI target absent")
    baseline = CANDIDATES["eden"][2]
    return {
        "kind": "nx2-pinned-source-preflight-v1",
        "repository": repository, "commit": head,
        "verified_blob_oids": evidence,
        "different_critical_files_from_eden": [
            path for path, a, b in zip(PATHS, blobs, baseline) if a != b],
        "headless_cli_target_present": True,
        "root_gpl_license_files_verified": True,
        "complete_third_party_dependency_audit": False,
        "legacy_source_overlays_applied": False,
        "runtime_qualified": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("engine", choices=sorted(CANDIDATES))
    p.add_argument("checkout", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    try:
        result = inspect(a.checkout, CANDIDATES[a.engine])
        if a.output:
            dest = a.output.absolute()
            if dest.exists() or dest.resolve().is_relative_to(a.checkout.resolve()):
                raise PreflightError("Receipt must be new and outside source")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print("NX2_SOURCE_PREFLIGHT_PASS engine=" + a.engine)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print("NX2_SOURCE_PREFLIGHT_FAILED: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
