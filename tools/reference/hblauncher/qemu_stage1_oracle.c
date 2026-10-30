/*
 * Independent QEMU-AArch64 oracle for unchanged HBLauncher Hello CPU stage 1.
 * Build this with the EXACT original app_c.o and SDK runtime objects emitted
 * by HBLauncher's pinned hbx-build.py. No copied upstream implementation.
 * This invokes the external hbx_app_main compiled code, not an NX2 mock.
 * HBX is a launcher-defined ABI, not Nintendo Horizon.
 */
#include "hbx_sdk.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int check_case(const char *name, int change, int expected) {
    struct hbx_ctx context;
    memset(&context, 0, sizeof context);
    context.magic = HBX_ABI_MAGIC;
    context.abi_version = HBX_ABI_VERSION;
    context.size = sizeof context;
    context.args[1] = 1; /* Original app's source-defined early-return stage */
    switch (change) {
    case 1: context.magic ^= 1u; break;
    case 2: context.abi_version = HBX_ABI_VERSION + 1u; break;
    case 3: context.size = sizeof context - 8u; break;
    default: break;
    }
    const int actual = hbx_app_main(&context);
    if (actual != expected) {
        fprintf(stderr, "HBX_QEMU_ORACLE_REFUSED:%s:%d:%d\n",
                name, actual, expected);
        return 1;
    }
    printf("hbx_original_%s_ret=%d\n", name, actual);
    return 0;
}

int main(void) {
    if (check_case("valid", 0, HBX_OK) != 0 ||
        check_case("bad_magic", 1, HBX_ERR_ABI) != 0 ||
        check_case("bad_version", 2, HBX_ERR_ABI) != 0 ||
        check_case("bad_size", 3, HBX_ERR_ABI) != 0) {
        return 1;
    }
    puts("HBX_QEMU_ORIGINAL_STAGE1_ORACLE_PASS");
    puts("upstream_app_object=unchanged_hbx_build_output");
    puts("horizon_services_executed=0");
    return 0;
}
