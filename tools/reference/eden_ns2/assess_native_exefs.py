#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Review actual source-built Eden CLI logs for original extended-ExeFS trial.

A test fixture being generated or an NSO header being parsed is NOT guest
execution. Only the original guest message reported by the real emulator SVC
handler qualifies as guest CPU/HLE progress.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

MESSAGE = "NX2 original extended ExeFS guest reached debug SVC"
MAX_LOG_SIZE = 20 * 1024 * 1024
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LOG_PREFIX = r"(?:\[[ \t]*\d+\.\d+\][ \t]+)?"
CLASSIFIED = re.compile(
    LOG_PREFIX + r"Core <Info> core/core\.cpp:\d+:Load: "
    r"Switch 2 program: using the 12 GiB memory layout"
)
GUEST_OUTPUT = re.compile(
    LOG_PREFIX + r"Debug\.Emulated <Info> core/hle/kernel/svc/svc_debug_string\.cpp:\d+:"
    r"OutputDebugString: " + re.escape(MESSAGE)
)
GUEST_EXIT = re.compile(
    LOG_PREFIX + r"Kernel\.SVC <Info> core/hle/kernel/svc/svc_process\.cpp:\d+:"
    r"ExitProcess: Process \d+ exiting"
)
NPDM_FAILURE = re.compile(
    LOG_PREFIX + r"Core <Critical> core/core\.cpp:\d+:Load: "
    r"Failed to load ROM \(Error 4\)!"
)
FRONTEND_LOADER_FAILURE = re.compile(
    LOG_PREFIX + r"Frontend <Critical> yuzu_cmd/yuzu\.cpp:\d+:SDL_AppInit: "
    + re.escape(
        "While attempting to load the ROM requested, an error occurred. Please "
        "refer to the Eden wiki for more information or the Eden discord for "
        "additional help."
    )
)
EXECUTION_FAILURE = re.compile(
    r"\bassert(?:ion)?\b|ExceptionRaised|Cannot execute instruction at unmapped address|"
    r"Segmentation fault|\bAborted\b|AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:",
    re.IGNORECASE,
)


def normalize(raw: bytes) -> str:
    return ANSI_ESCAPE.sub("", raw.decode("utf-8", "replace")).replace("\0", "[NUL]")


def source_lines(raw: bytes) -> list[str]:
    # NUL separators occur at record boundaries in the real CLI logs. Preserve
    # embedded NUL bytes so corrupted or host-prefixed records cannot be joined.
    text = ANSI_ESCAPE.sub("", raw.decode("utf-8", "replace"))
    return [line.strip("\0") for line in text.splitlines()]


def expected_npdm_rejection(raw: bytes) -> bool:
    # At frozen Eden e2f285ab, ErrorBadNPDMHeader is loader result 4 and
    # SystemResultStatus::ErrorLoader is 7. The logger's enum formatter emits
    # numeric 4; GetResultStatusString supplies the corresponding English text.
    # Bind the complete frontend diagnostic to its real source record, rather
    # than accepting an unrelated Error 4 or a host-echoed description.
    lines = source_lines(raw)
    core = [i for i, line in enumerate(lines) if NPDM_FAILURE.fullmatch(line)]
    frontend = [i for i, line in enumerate(lines)
                if FRONTEND_LOADER_FAILURE.fullmatch(line)]
    if len(core) != 1 or len(frontend) != 1 or core[0] >= frontend[0]:
        return False
    block = lines[frontend[0] + 1:frontend[0] + 4]
    return (len(block) == 3 and block[0] == "" and
            block[1] == "Error Code: 0007-0004" and
            block[2] in ("Error Description: 4",
                         "Error Description: The NPDM file has a bad header."))


def report(raw: bytes, label: str) -> str:
    text = normalize(raw)
    lines = text.splitlines()
    print(f"NX2_NATIVE_{label}_LOG_BYTES={len(raw)}")
    print(f"NX2_NATIVE_{label}_LOG_NUL_COUNT={raw.count(bytes([0]))}")
    terms = ("Switch 2 program", "Loading", "Loader", "OutputDebugString", "ExitProcess",
             "ExceptionRaised", "Failed", "Critical", "Error", "Address", "Invalid", "NPDM",
             "SystemResult", "NX2 original extended")
    selected = set(range(min(10, len(lines))))
    selected.update(range(max(0, len(lines)-15), len(lines)))
    selected.update(i for i,x in enumerate(lines) if any(t in x for t in terms))
    indices = sorted(selected)
    if len(indices)>110:
        indices = sorted(set(indices[:60]+indices[-50:]))
    for i in indices:
        clean = "".join(c if c.isprintable() or c=="\t" else "?" for c in lines[i])
        print(f"NX2_NATIVE_{label}_LOG[{i}]={clean[:360]}")
    return text

