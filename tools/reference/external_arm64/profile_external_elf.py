#!/usr/bin/env python3
"""Research-only: authenticate one external AArch64 ELF64 load and first SVC.

No general ELF loader, host syscalls, Nintendo/Horizon ABI, or game execution.
"""
import argparse
from pathlib import Path
import struct

MAX_ELF = 2 * 1024 * 1024
MAX_WORDS = 4096
HEADER = struct.Struct('<HHIQQQIHHHHHH')
PHDR = struct.Struct('<IIQQQQQQ')
SOURCE_PREFIX = bytes.fromhex('200080d2e1000058c20180d2080880d2010000d4')
SOURCE_MESSAGE = b'Hello, World!\n'

class ExternalElfRefused(ValueError):
    pass

def demand(condition, reason):
    if not condition:
        raise ExternalElfRefused(reason)

def make_owned_image(data: bytes) -> tuple[bytes, int, int]:
    demand(64 <= len(data) <= MAX_ELF, 'elf_size')
    demand(data[:6] == b'\x7fELF\x02\x01' and data[6] == 1,
           'elf64_little_endian_required')
    (typ, machine, version, entry, phoff, _shoff, _flags, ehsize,
     phsize, phnum, *_rest) = HEADER.unpack_from(data, 16)
    demand(typ == 2 and machine == 183 and version == 1 and ehsize == 64,
           'static_aarch64_executable_required')
    demand(phsize == PHDR.size and 1 <= phnum <= 32 and
           phoff >= 64 and phoff + phnum * phsize <= len(data),
           'program_header_bounds')
    loads = []
    entry_loads = []
    for i in range(phnum):
        kind, flags, offset, vaddr, _paddr, filesz, memsz, _align = (
            PHDR.unpack_from(data, phoff + i * phsize))
        if kind != 1:
            continue
        demand(flags <= 7 and filesz <= memsz and offset <= len(data) and
               filesz <= len(data) - offset and
               vaddr <= (1 << 64) - 1 - memsz, 'load_extent')
        record = (flags, offset, vaddr, filesz)
        loads.append(record)
        if (flags & 1) and vaddr <= entry < vaddr + filesz:
            entry_loads.append(record)
    demand(len(entry_loads) == 1, 'unique_executable_entry')
    flags, offset, vaddr, size = entry_loads[0]
    demand(flags == 5 and entry == vaddr and size % 4 == 0 and
           10 <= size // 4 <= MAX_WORDS, 'bounded_rx_entry_segment')
    code = data[offset:offset + size]
    demand(code[:len(SOURCE_PREFIX)] == SOURCE_PREFIX,
           'pinned_external_instruction_identity')
    # First LDR X1, [PC + 7*4] at instruction PC+4 points to a
    # 64-bit pointer in the same RX PT_LOAD (PC + 0x20). This is a
    # literal READ from code, not permission to dereference the pointer.
    word = struct.unpack_from('<I', code, 4)[0]
    demand((word & 0xFF00001F) == 0x58000001, 'literal_load_encoding')
    imm19 = (word >> 5) & 0x7FFFF
    signed19 = imm19 - 0x80000 if imm19 & 0x40000 else imm19
    literal_offset = 4 + signed19 * 4
    demand(0 <= literal_offset <= len(code) - 8 and literal_offset == 0x20,
           'original_literal_within_rx_segment')
    pointer = struct.unpack_from('<Q', code, literal_offset)[0]
    # Independently verify that the original literal points to the
    # exact bytes in the original separate, file-backed RW (PF_R | PF_W),
    # nonexecutable data PT_LOAD. Write permission alone does not permit reads.
    data_matches = []
    for data_flags, data_offset, data_va, data_size in loads:
        if data_flags == 6 and (
            data_va <= pointer and
            pointer - data_va <= data_size and
            len(SOURCE_MESSAGE) <= data_size - (pointer - data_va)):
            start = data_offset + (pointer - data_va)
            if data[start:start + len(SOURCE_MESSAGE)] == SOURCE_MESSAGE:
                data_matches.append(start)
    demand(len(data_matches) == 1, 'literal_pointer_data_segment_identity')
    envelope = struct.pack('<4sHHII', b'NX2O', 1, 0, 0, size // 4)
    return envelope + code, size // 4, pointer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--elf', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--data-output', type=Path,
                        help='Research-only verified original message sidecar')
    args = parser.parse_args()
    try:
        raw = args.elf.read_bytes()
        image, count, pointer = make_owned_image(raw)
    except (OSError, ExternalElfRefused, struct.error) as exc:
        parser.exit(2, 'NX2_EXTERNAL_ELF_REFUSED:' + str(exc) + '\n')
    args.output.write_bytes(image)
    if args.data_output is not None:
        # This constant was independently checked against the exact source
        # ELF's nonexecutable PT_LOAD by make_owned_image. The separately
        # created bytes are never committed, forwarded to a host syscall,
        # or interpreted as Nintendo/Horizon data.
        args.data_output.write_bytes(SOURCE_MESSAGE)
    print('NX2_EXTERNAL_ELF_PROFILE_PASS')
    print('external_source_code_redistributed=no')
    print('guest_format=ELF64_AArch64_research_extract')
    print('original_first_instruction=0xd2800020')
    print('original_second_instruction=0x580000e1')
    print(f'bounded_executable_words={count}')
    print('literal_pointer_data_mapping=verified')
    print(f'literal_guest_address=0x{pointer:x}')
    print('linux_or_horizon_services_dispatched=0')
    print('nintendo_software_executed=0')

if __name__ == '__main__':
    main()
