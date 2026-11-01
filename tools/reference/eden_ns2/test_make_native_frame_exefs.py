# SPDX-License-Identifier: GPL-3.0-only
"""Actual assembly and bounded-container regressions; never renderer evidence."""
import hashlib
import os
import struct
import unittest

from make_native_exefs import NSO_HEADER, build_extended_npdm, build_nso
from make_native_frame_exefs import (
    FIELD_COUNT, GPU_SEGMENT_ADDRESSES, GPU_SEGMENT_SIZES, IMAGE_ADDRESS, IMAGE_SIZE,
    MARKERS, REQUEST_BYTES, REQUEST_COUNT,
    REQUEST_SHA256, SEGMENT_ADDRESSES, SEGMENT_SIZES, build_frame_nso,
    compile_frame_segments, read_field_names, read_frame_segments, verify_frame_fixture,
)


class NativeFrameFixtureTests(unittest.TestCase):
    @classmethod
    def assemble(cls, variant=0):
        return compile_frame_segments(
            os.environ.get("NX2_AARCH64_PREFIX", "aarch64-linux-gnu-"), variant=variant)

    @classmethod
    def setUpClass(cls):
        cls.sections = cls.assemble(0)
        cls.alternate = cls.assemble(1)
        cls.nso = build_frame_nso(cls.sections)
        cls.npdm = build_extended_npdm()
        cls.names, cls.request_offset = read_field_names(cls.sections[1])

    def changed_section(self, index, offset, replacement):
        sections = list(self.sections)
        damaged = bytearray(sections[index])
        damaged[offset:offset + len(replacement)] = replacement
        sections[index] = bytes(damaged)
        return build_frame_nso(tuple(sections))

    def test_actual_assembly_matches_independent_libnx_request_vectors(self):
        verify_frame_fixture(self.nso, self.npdm, 0)
        self.assertEqual(len(self.names), FIELD_COUNT)
        self.assertEqual(len(set(self.names)), 281)
        self.assertEqual(self.request_offset, 0xF40)
        requests = self.sections[1][self.request_offset:self.request_offset + REQUEST_BYTES]
        self.assertEqual(len(requests), 35 * 128)
        self.assertEqual(hashlib.sha256(requests).hexdigest(), REQUEST_SHA256)
        # Real request bodies exceed the old 64-byte copier bound.
        for index, count in ((14, 17), (15, 17), (18, 18), (26, 24)):
            self.assertEqual(struct.unpack_from("<I", requests, index * 128 + 4)[0], count)

    def test_frame_mapping_separates_owned_image_pages_from_records(self):
        text, rodata, data = read_frame_segments(self.nso)
        self.assertEqual(tuple(map(len, (text, rodata, data))), SEGMENT_SIZES)
        self.assertEqual(len(self.nso), 33024)
        self.assertEqual(SEGMENT_ADDRESSES, (0, 0x2000, 0x5000))
        start = IMAGE_ADDRESS - SEGMENT_ADDRESSES[2]
        self.assertEqual(start, 4096)
        self.assertEqual(data[start:start + IMAGE_SIZE], bytes(8192))
        self.assertEqual(start + IMAGE_SIZE, len(data))

    def test_required_actual_tls_and_service_instructions_exist(self):
        text = self.sections[0]
        self.assertEqual(len(text) % 4, 0)
        words = struct.unpack("<" + "I" * (len(text) // 4), text)
        self.assertIn(0xD53BD075, words)  # mrs x21, tpidrro_el0
        for svc in (0x1F, 0x21, 0x16, 0x27, 0x07, 0x0B):
            self.assertIn(0xD4000001 | (svc << 5), words)

    def test_variants_change_only_reviewed_drawing_configuration(self):
        verify_frame_fixture(build_frame_nso(self.alternate), self.npdm, 1)
        self.assertEqual(self.sections[0], self.alternate[0])
        self.assertEqual(self.sections[2], self.alternate[2])
        start = self.request_offset + REQUEST_BYTES
        self.assertEqual(self.sections[1][:start], self.alternate[1][:start])
        self.assertEqual(self.sections[1][start + 36:], self.alternate[1][start + 36:])
        self.assertNotEqual(self.sections[1][start:start + 36],
                            self.alternate[1][start:start + 36])
        with self.assertRaisesRegex(ValueError, "selected variant"):
            verify_frame_fixture(self.nso, self.npdm, 1)

    def test_repeated_real_assembly_is_deterministic(self):
        self.assertEqual(self.sections, self.assemble(0))

    def test_existing_baseline_fixture_and_synthetic_npdm_remain_exact(self):
        self.assertEqual(hashlib.sha256(self.nso).hexdigest(),
                         "0272cd78f6aed95464b7980a087ee888459de4fc0922ff7928b02091bd9d465f")
        self.assertEqual(hashlib.sha256(build_frame_nso(self.alternate)).hexdigest(),
                         "020cee2fa09e2663ea9c9685d09b79cadc3376cc9c17be34dc45ec348039ff2a")
        self.assertEqual(hashlib.sha256(build_nso()).hexdigest(),
                         "508edcf6870546ed2f67c6ed11f0df3deb0242427ea2b9d7562ae6d015084ed5")
        self.assertEqual(hashlib.sha256(self.npdm).hexdigest(),
                         "64e25a2e3e37495d75341f9564afa3e6a665f10f94b36ea7e4e3c533b4573148")

    def test_envelope_mapping_hash_and_reserved_corruptions_fail(self):
        offsets = (0, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x2C, 0x3C,
                   0x40, 0x60, 0x6C, 0x9F, 0xA0, NSO_HEADER,
                   NSO_HEADER + 0x2000, NSO_HEADER + 0x5000, len(self.nso) - 1)
        for offset in offsets:
            damaged = bytearray(self.nso)
            damaged[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                verify_frame_fixture(bytes(damaged), self.npdm, 0)
        for wrong_length in (self.nso[:-1], self.nso + b"\0"):
            with self.assertRaisesRegex(ValueError, "length"):
                read_frame_segments(wrong_length)

    def test_each_rehashed_malformed_request_is_rejected(self):
        for index in range(REQUEST_COUNT):
            offset = self.request_offset + index * 128
            changed = bytes([self.sections[1][offset] ^ 1])
            with self.subTest(request=index), self.assertRaisesRegex(ValueError, "requests differ"):
                verify_frame_fixture(self.changed_section(1, offset, changed), self.npdm, 0)

    def test_nonzero_tail_of_largest_request_is_rejected(self):
        offset = self.request_offset + 26 * 128 + 127
        with self.assertRaisesRegex(ValueError, "requests differ"):
            verify_frame_fixture(self.changed_section(1, offset, b"\x01"), self.npdm, 0)

    def test_changed_names_array_order_and_alignment_fail(self):
        rodata = self.sections[1]
        for offset, changed in ((0, b"badname"),
                                (rodata.index(b"~released_word"), b"~unknown__word"),
                                (rodata.index(b"~released_word"), b"~clear_word\0\0\0"),
                                (self.request_offset - 1, b"x")):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                verify_frame_fixture(self.changed_section(1, offset, changed), self.npdm, 0)
        for malformed in (b"", b"field", b"field\0", b"\xff\0\0",
                          b"~wrong_word\0\0", b"field\0" * 282):
            with self.subTest(malformed=malformed[:20]), self.assertRaises(ValueError):
                read_field_names(malformed)

    def test_preclaimed_records_handles_or_host_prefilled_image_fail(self):
        for offset, changed in ((0, bytes(4)), ((FIELD_COUNT - 1) * 4, bytes(4)),
                                (FIELD_COUNT * 4, b"\x01\x80\0\0"),
                                (4096, b"\xff\0\0\xff"),
                                (len(self.sections[2]) - 1, b"\x01")):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "unobserved"):
                verify_frame_fixture(self.changed_section(2, offset, changed), self.npdm, 0)

    def test_drawing_parameters_and_markers_are_guarded(self):
        config = self.request_offset + REQUEST_BYTES
        for offset in range(config, config + 36, 4):
            changed = bytes([self.sections[1][offset] ^ 1])
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "configuration"):
                verify_frame_fixture(self.changed_section(1, offset, changed), self.npdm, 0)
        for marker in MARKERS:
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, "marker"):
                verify_frame_fixture(self.changed_section(1, self.sections[1].index(marker), b"!"),
                                     self.npdm, 0)
        sections = list(self.sections)
        sections[1] += MARKERS[0]
        with self.assertRaisesRegex(ValueError, "marker"):
            verify_frame_fixture(build_frame_nso(tuple(sections)), self.npdm, 0)

    def test_invalid_bounds_variants_and_npdm_fail(self):
        for index in range(3):
            sections = list(self.sections)
            sections[index] = bytes(SEGMENT_SIZES[index] + 1)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "bounded"):
                build_frame_nso(tuple(sections))
        for sections in ((), (b"x",), (b"", b"x", b"x")):
            with self.assertRaises(ValueError):
                build_frame_nso(sections)
        for variant in (-1, 2):
            with self.assertRaises(ValueError):
                compile_frame_segments(variant=variant)
            with self.assertRaises(ValueError):
                verify_frame_fixture(self.nso, self.npdm, variant)
        with self.assertRaisesRegex(ValueError, "baseline NPDM"):
            verify_frame_fixture(self.nso, b"BAD!" + self.npdm[4:], 0)


class NativeGpuFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prefix = os.environ.get("NX2_AARCH64_PREFIX", "aarch64-linux-gnu-")
        cls.fixtures = {mode: compile_frame_segments(prefix, variant=mode[0], gpu=True,
                                                    clear_only=mode[1])
                        for mode in ((0, False), (1, False), (0, True))}
        cls.sections = cls.fixtures[0, False]
        cls.npdm = build_extended_npdm()
        cls.layout = cls.sections[1].index(b"NX2GPUv1") + 8
        cls.names, cls.count, cls.record, cls.state, _, cls.buffer, cls.inputs = (
            struct.unpack_from("<7I", cls.sections[1], cls.layout))

    def changed_section(self, index, offset, replacement):
        sections = list(self.sections)
        damaged = bytearray(sections[index])
        damaged[offset:offset + len(replacement)] = replacement
        sections[index] = bytes(damaged)
        return build_frame_nso(tuple(sections), gpu=True)

    def test_all_actual_guests_keep_empty_image_and_unobserved_results(self):
        for (variant, clear_only), sections in self.fixtures.items():
            with self.subTest(variant=variant, clear_only=clear_only):
                nso = build_frame_nso(sections, gpu=True)
                verify_frame_fixture(nso, self.npdm, variant, gpu=True, clear_only=clear_only)
                _, _, data = read_frame_segments(nso, gpu=True)
                self.assertEqual(len(nso), 98560)
                self.assertEqual(data[0x1000:0x3000], bytes(IMAGE_SIZE))
                self.assertEqual(data[self.record:self.record + 4 * self.count],
                                 b"\xff" * (4 * 337))
                self.assertEqual(data[self.buffer:], bytes(0x4000))
        self.assertEqual(GPU_SEGMENT_ADDRESSES, (0, 0x4000, 0x10000))
        self.assertEqual(tuple(map(len, read_frame_segments(
            build_frame_nso(self.sections, gpu=True), gpu=True))), GPU_SEGMENT_SIZES)

    def test_modes_cannot_be_confused(self):
        for (variant, clear_only), sections in self.fixtures.items():
            nso = build_frame_nso(sections, gpu=True)
            with self.subTest(variant=variant, clear_only=clear_only):
                with self.assertRaises(ValueError):
                    verify_frame_fixture(nso, self.npdm, variant, gpu=True,
                                         clear_only=not clear_only)
                with self.assertRaises(ValueError):
                    verify_frame_fixture(nso, self.npdm, 1 - variant, gpu=True,
                                         clear_only=clear_only)
                with self.assertRaises(ValueError):
                    read_frame_segments(nso)
        self.assertEqual(self.sections[0], self.fixtures[1, False][0])
        self.assertEqual(self.sections[2], self.fixtures[1, False][2])

    def test_rehashed_commands_shaders_vertices_and_schema_corruption_fail(self):
        for offset in (self.names, self.inputs, self.inputs + 0x1000,
                       self.inputs + 0x2084, self.inputs + 0x3000):
            changed = bytes([self.sections[1][offset] ^ 1])
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                verify_frame_fixture(self.changed_section(1, offset, changed), self.npdm,
                                     0, gpu=True)

    def test_preclaimed_gpu_results_or_host_prefilled_backing_fail(self):
        for offset in (self.record, self.record + 4 * self.count - 1, self.state,
                       self.state + 12, 0x1000, self.buffer, self.buffer + 0x3FFF):
            changed = bytes([self.sections[2][offset] ^ 1])
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "unobserved"):
                verify_frame_fixture(self.changed_section(2, offset, changed), self.npdm,
                                     0, gpu=True)

    def test_rehashed_metadata_cannot_overlap_owned_regions(self):
        for index, value in ((0, 0xFFFFFFF0), (1, 336), (2, 0x1000),
                             (3, self.record), (4, 0x8000), (5, self.state),
                             (5, 0x8000), (6, self.inputs + 1), (6, 0xC000)):
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                verify_frame_fixture(self.changed_section(
                    1, self.layout + 4 * index, struct.pack("<I", value)), self.npdm,
                    0, gpu=True)

    def test_clear_control_requires_gpu_mode(self):
        with self.assertRaisesRegex(ValueError, "requires the GPU"):
            compile_frame_segments(clear_only=True)


if __name__ == "__main__":
    unittest.main()
