"""Regress the real exit-lifecycle failure modes without rebuilding Eden."""
import contextlib
import io
import unittest

from assess_adapted_nro import assess

PREFIX = b"Debug.Emulated <Info> core/hle/kernel/svc/svc_debug_string.cpp:25:OutputDebugString: "
MESSAGES = (
    b"Hola desde un NRO en NeXo 2!",
    b"Contador (.data): 42",
    b"Suma en el heap: 499500",
    b"fibonacci(50) = 12586269025",
    b"Adios! (main devuelve -> svcExitProcess)",
)
COMPUTATION = b"".join(PREFIX + message + b"\x00\n" for message in MESSAGES)
EXIT = b"Kernel.SVC <Info> core/hle/kernel/svc/svc_process.cpp:17:ExitProcess: Process 81 exiting\n"
GOOD = COMPUTATION + EXIT


class AdaptedNroAssessmentTest(unittest.TestCase):
    def run_case(self, raw=GOOD, status=0):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            verdict = assess(raw, status)
        return verdict, output.getvalue()

    def test_computations_real_svc_and_natural_exit_pass(self):
        result, output = self.run_case()
        self.assertTrue(result)
        self.assertIn("NX2_ADAPTED_EXIT_PROCESS_SVC=1", output)
        self.assertIn("NX2_ADAPTED_NATURAL_EXIT=1", output)
        self.assertIn("NX2_ADAPTED_EXECUTION_FAULT=0", output)

    def test_exit_svc_followed_by_timeout_or_crash_fails(self):
        for status in (-11, 1, 2, 124, 125, 126, 127, 134, 137, 139, 143):
            with self.subTest(status=status):
                result, _ = self.run_case(status=status)
                self.assertFalse(result)

    def test_guest_goodbye_does_not_prove_exit_svc(self):
        result, output = self.run_case(COMPUTATION)
        self.assertFalse(result)
        self.assertIn("NX2_ADAPTED_EXIT_PROCESS_SVC=0", output)

    def test_host_authored_echo_cannot_prove_guest_computation(self):
        result, _ = self.run_case(GOOD.replace(PREFIX, b"Fixture echo: "))
        self.assertFalse(result)

    def test_host_authored_echo_cannot_prove_exit_svc(self):
        result, _ = self.run_case(COMPUTATION + b"Fixture echo: ExitProcess: Process 81 exiting\n")
        self.assertFalse(result)

    def test_incomplete_or_wrong_computation_fails(self):
        for original, replacement in ((b"499500", b"499501"),
                                      (b"12586269025", b"12586269026"),
                                      (MESSAGES[-1], b"interrupted")):
            with self.subTest(original=original):
                result, _ = self.run_case(GOOD.replace(original, replacement))
                self.assertFalse(result)

    def test_exit_must_follow_final_guest_message(self):
        result, _ = self.run_case(EXIT + COMPUTATION)
        self.assertFalse(result)

    def test_guest_fault_or_assertion_is_failure_even_with_exit_zero(self):
        for diagnostic in (
            b"Core.ARM <Critical> ExceptionRaised: Cannot execute instruction at unmapped address 0x0",
            b"Debug <Critical> core/hle/kernel/k_thread.cpp:140:operator(): assert ((owner == nullptr) || priority)",
            b"Assertion failed: thread state",
            b"Segmentation fault (core dumped)",
        ):
            with self.subTest(diagnostic=diagnostic):
                result, output = self.run_case(GOOD + diagnostic + b"\n")
                self.assertFalse(result)
                self.assertIn("NX2_ADAPTED_EXECUTION_FAULT=1", output)

    def test_binary_noise_and_terminal_colors_preserve_real_diagnostics(self):
        colored = b"\xff\0\n\x1b[0;37m" + GOOD.replace(b"\n", b"\x1b[0m\n\0\x1b[0;37m")
        result, output = self.run_case(colored)
        self.assertTrue(result)
        self.assertIn("[NUL]", output)

    def test_unrelated_filesystem_warning_does_not_hide_success(self):
        result, _ = self.run_case(GOOD + b"Common.Filesystem <Error> Failed to open playtime.bin\n")
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
