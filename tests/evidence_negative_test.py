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
    ("array_category", {**original, "category": []}),
    ("bool_schema", {**original, "schema": True}),
    ("float_schema", {**original, "schema": 1.0}),
    ("invalid_date", {**original, "date_utc": "not-a-date"}),
    ("invalid_calendar_date", {**original, "date_utc": "2026-02-30"}),
    ("compact_date", {**original, "date_utc": "20261029"}),
]
raw_probes = [(label, json.dumps(record)) for label, record in probes]
raw_probes += [
    ("duplicate_schema", '{"schema":0,' + json.dumps(original)[1:]),
    ("duplicate_source", '{"source_file":"../README.md",' + json.dumps(original)[1:]),
]
for label, raw in raw_probes:
    # Temporary manifest is inside evidence to ensure we exercise the claimed
    # validation, not merely the path-to-manifest protection.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                 dir=base / "evidence", delete=False) as f:
        f.write(raw)
        path = Path(f.name)
    try:
        try:
            validate(path)
        except (ValueError, OSError):
            continue
        raise AssertionError("invalid manifest admitted: " + label)
    finally:
        path.unlink(missing_ok=True)
print(f"EVIDENCE_NEGATIVE_PASS:{len(raw_probes)}_cases")
