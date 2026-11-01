/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (c) 2026 nx2-lab contributors.
 * Bounded original frame fixture; earlier three-page guests are unchanged.
 */
OUTPUT_ARCH(aarch64)
ENTRY(_start)
PHDRS {
    text PT_LOAD FLAGS(5);
    rodata PT_LOAD FLAGS(4);
    data PT_LOAD FLAGS(6);
}
SECTIONS {
    .text 0 : { *(.text) } :text
    .rodata 0x2000 : { *(.rodata) } :rodata
    .data 0x5000 : { *(.data) } :data
    /DISCARD/ : { *(.note*) *(.comment*) }
    ASSERT(SIZEOF(.text) <= 0x2000, "frame text exceeds two pages")
    ASSERT(SIZEOF(.rodata) <= 0x3000, "frame rodata exceeds three pages")
    ASSERT(SIZEOF(.data) == 0x3000, "frame data must be record page plus two image pages")
    ASSERT(image_buffer == 0x6000, "frame image must start on its separate aligned pages")
}
