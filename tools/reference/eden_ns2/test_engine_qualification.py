#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source identity and original ExeFS negative controls; no network required."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from engine_source_preflight import PATHS, inspect, oid, PreflightError
from smoke_candidate_exefs import assess_silently, lifecycle, fault_signatures


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("remote", "add", "origin", "https://github.com/test/source.git")
        blobs = []
        for path in PATHS:
            data = b"// SPDX-License-Identifier: GPL-3.0-or-later\n"
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            blobs.append(oid(data))
        self.licenses = {}
        for path in ("LICENSE.txt", "LICENSES/GPL-3.0-or-later.txt"):
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"GNU GENERAL PUBLIC LICENSE\nVersion 3\n")
            self.licenses[path] = oid(file.read_bytes())
        (self.root / "src/yuzu_cmd/CMakeLists.txt").write_text(
            "add_executable(yuzu-cmd original.cpp)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "original fixture")
        self.spec = ("test/source", self.git("rev-parse", "HEAD"), tuple(blobs))

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], text=True).strip()

    def test_clean_exact_source_reports_no_runtime_qualification(self):
        receipt = inspect(self.root, self.spec, license_blobs=self.licenses)
        self.assertEqual(len(receipt["verified_blob_oids"]), 7)
        self.assertFalse(receipt["runtime_qualified"])
        self.assertFalse(receipt["complete_third_party_dependency_audit"])

    def test_wrong_commit_rejected(self):
        with self.assertRaisesRegex(PreflightError, "frozen commit"):
            inspect(self.root, (self.spec[0], "0" * 40, self.spec[2]),
                    license_blobs=self.licenses)

    def test_untracked_file_rejected(self):
        (self.root / "untracked").write_text("change")
        with self.assertRaisesRegex(PreflightError, "not clean"):
            inspect(self.root, self.spec, license_blobs=self.licenses)

    def test_wrong_reviewed_blob_rejected(self):
        other = ("0" * 40, *self.spec[2][1:])
        with self.assertRaisesRegex(PreflightError, "Source blob"):
            inspect(self.root, (self.spec[0], self.spec[1], other),
                    license_blobs=self.licenses)

    def test_wrong_repository_rejected(self):
        self.git("remote", "set-url", "origin", "https://github.com/other/source.git")
        with self.assertRaisesRegex(PreflightError, "remote origin"):
            inspect(self.root, self.spec, license_blobs=self.licenses)


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.good = (
            b"[ 0.01] Core <Info> core/core.cpp:355:Load: Switch 2 program: using the 12 GiB memory layout\n"
            b"[ 0.02] Debug.Emulated <Info> core/hle/kernel/svc/svc_debug_string.cpp:25:OutputDebugString: NX2 original extended ExeFS guest reached debug SVC\n"
            b"[ 0.03] Kernel.SVC <Info> core/hle/kernel/svc/svc_process.cpp:40:ExitProcess: Process 1 exiting\n"
        )
        self.bad = (
            b"[ 0.01] Core <Critical> core/core.cpp:355:Load: Failed to load ROM (Error 4)!\n"
            b"[ 0.02] Frontend <Critical> yuzu_cmd/yuzu.cpp:310:SDL_AppInit: While attempting to load the ROM requested, an error occurred. Please refer to the Eden wiki for more information or the Eden discord for additional help.\n"
            b"\nError Code: 0007-0004\nError Description: 4\n"
        )

    def test_original_positive_and_negative_signals(self):
        result = assess_silently(self.good, self.bad, 0, 1)
        self.assertTrue(result["original_controls_pass"])
        self.assertEqual(result["first_stop"], "original_exefs_controls_passed")

    def test_guest_exit_marker_never_overrides_bad_host_exit(self):
        result = assess_silently(self.good, self.bad, 137, 1)
        self.assertFalse(result["original_controls_pass"])
        self.assertEqual(result["first_stop"], "host_did_not_exit_naturally")

    def test_missing_svc_and_corrupt_negative_control_rejected(self):
        self.assertFalse(assess_silently(b"host echo original\n", self.bad, 0, 1)
                         ["original_controls_pass"])
        self.assertFalse(assess_silently(self.good, self.bad + self.good, 0, 1)
                         ["original_controls_pass"])

    def test_malformed_meta_guest_execution_has_explicit_failure_reason(self):
        result = assess_silently(self.good, self.good, 0, 0)
        self.assertFalse(result["original_controls_pass"])
        self.assertEqual(result["first_stop"], "negative_control_guest_executed")
        self.assertEqual(result["negative_guest_debug_records"], 1)
        self.assertEqual(result["negative_guest_kernel_svc_records"], 1)
        self.assertEqual(result["negative_rc"], 0)

    def test_attributed_loader_rejection_with_guest_execution_still_fails(self):
        result = assess_silently(self.good, self.bad + self.good, 0, 1)
        self.assertFalse(result["original_controls_pass"])
        self.assertTrue(result["negative_meta_diagnostic"])
        self.assertEqual(result["first_stop"], "negative_control_guest_executed")

    def test_missing_negative_diagnostic_without_guest_execution_remains_distinct(self):
        result = assess_silently(self.good, b"Frontend <Warning> unknown failure\\n", 0, 1)
        self.assertFalse(result["original_controls_pass"])
        self.assertEqual(result["first_stop"], "negative_loader_diagnostic_not_attributed")
        self.assertEqual(result["negative_guest_debug_records"], 0)
        self.assertEqual(result["negative_guest_kernel_svc_records"], 0)

    def test_fault_taxonomy_is_bounded_and_never_contains_raw_messages(self):
        messages = (
            "[ 0.01] Frontend <Warning> secret.cpp:12:Boot: "
            "Assertion in private-user-path\n"
            "[ 0.02] Kernel.SVC <Error> private.cpp:22:Fault: "
            "ExceptionRaised private-key\n"
            "unattributed runtime error: private-value\n"
        )
        report = fault_signatures(messages.splitlines())
        self.assertEqual(report["categories"]["assertion"], 1)
        self.assertEqual(report["categories"]["guest_exception"], 1)
        self.assertEqual(report["categories"]["runtime_error"], 1)
        self.assertEqual(report["source_stages"]["frontend"], 1)
        self.assertEqual(report["source_stages"]["kernel"], 1)
        self.assertEqual(report["source_stages"]["unclassified"], 1)
        self.assertNotIn("private", str(report))
        self.assertNotIn("secret", str(report))

    def test_soft_assert_source_site_from_exact_public_checkout_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src/core/guest.cpp"
            source.parent.mkdir(parents=True)
            source.write_text("// SPDX-License-Identifier: GPL-3.0-or-later\n")
            raw = ("[ 0.0123] Debug <Critical> core/guest.cpp:1:Run: "
                   "/private/build/src/core/guest.cpp: assert "
                   "private-assertion-argument\n")
            report = fault_signatures(raw.splitlines(), root)
            self.assertEqual(report["source_stages"]["host_debug"], 1)
            self.assertEqual(report["categories"]["assertion"], 1)
            self.assertEqual(report["reviewed_source_assert_sites"],
                             [{"site": "core/guest.cpp:1", "count": 1}])
            self.assertFalse(report["source_assert_site_count_truncated"])
            self.assertNotIn("private", str(report))
            self.assertNotIn("argument", str(report))
            # Attribution is for debugging; a matching source site cannot
            # certify a clean emulator execution or defeat strict assessment.
            assessment = assess_silently(self.good + raw.encode(), self.bad, 0, 1,
                                         root)
            self.assertFalse(assessment["original_controls_pass"])
            self.assertEqual(assessment["first_stop"],
                             "positive_execution_fault_signature_observed")

    def test_fake_and_guest_supplied_fault_sources_remain_unattributed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # A made-up or absolute private file must never be exposed.
            records = [
                "Debug <Critical> /private/home/core/secret.cpp:1:Run: "
                "assert private-key",
                "Debug <Critical> core/missing.cpp:1:Run: assert private-key",
                "Debug.Emulated <Info> core/guest.cpp:1:Run: "
                "assert private-key",
            ]
            report = fault_signatures(records, root)
            self.assertEqual(report["reviewed_source_assert_sites"], [])
            self.assertNotIn("private", str(report))
            self.assertNotIn("secret", str(report))
            self.assertNotIn("key", str(report))

    def test_fault_signatures_remain_strict_runtime_rejection(self):
        positive_fault = self.good + (
            b"[ 1.0] Frontend <Error> file.cpp:1:Start: "
            b"Assertion at private-path\n"
        )
        result = assess_silently(positive_fault, self.bad, 0, 1)
        self.assertFalse(result["original_controls_pass"])
        self.assertEqual(result["first_stop"],
                         "positive_execution_fault_signature_observed")
        self.assertEqual(result["positive_lifecycle"]
                         ["fault_signature_evidence"]["categories"]["assertion"], 1)

        negative_fault = self.bad + b"runtime error: private-token\n"
        result = assess_silently(self.good, negative_fault, 0, 1)
        self.assertFalse(result["original_controls_pass"])
        self.assertEqual(result["first_stop"],
                         "negative_execution_fault_signature_observed")
        self.assertEqual(result["negative_lifecycle"]
                         ["fault_signature_evidence"]["categories"]["runtime_error"], 1)
        self.assertNotIn("private-token", str(result))

    def test_redacted_lifecycle_reports_markers_not_log_content(self):
        raw = self.good + b"\nFrontend <Error> example.cpp:1:Start: private-token\n"
        report = lifecycle(raw)
        self.assertEqual(report["milestones"]["guest_layout"], 1)
        self.assertEqual(report["milestones"]["original_guest_debug"], 1)
        self.assertEqual(report["milestones"]["guest_exit"], 1)
        self.assertEqual(report["last_source_stage"], "frontend")
        self.assertFalse(report["raw_lines_preserved"])
        import json
        receipt = json.dumps(report)
        self.assertNotIn("private-token", receipt)
        self.assertNotIn("example.cpp", receipt)

    def test_absent_log_records_do_not_invent_guest_progress(self):
        report = lifecycle(b"unknown source private-token\n")
        self.assertEqual(report["milestones"]["guest_exit"], 0)
        self.assertEqual(report["last_source_stage"], "unclassified")

    def test_loader_reject_and_timeout_stay_distinct(self):
        result = assess_silently(self.good, self.bad, 0, 137)
        self.assertFalse(result["original_controls_pass"])
        self.assertTrue(result["negative_lifecycle"]["milestones"]["invalid_meta_loader"])
        self.assertTrue(result["negative_lifecycle"]["milestones"]["invalid_meta_frontend"])
        self.assertEqual(result["negative_rc"], 137)


if __name__ == "__main__":
    unittest.main()
