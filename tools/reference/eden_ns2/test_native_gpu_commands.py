# SPDX-License-Identifier: GPL-3.0-only
"""Original input checks and optional frozen shader capture/lowering unit test.

The C++ check runs the real pinned headers on the emitted bytes. Neither this
suite nor its successful lowering result is evidence of a guest GPU draw.
"""
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

import native_gpu_commands as gpu
from build_native_engine import CANDIDATE_SHA, EDEN_REVISIONS, git


def packets(blob):
    """Independent, restricted decoder for the generated GPFIFO method packets."""
    words = struct.unpack_from("<" + "I" * gpu.GPFIFO_WORD_COUNT, blob)
    result, offset = [], 0
    while offset < len(words):
        header = words[offset]
        if header >> 29 != 1 or (header >> 13) & 7:
            raise ValueError("expected increasing packets on subchannel 0")
        count = (header >> 16) & 0x1FFF
        if not count or count > len(words) - offset - 1:
            raise ValueError("packet exceeds the submitted command range")
        method = (header & 0x1FFF) * 4
        if method + (count - 1) * 4 >= 0x3800:
            raise ValueError("packet exceeds the frozen graphics register file")
        result.append((method, words[offset + 1:offset + count + 1]))
        offset += count + 1
    return result


class NativeGpuCommandsTests(unittest.TestCase):
    def test_bounded_regions_and_padding(self):
        blob = gpu.build_gpu_buffer()
        self.assertEqual(len(blob), 0x4000)
        self.assertEqual(gpu.GPFIFO_WORD_COUNT, 149)
        self.assertEqual(blob[596:0x1000], bytes(0x1000 - 596))
        self.assertEqual(blob[0x10B0:0x2000], bytes(0x2000 - 0x10B0))
        self.assertEqual(blob[0x20D0:0x3000], bytes(0x3000 - 0x20D0))
        self.assertEqual(blob[0x3030:], bytes(0x4000 - 0x3030))
        self.assertEqual(packets(blob)[0], (0, (0xC797,)))
        self.assertEqual(packets(blob)[-1], (0x110, (0,)))

    def test_native_target_and_program_addresses(self):
        regs = {}
        for method, arguments in packets(gpu.build_gpu_buffer()):
            for index, value in enumerate(arguments):
                regs[method + index * 4] = value
        self.assertEqual(tuple(regs[p] for p in range(0x800, 0x828, 4)),
                         (1, 0, 16, 9, 0xD5, 0x40, 1, 0x800, 0, 0))
        self.assertEqual((regs[0x600], regs[0x604]), (0, 48))
        self.assertEqual(tuple(regs[p] for p in range(0x1C00, 0x1C10, 4)),
                         (0x1010, 1, 0x13000, 0))
        self.assertEqual(regs[0x1160], 0x38200000)
        self.assertEqual((regs[0x2054], regs[0x2058]), (1, 0x11000))
        self.assertEqual((regs[0x2154], regs[0x2158]), (1, 0x12000))
        self.assertEqual((regs[0x2040], regs[0x2140]), (0x11, 0x51))
        self.assertTrue(all(regs[p] == 0 for p in (0x2000, 0x2080, 0x20C0, 0x2100)))
        self.assertEqual(regs[0x121C], 1)
        self.assertEqual(regs[0x1A00], 0x1111)
        self.assertEqual(regs[0x1558], 1)

    def test_viewport_positions_and_no_inherited_blend_or_depth(self):
        blob = gpu.build_gpu_buffer()
        regs = {method + 4 * n: value for method, args in packets(blob)
                for n, value in enumerate(args)}
        floats = lambda addr, n: struct.unpack("<" + "f" * n,
                    struct.pack("<" + "I" * n, *(regs[addr + 4 * i] for i in range(n))))
        self.assertEqual(floats(0xA00, 6), (8, 4.5, 1, 8, 4.5, 0))
        self.assertEqual((regs[0x13AC], regs[0x192C]), (0, 1))
        vertices = struct.unpack_from("<12f", blob, 0x3000)
        for i, (x, y) in enumerate(((2, 2), (14, 2), (2, 7))):
            self.assertAlmostEqual(8 * vertices[4 * i] + 8, x, places=6)
            self.assertAlmostEqual(4.5 * vertices[4 * i + 1] + 4.5, y, places=6)
            self.assertEqual(vertices[4 * i + 2:4 * i + 4], (0.5, 1))
        for method in (0x12CC, 0x12E4, 0x12E8, 0x12EC, 0x1380, 0x1538,
                       0x153C, 0x15B8, 0x15D0, 0x1918, 0x19BC, 0x19C4):
            self.assertEqual(regs[method], 0, hex(method))
        self.assertTrue(all(regs[p] == 0 for p in range(0x1360, 0x1380, 4)))
        clear = tuple(round(x * 255) for x in floats(0xD80, 4))
        self.assertEqual(clear, (16, 32, 48, 255))
        self.assertNotEqual(clear, gpu.SENTINEL_RGBA)

    def test_clear_only_has_identical_inputs_but_no_draw_trigger(self):
        normal = gpu.build_gpu_buffer()
        control = gpu.build_gpu_buffer(clear_only=True)
        self.assertEqual(normal[0x1000:], control[0x1000:])
        a, b = packets(normal), packets(control)
        self.assertEqual(len(a), len(b))
        changes = [(before, after) for before, after in zip(a, b) if before != after]
        self.assertEqual(changes, [
            ((0x1618, (4,)), (0x100, (4,))),
            ((0x0D74, (0,)), (0x100, (0,))),
            ((0x0D78, (3,)), (0x100, (3,))),
            ((0x1614, (0,)), (0x100, (0,))),
        ])
        self.assertEqual(a[-6:], [(0x19D0, (0x3C,)), (0x1618, (4,)),
                                (0xD74, (0,)), (0xD78, (3,)),
                                (0x1614, (0,)), (0x110, (0,))])
        self.assertFalse(any(method in (0x1618, 0x1614) for method, _ in b))

    def test_variant_changes_only_three_fragment_immediates(self):
        a, b = gpu.build_gpu_buffer(0), gpu.build_gpu_buffer(1)
        changed = {i for i in range(len(a)) if a[i] != b[i]}
        self.assertEqual(changed, {0x2080 + 16 * reg + byte
                                  for reg in range(3) for byte in (6, 7)})
        for blob, expected in ((a, (1, 0, 1, 1)), (b, (0, 1, 0, 1))):
            actual = tuple(struct.unpack_from("<f", blob, 0x2084 + 16 * i)[0]
                           for i in range(4))
            self.assertEqual(actual, expected)

    def test_shader_headers_and_exact_end_of_capture(self):
        blob = gpu.build_gpu_buffer()
        vs, fs = blob[0x1000:0x1080], blob[0x2000:0x2080]
        self.assertEqual({i: b for i, b in enumerate(vs) if b}, {0x18: 0xF, 0x35: 0xF0})
        self.assertEqual({i: b for i, b in enumerate(fs) if b}, {0x48: 0xF})
        for offset in (0x10A0, 0x20C0):
            self.assertEqual(struct.unpack_from("<4I", blob, offset),
                             (0x794D, 0, 0x03800000, 0))

    def test_animation_uploads_only_change_target_and_vertices(self):
        original = gpu.build_gpu_buffer()
        positions = (((0, 0), (1, 0), (0, 1), (-1, 0)),
                     ((0, 0), (-1, 0), (0, 1), (1, 0)))
        for variant in (0, 1):
            uploads = gpu.build_animation_inputs(variant)
            self.assertEqual(len(uploads), 256)
            reconstructed = bytearray(original)
            for frame, (dx, dy) in enumerate(positions[variant]):
                with self.subTest(variant=variant, frame=frame):
                    upload = uploads[frame * 64:(frame + 1) * 64]
                    self.assertEqual(upload[56:], bytes(8))
                    # Match the guest's two bounded writes, independently of
                    # build_gpu_buffer's full allocation construction.
                    reconstructed[36:44] = upload[:8]
                    reconstructed[0x3000:0x3030] = upload[8:56]
                    result = gpu.build_gpu_buffer(variant, animation_frame=frame)
                    self.assertEqual(bytes(reconstructed), result)
                    self.assertEqual(result[0x1000:0x3000], original[0x1000:0x3000])
                    regs = {method + 4 * n: value for method, args in packets(result)
                            for n, value in enumerate(args)}
                    self.assertEqual((regs[0x800], regs[0x804]), (1, (frame % 2) * 8192))
                    vertices = struct.unpack_from("<12f", result, 0x3000)
                    for index, (x, y) in enumerate(((2 + dx, 2 + dy),
                                                  (14 + dx, 2 + dy), (2 + dx, 7 + dy))):
                        self.assertAlmostEqual(8 * vertices[4 * index] + 8, x, places=6)
                        self.assertAlmostEqual(4.5 * vertices[4 * index + 1] + 4.5, y, places=6)
                        self.assertEqual(vertices[4 * index + 2:4 * index + 4], (0.5, 1))
        self.assertNotEqual(gpu.build_animation_inputs(0), gpu.build_animation_inputs(1))
        self.assertEqual(gpu.build_gpu_buffer(0, animation_frame=1),
                         gpu.build_gpu_buffer(1, animation_frame=3))

    def test_existing_static_inputs_remain_exact(self):
        expected = {(0, False): "c623432a76e1396dbb780be7699e8d33d8078aec1693ce30d44e55159d828c02",
                    (1, False): "c88f70a5f4ff175b4b982f9238fbdc451caadbc0cff273e84dd71eb79278efe2",
                    (0, True): "42b3fe9d9042c5a45d960dd496af037d1b0ff79eaa9f9fdcc93bef992af17181"}
        for (variant, clear), digest in expected.items():
            self.assertEqual(hashlib.sha256(gpu.build_gpu_buffer(variant, clear)).hexdigest(), digest)

    def test_rejects_unsupported_modes(self):
        for variant in (-1, 2, True, 0.0, "0", None):
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                gpu.build_gpu_buffer(variant)
        for clear in (0, 1, "false", None):
            with self.subTest(clear=clear), self.assertRaises(ValueError):
                gpu.build_gpu_buffer(clear_only=clear)
        for frame in (-1, 4, True, 0.0, "0"):
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                gpu.build_gpu_buffer(animation_frame=frame)
        with self.assertRaises(ValueError):
            gpu.build_gpu_buffer(clear_only=True, animation_frame=0)


