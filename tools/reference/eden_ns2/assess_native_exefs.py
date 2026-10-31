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

def report(raw: bytes, label: str) -> str:
    text = raw.decode("utf-8", "replace").replace("\0", "[NUL]")
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
    native_classified = "Switch 2 program: using the 12 GiB memory layout" in good
    guest_logged = any(
        MESSAGE in line and "OutputDebugString:" in line and "Debug.Emulated" in line
        for line in good.splitlines()
    )
    invalid_diagnostic = any(t in bad for t in (
        "Failed to load ROM", "Failed to obtain loader", "Error Description:",
        "NPDM file has a bad header", "bad ACID header"
    ))
    invalid_clean = invalid_rc not in (0,124,137) and invalid_rc>0
    has_fault = "Cannot execute instruction at unmapped address" in good or "ExceptionRaised(exception" in good
    print(f"NX2_NATIVE_EXTENDED_CLASSIFIED={int(native_classified)}")
    print(f"NX2_NATIVE_GUEST_ORIGINAL_SVC_OUTPUT={int(guest_logged)}")
    print(f"NX2_NATIVE_GUEST_EXECUTION_FAULT_SEEN={int(has_fault)}")
    print(f"NX2_NATIVE_GUEST_PROCESS_TIMEOUT={int(valid_rc in (124,137))}")
    print(f"NX2_NATIVE_INVALID_EXPLICIT_DIAGNOSTIC={int(invalid_diagnostic)}")
    print(f"NX2_NATIVE_INVALID_CLEAN_REJECTION={int(invalid_clean)}")
    ok=native_classified and guest_logged and invalid_diagnostic and invalid_clean
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
