# SPDX-License-Identifier: GPL-3.0-only
"""Prevent inherited debug switches from substituting for original GPU work."""
import configparser
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_native_frame import CONFIG, GPU_CONFIG, verify_shader_inputs, vulkan_environment


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


if __name__ == "__main__":
    unittest.main()
