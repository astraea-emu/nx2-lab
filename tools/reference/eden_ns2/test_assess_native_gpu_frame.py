# SPDX-License-Identifier: GPL-3.0-only
"""Independent triangle image controls; synthetic logs are not runtime evidence."""
import contextlib
import io
import struct
import unittest

import assess_native_gpu_frame as gpu
from assess_native_frame import assess as assess_cpu
from test_assess_native_frame import (
    CAPTURED, CLASSIFIED, EXIT, FRONTEND, MANAGER, PREFIX, QUEUED, RENDERER,
    SUBMITTED, marker, observed_fields, record,
)


# Manually enumerated logical rows, independent of the checker's edge equations.
MASK = (
    "................", "................", "..###########...",
    "..########......", "..######........", "..####..........",
    "..#.............", "................", "................",
)


def image(variant=0, *, clear_only=False, sentinel=False):
    pixels = bytearray()
    for row in MASK:
        line = bytearray()
        for cell in row:
            colour = ((255, 255, 0, 255) if sentinel else
                      ((255, 0, 255, 255) if variant == 0 else (0, 255, 0, 255))
                      if cell == "#" and not clear_only else (16, 32, 48, 255))
            red, green, blue, alpha = colour
            line.extend(bytes((blue, green, red, alpha)) * 120)
        pixels.extend(line * 120)
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, 1920, 1080, 32, 0x28)
    return header + pixels


def gpu_fields(variant=0, clear_only=False):
    """An explicit wire fixture, independent of the assessor's expected table."""
    checksum = ((0x9FD0D419, 0x37270BE4), (0x4DBA94DD, 0xA8667CF0))[clear_only][variant]
    fields = [("gpu_clear_only", int(clear_only)), ("gpu_buffer_address_lo", 0x8010000),
              ("gpu_buffer_address_hi", 0), ("gpu_buffer_size", 16384),
              ("gpu_buffer_checksum", checksum), ("gpu_command_words", 149),
              ("gpu_entry_lo", 0x10000), ("gpu_entry_hi", 0x25401)]

    def tipc(name, command, words=1):
        fields.extend((f"gpu_{name}_{part}", value) for part, value in (
            ("transport", 0), ("header0", command + 16), ("header1", words), ("result", 0)))

    def cmif(name, fd=None):
        fields.extend((f"gpu_{name}_{part}", value) for part, value in (
            ("transport", 0), ("header0", 0), ("header1", 12 if fd is None else 14),
            ("pad0", 0), ("pad1", 0), ("magic", 0x4F434653), ("version", 0),
            ("result_lo", 0), ("result_hi", 0)))
        if fd is not None:
            fields.append((f"gpu_{name}_fd", fd))
        fields.append((f"gpu_{name}_nv_result", 0))

    def ioctl(name, words):
        cmif(name)
        fields.append((f"gpu_{name}_guard_before", 0xA5A5A5A5))
        fields.extend((f"gpu_{name}_word{index:02d}", value) for index, value in enumerate(words))
        fields.append((f"gpu_{name}_guard_after", 0xA5A5A5A5))

    tipc("memory_create", 111, 2)
    fields.append(("gpu_memory_id", 8))
    tipc("memory_bind", 114)
    tipc("sync_init", 201)
    fields.extend((f"gpu_sync_open_{part}", value) for part, value in (
        ("transport", 0), ("header0", 218), ("header1", 0x80000001), ("descriptor", 0x20)))
    fields.extend((("gpu_sync_handle", 0x503F6), ("gpu_sync_open_result", 0)))
    for name, fd in (("as", 1), ("channel", 2), ("tsg", 3)):
        cmif("open_" + name, fd)
    for name, words in (
        ("as_init", [0xA5A5A5A5] * 10), ("as_bind", [0xA5A5A5A5]),
        ("tsg_bind", [2]), ("fifo", [1, 1, 0, 5, 0, 0, 0, 0]),
        ("object", [0xC797, 0, 0, 0]), ("reserve_image", [2, 4096, 1, 0, 0, 1]),
        ("map_image", [1, 0, 4, 4096, 0, 0, 8192, 0, 0, 1]),
        ("reserve_buffer", [4, 4096, 1, 0, 65536, 1]),
        ("map_buffer", [1, 0, 8, 4096, 0, 0, 16384, 0, 65536, 1]),
    ):
        ioctl(name, words)
    tipc("counter_before", 103, 4)
    fields.extend(("gpu_counter_before_" + part, 0) for part in ("lo", "hi", "width"))
    ioctl("submit", [0, 0, 1, 0, 5, 2])
    tipc("counter_after", 103, 4)
    fields.extend(("gpu_counter_after_" + part, value) for part, value in (
        ("lo", 2), ("hi", 0), ("width", 0)))
    fields.append(("gpu_counter_poll_count", 2))
    ioctl("free_buffer", [0xA5A5A5A5] * 4)
    ioctl("free_image", [0xA5A5A5A5] * 4)
    ioctl("tsg_unbind", [2])
    for name in ("channel", "tsg", "as"):
        cmif("close_" + name)
    tipc("memory_destroy", 112)
    fields.append(("gpu_close_sync", 0))
    return fields


