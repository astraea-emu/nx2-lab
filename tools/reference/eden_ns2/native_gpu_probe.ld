/* SPDX-License-Identifier: GPL-3.0-only
 * Original GPU guest: shared frame lifecycle, driver state and shader memory.
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
    .rodata 0x4000 : { *(.rodata) } :rodata
    .data 0x10000 : { *(.data) } :data
    /DISCARD/ : { *(.note*) *(.comment*) }
    ASSERT(SIZEOF(.text) <= 0x4000, "GPU guest text exceeds four pages")
    ASSERT(SIZEOF(.rodata) <= 0xc000, "GPU guest constants exceed twelve pages")
    ASSERT(SIZEOF(.data) <= (NX2_GPU_ANIMATION ? 0xa000 : 0x8000), "GPU guest data exceeds its bounded allocation")
    ASSERT(image_buffer == 0x11000, "GPU image must retain separate aligned pages")
    ASSERT((gpu_buffer & 0xfff) == 0, "GPU command and shader memory must be aligned")
}
