# SPDX-License-Identifier: GPL-3.0-only
"""Prevent inherited debug switches from substituting for original GPU work."""
import configparser
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_native_frame import (
    ANIMATION_CONFIG, CAPTURE_SIZE, CONFIG, FLUSH_CONFIG, GPU_CONFIG, AnimationCaptures,
    verify_shader_inputs, vulkan_environment,
)


class NativeFrameEnvironmentTests(unittest.TestCase):
    def test_observed_shader_pages_must_match_the_selected_originals(self):
        from native_gpu_commands import build_gpu_buffer
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertTrue(verify_shader_inputs(root, 0, True))
            self.assertFalse(verify_shader_inputs(root, 0, False))
            for variant in (0, 1):
                inputs = build_gpu_buffer(variant)
                vertex, fragment = (root / f"native-graphics-shader-{stage}.bin" for stage in (1, 5))
                vertex.write_bytes(inputs[0x1000:0x2000])
                fragment.write_bytes(inputs[0x2000:0x3000])
                self.assertTrue(verify_shader_inputs(root, variant, False))
                self.assertEqual(verify_shader_inputs(root, 1, False, animation=True), variant == 0)
                self.assertFalse(verify_shader_inputs(root, 1 - variant, False))
                self.assertFalse(verify_shader_inputs(root, variant, True))
                fragment.write_bytes(inputs[0x2000:0x3000] + b"\0")
                self.assertFalse(verify_shader_inputs(root, variant, False))
            fragment.write_bytes(inputs[0x2000:0x3000])
            (root / "native-graphics-shader-0.bin").write_bytes(bytes(4096))
            self.assertFalse(verify_shader_inputs(root, 1, False))

    def test_child_environment_forces_reviewed_mode_and_discards_overrides(self):
        inherited = {"PATH": "/test/bin", "HOME": "/original-home",
                     "EDEN_NATIVE_STRICT": "0", "EDEN_NATIVE_FRONTEND": "off",
                     "EDEN_NATIVE_SHADER_OVERRIDE_DIR": "/replacement-shaders",
                     "EDEN_NATIVE_SKIP_VS": "1", "EDEN_NATIVE_DEBUG_CLEAR": "1",
                     "EDEN_UNKNOWN_OVERRIDE": "1", "VK_DRIVER_FILES": "/wrong-icd",
                     "VK_ICD_FILENAMES": "/other-icd", "VK_ADD_DRIVER_FILES": "/extra-icd",
                     "VK_INSTANCE_LAYERS": "unexpected", "SDL_VIDEODRIVER": "dummy",
                     "SDL_AUDIODRIVER": "unexpected"}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, inherited, clear=True):
            home, icd = Path(temporary), Path("/reviewed-lvp.json")
            for gpu in (False, True):
                with self.subTest(gpu=gpu):
                    env = vulkan_environment(home, icd, gpu=gpu)
                    expected = {"EDEN_NX2_HIDE_WINDOW": "0", "EDEN_NATIVE_FRAME_ON_DEMAND": "1"}
                    if gpu:
                        expected.update(EDEN_NATIVE_STRICT="1", EDEN_NATIVE_FRONTEND="lower",
                                        EDEN_NATIVE_DRAW_DIAGNOSTICS="1")
                    self.assertEqual({k: v for k, v in env.items() if k.startswith("EDEN_")}, expected)
                    self.assertEqual(env["VK_DRIVER_FILES"], str(icd))
                    self.assertEqual(env["SDL_VIDEO_DRIVER"], "x11")
                    self.assertEqual(env["SDL_AUDIO_DRIVER"], "dummy")
                    self.assertEqual(env["HOME"], str(home))
                    self.assertEqual(env["PATH"], inherited["PATH"])
                    for key in ("VK_ICD_FILENAMES", "VK_ADD_DRIVER_FILES", "VK_INSTANCE_LAYERS",
                                "SDL_VIDEODRIVER", "SDL_AUDIODRIVER"):
                        self.assertNotIn(key, env)
                    self.assertEqual((home / "runtime").stat().st_mode & 0o777, 0o700)
            self.assertEqual(dict(os.environ), inherited)

    def test_gpu_settings_require_synchronous_shader_build_and_accurate_fences(self):
        config = configparser.ConfigParser()
        config.read_string(GPU_CONFIG)
        renderer = config["Renderer"]
        for name, expected in (("backend", "1"), ("gpu_accuracy", "1"),
                               ("gpu_fence_behavior", "3"), ("use_asynchronous_shaders", "false")):
            self.assertEqual(renderer[name], expected)
            self.assertEqual(renderer[name + "\\default"], "false")
        self.assertEqual(config["Miscellaneous"]["log_filter"],
                         "*:Info HW.GPU:Debug Service.NVDRV:Debug Shader:Debug")
        self.assertTrue(GPU_CONFIG.startswith(CONFIG))

    def test_animation_retirement_logging_and_durable_file_log_are_explicit(self):
        config = configparser.ConfigParser()
        config.read_string(ANIMATION_CONFIG + FLUSH_CONFIG)
        self.assertIn("Service.AM:Debug", config["Miscellaneous"]["log_filter"])
        self.assertEqual(config["Miscellaneous"]["flush_line"], "true")
        self.assertEqual(config["Miscellaneous"]["flush_line\\default"], "false")


