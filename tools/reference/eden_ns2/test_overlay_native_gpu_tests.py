# SPDX-License-Identifier: GPL-3.0-only
# Earlier MIT-licensed material retains that permission; see LICENSES/MIT.txt.
"""Overlay regressions using original checks and, when supplied, real Eden source.

Set NX2_EDEN_SOURCE to an exact frozen Git checkout for the source-backed cases.
Each case uses a temporary local shared clone and never edits the supplied tree.
The C++ checks compile the actual frozen interpreter header; they are explicitly
not a build or execution of Eden's linked Catch2 target.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import overlay_native_gpu_tests as overlay

SOURCE_ROOT = os.environ.get("NX2_EDEN_SOURCE")
COMPILER = shutil.which(os.environ.get("CXX", "c++"))


class OverlayContractTests(unittest.TestCase):
    def test_blob_identity_matches_git_for_binary_and_text_inputs(self):
        for data in (b"", b"original audit\n", b"\0META\xff\x80\n"):
            with self.subTest(data=data):
                expected = subprocess.check_output(
                    ["git", "hash-object", "--stdin"], input=data).decode().strip()
                self.assertEqual(overlay.git_blob(data), expected)

    def test_unpinned_input_is_refused_before_transforming(self):
        for data in (b"", b"TEST_CASE(\"other\", \"[native-gpu]\") {}\n",
                     b"\xffnot UTF-8"):
            with self.subTest(data=data):
                with self.assertRaisesRegex(ValueError, "frozen source blob"):
                    overlay.transform(data)

    def test_replacement_refuses_missing_or_ambiguous_context(self):
        for source in ("unchanged", "target target"):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    overlay.replace_once(source, "target", "changed")

    def test_non_checkout_cli_refuses_without_writing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                [sys.executable, overlay.__file__, str(root)],
                capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("NX2_NATIVE_GPU_OVERLAY_REFUSED", result.stderr)
            self.assertEqual(list(root.iterdir()), [])


@unittest.skipUnless(SOURCE_ROOT, "set NX2_EDEN_SOURCE for actual frozen-source checks")
class FrozenSourceOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(SOURCE_ROOT).resolve()
        head = overlay.git_output(cls.source, "rev-parse", "HEAD").decode().strip()
        if head != overlay.EDEN_COMMIT:
            raise RuntimeError("NX2_EDEN_SOURCE must point to the exact frozen commit")
        for path, expected in overlay.ORIGINAL_BLOBS.items():
            content = overlay.git_output(cls.source, "show", f"{overlay.EDEN_COMMIT}:{path}")
            if overlay.git_blob(content) != expected:
                raise RuntimeError(f"source object mismatch: {path}")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "eden"
        subprocess.run(
            ["git", "clone", "--quiet", "--shared", "--no-checkout",
             str(self.source), str(self.root)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(self.root), "reset", "--quiet", "--soft", overlay.EDEN_COMMIT],
            check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(self.root), "checkout", overlay.EDEN_COMMIT, "--",
             *overlay.ORIGINAL_BLOBS], check=True, capture_output=True)
        self.original = (self.root / overlay.TEST_PATH).read_bytes()

    def apply(self):
        return overlay.reconcile(self.root)

    def assert_test_unchanged(self):
        self.assertEqual((self.root / overlay.TEST_PATH).read_bytes(), self.original)

    def test_inventory_has_29_selected_and_two_named_unresolved_cases(self):
        manifest = self.apply()
        self.assertEqual(manifest["counts"], {
            "original_cases": 31, "mme_cases": 8, "other_cases": 23,
            "unchanged_bodies": 24, "compatibility_cases": 5,
            "unresolved_disabled": 2, "selected_cases": 29,
            "existing_cases": 33, "combined_selected_cases": 62,
        })
        self.assertEqual(manifest["required_environment"], {"EDEN_NATIVE_STRICT": "1"})
        selected = [case for case in manifest["cases"] if case["expected_registered"]]
        self.assertEqual(len(selected), 29)
        self.assertEqual({case["name"] for case in manifest["cases"]
                          if not case["expected_registered"]}, set(overlay.UNRESOLVED_CASES))
        for case in selected:
            self.assertEqual(case["applied_tags"],
                             "[native-gpu][nx2-native-gpu-restored]")
        self.assertIn("linked Catch2 execution not established", manifest["evidence"])

    def test_existing_inventory_is_derived_from_the_three_guarded_sources(self):
        manifest = self.apply()
        existing = manifest["existing_cases"]
        self.assertEqual(len(existing), 33)
        self.assertEqual(len({case["name"] for case in existing}), 33)
        self.assertEqual(manifest["combined_filter"], "[native-gpu],[graphics-supervisor]")
        for path, (tag, count) in overlay.EXISTING_SOURCE_SPECS.items():
            selected = [case for case in existing if case["source_path"] == path]
            with self.subTest(path=path):
                self.assertEqual(len(selected), count)
                source_lines = (self.root / path).read_text().splitlines()
                for case in selected:
                    self.assertIn(case["name"], source_lines[case["original_line"] - 1])
                    self.assertIn(tag, case["tags"])
        restored = {case["name"] for case in manifest["cases"]}
        self.assertFalse(restored & {case["name"] for case in existing})

    def test_unchanged_bodies_and_disabled_original_expectations_are_retained(self):
        prefix, original_cases = overlay.split_cases(self.original.decode())
        manifest = self.apply()
        patched = (self.root / overlay.TEST_PATH).read_text()
        self.assertTrue(patched.startswith(prefix + overlay.MME_ENCODER))
        self.assertEqual(len(original_cases), len(manifest["cases"]))
        for case, record in zip(original_cases, manifest["cases"]):
            with self.subTest(case=case.name):
                self.assertEqual(record["name"], case.name)
                self.assertEqual(record["original_assertion_expressions"],
                                 record["adapted_assertion_expressions"])
                if record["disposition"] != "compatible":
                    self.assertEqual(record["original_body_sha256"],
                                     record["adapted_body_sha256"])
                    self.assertIn(case.body, patched)
                if record["disposition"] == "unresolved_disabled":
                    self.assertIn(
                        "#if 0 // NX2_UNRESOLVED_DMA_CONTRACT: retained, not passed\n"
                        + case.header + case.body
                        + "#endif // NX2_UNRESOLVED_DMA_CONTRACT\n", patched)
        self.assertEqual(patched.count("TEST_CASE("), 31)
        self.assertEqual(patched.count(overlay.CATCH2_FILTER), 29)
        self.assertEqual(patched.count("#if 0 // NX2_UNRESOLVED_DMA_CONTRACT"), 2)

    def test_production_sources_and_original_cmake_entry_are_not_changed(self):
        self.apply()
        for path, expected in overlay.ORIGINAL_BLOBS.items():
            if path != overlay.TEST_PATH:
                with self.subTest(path=path):
                    self.assertEqual(overlay.git_blob((self.root / path).read_bytes()), expected)

    def test_drift_in_each_guarded_input_refuses_before_test_write(self):
        for relative in overlay.ORIGINAL_BLOBS:
            path = self.root / relative
            original = path.read_bytes()
            with self.subTest(path=relative):
                path.write_bytes(original + b"\n")
                try:
                    with self.assertRaisesRegex(ValueError, "frozen source mismatch"):
                        self.apply()
                    if relative != overlay.TEST_PATH:
                        self.assert_test_unchanged()
                    else:
                        self.assertEqual(path.read_bytes(), original + b"\n")
                finally:
                    path.write_bytes(original)

    def test_existing_whole_file_exclusion_is_refused(self):
        path = self.root / overlay.CMAKE_PATH
        original = path.read_text()
        path.write_text(original.replace("    core/native_gpu_characteristics.cpp\n", ""))
        with self.assertRaisesRegex(ValueError, "frozen source mismatch"):
            self.apply()
        self.assert_test_unchanged()

    def test_wrong_head_refuses_before_writing(self):
        subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=NX2 local test",
             "-c", "user.email=nx2-test@example.invalid", "commit", "--quiet",
             "--allow-empty", "-m", "Local wrong-head regression"],
            check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, "wrong Eden revision"):
            self.apply()
        self.assert_test_unchanged()

    def test_subdirectory_is_not_treated_as_checkout_root(self):
        with self.assertRaisesRegex(ValueError, "exact Eden checkout root"):
            overlay.reconcile(self.root / "src")
        self.assert_test_unchanged()

    def test_source_symlink_cannot_redirect_the_write(self):
        path = self.root / overlay.TEST_PATH
        external = self.workspace / "outside.cpp"
        external.write_bytes(self.original)
        path.unlink()
        path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "in-checkout path"):
            self.apply()
        self.assertEqual(external.read_bytes(), self.original)

    def test_second_apply_refuses_but_verify_applied_is_read_only(self):
        applied = self.apply()
        after = (self.root / overlay.TEST_PATH).read_bytes()
        with self.assertRaisesRegex(ValueError, "frozen source mismatch"):
            self.apply()
        verified = overlay.reconcile(self.root, verify_applied=True)
        self.assertEqual(verified["overlay_state"], "verified_applied")
        self.assertEqual(verified["patched_test_blob"], applied["patched_test_blob"])
        self.assertEqual((self.root / overlay.TEST_PATH).read_bytes(), after)

    def test_verify_applied_rejects_unapplied_or_modified_results(self):
        with self.assertRaisesRegex(ValueError, "frozen source mismatch"):
            overlay.reconcile(self.root, verify_applied=True)
        self.apply()
        path = self.root / overlay.TEST_PATH
        path.write_bytes(path.read_bytes() + b"// drift\n")
        with self.assertRaisesRegex(ValueError, "frozen source mismatch"):
            overlay.reconcile(self.root, verify_applied=True)

    def test_cli_exports_auditable_manifest_without_claiming_execution(self):
        manifest_path = self.workspace / "manifest.json"
        result = subprocess.run(
            [sys.executable, overlay.__file__, str(self.root),
             "--manifest", str(manifest_path)],
            capture_output=True, text=True, check=True)
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["counts"]["selected_cases"], 29)
        self.assertEqual(manifest["frozen_commit"], overlay.EDEN_COMMIT)
        self.assertEqual(manifest["guarded_original_blobs"], overlay.ORIGINAL_BLOBS)
        self.assertIn("NX2_NATIVE_GPU_LINKED_CATCH2_EXECUTION_NOT_ESTABLISHED", result.stdout)
        self.assertNotIn("_PASS", result.stdout)
        self.assertEqual(result.stdout.count("NX2_NATIVE_GPU_UNRESOLVED="), 2)

    def compile_and_run(self, source):
        program = self.workspace / "actual_header_check.cpp"
        program.write_text(source)
        binary = self.workspace / "actual_header_check"
        subprocess.run(
            [COMPILER, "-std=c++20", "-O2", "-Wall", "-Wextra", "-pedantic",
             "-I", str(self.root / "src/video_core"), str(program), "-o", str(binary)],
            check=True, capture_output=True, text=True)
        return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout

    @unittest.skipUnless(COMPILER, "a C++20 compiler is required for the actual-header check")
    def test_encoder_matches_actual_decoder_including_word_order_and_fifo_loads(self):
        source = """
