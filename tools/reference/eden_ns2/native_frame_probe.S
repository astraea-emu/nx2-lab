/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (c) 2026 nx2-lab contributors.
 * Original CPU image / native display workload for frozen Eden e2f285ab.
 * CMIF and reporting helpers adapt earlier NX2 probes. No SDK is used.
 * Replies begin unobserved. Pixels are drawn by ARM64 code, never embedded.
 */
.ifndef NX2_FRAME_VARIANT
    .set NX2_FRAME_VARIANT, 0
.endif
.ifndef NX2_GPU_PROBE
    .set NX2_GPU_PROBE, 0
.endif
.if (NX2_FRAME_VARIANT != 0) && (NX2_FRAME_VARIANT != 1)
    .error "NX2_FRAME_VARIANT must be 0 or 1"
.endif
.section .rodata, "a"
.global field_names
field_names:
.set FIELD_OFFSET, 0
.macro field name, count=1
    .equ F_\name, FIELD_OFFSET
    .set FIELD_OFFSET, FIELD_OFFSET + 4 * \count
.if \count == 1
    .asciz "\name"
.else
    .asciz "~\name"
.endif
.endm
.macro cmif_fields prefix
    field \prefix\()_transport
    field \prefix\()_header0
    field \prefix\()_header1
    field \prefix\()_descriptor
    field \prefix\()_magic
    field \prefix\()_result
.endm
.macro tipc_fields prefix
    field \prefix\()_transport
    field \prefix\()_header0
    field \prefix\()_header1
    field \prefix\()_result
.endm
.macro notification_fields prefix
    tipc_fields \prefix
    field \prefix\()_guard_before
    field \prefix\()_word, 32
    field \prefix\()_guard_after
.endm
    field variant
    field image_width
    field image_height
    field image_address_lo
    field image_address_hi
    field image_checksum
    field connect_rc
    field sm_handle
    cmif_fields sm_init
    cmif_fields get_applet
    field applet_handle
    cmif_fields open_proxy
    field proxy_handle
    cmif_fields get_window
    field window_handle
    cmif_fields get_aruid
    field aruid_lo
    field aruid_hi
    cmif_fields get_self
    field self_handle
    cmif_fields get_gsv
    field gsv_handle
    tipc_fields bootstrap
    tipc_fields bind
    tipc_fields ready
    tipc_fields image_init
    tipc_fields image_formats
    field open_nvdrv_transport
    field open_nvdrv_header0
    field open_nvdrv_header1
    field open_nvdrv_descriptor
    field nvdrv_handle
    field open_nvdrv_result
    tipc_fields gpu_init
    tipc_fields gpu_ready
    tipc_fields size_zero
    field size_zero_lo
    field size_zero_hi
    tipc_fields size_valid
    field size_valid_lo
    field size_valid_hi
    tipc_fields memory_create
    field memory_id
    tipc_fields memory_bind
    tipc_fields image_create
    field image_id
    tipc_fields pool_create
    tipc_fields display_init
    field open_vi2_transport
    field open_vi2_header0
    field open_vi2_header1
    field open_vi2_descriptor
    field vi2_handle
    field open_vi2_result
    tipc_fields register
    tipc_fields open_display
    tipc_fields bind_display
    tipc_fields available_before
    field available_before_lo
    field available_before_hi
    tipc_fields present
    field present_lo
    field present_hi
    field present_tail00
    field present_tail01
    field present_tail02
    field present_tail03
    tipc_fields poll
    field poll_lo
    field poll_hi
    field poll_count
    field poll_queued_count
    field poll_released_count
    notification_fields released
    notification_fields clear
    tipc_fields unbind_display
    tipc_fields unregister
    tipc_fields close_display
    tipc_fields pool_destroy
    tipc_fields image_destroy
    tipc_fields memory_destroy
    tipc_fields display_finalize
    field close_vi2
    field close_nvdrv
    field close_gsv
    field close_self
    field close_window
    field close_proxy
    field close_applet
    field close_sm
    field fail_step
    .byte 0
.global FIELD_COUNT
.equ FIELD_COUNT, FIELD_OFFSET / 4
.if FIELD_COUNT != 281
    .error "frame report contract must have 281 fields"
