#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Offline original authored pixel-oracle tests for the modern image capture."""
import struct
import unittest

from smoke_candidate_frame import (
    HEIGHT, SCALE, TGA_H, TGA_W, WIDTH, check_capture, expected_pixels,
    original_guest_failure_step,
)


def make_tga(variant: int, *, bottom_up: bool = False) -> bytes:
    pixels = expected_pixels(variant)
    if bottom_up:
        stride = TGA_W * 4
        pixels = b"".join(pixels[i:i + stride]
                          for i in range(len(pixels) - stride, -1, -stride))
    return (b"\x00\x00\x02" + bytes(9) + struct.pack("<HH", TGA_W, TGA_H) +
            bytes((32, 0x08 if bottom_up else 0x28)) + pixels)


class ModernOriginalPixelsTests(unittest.TestCase):
    def test_exact_original_pixel_oracle_matches_both_variants(self):
        self.assertEqual((WIDTH, HEIGHT, SCALE, TGA_W, TGA_H), (16, 9, 80, 1280, 720))
        for variant in (0, 1):
            with self.subTest(variant=variant):
                r = check_capture(make_tga(variant), variant)
                self.assertTrue(r["original_tga_header_match"])
                self.assertTrue(r["every_original_pixel_match"])

    def test_both_tga_origin_directions_are_checked(self):
        for variant in (0, 1):
            self.assertTrue(check_capture(make_tga(variant, bottom_up=True), variant)
                            ["every_original_pixel_match"])

    def test_variant_pixels_must_change(self):
        self.assertNotEqual(expected_pixels(0), expected_pixels(1))
        self.assertFalse(check_capture(make_tga(0), 1)["every_original_pixel_match"])

    def test_changed_content_is_not_accepted(self):
        damaged = bytearray(make_tga(0))
        damaged[-1] ^= 0x7F
        r = check_capture(bytes(damaged), 0)
        self.assertTrue(r["original_tga_header_match"])
        self.assertFalse(r["every_original_pixel_match"])

    def test_changed_header_and_truncated_capture_rejected(self):
        damaged = bytearray(make_tga(0))
        damaged[12] ^= 1
        self.assertFalse(check_capture(bytes(damaged), 0)["every_original_pixel_match"])
        self.assertFalse(check_capture(make_tga(1)[:-1], 1)["every_original_pixel_match"])
        self.assertFalse(check_capture(b"", 0)["every_original_pixel_match"])

    def test_only_two_original_variants_permitted(self):
        with self.assertRaises(ValueError):
            expected_pixels(2)

    def test_guest_stage_diagnostic_is_bounded_and_redacted(self):
        report = original_guest_failure_step(
            b"private-path NX2_FRAME fail_step=00000013 private-key\n")
        self.assertEqual(report, {"step_observed_once": True, "step": 19,
                                  "stage": "setup"})
        self.assertNotIn("private", str(report))
        self.assertEqual(original_guest_failure_step(
            b"NX2_FRAME fail_step=0000001e")["stage"], "present")
        self.assertEqual(original_guest_failure_step(
            b"NX2_FRAME fail_step=00000000")["stage"], "completed")

    def test_missing_duplicated_or_out_of_contract_stage_rejected(self):
        for raw in (b"", b"NX2_FRAME fail_step=00000022",
                    b"NX2_FRAME fail_step=00000001\n"
                    b"NX2_FRAME fail_step=00000002"):
            with self.subTest(raw=raw):
                self.assertFalse(original_guest_failure_step(raw)["step_observed_once"])


if __name__ == "__main__":
    unittest.main()
