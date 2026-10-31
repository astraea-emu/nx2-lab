/* SPDX-License-Identifier: MIT — original bounded NX2 guest layout. */
OUTPUT_ARCH(aarch64)
ENTRY(_start)
PHDRS {
    text PT_LOAD FLAGS(5);
    rodata PT_LOAD FLAGS(4);
    data PT_LOAD FLAGS(6);
}
SECTIONS {
    .text 0 : { *(.text) } :text
    .rodata 0x1000 : { *(.rodata) } :rodata
    .data 0x2000 : { *(.data) } :data
    /DISCARD/ : { *(.note*) *(.comment*) }
    ASSERT(SIZEOF(.text) <= 0x1000, "IPC guest text exceeds one page")
    ASSERT(SIZEOF(.rodata) <= 0x1000, "IPC guest rodata exceeds one page")
    ASSERT(SIZEOF(.data) <= 0x1000, "IPC guest data exceeds one page")
}
