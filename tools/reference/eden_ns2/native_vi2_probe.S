/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (c) 2026 nx2-lab contributors.
 * Original ARM64 workload for frozen Eden e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c.
 * This exercises its CMIF/TIPC service model, not hardware ABI or guest pixels.
 * All reply records start as ffffffff and contain observed W0/TLS/memory values.
 */

/* Generate offsets and the compact report-name stream together. A leading '~'
 * expands one array name into 32 decimal-suffixed fields (word00 ... word31).
 */
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
    tipc_fields display_init
    field open_vi2_transport
    field open_vi2_header0
    field open_vi2_header1
    field open_vi2_descriptor
    field vi2_handle
    field open_vi2_result
    tipc_fields register
    tipc_fields duplicate
    tipc_fields unregister
    tipc_fields missing
    notification_fields short
    notification_fields first
    notification_fields clear
    tipc_fields display_finalize
    field close_vi2
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
.if FIELD_COUNT != 215
    .error "VI2 report contract must have 215 fields"
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
    cmp x7, #7
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
.macro tipc_check prefix, command, expected=0
    add x9, x22, #F_\prefix\()_transport
    ldp w0, w1, [x9]
    ldp w2, w3, [x9, #8]
    cbnz w0, failure
    cmp w1, #(16 + \command)
    b.ne failure
    cmp w2, #1
    b.ne failure
    mov w4, #\expected
    cmp w3, w4
    b.ne failure
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
    ldr w0, [x19, #24]
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

_start:
    mrs x21, tpidrro_el0
    address x22, record
    address x19, live_handles
    address x0, begin_message
    mov x1, #(begin_message_end - begin_message)
    svc #0x27

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
    tipc_call display_init_request, 5, display_init, 301

    step 13
    prepare open_vi2_request
    ldr w0, [x19, #20]
    svc #0x21
    str w0, [x22, #F_open_vi2_transport]
    ldp w1, w2, [x21]
    str w1, [x22, #F_open_vi2_header0]
    str w2, [x22, #F_open_vi2_header1]
    ldr w3, [x21, #8]
    str w3, [x22, #F_open_vi2_descriptor]
    ldr w6, [x21, #12]
    str w6, [x22, #F_vi2_handle]
    ldr w5, [x21, #16]
    str w5, [x22, #F_open_vi2_result]
    cbnz w0, failure
    cmp w1, #0x141
    b.ne failure
    mov w7, #0x80000001
    cmp w2, w7
    b.ne failure
    cmp w3, #0x20
    b.ne failure
    admit 6
    cbnz w5, failure

    step 14
    tipc_call register_request, 6, register, 201
    step 15
    tipc_call register_request, 6, duplicate, 201, 0xfa01
    step 16
    tipc_call unregister_request, 6, unregister, 202
    step 17
    tipc_call unregister_request, 6, missing, 202, 0xf201

    step 18
    notification_call short, 127, 0xca01, 0xa5a5a5a5, 0xa5a5a5a5
    step 19
    notification_call first, 128, 0, 4, 0
    step 20
    notification_call clear, 128, 0, 0, 0
    step 21
    tipc_call display_finalize_request, 5, display_finalize, 303
    str wzr, [x22, #F_fail_step]
    b cleanup

/* Clear only the 0x100-byte IPC area; retain the remainder of the guest TLS. */
prepare_request:
    mov x2, x21
    mov w3, #16
1:  stp xzr, xzr, [x2], #16
    subs w3, w3, #1
    b.ne 1b
    mov x2, x21
    mov w3, #4
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
    /* Keep the first failed service step; cleanup never creates COMPLETE. */
cleanup:
    mov x23, #6
    add x24, x22, #F_close_vi2
    mov w25, #22
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
    add x2, x25, #8
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
/* Templates are 64 bytes each, authored for the frozen public source model.
 * PID=0 slots are overwritten by the kernel. CurrentProcess=ffff8001 is copied,
 * not acquired as an owned handle. No CMIF domain conversion is performed.
 */
.global sm_initialize_request, get_applet_request, open_proxy_request
.global get_window_request, command1_request, get_gsv_request
.global bootstrap_request, bind_request, ready_request, display_init_request
.global open_vi2_request, register_request, unregister_request
.global notification_request, display_finalize_request
sm_initialize_request:
    .word 4, 0x8000000a, 1, 0, 0, 0, 0, 0
    .word 0x49434653, 0, 0, 0, 0, 0, 0, 0
get_applet_request:
    .word 4, 10, 0, 0, 0x49434653, 0, 1, 0
    .ascii "appletOE"
    .zero 24
open_proxy_request:
    .word 4, 0x8000000a, 3, 0, 0, 0xffff8001, 0, 0
    .word 0x49434653, 0, 0, 0, 0, 0, 0, 0
get_window_request:
    .word 4, 8, 0, 0, 0x49434653, 0, 2, 0
    .zero 32
command1_request:
    .word 4, 8, 0, 0, 0x49434653, 0, 1, 0
    .zero 32
get_gsv_request:
    .word 4, 8, 0, 0, 0x49434653, 0, 2000, 0
    .zero 32
bootstrap_request:
    .word 0x14, 0x8000000c, 2, 0xffff8001
    .word 0, 0, 5, 0x80000000
    .zero 32
bind_request:
    .word 0x1b, 0x80000000, 2, 0xffff8001
    .zero 48
ready_request:
    .word 0x75, 0
    .zero 56
display_init_request:
    .word 0x13d, 0
    .zero 56
open_vi2_request:
    .word 0x141, 2, 0x00020000, 3
    .zero 48
register_request:
    .word 0xd9, 4, 0x584e0001, 0x32495632, 2, 3
    .zero 40
unregister_request:
    .word 0xda, 2, 0x584e0001, 0x32495632
    .zero 48
notification_request:
    .word 0x01000025, 0, 0, 0, 0
    .zero 44
display_finalize_request:
    .word 0x13f, 0
    .zero 56
sm_name:
    .asciz "sm:"
line_prefix:
    .ascii "NX2_VI2 "
begin_message:
    .ascii "NX2_VI2_BEGIN\n"
begin_message_end:
complete_message:
    .ascii "NX2_VI2_COMPLETE\n"
complete_message_end:
failure_message:
    .ascii "NX2_VI2_FAILURE\n"
failure_message_end:

.section .data, "aw"
.balign 16
.global record, live_handles, notification_buffer, notification_guard_before
.global notification_guard_after, line_buffer
record:
    .fill FIELD_COUNT, 4, 0xffffffff
live_handles:
    .zero 28
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
    .zero 64
.section .note.GNU-stack, "", @progbits
