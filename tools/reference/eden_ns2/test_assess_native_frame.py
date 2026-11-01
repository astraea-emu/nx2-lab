# SPDX-License-Identifier: GPL-3.0-only
"""Reject false frame evidence, corrupted pixels and incomplete guest teardown."""
import contextlib
from functools import lru_cache
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import assess_native_frame
from assess_native_frame import assess, logical_pixel, verify_pixels


PREFIX = (b"[   1.000000] Debug.Emulated <Info> "
          b"core/hle/kernel/svc/svc_debug_string.cpp:25:OutputDebugString: ")
CLASSIFIED = (b"[   0.020000] Core <Info> core/core.cpp:321:Load: "
              b"Switch 2 program: using the 12 GiB memory layout\n")
FRONTEND = (b"[   0.010000] Frontend <Info> "
            b"yuzu_cmd/emu_window/emu_window_sdl3_vk.cpp:92:EmuWindow_SDL3_VK: "
            b"Eden Version: Eden | HEAD-e2f285ab1e-HEAD (Vulkan)\n")
RENDERER = (
    b"[   0.200000] Render.Vulkan <Info> video_core/renderer_vulkan/renderer_vulkan.cpp:278:Report: Driver: Mesa 26.0.3\n"
    b"[   0.200001] Render.Vulkan <Info> video_core/renderer_vulkan/renderer_vulkan.cpp:279:Report: Device: llvmpipe (LLVM 21.1.8, 256 bits)\n"
    b"[   0.200002] Render.Vulkan <Info> video_core/renderer_vulkan/renderer_vulkan.cpp:280:Report: Vulkan: 1.4.305\n"
)
MANAGER = (b"[   1.100000] Service.VI <Warning> "
           b"core/hle/service/vi/application_display_service.cpp:81:GetManagerDisplayService: "
           b"(STUBBED) called\n")
QUEUED = (b"[   1.200001] Service.AM <Info> "
          b"core/hle/service/am/service/graphics_supervisor.cpp:948:QueueNativeImage: "
          b"Native image queued for display: image=1, slot=0, fence=4294967295/0, dimensions=16x9\n")
SUBMITTED = (b"[   1.300000] Service.NVDRV <Info> "
             b"core/hle/service/nvdrv/devices/nvdisp_disp0.cpp:116:Composite: "
             b"Native composite submitted: layers=1, address=0x80004000\n")
CAPTURED = (b"[   1.400000] Service.NVDRV <Info> "
            b"core/hle/service/nvdrv/devices/nvdisp_disp0.cpp:147:operator(): "
            b"Captured composited frame: 1920x1080, saved=true, nonblack=true\n")
EXIT = (b"[  12.000000] Kernel.SVC <Info> "
        b"core/hle/kernel/svc/svc_process.cpp:17:ExitProcess: Process 81 exiting\n")
EMPTY_PATH = (b"Common.Filesystem <Error> common/fs/path_util.cpp:308:SetEdenPath: "
              b"Filesystem object at new_path= is not a directory\n")
MISSING_TITLE = b"Core <Error> core/core.cpp:355:Load: Failed to read title for ROM!\n"
NETWORK = b"Service <Error> core/hle/service/sockets/bsd.cpp:1164:BSD_USA: Network isn't initialized\n"


def marker(name):
    return PREFIX + b"NX2_FRAME_" + name.encode() + b"\n"


def record(name, value):
    return PREFIX + f"NX2_FRAME {name}={value:08x}\n".encode()


