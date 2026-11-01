# SPDX-License-Identifier: GPL-3.0-only
"""Independent triangle image controls; synthetic logs are not runtime evidence."""
import contextlib
from functools import lru_cache
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


def candidate_log(log):
    for before, after in (
        (b"nvhost_gpu.cpp:370:", b"nvhost_gpu.cpp:379:"),
        (b"nvhost_gpu.cpp:386:", b"nvhost_gpu.cpp:395:"),
        (b"draw_manager.cpp:312:", b"draw_manager.cpp:339:"),
        (b"draw_manager.cpp:320:", b"draw_manager.cpp:347:"),
        (b"Shader <Info> video_core/shader_environment.cpp:642:",
         b"Shader <Debug> video_core/shader_environment.cpp:697:"),
    ):
        log = log.replace(before, after)
    return log


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

    def check(self, log=None, *, capture=None, variant=0, clear_only=False, rc=0,
              eden_revision=gpu.BASELINE_SHA):
        with contextlib.redirect_stdout(io.StringIO()):
            return gpu.assess(self.log if log is None else log, rc,
                              self.capture if capture is None else capture, variant,
                              clear_only=clear_only, eden_revision=eden_revision)

    def changed(self, name, value):
        original = dict(gpu_fields())[name]
        return self.log.replace(record(name, original), record(name, value), 1)

    def test_complete_original_variant_and_clear_control(self):
        self.assertEqual(len(gpu_fields()), 337)
        self.assertTrue(self.check())
        self.assertTrue(self.check(good_log(1), capture=image(1), variant=1))
        self.assertTrue(self.check(good_log(clear_only=True), capture=image(clear_only=True), clear_only=True))

    def test_candidate_preserves_both_triangles_and_clear_control(self):
        for variant, clear_only in ((0, False), (1, False), (0, True)):
            with self.subTest(variant=variant, clear_only=clear_only):
                self.assertTrue(self.check(candidate_log(good_log(variant, clear_only)),
                    capture=image(variant, clear_only=clear_only), variant=variant,
                    clear_only=clear_only, eden_revision=gpu.CANDIDATE_SHA))

    def test_revision_mismatch_mixed_sites_and_old_lowering_level_fail(self):
        candidate = candidate_log(self.log)
        self.assertFalse(self.check(candidate))
        self.assertFalse(self.check(self.log, eden_revision=gpu.CANDIDATE_SHA))
        for block in (NATIVE_SUBMIT, PUSHBUFFER, DRAW, *STAGES.splitlines(keepends=True),
                      *LOWERED.splitlines(keepends=True)):
            with self.subTest(block=block[:60]):
                mixed = candidate.replace(candidate_log(block), block, 1)
                self.assertFalse(self.check(mixed, eden_revision=gpu.CANDIDATE_SHA))
        old_level = candidate.replace(b"Shader <Debug>", b"Shader <Info>")
        self.assertFalse(self.check(old_level, eden_revision=gpu.CANDIDATE_SHA))
        for revision in ("0" * 40, "main", "b2cef0c", 0, False):
            with self.subTest(revision=revision):
                self.assertFalse(self.check(eden_revision=revision))

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


ANIMATION_MASKS = (
    MASK,
    ("................", "................", "...###########..", "...########.....",
     "...######.......", "...####.........", "...#............", "................", "................"),
    ("................", "................", "................", "..###########...",
     "..########......", "..######........", "..####..........", "..#.............", "................"),
    ("................", "................", ".###########....", ".########.......",
     ".######.........", ".####...........", ".#..............", "................", "................"),
)


@lru_cache(maxsize=8)
def animation_image(variant, frame):
    # Hand-enumerated screen masks; no guest input or assessor geometry import.
    selected = ((0, 1, 2, 3), (0, 3, 2, 1))[variant][frame]
    pixels = bytearray()
    for row in ANIMATION_MASKS[selected]:
        line = b"".join((bytes((255, 0, 255, 255)) if cell == "#" else
                         bytes((48, 32, 16, 255))) * 120 for cell in row)
        pixels.extend(line * 120)
    return bytes.fromhex("000002000000000000000000800738042028") + pixels


