"""NX2-authored deterministic negative tests, no Nintendo files."""
import contextlib
import io
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import nro_preflight
from nro_preflight import (
    MAX_PROGRAM_ALLOCATION, NroPreflightError, preflight_nro,
)


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

    def test_mod0_bss_override_is_bounded_even_with_small_header_bss(self):
        data = bytearray(good_nro())
        struct.pack_into("<I", data, 0x04, 0x80)
        struct.pack_into("<I", data, 0x38, 0)
        data[0x80:0x84] = b"MOD0"
        # Only a 12 KiB fixture: no large allocation or emulator execution.
        for start, end in ((0, 0x40000000), (0x1000, 0), (0, 0xFFFFFFFF)):
            struct.pack_into("<II", data, 0x88, start, end)
            with self.subTest(start=start, end=end), self.assertRaises(NroPreflightError):
                preflight_nro(bytes(data))

    def test_effective_mod0_bss_replaces_header_and_is_page_aligned(self):
        data = bytearray(good_nro())
        struct.pack_into("<I", data, 0x04, 0x80)
        struct.pack_into("<I", data, 0x38, 0xFFFFFFFF)
        data[0x80:0x84] = b"MOD0"
        struct.pack_into("<II", data, 0x88, 0x200, 0x1201)
        self.assertEqual(preflight_nro(bytes(data)).bss_bytes, 0x2000)

    def test_effective_allocation_limit_is_inclusive_for_both_bss_sources(self):
        for use_mod0 in (False, True):
            data = bytearray(good_nro())
            maximum_bss = MAX_PROGRAM_ALLOCATION - len(data)
            if use_mod0:
                struct.pack_into("<I", data, 0x04, 0x80)
                data[0x80:0x84] = b"MOD0"
                struct.pack_into("<I", data, 0x88, 0)
            field = 0x8C if use_mod0 else 0x38
            struct.pack_into("<I", data, field, maximum_bss)
            with self.subTest(mod0=use_mod0):
                self.assertEqual(preflight_nro(bytes(data)).bss_bytes, maximum_bss)
                struct.pack_into("<I", data, field, maximum_bss + 1)
                with self.assertRaisesRegex(NroPreflightError, "effective BSS"):
                    preflight_nro(bytes(data))

    def test_nonempty_asset_extents_must_fit_the_actual_trailer(self):
        data = bytearray(good_nro() + bytes(0x100))
        data[0x3000:0x3004] = b"ASET"
        for field in (0x3008, 0x3018, 0x3028):
            for offset, size in ((0x38, 0x40000000), (0x100, 1),
                                 (0xFFFFFFFFFFFFFFF0, 32)):
                broken = bytearray(data)
                struct.pack_into("<QQ", broken, field, offset, size)
                with self.subTest(field=field, offset=offset, size=size), \
                        self.assertRaisesRegex(NroPreflightError, "ASET"):
                    preflight_nro(bytes(broken))
        for field in (0x3008, 0x3018, 0x3028):
            struct.pack_into("<QQ", data, field, 0x38, 0xC8)
        self.assertEqual(preflight_nro(bytes(data)).image_bytes, 0x3000)

    def test_absent_or_empty_assets_do_not_imply_an_allocation(self):
        data = bytearray(good_nro() + bytes(0x38))
        data[0x3000:0x3004] = b"ASET"
        for field in (0x3008, 0x3018, 0x3028):
            struct.pack_into("<QQ", data, field, 0xFFFFFFFFFFFFFFFF, 0)
        preflight_nro(bytes(data))
        preflight_nro(good_nro() + b"ASET")  # no complete trailer header

    def test_cli_caps_the_read_before_rejecting_an_oversized_file(self):
        # Model a file growing beyond a prior stat: the actual read itself must
        # have a cap. A small substituted cap keeps the regression inexpensive.
        stream = io.BytesIO(good_nro() + bytes(4096))
        with patch.object(nro_preflight, "MAX_IMAGE_SIZE", 0x3000), \
                patch.object(Path, "stat", return_value=SimpleNamespace(st_size=0x3000)), \
                patch.object(Path, "open", return_value=stream), \
                patch.object(stream, "read", wraps=stream.read) as read, \
                patch("sys.argv", ["nro_preflight.py", "oversized.nro"]), \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as exit_status:
                nro_preflight.main()
            self.assertEqual(exit_status.exception.code, 1)
            read.assert_called_once_with(0x3001)
            self.assertIn("input limit", errors.getvalue())

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
