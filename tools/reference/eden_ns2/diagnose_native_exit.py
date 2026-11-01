#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Temporary diagnostic for the post-merge native guest exit hang; do not merge."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import re
import shutil
import signal
import struct
import subprocess
import time

import run_native_frame as runner
from build_native_engine import BASELINE_SHA, build_engine, digest

FILE_LIMIT = 16 * 1024 * 1024
TRACE_LIMIT = 2 * 1024 * 1024
ARTIFACT_LIMIT = 768 * 1024 * 1024


def engine_descendants(parent: int, executable: Path) -> list[int]:
    """Only inspect the launched process tree, then verify its executable link."""
    children: dict[int, list[int]] = {}
    entries = [p for p in Path("/proc").iterdir() if p.name.isdigit()]
    if len(entries) > 4096:
        raise RuntimeError("process inventory exceeds its diagnostic bound")
    for entry in entries:
        try:
            # /proc/PID/task/PID/children is optional in Linux configurations.
            fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
            children.setdefault(int(fields[1]), []).append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    pending, visited, matches = [parent], set(), []
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        if len(visited) > 512:
            raise RuntimeError("diagnostic process tree exceeds its bound")
        pending.extend(children.get(pid, ()))
        try:
            if Path(f"/proc/{pid}/exe").resolve(strict=True) == executable:
                matches.append(pid)
        except (FileNotFoundError, ProcessLookupError):
            continue
    return matches


def capture_process_state(pid: int, executable: Path, directory: Path, env: dict[str, str]) -> dict:
    """Retain non-ptrace evidence before a debugger might stall on a core dump."""
    process = Path(f"/proc/{pid}")
    if (process / "exe").resolve(strict=True) != executable:
        raise RuntimeError("diagnostic target changed before process snapshot")
    result = {}
    for name in ("maps", "status", "limits"):
        raw = runner.read_capped(process / name, 1024 * 1024)
        if len(raw) > 1024 * 1024:
            raise RuntimeError("process snapshot exceeds its bound")
        target = directory / ("proc-" + name + ".txt")
        target.write_bytes(raw)
        result[name] = {"sha256": digest(target), "bytes": len(raw)}
    tasks = sorted((process / "task").iterdir(), key=lambda p: int(p.name))
    if len(tasks) > 512:
        raise RuntimeError("thread inventory exceeds its diagnostic bound")
    states = []
    for task in tasks:
        try:
            states.append({"tid": int(task.name),
                           "status": runner.read_capped(task / "status", 8192).decode(),
                           "wchan": runner.read_capped(task / "wchan", 256).decode()})
        except FileNotFoundError:
            continue
    (directory / "proc-threads.json").write_text(json.dumps(states, indent=2) + "\n")
    source = Path(env["XDG_DATA_HOME"]) / "eden/log/eden_log.txt"
    raw = runner.read_capped(source, FILE_LIMIT).decode("utf-8", "replace") if source.is_file() else ""
    faults = re.findall(r"Unhandled SIGSEGV at (0x[0-9a-fA-F]+)", raw)
    if faults:
        pc = int(faults[-1], 16)
        matches = []
        for line in (directory / "proc-maps.txt").read_text().splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) != 6 or fields[5] != str(executable) or "x" not in fields[1]:
                continue
            start, end = (int(value, 16) for value in fields[0].split("-"))
            if start <= pc < end:
                matches.append((line, start - int(fields[2], 16)))
        result["fault_pc"] = hex(pc)
        if len(matches) == 1:
            mapping, bias = matches[0]
            with executable.open("rb") as stream:
                header = stream.read(20)
            if header[:6] != b"\x7fELF\x02\x01":
                raise RuntimeError("expected the verified little-endian ELF64 executable")
            kind = struct.unpack_from("<H", header, 16)[0]
            if kind not in (2, 3):
                raise RuntimeError("unsupported ELF type for fault symbolization")
            relative = pc - bias if kind == 3 else pc
            argv = ["addr2line", "-f", "-C", "-e", str(executable), hex(relative)]
            symbol = {"mapping": mapping, "load_bias": hex(bias), "elf_type": kind,
                      "relative_pc": hex(relative), "argv": argv}
            try:
                lookup = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        timeout=5, check=False)
                symbol.update(returncode=lookup.returncode,
                              output=lookup.stdout[:16384].decode("utf-8", "replace"),
                              output_truncated=len(lookup.stdout) > 16384)
            except subprocess.TimeoutExpired:
                symbol["timed_out"] = True
            result["symbolization"] = symbol
    (directory / "process-snapshot.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def capture_threads(pid: int, executable: Path, directory: Path) -> dict:
    if Path(f"/proc/{pid}/exe").resolve(strict=True) != executable:
        raise RuntimeError("diagnostic target changed before debugger attachment")
    argv = ["sudo", "-n", "stdbuf", "-oL", "-eL", "gdb", "--batch", "--nx", "--nh",
            "-iex", "set auto-load off", "-iex", "set debuginfod enabled off",
            "-ex", "set pagination off", "-ex", "info proc mappings", "-ex", "info threads",
            "-ex", "thread apply all bt", "-ex", "detach", "-p", str(pid)]
    path = directory / "host-backtrace.log"
    with path.open("wb") as stream:
        def trace_limit() -> None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (TRACE_LIMIT, TRACE_LIMIT))
        debugger = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT,
                                    start_new_session=True, preexec_fn=trace_limit)
        try:
            rc = debugger.wait(timeout=25)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(debugger.pid, signal.SIGTERM)
            try:
                rc = debugger.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(debugger.pid, signal.SIGKILL)
                rc = debugger.wait(timeout=1)
    return {"pid": pid, "argv": argv, "returncode": rc, "timed_out": timed_out,
            "sha256": digest(path), "bytes": path.stat().st_size}