def animation_fields(variant, frame, *, final=False):
    fields = observed_fields(variant)
    overrides = {"image_checksum": 0x402B5DC5, "present_lo": (0x7FFE, 0x7FFD)[frame % 2],
                 "poll_count": 20, "poll_queued_count": 2, "poll_released_count": 18}
    cleanup = False
    for index, (name, value) in enumerate(fields):
        if name == "unbind_display_transport":
            cleanup = True
        fields[index] = (name, 0xFFFFFFFF if cleanup and not final and name != "fail_step"
                         else overrides.get(name, value))
    fields.extend((("animation_frame", frame), ("animation_slot", frame % 2),
                   ("second_memory_id", 12), ("second_image_id", 2)))
    for name, command, words in (("second_memory_create", 111, 2),
                                 ("second_memory_bind", 114, 1), ("second_image_create", 429, 2),
                                 ("second_pool_create", 315, 1), ("second_pool_destroy", 314, 1),
                                 ("second_image_destroy", 430, 1), ("second_memory_destroy", 112, 1)):
        fields.extend((name + "_" + part, 0xFFFFFFFF if not final and "destroy" in name else value)
                      for part, value in (("transport", 0), ("header0", command + 16),
                                          ("header1", words), ("result", 0)))
    fields.extend((("animation_target_address_lo", 0x8006000 + (frame % 2) * 8192),
                   ("animation_target_address_hi", 0)))
    gpu_records = gpu_fields()
    checksums = ((0x9FD0D419, 0xA47DD7D9, 0xD29CD296, 0x555B0019),
                 (0x9FD0D419, 0x555B0019, 0xD29CD296, 0xA47DD7D9))
    overrides = {"gpu_reserve_image_word00": 4, "gpu_buffer_checksum": checksums[variant][frame],
                 "gpu_counter_before_lo": frame * 2, "gpu_counter_after_lo": (frame + 1) * 2,
                 "gpu_submit_word05": (frame + 1) * 2}
    cleanup = False
    for name, value in gpu_records:
        if name == "gpu_free_buffer_transport":
            cleanup = True
        fields.append((name, 0xFFFFFFFF if cleanup and not final else overrides.get(name, value)))
    fields.extend(("gpu_map_second_image_" + part, value) for part, value in (
        ("transport", 0), ("header0", 0), ("header1", 12), ("pad0", 0), ("pad1", 0),
        ("magic", 0x4F434653), ("version", 0), ("result_lo", 0), ("result_hi", 0),
        ("nv_result", 0), ("guard_before", 0xA5A5A5A5)))
    fields.extend((f"gpu_map_second_image_word{index:02d}", value)
                  for index, value in enumerate((1, 0, 12, 4096, 0, 0, 8192, 0, 8192, 1)))
    fields.append(("gpu_map_second_image_guard_after", 0xA5A5A5A5))
    return fields


def animation_marker(name):
    return PREFIX + b"NX2_ANIMATION_FRAME_" + name.encode() + b"\n"


def availability(mask):
    return (b"Service.AM <Debug> core/hle/service/am/service/graphics_supervisor.cpp:808:GetClientAvailability: "
            b"VI2 client availability token=0x32495632584e0001, layer=1, mask=" +
            hex(mask).encode() + b", result=0x0\n")


