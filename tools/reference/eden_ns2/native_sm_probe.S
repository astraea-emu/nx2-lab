/* SPDX-License-Identifier: GPL-3.0-only
 * Earlier MIT-licensed material retains that permission; see LICENSES/MIT.txt.
 * Original NX2 ARM64 service-manager probe, no SDK or console code.
 * Request format independently checked with public libnx cmifMakeRequest at
 * b156b4774fb2df7b93402169509266da7547fc4c. Expected replies describe frozen
 * Eden e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c, not hardware conformance.
 */
.section .text, "ax"
.global _start
.equ FAIL_STEP, 80

.macro step number
    mov w0, #\number
    str w0, [x22, #FAIL_STEP]
.endm

/* Save the actual transport result and fields read back from guest TLS. */
.macro capture offset
    str w0, [x22, #\offset]
    ldr w1, [x21, #0x10]
    str w1, [x22, #(\offset + 4)]
    ldr w2, [x21, #0x18]
    str w2, [x22, #(\offset + 8)]
    ldr w3, [x21, #4]
    str w3, [x22, #(\offset + 12)]
    ldr w4, [x21, #8]
    str w4, [x22, #(\offset + 16)]
.endm

.macro check_reply result, moved
    cbnz w0, failure
    mov w5, #0x4653
    movk w5, #0x4f43, lsl #16
    cmp w1, w5
    b.ne failure
    cmp w2, #\result
    b.ne failure
    mov w5, #10
.if \moved
    orr w5, w5, #0x80000000
.endif
    cmp w3, w5
    b.ne failure
    cmp w4, #(\moved * 0x20)
    b.ne failure
.endm

_start:
    mov x19, #0
    mov x20, #0
    mrs x21, tpidrro_el0
    adrp x22, record
    add x22, x22, :lo12:record

    step 1
    adrp x1, sm_name
    add x1, x1, :lo12:sm_name
    svc #0x1f
    str w0, [x22, #0]
    str w1, [x22, #4]
    cbnz w0, failure
    cbz w1, failure
    mov w19, w1

    step 2
    adrp x0, initialize_request
    add x0, x0, :lo12:initialize_request
    bl prepare_request
    mov w0, w19
    svc #0x21
    capture 8
    check_reply 0, 0

    step 3
    adrp x0, get_service_request
    add x0, x0, :lo12:get_service_request
    bl prepare_request
    mov w0, w19
    svc #0x21
    capture 28
    ldr w6, [x21, #0x0c]
    str w6, [x22, #48]
    check_reply 0, 1
    cbz w6, failure
    cmp w6, w19
    b.eq failure
    mov w20, w6

    step 4
    adrp x0, invalid_name_request
    add x0, x0, :lo12:invalid_name_request
    bl prepare_request
    mov w0, w19
    svc #0x21
    capture 52
    check_reply 0xc15, 0

    step 5
    mov w0, w20
    svc #0x16
    str w0, [x22, #72]
    mov x20, #0
    cbnz w0, failure

    step 6
    mov w0, w19
    svc #0x16
    str w0, [x22, #76]
    mov x19, #0
    cbnz w0, failure
    str wzr, [x22, #FAIL_STEP]
    b report

/* Clear only the 0x100-byte IPC area, preserving the rest of TLS. Copy one
 * complete, independently checked 64-byte original request template. */
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

failure:
    /* Close only handles we admitted. Keep the first failing step intact. */
    cbz x20, 1f
    mov w0, w20
    svc #0x16
    str w0, [x22, #72]
1:  cbz x19, report
    mov w0, w19
    svc #0x16
    str w0, [x22, #76]

report:
    adrp x23, field_names
    add x23, x23, :lo12:field_names
    mov x24, #0
    adrp x25, line_buffer
    add x25, x25, :lo12:line_buffer
1:  adrp x2, line_prefix
    add x2, x2, :lo12:line_prefix
    ldr x3, [x2]
    str x3, [x25]
    add x2, x25, #8
2:  ldrb w3, [x23], #1
    cbz w3, 3f
    strb w3, [x2], #1
    b 2b
3:  mov w3, #'='
    strb w3, [x2], #1
    ldr w4, [x22, x24, lsl #2]
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
    add x24, x24, #1
    cmp x24, #21
    b.ne 1b

    ldr w0, [x22, #FAIL_STEP]
    cbnz w0, 1f
    adrp x0, complete_message
    add x0, x0, :lo12:complete_message
    mov x1, #(complete_message_end - complete_message)
    b 2f
1:  adrp x0, failure_message
    add x0, x0, :lo12:failure_message
    mov x1, #(failure_message_end - failure_message)
2:  svc #0x27
    svc #0x7
3:  b 3b

.section .rodata, "a"
.balign 16
.global initialize_request, get_service_request, invalid_name_request, field_names
initialize_request:
    .word 4, 0x8000000a, 1, 0, 0, 0, 0, 0
    .word 0x49434653, 0, 0, 0, 0, 0, 0, 0
get_service_request:
    .word 4, 10, 0, 0, 0x49434653, 0, 1, 0
    .ascii "set\0\0\0\0\0"
    .zero 24
invalid_name_request:
    .word 4, 10, 0, 0, 0x49434653, 0, 1, 0
    .zero 32
sm_name:
    .asciz "sm:"
line_prefix:
    .ascii "NX2_IPC "
complete_message:
    .ascii "NX2_IPC_COMPLETE\n"
complete_message_end:
failure_message:
    .ascii "NX2_IPC_FAILURE\n"
failure_message_end:
field_names:
    .asciz "connect_rc", "sm_handle"
    .asciz "init_transport", "init_magic", "init_result", "init_header", "init_descriptor"
    .asciz "get_transport", "get_magic", "get_result", "get_header", "get_descriptor", "service_handle"
    .asciz "invalid_transport", "invalid_magic", "invalid_result", "invalid_header", "invalid_descriptor"
    .asciz "close_service", "close_sm", "fail_step"

.section .data, "aw"
.balign 16
.global record, line_buffer
record:
    .fill 21, 4, 0xffffffff
.balign 16
line_buffer:
    .zero 64
.section .note.GNU-stack, "", @progbits
