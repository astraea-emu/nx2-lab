"""Real assembly and corruption controls; these do not execute an emulator."""
import os
import struct
import unittest

from make_native_exefs import NSO_HEADER, PAGE, build_extended_npdm
from make_native_ipc_exefs import ROOT, build_ipc_nso, compile_segments
from make_native_vi2_exefs import read_field_names, verify_vi2_fixture


class NativeVi2FixtureTests(unittest.TestCase):
    @classmethod
    def assemble(cls):
        return compile_segments(
            os.environ.get("NX2_AARCH64_PREFIX", "aarch64-linux-gnu-"),
            source=ROOT / "native_vi2_probe.S", linker=ROOT / "native_vi2_probe.ld")

    @classmethod
    def setUpClass(cls):
        cls.sections = cls.assemble()
        cls.nso = build_ipc_nso(cls.sections)
        cls.npdm = build_extended_npdm()

    def changed_section(self, index, offset, replacement):
        sections = list(self.sections)
        section = bytearray(sections[index])
        section[offset:offset + len(replacement)] = replacement
        sections[index] = bytes(section)
        return build_ipc_nso(tuple(sections))

    def test_valid_actual_assembly_and_independent_request_vectors(self):
        verify_vi2_fixture(self.nso, self.npdm)
        names, start = read_field_names(self.sections[1])
        self.assertEqual(len(names), 215)
        self.assertEqual(len(set(names)), 215)
        self.assertEqual(start, 0x7F0)
        self.assertEqual(len(self.nso), 12544)
        self.assertEqual(len(self.npdm), 1536)

    def test_required_guest_syscalls_and_tls_read_are_present(self):
        text = self.sections[0]
        words = struct.unpack("<" + "I" * (len(text) // 4), text)
        self.assertIn(0xD53BD075, words)  # mrs x21, tpidrro_el0
        for svc in (0x1F, 0x21, 0x16, 0x27, 0x07):
            self.assertIn(0xD4000001 | (svc << 5), words)

    def test_repeat_assembly_is_identical(self):
        self.assertEqual(self.sections, self.assemble())

    def test_corrupted_envelope_or_segments_are_rejected(self):
        for offset in (0, 0x40, 0x60, NSO_HEADER, NSO_HEADER + PAGE,
                       NSO_HEADER + 2 * PAGE):
            damaged = bytearray(self.nso)
            damaged[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                verify_vi2_fixture(bytes(damaged), self.npdm)

    def test_each_rehashed_malformed_request_is_rejected(self):
        for index in range(15):
            offset = 0x7F0 + index * 64
            replacement = bytes([self.sections[1][offset] ^ 1])
            with self.subTest(request=index), self.assertRaisesRegex(ValueError, "requests differ"):
                verify_vi2_fixture(self.changed_section(1, offset, replacement), self.npdm)

    def test_corrupt_names_arrays_order_and_padding_are_rejected(self):
        rodata = self.sections[1]
        cases = ((0, b"bad_name__"), (rodata.index(b"~short_word"), b"~wrong_word"),
                 (rodata.index(b"~first_word"), b"~short_word"), (0x7E5, b"x"))
        for offset, replacement in cases:
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                verify_vi2_fixture(self.changed_section(1, offset, replacement), self.npdm)
        for unterminated in (b"field", b"field\0", b"", b"\xff\0\0"):
            with self.subTest(unterminated=unterminated), self.assertRaises(ValueError):
                read_field_names(unterminated)

    def test_preclaimed_result_or_owned_handle_is_rejected(self):
        for offset, replacement in ((0, bytes(4)), (214 * 4, bytes(4)),
                                    (215 * 4, b"\x01\x80\x00\x00")):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                verify_vi2_fixture(self.changed_section(2, offset, replacement), self.npdm)

    def test_missing_marker_or_changed_npdm_is_rejected(self):
        for marker in (b"NX2_VI2_BEGIN", b"NX2_VI2_COMPLETE", b"NX2_VI2_FAILURE"):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, "marker"):
                verify_vi2_fixture(self.changed_section(1, self.sections[1].index(marker), b"!"),
                                   self.npdm)
        with self.assertRaisesRegex(ValueError, "baseline NPDM"):
            verify_vi2_fixture(self.nso, b"NX2!" + self.npdm[4:])


if __name__ == "__main__":
    unittest.main()
