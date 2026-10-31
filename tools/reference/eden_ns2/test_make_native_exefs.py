"""Original NX2 synthetic ExeFS fixture checks; no console files."""
import hashlib
import struct
import tempfile
from pathlib import Path
import unittest

from make_native_exefs import (
    MAIN_THREAD_CORE, MAIN_THREAD_PRIORITY, MESSAGE, NPDM_SIZE, NSO_HEADER, PAGE,
    THREAD_INFO_CAPABILITY, TITLE_ID,
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

    def test_main_thread_matches_declared_core_priority_mask(self):
        npdm = build_extended_npdm()
        aci_offset, aci_size = struct.unpack_from("<II", npdm, 0x70)
        kac_offset, kac_size = struct.unpack_from("<II", npdm, aci_offset + 0x30)
        self.assertEqual(kac_size, 4)
        self.assertLessEqual(kac_offset + kac_size, aci_size)
        capability = struct.unpack_from("<I", npdm, aci_offset + kac_offset)[0]
        self.assertEqual(capability, THREAD_INFO_CAPABILITY)
        self.assertEqual(capability & 0xF, 7)
        self.assertEqual(((capability >> 4) & 63, (capability >> 10) & 63),
                         (63, 16))
        self.assertEqual(((capability >> 16) & 255, (capability >> 24) & 255),
                         (0, 3))
        priorities = sum(1 << p for p in range(16, 64))
        cores = sum(1 << c for c in range(4))
        self.assertEqual(npdm[0xE], MAIN_THREAD_PRIORITY)
        self.assertEqual(npdm[0xF], MAIN_THREAD_CORE)
        self.assertNotEqual(priorities & (1 << npdm[0xE]), 0)
        self.assertNotEqual(cores & (1 << npdm[0xF]), 0)

    def test_disallowed_main_priority_or_core_is_refused(self):
        for offset, value in ((0xE, 0), (0xE, 15), (0xE, 64), (0xF, 4)):
            broken = bytearray(build_extended_npdm())
            broken[offset] = value
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                verify_self_authored_fixture(build_nso(), bytes(broken))

    def test_declared_priority_and_core_boundaries_are_inclusive(self):
        for priority in (16, 63):
            for core in (0, 3):
                changed = bytearray(build_extended_npdm())
                changed[0xE], changed[0xF] = priority, core
                with self.subTest(priority=priority, core=core):
                    verify_self_authored_fixture(build_nso(), bytes(changed))

    def test_changed_thread_capability_mask_is_refused(self):
        # Wrong descriptor type, inverted priority range, kernel priorities,
        # disallowed main core, and a capability outside its ACI0 container.
        mutations = (
            (0x580, THREAD_INFO_CAPABILITY ^ 0x8),
            (0x580, 0x0300FC07),
            (0x580, 0x030003F7),
            (0x580, 0x030143F7),
            (0x530, 0x100),
            (0x534, 0),
        )
        for offset, value in mutations:
            broken = bytearray(build_extended_npdm())
            struct.pack_into("<I", broken, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                verify_self_authored_fixture(build_nso(), bytes(broken))

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
