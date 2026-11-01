#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check local Markdown links, core CTest, Python regressions and fixture assembly.

Requires Python 3.9+, Git, CMake, a C++23 compiler and GNU AArch64 binutils.
--python-only omits the core build and CTest for CI's separate platform jobs.
No external source, emulator, console data or network access is needed.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def markdown_destinations(source: str):
    """Read ordinary inline/image links and reference definitions, excluding code.

    This checks file destinations, not Markdown syntax, anchors or remote URLs.
    """
    visible = []
    fence = ""
    for line in source.splitlines(keepends=True):
        marker = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if fence:
            if (marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence)
                    and not line[marker.end():].strip()):
                fence = ""
        elif marker:
            fence = marker[1]
        else:
            visible.append(line)
    text = re.sub(r"(`+).*?\1", "", "".join(visible), flags=re.DOTALL)
    inline = r'\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+"[^"\n]*")?\s*\)'
    reference = r'^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)'
    for match in re.finditer(inline + "|" + reference, text, re.MULTILINE):
        yield (match[1] or match[2]).strip("<>")


def check_markdown_links(root: Path = ROOT) -> None:
    """Check repository Markdown without entering ignored build/vendor trees."""
    root = root.resolve()
    listed = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "--", "*.md"], cwd=root)
    files = sorted({os.fsdecode(name) for name in listed.split(b"\0") if name})
    errors = []
    count = 0
    for name in files:
        source = root / name
        if not source.is_file():
            continue
        for destination in markdown_destinations(source.read_text(encoding="utf-8")):
            url = urlsplit(destination)
            if url.scheme or url.netloc or not url.path:
                continue
            target = (source.parent / unquote(url.path)).resolve()
            count += 1
            if not target.is_relative_to(root) or not target.exists():
                errors.append(f"{name}: missing repository target {destination}")
    if errors:
        raise ValueError("Local Markdown links failed:\n" + "\n".join(errors))
    print(f"Local Markdown links passed: {len(files)} files, {count} file targets.")


def run(command: list[str]) -> None:
    print("+ " + shlex.join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-only", action="store_true",
                        help="run offline Python and assembler checks without the core build")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build",
                        help="core CMake build directory (default: repository build/)")
    args = parser.parse_args()
    if sys.version_info < (3, 9):
        parser.exit(2, "Python 3.9 or newer is required.\n")
    if not __debug__:
        parser.exit(2, "Run checks without -O or PYTHONOPTIMIZE; self-test assertions are required.\n")

    prefix = os.environ.get("NX2_AARCH64_PREFIX", "aarch64-linux-gnu-")
    required = ["git"] + [prefix + name for name in ("as", "ld", "objcopy")]
    if not args.python_only:
        required += ["cmake", "ctest"]
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        parser.exit(2, "Missing required tools: " + ", ".join(missing) +
                    "\nInstall the prerequisites above; for an existing assembler, "
                    "set NX2_AARCH64_PREFIX.\n")

    try:
        check_markdown_links()
        if not args.python_only:
            build = str(args.build_dir.resolve())
            run(["cmake", "-S", str(ROOT), "-B", build, "-DBUILD_TESTING=ON",
                 "-DCMAKE_BUILD_TYPE=Debug", "-DPython3_EXECUTABLE=" + sys.executable])
            run(["cmake", "--build", build, "--config", "Debug", "--parallel", "2"])
            run(["ctest", "--test-dir", build, "-C", "Debug", "--output-on-failure"])
        for folder in ("tests", "tools/ci", "tools/reference/eden_ns2"):
            run([sys.executable, "-m", "unittest", "discover", "-s", folder,
                 "-p", "test_*.py", "-v"])
        run([sys.executable,
             "tools/reference/external_arm64/profile_external_elf_selftest.py"])
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Repository checks failed: " + str(error), file=sys.stderr)
        return 1
    print("NX2_OFFLINE_PYTHON_CHECKS_PASS" if args.python_only else
          "NX2_CORE_AND_OFFLINE_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
