#!/usr/bin/env python3
"""Deterministic malformed synthetic ELF64 negatives; no external source used."""
import struct

from profile_external_elf import ExternalElfRefused, make_owned_image


CODE = bytes.fromhex("200080d2e1000058") + bytes.fromhex("1f2003d5") * 8


def make_fixture():
    data = bytearray(128 + len(CODE))
    data[:16] = b"\x7fELF\x02\x01\x01" + bytes(9)
    struct.pack_into("<HHIQQQIHHHHHH", data, 16,
                     2, 183, 1, 0x1000, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    struct.pack_into("<IIQQQQQQ", data, 64,
                     1, 5, 128, 0x1000, 0x1000, len(CODE), len(CODE), 4096)
    data[128:] = CODE
    return data


def changed(offset, value, fmt):
    data = make_fixture()
    struct.pack_into(fmt, data, offset, value)
    return data


def check():
    image, word_count = make_owned_image(bytes(make_fixture()))
    assert word_count == 10 and image[:4] == b"NX2O" and image[16:] == CODE
    cases = {
        "truncated": bytes(make_fixture())[:100],
        "bad_magic": changed(0, b"NOPE", "<4s"),
        "wrong_machine": changed(18, 62, "<H"),
        "dynamic_elf": changed(16, 3, "<H"),
        "wrong_entry": changed(24, 0x1004, "<Q"),
        "program_table_overflow": changed(32, 0xfffffffffffffff0, "<Q"),
        "empty_code": changed(64 + 32, 0, "<Q"),
        "writable_executable": changed(64 + 4, 7, "<I"),
        "invalid_file_extent": changed(64 + 32, 10000, "<Q"),
        "not_executable": changed(64 + 4, 4, "<I"),
        "changed_instruction": changed(128, 0xd2800021, "<I"),
        "unaligned_code_size": changed(64 + 32, 39, "<Q"),
    }
    duplicate = bytearray(176 + len(CODE))
    duplicate[:64] = make_fixture()[:64]
    struct.pack_into("<H", duplicate, 56, 2)
    duplicate[64:120] = make_fixture()[64:120]
    duplicate[120:176] = duplicate[64:120]
    for offset in (64, 120):
        struct.pack_into("<Q", duplicate, offset + 8, 176)
    duplicate[176:] = CODE
    cases["duplicate_executable_entry"] = duplicate
    for name, raw in cases.items():
        try:
            make_owned_image(bytes(raw))
        except (ExternalElfRefused, struct.error):
            continue
        raise AssertionError("invalid synthetic ELF admitted: " + name)
    print("NX2_EXTERNAL_ELF_NEGATIVES_PASS")
    print("invalid_elf_cases=" + str(len(cases)))
    print("third_party_code_required_for_negatives=no")


if __name__ == "__main__":
    check()
