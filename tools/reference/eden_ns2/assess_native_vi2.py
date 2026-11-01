#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check observed VI2 lifecycle replies, notification memory and guest teardown.

The wire expectations come from Eden e2f285ab, not hardware observations.
Only complete source-attributed emulator records count. Known startup errors
and the single manager-service diagnostic are recorded, never hidden.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from assess_native_ipc import CLASSIFIED, GUEST_EXIT, GUEST_OUTPUT, LOG_PREFIX, MAX_LOG_SIZE


def _cmif(name: str, header: int = 10, descriptor: int = 0):
    return tuple((name + "_" + suffix, value) for suffix, value in (
        ("transport", 0), ("header0", 0), ("header1", header),
        ("descriptor", descriptor), ("magic", 0x4F434653), ("result", 0)))


def _tipc(name: str, command: int, result: int = 0, handle: str = ""):
    fields = [(name + "_transport", 0), (name + "_header0", command + 16),
              (name + "_header1", 0x80000001 if handle else 1)]
    if handle:
        fields.extend(((name + "_descriptor", 0x20), (handle, None)))
    return tuple(fields + [(name + "_result", result)])


def _notifications(name: str, result: int, first: int, remaining: int):
    return (_tipc(name, 21, result) + ((name + "_guard_before", 0xA5A5A5A5),) +
            tuple((f"{name}_word{index:02d}", first if index == 0 else remaining)
                  for index in range(32)) + ((name + "_guard_after", 0xA5A5A5A5),))


# ipc_helpers.h: CMIF has SFCO and ten raw words (14 with an extra u64);
# TIPC preserves command+16, has one result word and no SFCO. self_controller.cpp
# returns a copied supervisor handle; OpenDisplaySession returns a moved handle.
# svc_results.h/result.h encode Kernel errors as (description << 9) | 1.
# graphics_supervisor.cpp: duplicate=125, missing=121, short-buffer=101.
FIELDS = (
    ("connect_rc", 0), ("sm_handle", None),
    *_cmif("sm_init"),
    *_cmif("get_applet", 0x8000000A, 0x20), ("applet_handle", None),
    *_cmif("open_proxy", 0x8000000A, 0x20), ("proxy_handle", None),
    *_cmif("get_window", 0x8000000A, 0x20), ("window_handle", None),
    *_cmif("get_aruid", 14), ("aruid_lo", None), ("aruid_hi", None),
    *_cmif("get_self", 0x8000000A, 0x20), ("self_handle", None),
    *_cmif("get_gsv", 0x8000000A, 2), ("gsv_handle", None),
    *_tipc("bootstrap", 4), *_tipc("bind", 11), *_tipc("ready", 101),
    *_tipc("display_init", 301), *_tipc("open_vi2", 305, handle="vi2_handle"),
    *_tipc("register", 201), *_tipc("duplicate", 201, 0xFA01),
    *_tipc("unregister", 202), *_tipc("missing", 202, 0xF201),
    *_notifications("short", 0xCA01, 0xA5A5A5A5, 0xA5A5A5A5),
    *_notifications("first", 0, 4, 0), *_notifications("clear", 0, 0, 0),
    *_tipc("display_finalize", 303),
    *(("close_" + name, 0) for name in
      ("vi2", "gsv", "self", "window", "proxy", "applet", "sm")),
    ("fail_step", 0),
)
HANDLE_FIELDS = tuple(name + "_handle" for name in
                      ("sm", "applet", "proxy", "window", "self", "gsv", "vi2"))
FIELD_RECORD = re.compile(r"NX2_VI2 ([a-z][a-z0-9_]*)=([0-9a-f]{8})")
# Strip only record boundaries. Removing ANSI/NUL inside a record could repair
# corrupted evidence into a valid source tag, result, or error diagnostic.
BOUNDARY = re.compile(r"^(?:[\0 \t]|\x1b\[[0-9;]*m)+|(?:[\0 \t]|\x1b\[[0-9;]*m)+$")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\ufffd]")
ERROR = re.compile(r"<(?:Error|Critical)>", re.IGNORECASE)
FAILURE = re.compile(
    r"\bassert(?:ion)?\b|ExceptionRaised|Cannot execute instruction|"
    r"Segmentation fault|\bAborted\b|AddressSanitizer|UndefinedBehaviorSanitizer|"
    r"runtime error:|\b(?:timeout|timed\s*out|timedout|fatal|panic)\b",
    re.IGNORECASE)
