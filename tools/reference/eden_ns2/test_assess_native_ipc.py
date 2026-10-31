# SPDX-License-Identifier: MIT
"""Reject false IPC evidence, wrong replies and incomplete guest cleanup."""
import contextlib
import io
import unittest
from unittest.mock import patch

import assess_native_ipc
from assess_native_ipc import assess


CLASSIFIED = (b"[   0.022450] Core <Info> core/core.cpp:321:Load: "
              b"Switch 2 program: using the 12 GiB memory layout\n")
PREFIX = (b"[   0.753159] Debug.Emulated <Info> "
          b"core/hle/kernel/svc/svc_debug_string.cpp:25:OutputDebugString: ")
EXIT = (b"[   0.753189] Kernel.SVC <Info> "
        b"core/hle/kernel/svc/svc_process.cpp:17:ExitProcess: Process 81 exiting\n")
# Independent fixture spells out actual wire values rather than importing the
# assessor's expected-value table and thereby repeating any table error.
FIELDS = (
    b"connect_rc=00000000", b"sm_handle=02008001",
    b"init_transport=00000000", b"init_magic=4f434653", b"init_result=00000000",
    b"init_header=0000000a", b"init_descriptor=00000000",
    b"get_transport=00000000", b"get_magic=4f434653", b"get_result=00000000",
    b"get_header=8000000a", b"get_descriptor=00000020", b"service_handle=02108002",
    b"invalid_transport=00000000", b"invalid_magic=4f434653", b"invalid_result=00000c15",
    b"invalid_header=0000000a", b"invalid_descriptor=00000000",
    b"close_service=00000000", b"close_sm=00000000", b"fail_step=00000000",
)
RECORDS = b"".join(PREFIX + b"NX2_IPC " + field + b"\n" for field in FIELDS)
COMPLETE = PREFIX + b"NX2_IPC_COMPLETE\n"
GOOD = CLASSIFIED + RECORDS + COMPLETE + EXIT


