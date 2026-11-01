/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (c) 2026 nx2-lab contributors.
 * Original native NVDRV/TSG/GSV driver for the pinned Eden source model.
 * No SDK or external guest instruction bytes are used.
 */
.set NX2_GPU_PROBE, 1
.include "native_frame_probe.S"

.ifndef NX2_GPU_WORD_COUNT
    .error "NX2_GPU_WORD_COUNT must describe the original command buffer"
.endif
.ifndef NX2_GPU_CLEAR_ONLY
    .error "NX2_GPU_CLEAR_ONLY must be 0 or 1"
.endif
.if (NX2_GPU_CLEAR_ONLY != 0) && (NX2_GPU_CLEAR_ONLY != 1)
    .error "invalid GPU control mode"
.endif
.if (NX2_GPU_WORD_COUNT <= 0) || (NX2_GPU_WORD_COUNT > 1024)
    .error "command list must fit its first backing page"
.endif
.equ GPU_IMAGE_VA, 0x100000000
.equ GPU_BUFFER_VA, 0x100010000
.equ GPU_BUFFER_SIZE, 0x4000
.equ S_AS_FD, 0
.equ S_CHANNEL_FD, 4
.equ S_TSG_FD, 8
.equ S_SYNC_HANDLE, 12
.equ S_MEMORY_ID, 16
.equ S_FLAGS, 20
.equ S_FENCE_ID, 24
.equ S_FENCE_TARGET, 28
/* Flags: acquired memory, reserved image VA, reserved buffer VA, TSG binding. */
.equ G_MEMORY, 0
.equ G_IMAGE_VA, 1
.equ G_BUFFER_VA, 2
.equ G_TSG_BOUND, 3

.section .rodata, "a"
.global gpu_field_names, GPU_FIELD_COUNT
gpu_field_names:
.set GPU_FIELD_OFFSET, 0
.macro gpu_field name
    .equ G_\name, GPU_FIELD_OFFSET
    .set GPU_FIELD_OFFSET, GPU_FIELD_OFFSET + 4
    .asciz "gpu_\name"
.endm
.macro gpu_tipc_fields prefix
    gpu_field \prefix\()_transport
    gpu_field \prefix\()_header0
    gpu_field \prefix\()_header1
    gpu_field \prefix\()_result
.endm
.macro gpu_cmif_fields prefix, open=0
    gpu_field \prefix\()_transport
    gpu_field \prefix\()_header0
    gpu_field \prefix\()_header1
    gpu_field \prefix\()_pad0
    gpu_field \prefix\()_pad1
    gpu_field \prefix\()_magic
    gpu_field \prefix\()_version
    gpu_field \prefix\()_result_lo
    gpu_field \prefix\()_result_hi
.if \open
    gpu_field \prefix\()_fd
.endif
    gpu_field \prefix\()_nv_result
.endm
.macro gpu_ioctl_fields prefix, words
    gpu_cmif_fields \prefix
    gpu_field \prefix\()_guard_before
    .irp n,0,1,2,3,4,5,6,7,8,9
      .if \n < \words
        gpu_field \prefix\()_word0\n
      .endif
    .endr
    gpu_field \prefix\()_guard_after
.endm
.macro gpu_counter_fields prefix
    gpu_tipc_fields \prefix
    gpu_field \prefix\()_lo
    gpu_field \prefix\()_hi
    gpu_field \prefix\()_width
.endm
    gpu_field clear_only
    gpu_field buffer_address_lo
    gpu_field buffer_address_hi
    gpu_field buffer_size
    gpu_field buffer_checksum
    gpu_field command_words
    gpu_field entry_lo
    gpu_field entry_hi
    gpu_tipc_fields memory_create
    gpu_field memory_id
    gpu_tipc_fields memory_bind
    gpu_tipc_fields sync_init
    gpu_field sync_open_transport
    gpu_field sync_open_header0
    gpu_field sync_open_header1
    gpu_field sync_open_descriptor
    gpu_field sync_handle
    gpu_field sync_open_result
    gpu_cmif_fields open_as, 1
    gpu_cmif_fields open_channel, 1
    gpu_cmif_fields open_tsg, 1
    gpu_ioctl_fields as_init, 10
    gpu_ioctl_fields as_bind, 1
    gpu_ioctl_fields tsg_bind, 1
    gpu_ioctl_fields fifo, 8
    gpu_ioctl_fields object, 4
    gpu_ioctl_fields reserve_image, 6
    gpu_ioctl_fields map_image, 10
    gpu_ioctl_fields reserve_buffer, 6
    gpu_ioctl_fields map_buffer, 10
    gpu_counter_fields counter_before
    gpu_ioctl_fields submit, 6
    gpu_counter_fields counter_after
    gpu_field counter_poll_count
    gpu_ioctl_fields free_buffer, 4
    gpu_ioctl_fields free_image, 4
    gpu_ioctl_fields tsg_unbind, 1
    gpu_cmif_fields close_channel
    gpu_cmif_fields close_tsg
    gpu_cmif_fields close_as
    gpu_tipc_fields memory_destroy
    gpu_field close_sync
    .byte 0
