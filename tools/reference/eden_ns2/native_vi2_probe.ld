/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (c) 2026 nx2-lab contributors.
 * Layout adapts the earlier MIT-licensed NX2 SM probe; see LICENSES/MIT.txt.
 * Original bounded three-page VI2 lifecycle guest.
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
    .rodata 0x1000 : { *(.rodata) } :rodata
    .data 0x2000 : { *(.data) } :data
    /DISCARD/ : { *(.note*) *(.comment*) }
    ASSERT(SIZEOF(.text) <= 0x1000, "VI2 guest text exceeds one page")
    ASSERT(SIZEOF(.rodata) <= 0x1000, "VI2 guest rodata exceeds one page")
    ASSERT(SIZEOF(.data) <= 0x1000, "VI2 guest data exceeds one page")
}
