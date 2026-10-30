"""NX2-authored deterministic negative tests, no Nintendo files."""
import struct
import unittest
from nro_preflight import NroPreflightError, preflight_nro


def good_nro(image_bytes=0x3000, file_bytes=None):
    if file_bytes is None:
        file_bytes = image_bytes
    data = bytearray(file_bytes)
    data[0x10:0x14] = b"NRO0"
    struct.pack_into("<I", data, 0x18, image_bytes)
    struct.pack_into("<I", data, 0x04, 0)
    struct.pack_into("<I", data, 0x38, 0x2000)
    for at, offset, length in ((0x20, 0, 0x1000), (0x28, 0x1000, 0x1000),
                               (0x30, 0x2000, 0x1000)):
        struct.pack_into("<II", data, at, offset, length)
    return bytes(data)


class TestNroPreflight(unittest.TestCase):
    def test_valid_original_style(self):
        a = preflight_nro(good_nro())
        self.assertEqual(a.image_bytes, 0x3000)
        self.assertEqual(a.copied_bytes, 0x3000)
        self.assertEqual(a.segments[2], ("data", 0x2000, 0x1000))

    def test_short_and_wrong_magic(self):
        for value in [b"", bytes(0x7F), b"not-nro" * 600]:
            with self.subTest(case=len(value)), self.assertRaises(NroPreflightError):
                preflight_nro(value)

    def test_declared_image_exceeds_input(self):
        data = bytearray(good_nro())
        struct.pack_into("<I", data, 0x18, 0x4000)
        with self.assertRaisesRegex(NroPreflightError, "memcpy"):
            preflight_nro(bytes(data))

    def test_page_padding_is_required_by_this_upstream_loader(self):
        data = bytearray(good_nro(0x3000))
        struct.pack_into("<I", data, 0x18, 0x2F00)
        struct.pack_into("<I", data, 0x34, 0xF00)
        self.assertEqual(preflight_nro(bytes(data)).copied_bytes, 0x3000)
        with self.assertRaisesRegex(NroPreflightError, "memcpy"):
            preflight_nro(bytes(data[:0x2F00]))

    def test_bad_module_offset(self):
        data = bytearray(good_nro())
        struct.pack_into("<I", data, 0x04, 0x2FF0)
        with self.assertRaisesRegex(NroPreflightError, "MOD0"):
            preflight_nro(bytes(data))

    def test_unbounded_image_and_bss(self):
        for field, value in [(0x18, 0xFFFFFFF0), (0x38, 0xFFFFFFF0)]:
            data = bytearray(good_nro())
            struct.pack_into("<I", data, field, value)
            with self.subTest(field=field), self.assertRaises(NroPreflightError):
                preflight_nro(bytes(data))

    def test_bad_segment_offset_and_bounds(self):
        for field, value in [(0x20, 1), (0x28, 0x5000), (0x2c, 0x10000000),
                             (0x30, 0x2100), (0x34, 0xFFF00000)]:
            data = bytearray(good_nro())
            struct.pack_into("<I", data, field, value)
            with self.subTest(field=field), self.assertRaises(NroPreflightError):
                preflight_nro(bytes(data))

    def test_segment_overlap(self):
        data = bytearray(good_nro())
        struct.pack_into("<I", data, 0x24, 0x2000)
        with self.assertRaisesRegex(NroPreflightError, "overlapping"):
            preflight_nro(bytes(data))

    def test_bad_type(self):
        with self.assertRaises(TypeError):
            preflight_nro(bytearray(good_nro()))


if __name__ == "__main__":
    unittest.main()