class NativeIpcAssessmentTests(unittest.TestCase):
    def run_case(self, log=GOOD, status=0):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = assess(log, status)
        return result, output.getvalue()

    def test_observed_sm_replies_handles_negative_result_and_cleanup(self):
        ok, output = self.run_case()
        self.assertTrue(ok)
        self.assertIn("NX2_NATIVE_IPC_FIELD_COUNT=21", output)
        self.assertIn("NX2_NATIVE_IPC_OBSERVED_INVALID_RESULT=00000c15", output)
        self.assertIn("NX2_NATIVE_IPC_CLASSIFY_COMPLETE_EXIT_IN_ORDER=1", output)

    def test_every_field_is_required_and_must_be_unique(self):
        for field in FIELDS:
            line = PREFIX + b"NX2_IPC " + field + b"\n"
            with self.subTest(field=field, missing=True):
                self.assertFalse(self.run_case(GOOD.replace(line, b"", 1))[0])
            with self.subTest(field=field, duplicate=True):
                self.assertFalse(self.run_case(GOOD.replace(line, line + line, 1))[0])

    def test_transport_and_service_results_cannot_be_fabricated_as_success(self):
        for field in (b"connect_rc", b"init_transport", b"init_result", b"get_transport",
                      b"get_result", b"invalid_transport", b"close_service", b"close_sm",
                      b"fail_step"):
            with self.subTest(field=field):
                self.assertFalse(self.run_case(GOOD.replace(field + b"=00000000",
                                                           field + b"=00000001"))[0])

    def test_sfco_magic_is_required_for_each_reply(self):
        for field in (b"init_magic", b"get_magic", b"invalid_magic"):
            with self.subTest(field=field):
                self.assertFalse(self.run_case(GOOD.replace(field + b"=4f434653",
                                                           field + b"=49434653"))[0])

    def test_moved_handle_requires_exact_hipc_special_header_and_descriptor(self):
        for before, after in ((b"get_header=8000000a", b"get_header=0000000a"),
                              (b"get_header=8000000a", b"get_header=8000000b"),
                              (b"get_descriptor=00000020", b"get_descriptor=00000002"),
                              (b"get_descriptor=00000020", b"get_descriptor=00000040")):
            with self.subTest(after=after):
                self.assertFalse(self.run_case(GOOD.replace(before, after))[0])

    def test_negative_empty_name_must_be_c15_without_moved_handle(self):
        for before, after in ((b"invalid_result=00000c15", b"invalid_result=00000000"),
                              (b"invalid_header=0000000a", b"invalid_header=8000000a"),
                              (b"invalid_descriptor=00000000", b"invalid_descriptor=00000020")):
            with self.subTest(after=after):
                self.assertFalse(self.run_case(GOOD.replace(before, after))[0])

    def test_handles_must_be_observed_nonzero_and_distinct(self):
        for before, after in ((b"sm_handle=02008001", b"sm_handle=00000000"),
                              (b"sm_handle=02008001", b"sm_handle=ffffffff"),
                              (b"service_handle=02108002", b"service_handle=00000000"),
                              (b"service_handle=02108002", b"service_handle=ffffffff"),
                              (b"service_handle=02108002", b"service_handle=02008001")):
            with self.subTest(after=after):
                self.assertFalse(self.run_case(GOOD.replace(before, after))[0])

    def test_guest_failure_marker_is_fatal_even_after_complete(self):
        for failure in (PREFIX + b"NX2_IPC_FAILURE\n", b"NX2_IPC_FAILURE\n"):
            with self.subTest(failure=failure):
                self.assertFalse(self.run_case(GOOD + failure)[0])

    def test_timeout_crash_or_nonzero_process_status_cannot_pass(self):
        for status in (-11, -9, 1, 2, 124, 125, 126, 127, 134, 137, 139, 143):
            with self.subTest(status=status):
                self.assertFalse(self.run_case(status=status)[0])

    def test_real_exit_after_complete_is_required(self):
        for log in (CLASSIFIED + RECORDS + COMPLETE,
                    CLASSIFIED + RECORDS + EXIT + COMPLETE,
                    CLASSIFIED + COMPLETE + RECORDS + EXIT,
                    CLASSIFIED + RECORDS + COMPLETE + EXIT + EXIT):
            with self.subTest(log=log[-250:]):
                self.assertFalse(self.run_case(log)[0])

    def test_native_classification_must_precede_guest_records(self):
        for log in (RECORDS + COMPLETE + EXIT,
                    RECORDS + CLASSIFIED + COMPLETE + EXIT,
                    CLASSIFIED + GOOD):
            with self.subTest(log=log[:200]):
                self.assertFalse(self.run_case(log)[0])

    def test_plain_host_echo_or_embedded_source_tags_cannot_supply_evidence(self):
        for log in (GOOD.replace(PREFIX, b"Fixture echo: "),
                    GOOD.replace(PREFIX, b"Fixture echo: " + PREFIX),
                    GOOD.replace(b"Core <Info>", b"Fixture Core <Info>"),
                    GOOD.replace(b"Kernel.SVC <Info>", b"Fixture Kernel.SVC <Info>"),
                    GOOD + b"NX2_IPC connect_rc=00000000\n"):
            with self.subTest(log=log[:100]):
                self.assertFalse(self.run_case(log)[0])

    def test_wrong_source_file_cannot_supply_guest_records(self):
        self.assertFalse(self.run_case(GOOD.replace(b"svc_debug_string.cpp", b"fixture_echo.cpp"))[0])

    def test_exact_field_spelling_width_case_and_order_are_required(self):
        for before, after in ((b"connect_rc=00000000", b"connect_rc=0"),
                              (b"connect_rc=00000000", b"connect_rc=000000000"),
                              (b"connect_rc=00000000", b"connect_rc=0x00000000"),
                              (b"get_magic=4f434653", b"get_magic=4F434653"),
                              (b"connect_rc=00000000", b"unexpected=00000000"),
                              (b"connect_rc=00000000", b"connect_rc=0000\x000000"),
                              (b"connect_rc=00000000", b"connect_rc=00000000 trailing")):
            with self.subTest(after=after):
                self.assertFalse(self.run_case(GOOD.replace(before, after))[0])
        first, second = (PREFIX + b"NX2_IPC " + field + b"\n" for field in FIELDS[:2])
        self.assertFalse(self.run_case(GOOD.replace(first + second, second + first))[0])

    def test_complete_is_required_once_and_must_be_guest_authored(self):
        for log in (GOOD.replace(COMPLETE, b""), GOOD.replace(COMPLETE, COMPLETE * 2),
                    GOOD.replace(COMPLETE, b"NX2_IPC_COMPLETE\n")):
            with self.subTest(log=log[-200:]):
                self.assertFalse(self.run_case(log)[0])

    def test_assertions_faults_and_real_auto_stub_diagnostics_reject_success(self):
        for diagnostic in (
            b"Debug <Critical> core/hle/kernel/k_thread.cpp:140: assert (priority)",
            b"ExceptionRaised(exception=UndefinedInstruction)",
            b"Cannot execute instruction at unmapped address 0x0",
            b"Segmentation fault", b"AddressSanitizer: heap-buffer-overflow",
            b"UndefinedBehaviorSanitizer", b"runtime error: misaligned access",
            b"Service <Warning> Using auto stub fallback!",
            b"Debug <Critical> Unknown / unimplemented GetService",
        ):
            with self.subTest(diagnostic=diagnostic):
                self.assertFalse(self.run_case(GOOD + diagnostic + b"\n")[0])

    def test_expected_invalid_service_name_error_is_not_an_execution_fault(self):
        log = GOOD.replace(COMPLETE, b"Service.SM <Error> Invalid service name!\n" + COMPLETE)
        self.assertTrue(self.run_case(log)[0])

    def test_binary_safe_logs_preserve_real_records_and_visible_nul_diagnostics(self):
        raw = b"noise\xff\0\n" + b"".join(
            b"\0\x1b[0;37m" + line + b"\0\x1b[0m\n" for line in GOOD.splitlines()
        )
        ok, output = self.run_case(raw)
        self.assertTrue(ok)
        self.assertIn("[NUL]", output)
        self.assertNotIn("\x1b", output)

    def test_oversize_input_is_refused_before_parsing(self):
        with patch.object(assess_native_ipc, "MAX_LOG_SIZE", 16):
            ok, output = self.run_case()
        self.assertFalse(ok)
        self.assertIn("NX2_NATIVE_IPC_LOG_LIMIT_EXCEEDED", output)


if __name__ == "__main__":
    unittest.main()
