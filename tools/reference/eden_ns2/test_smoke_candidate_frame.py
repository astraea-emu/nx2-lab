#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Offline original authored pixel-oracle tests for the modern image capture."""
import struct
import unittest

from smoke_candidate_frame import (
    HEIGHT, SCALE, TGA_H, TGA_W, WIDTH, check_capture, expected_pixels,
    original_guest_failure_step, original_invalid_size_observation,
    original_graphics_device_mapping_observation,
    original_pixel_difference, original_finalize_observation,
    original_exact_pixel_renderer_config,
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
        for raw in (b"", b"NX2_FRAME fail_step=0000002a",
                    b"NX2_FRAME fail_step=00000001\n"
                    b"NX2_FRAME fail_step=00000002"):
            with self.subTest(raw=raw):
                self.assertFalse(original_guest_failure_step(raw)["step_observed_once"])

    def test_invalid_size_response_is_reported_without_accepting_it(self):
        def record(result, lo=0, hi=0):
            return b"".join(
                f"NX2_FRAME size_zero_{name}={value:08x}\n".encode()
                for name, value in (
                    ("transport", 0), ("header0", 451), ("header1", 3),
                    ("result", result), ("lo", lo), ("hi", hi)))
        expected = original_invalid_size_observation(record(0x100F3))
        self.assertTrue(expected["original_rejection_observed"])
        bypassed = original_invalid_size_observation(record(0, 8192))
        self.assertTrue(bypassed["fields_observed_once"])
        self.assertFalse(bypassed["original_rejection_observed"])
        self.assertEqual(bypassed["returned_size"], 8192)
        self.assertEqual(bypassed["returned_code"], "0x00000000")

    def test_duplicate_missing_and_private_size_fields_fail_closed(self):
        sample = b"NX2_FRAME size_zero_result=00000000 private-path\n"
        for raw in (b"", sample, sample + sample):
            self.assertFalse(original_invalid_size_observation(raw)["fields_observed_once"])
            self.assertNotIn("private", str(original_invalid_size_observation(raw)))


    def test_cleanup_release_failures_are_not_discarded_as_out_of_contract(self):
        for step in (34, 35, 36, 37, 38, 39, 40):
            with self.subTest(step=step):
                report = original_guest_failure_step(
                    f"NX2_FRAME fail_step={step:08x}\n".encode())
                self.assertEqual(report["stage"], "cleanup_release")
                self.assertEqual(report["step"], step)
                self.assertTrue(report["step_observed_once"])

    def test_redacted_device_mapping_categories_only(self):
        raw = (b"secret-address GPU: nx2:vi2 229 present #1\n"
               b"guest image 42 has no device mapping @0xSECRET\n"
               b"GPU memory: no address space or session secret path\n")
        report = original_graphics_device_mapping_observation(raw)
        self.assertEqual(report["native_image_missing_device_mapping_count"], 1)
        self.assertEqual(report["gpu_mapping_missing_address_space_count"], 1)
        self.assertEqual(report["native_vi2_present_request_count"], 1)
        self.assertFalse(report["raw_host_log_retained"])
        self.assertNotIn("secret", str(report).lower())



    def test_modern_image_map_stage_is_distinct_from_cleanup_release(self):
        self.assertEqual(original_guest_failure_step(
            b"NX2_FRAME fail_step=00000029\n")["stage"], "gpu_address_space_close")
        self.assertFalse(original_guest_failure_step(
            b"NX2_FRAME fail_step=0000002a\n")["step_observed_once"])



    def test_original_pixel_difference_is_bounded_and_precise(self):
        raw = expected_pixels(0)
        result = original_pixel_difference(raw, raw)
        self.assertEqual(result["mismatched_pixel_count"], 0)
        self.assertIsNone(result["first_mismatch"])
        self.assertEqual(len(result["fixed_original_pattern_probes"]), 6)
        self.assertFalse(result["raw_capture_preserved"])
        damaged = bytearray(raw)
        # Deliberately change only the blue byte of the very first pixel.
        damaged[0] ^= 7
        report = original_pixel_difference(bytes(damaged), raw)
        self.assertEqual(report["mismatched_pixel_count"], 1)
        self.assertEqual(report["first_mismatch"]["x"], 0)
        self.assertEqual(report["first_mismatch"]["y"], 0)
        self.assertEqual(report["first_mismatch"]["channel"], "B")
        self.assertFalse(report["red_blue_swapped_exact_match"])
        self.assertNotIn("private-path", str(report))

    def test_capture_mismatch_is_diagnostic_not_a_pass(self):
        original = make_tga(0)
        corrupted = bytearray(original)
        corrupted[18] ^= 7
        evidence = check_capture(bytes(corrupted), 0)
        self.assertFalse(evidence["every_original_pixel_match"])
        self.assertEqual(evidence["bounded_mismatch_diagnostics"]["mismatched_pixel_count"], 1)
        self.assertIsNone(check_capture(original, 0)["bounded_mismatch_diagnostics"])
        self.assertIsNone(check_capture(original[:-1], 0)["bounded_mismatch_diagnostics"])

    def test_channel_swapped_capture_still_fails_exact_pixel_gate(self):
        expected = expected_pixels(1)
        swapped = bytearray(expected)
        for offset in range(0, len(swapped), 4):
            swapped[offset], swapped[offset + 2] = swapped[offset + 2], swapped[offset]
        report = original_pixel_difference(bytes(swapped), expected)
        self.assertTrue(report["red_blue_swapped_exact_match"])
        self.assertGreater(report["mismatched_pixel_count"], 0)
        tga = make_tga(1)[:18] + swapped
        self.assertFalse(check_capture(bytes(tga), 1)["every_original_pixel_match"])
        with self.assertRaises(ValueError):
            original_pixel_difference(expected[:-4], expected)

    def test_cleanup_numeric_response_is_redacted_and_fail_closed(self):
        valid = b"".join(
            f"NX2_FRAME display_finalize_{name}={value:08x}\n".encode()
            for name, value in (("transport", 0), ("header0", 319),
                                ("header1", 1), ("result", 0)))
        good = original_finalize_observation(valid + b"private-path")
        self.assertTrue(good["fields_observed_once"])
        self.assertTrue(good["legacy_reply_shape_match"])
        self.assertNotIn("private-path", str(good))
        bad = original_finalize_observation(
            valid.replace(b"header1=00000001", b"header1=00000002"))
        self.assertTrue(bad["fields_observed_once"])
        self.assertFalse(bad["legacy_reply_shape_match"])
        self.assertFalse(original_finalize_observation(valid + valid)["fields_observed_once"])
        self.assertFalse(original_finalize_observation(b"")["fields_observed_once"])



    def test_exact_pixel_renderer_disables_both_default_postprocesses(self):
        cfg = original_exact_pixel_renderer_config()
        self.assertTrue(cfg.startswith("[Renderer]\n"))
        for key in ("backend", "vulkan_device", "scaling_filter", "anti_aliasing"):
            self.assertEqual(cfg.count(f"\n{key}="), 1)
            self.assertEqual(cfg.count(f"\n{key}\\default=false"), 1)
        self.assertIn("\nscaling_filter=0\n", cfg)
        self.assertIn("\nanti_aliasing=0\n", cfg)


if __name__ == "__main__":
    unittest.main()
