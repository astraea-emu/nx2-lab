#!/usr/bin/env python3
"""Verify a bounded, path-safe, fully owned local evidence manifest.

This only validates source identity and metadata. It does NOT establish that
an observed behaviour matches Nintendo Switch 2 hardware or host containment.
"""
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

MAX_MANIFEST = 16_384
MAX_SOURCE = 1_048_576
REQUIRED = {"schema", "id", "category", "source_file", "sha256",
            "date_utc", "claims", "limitations"}
CATEGORIES = {"source_owned", "public_specification", "hardware_local_aggregate"}


def unique_object(pairs):
    """Refuse ambiguous JSON objects instead of silently taking the last key."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate evidence field: " + key)
        result[key] = value
    return result


def validate(manifest: Path) -> str:
    base = Path(__file__).resolve().parent.parent
    evidence = (base / "evidence").resolve()
    manifest = manifest.resolve(strict=True)
    if not manifest.is_relative_to(evidence):
        raise ValueError("evidence manifest must be inside evidence/")
    if manifest.stat().st_size > MAX_MANIFEST:
        raise ValueError("oversized evidence manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"),
                      object_pairs_hook=unique_object)
    if (type(data) is not dict or set(data) != REQUIRED or
            type(data["schema"]) is not int or data["schema"] != 1):
        raise ValueError("invalid evidence schema")
    if type(data["category"]) is not str or data["category"] not in CATEGORIES:
        raise ValueError("unrecognized evidence category")
    if not all(type(data[k]) is str and 0 < len(data[k]) <= 256
               for k in ("id", "source_file", "sha256", "date_utc")):
        raise ValueError("invalid evidence identity fields")
    try:
        canonical_date = date.fromisoformat(data["date_utc"]).isoformat()
    except ValueError:
        raise ValueError("date_utc must be a valid YYYY-MM-DD date") from None
    if canonical_date != data["date_utc"]:
        raise ValueError("date_utc must be a valid YYYY-MM-DD date")
    if len(data["sha256"]) != 64 or any(c not in "0123456789abcdef"
                                       for c in data["sha256"]):
        raise ValueError("invalid SHA-256 hex")
    if not isinstance(data["claims"], list) or not data["claims"] or \
            len(data["claims"]) > 16 or not all(
                isinstance(x, str) and 0 < len(x) <= 256 for x in data["claims"]):
        raise ValueError("invalid claims")
    if not isinstance(data["limitations"], list) or not data["limitations"] or \
            len(data["limitations"]) > 16 or not all(
                isinstance(x, str) and 0 < len(x) <= 256 for x in data["limitations"]):
        raise ValueError("missing limitations")
    rel = Path(data["source_file"])
    source = (base / rel).resolve(strict=True)
    if (rel.is_absolute() or not source.is_relative_to((base / "fixtures").resolve())
            or not source.is_file()):
        raise ValueError("reference source outside owned fixtures")
    if source.stat().st_size > MAX_SOURCE:
        raise ValueError("oversized referenced fixture")
    if hashlib.sha256(source.read_bytes()).hexdigest() != data["sha256"]:
        raise ValueError("source digest mismatch")
    return data["id"]


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("usage: verify_evidence.py evidence/FILE.json")
        print("EVIDENCE_SOURCE_IDENTITY_PASS:" + validate(Path(sys.argv[1])))
    except (ValueError, OSError, json.JSONDecodeError, UnicodeError) as err:
        print("EVIDENCE_REFUSED:" + str(err), file=sys.stderr)
        sys.exit(1)
