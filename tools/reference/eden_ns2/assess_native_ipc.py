#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify the original synthetic native guest's observed SM IPC round trip.

Only records attributed to the frozen emulator's debug SVC count. The guest
reports raw response fields, transport results, returned handles and cleanup
results; a successful debug print or a host-authored echo is insufficient.
This qualifies one modeled, source-owned IPC exchange, not hardware ABI fidelity.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

MAX_LOG_SIZE = 20 * 1024 * 1024
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LOG_PREFIX = r"(?:\[\s*\d+(?:\.\d+)?\]\s*)?"
CLASSIFIED = re.compile(
    LOG_PREFIX + r"Core <Info> core/core\.cpp:\d+:Load: "
    r"Switch 2 program: using the 12 GiB memory layout"
)
GUEST_OUTPUT = re.compile(
    LOG_PREFIX + r"Debug\.Emulated <Info> "
    r"core/hle/kernel/svc/svc_debug_string\.cpp:\d+:OutputDebugString: (.*)"
)
GUEST_EXIT = re.compile(
    LOG_PREFIX + r"Kernel\.SVC <Info> "
    r"core/hle/kernel/svc/svc_process\.cpp:\d+:ExitProcess: Process \d+ exiting"
)
FIELD_RECORD = re.compile(r"NX2_IPC ([a-z_]+)=([0-9a-f]{8})")
EXECUTION_FAILURE = re.compile(
    r"\bassert(?:ion)?\b|ExceptionRaised|Cannot execute instruction|"
    r"Segmentation fault|\bAborted\b|AddressSanitizer|UndefinedBehaviorSanitizer|"
    r"runtime error:|\b(?:Core\.ARM|Debug) <(?:Critical|Error)>",
    re.IGNORECASE,
)
STUB_FAILURE = re.compile(
    r"Using auto stub fallback!|Unknown\s*/\s*unimplemented",
    re.IGNORECASE,
)

# Ordered wire contract shared with the separately authored ARM64 guest.
# Values are raw HIPC word 1 / descriptor word 2, not decoded host summaries.
# A None expectation denotes an observed handle, validated below.
FIELDS = (
    ("connect_rc", 0),
    ("sm_handle", None),
    ("init_transport", 0),
    ("init_magic", 0x4F434653),
    ("init_result", 0),
    ("init_header", 0x0000000A),
    ("init_descriptor", 0),
    ("get_transport", 0),
    ("get_magic", 0x4F434653),
    ("get_result", 0),
    ("get_header", 0x8000000A),
    ("get_descriptor", 0x00000020),
    ("service_handle", None),
    ("invalid_transport", 0),
    ("invalid_magic", 0x4F434653),
    ("invalid_result", 0x00000C15),
    ("invalid_header", 0x0000000A),
    ("invalid_descriptor", 0),
    ("close_service", 0),
    ("close_sm", 0),
    ("fail_step", 0),
)


def report(lines: list[str], byte_count: int, nul_count: int) -> None:
    """Preserve binary diagnostics while bounding noisy emulator output."""
    print(f"NX2_NATIVE_IPC_LOG_BYTES={byte_count}")
    print(f"NX2_NATIVE_IPC_LOG_NUL_COUNT={nul_count}")
    terms = ("NX2_IPC", "Switch 2 program", "ExitProcess", "Error", "Critical",
             "ExceptionRaised", "assert", "stub", "unimplemented")
    selected = set(range(min(8, len(lines))))
    selected.update(range(max(0, len(lines) - 12), len(lines)))
    selected.update(i for i, line in enumerate(lines) if any(t in line for t in terms))
    indices = sorted(selected)
    if len(indices) > 110:
        indices = sorted(set(indices[:60] + indices[-50:]))
    for index in indices:
        line = lines[index].replace("\0", "[NUL]")
        clean = "".join(c if c.isprintable() or c == "\t" else "?" for c in line)
        print(f"NX2_NATIVE_IPC_LOG[{index}]={clean[:400]}")


