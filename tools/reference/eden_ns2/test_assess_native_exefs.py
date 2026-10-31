# SPDX-License-Identifier: MIT
"""Acceptance regressions for observed Eden runtime false-positive cases."""
import contextlib
import io
import unittest

from assess_native_exefs import assess, MESSAGE

CLASSIFICATION = (
    b"Core <Info> core/core.cpp:321:Load: "
    b"Switch 2 program: using the 12 GiB memory layout\n"
)
OUTPUT = (
    b"Debug.Emulated <Info> core/hle/kernel/svc/svc_debug_string.cpp:25:"
    b"OutputDebugString: " + MESSAGE.encode() + b"\x00\n"
)
EXIT = (
    b"Kernel.SVC <Info> core/hle/kernel/svc/svc_process.cpp:17:"
    b"ExitProcess: Process 81 exiting\n"
)
GOOD = CLASSIFICATION + OUTPUT + EXIT
CORE_REJECTION = (
    b"Core <Critical> core/core.cpp:339:Load: Failed to load ROM (Error 4)!\n"
)
FRONTEND_REJECTION = (
    b"Frontend <Critical> yuzu_cmd/yuzu.cpp:402:SDL_AppInit: "
    b"While attempting to load the ROM requested, an error occurred. Please "
    b"refer to the Eden wiki for more information or the Eden discord for "
    b"additional help.\n\nError Code: 0007-0004\nError Description: 4\n"
)
BAD = CORE_REJECTION + FRONTEND_REJECTION
PRIORITY_ASSERT = (
    b"Debug <Critical> core/hle/kernel/k_thread.cpp:140:operator(): "
    b"/tmp/eden/src/core/hle/kernel/k_thread.cpp: assert "
    b"((owner->GetPriorityMask() | (1ULL << prio)) == owner->GetPriorityMask())\n"
)