STUB = re.compile(r"stub|fallback|unimplemented|not implemented", re.IGNORECASE)
MANAGER_DIAGNOSTIC = re.compile(
    LOG_PREFIX + r"Service\.VI <Warning> "
    r"core/hle/service/vi/application_display_service\.cpp:81:GetManagerDisplayService: "
    r"\(STUBBED\) called")
# Reproduced on the original isolated native controls. These exact errors are
# allowed only before NX2_VI2_BEGIN, within the stated count limits. No AM/VI
# error, SM negative-control error, or shutdown filesystem error is exempted.
STARTUP_ERRORS = (
    ("EMPTY_PATH", 5, re.compile(LOG_PREFIX +
        r"Common\.Filesystem <Error> common/fs/path_util\.cpp:308:SetEdenPath: "
        r"Filesystem object at new_path= is not a directory")),
    ("MISSING_TITLE", 1, re.compile(LOG_PREFIX +
        r"Core <Error> core/core\.cpp:355:Load: Failed to read title for ROM!")),
    ("NETWORK_UNINITIALIZED", 3, re.compile(LOG_PREFIX +
        r"Service <Error> core/hle/service/sockets/bsd\.cpp:1164:BSD_USA: "
        r"Network isn't initialized")),
)


def assess(raw: bytes, process_rc: int) -> bool:
    print(f"NX2_NATIVE_VI2_PROCESS_RC={process_rc}")
    print(f"NX2_NATIVE_VI2_LOG_BYTES={len(raw)}")
    print(f"NX2_NATIVE_VI2_LOG_NUL_COUNT={raw.count(bytes([0]))}")
    if len(raw) > MAX_LOG_SIZE:
        print("NX2_NATIVE_VI2_LOG_LIMIT_EXCEEDED")
        return False
    lines = [BOUNDARY.sub("", line.removesuffix("\r"))
             for line in raw.decode("utf-8", "replace").split("\n")]
    classifications, begins, completions, exits, records = [], [], [], [], []
    protocol_errors, manager_records = [], []
    for index, line in enumerate(lines):
        if CONTROL.search(line):
            protocol_errors.append(f"corrupted record at line {index}")
        if CLASSIFIED.fullmatch(line):
            classifications.append(index)
        elif "Switch 2 program: using the 12 GiB memory layout" in line:
            protocol_errors.append(f"unattributed classification at line {index}")
        if GUEST_EXIT.fullmatch(line):
            exits.append((index, int(line.rsplit(" ", 2)[1])))
        elif "ExitProcess:" in line:
            protocol_errors.append(f"unattributed process exit at line {index}")
        if MANAGER_DIAGNOSTIC.fullmatch(line):
            manager_records.append(index)
        if "NX2_VI2" not in line:
            continue
        output = GUEST_OUTPUT.fullmatch(line)
        if output is None:
            protocol_errors.append(f"unattributed guest record at line {index}")
            continue
        payload = output.group(1)
        if payload == "NX2_VI2_BEGIN":
            begins.append(index)
        elif payload == "NX2_VI2_COMPLETE":
            completions.append(index)
        else:
            record = FIELD_RECORD.fullmatch(payload)
            if record is None:
                protocol_errors.append(f"malformed or failure record at line {index}")
            else:
                records.append((index, record.group(1), int(record.group(2), 16)))

    startup_counts = {name: 0 for name, _, _ in STARTUP_ERRORS}
    unexpected_errors, unexpected_stubs, allowed_startup_records = [], [], []
    for index, line in enumerate(lines):
        if ERROR.search(line):
            allowed = next((name for name, _, pattern in STARTUP_ERRORS
                            if pattern.fullmatch(line) and len(begins) == 1 and
                            index < begins[0]), None)
            if allowed is None:
                unexpected_errors.append(index)
            else:
                startup_counts[allowed] += 1
                allowed_startup_records.append(index)
        if STUB.search(line) and index not in manager_records:
            unexpected_stubs.append(index)
    startup_bounded = all(startup_counts[name] <= limit for name, limit, _ in STARTUP_ERRORS)
    fields_in_order = [name for _, name, _ in records] == [name for name, _ in FIELDS]
    values = {name: value for _, name, value in records}
    values_match = (all(expected is None or values.get(name) == expected
                        for name, expected in FIELDS) and
                    all(value != 0xFFFFFFFF for value in values.values()))
    handles = [values.get(name, 0) for name in HANDLE_FIELDS]
    # Frozen KHandleTable: 15-bit index (<1024), nonzero 15-bit generation,
    # two reserved high bits clear. Successful calls/close results must also exist.
    handles_observed = (len(set(handles)) == len(HANDLE_FIELDS) and
                        all(handle >> 30 == 0 and (handle & 0x7FFF) < 1024 and
                            ((handle >> 15) & 0x7FFF) != 0 for handle in handles))
    aruid = values.get("aruid_lo", 0) | (values.get("aruid_hi", 0) << 32)
    # applet.cpp binds ARUID to its process ID; compare with the actual exit SVC.
    aruid_matches = len(exits) == 1 and aruid != 0 and aruid == exits[0][1]
    events_in_order = (
        len(classifications) == len(begins) == len(completions) == len(exits) ==
        len(manager_records) == 1 and bool(records) and
        classifications[0] < begins[0] < manager_records[0] < records[0][0] and
        records[-1][0] < completions[0] < exits[0][0])
    failed = any(FAILURE.search(line) or "NX2_VI2_FAILURE" in line for line in lines)
    for name, _ in FIELDS:
        value = values.get(name)
        print(f"NX2_NATIVE_VI2_OBSERVED_{name.upper()}=" +
              (f"{value:08x}" if value is not None else "MISSING"))
    for name, _, _ in STARTUP_ERRORS:
        print(f"NX2_NATIVE_VI2_ALLOWED_STARTUP_{name}_ERRORS={startup_counts[name]}")
    for name, value in (
        ("FIELD_COUNT", len(records)), ("FIELDS_IN_ORDER", fields_in_order),
        ("VALUES_MATCH", values_match), ("DISTINCT_HANDLES_OBSERVED", handles_observed),
        ("ARUID_MATCHES_EXIT_PROCESS", aruid_matches), ("EVENTS_IN_ORDER", events_in_order),
        ("KNOWN_MANAGER_STUB_COUNT", len(manager_records)),
        ("STARTUP_ERROR_COUNTS_BOUNDED", startup_bounded),
        ("UNEXPECTED_ERROR_COUNT", len(unexpected_errors)),
        ("UNEXPECTED_STUB_COUNT", len(unexpected_stubs)), ("FAILURE_SEEN", failed),
        ("PROTOCOL_ERRORS", len(protocol_errors)),
    ):
        print(f"NX2_NATIVE_VI2_{name}={int(value)}")
    diagnostics = manager_records + allowed_startup_records + unexpected_errors + unexpected_stubs
    for index in sorted(set(diagnostics))[:20]:
        safe = "".join(c if c.isprintable() else "?" for c in lines[index])
        print(f"NX2_NATIVE_VI2_DIAGNOSTIC[{index}]={safe[:500]}")
    for error in protocol_errors[:10]:
        print(f"NX2_NATIVE_VI2_PROTOCOL_ERROR={error}")
    ok = (process_rc == 0 and fields_in_order and values_match and handles_observed and
          aruid_matches and events_in_order and startup_bounded and not failed and
          not unexpected_errors and not unexpected_stubs and not protocol_errors)
    print("NX2_NATIVE_VI2_CLIENT_LIFECYCLE_PASS" if ok else
          "NX2_NATIVE_VI2_CLIENT_LIFECYCLE_NOT_VERIFIED")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--exit", required=True, type=int, dest="process_rc")
    args = parser.parse_args()
    if args.log.stat().st_size > MAX_LOG_SIZE:
        parser.exit(1, "NX2_NATIVE_VI2_LOG_LIMIT_EXCEEDED\n")
    return 0 if assess(args.log.read_bytes(), args.process_rc) else 1


if __name__ == "__main__":
    raise SystemExit(main())