#include <iostream>
#include "macro_turing.h"
using u32 = std::uint32_t;
""" + overlay.MME_ENCODER + """
int main() {
    using Interpreter = Tegra::TuringMacroInterpreter;
    std::array<Interpreter::Decoded, 1> input{};
    auto& d = input[0];
    d.src_a.fill(24); d.src_b.fill(24); d.dst.fill(24); d.pred_reg = 24;
    const auto nop = Nx2EncodeMmeProgram(input);
    if (nop != std::array<u32, 3>{0x00000003, 0x18c00000, 0x318c0300}) return 1;
    d.imm = {0xffff, 0x8000}; d.op = {31, 22}; d.dst = {23, 24};
    d.src_a = {25, 28}; d.src_b = {29, 24};
    d.out_method = {5, 6}; d.out_emit = {3, 4};
    d.pred_reg = 29; d.pred_mode = 15; d.end = true;
    const auto encoded = Nx2EncodeMmeProgram(input);
    const auto result = Interpreter::Decode({encoded[2], encoded[1], encoded[0]});
    if (result.imm != d.imm || result.op != d.op || result.dst != d.dst ||
        result.src_a != d.src_a || result.src_b != d.src_b ||
        result.out_method != d.out_method || result.out_emit != d.out_emit ||
        result.pred_reg != d.pred_reg || result.pred_mode != d.pred_mode ||
        result.end != d.end || !result.load[0] || !result.load[1]) return 2;
    std::cout << "actual frozen decoder roundtrip verified\\n";
}
"""
        self.assertEqual(self.compile_and_run(source),
                         "actual frozen decoder roundtrip verified\n")

    @unittest.skipUnless(COMPILER, "a C++20 compiler is required for the actual-header check")
    def test_five_adapted_bodies_execute_against_actual_header_not_full_target(self):
        # Upstream bodies are read only from the supplied GPL checkout and are
        # copied only into this temporary derived check. They are not vendored.
        _, cases = overlay.split_cases(self.original.decode())
        cases = [case for case in cases if case.name in overlay.COMPATIBLE_CASES]
        source = """
// Temporary derived source check; upstream test portions remain GPL-3.0-or-later.
#include <iostream>
#include <stdexcept>
#include "macro_turing.h"
using u32 = std::uint32_t;
static unsigned assertion_evaluations = 0;
void require(bool value, int line) {
    ++assertion_evaluations;
    if (!value) throw std::runtime_error("original expectation failed at " + std::to_string(line));
}
#define REQUIRE(...) require(bool((__VA_ARGS__)), __LINE__)
#define REQUIRE_FALSE(...) require(!bool((__VA_ARGS__)), __LINE__)
""" + overlay.MME_ENCODER
        for index, case in enumerate(cases):
            source += f"\nvoid check_{index}() {{" + overlay.adapt_case(case)
        source += "\nint main() {\n"
        source += "".join(f"    check_{index}();\n" for index in range(len(cases)))
        source += """
    if (assertion_evaluations != 131) return 1;
    std::cout << "5 adapted bodies; 131 assertion evaluations; not the linked Catch2 target\\n";
}
"""
        self.assertEqual(
            self.compile_and_run(source),
            "5 adapted bodies; 131 assertion evaluations; not the linked Catch2 target\n")


if __name__ == "__main__":
    unittest.main()
