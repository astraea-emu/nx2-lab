#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source identity and original ExeFS negative controls; no network required."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from engine_source_preflight import PATHS, inspect, oid, PreflightError
from smoke_candidate_exefs import assess_silently


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


if __name__ == "__main__":
    unittest.main()
