"""Original NX2 unit tests for guest-log parser; no emulator required."""
import contextlib
import io
import unittest

from assess_eden_guest import assess

GUEST_PREFIX = b"Debug.Emulated <Info> core/hle/kernel/svc/svc_debug_string.cpp:25:OutputDebugString: "
GOOD = GUEST_PREFIX + b"Hola desde un NRO en NeXo 2!\x00\n"
BAD = b"Core <Critical> core/core.cpp:339:Load: Failed to load ROM (Error 35)!\n"


class GuestAssessmentTest(unittest.TestCase):
    def run_assessment(self, good, bad, good_rc=124, bad_rc=1):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            verdict = assess(good, bad, good_rc, bad_rc)
        return verdict, out.getvalue()

    def test_true_guest_svc_with_binary_log_and_rejected_image(self):
        verdict, output = self.run_assessment(
            GOOD + GUEST_PREFIX + b"Contador (.data): 42\n", BAD
        )
        self.assertTrue(verdict)
        self.assertIn("NX2_GOOD_LOG_NUL_BYTES=1", output)
        self.assertIn("NX2_EDEN_GUEST_MARKER_OBSERVED=Contador", output)
        self.assertIn("NX2_EDEN_POSITIVE_DID_NOT_EXIT_NATURALLY", output)

    def test_no_guest_debug_output_is_not_evidence(self):
        result, output = self.run_assessment(b"Initialized kernel\x00", BAD)
        self.assertFalse(result)
        self.assertIn("NX2_EDEN_GUEST_EXECUTION_NOT_VERIFIED", output)

    def test_corrupted_nro_timeout_is_failure(self):
        verdict, output = self.run_assessment(GOOD, b"", bad_rc=137)
        self.assertFalse(verdict)
        self.assertIn("NX2_EDEN_MALFORMED_EXITS_WITHOUT_TIMEOUT=0", output)

    def test_bad_program_crash_without_loader_rejection_is_failure(self):
        verdict, output = self.run_assessment(GOOD, b"Segmentation fault", bad_rc=139)
        self.assertFalse(verdict)
        self.assertIn("NX2_EDEN_MALFORMED_LOADER_DIAGNOSTIC=0", output)

    def test_negative_control_success_exit_is_not_rejection(self):
        result, _ = self.run_assessment(GOOD, BAD, bad_rc=0)
        self.assertFalse(result)

    def test_loader_error_followed_by_crash_is_not_clean_rejection(self):
        for status in (-11, 2, 124, 125, 126, 127, 134, 137, 139, 143):
            with self.subTest(status=status):
                result, _ = self.run_assessment(GOOD, BAD, bad_rc=status)
                self.assertFalse(result)

    def test_host_echo_cannot_supply_guest_or_loader_evidence(self):
        for good, bad in ((b"Fixture echo: Hola desde un NRO en NeXo 2!", BAD),
                          (GOOD, b"Fixture echo: Failed to load ROM (Error 35)!")):
            with self.subTest(good=good, bad=bad):
                result, _ = self.run_assessment(good, bad)
                self.assertFalse(result)

    def test_negative_control_must_not_execute_guest(self):
        result, _ = self.run_assessment(GOOD, BAD + GOOD)
        self.assertFalse(result)

    def test_crypto_probe_assertion_is_reported_separately_from_exit_and_rejection(self):
        diagnostic = (b"Debug <Critical> core/crypto/aes_util.cpp:97:operator(): "
                      b"assert EVP_CipherInit_ex2(ctx->encryption_context)\n")
        result, output = self.run_assessment(GOOD, diagnostic + BAD)
        self.assertTrue(result)
        self.assertIn("NX2_EDEN_MALFORMED_EXECUTION_FAULT=1", output)

    def test_original_return_fault_remains_explicit_partial_evidence(self):
        result, output = self.run_assessment(
            GOOD + b"Core.ARM <Critical> ExceptionRaised: Cannot execute instruction at unmapped address 0x0\n", BAD
        )
        self.assertTrue(result)
        self.assertIn("NX2_EDEN_ORIGINAL_EXECUTION_FAULT=1", output)
        self.assertIn("NX2_EDEN_ORIGINAL_RESULT_IS_EXECUTION_EVIDENCE_ONLY=1", output)

    def test_original_host_crash_is_not_an_accepted_bounded_trial(self):
        result, _ = self.run_assessment(GOOD, BAD, good_rc=139)
        self.assertFalse(result)

    def test_only_late_guest_marker_does_not_prove_guest_start(self):
        result, _ = self.run_assessment(b"fibonacci(50) = 12586269025", BAD)
        self.assertFalse(result)

    def test_no_silent_byte_deletion(self):
        verdict, output = self.run_assessment(
            b"noise\x00\xff\n" + GOOD, BAD
        )
        self.assertTrue(verdict)
        self.assertIn("[NUL]", output)
        self.assertIn("NX2_EDEN_SOURCE_AUTHORED_GUEST_EXECUTION_PASS", output)


if __name__ == "__main__":
    unittest.main()