def observed_fields(variant=0):
    # Explicit wire fixture: do not import the assessor's expected field table.
    fields = [("variant", variant), ("image_width", 16), ("image_height", 9),
              ("image_address_lo", 0x8006000), ("image_address_hi", 0),
              ("image_checksum", (0xB78A03D5, 0x0A9DFBD5)[variant]),
              ("connect_rc", 0), ("sm_handle", 0x103FE)]
    for name, words, descriptor, extra in (
        ("sm_init", 10, 0, ()),
        ("get_applet", 0x8000000A, 0x20, (("applet_handle", 0x183FD),)),
        ("open_proxy", 0x8000000A, 0x20, (("proxy_handle", 0x203FC),)),
        ("get_window", 0x8000000A, 0x20, (("window_handle", 0x283FB),)),
        ("get_aruid", 14, 0, (("aruid_lo", 81), ("aruid_hi", 0))),
        ("get_self", 0x8000000A, 0x20, (("self_handle", 0x303FA),)),
        ("get_gsv", 0x8000000A, 2, (("gsv_handle", 0x383F9),)),
    ):
        fields.extend((name + "_" + part, value) for part, value in (
            ("transport", 0), ("header0", 0), ("header1", words),
            ("descriptor", descriptor), ("magic", 0x4F434653), ("result", 0)))
        fields.extend(extra)
    for name, command, words, result, extra in (
        ("bootstrap", 4, 1, 0, ()), ("bind", 11, 1, 0, ()), ("ready", 101, 1, 0, ()),
        ("image_init", 1501, 1, 0, ()), ("image_formats", 1502, 1, 0, ()),
        ("open_nvdrv", 1402, 0x80000001, 0, ()),
        ("gpu_init", 401, 1, 0, ()), ("gpu_ready", 402, 1, 0, ()),
        ("size_zero", 435, 3, 0x100F3, (("size_zero_lo", 0), ("size_zero_hi", 0))),
        ("size_valid", 435, 3, 0, (("size_valid_lo", 8192), ("size_valid_hi", 0))),
        ("memory_create", 111, 2, 0, (("memory_id", 4),)),
        ("memory_bind", 114, 1, 0, ()),
        ("image_create", 429, 2, 0, (("image_id", 1),)),
        ("pool_create", 315, 1, 0, ()), ("display_init", 301, 1, 0, ()),
        ("open_vi2", 305, 0x80000001, 0, ()),
        ("register", 201, 1, 0, ()), ("open_display", 101, 1, 0, ()),
        ("bind_display", 251, 1, 0, ()),
        ("available_before", 212, 3, 0, (("available_before_lo", 0x7FFF), ("available_before_hi", 0))),
        ("present", 229, 7, 0, (("present_lo", 0x7FFE), ("present_hi", 0),
                              ("present_tail00", 0), ("present_tail01", 0),
                              ("present_tail02", 0), ("present_tail03", 0))),
        ("poll", 212, 3, 0, (("poll_lo", 0x7FFF), ("poll_hi", 0), ("poll_count", 100),
                           ("poll_queued_count", 2), ("poll_released_count", 98))),
        ("released", 21, 1, 0, ()), ("clear", 21, 1, 0, ()),
        ("unbind_display", 252, 1, 0, ()), ("unregister", 202, 1, 0, ()),
        ("close_display", 102, 1, 0, ()), ("pool_destroy", 314, 1, 0, ()),
        ("image_destroy", 430, 1, 0, ()), ("memory_destroy", 112, 1, 0, ()),
        ("display_finalize", 303, 1, 0, ()),
    ):
        fields.extend(((name + "_transport", 0), (name + "_header0", command + 16),
                       (name + "_header1", words)))
        if name == "open_nvdrv":
            fields.extend((("open_nvdrv_descriptor", 0x20), ("nvdrv_handle", 0x403F8)))
        if name == "open_vi2":
            fields.extend((("open_vi2_descriptor", 0x20), ("vi2_handle", 0x483F7)))
        fields.append((name + "_result", result))
        fields.extend(extra)
        if name in ("released", "clear"):
            fields.append((name + "_guard_before", 0xA5A5A5A5))
            fields.extend((f"{name}_word{i:02d}", 8 if name == "released" and i == 0 else 0)
                          for i in range(32))
            fields.append((name + "_guard_after", 0xA5A5A5A5))
    fields.extend(("close_" + name, 0) for name in
                  ("vi2", "nvdrv", "gsv", "self", "window", "proxy", "applet", "sm"))
    return fields + [("fail_step", 0)]


FIELDS = observed_fields()


