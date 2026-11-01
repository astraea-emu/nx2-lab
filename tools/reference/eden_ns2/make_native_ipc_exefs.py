#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Earlier MIT-licensed material retains that permission; see LICENSES/MIT.txt.
"""Compile the original NX2 SM IPC guest into a bounded synthetic ExeFS.

Requires GNU AArch64 binutils, not a console SDK. No emulator or ARM code runs
here. The baseline debug-only fixture remains unchanged. Synthetic NPDM and
the frozen engine's permissive SVC handling are not hardware ABI evidence.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile

from make_native_exefs import NSO_HEADER, PAGE, build_extended_npdm

ROOT = Path(__file__).resolve().parent
FIELDS = (
    "connect_rc", "sm_handle", "init_transport", "init_magic", "init_result",
    "init_header", "init_descriptor", "get_transport", "get_magic", "get_result",
    "get_header", "get_descriptor", "service_handle", "invalid_transport",
    "invalid_magic", "invalid_result", "invalid_header", "invalid_descriptor",
    "close_service", "close_sm", "fail_step",
)


def request_template(command: int, send_pid: bool, payload: bytes) -> bytes:
    """Original bytes independently compared with pinned libnx host builders.

    libnx b156b4774fb2df7b93402169509266da7547fc4c cmifMakeRequest with
    data_size=8: PID request payload at 0x30; ordinary payload at 0x20.
    """
    if len(payload) != 8:
        raise ValueError("SM input must contain exactly eight bytes")
    result = bytearray(64)
    struct.pack_into("<II", result, 0, 4, 10 | (int(send_pid) << 31))
    if send_pid:
        struct.pack_into("<I", result, 8, 1)
    start = 0x20 if send_pid else 0x10
    struct.pack_into("<IIII", result, start, 0x49434653, 0, command, 0)
    result[start + 16:start + 24] = payload
    return bytes(result)


def compile_segments(
    tool_prefix: str = "aarch64-linux-gnu-", *,
    source: Path = ROOT / "native_sm_probe.S",
    linker: Path = ROOT / "native_sm_probe.ld",
) -> tuple[bytes, bytes, bytes]:
    """Run only the host assembler/linker and extract three bounded sections."""
    with tempfile.TemporaryDirectory(prefix="nx2-sm-guest-") as temporary:
        directory = Path(temporary)
        obj, elf = directory / "guest.o", directory / "guest.elf"
        subprocess.run([tool_prefix + "as", "-o", str(obj), str(source)], check=True)
        subprocess.run([tool_prefix + "ld", "--build-id=none", "-T",
                        str(linker), "-o", str(elf), str(obj)],
                       check=True)
        header = elf.read_bytes()[:64]
        if (header[:7] != b"\x7fELF\x02\x01\x01" or
                struct.unpack_from("<HH", header, 16) != (2, 183) or
                struct.unpack_from("<Q", header, 24)[0] != 0):
            raise ValueError("expected an AArch64 little-endian executable with entry zero")
        command = [tool_prefix + "objcopy"]
        for name in ("text", "rodata", "data"):
            command.extend(["--dump-section", f".{name}={directory / name}"])
        command.extend([str(elf), str(directory / "section-copy.elf")])
        subprocess.run(command, check=True)
        sections = tuple((directory / name).read_bytes() for name in ("text", "rodata", "data"))
        if any(not section or len(section) > PAGE for section in sections):
            raise ValueError("guest section missing or larger than its one-page mapping")
        return sections


def build_ipc_nso(sections: tuple[bytes, bytes, bytes]) -> bytes:
    if len(sections) != 3 or any(not s or len(s) > PAGE for s in sections):
        raise ValueError("exactly three nonempty page-bounded sections are required")
    segments = tuple(section.ljust(PAGE, b"\0") for section in sections)
    header = bytearray(NSO_HEADER)
    struct.pack_into("<4sIII", header, 0, b"NSO0", 0, 0, 0)
    for index, segment in enumerate(segments):
        struct.pack_into("<IIII", header, 0x10 + index * 16,
                         NSO_HEADER + index * PAGE, index * PAGE, PAGE, PAGE)
        struct.pack_into("<I", header, 0x60 + index * 4, PAGE)
        header[0xA0 + index * 32:0xC0 + index * 32] = hashlib.sha256(segment).digest()
    header[0x40:0x60] = hashlib.sha256(b"".join(segments)).digest()
    return bytes(header) + b"".join(segments)


def read_ipc_segments(nso: bytes) -> tuple[bytes, bytes, bytes]:
    """Validate the bounded uncompressed NSO envelope and return its pages."""
    if len(nso) != NSO_HEADER + 3 * PAGE or nso[:16] != b"NSO0" + bytes(12):
        raise ValueError("unexpected uncompressed IPC NSO header")
    for index in range(3):
        start = NSO_HEADER + index * PAGE
        if struct.unpack_from("<IIII", nso, 0x10 + index * 16) != (start, index * PAGE, PAGE, PAGE):
            raise ValueError("unexpected IPC segment mapping")
        if struct.unpack_from("<I", nso, 0x60 + index * 4)[0] != PAGE:
            raise ValueError("incorrect IPC stored segment length")
        if hashlib.sha256(nso[start:start + PAGE]).digest() != nso[0xA0 + index * 32:0xC0 + index * 32]:
            raise ValueError("IPC segment hash mismatch")
    if nso[0x40:0x60] != hashlib.sha256(nso[NSO_HEADER:]).digest():
        raise ValueError("IPC build ID mismatch")
    return tuple(nso[NSO_HEADER + index * PAGE:NSO_HEADER + (index + 1) * PAGE]
                 for index in range(3))


def verify_ipc_fixture(nso: bytes, npdm: bytes) -> None:
    _, rodata, data = read_ipc_segments(nso)
    expected = (request_template(0, True, bytes(8)),
                request_template(1, False, b"set\0\0\0\0\0"),
                request_template(1, False, bytes(8)))
    if rodata[:192] != b"".join(expected):
        raise ValueError("IPC request differs from independently checked libnx format")
    if b"\0".join(field.encode() for field in FIELDS) + b"\0" not in rodata:
        raise ValueError("IPC observed-field order differs from wire contract")
    if data[:4 * len(FIELDS)] != b"\xff" * (4 * len(FIELDS)):
        raise ValueError("IPC result fields must start as unobserved sentinels")
    if npdm != build_extended_npdm():
        raise ValueError("IPC probe must retain the corrected synthetic baseline NPDM")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tool-prefix", default="aarch64-linux-gnu-")
    args = parser.parse_args()
    sections = compile_segments(args.tool_prefix)
    nso, npdm = build_ipc_nso(sections), build_extended_npdm()
    verify_ipc_fixture(nso, npdm)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in (("main", nso), ("main.npdm", npdm)):
        (args.output / name).write_bytes(content)
        print(f"NX2_IPC_FIXTURE name={name} bytes={len(content)} sha256={hashlib.sha256(content).hexdigest()}")
    for name in ("native_sm_probe.S", "native_sm_probe.ld"):
        print(f"NX2_IPC_SOURCE name={name} sha256={hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}")
    print("NX2_IPC_FIXTURE_GENERATED; guest execution not attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
