#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Require the declared restored cases in an actual strict Catch2 test run.

Checks source inventory, registered tests, executed results and process status.
This is a reduced native-test qualification, not GPU hardware or frame evidence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from overlay_native_gpu_tests import (
    CATCH2_FILTER, COMBINED_FILTER, COMPATIBLE_CASES, EDEN_COMMIT,
    EXISTING_SOURCE_SPECS, ORIGINAL_BLOBS, TEST_PATH, UNRESOLVED_CASES,
)

EXPECTED_COUNTS = {
    "original_cases": 31, "mme_cases": 8, "other_cases": 23,
    "unchanged_bodies": 24, "compatibility_cases": 5,
    "unresolved_disabled": 2, "selected_cases": 29,
    "existing_cases": 33, "combined_selected_cases": 62,
}
PRIOR_CASES = 33
MAX_REPORT = 32 * 1024 * 1024


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def tag_set(value: str) -> frozenset[str]:
    require(isinstance(value, str), "missing tag inventory")
    tags = re.findall(r"\[[^\[\]]+\]", value)
    require(bool(tags) and "".join(tags) == value and len(tags) == len(set(tags)),
            "malformed or duplicate tags")
    return frozenset(tags)


def source_path(value: str, relative: str) -> str:
    require(isinstance(value, str), "missing case source path")
    normalized = value.replace("\\", "/")
    require(normalized.endswith("/" + relative) or normalized == relative,
            "case came from another source file")
    return normalized


def manifest_cases(manifest: dict) -> tuple[dict, set[str]]:
    require(type(manifest) is dict, "manifest must be an object")
    require(type(manifest.get("schema_version")) is int and
            manifest["schema_version"] == 1, "unsupported manifest schema")
    require(manifest.get("frozen_commit") == EDEN_COMMIT and
            manifest.get("guarded_original_blobs") == ORIGINAL_BLOBS and
            manifest.get("modified_path") == TEST_PATH,
            "manifest source identity mismatch")
    require(manifest.get("catch2_filter") == CATCH2_FILTER and
            manifest.get("combined_filter") == COMBINED_FILTER and
            manifest.get("required_environment") == {"EDEN_NATIVE_STRICT": "1"} and
            manifest.get("overlay_state") == "verified_applied",
            "overlay must be verified after the build under the declared scope")
    require(manifest.get("counts") == EXPECTED_COUNTS,
            "manifest does not preserve the 31 = 24 + 5 + 2 inventory")
    require(isinstance(manifest.get("patched_test_blob"), str) and
            re.fullmatch(r"[0-9a-f]{40}", manifest["patched_test_blob"]) is not None,
            "missing patched source identity")
    cases = manifest.get("cases")
    require(type(cases) is list and len(cases) == 31, "expected 31 case records")
    selected, compatible, disabled, names = set(), set(), set(), set()
    identities = {}
    unchanged = 0
    for case in cases:
        require(type(case) is dict, "invalid case record")
        name = case.get("name")
        require(isinstance(name, str) and name and name not in names,
                "missing or duplicate manifest case name")
        names.add(name)
        disposition = case.get("disposition")
        expected = ("unresolved_disabled" if name in UNRESOLVED_CASES else
                    "compatible" if name in COMPATIBLE_CASES else "unchanged")
        require(disposition == expected, "case disposition changed: " + name)
        count = case.get("original_assertion_expressions")
        require(type(count) is int and count > 0 and
                case.get("adapted_assertion_expressions") == count,
                "assertion inventory changed: " + name)
        require(all(isinstance(case.get(key), str) and
                    re.fullmatch(r"[0-9a-f]{64}", case[key]) is not None
                    for key in ("original_body_sha256", "adapted_body_sha256")),
                "missing original or adapted body identity: " + name)
        if disposition in ("unchanged", "unresolved_disabled"):
            require(case.get("original_body_sha256") ==
                    case.get("adapted_body_sha256"), "original body changed: " + name)
        registered = disposition != "unresolved_disabled"
        require(case.get("expected_registered") is registered,
                "manifest registration mismatch: " + name)
        require(case.get("original_tags") == "[native-gpu]",
                "original restoration tags changed: " + name)
        if registered:
            tags = tag_set(case.get("applied_tags"))
            require(tags == frozenset(("[native-gpu]", CATCH2_FILTER)),
                    "restoration tag missing: " + name)
            selected.add(name)
            identities[name] = (TEST_PATH, tags)
            if disposition == "compatible":
                compatible.add(name)
            else:
                unchanged += 1
        else:
            require(case.get("reason") == UNRESOLVED_CASES[name],
                    "unresolved contract reason changed: " + name)
            disabled.add(name)
    require(len(selected) == 29 and unchanged == 24 and
            compatible == COMPATIBLE_CASES and disabled == UNRESOLVED_CASES.keys(),
            "manifest case accounting mismatch")
    existing = manifest.get("existing_cases")
    require(type(existing) is list and len(existing) == PRIOR_CASES,
            "expected the source-derived 33 existing case records")
    per_source = {path: 0 for path in EXISTING_SOURCE_SPECS}
    for case in existing:
        require(type(case) is dict, "invalid existing case record")
        name, path = case.get("name"), case.get("source_path")
        require(isinstance(name, str) and name and name not in names,
                "missing, duplicate or overlapping existing case name")
        require(path in EXISTING_SOURCE_SPECS, "unknown existing source file")
        require(type(case.get("original_line")) is int and case["original_line"] > 0,
                "missing existing source location")
        tags = tag_set(case.get("tags"))
        required_tag, _ = EXISTING_SOURCE_SPECS[path]
        allowed = {required_tag}
        if path == "src/tests/video_core/native_shader.cpp":
            allowed.add("[storage-ranges]")
        require(required_tag in tags and tags <= allowed,
                "existing case has inappropriate tags")
        names.add(name)
        identities[name] = (path, tags)
        per_source[path] += 1
    require(all(per_source[path] == count
                for path, (_, count) in EXISTING_SOURCE_SPECS.items()),
            "existing per-source case counts changed")
    return identities, selected


