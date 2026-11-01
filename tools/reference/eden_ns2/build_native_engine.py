#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build and verify the frozen Linux Eden CLI used by NX2's original guests.

Install --print-packages with your distribution's package manager first. The
recipe records system versions; it does not provide a hermetic toolchain.
Unexpected edits or interrupted builds require a new --engine-dir. Nothing is
reset or cleaned automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time

import overlay_eden_exit

BASELINE_SHA = "e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c"
CANDIDATE_SHA = "b2cef0c0f2e8517673233e22c929918e2c60e654"
EDEN_SHA = CANDIDATE_SHA
EDEN_REVISIONS = (BASELINE_SHA, CANDIDATE_SHA)
EDEN_REPO = "https://github.com/0x2593/Eden-NS2.git"
CAST = "src/video_core/texture_cache/util.cpp"
LOADER = "src/core/loader/loader.h"
LOGGING = "src/common/logging.cpp"
SOURCE_BLOBS = {**overlay_eden_exit.ORIGINAL_BLOBS, **overlay_eden_exit.APPLET_BLOBS,
                CAST: "94e841e8ea4e13beb547ecc1653b5088b770a166",
                LOADER: "d3c0230cb0637bbd227ba30b703960f0b50ecbb6",
                LOGGING: "ed12d5253244c1cd464c0a3703e62e412aeda8b6"}
CANDIDATE_BLOBS = {**SOURCE_BLOBS,
                   CAST: "cb197563386f76c031d17382ac516fcad73196da",
                   LOADER: "431aeace7395da49739d468dc65a76958db7865d"}
CAST_BEFORE = "const u64 segment_begin = u64{layer} * layer_stride + level_offset;"
CAST_AFTER = "const u64 segment_begin = static_cast<u64>(layer) * layer_stride + level_offset;"
CONSOLE_WRITES = r'''            std::fwrite(buffer, 1, (std::min)(sizeof(buffer) - 1, result.size), stdout);
            std::fwrite(entry.message, 1, entry.message_len, stdout);
            std::fwrite("\x1b[0m\n", 1, sizeof("\x1b[0m\n"), stdout);'''
CONSOLE_LOCKED_WRITES = ("            ::flockfile(stdout);\n" + CONSOLE_WRITES +
                         "\n            ::funlockfile(stdout);")
APT_PACKAGES = tuple("""ccache clang cmake ninja-build autoconf automake libtool
pkg-config nasm binutils-aarch64-linux-gnu g++ git python3 ca-certificates
libfmt-dev liblz4-dev nlohmann-json3-dev libzstd-dev libssl-dev zlib1g-dev
libboost-dev libboost-fiber-dev libboost-context-dev libxbyak-dev libopus-dev
libasound2-dev libavcodec-dev libavfilter-dev libswscale-dev libvulkan-dev
vulkan-utility-libraries-dev spirv-tools spirv-headers glslang-tools libsdl3-dev
libenet-dev libusb-1.0-0-dev libva-dev libvdpau-dev libxext-dev libxkbcommon-dev
xvfb xauth mesa-vulkan-drivers vulkan-tools""".split())
CMAKE_OPTIONS = {"CMAKE_BUILD_TYPE": "Release", "ENABLE_QT": "OFF",
                 "ENABLE_WEB_SERVICE": "OFF", "ENABLE_UPDATE_CHECKER": "OFF",
                 "ENABLE_CUBEB": "OFF", "ENABLE_LIBUSB": "OFF", "YUZU_ROOM": "OFF",
                 "ENABLE_OPENGL": "OFF", "YUZU_CMD": "ON", "YUZU_TESTS": "OFF",
                 "BUILD_TESTING": "OFF", "ENABLE_WERROR": "OFF", "YUZU_USE_CPM": "ON"}
BUILD_FILES = ("CMakeCache.txt", "build.ninja", "CMakeFiles/rules.ninja")
BUILD_OVERRIDES = {"CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CPATH", "C_INCLUDE_PATH",
                   "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "COMPILER_PATH", "GCC_EXEC_PREFIX",
                   "CCC_OVERRIDE_OPTIONS", "CMAKE_PREFIX_PATH", "CMAKE_TOOLCHAIN_FILE",
                   "CMAKE_GENERATOR", "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR"}


