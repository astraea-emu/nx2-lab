#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind the actual tracked NX2OWNED fixtures to their declared CLI outcomes.

Identity hashes do not prove runtime behavior. These checks run the files that
the evidence manifests reference; expected results are independent of their
instruction bytes. A matching message must never hide a failed process.
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
COMMON = ["research_only=1", "switch2_guest_execution=0", "image_format=NX2OWNED_v1"]
EXPECTED = {
    "demo": COMMON + ["stop=breakpoint_before_retirement", "retired=2", "pc=8", "x0=43"],
    "service": COMMON + ["stop=service_request_before_retirement", "retired=2", "pc=8",
                          "x0=7", "service_immediate=4660", "caller_x1=9",
                          "service_dispatched=0"],
}


def check_result(result: subprocess.CompletedProcess, kind: str) -> None:
    if result.returncode != 0:
        raise AssertionError(f"{kind} fixture process failed: exit {result.returncode}")
    if result.stderr:
        raise AssertionError(f"{kind} fixture wrote unexpected stderr: {result.stderr}")
    if result.stdout.splitlines() != EXPECTED[kind]:
        raise AssertionError(f"{kind} fixture outcomes differ: {result.stdout!r}")


class OwnedFixtureCliTests(unittest.TestCase):
    binary: Path

    @classmethod
    def execute(cls, fixture: Path) -> subprocess.CompletedProcess:
        return subprocess.run([str(cls.binary), "run-owned", str(fixture)],
                              capture_output=True, text=True, timeout=10, check=False)

    @staticmethod
    def fixture(kind: str) -> Path:
        return ROOT / "fixtures" / f"owned-aarch64-{kind}.nx2o"

    def test_actual_demo_fixture_outcomes(self):
        check_result(self.execute(self.fixture("demo")), "demo")

    def test_actual_service_fixture_outcomes(self):
        check_result(self.execute(self.fixture("service")), "service")

    def test_changed_demo_value_is_rejected_despite_successful_stop(self):
        changed = bytearray(self.fixture("demo").read_bytes())
        entry = struct.unpack_from("<I", changed, 8)[0]
        at = 16 + entry
        word = struct.unpack_from("<I", changed, at)[0]
        struct.pack_into("<I", changed, at, word ^ (1 << 5))
        with tempfile.TemporaryDirectory(prefix="nx2-fixture-value-") as temporary:
            fixture = Path(temporary) / "changed.nx2o"
            fixture.write_bytes(changed)
            result = self.execute(fixture)
        self.assertEqual(result.returncode, 0)
        self.assertIn("stop=breakpoint_before_retirement", result.stdout)
        with self.assertRaisesRegex(AssertionError, "outcomes differ"):
            check_result(result, "demo")

    def test_changed_service_immediate_is_rejected_despite_successful_stop(self):
        changed = bytearray(self.fixture("service").read_bytes())
        count = struct.unpack_from("<I", changed, 12)[0]
        words = struct.unpack_from("<" + "I" * count, changed, 16)
        positions = [index for index, word in enumerate(words)
                     if word & 0xFFE0001F == 0xD4000001]
        self.assertEqual(len(positions), 1)
        index = positions[0]
        struct.pack_into("<I", changed, 16 + index * 4, words[index] ^ (1 << 5))
        with tempfile.TemporaryDirectory(prefix="nx2-fixture-service-") as temporary:
            fixture = Path(temporary) / "changed.nx2o"
            fixture.write_bytes(changed)
            result = self.execute(fixture)
        self.assertEqual(result.returncode, 0)
        self.assertIn("stop=service_request_before_retirement", result.stdout)
        with self.assertRaisesRegex(AssertionError, "outcomes differ"):
            check_result(result, "service")

    def test_matching_output_cannot_hide_nonzero_exit(self):
        actual = self.execute(self.fixture("service"))
        check_result(actual, "service")
        failed = subprocess.run(
            [sys.executable, "-c", "import sys; print(sys.argv[1], end=''); sys.exit(9)",
             actual.stdout], capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(failed.stdout, actual.stdout)
        with self.assertRaisesRegex(AssertionError, "exit 9"):
            check_result(failed, "service")

    def test_duplicate_or_partial_success_output_is_rejected(self):
        actual = self.execute(self.fixture("demo"))
        check_result(actual, "demo")
        for text in (actual.stdout + "x0=43\n", "stop=breakpoint_before_retirement\n"):
            with self.subTest(text=text), self.assertRaisesRegex(AssertionError, "outcomes differ"):
                check_result(subprocess.CompletedProcess(actual.args, 0, text, ""), "demo")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: owned_fixture_test.py PATH_TO_NX2LAB")
    OwnedFixtureCliTests.binary = Path(sys.argv[1]).resolve(strict=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