# Guard every header in this small real-source compile; no source is copied into
# NX2. The full runtime builder independently verifies the complete engine tree.
SOURCE_BLOBS = {
    "common/bit_field.h": "fbc71590d5c80718ce1aa07a21d2f82189448cdf",
    "common/common_funcs.h": "18e83d338100556ee39c3e9af22a37479ccf818a",
    "common/common_types.h": "6e7e4ec0d9cfeaf369e51f8a198fb2d769c199cb",
    "common/swap.h": "c7646ea24d632f775a8148614fa62dc3ad225ea8",
    "shader_recompiler/frontend/ampere/instruction.h": "21872e4fa1b73408282f841f3fc0e58d89fdb342",
    "shader_recompiler/frontend/ampere/register_pressure.h": "089d68d2850a37c8c430cc56724040ea3d64c3a2",
    "shader_recompiler/frontend/ampere/lower_to_maxwell.h": "f3c44581a7ee428c6b0d9e880847d2b8d5cb5d6b",
    "shader_recompiler/frontend/ampere/program_capture.h": "a070dc252464b47026af7504471b621710c52822",
    "shader_recompiler/program_header.h": "1e8bae7cda6cbd89b7d2c1d07971ab1480d4d7e9",
}

SOURCE_PROBE = r'''
#include <array>
#include <cassert>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
#include "shader_recompiler/frontend/ampere/program_capture.h"
#include "shader_recompiler/program_header.h"
using namespace Shader::Ampere;
int main(int argc, char** argv) {
    assert(argc == 3);
    for (int variant = 0; variant != 2; ++variant) {
        std::ifstream input(argv[variant + 1], std::ios::binary);
        std::vector<char> bytes{std::istreambuf_iterator<char>{input}, {}};
        assert(bytes.size() == 0x4000);
        Shader::ProgramHeader vs{}, fs{};
        std::memcpy(&vs, bytes.data() + 0x1000, sizeof(vs));
        std::memcpy(&fs, bytes.data() + 0x2000, sizeof(fs));
        for (bool used : vs.vtg.InputGeneric(0)) assert(used);
        assert(vs.vtg.omap_systemb.position_x && vs.vtg.omap_systemb.position_y);
        assert(vs.vtg.omap_systemb.position_z && vs.vtg.omap_systemb.position_w);
        assert(fs.ps.omap.target == 15 && !fs.ps.omap.depth && !fs.ps.omap.sample_mask);
        for (int stage = 0; stage != 2; ++stage) {
            const size_t count = stage ? 5 : 3;
            std::vector<Instruction> code(count);
            std::memcpy(code.data(), bytes.data() + (stage ? 0x2080 : 0x1080), count * 16);
            ProgramCaptureState capture;
            for (u32 i = 0; i < count; ++i)
                assert(capture.Observe(code[i], i) == (i + 1 == count ?
                       ProgramCaptureState::Result::Complete : ProgramCaptureState::Result::Continue));
            const auto lowered = LowerToMaxwell(code, {}, true);
            assert(lowered && lowered.source_size == count * 16);
            assert(lowered.instructions.size() == count);
            const std::vector<u64> expected = stage ? std::vector<u64>{
                variant ? 0x010000000007f000ULL : 0x0103f8000007f000ULL,
                variant ? 0x0103f8000007f001ULL : 0x010000000007f001ULL,
                variant ? 0x010000000007f002ULL : 0x0103f8000007f002ULL,
                0x0103f8000007f003ULL, 0xe30000000007000fULL,
            } : std::vector<u64>{0xefd9ff800807ff00ULL, 0xeff1ff800707ff00ULL,
                                 0xe30000000007000fULL};
            assert(lowered.instructions == expected);
            auto bad = code;
            bad.back().words[0] &= ~0xf000U;
            ProgramCaptureState incomplete;
            for (u32 i = 0; i < count; ++i)
                assert(incomplete.Observe(bad[i], i) == ProgramCaptureState::Result::Continue);
            assert(!LowerToMaxwell(bad, {}, true));
            bad = code;
            if (stage) bad[0].words[2] = 0;       // Missing MOV lane mask.
            else bad[0].words[0] &= 0xffffffU;  // Indexed ALD is unsupported.
            assert(!LowerToMaxwell(bad, {}, true));
        }
    }
}
'''