def good_log(variant=0):
    records = b"".join(record(name, value) for name, value in observed_fields(variant))
    return (FRONTEND + CLASSIFIED + RENDERER + marker("BEGIN") + MANAGER +
            marker("PRESENT_BEGIN") + QUEUED + marker("PRESENTED") + SUBMITTED + CAPTURED +
            marker("CLEANUP_BEGIN") + records + marker("COMPLETE") + EXIT)


GOOD = good_log()


def changed(name, value, log=GOOD, variant=0):
    return log.replace(record(name, dict(observed_fields(variant))[name]), record(name, value), 1)


@lru_cache(maxsize=2)
def image_fixture(variant=0):
    # Independent screen-space rectangle painting. No oracle or guest tiling import.
    width, height = 1920, 1080
    pixels = bytearray(bytes((48, 32, 16, 255)) * width * height)

    def rectangle(x, y, w, h, bgra):
        row = bytes(bgra) * w
        for line in range(y, min(y + h, height)):
            start = (line * width + x) * 4
            pixels[start:start + len(row)] = row

    for row in range(5):
        for column in range(8):
            if (row + column) % 2:
                rectangle(column * 240, row * 240, 240, 240,
                          (224, 208, 192, 255) if variant == 0 else (160, 80, 224, 255))
    rectangle(0, 0, 240, 240, (0, 0, 255, 255))
    rectangle(1680, 0, 240, 240, (0, 255, 0, 255))
    rectangle(0, 840, 240, 240, (255, 0, 0, 255))
    rectangle(1680, 840, 240, 240, (0, 255, 255, 255))
    header = bytes.fromhex("000002000000000000000000800738042028")
    return header + pixels


class NativeFramePixelTests(unittest.TestCase):
    def pixels(self, capture, variant=0):
        with contextlib.redirect_stdout(io.StringIO()):
            return verify_pixels(capture, variant)

    def test_both_independently_painted_variants_match_every_pixel(self):
        for variant in (0, 1):
            self.assertEqual(len(image_fixture(variant)), 8294418)
            self.assertTrue(self.pixels(image_fixture(variant), variant))
            self.assertFalse(self.pixels(image_fixture(variant), 1 - variant))

    def test_logical_spec_has_asymmetric_corners_checker_parity_and_opaque_alpha(self):
        for x, y, rgba in ((0, 0, (255, 0, 0, 255)), (15, 1, (0, 255, 0, 255)),
                           (1, 7, (0, 0, 255, 255)), (14, 8, (255, 255, 0, 255)),
                           (4, 4, (16, 32, 48, 255)), (2, 4, (192, 208, 224, 255))):
            self.assertEqual(logical_pixel(x, y, 0), rgba)
        self.assertEqual(logical_pixel(2, 4, 1), (224, 80, 160, 255))

    def test_every_header_byte_is_fixed_including_origin_and_no_colour_map(self):
        image = image_fixture()
        for i in range(18):
            bad = bytearray(image)
            bad[i] ^= 1
            with self.subTest(offset=i):
                self.assertFalse(self.pixels(bad))

    def test_missing_truncated_and_extra_bytes_are_rejected(self):
        image = image_fixture()
        for bad in (b"", image[:18], image[:-1], image[:10000], image + b"\0"):
            with self.subTest(length=len(bad)):
                self.assertFalse(self.pixels(bad))

    def test_single_corrupted_pixel_or_alpha_fails_even_at_last_pixel(self):
        image = image_fixture()
        for offset in (18, 19, 20, 21, 18 + (540 * 1920 + 961) * 4, len(image) - 1):
            bad = bytearray(image)
            bad[offset] ^= 1
            with self.subTest(offset=offset):
                self.assertFalse(self.pixels(bad))

    def test_vertical_horizontal_and_channel_swaps_cannot_pass(self):
        image = image_fixture()
        rows = [image[18 + i * 7680:18 + (i + 1) * 7680] for i in range(1080)]
        flipped = image[:18] + b"".join(reversed(rows))
        self.assertFalse(self.pixels(flipped))
        horizontal = image[:18] + b"".join(
            b"".join(row[i:i + 4] for i in range(7676, -1, -4)) for row in rows)
        self.assertFalse(self.pixels(horizontal))
        swapped = bytearray(image)
        swapped[18::4], swapped[20::4] = swapped[20::4], swapped[18::4]
        self.assertFalse(self.pixels(swapped))

    def test_unknown_variant_does_not_select_an_implicit_default(self):
        for variant in (-1, 2, True, None, "0"):
            with self.subTest(variant=variant):
                self.assertFalse(self.pixels(image_fixture(), variant))


