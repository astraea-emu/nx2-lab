#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Require complete computation and natural exit of the labeled NRO variant.

The unchanged NRO is a separate execution-evidence control. This adapted guest
must actually request ExitProcess and finish, rather than merely print that it
is about to exit before timing out or faulting.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from assess_eden_guest import (
    GUEST_START, MAX_LOG_SIZE, decoded_lines, guest_messages,
    has_execution_fault, print_log,
)

REQUIRED_MESSAGES = (
    ("GUEST_DEBUG_SVC", GUEST_START.decode("ascii")),
    ("GUEST_COUNTER", "Contador (.data): 42"),
    ("GUEST_HEAP_SUM", "Suma en el heap: 499500"),
    ("GUEST_FIBONACCI", "fibonacci(50) = 12586269025"),
    ("GUEST_FINAL_OUTPUT", "Adios! (main devuelve -> svcExitProcess)"),
)
EXIT_PROCESS = re.compile(
    r"\bKernel\.SVC\s+<Info>\s+"
    r"core/hle/kernel/svc/svc_process\.cpp:\d+:ExitProcess: Process \d+ exiting\b"
)


def assess(raw: bytes, process_rc: int) -> bool:
    print(f"NX2_ADAPTED_NRO_PROCESS_EXIT={process_rc}")
    print_log("ADAPTED", raw)
    messages = guest_messages(raw)
    previous_index = -1
    computations_ok = True
    for label, expected in REQUIRED_MESSAGES:
        index = next((i for i, message in messages
                      if i > previous_index and message == expected), None)
        observed = index is not None
        print(f"NX2_ADAPTED_{label}={int(observed)}")
        computations_ok &= observed
        if observed:
            previous_index = index
    exit_requested = any(
        i > previous_index and EXIT_PROCESS.search(line)
        for i, line in enumerate(decoded_lines(raw))
    )
    fault = has_execution_fault(raw)
    natural_exit = process_rc == 0
    print(f"NX2_ADAPTED_EXIT_PROCESS_SVC={int(exit_requested)}")
    print(f"NX2_ADAPTED_EXECUTION_FAULT={int(fault)}")
    print(f"NX2_ADAPTED_NATURAL_EXIT={int(natural_exit)}")
    ok = computations_ok and exit_requested and natural_exit and not fault
    print("NX2_ADAPTED_GUEST_COMPUTATION_AND_NATURAL_EXIT_PASS" if ok else
          "NX2_ADAPTED_EXIT_PATH_NOT_VERIFIED")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--exit", required=True, type=int, dest="process_rc")
    args = parser.parse_args()
    if args.log.stat().st_size > MAX_LOG_SIZE:
        parser.exit(1, "NX2_ADAPTED_LOG_OVERSIZE_REFUSED\n")
    return 0 if assess(args.log.read_bytes(), args.process_rc) else 1


if __name__ == "__main__":
    raise SystemExit(main())