def diagnostic_run(command: list[str], directory: Path, env: dict[str, str],
                   log_name: str, seconds: int, *,
                   captures: runner.AnimationCaptures | None = None) -> tuple[int, float]:
    """Observe the unchanged animation, including its live capture collector."""
    if command[:3] != ["stdbuf", "-oL", "-eL"] or captures is None:
        raise ValueError("expected the exact line-buffered animation command and collector")
    executable = Path(command[3]).resolve(strict=True)
    argv = ["xvfb-run", "-a", "-e", str(directory / (log_name + ".xvfb")),
            "-s", "-screen 0 1920x1080x24 -nolisten tcp", "timeout",
            "--signal=TERM", "--kill-after=4s", str(seconds) + "s",
            *command]
    diagnostic = {"argv": argv, "io_mode": "animation-line-buffered", "copied_log_limit": FILE_LIMIT,
                  "trace_after_seconds": 15, "trace": None}
    started = time.monotonic()
    rc = None
    with (directory / log_name).open("wb") as output:
        process = subprocess.Popen(argv, cwd=directory, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        trace_attempted = False
        try:
            while process.poll() is None:
                captures.poll()
                elapsed = time.monotonic() - started
                if elapsed >= 15 and not trace_attempted:
                    trace_attempted = True
                    matches = engine_descendants(process.pid, executable)
                    diagnostic["matching_pids"] = matches
                    if len(matches) == 1:
                        try:
                            diagnostic["snapshot"] = capture_process_state(matches[0], executable, directory, env)
                        except (OSError, RuntimeError) as error:
                            diagnostic["snapshot_error"] = str(error)
                        try:
                            diagnostic["trace"] = capture_threads(matches[0], executable, directory)
                        except (OSError, RuntimeError) as error:
                            diagnostic["trace_error"] = str(error)
                if time.monotonic() - started > seconds + 6:
                    diagnostic["outer_deadline_exceeded"] = True
                    break
                try:
                    process.wait(timeout=0.02)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                rc = process.wait(timeout=2)
            if rc is None:
                rc = process.returncode
            captures.poll()
            log = directory / log_name
            diagnostic["runtime_log_bytes"] = log.stat().st_size
            if log.stat().st_size > FILE_LIMIT:
                with log.open("r+b") as retained:
                    retained.truncate(FILE_LIMIT)
                diagnostic["runtime_log_truncated"] = True
            source = Path(env["XDG_DATA_HOME"]) / "eden/log/eden_log.txt"
            if source.is_file() and not source.is_symlink():
                raw = runner.read_capped(source, FILE_LIMIT)
                target = directory / "engine.log"
                target.write_bytes(raw)
                diagnostic["engine_log"] = {"sha256": digest(target), "bytes": len(raw),
                                             "within_limit": len(raw) <= FILE_LIMIT}
            else:
                diagnostic["engine_log"] = None
            diagnostic["process_rc"] = rc
            diagnostic["elapsed_seconds"] = round(time.monotonic() - started, 3)
            (directory / "diagnostic.json").write_text(json.dumps(diagnostic, indent=2) + "\n")
    return rc, time.monotonic() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, choices=range(1, 21), default=20)
    args = parser.parse_args()
    for tool in ("gdb", "sudo", "xvfb-run", "xauth", "timeout", "stdbuf", "addr2line"):
        if not shutil.which(tool):
            raise SystemExit("missing diagnostic prerequisite: " + tool)
    subprocess.run(["sudo", "-n", "true"], check=True)
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    icds = sorted(Path("/usr/share/vulkan/icd.d").glob("lvp*.json"))
    if len(icds) != 1:
        raise SystemExit("expected one installed Lavapipe manifest")
    icd = icds[0].resolve(strict=True)
    if "lvp" not in json.loads(icd.read_text())["ICD"]["library_path"]:
        raise SystemExit("manifest is not Lavapipe")
    source, cli, engine = build_engine(args.engine_dir, eden_revision=BASELINE_SHA)
    provenance = {"eden_revision": BASELINE_SHA, "engine": engine,
                  "eden_source": str(source), "icd": str(icd), "icd_sha256": digest(icd),
                  "source_sha256": {p.name: digest(p) for p in (
                      Path(__file__), Path(runner.__file__),
                      runner.ROOT / "native_gpu_probe.S", runner.ROOT / "native_frame_probe.S",
                      runner.ROOT / "make_native_frame_exefs.py",
                      runner.ROOT / "native_gpu_commands.py",
                      runner.ROOT / "assess_native_gpu_frame.py")},
                  "diagnostic_tools": {name: subprocess.check_output(
                      [name, "--version"], text=True).splitlines()[0] for name in ("gdb",)}}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    runner.run_x11 = diagnostic_run
    summary = {"eden_revision": BASELINE_SHA, "workload": "gpu-animation", "variant": 0,
               "trials": [], "first_failure": None,
               "complete": False, "diagnostic_only": True}
    try:
        for number in range(1, args.trials + 1):
            if digest(cli) != engine["eden_cli_sha256"]:
                raise RuntimeError("engine executable changed between trials")
            directory = output / f"trial-{number:02}"
            directory.mkdir()
            result = runner.trial(cli, directory, icd, "aarch64-linux-gnu-", 0,
                                  gpu=True, animation=True, eden_revision=BASELINE_SHA)
            summary["trials"].append({"number": number, "result": result})
            print("NX2_EXIT_DIAGNOSTIC_TRIAL " + json.dumps(
                {"number": number, "rc": result["process_rc"], "verified": result["verified"]}),
                flush=True)
            if not result["verified"]:
                summary["first_failure"] = number
                break
            if number > 1:
                # Preserve one successful image reference and every failed image.
                # Later successful image hashes remain in each unchanged result.json.
                for image in (directory / "variant-0").glob("*.tga"):
                    image.unlink()
            total = sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
            if total > ARTIFACT_LIMIT:
                raise RuntimeError("diagnostic artifact budget exceeded")
        else:
            summary["complete"] = True
    finally:
        (output / "diagnostic-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 1 if summary["first_failure"] is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