.equ GPU_FIELD_COUNT, GPU_FIELD_OFFSET / 4

.section .text, "ax"
.macro gpu_enter
    stp x29, x30, [sp, #-64]!
    stp x23, x24, [sp, #16]
    stp x25, x26, [sp, #32]
    stp x27, x28, [sp, #48]
    address x23, gpu_record
    address x24, gpu_state
.endm
.macro gpu_leave
    ldp x23, x24, [sp, #16]
    ldp x25, x26, [sp, #32]
    ldp x27, x28, [sp, #48]
    ldp x29, x30, [sp], #64
.endm
.macro gpu_emit label
    address x0, \label
    mov x1, #(\label\()_end - \label)
    svc #0x27
.endm
.macro gpu_tipc_capture prefix
    str w0, [x23, #G_\prefix\()_transport]
    ldp w1, w2, [x21]
    str w1, [x23, #G_\prefix\()_header0]
    str w2, [x23, #G_\prefix\()_header1]
    ldr w3, [x21, #8]
    str w3, [x23, #G_\prefix\()_result]
.endm
.macro gpu_tipc_validate command, raw=1, fail=.Lgpu_setup_failed
    cbnz w0, \fail
    cmp w1, #(16 + \command)
    b.ne \fail
    cmp w2, #\raw
    b.ne \fail
    cbnz w3, \fail
.endm
.macro gpu_mark flag
    ldr w9, [x24, #S_FLAGS]
    orr w9, w9, #(1 << \flag)
    str w9, [x24, #S_FLAGS]
.endm
.macro gpu_input label, size
    address x0, \label
    mov w1, #\size
    bl gpu_copy_input
.endm
.macro gpu_ioctl fd, code, size, prefix, kind=1
    address x0, gpu_io_input
    mov w1, #\size
    ldr w2, [x24, #\fd]
    mov w3, #(\code & 0xffff)
    movk w3, #((\code >> 16) & 0xffff), lsl #16
    add x4, x23, #G_\prefix\()_transport
    mov w5, #\kind
    bl gpu_ioctl_call
.endm
.macro gpu_require_io_match size
    mov w0, #\size
    bl gpu_match_io
    cbnz w0, .Lgpu_setup_failed
.endm
.macro gpu_cleanup_result number
    cbz w0, .Lgpu_cleanup_ok\@
    ldr w1, [x22, #F_fail_step]
    cbnz w1, .Lgpu_cleanup_ok\@
    mov w1, #\number
    str w1, [x22, #F_fail_step]
.Lgpu_cleanup_ok\@:
.endm

/* Called instead of the CPU drawing routine. The sentinel is deliberately
 * distinct from every expected clear/fragment pixel. No later CPU image writes.
 */
.global gpu_initialize
gpu_initialize:
    gpu_enter
    mov w0, #NX2_GPU_CLEAR_ONLY
    str w0, [x23, #G_clear_only]
    address x9, image_buffer
    mov w10, #0xffff
    movk w10, #0xff00, lsl #16
    mov w11, #2048
1:  str w10, [x9], #4
    subs w11, w11, #1
    b.ne 1b
    address x0, image_buffer
    mov w1, #8192
    bl gpu_fnv1a
    str w0, [x22, #F_image_checksum]
    address x0, gpu_initial_data
    address x1, gpu_buffer
    str x1, [x23, #G_buffer_address_lo]
    mov w2, #1024
2:  ldp x3, x4, [x0], #16
    stp x3, x4, [x1], #16
    subs w2, w2, #1
    b.ne 2b
    address x0, gpu_buffer
    mov w1, #GPU_BUFFER_SIZE
    bl gpu_fnv1a
    str w0, [x23, #G_buffer_checksum]
    mov w0, #GPU_BUFFER_SIZE
    str w0, [x23, #G_buffer_size]
    mov w0, #NX2_GPU_WORD_COUNT
    str w0, [x23, #G_command_words]
    address x0, gpu_entry
    ldr x0, [x0]
    str x0, [x23, #G_entry_lo]
    gpu_leave
    ret

/* x0 bytes, w1 size; return observed FNV-1a32 in w0. */
gpu_fnv1a:
    mov x9, x0
    mov w0, #0x9dc5
    movk w0, #0x811c, lsl #16
    mov w10, #0x0193
    movk w10, #0x0100, lsl #16
1:  ldrb w11, [x9], #1
    eor w0, w0, w11
    mul w0, w0, w10
    subs w1, w1, #1
    b.ne 1b
    ret

.global gpu_submit_and_wait
gpu_submit_and_wait:
    gpu_enter
    gpu_emit gpu_begin_message
    step 100
    prepare gpu_memory_create_request
    ldr w0, [x19, #20]
    svc #0x21
    gpu_tipc_capture memory_create
    ldr w4, [x21, #12]
    str w4, [x23, #G_memory_id]
    gpu_tipc_validate 111, 2
    cbz w4, .Lgpu_setup_failed
    cmn w4, #1
    b.eq .Lgpu_setup_failed
    ldr w5, [x22, #F_memory_id]
    cmp w4, w5
    b.eq .Lgpu_setup_failed
    str w4, [x24, #S_MEMORY_ID]
    gpu_mark G_MEMORY
    step 101
    prepare gpu_memory_bind_request
    ldr w0, [x24, #S_MEMORY_ID]
    str w0, [x21, #8]
    address x0, gpu_buffer
    str x0, [x21, #12]
    ldr w0, [x19, #20]
    svc #0x21
    gpu_tipc_capture memory_bind
    gpu_tipc_validate 114
    step 102
    prepare gpu_sync_init_request
    ldr w0, [x19, #20]
    svc #0x21
    gpu_tipc_capture sync_init
    gpu_tipc_validate 201
    step 103
    prepare gpu_sync_open_request
    ldr w0, [x19, #20]
    svc #0x21
    str w0, [x23, #G_sync_open_transport]
    ldp w1, w2, [x21]
    stp w1, w2, [x23, #G_sync_open_header0]
    ldp w3, w4, [x21, #8]
    stp w3, w4, [x23, #G_sync_open_descriptor]
    ldr w5, [x21, #16]
    str w5, [x23, #G_sync_open_result]
    cbnz w0, .Lgpu_setup_failed
    cmp w1, #0xda
    b.ne .Lgpu_setup_failed
    mov w6, #0x80000001
    cmp w2, w6
    b.ne .Lgpu_setup_failed
    cmp w3, #0x20
    b.ne .Lgpu_setup_failed
    tst w4, #0xc0000000
    b.ne .Lgpu_setup_failed
    and w6, w4, #0x7fff
    cmp w6, #1024
    b.hs .Lgpu_setup_failed
    ubfx w6, w4, #15, #15
    cbz w6, .Lgpu_setup_failed
    mov w6, #0
1:  ldr w7, [x19, x6, lsl #2]
    cmp w4, w7
    b.eq .Lgpu_setup_failed
    add w6, w6, #1
    cmp w6, #8
    b.ne 1b
    str w4, [x24, #S_SYNC_HANDLE]
    cbnz w5, .Lgpu_setup_failed

    step 104
    address x0, gpu_as_name
    mov w1, #(gpu_as_name_end - gpu_as_name)
    add x2, x23, #G_open_as_transport
    bl gpu_open
    cbnz w0, .Lgpu_setup_failed
    str w1, [x24, #S_AS_FD]
    step 105
    address x0, gpu_channel_name
    mov w1, #(gpu_channel_name_end - gpu_channel_name)
    add x2, x23, #G_open_channel_transport
    bl gpu_open
    cbnz w0, .Lgpu_setup_failed
    ldr w2, [x24, #S_AS_FD]
    cmp w1, w2
    b.eq .Lgpu_setup_failed
    str w1, [x24, #S_CHANNEL_FD]
    step 106
    address x0, gpu_tsg_name
    mov w1, #(gpu_tsg_name_end - gpu_tsg_name)
    add x2, x23, #G_open_tsg_transport
    bl gpu_open
    cbnz w0, .Lgpu_setup_failed
    ldp w2, w3, [x24, #S_AS_FD]
    cmp w1, w2
    b.eq .Lgpu_setup_failed
    cmp w1, w3
    b.eq .Lgpu_setup_failed
    str w1, [x24, #S_TSG_FD]

    step 107
    gpu_input gpu_as_init_data, 40
    gpu_ioctl S_AS_FD, 0x40284109, 40, as_init
    cbnz w0, .Lgpu_setup_failed
    step 108
    gpu_input gpu_zero_data, 4
    address x9, gpu_io_input
    ldr w10, [x24, #S_CHANNEL_FD]
    str w10, [x9]
    gpu_ioctl S_AS_FD, 0x40044101, 4, as_bind
    cbnz w0, .Lgpu_setup_failed
    step 109
    /* The input still contains this process's channel FD. */
    gpu_ioctl S_TSG_FD, 0xc0045401, 4, tsg_bind
    cbnz w0, .Lgpu_setup_failed
    gpu_mark G_TSG_BOUND
    gpu_require_io_match 4
    step 110
    gpu_input gpu_fifo_data, 32
    gpu_ioctl S_CHANNEL_FD, 0xc020481a, 32, fifo
    cbnz w0, .Lgpu_setup_failed
    address x9, gpu_io_output
    ldp w10, w11, [x9]
    cmp w10, #1
    b.ne .Lgpu_setup_failed
    cmp w11, #1
    b.ne .Lgpu_setup_failed
    ldr w10, [x9, #8]
    cbnz w10, .Lgpu_setup_failed
    ldp w10, w11, [x9, #12]
    cbz w10, .Lgpu_setup_failed
    cmp w10, #192
    b.hs .Lgpu_setup_failed
    cbnz w11, .Lgpu_setup_failed
    str w10, [x24, #S_FENCE_ID]
    ldr w10, [x9, #20]
    ldr x11, [x9, #24]
    orr x10, x10, x11
    cbnz x10, .Lgpu_setup_failed
    step 111
    gpu_input gpu_object_data, 16
    gpu_ioctl S_CHANNEL_FD, 0xc0104809, 16, object
    cbnz w0, .Lgpu_setup_failed
    gpu_require_io_match 16

    step 112
    gpu_input gpu_reserve_image_data, 24
    gpu_ioctl S_AS_FD, 0xc0184102, 24, reserve_image
    cbnz w0, .Lgpu_setup_failed
    gpu_mark G_IMAGE_VA
    gpu_require_io_match 24
    step 113
    gpu_input gpu_map_image_data, 40
    address x9, gpu_io_input
    ldr w10, [x22, #F_memory_id]
    str w10, [x9, #8]
    gpu_ioctl S_AS_FD, 0xc0284106, 40, map_image
    cbnz w0, .Lgpu_setup_failed
    gpu_require_io_match 40
    step 114
    gpu_input gpu_reserve_buffer_data, 24
    gpu_ioctl S_AS_FD, 0xc0184102, 24, reserve_buffer
    cbnz w0, .Lgpu_setup_failed
    gpu_mark G_BUFFER_VA
    gpu_require_io_match 24
    step 115
    gpu_input gpu_map_buffer_data, 40
    address x9, gpu_io_input
    ldr w10, [x24, #S_MEMORY_ID]
    str w10, [x9, #8]
    gpu_ioctl S_AS_FD, 0xc0284106, 40, map_buffer
    cbnz w0, .Lgpu_setup_failed
    gpu_require_io_match 40
    step 116
    add x0, x23, #G_counter_before_transport
    bl gpu_query_counter
    cbnz w0, .Lgpu_setup_failed
    cbnz w1, .Lgpu_setup_failed
    step 117
    gpu_input gpu_submit_data, 24
    gpu_ioctl S_CHANNEL_FD, 0xc018481b, 24, submit, 2
    cbnz w0, .Lgpu_setup_failed
    address x9, gpu_io_output
    ldr x10, [x9]
    cbnz x10, .Lgpu_setup_failed
    ldp w10, w11, [x9, #8]
    cmp w10, #1
    b.ne .Lgpu_setup_failed
    cbnz w11, .Lgpu_setup_failed
    ldp w10, w11, [x9, #16]
    ldr w12, [x24, #S_FENCE_ID]
    cmp w10, w12
    b.ne .Lgpu_setup_failed
    cmp w11, #2
    b.ne .Lgpu_setup_failed
    str w11, [x24, #S_FENCE_TARGET]
    gpu_emit gpu_submitted_message

    /* A host-counter observation is ordered engine progress. The independent
     * Vulkan saved-capture event, before cleanup, proves actual readback.
     */
    step 118
    str wzr, [x23, #G_counter_poll_count]
    mov w25, #0
.Lgpu_poll:
    add x0, x23, #G_counter_after_transport
    bl gpu_query_counter
    cbnz w0, .Lgpu_setup_failed
    add w25, w25, #1
    str w25, [x23, #G_counter_poll_count]
    ldr w2, [x24, #S_FENCE_TARGET]
    cmp w1, w2
    b.eq .Lgpu_fence_observed
    b.hi .Lgpu_setup_failed
    cmp w25, #1000
    b.hs .Lgpu_setup_failed
    /* 10ms sleep, bounded to ten seconds of counter polling. */
    mov x0, #0x9680
    movk x0, #0x0098, lsl #16
    svc #0x0b
    b .Lgpu_poll
.Lgpu_fence_observed:
    gpu_emit gpu_fence_message
    gpu_leave
    ret
.Lgpu_setup_failed:
    gpu_leave
    b failure

.global gpu_patch_present
gpu_patch_present:
    address x9, gpu_state
    ldr w10, [x9, #S_FENCE_ID]
    mvn w10, w10
    str w10, [x21, #88]
    str wzr, [x21, #92]
    ldr w10, [x9, #S_FENCE_TARGET]
    str w10, [x21, #96]
    str wzr, [x21, #100]
    ret

/* Descriptor: x0 output descriptor, x1 actual guest address, w2 length. */
gpu_descriptor:
    str w2, [x0]
    str w1, [x0, #4]
    lsr x3, x1, #32
    and w3, w3, #15
    lsl w3, w3, #28
    lsr x4, x1, #36
    and w4, w4, #7
    orr w3, w3, w4, lsl #2
    str w3, [x0, #8]
    ret

/* Capture ten (or eleven for Open) actual CMIF response words and validate
 * all header/padding/version/result fields. w0 transport, x1 record, w2 open.
 * Returns w0=0 only for the exact successful source response.
 */
gpu_capture_cmif:
    str w0, [x1], #4
    ldp w3, w4, [x21]
    stp w3, w4, [x1], #8
    ldp w5, w6, [x21, #8]
    stp w5, w6, [x1], #8
    ldp w7, w8, [x21, #16]
    stp w7, w8, [x1], #8
    ldp w9, w10, [x21, #24]
    stp w9, w10, [x1], #8
    ldr w11, [x21, #32]
    str w11, [x1], #4
    cbz w2, 1f
    ldr w11, [x21, #36]
    str w11, [x1]
1:  orr w0, w0, w3
    orr w0, w0, w5
    orr w0, w0, w6
    orr w0, w0, w8
    orr w0, w0, w9
    orr w0, w0, w10
    orr w0, w0, w11
    mov w3, #12
    add w3, w3, w2, lsl #1
    cmp w4, w3
    cset w3, ne
    orr w0, w0, w3
    mov w3, #0x4653
    movk w3, #0x4f43, lsl #16
    cmp w7, w3
    cset w3, ne
    orr w0, w0, w3
    ret

/* x0 name, w1 bounded length including NUL, x2 response record. */
gpu_open:
    stp x29, x30, [sp, #-48]!
    stp x0, x1, [sp, #16]
    str x2, [sp, #32]
    prepare gpu_open_request
    add x0, x21, #8
    ldp x1, x2, [sp, #16]
    bl gpu_descriptor
    ldr w0, [x19, #24]
    svc #0x21
    ldr x1, [sp, #32]
    mov w2, #1
    bl gpu_capture_cmif
    ldr w1, [x21, #32]
    lsr w2, w1, #31
    orr w0, w0, w2
    ldp x29, x30, [sp], #48
    ret

/* Exact input copy into a private 40-byte packet, avoiding request aliases. */
gpu_copy_input:
    address x9, gpu_io_input
    stp xzr, xzr, [x9]
    stp xzr, xzr, [x9, #16]
    str xzr, [x9, #32]
1:  ldr w10, [x0], #4
    str w10, [x9], #4
    subs w1, w1, #4
    b.ne 1b
    ret

/* x0 input, w1 size, w2 device FD, w3 ioctl, x4 record, w5=1/2.
 * The sole Ioctl2 inline buffer is the original one-entry GPFIFO descriptor.
 * Record exact output plus the words immediately outside its descriptor.
 */
gpu_ioctl_call:
    stp x29, x30, [sp, #-80]!
    stp x0, x1, [sp, #16]
    stp x2, x3, [sp, #32]
    stp x4, x5, [sp, #48]
    address x9, gpu_io_guard_before
    mov w10, #0xa5a5
    movk w10, #0xa5a5, lsl #16
    mov w11, #12
1:  str w10, [x9], #4
    subs w11, w11, #1
    b.ne 1b
    cmp w5, #2
    b.eq 2f
    prepare gpu_ioctl1_request
    b 3f
2:  prepare gpu_ioctl2_request
3:  add x0, x21, #8
    ldp x1, x2, [sp, #16]
    bl gpu_descriptor
    ldr w9, [sp, #56]
    cmp w9, #2
    b.eq 4f
    add x0, x21, #20
    address x1, gpu_io_output
    ldr w2, [sp, #24]
    bl gpu_descriptor
    ldp x9, x10, [sp, #32]
    stp w9, w10, [x21, #48]
    b 5f
4:  add x0, x21, #20
    address x1, gpu_entry
    mov w2, #8
    bl gpu_descriptor
    add x0, x21, #32
    address x1, gpu_io_output
    ldr w2, [sp, #24]
    bl gpu_descriptor
    ldp x9, x10, [sp, #32]
    stp w9, w10, [x21, #64]
5:  ldr w0, [x19, #24]
    svc #0x21
    ldr x1, [sp, #48]
    mov w2, #0
    bl gpu_capture_cmif
    mov w17, w0
    ldr x9, [sp, #48]
    add x9, x9, #40
    address x10, gpu_io_guard_before
    ldr w11, [x10], #4
    str w11, [x9], #4
    mov w12, #0xa5a5
    movk w12, #0xa5a5, lsl #16
    cmp w11, w12
    cset w13, ne
    orr w17, w17, w13
    ldr w14, [sp, #24]
    ldr w16, [sp, #40]
6:  ldr w11, [x10], #4
    str w11, [x9], #4
    tbnz w16, #31, 7f
    /* Input-only ioctl must not have written the output descriptor. */
    cmp w11, w12
    cset w13, ne
    orr w17, w17, w13
7:  subs w14, w14, #4
    b.ne 6b
    ldr w11, [x10]
    str w11, [x9]
    cmp w11, w12
    cset w13, ne
    orr w0, w17, w13
    ldp x29, x30, [sp], #80
    ret

/* w0 size; verify an ioctl whose output must exactly echo its real input. */
gpu_match_io:
    address x9, gpu_io_input
    address x10, gpu_io_output
    mov w11, #0
1:  ldr w12, [x9], #4
    ldr w13, [x10], #4
    eor w12, w12, w13
    orr w11, w11, w12
    subs w0, w0, #4
    b.ne 1b
    mov w0, w11
    ret

/* x0 response record, return w0 validated/error, w1 actual 32-bit counter. */
gpu_query_counter:
    stp x29, x30, [sp, #-32]!
    str x0, [sp, #16]
    prepare gpu_query_request
    ldr w0, [x24, #S_FENCE_ID]
    mvn w0, w0
    str w0, [x21, #8]
    ldr w0, [x24, #S_SYNC_HANDLE]
    svc #0x21
    ldr x9, [sp, #16]
    str w0, [x9], #4
    ldp w2, w3, [x21]
    stp w2, w3, [x9], #8
    ldp w4, w1, [x21, #8]
    stp w4, w1, [x9], #8
    ldp w5, w6, [x21, #16]
    stp w5, w6, [x9]
    orr w0, w0, w4
    orr w0, w0, w5
    orr w0, w0, w6
    cmp w2, #0x77
    cset w2, ne
    orr w0, w0, w2
    cmp w3, #4
    cset w3, ne
    orr w0, w0, w3
    ldp x29, x30, [sp], #32
    ret

/* Input-only fixed-VA FreeSpace removes its mapping, pin and reservation.
 * Do not UnmapBuffer first: that leaves a stale mapping in allocation.mappings
 * in the frozen source. Release each acquired object once, preserve first error.
 */
.global gpu_cleanup
gpu_cleanup:
    gpu_enter
    gpu_emit gpu_cleanup_message
    ldr w9, [x24, #S_FLAGS]
    tbz w9, #G_BUFFER_VA, 1f
    bic w9, w9, #(1 << G_BUFFER_VA)
    str w9, [x24, #S_FLAGS]
    gpu_input gpu_free_buffer_data, 16
    gpu_ioctl S_AS_FD, 0x40104103, 16, free_buffer
    gpu_cleanup_result 120
1:  ldr w9, [x24, #S_FLAGS]
    tbz w9, #G_IMAGE_VA, 2f
    bic w9, w9, #(1 << G_IMAGE_VA)
    str w9, [x24, #S_FLAGS]
    gpu_input gpu_free_image_data, 16
    gpu_ioctl S_AS_FD, 0x40104103, 16, free_image
    gpu_cleanup_result 121
2:  ldr w9, [x24, #S_FLAGS]
    tbz w9, #G_TSG_BOUND, 3f
    bic w9, w9, #(1 << G_TSG_BOUND)
    str w9, [x24, #S_FLAGS]
    gpu_input gpu_zero_data, 4
    address x9, gpu_io_input
    ldr w10, [x24, #S_CHANNEL_FD]
    str w10, [x9]
    gpu_ioctl S_TSG_FD, 0xc0045402, 4, tsg_unbind
    mov w25, w0
    mov w0, #4
    bl gpu_match_io
    orr w0, w0, w25
    gpu_cleanup_result 122
3:  ldr w0, [x24, #S_CHANNEL_FD]
    tbnz w0, #31, 4f
    mov w9, #-1
    str w9, [x24, #S_CHANNEL_FD]
    add x1, x23, #G_close_channel_transport
    bl gpu_close
    gpu_cleanup_result 123
4:  ldr w0, [x24, #S_TSG_FD]
    tbnz w0, #31, 5f
    mov w9, #-1
    str w9, [x24, #S_TSG_FD]
    add x1, x23, #G_close_tsg_transport
    bl gpu_close
    gpu_cleanup_result 124
5:  ldr w0, [x24, #S_AS_FD]
    tbnz w0, #31, 6f
    mov w9, #-1
    str w9, [x24, #S_AS_FD]
    add x1, x23, #G_close_as_transport
    bl gpu_close
    gpu_cleanup_result 125
6:  ldr w9, [x24, #S_FLAGS]
    tbz w9, #G_MEMORY, 8f
    bic w9, w9, #(1 << G_MEMORY)
    str w9, [x24, #S_FLAGS]
    prepare memory_destroy_request
    ldr w0, [x24, #S_MEMORY_ID]
    str w0, [x21, #8]
    ldr w0, [x19, #20]
    svc #0x21
    gpu_tipc_capture memory_destroy
    gpu_tipc_validate 112, 1, 7f
    b 8f
7:  mov w0, #1
    gpu_cleanup_result 126
8:  ldr w0, [x24, #S_SYNC_HANDLE]
    cbz w0, 9f
    str wzr, [x24, #S_SYNC_HANDLE]
    svc #0x16
    str w0, [x23, #G_close_sync]
    gpu_cleanup_result 127
9:  gpu_leave
    ret

/* w0 device FD, x1 response record. No kernel handle is returned by NV Close. */
gpu_close:
    stp x29, x30, [sp, #-32]!
    stp x0, x1, [sp, #16]
    prepare gpu_close_request
    ldr w0, [sp, #16]
    str w0, [x21, #32]
    ldr w0, [x19, #24]
    svc #0x21
    ldr x1, [sp, #24]
    mov w2, #0
    bl gpu_capture_cmif
    ldp x29, x30, [sp], #32
    ret

/* Appended after the unchanged 281 base records, before COMPLETE/FAILURE. */
.global gpu_report
gpu_report:
    gpu_enter
    address x23, gpu_field_names
    address x24, gpu_record
    address x25, line_buffer
1:  ldrb w0, [x23]
    cbz w0, 5f
    address x2, line_prefix
    ldr x3, [x2]
    str x3, [x25]
    ldrh w3, [x2, #8]
    strh w3, [x25, #8]
    add x2, x25, #10
2:  ldrb w3, [x23], #1
    cbz w3, 3f
    strb w3, [x2], #1
    b 2b
3:  mov w3, #'='
    strb w3, [x2], #1
    ldr w4, [x24], #4
    mov w6, #28
4:  lsr w5, w4, w6
    and w5, w5, #15
    cmp w5, #9
    add w7, w5, #'0'
    add w8, w5, #('a' - 10)
    csel w5, w7, w8, ls
    strb w5, [x2], #1
    subs w6, w6, #4
    b.ge 4b
    mov w3, #10
    strb w3, [x2], #1
    mov x0, x25
    sub x1, x2, x25
    svc #0x27
    b 1b
5:  gpu_leave
    ret

.section .rodata, "a"
.balign 16
gpu_open_request:
    .word 0x00100004, 8, 0, 0, 0, 0, 0, 0
    .word 0x49434653, 0, 0, 0
    .zero 128 - (. - gpu_open_request)
gpu_ioctl1_request:
    .word 0x01100004, 10, 0, 0, 0, 0, 0, 0
    .word 0x49434653, 0, 1, 0, 0, 0
    .zero 128 - (. - gpu_ioctl1_request)
gpu_ioctl2_request:
    .word 0x01200004, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    .word 0x49434653, 0, 11, 0, 0, 0
    .zero 128 - (. - gpu_ioctl2_request)
gpu_close_request:
    .word 4, 9, 0, 0, 0x49434653, 0, 2, 0, 0
    .zero 128 - (. - gpu_close_request)
gpu_memory_create_request:
    .word 0x7f, 3, 0, GPU_BUFFER_SIZE, 0
    .zero 128 - (. - gpu_memory_create_request)
gpu_memory_bind_request:
    .word 0x82, 9, 0, 0, 0, GPU_BUFFER_SIZE, 0, 0, 0, 0, 0
    .zero 128 - (. - gpu_memory_bind_request)
gpu_sync_init_request:
    .word 0xd9, 0
    .zero 128 - (. - gpu_sync_init_request)
gpu_sync_open_request:
    .word 0xda, 0
    .zero 128 - (. - gpu_sync_open_request)
gpu_query_request:
    .word 0x77, 1, 0
    .zero 128 - (. - gpu_query_request)
.balign 8
gpu_zero_data:
    .zero 40
gpu_as_init_data:
    .word 0, 0, 0x20000, 0
    .quad 0, 0, 0
gpu_fifo_data:
    .word 1, 1, 0, 0, 0, 0, 0, 0
gpu_object_data:
    .word 0xc797, 0, 0, 0
gpu_reserve_image_data:
    .word 2, 0x1000, 1, 0
    .quad GPU_IMAGE_VA
gpu_reserve_buffer_data:
    .word 4, 0x1000, 1, 0
    .quad GPU_BUFFER_VA
gpu_map_image_data:
    .word 1, 0, 0, 0x1000
    .quad 0, 8192, GPU_IMAGE_VA
gpu_map_buffer_data:
    .word 1, 0, 0, 0x1000
    .quad 0, GPU_BUFFER_SIZE, GPU_BUFFER_VA
gpu_submit_data:
    .quad 0
    .word 1, 2, 0, 0
gpu_free_image_data:
    .quad GPU_IMAGE_VA
    .word 2, 0x1000
gpu_free_buffer_data:
    .quad GPU_BUFFER_VA
    .word 4, 0x1000
gpu_entry:
    .quad GPU_BUFFER_VA | (NX2_GPU_WORD_COUNT << 42)
gpu_as_name:
    .asciz "/dev/nvhost-as-gpu"
gpu_as_name_end:
gpu_channel_name:
    .asciz "/dev/nvhost-gpu"
gpu_channel_name_end:
gpu_tsg_name:
    .asciz "/dev/nvhost-tsg-gpu"
gpu_tsg_name_end:
gpu_begin_message:
    .ascii "NX2_GPU_BEGIN\n"
gpu_begin_message_end:
gpu_submitted_message:
    .ascii "NX2_GPU_SUBMITTED\n"
gpu_submitted_message_end:
gpu_fence_message:
    .ascii "NX2_GPU_FENCE_OBSERVED\n"
gpu_fence_message_end:
gpu_cleanup_message:
    .ascii "NX2_GPU_CLEANUP\n"
gpu_cleanup_message_end:
.balign 16
.global gpu_fixture_layout
gpu_fixture_layout:
    .ascii "NX2GPUv1"
    .word gpu_field_names - field_names, GPU_FIELD_COUNT
    .word gpu_record - record, gpu_state - record
    .word gpu_state_end - gpu_state, gpu_buffer - record
    .word gpu_initial_data - field_names
.balign 16
.global gpu_initial_data, gpu_initial_data_end
gpu_initial_data:
    .incbin "gpu-buffer.bin"
gpu_initial_data_end:
.if gpu_initial_data_end - gpu_initial_data != GPU_BUFFER_SIZE
    .error "GPU fixture must contain exactly sixteen KiB of original data"
.endif

.section .data, "aw"
.balign 16
.global gpu_record, gpu_state, gpu_buffer
gpu_record:
    .fill GPU_FIELD_COUNT, 4, 0xffffffff
gpu_state:
    .word -1, -1, -1, 0, 0, 0, 0, 0
.global gpu_state_end
gpu_state_end:
.balign 16
gpu_io_input:
    .zero 40
gpu_io_guard_before:
    .word 0
gpu_io_output:
    .zero 40
gpu_io_guard_after:
    .word 0
.balign 4096
gpu_buffer:
    .zero GPU_BUFFER_SIZE