def gpu_marker(name):
    return PREFIX + b"NX2_GPU_" + name.encode() + b"\n"


TSG_BIND = (b"Service.NVDRV <Debug> core/hle/service/nvdrv/devices/nvhost_tsg_gpu.cpp:47:Ioctl1: "
            b"native TSG ioctl=0xc0045401, input=4, output=4, words=0x2,0x0,0x0,0x0,0x0,0x0,0x0,0x0\n")
TSG_UNBIND = TSG_BIND.replace(b"5401", b"5402")
NATIVE_SUBMIT = (b"Service.NVDRV <Debug> core/hle/service/nvdrv/devices/nvhost_gpu.cpp:370:SubmitGPFIFOImpl: "
                 b"native submit channel=0, initialized=true, entries=1, flags=0x2, fence=0:0\n")
PUSHBUFFER = (b"Service.NVDRV <Debug> core/hle/service/nvdrv/devices/nvhost_gpu.cpp:386:SubmitGPFIFOImpl: "
              b"native pushbuffer entry=0 raw=0x2540100010000, address=0x100010000, words=149, mapped=true, "
              b"data=20010000,0000c797,20010049,00000002,200100df,00000001,200101d1,00000000,"
              b"200a0200,00000001,00000000,00000010,00000009,000000d5,00000040,00000001\n")
STAGES = (
    b"HW.GPU <Info> video_core/engines/draw_manager.cpp:312:ProcessDraw: Native graphics shader stage=1, address=0x100011000\n"
    b"HW.GPU <Info> video_core/engines/draw_manager.cpp:312:ProcessDraw: Native graphics shader stage=5, address=0x100012000\n"
)
DRAW = (b"HW.GPU <Debug> video_core/engines/draw_manager.cpp:320:ProcessDraw: "
        b"Translating native graphics draw: indexed=false, vertices=3, instances=1\n")
LOWERED_PAIR = (
    b"Shader <Info> video_core/shader_environment.cpp:642:InitializeNativeCode: Lowered native shader at 0x100011000: 176 source bytes, 3 instructions\n"
    b"Shader <Info> video_core/shader_environment.cpp:642:InitializeNativeCode: Lowered native shader at 0x100012000: 208 source bytes, 5 instructions\n"
)
LOWERED = LOWERED_PAIR * 2


def good_log(variant=0, clear_only=False):
    fields = [(name, 0x402B5DC5 if name == "image_checksum" else value)
              for name, value in observed_fields(variant)] + gpu_fields(variant, clear_only)
    shader_logs = b"" if clear_only else STAGES + DRAW + LOWERED
    return (FRONTEND + CLASSIFIED + RENDERER + marker("BEGIN") + MANAGER + gpu_marker("BEGIN") +
            TSG_BIND + NATIVE_SUBMIT + PUSHBUFFER + gpu_marker("SUBMITTED") + shader_logs +
            gpu_marker("FENCE_OBSERVED") + marker("PRESENT_BEGIN") +
            QUEUED.replace(b"4294967295/0", b"5/2") + marker("PRESENTED") + SUBMITTED + CAPTURED +
            marker("CLEANUP_BEGIN") + gpu_marker("CLEANUP") + TSG_UNBIND +
            b"".join(record(name, value) for name, value in fields) + marker("COMPLETE") + EXIT)


class TriangleExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = image()
        cls.log = good_log()

    def check(self, log=None, *, capture=None, variant=0, clear_only=False, rc=0):
        with contextlib.redirect_stdout(io.StringIO()):
            return gpu.assess(self.log if log is None else log, rc,
                              self.capture if capture is None else capture, variant,
                              clear_only=clear_only)

    def changed(self, name, value):
        original = dict(gpu_fields())[name]
        return self.log.replace(record(name, original), record(name, value), 1)

    def test_complete_original_variant_and_clear_control(self):
        self.assertEqual(len(gpu_fields()), 337)
        self.assertTrue(self.check())
        self.assertTrue(self.check(good_log(1), capture=image(1), variant=1))
        self.assertTrue(self.check(good_log(clear_only=True), capture=image(clear_only=True), clear_only=True))

    def test_cpu_contract_does_not_accept_a_gpu_sentinel_or_observed_fence(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(assess_cpu(self.log, 0, self.capture, 0))

    def test_native_records_must_be_unique_complete_and_source_attributed(self):
        for block in (TSG_BIND, TSG_UNBIND, NATIVE_SUBMIT, PUSHBUFFER, DRAW,
                      *STAGES.splitlines(keepends=True), *LOWERED.splitlines(keepends=True)):
            for replacement in (b"", block + block, b"host echo " + block,
                                block.replace(b":", b":\0", 1), block.replace(b".cpp:", b".cpp:9", 1)):
                with self.subTest(block=block[:55], replacement=replacement[:55]):
                    self.assertFalse(self.check(self.log.replace(block, replacement, 1)))

    def test_each_gpu_marker_is_required_unique_and_source_attributed(self):
        for name in ("BEGIN", "SUBMITTED", "FENCE_OBSERVED", "CLEANUP"):
            block = gpu_marker(name)
            for replacement in (b"", block + block, b"host " + block,
                                b"NX2_GPU_" + name.encode() + b"\n"):
                with self.subTest(name=name, replacement=replacement[:50]):
                    self.assertFalse(self.check(self.log.replace(block, replacement, 1)))
        self.assertFalse(self.check(self.log + gpu_marker("UNREVIEWED")))

    def test_all_fixed_gpu_wire_words_and_guards_are_checked(self):
        fixed = dict(gpu.GPU_FIELDS)
        for name, value in gpu_fields():
            if fixed[name] is not None:
                with self.subTest(name=name):
                    self.assertFalse(self.check(self.changed(name, value ^ 1)))

    def test_missing_duplicate_reordered_or_unknown_gpu_fields_fail(self):
        a = record("gpu_buffer_size", 16384)
        b = record("gpu_buffer_checksum", 0x9FD0D419)
        for replacement in (b, a + a + b, b + a, a + b + record("gpu_host_claim", 0)):
            self.assertFalse(self.check(self.log.replace(a + b, replacement, 1)))

    def test_input_addresses_checksum_and_mode_are_bound(self):
        for name, value in (("gpu_buffer_checksum", 0x37270BE4), ("gpu_clear_only", 1),
                            ("gpu_buffer_address_lo", 0), ("gpu_buffer_address_lo", 0x8006000),
                            ("gpu_buffer_address_lo", 0x8010001), ("gpu_buffer_address_hi", 128)):
            with self.subTest(name=name, value=value):
                self.assertFalse(self.check(self.changed(name, value)))

    def test_object_handle_tsg_mapping_and_fence_relationships_are_checked(self):
        changes = (("gpu_sync_handle", 0x103FE), ("gpu_sync_handle", 0),
                   ("gpu_sync_handle", 0xFFFF8001), ("gpu_open_as_fd", 2),
                   ("gpu_open_as_fd", 0x80000000), ("gpu_memory_id", 4),
                   ("gpu_memory_id", 0), ("gpu_map_image_word02", 8),
                   ("gpu_map_buffer_word02", 4), ("gpu_tsg_bind_word00", 1),
                   ("gpu_tsg_unbind_word00", 1), ("gpu_fifo_word03", 0),
                   ("gpu_fifo_word03", 192), ("gpu_submit_word04", 6),
                   ("gpu_counter_poll_count", 0), ("gpu_counter_poll_count", 1001))
        for name, value in changes:
            with self.subTest(name=name, value=value):
                self.assertFalse(self.check(self.changed(name, value)))
        self.assertFalse(self.check(self.log.replace(b"fence=5/2", b"fence=6/2")))
        self.assertFalse(self.check(self.log.replace(b"fence=5/2", b"fence=5/3")))

    def test_every_dynamic_field_rejects_the_unobserved_sentinel(self):
        for name, expected in gpu.GPU_FIELDS:
            if expected is None:
                with self.subTest(name=name):
                    self.assertFalse(self.check(self.changed(name, 0xFFFFFFFF)))

    def test_native_stream_and_actual_shader_identity_cannot_be_substituted(self):
        for before, after in ((b"flags=0x2", b"flags=0x0"), (b"mapped=true", b"mapped=false"),
                              (b"words=149,", b"words=148,"), (b"0000c797", b"0000b197"),
                              (b"vertices=3", b"vertices=6"), (b"indexed=false", b"indexed=true"),
                              (b"176 source bytes", b"160 source bytes"), (b"5 instructions", b"4 instructions"),
                              (b"stage=1, address=0x100011000", b"stage=1, address=0x100021000"),
                              (b"words=0x2,", b"words=0x3,")):
            with self.subTest(before=before):
                self.assertFalse(self.check(self.log.replace(before, after)))

    def test_shader_work_may_finish_before_submit_svc_returns(self):
        old = gpu_marker("SUBMITTED") + STAGES + DRAW + LOWERED
        new = STAGES + DRAW + LOWERED + gpu_marker("SUBMITTED")
        self.assertTrue(self.check(self.log.replace(old, new)))

    def test_fresh_pipeline_requires_exact_stage_discovery_then_pipeline_lowering(self):
        vertex, fragment = LOWERED_PAIR.splitlines(keepends=True)
        for replacement in (LOWERED_PAIR, LOWERED + LOWERED_PAIR,
                            vertex + vertex + fragment + fragment,
                            fragment + vertex + fragment + vertex):
            with self.subTest(replacement=replacement):
                self.assertFalse(self.check(self.log.replace(LOWERED, replacement)))
        late = self.log.replace(LOWERED, b"").replace(
            gpu_marker("FENCE_OBSERVED"), gpu_marker("FENCE_OBSERVED") + LOWERED)
        self.assertFalse(self.check(late))

    def test_fence_observation_and_capture_must_precede_cleanup(self):
        marker_bytes = gpu_marker("FENCE_OBSERVED")
        late = self.log.replace(marker_bytes, b"").replace(marker("PRESENTED"), marker("PRESENTED") + marker_bytes)
        self.assertFalse(self.check(late))
        early = self.log.replace(gpu_marker("CLEANUP"), b"").replace(CAPTURED, gpu_marker("CLEANUP") + CAPTURED)
        self.assertFalse(self.check(early))
        self.assertFalse(self.check(self.log.replace(CAPTURED, b"")))

    def test_unsupported_substituted_skipped_and_real_error_records_fail(self):
        for diagnostic in (
            b"Shader <Warning> video_core/shader_environment.cpp:596:InitializeNativeCode: Native shader resumed: key=12, instructions=5\n",
            b"Shader <Warning> video_core/shader_environment.cpp:538:InitializeNativeCode: ampere frontend falls back to lowering\n",
            b"Render.Vulkan <Warning> video_core/renderer_vulkan/vk_pipeline_cache.cpp:917:CreateGraphicsPipeline: Skipping shader with known issues\n",
            b"HW.GPU <Error> video_core/renderer_vulkan/vk_rasterizer.cpp:265:PrepareDraw: Native graphics draw failed\n",
            b"Service.NVDRV <Error> core/hle/service/nvdrv/nvdrv_interface.cpp:68:Ioctl1: invalid native input\n",
            b"Shader <Info> video_core/shader_environment.cpp:595:InitializeNativeCode: placeholder shader\n",
        ):
            with self.subTest(diagnostic=diagnostic):
                self.assertFalse(self.check(self.log.replace(gpu_marker("FENCE_OBSERVED"), diagnostic + gpu_marker("FENCE_OBSERVED"))))

    def test_clear_control_cannot_hide_draws_or_claim_triangle_success(self):
        clear = good_log(clear_only=True)
        pixels = image(clear_only=True)
        self.assertFalse(self.check(clear, capture=pixels))
        self.assertFalse(self.check(clear, capture=self.capture, clear_only=True))
        self.assertFalse(self.check(clear.replace(gpu_marker("FENCE_OBSERVED"), DRAW + gpu_marker("FENCE_OBSERVED")),
                                    capture=pixels, clear_only=True))

    def test_pixels_successful_counter_or_raw_guest_output_alone_are_insufficient(self):
        guest_only = b"".join(line[len(PREFIX):] for line in self.log.splitlines(keepends=True)
                               if line.startswith(PREFIX))
        self.assertFalse(self.check(guest_only))
        self.assertFalse(self.check(capture=b""))
        for rc in (1, 124, 137, 139):
            self.assertFalse(self.check(rc=rc))


class TrianglePixelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = image(0)
        cls.alternate = image(1)
        cls.clear = image(clear_only=True)

    def check(self, capture, variant=0, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return gpu.verify_pixels(capture, variant, **kwargs)

    def test_integer_coverage_matches_thirty_independently_enumerated_pixels(self):
        self.assertEqual(sum(row.count("#") for row in MASK), 30)
        for variant in (0, 1):
            for y, row in enumerate(MASK):
                for x, cell in enumerate(row):
                    wanted = gpu.FRAGMENT_COLOURS[variant] if cell == "#" else gpu.BACKGROUND
                    self.assertEqual(gpu.logical_pixel(x, y, variant), wanted)

    def test_both_colour_variants_match_all_pixels_and_reject_each_other(self):
        self.assertTrue(self.check(self.original, 0))
        self.assertTrue(self.check(self.alternate, 1))
        self.assertFalse(self.check(self.original, 1))
        self.assertFalse(self.check(self.alternate, 0))

    def test_clear_control_is_exact_background_and_fails_both_triangle_references(self):
        self.assertTrue(self.check(self.clear, clear_only=True))
        for variant in (0, 1):
            self.assertFalse(self.check(self.clear, variant))
            self.assertFalse(self.check(image(variant), variant, clear_only=True))

    def test_cpu_sentinel_and_blank_capture_cannot_pass_any_mode(self):
        for capture in (image(sentinel=True), bytes(gpu.CAPTURE_SIZE)):
            for clear_only in (False, True):
                self.assertFalse(self.check(capture, clear_only=clear_only))

    def test_single_pixel_alpha_and_final_byte_corruption_fail(self):
        for offset in (18, 18 + (2 * 120 * 1920 + 2 * 120) * 4,
                       18 + (3 * 120 * 1920 + 3 * 120) * 4 + 3, len(self.original) - 1):
            bad = bytearray(self.original)
            bad[offset] ^= 1
            with self.subTest(offset=offset):
                self.assertFalse(self.check(bytes(bad)))

    def test_flipped_image_and_swapped_channels_are_rejected(self):
        header, pixels = self.original[:18], self.original[18:]
        row_bytes = 1920 * 4
        flipped = b"".join(pixels[y * row_bytes:(y + 1) * row_bytes]
                           for y in reversed(range(1080)))
        self.assertFalse(self.check(header + flipped))
        swapped = bytearray(pixels)
        swapped[0::4], swapped[2::4] = pixels[2::4], pixels[0::4]
        self.assertFalse(self.check(header + swapped))

    def test_envelope_length_variant_and_mode_are_exact(self):
        for offset in range(18):
            bad = bytearray(self.original)
            bad[offset] ^= 1
            with self.subTest(header_byte=offset):
                self.assertFalse(self.check(bytes(bad)))
        for bad in (b"", self.original[:-1], self.original + b"\0"):
            self.assertFalse(self.check(bad))
        for variant in (-1, 2, True, 0.0):
            self.assertFalse(self.check(self.original, variant))
        self.assertFalse(self.check(self.original, clear_only=0))
        for x, y in ((-1, 0), (16, 0), (0, -1), (0, 9)):
            with self.assertRaises(ValueError):
                gpu.logical_pixel(x, y, 0)


if __name__ == "__main__":
    unittest.main()