def assess(valid_raw: bytes, invalid_raw: bytes, valid_rc: int, invalid_rc: int) -> bool:
    print(f"NX2_NATIVE_VALID_PROCESS_RC={valid_rc}")
    print(f"NX2_NATIVE_INVALID_PROCESS_RC={invalid_rc}")
    good = report(valid_raw, "VALID")
    bad = report(invalid_raw, "INVALID")
    lines = source_lines(valid_raw)
    classifications = [i for i, line in enumerate(lines) if CLASSIFIED.fullmatch(line)]
    outputs = [i for i, line in enumerate(lines) if GUEST_OUTPUT.fullmatch(line)]
    exit_requests = [i for i, line in enumerate(lines) if GUEST_EXIT.fullmatch(line)]
    native_classified = len(classifications) == 1
    guest_logged = len(outputs) == 1
    exited_in_order = (native_classified and guest_logged and len(exit_requests) == 1 and
                       classifications[0] < outputs[0] < exit_requests[0])
    # The negative fixture changes only META magic: an unrelated loader or
    # initialization failure is not the expected NPDM rejection.
    invalid_diagnostic = expected_npdm_rejection(invalid_raw)
    invalid_executed = bool(GUEST_OUTPUT.search(bad) or GUEST_EXIT.search(bad))
    invalid_fault = bool(EXECUTION_FAILURE.search(bad))
    # SDL_APP_FAILURE is 1. A signal or timeout after an error is not rejection.
    invalid_clean = invalid_rc == 1 and not invalid_fault and not invalid_executed
    has_fault = bool(EXECUTION_FAILURE.search(good))
    clean_exit = valid_rc == 0
    print(f"NX2_NATIVE_EXTENDED_CLASSIFIED={int(native_classified)}")
    print(f"NX2_NATIVE_GUEST_ORIGINAL_SVC_OUTPUT={int(guest_logged)}")
    print(f"NX2_NATIVE_GUEST_EXECUTION_FAULT_SEEN={int(has_fault)}")
    print(f"NX2_NATIVE_GUEST_PROCESS_TIMEOUT={int(valid_rc in (124,137))}")
    print(f"NX2_NATIVE_GUEST_EXIT_SVC_IN_ORDER={int(exited_in_order)}")
    print(f"NX2_NATIVE_GUEST_PROCESS_EXIT_SUCCESS={int(clean_exit)}")
    print(f"NX2_NATIVE_INVALID_EXPLICIT_DIAGNOSTIC={int(invalid_diagnostic)}")
    print(f"NX2_NATIVE_INVALID_CLEAN_REJECTION={int(invalid_clean)}")
    print(f"NX2_NATIVE_INVALID_EXECUTED_GUEST={int(invalid_executed)}")
    print(f"NX2_NATIVE_INVALID_FAULT_SEEN={int(invalid_fault)}")
    ok=(native_classified and guest_logged and exited_in_order and clean_exit and
        not has_fault and invalid_diagnostic and invalid_clean)
    print("NX2_NATIVE_EXEFS_GUEST_AND_CONTROL_PASS" if ok else
          "NX2_NATIVE_EXEFS_GUEST_OR_CONTROL_NOT_VERIFIED")
    return ok

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--valid-log",type=Path,required=True)
    p.add_argument("--invalid-log",type=Path,required=True)
    p.add_argument("--valid-exit",type=int,required=True)
    p.add_argument("--invalid-exit",type=int,required=True)
    args=p.parse_args()
    good,bad=args.valid_log.read_bytes(),args.invalid_log.read_bytes()
    if len(good)>MAX_LOG_SIZE or len(bad)>MAX_LOG_SIZE:
        p.exit(1,"NX2_NATIVE_EXEFS_LOG_LIMIT_EXCEEDED\n")
    return 0 if assess(good,bad,args.valid_exit,args.invalid_exit) else 1

if __name__=="__main__":
    raise SystemExit(main())