def assess(raw: bytes, process_rc: int) -> bool:
    print(f"NX2_NATIVE_IPC_PROCESS_RC={process_rc}")
    if len(raw) > MAX_LOG_SIZE:
        print("NX2_NATIVE_IPC_LOG_LIMIT_EXCEEDED")
        return False
    normalized = ANSI_ESCAPE.sub("", raw.decode("utf-8", "replace"))
    lines = normalized.splitlines()
    report(lines, len(raw), raw.count(bytes([0])))
    classifications = []
    exits = []
    completions = []
    records = []
    protocol_errors = []
    for index, raw_line in enumerate(lines):
        # The frozen logger places NUL separators at record boundaries. Do not
        # delete embedded NULs or malformed bytes inside a protocol record.
        line = raw_line.strip("\0 \t")
        if CLASSIFIED.fullmatch(line):
            classifications.append(index)
        if GUEST_EXIT.fullmatch(line):
            exits.append(index)
        if "NX2_IPC" not in line:
            continue
        output = GUEST_OUTPUT.fullmatch(line)
        if output is None:
            protocol_errors.append(f"unattributed record at line {index}")
            continue
        payload = output.group(1)
        if payload == "NX2_IPC_COMPLETE":
            completions.append(index)
            continue
        record = FIELD_RECORD.fullmatch(payload)
        if record is None:
            protocol_errors.append(f"malformed or failure record at line {index}")
            continue
        records.append((index, record.group(1), int(record.group(2), 16)))

    names = [name for _, name, _ in records]
    expected_names = [name for name, _ in FIELDS]
    fields_in_order = names == expected_names
    values = {name: value for _, name, value in records}
    values_match = all(value is None or values.get(name) == value for name, value in FIELDS)
    sm_handle = values.get("sm_handle", 0)
    service_handle = values.get("service_handle", 0)
    # 0xffffffff is the guest's unobserved-value sentinel, never handle evidence.
    handles_observed = (sm_handle not in (0, 0xFFFFFFFF) and
                        service_handle not in (0, 0xFFFFFFFF) and
                        sm_handle != service_handle)
    events_in_order = (
        len(classifications) == len(completions) == len(exits) == 1 and
        bool(records) and classifications[0] < records[0][0] and
        records[-1][0] < completions[0] < exits[0]
    )
    failed = "NX2_IPC_FAILURE" in normalized or bool(EXECUTION_FAILURE.search(normalized))
    stubbed = bool(STUB_FAILURE.search(normalized))
    for name, _ in FIELDS:
        value = values.get(name)
        print(f"NX2_NATIVE_IPC_OBSERVED_{name.upper()}="
              + (f"{value:08x}" if value is not None else "MISSING"))
    print(f"NX2_NATIVE_IPC_FIELD_COUNT={len(records)}")
    print(f"NX2_NATIVE_IPC_FIELDS_IN_ORDER={int(fields_in_order)}")
    print(f"NX2_NATIVE_IPC_VALUES_MATCH={int(values_match)}")
    print(f"NX2_NATIVE_IPC_DISTINCT_HANDLES_OBSERVED={int(handles_observed)}")
    print(f"NX2_NATIVE_IPC_CLASSIFY_COMPLETE_EXIT_IN_ORDER={int(events_in_order)}")
    print(f"NX2_NATIVE_IPC_FAILURE_SEEN={int(failed)}")
    print(f"NX2_NATIVE_IPC_STUB_FALLBACK_SEEN={int(stubbed)}")
    print(f"NX2_NATIVE_IPC_PROTOCOL_ERRORS={len(protocol_errors)}")
    for error in protocol_errors[:10]:
        print(f"NX2_NATIVE_IPC_PROTOCOL_ERROR={error}")
    ok = (process_rc == 0 and fields_in_order and values_match and handles_observed and
          events_in_order and not failed and not stubbed and not protocol_errors)
    print("NX2_NATIVE_IPC_GUEST_ROUND_TRIP_PASS" if ok else
          "NX2_NATIVE_IPC_GUEST_ROUND_TRIP_NOT_VERIFIED")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--exit", required=True, type=int, dest="process_rc")
    args = parser.parse_args()
    if args.log.stat().st_size > MAX_LOG_SIZE:
        parser.exit(1, "NX2_NATIVE_IPC_LOG_LIMIT_EXCEEDED\n")
    return 0 if assess(args.log.read_bytes(), args.process_rc) else 1


if __name__ == "__main__":
    raise SystemExit(main())