def animation_log(variant=0):
    result = FRONTEND + CLASSIFIED + RENDERER + marker("BEGIN") + MANAGER
    for frame in range(4):
        slot, target = frame % 2, (frame + 1) * 2
        queued_mask = (0x7FFE, 0x7FFD)[slot]
        queued = QUEUED.replace(b"image=1, slot=0", f"image={slot + 1}, slot={slot}".encode())
        queued = queued.replace(b"4294967295/0", f"5/{target}".encode())
        push = PUSHBUFFER if not slot else PUSHBUFFER.replace(
            b"200a0200,00000001,00000000", b"200a0200,00000001,00002000")
        retired = (b"Service.AM <Debug> core/hle/service/am/service/graphics_supervisor.cpp:858:RefreshReleasedBuffers: " +
                   f"Native display buffer retired: slot={slot}, mask=0x7fff\n".encode())
        presented = (b"Service.AM <Debug> core/hle/service/am/service/graphics_supervisor.cpp:965:PresentClientBuffer: " +
                     f"VI2 present token=0x32495632584e0001, image={slot + 1}, slot={slot}, mask={queued_mask:#x}, result=0x0\n".encode())
        fence = (b"Service.NVDRV <Info> core/hle/service/nvdrv/devices/nvdisp_disp0.cpp:112:Composite: " +
                 f"Native composite waits for syncpoint=5/{target}, current={target}\n".encode())
        composite = SUBMITTED.replace(b"0x80004000", (b"0x80004000", b"0x80006000")[slot])
        result += (animation_marker("BEGIN") + availability(0x7FFF) +
                   (gpu_marker("BEGIN") + TSG_BIND if frame == 0 else b"") +
                   NATIVE_SUBMIT + push + gpu_marker("SUBMITTED") +
                   (STAGES + DRAW + LOWERED if frame == 0 else b"") + gpu_marker("FENCE_OBSERVED") +
                   marker("PRESENT_BEGIN") + queued + presented + marker("PRESENTED") +
                   availability(queued_mask) * 2 + fence + composite + CAPTURED + retired +
                   availability(0x7FFF) * 18 +
                   b"".join(record(name, value) for name, value in animation_fields(variant, frame)) +
                   animation_marker("END"))
    return (result + marker("CLEANUP_BEGIN") + gpu_marker("CLEANUP") + TSG_UNBIND +
            b"".join(record(name, value) for name, value in animation_fields(variant, 3, final=True)) +
            marker("COMPLETE") + EXIT)


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.captures = tuple(animation_image(0, frame) for frame in range(4))
        cls.log = animation_log()

    def check(self, log=None, *, captures=None, variant=0, rc=0, revision=gpu.BASELINE_SHA):
        with contextlib.redirect_stdout(io.StringIO()):
            return gpu.assess_animation(self.log if log is None else log, rc,
                self.captures if captures is None else captures, variant, eden_revision=revision)

    def test_both_vertex_sequences_and_both_source_revisions(self):
        self.assertEqual(len(animation_fields(0, 0)), 674)
        for variant in (0, 1):
            log = animation_log(variant)
            captures = tuple(animation_image(variant, frame) for frame in range(4))
            self.assertTrue(self.check(log, captures=captures, variant=variant))
            self.assertTrue(self.check(candidate_log(log), captures=captures, variant=variant,
                                       revision=gpu.CANDIDATE_SHA))

    def test_independent_masks_are_distinct_and_only_vertex_order_changes(self):
        self.assertEqual(len(set(self.captures)), 4)
        self.assertEqual(self.captures[0], image())
        self.assertEqual(animation_image(1, 1), self.captures[3])
        self.assertEqual(animation_image(1, 3), self.captures[1])
        for frame, capture in enumerate(self.captures):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(gpu.verify_animation_pixels(capture, 0, frame))
                for wrong in range(4):
                    if wrong != frame:
                        self.assertFalse(gpu.verify_animation_pixels(capture, 0, wrong))

    def test_stale_reordered_missing_and_corrupt_captures_fail(self):
        for captures in (self.captures[:3], self.captures + self.captures[:1],
                         (self.captures[0],) * 4, tuple(reversed(self.captures)),
                         tuple(animation_image(1, frame) for frame in range(4))):
            self.assertFalse(self.check(captures=captures))
        bad = bytearray(self.captures[2])
        bad[-1] ^= 1
        self.assertFalse(self.check(captures=(*self.captures[:2], bytes(bad), self.captures[3])))

    def test_source_attributed_events_are_required_and_unique(self):
        for block in (NATIVE_SUBMIT, PUSHBUFFER, TSG_BIND, TSG_UNBIND, STAGES, DRAW,
                      LOWERED, CAPTURED, SUBMITTED, availability(0x7FFE),
                      animation_marker("BEGIN"), animation_marker("END")):
            for replacement in (b"", block + block, b"host echo " + block,
                                block.replace(b".cpp:", b".cpp:9", 1)):
                if replacement != block:
                    with self.subTest(block=block[:50], replacement=replacement[:25]):
                        self.assertFalse(self.check(self.log.replace(block, replacement, 1)))

    def test_capture_must_complete_before_the_next_guest_write_phase(self):
        parts = self.log.split(animation_marker("BEGIN"))
        parts[1] = parts[1].replace(CAPTURED, b"", 1)
        parts[2] = CAPTURED + parts[2]
        self.assertFalse(self.check(animation_marker("BEGIN").join(parts)))
        self.assertFalse(self.check(self.log.replace(CAPTURED, b"", 1) + CAPTURED))
        early_gpu = self.log.replace(gpu_marker("BEGIN"), b"", 1).replace(
            animation_marker("BEGIN"), gpu_marker("BEGIN") + animation_marker("BEGIN"), 1)
        self.assertFalse(self.check(early_gpu))

    def test_compositor_may_finish_before_present_returns_and_first_poll(self):
        parts = self.log.split(animation_marker("BEGIN"))
        first = parts[1]
        fence = (b"Service.NVDRV <Info> core/hle/service/nvdrv/devices/nvdisp_disp0.cpp:112:Composite: "
                 b"Native composite waits for syncpoint=5/2, current=2\n")
        capture = fence + SUBMITTED + CAPTURED
        retired = (b"Service.AM <Debug> core/hle/service/am/service/graphics_supervisor.cpp:858:RefreshReleasedBuffers: "
                   b"Native display buffer retired: slot=0, mask=0x7fff\n")
        first = first.replace(capture, b"", 1).replace(
            marker("PRESENT_BEGIN"), marker("PRESENT_BEGIN") + capture, 1)
        first = first.replace(retired, b"", 1).replace(marker("PRESENTED"), retired + marker("PRESENTED"), 1)
        first = first.replace(availability(0x7FFE) * 2, availability(0x7FFF) * 2, 1)
        first = first.replace(record("poll_queued_count", 2), record("poll_queued_count", 0), 1)
        first = first.replace(record("poll_released_count", 18), record("poll_released_count", 20), 1)
        parts[1] = first
        self.assertTrue(self.check(animation_marker("BEGIN").join(parts)))

    def test_each_frame_observation_binds_inputs_fences_and_two_objects(self):
        changes = (("animation_frame", 3), ("animation_slot", 1),
                   ("animation_target_address_lo", 0x8006001), ("second_memory_id", 4),
                   ("second_image_id", 1), ("gpu_map_second_image_word02", 4),
                   ("gpu_buffer_checksum", 0xA47DD7D9), ("gpu_counter_after_lo", 4),
                   ("gpu_submit_word05", 4), ("gpu_counter_before_lo", 2),
                   ("gpu_counter_poll_count", 0), ("poll_count", 19),
                   ("poll_queued_count", 20), ("poll_released_count", 0),
                   ("close_vi2", 0), ("fail_step", 0xFFFFFFFF))
        fields = dict(animation_fields(0, 0))
        for name, value in changes:
            with self.subTest(name=name):
                self.assertFalse(self.check(self.log.replace(record(name, fields[name]), record(name, value), 1)))

    def test_missing_reordered_extra_fields_and_incomplete_cleanup_fail(self):
        block = record("animation_frame", 0) + record("animation_slot", 0)
        for replacement in (b"", block + block, record("animation_slot", 0) + record("animation_frame", 0),
                            block + record("unexpected", 0)):
            self.assertFalse(self.check(self.log.replace(block, replacement, 1)))
        self.assertFalse(self.check(self.log.replace(record("gpu_close_sync", 0), record("gpu_close_sync", 1))))
        self.assertFalse(self.check(self.log.replace(record("second_memory_destroy_result", 0),
                                                     record("second_memory_destroy_result", 0xFFFFFFFF))))
        self.assertFalse(self.check(self.log[:self.log.index(marker("CLEANUP_BEGIN"))]))

    def test_ownership_and_returned_fence_require_actual_engine_records(self):
        for before, after in ((b"slot=1, mask=0x7fff", b"slot=0, mask=0x7fff"),
                              (b"fence=5/4", b"fence=5/2"),
                              (b"syncpoint=5/4, current=4", b"syncpoint=5/4, current=2"),
                              (b"address=0x80006000", b"address=0x80004000"),
                              (b"layer=1, mask=0x7fff", b"layer=2, mask=0x7fff")):
            with self.subTest(before=before):
                self.assertFalse(self.check(self.log.replace(before, after, 1)))

    def test_failures_placeholders_wrong_revisions_and_bad_inputs_fail_closed(self):
        for extra in (b"Shader <Error> unsupported instruction\n", b"unexpected placeholder\n",
                      b"Assertion Failed\n", gpu_marker("UNREVIEWED"), b"NX2_ANIMATION_FRAME_BEGIN\n"):
            self.assertFalse(self.check(self.log + extra))
        for rc in (1, 124, 137):
            self.assertFalse(self.check(rc=rc))
        self.assertFalse(self.check(candidate_log(self.log)))
        self.assertFalse(self.check(revision="main"))
        for variant in (-1, 2, True, 0.0):
            self.assertFalse(self.check(variant=variant))
        self.assertFalse(self.check(captures=b"xxxx"))


if __name__ == "__main__":
    unittest.main()