def digest(path: Path, limit: int | None = None) -> str:
    value = hashlib.sha256()
    size = path.stat().st_size
    if limit is not None and size > limit:
        raise ValueError(f"oversized file to hash: {path}")
    consumed = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            consumed += len(block)
            if consumed > size:
                raise ValueError(f"file grew while hashing: {path}")
            value.update(block)
    if consumed != size:
        raise ValueError(f"file shrank while hashing: {path}")
    return value.hexdigest()


def plain_path(path: Path) -> Path:
    path = path.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"symlink is not an engine input: {path}")
    return path.resolve()


def git(root: Path, *args: str) -> bytes:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return subprocess.check_output(["git", "-C", str(root), "-c", "core.fsmonitor=false", *args], env=env)


def blob_digest(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def bounded_read(path: Path, limit: int) -> bytes:
    path = plain_path(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f"invalid or oversized engine file: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"engine file grew beyond its bound: {path}")
    return raw


def patch_console_logging(original: str) -> str:
    """Serialize the frozen POSIX record writes without changing any bytes.

    Prefix formatting stays outside the lock. All three enclosed stdio calls
    are nonthrowing; the stream lock also coordinates other stdout stdio users.
    """
    before, start, rest = original.partition("#else // ^^^ Windows vvv POSIX\n")
    posix, end, after = rest.partition("#endif\n};")
    if not start or not end or posix.count(CONSOLE_WRITES) != 1:
        raise ValueError("unexpected original POSIX console write site")
    return before + start + posix.replace(CONSOLE_WRITES, CONSOLE_LOCKED_WRITES) + end + after


def revision_sources(eden_revision: str | None) -> tuple[str, dict[str, str]]:
    revision = EDEN_SHA if eden_revision is None else eden_revision
    if revision == BASELINE_SHA:
        return revision, SOURCE_BLOBS
    if revision == CANDIDATE_SHA:
        return revision, CANDIDATE_BLOBS
    raise ValueError("unsupported Eden revision; select one of the two reviewed pins")


def inspect_source(root: Path, allow_original: bool = False, *,
                   eden_revision: str | None = None) -> dict[str, bytes]:
    """Check every tracked byte/mode, not index flags or just Git's dirty status."""
    revision, blobs = revision_sources(eden_revision)
    root = plain_path(root)
    if Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()) != root:
        raise ValueError("Eden source must be the repository root")
    if git(root, "rev-parse", "HEAD").decode().strip() != revision:
        raise ValueError("Eden source is not the pinned revision")
    if git(root, "ls-files", "--others", "--exclude-standard", "-z"):
        raise ValueError("unexpected untracked Eden source files")
    tree = {}
    for entry in git(root, "ls-tree", "-rlz", revision).split(b"\0"):
        if entry:
            metadata, name = entry.split(b"\t", 1)
            mode, kind, blob, size = metadata.decode().split()
            if kind != "blob" or mode not in ("100644", "100755"):
                raise ValueError("Eden tree contains a symlink, gitlink or unsupported entry")
            tree[os.fsdecode(name)] = (mode, blob, int(size))
    index = [os.fsdecode(name) for name in git(root, "ls-files", "--cached", "-z").split(b"\0") if name]
    if set(index) != set(tree) or len(index) != len(tree):
        raise ValueError("Git index path inventory differs from the pinned tree")
    if any(tree.get(name, (None, None))[1] != blob for name, blob in blobs.items()):
        raise ValueError("frozen loader, cast, logging or exit-overlay blob changed")
    originals = {name: git(root, "show", f"{revision}:{name}") for name in blobs}
    if any(blob_digest(raw) != blobs[name] for name, raw in originals.items()):
        raise ValueError("original Git object bytes do not match the reviewed blobs")
    svc, frontend = overlay_eden_exit.patch_sources(
        *(originals[name].decode() for name in overlay_eden_exit.ORIGINAL_BLOBS))
    expected = dict(zip(overlay_eden_exit.ORIGINAL_BLOBS, (svc.encode(), frontend.encode())))
    expected.update(zip(overlay_eden_exit.APPLET_BLOBS, (text.encode() for text in
        overlay_eden_exit.patch_applet_sources(
            *(originals[name].decode() for name in overlay_eden_exit.APPLET_BLOBS)))))
    cast = originals[CAST].decode()
    if revision == BASELINE_SHA:
        if cast.count(CAST_BEFORE) != 1 or "for (s32 layer = 0; layer < info.resources.layers; ++layer)" not in cast:
            raise ValueError("unexpected original cast site")
        expected[CAST] = cast.replace(CAST_BEFORE, CAST_AFTER).encode()
    elif CAST_BEFORE in cast or cast.count(CAST_AFTER) != 1:
        raise ValueError("candidate does not contain the reviewed upstream cast repair")
    expected[LOGGING] = patch_console_logging(originals[LOGGING].decode()).encode()
    for name, (mode, blob, size) in tree.items():
        path = plain_path(root / name)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or bool(info.st_mode & 0o111) != (mode == "100755"):
            raise ValueError(f"unexpected source file type or mode: {name}")
        sizes = {len(expected[name])} if name in expected else {size}
        if allow_original:
            sizes.add(size)
        if info.st_size not in sizes:
            raise ValueError(f"unexpected source file size: {name}")
        raw = bounded_read(path, max(sizes))
        if name in expected:
            if raw != expected[name] and not (allow_original and raw == originals[name]):
                raise ValueError(f"unexpected repaired source: {name}")
        elif blob_digest(raw) != blob:
            raise ValueError(f"unexpected changed source: {name}")
    return expected


def check_source(root: Path, *, eden_revision: str | None = None) -> dict[str, str]:
    return {name: hashlib.sha256(raw).hexdigest()
            for name, raw in inspect_source(root, eden_revision=eden_revision).items()}


def ignored_inputs(root: Path) -> dict:
    """Fingerprint generated source and CPM inputs without a large file manifest."""
    names = sorted(name for name in git(root, "ls-files", "--others", "--ignored",
                                       "--exclude-standard", "-z").split(b"\0") if name)
    if len(names) > 100_000:
        raise ValueError("too many ignored engine inputs")
    combined, total = hashlib.sha256(), 0
    for name in names:
        path = root / os.fsdecode(name)
        plain_path(path.parent)
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            if not path.resolve().is_relative_to(root):
                raise ValueError(f"ignored input symlink escapes source: {path}")
            raw = os.fsencode(os.readlink(path))
            size, sha = len(raw), hashlib.sha256(raw).hexdigest()
        elif stat.S_ISREG(info.st_mode):
            size, sha = info.st_size, digest(path, 256 * 1024**2)
        else:
            raise ValueError(f"unsupported ignored input type: {path}")
        total += size
        if total > 4 * 1024**3:
            raise ValueError("ignored engine inputs exceed the 4 GiB bound")
        combined.update(json.dumps([os.fsdecode(name), info.st_mode, size, sha],
                                   separators=(",", ":")).encode() + b"\n")
    return {"sha256": combined.hexdigest(), "files": len(names), "bytes": total}


def prepare_source(root: Path, *, eden_revision: str | None = None) -> None:
    revision, _ = revision_sources(eden_revision)
    expected = inspect_source(root, allow_original=True, eden_revision=revision)
    for name, raw in expected.items():
        path = root / name
        if bounded_read(path, max(len(raw), int(git(root, "cat-file", "-s", f"{revision}:{name}")))) != raw:
            path.write_bytes(raw)  # Only exact original bytes passed inspection above.


def run(command: list[str], env: dict[str, str]) -> None:
    print("+ " + shlex.join(command), flush=True)
    subprocess.run(command, env=env, check=True)


def toolchain() -> dict:
    found = {}
    for name in ("git", "cmake", "ninja", "clang", "clang++", "ccache"):
        command = shutil.which(name)
        if not command:
            raise ValueError(f"missing prerequisite: {name}; install --print-packages")
        # Preserve clang++'s invocation name even when it is a symlink to clang.
        path = Path(command).absolute()
        version = subprocess.check_output([str(path), "--version"], text=True).strip()
        found[name] = {"path": str(path), "sha256": digest(path), "version": version}
    version = re.match(r"cmake version (\d+)\.(\d+)", found["cmake"]["version"])
    if not version or tuple(map(int, version.groups())) < (3, 31):
        raise ValueError("the frozen Eden build requires CMake 3.31 or newer")
    return found


def system_packages() -> dict:
    if not shutil.which("dpkg-query"):
        return {"available": False}
    result = subprocess.run(["dpkg-query", "--show", "--showformat=${binary:Package}=${Version}\n",
                             *APT_PACKAGES], capture_output=True, text=True, check=False)
    return {"available": True, "query_rc": result.returncode,
            "versions": sorted(result.stdout.splitlines())}


def resources() -> dict[str, int]:
    cpu = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    memory = dict(re.findall(r"^(MemTotal|MemAvailable):\s+(\d+) kB$",
                             Path("/proc/meminfo").read_text(), re.MULTILINE))
    total, available = int(memory["MemTotal"]), int(memory["MemAvailable"])
    jobs = 4 if cpu >= 4 and total >= 14 * 1024**2 and available >= 12 * 1024**2 else min(cpu, 2)
    return {"cpu": cpu, "memory_kib": total, "available_memory_kib": available, "jobs": jobs}


def output_hashes(build: Path, binary: Path) -> dict[str, str]:
    if not plain_path(binary).is_file() or not os.access(binary, os.X_OK):
        raise ValueError("Eden CLI is not a regular executable")
    result = {}
    for name in (*BUILD_FILES, "bin/eden-cli"):
        path = plain_path(build / name)
        limit = 2 * 1024**3 if name == "bin/eden-cli" else 16 * 1024**2
        if not path.is_file() or path.stat().st_size > limit:
            raise ValueError(f"invalid or oversized engine output: {name}")
        result[name] = digest(path, limit)
    return result


def verify_cache(build: Path, source: Path, options: dict[str, str]) -> None:
    cache = {}
    for line in bounded_read(build / "CMakeCache.txt", 1024**2).decode().splitlines():
        if line and not line.startswith(("#", "//")) and ":" in line and "=" in line:
            name, value = line.split("=", 1)
            cache[name.split(":", 1)[0]] = value
    required = {**options, "CMAKE_GENERATOR": "Ninja", "CMAKE_HOME_DIRECTORY": str(source)}
    if any(cache.get(name) != value for name, value in required.items()):
        raise ValueError("unexpected CMake configuration; use a new --engine-dir")


def build_engine(engine_dir: Path, ccache_dir: Path | None = None, *,
                 eden_revision: str | None = None) -> tuple[Path, Path, dict]:
    started = time.monotonic()
    revision, _ = revision_sources(eden_revision)
    if sys.platform != "linux":
        raise ValueError("the external engine recipe is qualified on Linux only")
    engine_dir = plain_path(engine_dir)
    source, build = engine_dir / "eden", engine_dir / "eden-build"
    binary, receipt, active = build / "bin/eden-cli", engine_dir / "native-engine.json", engine_dir / ".building"
    for path in (source, build, receipt, active):
        plain_path(path)
    if active.exists():
        raise ValueError("an engine build is active or was interrupted; use a new --engine-dir")
    previous = None
    if receipt.exists():
        previous = json.loads(bounded_read(receipt, 1024**2))
        if not isinstance(previous, dict) or type(previous.get("schema")) is not int or previous["schema"] != 1:
            raise ValueError("invalid engine receipt; use a new --engine-dir")
        if previous.get("eden_revision") != revision:
            raise ValueError("engine receipt belongs to another pinned revision; use a new --engine-dir")
    elif build.exists():
        raise ValueError("build directory has no successful receipt; use a new --engine-dir")
    ccache_dir = plain_path(ccache_dir or Path(os.environ.get("CCACHE_DIR", str(engine_dir / "ccache"))))
    if ccache_dir.is_relative_to(source) or ccache_dir.is_relative_to(build):
        raise ValueError("compiler cache must be outside source and build directories")
    tools = toolchain()
    options = {**CMAKE_OPTIONS, "CMAKE_C_COMPILER": tools["clang"]["path"],
               "CMAKE_CXX_COMPILER": tools["clang++"]["path"],
               "CMAKE_C_COMPILER_LAUNCHER": "ccache", "CMAKE_CXX_COMPILER_LAUNCHER": "ccache"}
    identity = {"eden_revision": revision, "source": str(source), "build": str(build),
                "helper_sha256": digest(Path(__file__)),
                "overlay_sha256": digest(Path(overlay_eden_exit.__file__)),
                "tools": tools, "options": options, "packages": system_packages(),
                "ccache_dir": str(ccache_dir), "machine": platform.machine(),
                "path": os.environ.get("PATH", "")}
    if source.exists():
        inspect_source(source, allow_original=previous is None, eden_revision=revision)
        ignored = ignored_inputs(source)
        if previous is None and ignored["files"]:
            raise ValueError("unverified preexisting ignored engine inputs; use a new --engine-dir")
        if previous and previous.get("ignored_source_inputs") != ignored:
            raise ValueError("ignored dependency or generated source changed; use a new --engine-dir")
    if previous:
        if (previous.get("identity") != identity or
                previous.get("modified_source_sha256") != check_source(source, eden_revision=revision)):
            raise ValueError("engine source or build identity changed; use a new --engine-dir")
        if previous.get("output_sha256") != output_hashes(build, binary):
            raise ValueError("engine binary or configuration changed; use a new --engine-dir")
        if previous.get("eden_cli_sha256") != previous["output_sha256"]["bin/eden-cli"]:
            raise ValueError("inconsistent engine receipt; use a new --engine-dir")
        verify_cache(build, source, options)
    engine_dir.mkdir(parents=True, exist_ok=True)
    with active.open("x") as marker:
        marker.write(f"pid={os.getpid()}\n")
    if previous:
        receipt.unlink()  # A failed rebuild cannot leave a successful receipt behind.
    env = {key: value for key, value in os.environ.items()
           if key not in BUILD_OVERRIDES and not key.startswith(("CPM_", "CCACHE_", "GIT_"))}
    env.update(CCACHE_DIR=str(ccache_dir), GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    if not source.exists():
        run([tools["git"]["path"], "init", "-q", str(source)], env)
        run([tools["git"]["path"], "-C", str(source), "remote", "add", "origin", EDEN_REPO], env)
        run([tools["git"]["path"], "-C", str(source), "-c", "protocol.version=2", "fetch",
             "--quiet", "--no-tags", "--depth=1", "--filter=blob:none", "origin", revision], env)
        run([tools["git"]["path"], "-C", str(source), "checkout", "-q", "--detach", "FETCH_HEAD"], env)
    prepare_source(source, eden_revision=revision)
    modified = check_source(source, eden_revision=revision)
    ccache_dir.mkdir(parents=True, exist_ok=True)
    run([tools["ccache"]["path"], "--max-size=1200M"], env)
    run([tools["ccache"]["path"], "--zero-stats"], env)
    configure_seconds = 0.0
    if previous is None:
        configured = time.monotonic()
        run([tools["cmake"]["path"], "-S", str(source), "-B", str(build), "-G", "Ninja",
             *(f"-D{name}={value}" for name, value in options.items())], env)
        configure_seconds = time.monotonic() - configured
        verify_cache(build, source, options)
    allocation = resources()
    print("NX2_EDEN_BUILD_RESOURCES " + json.dumps(allocation, sort_keys=True), flush=True)
    built = time.monotonic()
    run([tools["cmake"]["path"], "--build", str(build), "--target", "yuzu-cmd",
         "--parallel", str(allocation["jobs"])], env)
    build_seconds = time.monotonic() - built
    run([tools["ccache"]["path"], "--show-stats"], env)
    if check_source(source, eden_revision=revision) != modified:
        raise ValueError("engine source changed during build")
    if (digest(Path(__file__)) != identity["helper_sha256"] or
            digest(Path(overlay_eden_exit.__file__)) != identity["overlay_sha256"] or
            toolchain() != tools or system_packages() != identity["packages"]):
        raise ValueError("build recipe or toolchain changed during build")
    verify_cache(build, source, options)
    outputs = output_hashes(build, binary)
    if previous and outputs["bin/eden-cli"] != previous["eden_cli_sha256"]:
        raise ValueError("incremental build changed the engine binary; use a new --engine-dir")
    report = {"schema": 1, "identity": identity, "receipt": str(receipt),
              "reused": previous is not None, "eden_revision": revision,
              "eden_cli_sha256": outputs["bin/eden-cli"], "modified_source_sha256": modified,
              "source_diff": git(source, "diff", "--no-ext-diff", "--no-textconv",
                                 revision, "--").decode(),
              "ignored_source_inputs": ignored_inputs(source),
              "output_sha256": outputs, "configure_seconds": round(configure_seconds, 3),
              "build_seconds": round(build_seconds, 3), "resources": allocation,
              "elapsed_seconds": round(time.monotonic() - started, 3)}
    temporary = receipt.with_suffix(".tmp")
    with temporary.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, receipt)
    active.unlink()
    return source, binary, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, default=Path("build/native-engine"))
    parser.add_argument("--ccache-dir", type=Path)
    parser.add_argument("--eden-revision", choices=EDEN_REVISIONS, default=EDEN_SHA)
    parser.add_argument("--print-packages", action="store_true")
    args = parser.parse_args()
    if args.print_packages:
        print(" ".join(APT_PACKAGES))
        return 0
    try:
        _, _, report = build_engine(args.engine_dir, args.ccache_dir, eden_revision=args.eden_revision)
        print("NX2_NATIVE_ENGINE " + json.dumps(report, sort_keys=True), flush=True)
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"NX2_NATIVE_ENGINE_NOT_VERIFIED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
