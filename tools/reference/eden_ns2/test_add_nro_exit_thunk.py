"""NX2-authored return-thunk tests; runtime execution remains separate."""
import contextlib
import io
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import add_nro_exit_thunk
from add_nro_exit_thunk import SVC_EXIT, add_exit_thunk


def synthetic() -> bytes:
    raw = bytearray(0x5000)
    raw[0x10:0x14] = b"NRO0"
    struct.pack_into("<II", raw, 0x20, 0, 0xEB0)
    struct.pack_into("<II", raw, 0x28, 0x1000, 0x300)
    struct.pack_into("<II", raw, 0x30, 0x2000, 0x1000)
    return bytes(raw)


class ExitThunkTests(unittest.TestCase):
    def test_adapts_exactly_one_4_byte_slot(self):
        before = synthetic()
        after, offset = add_exit_thunk(before)
        self.assertEqual(offset, 0xEB0)
        self.assertEqual(len(after), len(before))
        self.assertEqual(after[:offset], before[:offset])
        self.assertEqual(after[offset + 4:], before[offset + 4:])
        self.assertEqual(after[offset:offset + 4], struct.pack("<I", SVC_EXIT))

    def test_original_is_not_mutated(self):
        before = synthetic()
        add_exit_thunk(before)
        self.assertEqual(before[0xEB0:0xEB4], b"\0" * 4)

    def test_no_padding_is_refused(self):
        before = bytearray(synthetic())
        struct.pack_into("<I", before, 0x24, 0x1000)
        with self.assertRaisesRegex(ValueError, "padding"):
            add_exit_thunk(bytes(before))

    def test_occupied_padding_refused(self):
        before = bytearray(synthetic())
        before[0xEB0] = 0xFF
        with self.assertRaisesRegex(ValueError, "not empty"):
            add_exit_thunk(bytes(before))

    def test_wrong_magic_refused(self):
        before = bytearray(synthetic())
        before[0x10:0x14] = b"NX2!"
        with self.assertRaisesRegex(ValueError, "magic"):
            add_exit_thunk(bytes(before))

    def test_misalignment_refused(self):
        before = bytearray(synthetic())
        struct.pack_into("<I", before, 0x24, 0xEB1)
        with self.assertRaisesRegex(ValueError, "aligned"):
            add_exit_thunk(bytes(before))

    def test_existing_exit_svc_refused(self):
        before = bytearray(synthetic())
        struct.pack_into("<I", before, 0x200, SVC_EXIT)
        with self.assertRaisesRegex(ValueError, "already contains"):
            add_exit_thunk(bytes(before))

    def test_oversized_fixture_is_refused_before_copying_or_writing(self):
        with patch.object(add_nro_exit_thunk, "MAX_IMAGE_SIZE", 16), \
                self.assertRaisesRegex(ValueError, "input limit"):
            add_exit_thunk(synthetic())

    def test_cli_caps_read_after_original_file_grows(self):
        stream = io.BytesIO(synthetic() + bytes(4096))
        with patch.object(add_nro_exit_thunk, "MAX_IMAGE_SIZE", 0x5000), \
                patch.object(Path, "exists", return_value=False), \
                patch.object(Path, "stat", return_value=SimpleNamespace(st_size=0x5000)), \
                patch.object(Path, "open", return_value=stream), \
                patch.object(stream, "read", wraps=stream.read) as read, \
                patch.object(Path, "write_bytes") as write, \
                patch("sys.argv", ["add_nro_exit_thunk.py", "--original", "growing.nro",
                                   "--output", "adapted.nro"]), \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as status:
                add_nro_exit_thunk.main()
            self.assertEqual(status.exception.code, 1)
            read.assert_called_once_with(0x5001)
            write.assert_not_called()
            self.assertIn("input limit", errors.getvalue())

    def test_cli_refuses_to_overwrite_the_original_it_claims_to_preserve(self):
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary) / "original.nro"
            before = synthetic()
            original.write_bytes(before)
            with patch("sys.argv", ["add_nro_exit_thunk.py", "--original", str(original),
                                   "--output", str(original)]), \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as status:
                    add_nro_exit_thunk.main()
                self.assertEqual(status.exception.code, 1)
                self.assertIn("must not alias", errors.getvalue())
            self.assertEqual(original.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
