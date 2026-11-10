#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source-built candidate smoke: execute only NX2's original ExeFS fixture.

A changed CLI log format is an adapter result, not proof of an emulator defect.
No raw host logs, firmware, keys, SDKs or games leave the ephemeral runner.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

import assess_native_exefs as exefs
from engine_source_preflight import CANDIDATES, inspect
from modern_exit_overlay import verify_applied

MAIN_SHA = "508edcf6870546ed2f67c6ed11f0df3deb0242427ea2b9d7562ae6d015084ed5"
NPDM_SHA = "64e25a2e3e37495d75341f9564afa3e6a665f10f94b36ea7e4e3c533b4573148"


def require(value: bool, reason: str) -> None:
    if not value:
        raise ValueError(reason)


def fixture_pair(valid: Path, invalid: Path) -> dict:
    require(valid.is_dir() and invalid.is_dir() and valid.resolve() != invalid.resolve(),
            "Expected separate original guest fixture directories")
    def bounded(path: Path) -> bytes:
        require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 131072,
                "Invalid bounded original guest file")
        return path.read_bytes()
    main = bounded(valid / "main")
    altered_main = bounded(invalid / "main")
    meta = bounded(valid / "main.npdm")
    altered_meta = bounded(invalid / "main.npdm")
    require(main == altered_main and hashlib.sha256(main).hexdigest() == MAIN_SHA,
            "Guest program differs from frozen NX2 input")
    require(hashlib.sha256(meta).hexdigest() == NPDM_SHA and meta[:4] == b"META",
            "Original NPDM differs from frozen NX2 input")
    require(len(meta) == len(altered_meta) and altered_meta == b"NX2!" + meta[4:],
            "Malformed control must change only META magic")
    return {"main_sha256": MAIN_SHA, "valid_npdm_sha256": NPDM_SHA,
            "invalid_npdm_sha256": hashlib.sha256(altered_meta).hexdigest()}


def built_cli(checkout: Path, build: Path) -> tuple[Path, str]:
    require(build.is_dir() and not build.is_symlink() and
            not build.resolve().is_relative_to(checkout.resolve()),
            "Expected a separate out-of-tree source build")
    cli = build.resolve() / "bin/eden-cli"
    require(cli.is_file() and not cli.is_symlink() and os.access(cli, os.X_OK),
            "Missing source-built candidate CLI")
    cache = build / "CMakeCache.txt"
    require(cache.is_file() and cache.stat().st_size < 2_000_000,
            "Missing bounded source-build cache")
    values = {}
    for line in cache.read_text(errors="replace").splitlines():
        if line.startswith(("#", "//")) or "=" not in line or ":" not in line:
            continue
        left, value = line.split("=", 1)
        name = left.split(":", 1)[0]
        require(name not in values, "Duplicate source-build parameter")
        values[name] = value
    require(values.get("CMAKE_HOME_DIRECTORY") == str(checkout.resolve()) and
            values.get("CMAKE_BUILD_TYPE") == "Release" and
            values.get("YUZU_CMD") == "ON" and values.get("ENABLE_QT") == "OFF",
            "Candidate CLI build does not match declared source")
    digest = hashlib.sha256()
    with cli.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return cli, digest.hexdigest()