class NativeFrameAssessmentTests(unittest.TestCase):
    def run_case(self, log=GOOD, status=0, capture=None, variant=0):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = assess(log, status, image_fixture(variant) if capture is None else capture, variant)
        return result, output.getvalue()

    def test_complete_guest_renderer_pixels_and_cleanup_are_required(self):
        self.assertEqual(len(FIELDS), 281)
        for variant in (0, 1):
            ok, output = self.run_case(good_log(variant), variant=variant)
            self.assertTrue(ok, output[-2000:])
            for item in ("FIELD_COUNT=281", "EVENTS_IN_ORDER=1", "ALL_PIXELS_MATCH=1",
                         "KNOWN_MANAGER_STUB_COUNT=1", "QUEUE_MATCHES_IMAGE=1", "GUEST_PIXELS_PASS"):
                self.assertIn("NX2_NATIVE_FRAME_" + item, output)

    def test_every_observed_field_is_required_once_and_in_order(self):
        for name, value in FIELDS:
            line = record(name, value)
            with self.subTest(field=name, defect="missing"):
                self.assertFalse(self.run_case(GOOD.replace(line, b"", 1))[0])
            with self.subTest(field=name, defect="duplicate"):
                self.assertFalse(self.run_case(GOOD.replace(line, line * 2, 1))[0])
        a, b = record(*FIELDS[0]), record(*FIELDS[1])
        self.assertFalse(self.run_case(GOOD.replace(a + b, b + a))[0])

    def test_each_fixed_reply_notification_guard_and_cleanup_result_is_checked(self):
        dynamic = {"variant", "image_address_lo", "image_address_hi", "image_checksum",
                   "aruid_lo", "aruid_hi", "memory_id", "image_id",
                   "poll_queued_count", "poll_released_count"}
        for name, value in FIELDS:
            if name in dynamic or name.endswith("_handle"):
                continue
            with self.subTest(field=name):
                self.assertFalse(self.run_case(changed(name, value ^ 1))[0])

    def test_unobserved_sentinel_cannot_satisfy_any_field(self):
        for name, _ in FIELDS:
            with self.subTest(field=name):
                self.assertFalse(self.run_case(changed(name, 0xFFFFFFFF))[0])

    def test_cmif_magic_tipc_lengths_and_moved_handles_are_distinct_contracts(self):
        for name, value in (("get_gsv_descriptor", 0x20), ("get_self_descriptor", 2),
                            ("open_nvdrv_descriptor", 2), ("open_vi2_header1", 10),
                            ("size_zero_result", 0), ("size_valid_lo", 4096),
                            ("present_header1", 3), ("present_result", 0x4F434653),
                            ("released_word00", 4), ("clear_word31", 8)):
            with self.subTest(field=name):
                self.assertFalse(self.run_case(changed(name, value))[0])

    def test_all_eight_handles_must_be_valid_and_pairwise_distinct(self):
        handles = [name for name, _ in FIELDS if name.endswith("_handle")]
        self.assertEqual(len(handles), 8)
        for name in handles:
            for value in (0, 1, 0x80000400, 0x00008400, 0x40008001, 0xFFFF8001):
                with self.subTest(field=name, value=value):
                    self.assertFalse(self.run_case(changed(name, value))[0])
            other = next(n for n in handles if n != name)
            self.assertFalse(self.run_case(changed(name, dict(FIELDS)[other]))[0])

    def test_aruid_matches_actual_exit_process(self):
        self.assertFalse(self.run_case(changed("aruid_lo", 82))[0])
        self.assertFalse(self.run_case(changed("aruid_hi", 1))[0])
        log = changed("aruid_lo", 82).replace(b"Process 81 exiting", b"Process 82 exiting")
        self.assertTrue(self.run_case(log)[0])

    def test_image_identity_checksums_dimensions_and_virtual_address_are_bound(self):
        for name, value in (("variant", 1), ("image_checksum", 0x0A9DFBD5),
                            ("image_address_lo", 0), ("image_address_lo", 0x8006001),
                            ("image_address_hi", 128), ("memory_id", 0), ("image_id", 0)):
            with self.subTest(field=name, value=value):
                self.assertFalse(self.run_case(changed(name, value))[0])
        log = changed("image_address_hi", 127)
        log = changed("image_address_lo", 0xFFFFF000, log)
        self.assertFalse(self.run_case(log)[0])
        self.assertFalse(self.run_case(capture=image_fixture(1))[0])

    def test_poll_counts_require_all_one_hundred_checks_and_actual_release(self):
        for queued, released in ((0, 0), (100, 0), (1, 100), (99, 0), (101, 1)):
            log = changed("poll_queued_count", queued)
            log = changed("poll_released_count", released, log)
            self.assertFalse(self.run_case(log)[0])
        log = changed("poll_queued_count", 0)
        log = changed("poll_released_count", 100, log)
        self.assertTrue(self.run_case(log)[0])

    def test_every_lifecycle_capture_and_renderer_event_is_unique(self):
        events = [marker(n) for n in ("BEGIN", "PRESENT_BEGIN", "PRESENTED", "CLEANUP_BEGIN", "COMPLETE")]
        events += [CLASSIFIED, EXIT, MANAGER, FRONTEND, QUEUED, SUBMITTED, CAPTURED]
        events += RENDERER.splitlines(keepends=True)
        for event in events:
            with self.subTest(event=event[:80], defect="missing"):
                self.assertFalse(self.run_case(GOOD.replace(event, b"", 1))[0])
            with self.subTest(event=event[:80], defect="duplicate"):
                self.assertFalse(self.run_case(GOOD.replace(event, event * 2, 1))[0])

    def test_capture_before_present_call_or_after_cleanup_is_rejected(self):
        without = GOOD.replace(SUBMITTED + CAPTURED, b"")
        for log in (SUBMITTED + CAPTURED + without,
                    without.replace(marker("PRESENT_BEGIN"), SUBMITTED + CAPTURED + marker("PRESENT_BEGIN")),
                    without.replace(marker("CLEANUP_BEGIN"), marker("CLEANUP_BEGIN") + SUBMITTED + CAPTURED),
                    without + SUBMITTED + CAPTURED):
            self.assertFalse(self.run_case(log)[0])

    def test_capture_before_present_reply_is_a_legitimate_async_ordering(self):
        default = QUEUED + marker("PRESENTED") + SUBMITTED + CAPTURED
        for concurrent in (QUEUED + SUBMITTED + CAPTURED + marker("PRESENTED"),
                           SUBMITTED + CAPTURED + QUEUED + marker("PRESENTED")):
            self.assertTrue(self.run_case(GOOD.replace(default, concurrent))[0])

    def test_stale_capture_record_or_concatenated_runs_cannot_qualify(self):
        self.assertFalse(self.run_case(CAPTURED + GOOD.replace(CAPTURED, b""))[0])
        self.assertFalse(self.run_case(GOOD + GOOD)[0])
        self.assertFalse(self.run_case(GOOD.replace(CAPTURED, b""), capture=image_fixture())[0])

    def test_capture_log_flags_layer_count_address_image_and_dimensions_are_checked(self):
        for before, after in ((b"saved=true", b"saved=false"), (b"nonblack=true", b"nonblack=false"),
                              (b"1920x1080", b"1280x720"), (b"layers=1", b"layers=0"),
                              (b"layers=1", b"layers=2"), (b"address=0x80004000", b"address=0x0"),
                              (b"image=1, slot=0", b"image=2, slot=0"),
                              (b"slot=0", b"slot=1"), (b"dimensions=16x9", b"dimensions=9x16"),
                              (b"fence=4294967295/0", b"fence=1/0")):
            with self.subTest(after=after):
                self.assertFalse(self.run_case(GOOD.replace(before, after))[0])

    def test_all_evidence_requires_genuine_complete_source_tags(self):
        for source in (PREFIX, CLASSIFIED, EXIT, FRONTEND, QUEUED, SUBMITTED, CAPTURED,
                       RENDERER.splitlines(keepends=True)[0]):
            for replacement in (b"Host echo: " + source, b"Host echo only\n"):
                with self.subTest(source=source[:80], replacement=replacement[:20]):
                    self.assertFalse(self.run_case(GOOD.replace(source, replacement))[0])
        for before, after in ((b"svc_debug_string.cpp", b"fixture_echo.cpp"),
                              (b"nvdisp_disp0.cpp:147", b"nvdisp_disp0.cpp:148"),
                              (b"graphics_supervisor.cpp:948", b"other.cpp:948")):
            self.assertFalse(self.run_case(GOOD.replace(before, after))[0])
        self.assertFalse(self.run_case(GOOD + b"NX2_FRAME variant=00000000\n")[0])

    def test_multiline_log_calls_require_actual_clang_attribution_not_guessed_first_line(self):
        # Run 41268051638 captured both complete source records at the closing
        # invocation lines. Preserve that correction without broadening matches.
        for actual, guessed in ((b"graphics_supervisor.cpp:948", b"graphics_supervisor.cpp:947"),
                                (b"emu_window_sdl3_vk.cpp:92", b"emu_window_sdl3_vk.cpp:91")):
            with self.subTest(guessed=guessed):
                self.assertFalse(self.run_case(GOOD.replace(actual, guessed))[0])

    def test_malformed_unknown_or_interior_control_bytes_are_never_repaired(self):
        for bad in (b"variant=0", b"variant=000000000", b"variant=0x00000000",
                    b"variant=0000\0\x1b[0m0000", b"variant=0000\xff0000",
                    b"variant=00000000 trailing", b"VARIANT=00000000", b"unknown=00000000"):
            with self.subTest(bad=bad):
                self.assertFalse(self.run_case(GOOD.replace(b"variant=00000000", bad, 1))[0])
        self.assertFalse(self.run_case(GOOD + b"Render.Vulkan <Er\0ror> failed\n")[0])

    def test_known_startup_errors_are_source_exact_bounded_and_only_before_begin(self):
        startup = EMPTY_PATH * 5 + MISSING_TITLE + NETWORK * 3
        self.assertTrue(self.run_case(startup + GOOD)[0])
        for item, limit in ((EMPTY_PATH, 5), (MISSING_TITLE, 1), (NETWORK, 3)):
            self.assertFalse(self.run_case(item * (limit + 1) + GOOD)[0])
            self.assertFalse(self.run_case(GOOD.replace(marker("BEGIN"), marker("BEGIN") + item))[0])
            self.assertFalse(self.run_case(GOOD + item)[0])
            self.assertFalse(self.run_case(b"Host echo: " + item + GOOD)[0])
            self.assertFalse(self.run_case(item.replace(b" <Error>", b" <Critical>") + GOOD)[0])

    def test_only_exact_manager_stub_is_allowed_during_the_guest(self):
        for log in (MANAGER + GOOD.replace(MANAGER, b""), GOOD + MANAGER,
                    GOOD.replace(MANAGER, MANAGER.replace(b".cpp:81:", b".cpp:82:")),
                    GOOD.replace(MANAGER, MANAGER.replace(b"<Warning>", b"<Error>")),
                    GOOD + b"Service.VI <Warning> Using auto stub fallback!\n"):
            self.assertFalse(self.run_case(log)[0])

    def test_required_capabilities_and_faults_fail_even_with_complete_pixels(self):
        for diagnostic in (
            b"Render.Vulkan <Warning> Unsuitable driver - continuing anyways",
            b"Render.Vulkan <Warning> Skipping composite while the swapchain has no format",
            b"Render.Vulkan <Error> Missing required feature geometryShader",
            b"Render.Vulkan <Error> Missing required extension VK_KHR_swapchain",
            b"Render.Vulkan <Error> Vulkan initialization failed with error: unavailable",
            b"VK_ERROR_DEVICE_LOST", b"assert (memory)", b"ExceptionRaised(exception=UndefinedInstruction)",
            b"Segmentation fault", b"Aborted", b"AddressSanitizer: heap-buffer-overflow",
            b"runtime error: misaligned access", b"Operation timed out", b"NX2_FRAME_FAILURE",
            b"Common.Filesystem <Error> Failed to save playtime database",
        ):
            with self.subTest(diagnostic=diagnostic):
                self.assertFalse(self.run_case(GOOD + diagnostic + b"\n")[0])
        optional = b"Render.Vulkan <Info> Device doesn't support extension VK_NV_viewport_swizzle\n"
        self.assertTrue(self.run_case(optional + GOOD)[0])

    def test_vulkan_report_cannot_claim_unsupported_or_malformed_api(self):
        for version in (b"1.0.0", b"1.3", b"v1.4.305", b" "):
            self.assertFalse(self.run_case(GOOD.replace(b"Vulkan: 1.4.305", b"Vulkan: " + version))[0])
        self.assertFalse(self.run_case(GOOD.replace(b"(Vulkan)", b"(Null)"))[0])
        self.assertFalse(self.run_case(GOOD.replace(b"renderer_vulkan.cpp:279", b"renderer_vulkan.cpp:278"))[0])

    def test_nonzero_process_status_cannot_pass(self):
        for status in (-11, -9, 1, 124, 125, 126, 127, 134, 137, 139, 143):
            with self.subTest(status=status):
                self.assertFalse(self.run_case(status=status)[0])

    def test_log_success_cannot_substitute_for_real_capture_bytes(self):
        for capture in (b"", b"saved=true nonblack=true", image_fixture()[:-1]):
            self.assertFalse(self.run_case(capture=capture)[0])

    def test_record_boundary_noise_is_preserved_without_repairing_interior(self):
        colored = b"".join(b"\0\x1b[0;37m" + line + b"\0\x1b[0m\r\n"
                           for line in GOOD.splitlines())
        self.assertTrue(self.run_case(colored)[0])

    def test_log_limit_and_invalid_variant_fail_before_parsing(self):
        with patch.object(assess_native_frame, "MAX_LOG_SIZE", 16):
            self.assertFalse(self.run_case()[0])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(assess(GOOD, 0, image_fixture(), 2))

    def test_cli_missing_capture_and_wrong_size_are_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log, capture = root / "frame.log", root / "frame.tga"
            log.write_bytes(GOOD)
            command = [sys.executable, str(Path(assess_native_frame.__file__)),
                       "--log", str(log), "--exit", "0", "--capture", str(capture), "--variant", "0"]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
            capture.write_bytes(b"truncated")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)

    def test_cli_bounds_reads_after_a_file_grows_beyond_stat_size(self):
        streams = (io.BytesIO(bytes(100)), io.BytesIO(image_fixture() + b"extra"))
        with patch.object(assess_native_frame, "MAX_LOG_SIZE", 16), \
                patch.object(Path, "stat", side_effect=(SimpleNamespace(st_size=16),
                    SimpleNamespace(st_size=assess_native_frame.CAPTURE_SIZE))), \
                patch.object(Path, "open", side_effect=streams), \
                patch.object(streams[0], "read", wraps=streams[0].read) as log_read, \
                patch.object(streams[1], "read", wraps=streams[1].read) as capture_read, \
                patch("sys.argv", ["assess_native_frame.py", "--log", "growing.log", "--exit", "0",
                                   "--capture", "growing.tga", "--variant", "0"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(assess_native_frame.main(), 1)
            log_read.assert_called_once_with(17)
            capture_read.assert_called_once_with(assess_native_frame.CAPTURE_SIZE + 1)


if __name__ == "__main__":
    unittest.main()
