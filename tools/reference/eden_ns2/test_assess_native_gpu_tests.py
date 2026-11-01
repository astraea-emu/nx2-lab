"""Original report mutations prevent incomplete/failed GPU runs passing the gate."""
import copy
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import assess_native_gpu_tests
from assess_native_gpu_tests import EXPECTED_COUNTS, assess, read_report
from overlay_native_gpu_tests import (
    CATCH2_FILTER, COMBINED_FILTER, COMPATIBLE_CASES, EDEN_COMMIT,
    EXISTING_SOURCE_SPECS, ORIGINAL_BLOBS, SOURCE_BLOBS, TEST_PATH, UNRESOLVED_CASES,
)


def inputs():
    records = []
    for name in ([f"Original unchanged case {i}" for i in range(24)] +
                 sorted(COMPATIBLE_CASES) + sorted(UNRESOLVED_CASES)):
        disabled = name in UNRESOLVED_CASES
        disposition = ("unresolved_disabled" if disabled else
                       "compatible" if name in COMPATIBLE_CASES else "unchanged")
        records.append({
            "name": name, "disposition": disposition,
            "expected_registered": not disabled,
            "original_tags": "[native-gpu]",
            "applied_tags": "[native-gpu]" + ("" if disabled else CATCH2_FILTER),
            "original_assertion_expressions": 1, "adapted_assertion_expressions": 1,
            "original_body_sha256": "a" * 64, "adapted_body_sha256": "a" * 64,
            **({"reason": UNRESOLVED_CASES[name]} if disabled else {}),
        })
    existing = []
    for path, (required_tag, count) in EXISTING_SOURCE_SPECS.items():
        for index in range(count):
            extra_tag = ("[storage-ranges]" if path.endswith("native_shader.cpp")
                         and index else "")
            existing.append({
                "name": f"Existing {path} case {index}", "source_path": path,
                "tags": required_tag + extra_tag, "original_line": index + 1,
            })
    manifest = {
        "schema_version": 1, "frozen_commit": EDEN_COMMIT,
        "guarded_original_blobs": dict(ORIGINAL_BLOBS), "modified_path": TEST_PATH,
        "patched_test_blob": "b" * 40, "catch2_filter": CATCH2_FILTER,
        "combined_filter": COMBINED_FILTER,
        "required_environment": {"EDEN_NATIVE_STRICT": "1"},
        "overlay_state": "verified_applied", "counts": dict(EXPECTED_COUNTS),
        "cases": records, "existing_cases": existing,
    }
    listed = ET.Element("MatchingTests")
    report = ET.Element("Catch2TestRun", {"xml-format-version": "3"})
    selected = [{"name": case["name"], "source_path": TEST_PATH,
                 "tags": case["applied_tags"]}
                for case in records if case["expected_registered"]] + existing
    for expected in selected:
        case = ET.SubElement(listed, "TestCase")
        ET.SubElement(case, "Name").text = expected["name"]
        ET.SubElement(case, "Tags").text = expected["tags"]
        source = ET.SubElement(case, "SourceInfo")
        ET.SubElement(source, "File").text = "/tmp/eden/" + expected["source_path"]
        case = ET.SubElement(report, "TestCase", {
            "name": expected["name"], "tags": expected["tags"],
            "filename": "/tmp/eden/" + expected["source_path"],
        })
        ET.SubElement(case, "OverallResult", {"success": "true", "skips": "0"})
    for tag, successes in (("OverallResults", "100"), ("OverallResultsCases", "62")):
        ET.SubElement(report, tag, {"successes": successes, "failures": "0",
                                   "expectedFailures": "0", "skips": "0"})
    return manifest, listed, report


class GpuReportTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.listed, self.results = inputs()

    def assess(self, status=0, strict="1"):
        return assess(self.manifest, ET.tostring(self.listed),
                      ET.tostring(self.results), status, strict)

    def test_complete_declared_report_shape(self):
        self.assertEqual(self.assess(), {
            "executed_cases": 62, "restored_cases": 29, "existing_cases": 33,
            "unresolved_cases": 2, "assertions": 100,
        })

    def test_crashes_and_timeouts_fail(self):
        for status in (1, 124, 137, -11):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.assess(status=status)

    def test_strict_mode_is_required(self):
        for value in ("", "0", "true"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.assess(strict=value)

    def test_wrong_source_or_unverified_overlay(self):
        for key, value in (("frozen_commit", "0" * 40), ("overlay_state", "applied"),
                           ("schema_version", True), ("guarded_original_blobs", {})):
            original = self.manifest[key]
            self.manifest[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.assess()
            self.manifest[key] = original

    def test_reviewed_candidate_requires_its_own_source_guards(self):
        candidate = next(revision for revision in SOURCE_BLOBS if revision != EDEN_COMMIT)
        self.manifest["frozen_commit"] = candidate
        with self.assertRaisesRegex(ValueError, "source identity mismatch"):
            self.assess()
        self.manifest["guarded_original_blobs"] = dict(SOURCE_BLOBS[candidate])
        self.assertEqual(self.assess()["executed_cases"], 62)
        self.manifest["frozen_commit"] = EDEN_COMMIT
        with self.assertRaisesRegex(ValueError, "source identity mismatch"):
            self.assess()

    def test_changed_body_or_removed_assertion_fails(self):
        for key, value in (("adapted_body_sha256", "b" * 64),
                           ("original_body_sha256", None),
                           ("adapted_assertion_expressions", 0)):
            original = self.manifest["cases"][0][key]
            self.manifest["cases"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.assess()
            self.manifest["cases"][0][key] = original

    def test_manifest_cannot_hide_an_unresolved_case(self):
        self.manifest["cases"][-1]["expected_registered"] = True
        with self.assertRaises(ValueError):
            self.assess()

    def test_missing_registration(self):
        self.listed.remove(self.listed[0])
        with self.assertRaises(ValueError):
            self.assess()

    def test_duplicate_registration_cannot_replace_another_case(self):
        self.listed[1].find("Name").text = self.listed[0].findtext("Name")
        with self.assertRaises(ValueError):
            self.assess()

    def test_registered_source_and_tag_are_required(self):
        self.listed[0].find("SourceInfo/File").text = "/tmp/unrelated.cpp"
        with self.assertRaises(ValueError):
            self.assess()
        self.listed[0].find("SourceInfo/File").text = "/tmp/eden/" + TEST_PATH
        self.listed[0].find("Tags").text = "[native-gpu]"
        with self.assertRaises(ValueError):
            self.assess()

    def test_missing_execution_even_with_forged_totals(self):
        self.results.remove(self.results[0])
        with self.assertRaises(ValueError):
            self.assess()

    def test_duplicate_execution(self):
        self.results.insert(0, copy.deepcopy(self.results[0]))
        with self.assertRaises(ValueError):
            self.assess()

    def test_failure_skip_and_expected_failure_totals(self):
        for key in ("failures", "expectedFailures", "skips"):
            total = self.results.find("OverallResults")
            total.set(key, "1")
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.assess()
            total.set(key, "0")

    def test_failed_or_skipped_case_with_false_success_totals(self):
        outcome = self.results[0].find("OverallResult")
        outcome.set("success", "false")
        with self.assertRaises(ValueError):
            self.assess()
        outcome.set("success", "true")
        outcome.set("skips", "1")
        with self.assertRaises(ValueError):
            self.assess()

    def test_missing_totals_or_empty_assertions(self):
        self.results.find("OverallResults").set("successes", "0")
        with self.assertRaises(ValueError):
            self.assess()
        self.results.remove(self.results.find("OverallResults"))
        with self.assertRaises(ValueError):
            self.assess()

    def test_unresolved_dma_case_not_silently_admitted(self):
        self.results[0].set("name", next(iter(UNRESOLVED_CASES)))
        with self.assertRaises(ValueError):
            self.assess()

    def test_wrong_xml_and_external_declarations(self):
        for raw in (b"<MatchingTests/>", b"not XML", b'<!DOCTYPE x><Catch2TestRun/>'):
            with self.subTest(raw=raw), self.assertRaises((ValueError, ET.ParseError)):
                assess(self.manifest, ET.tostring(self.listed), raw, 0, "1")

    def test_report_files_are_bounded_before_json_or_xml_parsing(self):
        # The same bounded reader admits the manifest, listing and result XML.
        for name in ("manifest.json", "listed.xml", "results.xml"):
            stream = io.BytesIO(bytes(100))
            with self.subTest(name=name), \
                    patch.object(assess_native_gpu_tests, "MAX_REPORT", 16), \
                    patch.object(Path, "open", return_value=stream), \
                    patch.object(stream, "read", wraps=stream.read) as read:
                with self.assertRaisesRegex(ValueError, "oversized report"):
                    read_report(Path(name))
                read.assert_called_once_with(17)

    def test_report_reader_preserves_exact_valid_bytes(self):
        raw = b'{"manifest": 1}\n'
        with patch.object(Path, "open", return_value=io.BytesIO(raw)):
            self.assertEqual(read_report(Path("manifest.json")), raw)

    def test_unrelated_33_cases_cannot_replace_the_previous_native_cases(self):
        for case in self.results.findall("TestCase")[-33:]:
            case.set("name", "Unrelated " + case.get("name"))
            case.set("tags", "[unrelated]")
            case.set("filename", "/tmp/not-the-frozen-native-tests.cpp")
        with self.assertRaises(ValueError):
            self.assess()

    def test_unknown_prior_name_in_both_reports_still_fails_source_inventory(self):
        self.listed[-1].find("Name").text = "Unrelated replacement"
        self.results.findall("TestCase")[-1].set("name", "Unrelated replacement")
        with self.assertRaises(ValueError):
            self.assess()

    def test_missing_prior_registration_or_execution_cannot_hide_in_totals(self):
        self.listed.remove(self.listed[-1])
        with self.assertRaises(ValueError):
            self.assess()
        self.manifest, self.listed, self.results = inputs()
        self.results.remove(self.results.findall("TestCase")[-1])
        with self.assertRaises(ValueError):
            self.assess()

    def test_restored_only_registration_is_not_the_combined_inventory(self):
        for case in list(self.listed)[29:]:
            self.listed.remove(case)
        with self.assertRaises(ValueError):
            self.assess()

    def test_prior_registration_source_and_tags_must_match_frozen_inventory(self):
        for field, value in (("SourceInfo/File", "/tmp/unrelated.cpp"),
                             ("SourceInfo/File", None), ("Tags", "[unrelated]"),
                             ("Tags", None), ("Tags", "[native-gpu]")):
            self.manifest, self.listed, self.results = inputs()
            self.listed[-1].find(field).text = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.assess()

    def test_prior_execution_source_and_tags_are_bound_to_registration(self):
        for field, value in (("filename", "/tmp/other/src/tests/video_core/native_shader.cpp"),
                             ("filename", "/tmp/unrelated.cpp"),
                             ("tags", "[unrelated]"), ("tags", "[native-gpu]")):
            self.manifest, self.listed, self.results = inputs()
            self.results.findall("TestCase")[-1].set(field, value)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.assess()

    def test_every_case_requires_explicit_zero_skips(self):
        for index in (0, -1):
            self.manifest, self.listed, self.results = inputs()
            outcome = self.results.findall("TestCase")[index].find("OverallResult")
            del outcome.attrib["skips"]
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.assess()

    def test_manifest_existing_inventory_cannot_drop_a_case_or_change_its_source_group(self):
        self.manifest["existing_cases"].pop()
        with self.assertRaises(ValueError):
            self.assess()
        self.manifest, self.listed, self.results = inputs()
        self.manifest["existing_cases"][-1]["source_path"] = \
            "src/tests/video_core/native_semaphore.cpp"
        with self.assertRaises(ValueError):
            self.assess()

    def test_manifest_existing_tags_and_source_guards_are_required(self):
        self.manifest["existing_cases"][0]["tags"] = "[unrelated]"
        with self.assertRaises(ValueError):
            self.assess()
        self.manifest, self.listed, self.results = inputs()
        path = next(iter(EXISTING_SOURCE_SPECS))
        self.manifest["guarded_original_blobs"][path] = "0" * 40
        with self.assertRaises(ValueError):
            self.assess()

    def test_equivalent_tag_order_does_not_change_case_identity(self):
        self.listed[-1].find("Tags").text = "[storage-ranges][native-gpu]"
        self.assertEqual(self.assess()["executed_cases"], 62)


if __name__ == "__main__":
    unittest.main()
