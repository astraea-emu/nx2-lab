#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Assemble the original VI2 lifecycle guest into the bounded synthetic ExeFS.

Only host GNU AArch64 binutils run here. Runtime replies, notification memory
and teardown require the separate Eden trial and assess_native_vi2.py.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from assess_native_vi2 import FIELDS
from make_native_exefs import build_extended_npdm
from make_native_ipc_exefs import ROOT, build_ipc_nso, compile_segments, read_ipc_segments

# Fifteen 64-byte requests, independently emitted with unchanged libnx
# b156b4774fb2df7b93402169509266da7547fc4c cmifMakeRequest/hipcMakeRequest.
# The notification template has a zero buffer; the guest patches its descriptor
# before sending. This structural digest does not establish runtime behavior.
REQUEST_BYTES = 15 * 64
REQUEST_SHA256 = "f25d4d5259c0a1d86cb372528f7012f918c71982ecbb7292508ea20fec43f8dd"
ARRAY_NAMES = {"~short_word", "~first_word", "~clear_word"}


def read_field_names(rodata: bytes) -> tuple[tuple[str, ...], int]:
    """Expand the bounded compact name stream and locate its aligned requests."""
    names = []
    offset = 0
    while offset < len(rodata):
        end = rodata.find(b"\0", offset)
        if end < 0:
            raise ValueError("unterminated VI2 field name")
        name = rodata[offset:end].decode("ascii")
        offset = end + 1
        if not name:
            request_offset = (offset + 15) & ~15
            if request_offset > len(rodata) or any(rodata[offset:request_offset]):
                raise ValueError("VI2 field alignment must contain only zero bytes")
            return tuple(names), request_offset
        if name.startswith("~"):
            if name not in ARRAY_NAMES:
                raise ValueError("unknown VI2 field array")
            names.extend(f"{name[1:]}{index:02d}" for index in range(32))
        else:
            names.append(name)
    raise ValueError("unterminated VI2 field stream")


def verify_vi2_fixture(nso: bytes, npdm: bytes) -> None:
    _, rodata, data = read_ipc_segments(nso)
    names, request_offset = read_field_names(rodata)
    if names != tuple(name for name, _ in FIELDS):
        raise ValueError("VI2 observed-field order differs from wire contract")
    requests = rodata[request_offset:request_offset + REQUEST_BYTES]
    if len(requests) != REQUEST_BYTES or hashlib.sha256(requests).hexdigest() != REQUEST_SHA256:
        raise ValueError("VI2 requests differ from independently checked libnx vectors")
    record_bytes = 4 * len(FIELDS)
    if data[:record_bytes] != b"\xff" * record_bytes:
        raise ValueError("VI2 result fields must start as unobserved sentinels")
    if data[record_bytes:record_bytes + 7 * 4] != bytes(7 * 4):
        raise ValueError("VI2 owned handles must start empty")
    for marker in (b"NX2_VI2_BEGIN\n", b"NX2_VI2_COMPLETE\n", b"NX2_VI2_FAILURE\n"):
        if rodata.count(marker) != 1:
            raise ValueError("VI2 lifecycle marker missing or duplicated")
    if npdm != build_extended_npdm():
        raise ValueError("VI2 probe must retain the corrected synthetic baseline NPDM")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tool-prefix", default="aarch64-linux-gnu-")
    args = parser.parse_args()
    sources = (ROOT / "native_vi2_probe.S", ROOT / "native_vi2_probe.ld")
    sections = compile_segments(args.tool_prefix, source=sources[0], linker=sources[1])
    nso, npdm = build_ipc_nso(sections), build_extended_npdm()
    verify_vi2_fixture(nso, npdm)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in (("main", nso), ("main.npdm", npdm)):
        (args.output / name).write_bytes(content)
        print(f"NX2_VI2_FIXTURE name={name} bytes={len(content)} sha256={hashlib.sha256(content).hexdigest()}")
    for source in sources:
        print(f"NX2_VI2_SOURCE name={source.name} sha256={hashlib.sha256(source.read_bytes()).hexdigest()}")
    print("NX2_VI2_FIXTURE_GENERATED; guest execution not attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
