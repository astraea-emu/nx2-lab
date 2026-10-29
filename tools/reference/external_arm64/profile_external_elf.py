#!/usr/bin/env python3
"""Research-only: extract an exact, bounded AArch64 executable PT_LOAD.

Outputs NX2 Lab's generic test envelope; does NOT implement Linux, Horizon,
Nintendo executables, dynamic modules, relocations, or host syscalls.
"""
import argparse
from pathlib import Path
import struct

MAX_ELF = 2 * 1024 * 1024
MAX_WORDS = 4096
HEADER = struct.Struct("<HHIQQQIHHHHHH")
PHDR = struct.Struct("<IIQQQQQQ")


class ExternalElfRefused(ValueError):
    pass


def demand(condition, reason):
    if not condition:
        raise ExternalElfRefused(reason)


def make_owned_image(data: bytes) -> tuple[bytes, int]:
    demand(64 <= len(data) <= MAX_ELF, "elf_size")
    demand(data[:6] == b"\x7fELF\x02\x01" and data[6] == 1,
           "elf64_little_endian_required")
    (typ, machine, version, entry, phoff, _shoff, _flags, ehsize,
     phsize, phnum, *_rest) = HEADER.unpack_from(data, 16)
    demand(typ == 2 and machine == 183 and version == 1 and ehsize == 64,
           "static_aarch64_executable_required")
    demand(phsize == PHDR.size and 1 <= phnum <= 32 and phoff >= 64 and
           phoff + phnum * phsize <= len(data), "program_header_bounds")
    runnable = []
    for i in range(phnum):
        kind, flags, offset, vaddr, _paddr, filesz, memsz, _align = (
            PHDR.unpack_from(data, phoff + i * phsize))
        if kind != 1:
            continue
        demand(filesz <= memsz and offset <= len(data) and
               filesz <= len(data) - offset and
               vaddr <= (1 << 64) - 1 - memsz, "load_extent")
        if (flags & 1) and vaddr <= entry < vaddr + filesz:
            runnable.append((flags, offset, vaddr, filesz))
    demand(len(runnable) == 1, "unique_executable_entry")
    flags, offset, vaddr, size = runnable[0]
    demand(flags == 5 and entry == vaddr and size % 4 == 0 and
           2 <= size // 4 <= MAX_WORDS, "bounded_rx_entry_segment")
    code = data[offset:offset + size]
    # Frozen external author source starts MOVZ X0,#1; LDR X1,literal.
    # LDR remains unsupported by the tiny NX2 reference interpreter.
    demand(code[:8] == bytes.fromhex("200080d2e1000058"),
           "pinned_external_instruction_identity")
    envelope = struct.pack("<4sHHII", b"NX2O", 1, 0, 0, size // 4)
    return envelope + code, size // 4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        raw = args.elf.read_bytes()
        image, count = make_owned_image(raw)
    except (OSError, ExternalElfRefused, struct.error) as exc:
        parser.exit(2, "NX2_EXTERNAL_ELF_REFUSED:" + str(exc) + "\n")
    args.output.write_bytes(image)
    print("NX2_EXTERNAL_ELF_PROFILE_PASS")
    print("external_source_code_redistributed=no")
    print("guest_format=ELF64_AArch64_research_extract")
    print("original_first_instruction=0xd2800020")
    print("original_second_instruction=0x580000e1")
    print(f"bounded_executable_words={count}")
    print("linux_or_horizon_services_dispatched=0")
    print("nintendo_software_executed=0")


if __name__ == "__main__":
    main()