.endif
.section .text, "ax"
.global _start
.macro address target, symbol
    adrp \target, \symbol
    add \target, \target, :lo12:\symbol
.endm
.macro step number
    mov w0, #\number
    str w0, [x22, #F_fail_step]
.endm
.macro prepare name
    address x0, \name
    bl prepare_request
.endm

/* Admit a validated, distinct real handle before later payload comparisons,
 * so a malformed result/magic still causes cleanup of the acquired object.
 * Frozen KHandleTable: index < 1024, nonzero 15-bit serial, top two bits zero.
 */
.macro admit slot
    tst w6, #0xc0000000
    b.ne failure
    and w7, w6, #0x7fff
    cmp w7, #1024
    b.hs failure
    ubfx w7, w6, #15, #15
    cbz w7, failure
    mov x7, #0
1:  ldr w8, [x19, x7, lsl #2]
    cmp w6, w8
    b.eq failure
    add x7, x7, #1
    cmp x7, #8
    b.ne 1b
    str w6, [x19, #(4 * \slot)]
.endm

/* CMIF response: HIPC header, optional handle descriptor, aligned SFCO at
 * 0x10, result at 0x18. ARUID adds eight raw bytes at 0x20. Its frozen builder
 * reports 14 words rather than the result-only 10. These are not TIPC offsets.
 */
.macro cmif_call request, slot, prefix, descriptor=0, outslot=-1, outfield=0, aruid=0
    prepare \request
    ldr w0, [x19, #(4 * \slot)]
    svc #0x21
    str w0, [x22, #F_\prefix\()_transport]
    ldp w1, w2, [x21]
    str w1, [x22, #F_\prefix\()_header0]
    str w2, [x22, #F_\prefix\()_header1]
    ldr w3, [x21, #8]
    str w3, [x22, #F_\prefix\()_descriptor]
    ldr w4, [x21, #0x10]
    str w4, [x22, #F_\prefix\()_magic]
    ldr w5, [x21, #0x18]
    str w5, [x22, #F_\prefix\()_result]
.if \outslot >= 0
    ldr w6, [x21, #0x0c]
    str w6, [x22, #\outfield]
.endif
.if \aruid
    ldr x7, [x21, #0x20]
    str x7, [x22, #F_aruid_lo]
.endif
    cbnz w0, failure
    cbnz w1, failure
    mov w7, #(10 + 4 * \aruid)
.if \descriptor
    orr w7, w7, #0x80000000
.endif
    cmp w2, w7
    b.ne failure
    cmp w3, #\descriptor
    b.ne failure
.if \outslot >= 0
    admit \outslot
.endif
    mov w7, #0x4653
    movk w7, #0x4f43, lsl #16
    cmp w4, w7
    b.ne failure
    cbnz w5, failure
.endm

/* TIPC result-only replies preserve type=16+command and carry exactly one
 * raw word at offset 8. They contain neither mandatory CMIF padding nor SFCO.
 */
.macro tipc_capture prefix
    str w0, [x22, #F_\prefix\()_transport]
    ldp w1, w2, [x21]
    str w1, [x22, #F_\prefix\()_header0]
    str w2, [x22, #F_\prefix\()_header1]
    ldr w3, [x21, #8]
    str w3, [x22, #F_\prefix\()_result]
.endm
.macro tipc_check prefix, command, expected=0, raw=1, fail=failure
    add x9, x22, #F_\prefix\()_transport
    ldp w0, w1, [x9]
    ldp w2, w3, [x9, #8]
    cbnz w0, \fail
    cmp w1, #(16 + \command)
    b.ne \fail
    cmp w2, #\raw
    b.ne \fail
    mov w4, #((\expected) & 0xffff)
    movk w4, #(((\expected) >> 16) & 0xffff), lsl #16
    cmp w3, w4
    b.ne \fail
.endm
.macro tipc_call request, slot, prefix, command, expected=0
    prepare \request
    ldr w0, [x19, #(4 * \slot)]
    svc #0x21
    tipc_capture \prefix
    tipc_check \prefix, \command, \expected
.endm

.macro notification_call prefix, size, result, first, rest
    prepare notification_request
    mov w0, #\size
    str w0, [x21, #8]
    address x0, notification_buffer
    str w0, [x21, #12]
    lsr x1, x0, #32
    and w1, w1, #15
    lsl w1, w1, #28
    lsr x2, x0, #36
    and w2, w2, #7
    orr w1, w1, w2, lsl #2
    str w1, [x21, #16]
    /* B descriptor flags=0, writable real guest address, explicit size. */
    address x0, notification_guard_before
    mov w1, #0xa5a5
    movk w1, #0xa5a5, lsl #16
    mov w2, #34
1:  str w1, [x0], #4
    subs w2, w2, #1
    b.ne 1b
    ldr w0, [x19, #28]
    svc #0x21
    tipc_capture \prefix
    /* Snapshot before comparison, including both words outside the buffer. */
    address x0, notification_guard_before
    add x1, x22, #F_\prefix\()_guard_before
    mov w2, #34
2:  ldr w3, [x0], #4
    str w3, [x1], #4
    subs w2, w2, #1
    b.ne 2b
    tipc_check \prefix, 21, \result
    add x0, x22, #F_\prefix\()_guard_before
    mov w1, #((\first) & 0xffff)
    movk w1, #(((\first) >> 16) & 0xffff), lsl #16
    mov w2, #((\rest) & 0xffff)
    movk w2, #(((\rest) >> 16) & 0xffff), lsl #16
    bl check_notification_snapshot
.endm


.macro emit marker
    address x0, \marker\()_message
    mov x1, #(\marker\()_message_end - \marker\()_message)
    svc #0x27
.endm
.macro send slot, prefix
    ldr w0, [x19, #(4 * \slot)]
    svc #0x21
    tipc_capture \prefix
.endm
.macro moved request, prefix, command, slot, outfield
    prepare \request
    ldr w0, [x19, #20]
    svc #0x21
    str w0, [x22, #F_\prefix\()_transport]
    ldp w1, w2, [x21]
    str w1, [x22, #F_\prefix\()_header0]
    str w2, [x22, #F_\prefix\()_header1]
    ldr w3, [x21, #8]
    str w3, [x22, #F_\prefix\()_descriptor]
    ldr w6, [x21, #12]
    str w6, [x22, #F_\outfield]
    ldr w5, [x21, #16]
    str w5, [x22, #F_\prefix\()_result]
    cbnz w0, failure
    cmp w1, #(16 + \command)
    b.ne failure
    mov w7, #0x80000001
    cmp w2, w7
    b.ne failure
    cmp w3, #0x20
    b.ne failure
    admit \slot
    cbnz w5, failure
.endm
.macro capture_u64 prefix
    ldp w4, w5, [x21, #12]
    str w4, [x22, #F_\prefix\()_lo]
    str w5, [x22, #F_\prefix\()_hi]
.endm
.macro check_u64 prefix, value
    add x9, x22, #F_\prefix\()_lo
    ldr x0, [x9]
    mov x1, #\value
    cmp x0, x1
    b.ne failure
.endm
.macro patch_id field, offset=8
    ldr w0, [x22, #F_\field]
    str w0, [x21, #\offset]
.endm
.macro take_id field, flag
    ldr w0, [x21, #12]
    str w0, [x22, #F_\field]
    cbz w0, failure
    cmn w0, #1
    b.eq failure
    orr x20, x20, #(1 << \flag)
.endm
/* Cleanup preserves the first failure and attempts each acquired resource once. */
.macro release request, slot, prefix, command, flag, number, idfield=0
    tbz x20, #\flag, .Lskip\@
    bic x20, x20, #(1 << \flag)
    prepare \request
.ifnc \idfield,0
    patch_id \idfield
.endif
    send \slot, \prefix
    tipc_check \prefix, \command, 0, 1, .Lbad\@
    b .Lskip\@
.Lbad\@:
    ldr w0, [x22, #F_fail_step]
    cbnz w0, .Lskip\@
    mov w0, #\number
    str w0, [x22, #F_fail_step]
.Lskip\@:
.endm
_start:
    mrs x21, tpidrro_el0
    address x22, record
    address x19, live_handles
    mov x20, #0
    address x0, frame_config
    ldp w1, w2, [x0]
    ldr w3, [x0, #8]
    str w1, [x22, #F_variant]
    str w2, [x22, #F_image_width]
    str w3, [x22, #F_image_height]
    address x0, image_buffer
    str x0, [x22, #F_image_address_lo]
    emit begin

    step 1
    address x1, sm_name
    svc #0x1f
    str w0, [x22, #F_connect_rc]
    str w1, [x22, #F_sm_handle]
    cbnz w0, failure
    mov w6, w1
    admit 0

    step 2
    cmif_call sm_initialize_request, 0, sm_init
    step 3
    cmif_call get_applet_request, 0, get_applet, 0x20, 1, F_applet_handle
    step 4
    cmif_call open_proxy_request, 1, open_proxy, 0x20, 2, F_proxy_handle
    step 5
    cmif_call get_window_request, 2, get_window, 0x20, 3, F_window_handle
    step 6
    cmif_call command1_request, 3, get_aruid, 0, -1, 0, 1
    ldr x0, [x22, #F_aruid_lo]
    cbz x0, failure
    step 7
    cmif_call command1_request, 2, get_self, 0x20, 4, F_self_handle
    step 8
    cmif_call get_gsv_request, 4, get_gsv, 2, 5, F_gsv_handle

    step 9
    prepare bootstrap_request
    ldr x0, [x22, #F_aruid_lo]
    str x0, [x21, #16]
    ldr w0, [x19, #20]
    svc #0x21
    tipc_capture bootstrap
    tipc_check bootstrap, 4
    step 10
    tipc_call bind_request, 5, bind, 11
    step 11
    tipc_call ready_request, 5, ready, 101
    step 12
    tipc_call image_init_request, 5, image_init, 1501
    step 13
    tipc_call image_formats_request, 5, image_formats, 1502
    step 14
    moved open_nvdrv_request, open_nvdrv, 1402, 6, nvdrv_handle
    step 15
    tipc_call gpu_init_request, 5, gpu_init, 401
    step 16
    tipc_call gpu_ready_request, 5, gpu_ready, 402

    step 17
    prepare size_zero_request
    send 5, size_zero
    capture_u64 size_zero
    tipc_check size_zero, 435, 0x100f3, 3
    check_u64 size_zero, 0
    step 18
    prepare size_valid_request
    send 5, size_valid
    capture_u64 size_valid
    tipc_check size_valid, 435, 0, 3
    check_u64 size_valid, 8192
    step 19
.if NX2_GPU_PROBE
    bl gpu_initialize
.else
    bl draw_image
.endif

    step 20
    prepare memory_create_request
    send 5, memory_create
    ldr w4, [x21, #12]
    str w4, [x22, #F_memory_id]
    tipc_check memory_create, 111, 0, 2
    take_id memory_id, 1
    step 21
    prepare memory_bind_request
    patch_id memory_id
    address x0, image_buffer
    str x0, [x21, #12]
    send 5, memory_bind
    tipc_check memory_bind, 114
    step 22
    prepare image_create_request
    patch_id memory_id, 76
    send 5, image_create
    ldr w4, [x21, #12]
    str w4, [x22, #F_image_id]
    tipc_check image_create, 429, 0, 2
    take_id image_id, 2
    step 23
    prepare pool_create_request
    patch_id image_id
    send 5, pool_create
    tipc_check pool_create, 315
    orr x20, x20, #(1 << 3)
    step 24
    tipc_call display_init_request, 5, display_init, 301
    orr x20, x20, #1
    step 25
    moved open_vi2_request, open_vi2, 305, 7, vi2_handle
    step 26
    tipc_call register_request, 7, register, 201
    orr x20, x20, #(1 << 4)
    step 27
    tipc_call open_display_request, 7, open_display, 101
    orr x20, x20, #(1 << 5)
    step 28
    tipc_call bind_display_request, 7, bind_display, 251
    orr x20, x20, #(1 << 6)
    step 29
    prepare availability_request
    send 7, available_before
    capture_u64 available_before
    tipc_check available_before, 212, 0, 3
    check_u64 available_before, 0x7fff
.if NX2_GPU_PROBE
    bl gpu_submit_and_wait
.endif
    step 30
    prepare present_request
    patch_id image_id, 20
.if NX2_GPU_PROBE
    bl gpu_patch_present
.endif
    emit present_begin
    send 7, present
    capture_u64 present
    ldp w4, w5, [x21, #20]
    str w4, [x22, #F_present_tail00]
    str w5, [x22, #F_present_tail01]
    ldp w4, w5, [x21, #28]
    str w4, [x22, #F_present_tail02]
    str w5, [x22, #F_present_tail03]
    tipc_check present, 229, 0, 7
    check_u64 present, 0x7ffe
    add x9, x22, #F_present_tail00
    ldp x0, x1, [x9]
    orr x0, x0, x1
    cbnz x0, failure
    emit presented

    /* Retirement is checked, never used as a renderer-completion fence.
     * Hold unchanged image/resources for 100 x 100ms. The host must separately
     * observe successful capture before CLEANUP_BEGIN, or reject the trial.
     */
    step 31
    str wzr, [x22, #F_poll_count]
    str wzr, [x22, #F_poll_queued_count]
    str wzr, [x22, #F_poll_released_count]
    mov w23, #100
.Lhold:
    prepare availability_request
    send 7, poll
    capture_u64 poll
    tipc_check poll, 212, 0, 3
    add x9, x22, #F_poll_lo
    ldr x0, [x9]
    mov x1, #0x7ffe
    cmp x0, x1
    b.eq .Lqueued
    add x1, x1, #1
    cmp x0, x1
    b.ne failure
    ldr w0, [x22, #F_poll_released_count]
    add w0, w0, #1
    str w0, [x22, #F_poll_released_count]
    b .Lsleep
.Lqueued:
    ldr w0, [x22, #F_poll_queued_count]
    add w0, w0, #1
    str w0, [x22, #F_poll_queued_count]
.Lsleep:
    ldr w0, [x22, #F_poll_count]
    add w0, w0, #1
    str w0, [x22, #F_poll_count]
    mov x0, #0xe100
    movk x0, #0x05f5, lsl #16
    svc #0x0b
    subs w23, w23, #1
    b.ne .Lhold
    check_u64 poll, 0x7fff
    step 32
    notification_call released, 128, 0, 8, 0
    step 33
    notification_call clear, 128, 0, 0, 0
    str wzr, [x22, #F_fail_step]
    b cleanup

/* CPU-produced pattern: 2x2 checker, with four asymmetric 2x2 corners.
 * Native 16x9 GOB addressing swaps offset bits 5/6 relative to legacy tiling.
 * Nothing writes this backing after draw_image returns.
 */
.if !NX2_GPU_PROBE
draw_image:
    address x9, image_buffer
    mov x0, x9
    mov w1, #512
1:  stp xzr, xzr, [x0], #16
    subs w1, w1, #1
    b.ne 1b
    address x8, frame_config
    ldr w10, [x8, #12]
    ldr w11, [x8, #16]
    mov w1, #0
2:  mov w0, #0
3:  lsr w2, w0, #1
    eor w2, w2, w1, lsr #1
    tst w2, #1
    csel w3, w10, w11, eq
    cmp w1, #2
    b.hs 4f
    cmp w0, #2
    b.hs 5f
    ldr w3, [x8, #20]
    b 6f
5:  cmp w0, #14
    b.lo 6f
    ldr w3, [x8, #24]
    b 6f
4:  cmp w1, #7
    b.lo 6f
    cmp w0, #2
    b.hs 7f
    ldr w3, [x8, #28]
    b 6f
7:  cmp w0, #14
    b.lo 6f
    ldr w3, [x8, #32]
6:  lsr w2, w1, #3
    lsl w2, w2, #9
    and w4, w0, #3
    add w2, w2, w4, lsl #2
    and w4, w1, #3
    add w2, w2, w4, lsl #4
    and w4, w0, #4
    add w2, w2, w4, lsl #4
    and w4, w1, #4
    add w2, w2, w4, lsl #5
    and w4, w0, #8
    add w2, w2, w4, lsl #5
    str w3, [x9, x2]
    add w0, w0, #1
    cmp w0, #16
    b.ne 3b
    add w1, w1, #1
    cmp w1, #9
    b.ne 2b
    /* FNV-1a over the actual full backing, including untouched padding. */
    mov w0, #0x9dc5
    movk w0, #0x811c, lsl #16
    mov w1, #0x0193
    movk w1, #0x0100, lsl #16
    mov w2, #8192
8:  ldrb w3, [x9], #1
    eor w0, w0, w3
    mul w0, w0, w1
    subs w2, w2, #1
    b.ne 8b
    str w0, [x22, #F_image_checksum]
    ret
.endif

/* Clear only the 0x100-byte IPC area; retain the remainder of the guest TLS. */
prepare_request:
    mov x2, x21
    mov w3, #16
1:  stp xzr, xzr, [x2], #16
    subs w3, w3, #1
    b.ne 1b
    mov x2, x21
    mov w3, #8
2:  ldp x4, x5, [x0], #16
    stp x4, x5, [x2], #16
    subs w3, w3, #1
    b.ne 2b
    ret

/* x0 points to snapshot guard/32 words/guard; w1 is first, w2 is rest. */
check_notification_snapshot:
    mov w4, #0xa5a5
    movk w4, #0xa5a5, lsl #16
    ldr w3, [x0], #4
    cmp w3, w4
    b.ne failure
    ldr w3, [x0], #4
    cmp w3, w1
    b.ne failure
    mov w5, #31
1:  ldr w3, [x0], #4
    cmp w3, w2
    b.ne failure
    subs w5, w5, #1
    b.ne 1b
    ldr w3, [x0]
    cmp w3, w4
    b.ne failure
    ret


failure:
cleanup:
    /* This marker precedes every resource/handle release, including failure. */
    emit cleanup_begin
.if NX2_GPU_PROBE
    bl gpu_cleanup
.endif
    release unbind_display_request, 7, unbind_display, 252, 6, 34
    release unregister_request, 7, unregister, 202, 4, 35
    release close_display_request, 7, close_display, 102, 5, 36
    release pool_destroy_request, 5, pool_destroy, 314, 3, 37, image_id
    release image_destroy_request, 5, image_destroy, 430, 2, 38, image_id
    release memory_destroy_request, 5, memory_destroy, 112, 1, 39, memory_id
    release display_finalize_request, 5, display_finalize, 303, 0, 40
    mov x23, #7
    add x24, x22, #F_close_vi2
    mov w25, #41
1:  ldr w0, [x19, x23, lsl #2]
    cbz w0, 3f
    svc #0x16
    str w0, [x24]
    str wzr, [x19, x23, lsl #2]
    cbz w0, 3f
    ldr w1, [x22, #F_fail_step]
    cbnz w1, 3f
    str w25, [x22, #F_fail_step]
3:  add x24, x24, #4
    add w25, w25, #1
    subs x23, x23, #1
    b.ge 1b
report:
    address x23, field_names
    mov x24, #0
    address x25, line_buffer
1:  ldrb w0, [x23]
    cbz w0, report_end
    cmp w0, #'~'
    cset w28, eq
    add x23, x23, x28
    mov x26, x23
    mov x27, #0
2:  address x2, line_prefix
    ldr x3, [x2]
    str x3, [x25]
    ldrh w3, [x2, #8]
    strh w3, [x25, #8]
    add x2, x25, #10
    mov x23, x26
3:  ldrb w3, [x23], #1
    cbz w3, 4f
    strb w3, [x2], #1
    b 3b
4:  cbz w28, 5f
    mov w3, #10
    udiv w4, w27, w3
    msub w5, w4, w3, w27
    add w4, w4, #'0'
    add w5, w5, #'0'
    strb w4, [x2], #1
    strb w5, [x2], #1
5:  mov w3, #'='
    strb w3, [x2], #1
    ldr w4, [x22, x24, lsl #2]
    mov w6, #28
6:  lsr w5, w4, w6
    and w5, w5, #15
    cmp w5, #9
    add w7, w5, #'0'
    add w8, w5, #('a' - 10)
    csel w5, w7, w8, ls
    strb w5, [x2], #1
    subs w6, w6, #4
    b.ge 6b
    mov w3, #10
    strb w3, [x2], #1
    mov x0, x25
    sub x1, x2, x25
    svc #0x27
    add x24, x24, #1
    cbz w28, 1b
    add x27, x27, #1
    cmp x27, #32
    b.ne 2b
    b 1b

report_end:
.if NX2_GPU_PROBE
    bl gpu_report
.endif
    ldr w0, [x22, #F_fail_step]
    cbnz w0, 1f
    address x0, complete_message
    mov x1, #(complete_message_end - complete_message)
    b 2f
1:  address x0, failure_message
    mov x1, #(failure_message_end - failure_message)
2:  svc #0x27
    svc #0x7
3:  b 3b

.section .rodata, "a"
.balign 16
.global request_templates
request_templates:
/* Bounded 128-byte original templates; dynamic addresses/IDs start at zero.
 * No request has more than 104 meaningful bytes; prepare_request clears TLS
 * and copies all 128 bytes so stale request tails cannot become payload.
 */
.global sm_initialize_request
sm_initialize_request:
    .word 4, 0x8000000a, 1, 0, 0, 0, 0, 0
    .word 0x49434653, 0, 0, 0, 0, 0
    .zero 128 - (. - sm_initialize_request)
.global get_applet_request
get_applet_request:
    .word 4, 10, 0, 0, 0x49434653, 0, 1, 0
    .ascii "appletOE"
    .zero 128 - (. - get_applet_request)
.global open_proxy_request
open_proxy_request:
    .word 4, 0x8000000a, 3, 0, 0, 0xffff8001, 0, 0
    .word 0x49434653, 0, 0, 0, 0, 0
    .zero 128 - (. - open_proxy_request)
.global get_window_request
get_window_request:
    .word 4, 8, 0, 0, 0x49434653, 0, 2, 0
    .zero 128 - (. - get_window_request)
.global command1_request
command1_request:
    .word 4, 8, 0, 0, 0x49434653, 0, 1, 0
    .zero 128 - (. - command1_request)
.global get_gsv_request
get_gsv_request:
    .word 4, 8, 0, 0, 0x49434653, 0, 2000, 0
    .zero 128 - (. - get_gsv_request)
.global bootstrap_request
bootstrap_request:
    .word 0x14, 0x8000000c, 2, 0xffff8001, 0, 0, 5, 0x80000000
    .zero 128 - (. - bootstrap_request)
.global bind_request
bind_request:
    .word 0x1b, 0x80000000, 2, 0xffff8001
    .zero 128 - (. - bind_request)
.global ready_request
ready_request:
    .word 0x75, 0
    .zero 128 - (. - ready_request)
.global image_init_request
image_init_request:
    .word 0x5ed, 0
    .zero 128 - (. - image_init_request)
.global image_formats_request
image_formats_request:
    .word 0x5ee, 0
    .zero 128 - (. - image_formats_request)
.global open_nvdrv_request
open_nvdrv_request:
    .word 0x58a, 0
    .zero 128 - (. - open_nvdrv_request)
.global gpu_init_request
gpu_init_request:
    .word 0x1a1, 0
    .zero 128 - (. - gpu_init_request)
.global gpu_ready_request
gpu_ready_request:
    .word 0x1a2, 0
    .zero 128 - (. - gpu_ready_request)
.global size_zero_request
size_zero_request:
    .word 0x1c3, 17
    .word 0, 1, 0x0008000f, 0, 7, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0
    .word 0
    .zero 128 - (. - size_zero_request)
.global size_valid_request
size_valid_request:
    .word 0x1c3, 17
    .word 0, 1, 0x0008000f, 0, 7, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0
    .word 1
    .zero 128 - (. - size_valid_request)
.global memory_create_request
memory_create_request:
    .word 0x7f, 3, 0, 8192, 0
    .zero 128 - (. - memory_create_request)
.global memory_bind_request
memory_bind_request:
    .word 0x82, 9, 0, 0, 0, 8192, 0, 0, 0, 0, 0
    .zero 128 - (. - memory_bind_request)
.global image_create_request
image_create_request:
    .word 0x1bd, 18
    .word 0, 1, 0x0008000f, 0, 7, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0
    .word 1, 0
    .zero 128 - (. - image_create_request)
.global pool_create_request
pool_create_request:
    .word 0x14b, 2, 0, 1
    .zero 128 - (. - pool_create_request)
.global display_init_request
display_init_request:
    .word 0x13d, 0
    .zero 128 - (. - display_init_request)
.global open_vi2_request
open_vi2_request:
    .word 0x141, 2, 0x00020000, 3
    .zero 128 - (. - open_vi2_request)
.global register_request
register_request:
    .word 0xd9, 4, 0x584e0001, 0x32495632, 2, 3
    .zero 128 - (. - register_request)
.global open_display_request
open_display_request:
    .word 0x75, 3, 0x61666564, 0x00746c75, 1
    .zero 128 - (. - open_display_request)
.global bind_display_request
bind_display_request:
    .word 0x10b, 4, 0x584e0001, 0x32495632, 0x61666564, 0x00746c75
    .zero 128 - (. - bind_display_request)
.global availability_request
availability_request:
    .word 0xe4, 2, 0x584e0001, 0x32495632
    .zero 128 - (. - availability_request)
.global present_request
present_request:
    .word 0xf5, 24, 0x584e0001, 0x32495632, 0, 0, 0, 0x0008000f, 3
    .zero 128 - (. - present_request)
.global notification_request
notification_request:
    .word 0x01000025, 0, 0, 0, 0
    .zero 128 - (. - notification_request)
.global unbind_display_request
unbind_display_request:
    .word 0x10c, 2, 0x584e0001, 0x32495632
    .zero 128 - (. - unbind_display_request)
.global unregister_request
unregister_request:
    .word 0xda, 2, 0x584e0001, 0x32495632
    .zero 128 - (. - unregister_request)
.global close_display_request
close_display_request:
    .word 0x76, 2, 0x61666564, 0x00746c75
    .zero 128 - (. - close_display_request)
.global pool_destroy_request
pool_destroy_request:
    .word 0x14a, 1, 0
    .zero 128 - (. - pool_destroy_request)
.global image_destroy_request
image_destroy_request:
    .word 0x1be, 1, 0
    .zero 128 - (. - image_destroy_request)
.global memory_destroy_request
memory_destroy_request:
    .word 0x80, 1, 0
    .zero 128 - (. - memory_destroy_request)
.global display_finalize_request
display_finalize_request:
    .word 0x13f, 0
    .zero 128 - (. - display_finalize_request)
.global frame_config
frame_config:
    .word NX2_FRAME_VARIANT, 16, 9
    .word 0xff302010
.if NX2_GPU_PROBE || NX2_FRAME_VARIANT == 0
    .word 0xffe0d0c0
.else
    .word 0xffa050e0
.endif
    .word 0xff0000ff, 0xff00ff00, 0xffff0000, 0xff00ffff
sm_name:
    .asciz "sm:"
line_prefix:
    .ascii "NX2_FRAME "
begin_message:
    .ascii "NX2_FRAME_BEGIN\n"
begin_message_end:
present_begin_message:
    .ascii "NX2_FRAME_PRESENT_BEGIN\n"
present_begin_message_end:
presented_message:
    .ascii "NX2_FRAME_PRESENTED\n"
presented_message_end:
cleanup_begin_message:
    .ascii "NX2_FRAME_CLEANUP_BEGIN\n"
cleanup_begin_message_end:
complete_message:
    .ascii "NX2_FRAME_COMPLETE\n"
complete_message_end:
failure_message:
    .ascii "NX2_FRAME_FAILURE\n"
failure_message_end:
.section .data, "aw"
.balign 16
.global record, live_handles, notification_buffer, notification_guard_before
.global notification_guard_after, line_buffer, image_buffer
record:
    .fill FIELD_COUNT, 4, 0xffffffff
live_handles:
    .zero 32
.balign 16
    .zero 12
notification_guard_before:
    .word 0xa5a5a5a5
notification_buffer:
    .fill 32, 4, 0xa5a5a5a5
notification_guard_after:
    .word 0xa5a5a5a5
.balign 16
line_buffer:
    .zero 96
/* Keep the device-shared backing on separate pages from writable records. */
.balign 4096
image_buffer:
    .zero 8192
.section .note.GNU-stack, "", @progbits
