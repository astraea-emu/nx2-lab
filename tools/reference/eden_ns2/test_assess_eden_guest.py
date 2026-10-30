"""Original NX2 unit tests for guest-log parser; no emulator required."""
import contextlib
import io
import unittest

from assess_eden_guest import assess

GOOD = b"Debug_Emulated: Hola desde un NRO en NeXo 2!\x00\n"
BAD = b"Frontend: Failed to obtain loader for bad-magic.nro!\n"


class GuestAssessmentTest(unittest.TestCase):
    def run_assessment(self, good, bad, good_rc=124, bad_rc=1):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            verdict = assess(good, bad, good_rc, bad_rc)
        return verdict, out.getvalue()

    def test_true_guest_svc_with_binary_log_and_rejected_image(self):
        verdict, output = self.run_assessment(
            GOOD + b"Contador (.data): 42\n", BAD
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