def run(cli: Path, guest: Path | None, directory: Path, seconds: int) -> tuple[int, bytes, float]:
    directory.mkdir()
    home = directory / "home"
    home.mkdir()
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH")
           if key in os.environ}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / "config"),
               XDG_DATA_HOME=str(home / "data"), XDG_CACHE_HOME=str(home / "cache"),
               SDL_AUDIODRIVER="dummy")
    command = ["xvfb-run", "-a", "-e", str(directory / "xvfb.log"), "-s",
               "-screen 0 1280x720x24 -nolisten tcp", "timeout",
               "--signal=TERM", "--kill-after=4s", f"{seconds}s",
               str(cli)]
    command += ["--help"] if guest is None else [
        "--null-render", "--singlecore", "--game", str(guest / "main")]
    log = directory / "runtime.log"
    start = time.monotonic()
    with log.open("wb") as output:
        process = subprocess.Popen(command, cwd=directory, env=env,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            rc = process.wait(timeout=seconds + 12)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            rc = process.wait()
    require(log.stat().st_size <= exefs.MAX_LOG_SIZE, "Host log exceeds bounded inspection limit")
    return rc, log.read_bytes(), round(time.monotonic() - start, 3)


# Deliberately allowlisted *classes*, not copied host log messages.
# Never persist raw frontend, guest or environment-derived diagnostics.
LOG_CATEGORIES = (
    ("guest_layout", exefs.CLASSIFIED),
    ("original_guest_debug", exefs.GUEST_OUTPUT),
    ("guest_exit", exefs.GUEST_EXIT),
    ("invalid_meta_loader", exefs.NPDM_FAILURE),
    ("invalid_meta_frontend", exefs.FRONTEND_LOADER_FAILURE),
)
SOURCE_STAGE = (
    ("frontend", re.compile(r"\bFrontend <(?:Info|Warning|Error|Critical)> ")),
    ("network", re.compile(r"\bNetwork <(?:Info|Warning|Error|Critical)> ")),
    ("core", re.compile(r"\bCore <(?:Info|Warning|Error|Critical)> ")),
    ("kernel", re.compile(r"\bKernel\.[^ ]+ <(?:Info|Warning|Error|Critical)> ")),
    ("guest_debug", re.compile(r"\bDebug\.Emulated <(?:Info|Warning|Error|Critical)> ")),
    ("gpu", re.compile(r"\b(?:Render|VideoCore|HW\.GPU)[^ ]* <(?:Info|Warning|Error|Critical)> ")),
)


# Do not persist host messages or paths. This taxonomy is diagnostic only:
# strict source-attributed execution-failure checks remain unchanged.
FAULT_SIGNATURES = (
    ("assertion", re.compile(r"\\bassert(?:ion)?\\b", re.IGNORECASE)),
    ("guest_exception", re.compile(r"ExceptionRaised", re.IGNORECASE)),
    ("unmapped_instruction", re.compile(
        r"Cannot execute instruction at unmapped address", re.IGNORECASE)),
    ("segmentation_fault", re.compile(r"Segmentation fault", re.IGNORECASE)),
    ("aborted", re.compile(r"\\bAborted\\b", re.IGNORECASE)),
    ("address_sanitizer", re.compile(r"AddressSanitizer", re.IGNORECASE)),
    ("undefined_behavior_sanitizer", re.compile(r"UndefinedBehaviorSanitizer", re.IGNORECASE)),
    ("runtime_error", re.compile(r"runtime error:", re.IGNORECASE)),
)


def fault_signatures(lines: list[str]) -> dict:
    """Return only allowlisted class and subsystem counts, never source text."""
    classes = {name: 0 for name, _ in FAULT_SIGNATURES}
    stages = {name: 0 for name, _ in SOURCE_STAGE}
    stages["unclassified"] = 0
    for line in lines:
        matched = [name for name, pattern in FAULT_SIGNATURES if pattern.search(line)]
        if not matched:
            continue
        stage = next((name for name, pattern in SOURCE_STAGE
                      if pattern.search(line)), "unclassified")
        stages[stage] = min(stages[stage] + 1, 100000)
        for name in matched:
            classes[name] = min(classes[name] + 1, 100000)
    return {"categories": classes, "source_stages": stages}


def lifecycle(raw: bytes) -> dict:
    """Lossy, redacted milestones for the first real modern-engine execution.

    A count/last-stage hint is not a fault attribution or a compatibility pass.
    """
    lines = exefs.source_lines(raw)
    category_counts = {name: sum(bool(pattern.fullmatch(line)) for line in lines)
                       for name, pattern in LOG_CATEGORIES}
    stage_counts = {name: 0 for name, _ in SOURCE_STAGE}
    first_stage = last_stage = "unclassified"
    for line in lines:
        stage = next((name for name, pattern in SOURCE_STAGE if pattern.search(line)), None)
        if stage:
            stage_counts[stage] = min(stage_counts[stage] + 1, 100000)
            if first_stage == "unclassified":
                first_stage = stage
            last_stage = stage
    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "line_count": min(len(lines), 1000000),
        "nul_bytes": min(raw.count(b"\0"), 1000000),
        "milestones": category_counts,
        "source_stage_counts": stage_counts,
        "first_source_stage": first_stage,
        "last_source_stage": last_stage,
        "fault_signature_seen": bool(exefs.EXECUTION_FAILURE.search(
            exefs.normalize(raw))),
        "fault_signature_evidence": fault_signatures(lines),
        "raw_lines_preserved": False,
    }


