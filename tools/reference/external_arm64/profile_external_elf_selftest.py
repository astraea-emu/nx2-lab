#!/usr/bin/env python3
"""Independent source-owned synthetic ELF64 input and mutation negatives."""
import struct
from profile_external_elf import (
    ExternalElfRefused, SOURCE_MESSAGE, SOURCE_PREFIX, make_owned_image,
)

CODE = (SOURCE_PREFIX + b'\x00' * (0x20 - len(SOURCE_PREFIX)) +
        struct.pack('<Q', 0x3000))


def make_fixture():
    raw = bytearray(0x140 + len(SOURCE_MESSAGE))
    raw[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH', raw, 16,
                     2, 183, 1, 0x1000, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    struct.pack_into('<IIQQQQQQ', raw, 64,
                     1, 5, 0xB0, 0x1000, 0x1000, len(CODE), len(CODE), 4096)
    struct.pack_into('<IIQQQQQQ', raw, 120,
                     1, 6, 0x140, 0x3000, 0x3000,
                     len(SOURCE_MESSAGE), len(SOURCE_MESSAGE), 4096)
    raw[0xB0:0xB0+len(CODE)] = CODE
    raw[0x140:] = SOURCE_MESSAGE
    return raw


def changed(offset, value, fmt):
    data = make_fixture()
    struct.pack_into(fmt, data, offset, value)
    return data


def check():
    image, words, literal = make_owned_image(bytes(make_fixture()))
    assert words == len(CODE) // 4 and image[:4] == b'NX2O'
    assert image[16:] == CODE and literal == 0x3000
    cases = {
        'truncated': bytes(make_fixture())[:100],
        'bad_magic': changed(0, b'NOPE', '<4s'),
        'wrong_machine': changed(18, 62, '<H'),
        'dynamic_elf': changed(16, 3, '<H'),
        'wrong_entry': changed(24, 0x1004, '<Q'),
        'program_table_overflow': changed(32, 0xfffffffffffffff0, '<Q'),
        'empty_code': changed(64 + 32, 0, '<Q'),
        'writable_executable': changed(64 + 4, 7, '<I'),
        'invalid_file_extent': changed(64 + 32, 10000, '<Q'),
        'not_executable': changed(64 + 4, 4, '<I'),
        'changed_instruction': changed(0xB0, 0xd2800021, '<I'),
        'unaligned_code_size': changed(64 + 32, len(CODE)-1, '<Q'),
        'mutated_literal_pointer': changed(0xB0 + 0x20, 0x4000, '<Q'),
        'mutated_data_bytes': changed(0x140, b'NOPE', '<4s'),
        'data_not_read_write': changed(120 + 4, 4, '<I'),
        'data_write_only': changed(120 + 4, 2, '<I'),
        'data_no_access': changed(120 + 4, 0, '<I'),
        'data_executable': changed(120 + 4, 7, '<I'),
    }
    duplicate = bytearray(make_fixture())
    # A third executable PT_LOAD also covering entry must be refused.
    struct.pack_into('<H', duplicate, 56, 3)
    struct.pack_into('<IIQQQQQQ', duplicate, 176,
                     1, 5, 0xB0, 0x1000, 0x1000,
                     len(CODE), len(CODE), 4096)
    cases['duplicate_executable_entry'] = duplicate
    for name, raw in cases.items():
        try:
            make_owned_image(bytes(raw))
        except (ExternalElfRefused, struct.error):
            continue
        raise AssertionError('bad synthetic ELF accepted: ' + name)
    print('NX2_EXTERNAL_ELF_NEGATIVES_PASS')
    print('invalid_elf_cases=' + str(len(cases)))
    print('literal_target_mutations=refused')
    print('third_party_code_required_for_negatives=no')


if __name__ == '__main__':
    check()
