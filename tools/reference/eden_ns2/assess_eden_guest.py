#!/usr/bin/env python3
"""Review bounded Eden-NS2 CLI guest logs without hiding binary output.

Only a string emitted by the original guest counts as evidence of reaching a
guest SVC. The invalid NRO must fail in the loader, not time out or crash.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

GUEST_START = b"Hola desde un NRO en NeXo 2!"
PROGRESS = (
    b"Loader: X1=",
    b"Contador (.data): 42",
    b"Suma en el heap: 499500",
    b"fibonacci(50) = 12586269025",
    b"Adios! (main devuelve -> svcExitProcess)",
)
MAX_LOG_SIZE = 32 * 1024 * 1024
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
GUEST_OUTPUT = re.compile(
    r"\bDebug\.Emulated\s+<Info>\s+"
    r"core/hle/kernel/svc/svc_debug_string\.cpp:\d+:OutputDebugString:\s*(.*)"
)
LOADER_REJECTION = re.compile(
    r"\b(?:Core|Frontend|Loader)\s+<(?:Critical|Error)>\s+"
    r"(?:core/|yuzu_cmd/)[^\n]*:(?:Load|SDL_AppInit|main):\s*"
    r"(?:Failed to load ROM|Failed to obtain loader)\b"
)
EXECUTION_FAULT = re.compile(
    r"\b(?:Core\.ARM|Debug)\s+<(?:Critical|Error)>|"
    r"\bExceptionRaised\b|Cannot execute instruction|"
    r"\bassert\s*\(|\bassertion failed\b|\bassert failed\b|"
    r"Segmentation fault|AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:",
    re.IGNORECASE,
)
LOG_MATCH = re.compile(
    r"nro|homebrew|loader|svc|thread|error|fault|failed|"
    r"hola desde|contador|suma en el heap|fibonacci|adios|nx2|"
    r"initialized|guest|firmware|profil|process|fatal|critical|"
    r"could not|invalid|SDL|cannot",
    re.IGNORECASE,
)


def decoded_lines(raw: bytes) -> list[str]:
    return ANSI_ESCAPE.sub("", raw.decode("utf-8", "replace")).replace("\0", " ").splitlines()


def guest_messages(raw: bytes) -> list[tuple[int, str]]:
    """Keep only messages attributed to the pinned emulator's debug SVC."""
    messages = []
    for index, line in enumerate(decoded_lines(raw)):
        match = GUEST_OUTPUT.search(line)
        if match:
            messages.append((index, match.group(1).strip()))
    return messages


def has_execution_fault(raw: bytes) -> bool:
    return any(EXECUTION_FAULT.search(line) for line in decoded_lines(raw))


def print_log(label: str, raw: bytes) -> None:
    """Print useful bounded lines, including NUL-containing logs and endings."""
    print(f"NX2_{label}_LOG_BYTES={len(raw)}")
    print(f"NX2_{label}_LOG_NUL_BYTES={raw.count(bytes([0]))}")
    text = raw.decode("utf-8", "replace").replace("\x00", "[NUL]")
    lines = text.splitlines()
    print(f"NX2_{label}_LOG_LINES={len(lines)}")
    # The first and last lines help identify startup failures and timeout paths.
    selected = set(range(min(12, len(lines))))
    selected.update(range(max(0, len(lines) - 35), len(lines)))
    selected.update(i for i, line in enumerate(lines) if LOG_MATCH.search(line))
    order = sorted(selected)
    if len(order) > 120:
        # Explicitly bound noisy warning output while preserving start and tail.
        order = sorted(set(order[:55] + order[-65:]))
    for i in order:
        # Strip terminal control sequences and bound each line.
        clean = "".join(c if c.isprintable() or c == "\t" else "?" for c in lines[i])
        print(f"NX2_{label}_LOG[{i}]={clean[:350]}")


def assess(good_log: bytes, bad_log: bytes, good_exit: int, bad_exit: int) -> bool:
    print(f"NX2_GOOD_NRO_PROCESS_EXIT={good_exit}")
    print(f"NX2_BAD_NRO_PROCESS_EXIT={bad_exit}")
    print_log("GOOD", good_log)
    print_log("BAD", bad_log)
    messages = [message for _, message in guest_messages(good_log)]
    guest_started = GUEST_START.decode("ascii") in messages
    print("NX2_EDEN_GUEST_AUTHORED_DEBUG_STRING_OBSERVED" if guest_started
          else "NX2_EDEN_GUEST_EXECUTION_NOT_VERIFIED")
    for marker in PROGRESS:
        label = marker.decode("ascii")
        observed = any(message.startswith(label) for message in messages)
        print(f"NX2_EDEN_GUEST_MARKER_{'OBSERVED' if observed else 'NOT_OBSERVED'}={label}")
    if good_exit in (124, 137):
        print("NX2_EDEN_POSITIVE_DID_NOT_EXIT_NATURALLY")
    if good_exit < 0:
        print("NX2_EDEN_POSITIVE_SIGNAL_FAILURE")
    # SDL_APP_FAILURE maps to 1 for this frozen CLI. A signal encoded by the
    # shell (for example 139), a timeout or an unrelated nonzero exit is not a
    # successful invalid-image rejection, even if a loader line preceded it.
    loader_rejected = any(LOADER_REJECTION.search(line) for line in decoded_lines(bad_log))
    bad_exit_ok = bad_exit == 1
    bad_fault = has_execution_fault(bad_log)
    bad_executed = bool(guest_messages(bad_log))
    original_status_ok = good_exit in (0, 124)
    print(f"NX2_EDEN_MALFORMED_LOADER_DIAGNOSTIC={int(loader_rejected)}")
    print(f"NX2_EDEN_MALFORMED_EXITS_WITHOUT_TIMEOUT={int(bad_exit_ok)}")
    print(f"NX2_EDEN_MALFORMED_EXECUTION_FAULT={int(bad_fault)}")
    print(f"NX2_EDEN_MALFORMED_GUEST_OUTPUT={int(bad_executed)}")
    print(f"NX2_EDEN_ORIGINAL_EXECUTION_FAULT={int(has_execution_fault(good_log))}")
    print("NX2_EDEN_ORIGINAL_RESULT_IS_EXECUTION_EVIDENCE_ONLY=1")
    # This control qualifies loader rejection plus ordinary process termination.
    # The frozen generic file detector can also log a crypto-probe assertion on
    # corrupt magic; report it separately instead of claiming assertion-free
    # loader behavior. The adapted lifecycle gate forbids every such fault.
    ok = (guest_started and original_status_ok and loader_rejected and bad_exit_ok
          and not bad_executed)
    print("NX2_EDEN_SOURCE_AUTHORED_GUEST_EXECUTION_PASS" if ok
          else "NX2_EDEN_SOURCE_AUTHORED_GUEST_EXECUTION_INCOMPLETE")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--good-log", type=Path, required=True)
    parser.add_argument("--bad-log", type=Path, required=True)
    parser.add_argument("--good-exit", type=int, required=True)
    parser.add_argument("--bad-exit", type=int, required=True)
    args = parser.parse_args()
    good = args.good_log.read_bytes()
    bad = args.bad_log.read_bytes()
    if len(good) > MAX_LOG_SIZE or len(bad) > MAX_LOG_SIZE:
        parser.exit(1, "NX2_EDEN_LOG_OVERSIZE_REFUSED\n")
    return 0 if assess(good, bad, args.good_exit, args.bad_exit) else 1


if __name__ == "__main__":
    raise SystemExit(main())