class AnimationCaptureTests(unittest.TestCase):
    callback = ("[ 1.234] Service.NVDRV <Info> "
                "core/hle/service/nvdrv/devices/nvdisp_disp0.cpp:147:operator(): "
                "Captured composited frame: 1920x1080, saved=true, nonblack=true")

    def test_archives_each_completed_capture_before_rearming_and_keeps_first_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "runtime.log"
            log.write_bytes(b"")
            collector = AnimationCaptures(root)
            for frame in range(4):
                request = root / "native-frame.request"
                if frame:
                    self.assertTrue(request.exists())
                    request.unlink()  # The compositor consumes each request.
                pixels = bytes([frame]) * CAPTURE_SIZE
                (root / "native-latest-frame.tga").write_bytes(pixels)
                with log.open("ab") as stream:
                    stream.write(("\0\x1b[32m" + self.callback + "\x1b[0m\n").encode())
                collector.poll()
                self.assertIsNone(collector.error)
                self.assertEqual((root / f"frame-{frame}.tga").read_bytes(), pixels)
                self.assertEqual(len(collector.events), frame + 1)
                self.assertEqual(request.exists(), frame < 3)
            self.assertEqual((root / "frame-0.tga").read_bytes(), bytes(CAPTURE_SIZE))
            collector.poll()
            self.assertEqual(len(collector.events), 4)

    def test_incomplete_or_wrongly_attributed_callback_cannot_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "runtime.log"
            (root / "native-latest-frame.tga").write_bytes(bytes(CAPTURE_SIZE))
            collector = AnimationCaptures(root)
            log.write_text(self.callback.replace(":147:", ":148:") + "\n" + self.callback[:40])
            collector.poll()
            self.assertEqual(collector.events, [])
            with log.open("a") as stream:
                stream.write(self.callback[40:] + "\n")
            collector.poll()
            self.assertIsNone(collector.error)
            self.assertEqual(len(collector.events), 1)

    def test_missing_short_or_replaced_capture_preserves_failure_without_rearming(self):
        for invalid in ("missing", "short", "preexisting"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "runtime.log").write_text(self.callback + "\n")
                if invalid != "missing":
                    (root / "native-latest-frame.tga").write_bytes(
                        b"short" if invalid == "short" else bytes(CAPTURE_SIZE))
                if invalid == "preexisting":
                    (root / "frame-0.tga").write_bytes(b"previous evidence")
                collector = AnimationCaptures(root)
                collector.poll()
                self.assertIsNotNone(collector.error)
                self.assertFalse((root / "native-frame.request").exists())
                first_error = collector.error
                collector.poll()
                self.assertEqual(collector.error, first_error)
                if invalid == "preexisting":
                    self.assertEqual((root / "frame-0.tga").read_bytes(), b"previous evidence")

    def test_duplicate_callback_is_not_treated_as_a_fresh_frame(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runtime.log").write_text((self.callback + "\n") * 2)
            (root / "native-latest-frame.tga").write_bytes(bytes(CAPTURE_SIZE))
            collector = AnimationCaptures(root)
            collector.poll()
            self.assertIsNotNone(collector.error)  # The newly armed request was never consumed.


if __name__ == "__main__":
    unittest.main()
