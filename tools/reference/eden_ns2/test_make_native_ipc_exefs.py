"""Original IPC guest compile/format checks, never emulator execution."""
import hashlib
import os
import struct
import unittest

from make_native_exefs import NSO_HEADER, PAGE, build_extended_npdm, build_nso
from make_native_ipc_exefs import (
    FIELDS, build_ipc_nso, compile_segments, verify_ipc_fixture,
)


class NativeIpcFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sections = compile_segments(os.environ.get("NX2_AARCH64_PREFIX", "aarch64-linux-gnu-"))
        cls.nso = build_ipc_nso(cls.sections)
        cls.npdm = build_extended_npdm()

    def test_valid_original_fixture(self):
        verify_ipc_fixture(self.nso, self.npdm)
        self.assertEqual(len(self.nso), 12544)
        self.assertEqual(len(self.npdm), 1536)

    def test_actual_assembly_requests_match_independent_libnx_host_vectors(self):
        expected_initialize = bytes.fromhex(
            "040000000a000080010000000000000000000000000000000000000000000000"
            "5346434900000000000000000000000000000000000000000000000000000000")
        expected_get = bytes.fromhex(
            "040000000a000000000000000000000053464349000000000100000000000000"
            "7365740000000000000000000000000000000000000000000000000000000000")
        self.assertEqual(self.sections[1][:64], expected_initialize)
        self.assertEqual(self.sections[1][64:128], expected_get)
        empty_name = bytearray(expected_get)
        empty_name[0x20:0x28] = bytes(8)
        self.assertEqual(self.sections[1][128:192], bytes(empty_name))

    def test_guest_contains_actual_tls_svc_and_exit_instructions(self):
        text = self.sections[0]
        words = struct.unpack("<" + "I" * (len(text) // 4), text)
        self.assertIn(0xD53BD075, words)  # mrs x21, tpidrro_el0
        for svc in (0x1F, 0x21, 0x16, 0x27, 0x07):
            self.assertIn(0xD4000001 | (svc << 5), words)
        self.assertEqual(words.count(0xD4000001 | (0x21 << 5)), 3)

    def test_result_records_start_unobserved(self):
        self.assertEqual(len(FIELDS), 21)
        self.assertEqual(self.sections[2][:84], b"\xff" * 84)
        self.assertIn(b"NX2_IPC_COMPLETE\n", self.sections[1])
        self.assertIn(b"NX2_IPC_FAILURE\n", self.sections[1])

    def test_independent_repeat_build_is_identical(self):
        repeated = compile_segments(os.environ.get("NX2_AARCH64_PREFIX", "aarch64-linux-gnu-"))
        self.assertEqual(self.sections, repeated)

    def test_baseline_debug_guest_and_npdm_are_unchanged(self):
        self.assertEqual(hashlib.sha256(build_nso()).hexdigest(),
                         "508edcf6870546ed2f67c6ed11f0df3deb0242427ea2b9d7562ae6d015084ed5")
        self.assertEqual(hashlib.sha256(self.npdm).hexdigest(),
                         "64e25a2e3e37495d75341f9564afa3e6a665f10f94b36ea7e4e3c533b4573148")

    def test_corrupted_program_or_header_is_rejected(self):
        for offset in (0, 0x60, NSO_HEADER, NSO_HEADER + PAGE, NSO_HEADER + 2 * PAGE):
            changed = bytearray(self.nso)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                verify_ipc_fixture(bytes(changed), self.npdm)

    def test_rehashed_malformed_request_is_rejected(self):
        sections = list(self.sections)
        damaged = bytearray(sections[1])
        damaged[0x04] = 9
        sections[1] = bytes(damaged)
        with self.assertRaisesRegex(ValueError, "request differs"):
            verify_ipc_fixture(build_ipc_nso(tuple(sections)), self.npdm)

    def test_rehashed_false_result_default_is_rejected(self):
        sections = list(self.sections)
        damaged = bytearray(sections[2])
        damaged[0:4] = bytes(4)
        sections[2] = bytes(damaged)
        with self.assertRaisesRegex(ValueError, "sentinels"):
            verify_ipc_fixture(build_ipc_nso(tuple(sections)), self.npdm)


if __name__ == "__main__":
    unittest.main()
