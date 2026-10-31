"""NX2-authored return-thunk tests; runtime execution remains separate."""
import struct
import unittest
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


if __name__ == "__main__":
    unittest.main()