class NativeExeFsAssessmentTests(unittest.TestCase):
    def run_case(self, g=GOOD, b=BAD, grc=0, brc=1):
        with contextlib.redirect_stdout(io.StringIO()) as cap:
            success = assess(g, b, grc, brc)
        return success, cap.getvalue()

    def test_guest_classification_output_exit_and_expected_rejection(self):
        ok, report = self.run_case()
        self.assertTrue(ok)
        self.assertIn("NX2_NATIVE_GUEST_EXIT_SVC_IN_ORDER=1", report)
        self.assertIn("NX2_NATIVE_GUEST_PROCESS_EXIT_SUCCESS=1", report)

    def test_actual_first_trial_cannot_pass_after_negative_is_fixed(self):
        # First trial printed the message after a priority assertion and timed out.
        ok, report = self.run_case(g=CLASSIFICATION + PRIORITY_ASSERT + OUTPUT + EXIT,
                                   grc=124)
        self.assertFalse(ok)
        self.assertIn("NX2_NATIVE_GUEST_EXECUTION_FAULT_SEEN=1", report)

    def test_positive_timeout_crash_or_failure_never_qualifies(self):
        for rc in (1, 124, 126, 127, 134, 137, 139, -9, -11):
            with self.subTest(rc=rc):
                self.assertFalse(self.run_case(grc=rc)[0])

    def test_assertion_or_fault_rejects_even_successful_exit(self):
        for fault in (PRIORITY_ASSERT, b"Cannot execute instruction at unmapped address",
                      b"ExceptionRaised(exception=UndefinedInstruction)",
                      b"Segmentation fault", b"AddressSanitizer: heap-buffer-overflow",
                      b"UndefinedBehaviorSanitizer", b"runtime error: bad access"):
            with self.subTest(fault=fault):
                self.assertFalse(self.run_case(g=GOOD + fault)[0])

    def test_plain_host_echo_is_not_guest_execution(self):
        self.assertFalse(self.run_case(g=GOOD.replace(
            b"core/hle/kernel/svc/svc_debug_string.cpp:25:", b"Fixture print: "))[0])

    def test_host_prefixed_full_source_records_cannot_satisfy_positive_events(self):
        for event in (CLASSIFICATION, OUTPUT, EXIT):
            for prefix in (b"host echo: ", b"host echo: [   0.712979] "):
                with self.subTest(event=event, prefix=prefix):
                    self.assertFalse(self.run_case(g=GOOD.replace(event, prefix + event))[0])

    def test_positive_interior_nul_cannot_hide_a_host_prefix_or_join_tokens(self):
        for event in (CLASSIFICATION, OUTPUT, EXIT):
            for corrupted in (b"host echo:\0" + event,
                              event.replace(b": ", b": \0", 1)):
                with self.subTest(event=event, corrupted=corrupted):
                    self.assertFalse(self.run_case(g=GOOD.replace(event, corrupted))[0])

    def test_each_positive_source_event_must_be_unique(self):
        for event in (CLASSIFICATION, OUTPUT, EXIT):
            with self.subTest(event=event):
                self.assertFalse(self.run_case(g=GOOD + event)[0])

    def test_positive_timestamps_ansi_and_boundary_nul_are_accepted(self):
        good = b"".join(b"\0\x1b[0;37m[   0.712979] " + event + b"\x1b[0m"
                        for event in (CLASSIFICATION, OUTPUT, EXIT))
        self.assertTrue(self.run_case(g=good)[0])

    def test_missing_or_host_echoed_classification_fails(self):
        self.assertFalse(self.run_case(g=OUTPUT + EXIT)[0])
        self.assertFalse(self.run_case(g=GOOD.replace(b"core/core.cpp:321:Load: ", b""))[0])

    def test_loader_only_is_not_guest_execution(self):
        self.assertFalse(self.run_case(g=CLASSIFICATION)[0])

    def test_clean_exit_without_guest_exit_svc_is_insufficient(self):
        self.assertFalse(self.run_case(g=CLASSIFICATION + OUTPUT)[0])
        self.assertFalse(self.run_case(g=GOOD.replace(b"Kernel.SVC", b"Host echo"))[0])

    def test_execution_events_must_be_ordered(self):
        self.assertFalse(self.run_case(g=CLASSIFICATION + EXIT + OUTPUT)[0])

    def test_negative_must_exit_with_expected_sdl_failure(self):
        for rc in (0, 2, 124, 126, 127, 134, 137, 139, -9, -11):
            with self.subTest(rc=rc):
                self.assertFalse(self.run_case(brc=rc)[0])

    def test_negative_needs_specific_npdm_failure_not_unrelated_error(self):
        for log in (b"", b"Segmentation fault", b"Failed to initialize VideoCore!",
                    b"Error Description: unrelated failure",
                    BAD.replace(b"core/core.cpp:339:Load: ", b"")):
            with self.subTest(log=log):
                self.assertFalse(self.run_case(b=log)[0])

    def test_observed_numeric_npdm_diagnostic_is_accepted(self):
        ok, report = self.run_case()
        self.assertTrue(ok)
        self.assertIn("NX2_NATIVE_INVALID_EXPLICIT_DIAGNOSTIC=1", report)

    def test_exact_english_npdm_description_is_accepted_with_typed_tuple(self):
        bad = BAD.replace(b"Error Description: 4",
                          b"Error Description: The NPDM file has a bad header.")
        self.assertTrue(self.run_case(b=bad)[0])

    def test_negative_error_ids_and_description_must_agree(self):
        for old, new in ((b"(Error 4)", b"(Error 9)"),
                         (b"0007-0004", b"0007-0005"),
                         (b"0007-0004", b"0006-0004"),
                         (b"Description: 4", b"Description: 5"),
                         (b"Description: 4", b"Description: 40"),
                         (b"Description: 4", b"Description: The NPDM has a bad ACID header.")):
            with self.subTest(old=old, new=new):
                self.assertFalse(self.run_case(b=BAD.replace(old, new))[0])

    def test_negative_diagnostic_needs_both_sources_and_complete_block(self):
        for bad in (CORE_REJECTION, FRONTEND_REJECTION,
                    CORE_REJECTION + b"Error Code: 0007-0004\nError Description: 4\n",
                    CORE_REJECTION + b"Error Description: The NPDM file has a bad header.\n",
                    BAD.replace(b"\nError Code: 0007-0004", b""),
                    BAD.replace(b"\nError Description: 4", b""),
                    BAD.replace(b"additional help.\n\n", b"additional help.\n"),
                    BAD.replace(b"Error Description: 4", b"unrelated record\nError Description: 4")):
            with self.subTest(bad=bad):
                self.assertFalse(self.run_case(b=bad)[0])

    def test_negative_host_echoes_do_not_qualify_as_source_records(self):
        for bad in (b"host echo: " + BAD,
                    BAD.replace(b"Frontend <Critical>", b"host echo: Frontend <Critical>"),
                    BAD.replace(b"yuzu_cmd/yuzu.cpp:402:SDL_AppInit: ", b""),
                    BAD.replace(b"Error Code: 0007-0004", b"host echo: Error Code: 0007-0004"),
                    BAD.replace(b"Error Description: 4", b"host echo: Error Description: 4")):
            with self.subTest(bad=bad):
                self.assertFalse(self.run_case(b=bad)[0])

    def test_negative_rejection_records_must_be_unique_and_ordered(self):
        for bad in (FRONTEND_REJECTION + CORE_REJECTION,
                    CORE_REJECTION + BAD, BAD + FRONTEND_REJECTION):
            with self.subTest(bad=bad):
                self.assertFalse(self.run_case(b=bad)[0])

    def test_negative_actual_logger_timestamp_ansi_and_boundary_nul_are_accepted(self):
        bad = (b"\x1b[0;31m[   0.156897] " + CORE_REJECTION + b"\x1b[0m\0"
               b"\x1b[0;31m[   0.182388] " + FRONTEND_REJECTION + b"\x1b[0m\0")
        self.assertTrue(self.run_case(b=bad)[0])

    def test_negative_interior_nul_cannot_join_diagnostic_tokens(self):
        self.assertFalse(self.run_case(b=BAD.replace(b"0007-0004", b"0007-\0\n0004"))[0])
        self.assertFalse(self.run_case(b=BAD.replace(b"Error 4", b"Error \0" + b"4"))[0])

    def test_negative_diagnostic_followed_by_crash_or_assertion_fails(self):
        self.assertFalse(self.run_case(b=BAD + b"Segmentation fault", brc=139)[0])
        self.assertFalse(self.run_case(b=BAD + PRIORITY_ASSERT)[0])

    def test_invalid_metadata_cannot_execute_guest_before_rejection(self):
        self.assertFalse(self.run_case(b=BAD + OUTPUT)[0])
        self.assertFalse(self.run_case(b=BAD + EXIT)[0])

    def test_ansi_and_nul_noise_preserves_actual_source_log_records(self):
        ok, report = self.run_case(g=b"noise\0\n\x1b[0;37m" + GOOD + b"\x1b[0m")
        self.assertTrue(ok)
        self.assertIn("[NUL]", report)
        self.assertNotIn("\x1b", report)


if __name__ == "__main__":
    unittest.main()
