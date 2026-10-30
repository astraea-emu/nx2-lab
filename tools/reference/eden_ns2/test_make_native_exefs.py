"""Original NX2 synthetic ExeFS fixture checks; no console files."""
import hashlib
import struct
import tempfile
from pathlib import Path
import unittest

from make_native_exefs import (
    MESSAGE, NPDM_SIZE, NSO_HEADER, PAGE, TITLE_ID,
    build_extended_npdm, build_guest_text, build_nso,
    verify_self_authored_fixture, main,
)


class NativeExeFsTests(unittest.TestCase):
    def test_deterministic_executable(self):
        original = build_nso()
        self.assertEqual(original, build_nso())
        self.assertEqual(len(original), NSO_HEADER + 3 * PAGE)
        self.assertEqual(original[:4], b"NSO0")
        self.assertEqual(struct.unpack_from("<I", original, 0x0C)[0], 0)

    def test_guest_contains_real_arm64_svc_and_bounded_stop(self):
        words = struct.unpack_from("<7I", build_guest_text())
        self.assertEqual(words[0], 0xB0000000)
        self.assertEqual(words[1], 0x91000000)
        self.assertEqual(words[2], 0xD2800001 | (len(MESSAGE) << 5))
        self.assertEqual(words[3], 0xD40004E1)
        self.assertEqual(words[5], 0xD40000E1)
        self.assertEqual(words[6], 0x14000000)

    def test_original_guest_message_maps_to_rodata_page(self):
        nso = build_nso()
        self.assertEqual(nso[NSO_HEADER + PAGE:NSO_HEADER + PAGE + len(MESSAGE)],
                         MESSAGE)

    def test_three_segment_hashes_are_independent(self):
        nso = build_nso()
        for index in range(3):
            offset, mem, size, reserved = struct.unpack_from(
                "<IIII", nso, 0x10 + 16 * index)
            self.assertEqual(offset, NSO_HEADER + PAGE * index)
            self.assertEqual(mem, PAGE * index)
            self.assertEqual(size, PAGE)
            self.assertEqual(reserved, PAGE)
            self.assertEqual(
                hashlib.sha256(nso[offset:offset + size]).digest(),
                nso[0xA0 + 0x20 * index:0xC0 + 0x20 * index],
            )

    def test_extended_acid_never_claims_device_provenance(self):
        npdm = build_extended_npdm()
        self.assertEqual(len(npdm), NPDM_SIZE)
        self.assertEqual(npdm[:4], b"META")
        self.assertEqual(npdm[0x380:0x384], b"ACID")
        self.assertNotEqual(npdm[0x280:0x284], b"ACID")
        self.assertEqual(npdm[0x500:0x504], b"ACI0")
        self.assertEqual(struct.unpack_from("<Q", npdm, 0x510)[0], TITLE_ID)
        self.assertEqual(struct.unpack_from("<I", npdm, 0x7C)[0], 0x380)

    def test_valid_fixture_pair(self):
        verify_self_authored_fixture(build_nso(), build_extended_npdm())

    def test_corrupted_header_or_data_hash_is_refused(self):
        base = bytearray(build_nso())
        for offset, byte in [(0, ord("X")), (NSO_HEADER, 0xFF)]:
            broken = bytearray(base)
            broken[offset] = byte
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                verify_self_authored_fixture(bytes(broken), build_extended_npdm())

    def test_corrupted_extended_metadata_is_refused(self):
        bad = bytearray(build_extended_npdm())
        bad[0x380] = 0
        with self.assertRaises(ValueError):
            verify_self_authored_fixture(build_nso(), bytes(bad))

    def test_cli_produces_only_two_expected_original_files(self):
        import subprocess
        import sys
        script = Path(__file__).with_name("make_native_exefs.py")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "exefs"
            p = subprocess.run([sys.executable, str(script), "--output", str(out)],
                               text=True, capture_output=True, check=True)
            self.assertIn("NX2_ORIGINAL_EXTENDED_EXEFS_FIXTURE_PASS", p.stdout)
            self.assertEqual({f.name for f in out.iterdir()}, {"main", "main.npdm"})
            verify_self_authored_fixture((out / "main").read_bytes(),
                                         (out / "main.npdm").read_bytes())


if __name__ == "__main__":
    unittest.main()