def read_xml(raw: bytes, root_name: str) -> ET.Element:
    require(0 < len(raw) <= MAX_REPORT, "missing or oversized Catch2 report")
    require(b"<!DOCTYPE" not in raw and b"<!ENTITY" not in raw,
            "external declarations are not supported")
    root = ET.fromstring(raw)
    require(root.tag == root_name, "unexpected Catch2 XML root")
    return root


def assess(manifest: dict, listed: bytes, results: bytes,
           exit_code: int, strict_mode: str) -> dict:
    require(exit_code == 0, f"Catch2 process failed or timed out: {exit_code}")
    require(strict_mode == "1", "EDEN_NATIVE_STRICT=1 is required")
    identities, expected = manifest_cases(manifest)
    inventory = read_xml(listed, "MatchingTests")
    registered = {}
    for case in inventory.findall("TestCase"):
        name = case.findtext("Name")
        require(name in identities and name not in registered,
                "unexpected or duplicate registered case")
        relative, expected_tags = identities[name]
        tags = tag_set(case.findtext("Tags"))
        require(tags == expected_tags, "registered tags differ from the source inventory")
        path = source_path(case.findtext("SourceInfo/File"), relative)
        registered[name] = (path, tags)
    require(set(registered) == set(identities),
            "combined registration inventory differs from the manifest")

    report = read_xml(results, "Catch2TestRun")
    require(report.get("xml-format-version") == "3", "unsupported Catch2 XML format")
    executed = []
    restored = set()
    for case in report.findall("TestCase"):
        name = case.get("name")
        require(name not in UNRESOLVED_CASES, "unresolved DMA case was silently admitted")
        require(name in registered and name not in executed,
                "missing, undeclared or duplicate executed case")
        outcomes = case.findall("OverallResult")
        require(len(outcomes) == 1 and outcomes[0].get("success") == "true" and
                outcomes[0].get("skips") == "0",
                "failed, skipped or incomplete case: " + name)
        path = source_path(case.get("filename"), identities[name][0])
        tags = tag_set(case.get("tags"))
        require((path, tags) == registered[name],
                "executed source or tags differ from registration: " + name)
        if name in expected:
            restored.add(name)
        executed.append(name)
    require(restored == expected and set(executed) == set(registered),
            "expected all 29 restored and 33 existing native cases to execute")
    for tag in ("OverallResults", "OverallResultsCases"):
        totals = report.findall(tag)
        require(len(totals) == 1, "missing or duplicated totals: " + tag)
        total = totals[0]
        for key in ("failures", "expectedFailures", "skips"):
            require(total.get(key) == "0", "nonzero or missing " + tag + "/" + key)
        successes = total.get("successes", "")
        require(successes.isdecimal(), "invalid success total")
        if tag == "OverallResultsCases":
            require(int(successes) == len(executed), "executed-case total mismatch")
        else:
            require(int(successes) >= sum(c["original_assertion_expressions"]
                    for c in manifest["cases"] if c["expected_registered"]),
                    "assertion count is below the preserved restoration inventory")
    return {"executed_cases": len(executed), "restored_cases": len(restored),
            "existing_cases": PRIOR_CASES, "unresolved_cases": 2,
            "assertions": int(report.find("OverallResults").get("successes"))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--listed", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--exit", type=int, required=True, dest="exit_code")
    args = parser.parse_args()
    try:
        result = assess(json.loads(args.manifest.read_text()), args.listed.read_bytes(),
                        args.results.read_bytes(), args.exit_code,
                        os.environ.get("EDEN_NATIVE_STRICT", ""))
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError) as error:
        parser.exit(1, f"NX2_NATIVE_GPU_RESULTS_REFUSED: {error}\n")
    print("NX2_NATIVE_GPU_RESTORATION_PASS")
    print(json.dumps(result, sort_keys=True))
    print("NX2_NATIVE_GPU_TWO_DMA_CONTRACTS_REMAIN_UNQUALIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