@unittest.skipUnless(os.environ.get("NX2_EDEN_SOURCE"),
                     "set NX2_EDEN_SOURCE for the actual frozen shader-unit check")
class FrozenNativeShaderTests(unittest.TestCase):
    def test_actual_source_captures_lowers_and_rejects_malformed_programs(self):
        source = Path(os.environ["NX2_EDEN_SOURCE"]).resolve()
        revision = git(source, "rev-parse", "HEAD").decode().strip()
        self.assertIn(revision, EDEN_REVISIONS, "unreviewed Eden source revision")
        blobs = dict(SOURCE_BLOBS)
        if revision == CANDIDATE_SHA:
            blobs["shader_recompiler/frontend/ampere/lower_to_maxwell.h"] = \
                "6a8cd826674fc3082bff3b88cfbe7dae5a9f6571"
        for path, expected in blobs.items():
            content = (source / "src" / path).read_bytes()
            digest = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
            self.assertEqual(digest, expected, path)
        compiler = shutil.which("g++")
        self.assertIsNotNone(compiler, "g++ is required when NX2_EDEN_SOURCE is provided")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cpp, executable = root / "probe.cpp", root / "probe"
            cpp.write_text(SOURCE_PROBE, encoding="utf-8")
            paths = [root / f"input-{i}.bin" for i in range(2)]
            for i, path in enumerate(paths):
                path.write_bytes(gpu.build_gpu_buffer(i))
            build = subprocess.run([compiler, "-std=c++20", "-O1", "-I", str(source / "src"),
                                    str(cpp), "-o", str(executable)], capture_output=True,
                                   text=True, timeout=90, check=False)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(executable), *map(str, paths)], capture_output=True,
                                 text=True, timeout=10, check=False)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
