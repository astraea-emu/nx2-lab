#!/usr/bin/env python3
"""Negative metadata checks; no device or third-party input required."""
import json
from pathlib import Path
import tempfile
import sys

base = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(base / "tools"))
from verify_evidence import validate

original = json.loads((base / "evidence/owned-aarch64-fixture.json").read_text())
probes = [
    ("wrong_sha", {**original, "sha256": "0" * 64}),
    ("path_escape", {**original, "source_file": "../README.md"}),
    ("empty_claims", {**original, "claims": []}),
    ("missing_limits", {**original, "limitations": []}),
    ("bad_category", {**original, "category": "verified_switch2_gameplay"}),
]
for label, record in probes:
    # Temporary manifest is inside evidence to ensure we exercise the claimed
    # validation, not merely the path-to-manifest protection.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                 dir=base / "evidence", delete=False) as f:
        json.dump(record, f)
        path = Path(f.name)
    try:
        try:
            validate(path)
        except (ValueError, OSError):
            continue
        raise AssertionError("invalid manifest admitted: " + label)
    finally:
        path.unlink(missing_ok=True)
print("EVIDENCE_NEGATIVE_PASS:5_cases")