def assess_silently(good: bytes, bad: bytes, good_rc: int, bad_rc: int) -> dict:
    with contextlib.redirect_stdout(io.StringIO()):
        accepted = exefs.assess(good, bad, good_rc, bad_rc)
    lines = exefs.source_lines(good)
    count = lambda pattern: sum(bool(pattern.fullmatch(line)) for line in lines)
    classification = count(exefs.CLASSIFIED)
    debug = count(exefs.GUEST_OUTPUT)
    exit_svc = count(exefs.GUEST_EXIT)
    bad_lines = exefs.source_lines(bad)
    negative_guest_debug = sum(bool(exefs.ANY_GUEST_OUTPUT.fullmatch(line)) for line in bad_lines)
    negative_guest_svc = sum(bool(exefs.ANY_GUEST_SVC.fullmatch(line)) for line in bad_lines)
    negative = exefs.expected_npdm_rejection(bad)
    if good_rc in (124, 137, -9):
        first = "host_did_not_exit_naturally"
    elif classification != 1:
        first = "guest_layout_log_not_attributed"
    elif debug != 1:
        first = "original_debug_svc_not_attributed"
    elif exit_svc != 1:
        first = "guest_exit_svc_not_attributed"
    elif good_rc != 0:
        first = "guest_exit_observed_but_host_exit_nonzero"
    elif negative_guest_debug or negative_guest_svc:
        first = "negative_control_guest_executed"
    elif not negative:
        first = "negative_loader_diagnostic_not_attributed"
    elif bad_rc != 1:
        first = "negative_loader_exit_mismatch"
    elif exefs.EXECUTION_FAILURE.search(exefs.normalize(good)):
        first = "positive_execution_fault_signature_observed"
    elif exefs.EXECUTION_FAILURE.search(exefs.normalize(bad)):
        first = "negative_execution_fault_signature_observed"
    elif not accepted:
        first = "strict_assessor_or_negative_control_rejected"
    else:
        first = "original_exefs_controls_passed"
    return {"original_controls_pass": accepted, "first_stop": first,
            "layout_records": classification, "original_debug_svc_records": debug,
            "exit_svc_records": exit_svc, "negative_meta_diagnostic": negative,
            "negative_guest_debug_records": negative_guest_debug,
            "negative_guest_kernel_svc_records": negative_guest_svc,
            "positive_rc": good_rc, "negative_rc": bad_rc,
            "positive_lifecycle": lifecycle(good),
            "negative_lifecycle": lifecycle(bad),
            "log_adapter_or_runtime_unverified_if_failed": not accepted}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("candidate", choices=("eglantine", "lichii"))
    p.add_argument("checkout", type=Path)
    p.add_argument("build", type=Path)
    p.add_argument("valid", type=Path)
    p.add_argument("invalid", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seconds", type=int, default=30)
    p.add_argument("--reviewed-exit-adapter", action="store_true",
                   help="require exactly the source-verified, isolated GPL guest-exit patch")
    a = p.parse_args()
    try:
        require(5 <= a.seconds <= 120 and not a.output.exists(),
                "Require a fresh receipt and a 5-120 second bound")
        require(not a.output.resolve().is_relative_to(a.checkout.resolve()),
                "Output cannot change source")
        check_source = (lambda: verify_applied(a.checkout, a.candidate)) if a.reviewed_exit_adapter else (lambda: inspect(a.checkout, CANDIDATES[a.candidate]))
        original = check_source()
        inputs = fixture_pair(a.valid, a.invalid)
        cli, cli_hash = built_cli(a.checkout, a.build)
        with tempfile.TemporaryDirectory(prefix="nx2-original-exefs-") as temp:
            root = Path(temp)
            help_rc, help_log, help_time = run(cli, None, root / "help", 10)
            good_rc, good, good_time = run(cli, a.valid.resolve(), root / "valid", a.seconds)
            bad_rc, bad, bad_time = run(cli, a.invalid.resolve(), root / "invalid", a.seconds)
        result = assess_silently(good, bad, good_rc, bad_rc)
        require(check_source() == original,
                "Source changed during experiment")
        receipt = {"candidate": a.candidate, "commit": original["commit"],
                   "source_identity_verified": True, "cli_sha256": cli_hash,
                   "original_guest": inputs, "assessment": result,
                   "seconds": {"help": help_time, "valid": good_time, "invalid": bad_time},
                   "frontend_help": {"rc": help_rc, "lifecycle": lifecycle(help_log),
                                     "natural_exit": help_rc == 0},
                   "raw_logs_retained": False,
                   "reviewed_exit_adapter_applied": a.reviewed_exit_adapter,
                   "reviewed_npdm_signature_guard_applied": a.reviewed_exit_adapter,
                   "game_compatibility_qualified": False}
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        print("NX2_FRONTEND_HELP=" + ("PASS" if help_rc == 0 else "NOT_VERIFIED") +
              " candidate=" + a.candidate)
        print("NX2_ORIGINAL_EXEFS_" +
              ("PASS" if result["original_controls_pass"] else "NOT_VERIFIED") +
              " candidate=" + a.candidate + " first_stop=" + result["first_stop"])
        return 0 if result["original_controls_pass"] else 1
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("NX2_ORIGINAL_EXEFS_UNAVAILABLE: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
