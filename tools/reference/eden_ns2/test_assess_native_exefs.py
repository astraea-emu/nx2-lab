# SPDX-License-Identifier: MIT
import contextlib
import io
import unittest
from assess_native_exefs import assess, MESSAGE

GOOD=(
    b"Core <Info> Switch 2 program: using the 12 GiB memory layout\n"
    + b"Debug.Emulated <Info> OutputDebugString: " + MESSAGE.encode()+b"\x00\n"
)
BAD=b"Core <Critical> Failed to load ROM (Error The NPDM file has a bad header.)!\n"

class NativeExeFsAssessmentTests(unittest.TestCase):
    def run_case(self,g=GOOD,b=BAD,grc=124,brc=1):
        with contextlib.redirect_stdout(io.StringIO()) as cap:
            success=assess(g,b,grc,brc)
        return success,cap.getvalue()

    def test_svc_and_classification_with_rejected_invalid(self):
        ok,s=self.run_case()
        self.assertTrue(ok)
        self.assertIn("NX2_NATIVE_GUEST_ORIGINAL_SVC_OUTPUT=1",s)
        self.assertIn("NX2_NATIVE_GUEST_PROCESS_TIMEOUT=1",s)

    def test_plain_host_echo_is_not_guest_execution(self):
        ok,_=self.run_case(g=GOOD.replace(b"OutputDebugString: ",b"Fixture print: "))
        self.assertFalse(ok)

    def test_loader_only_is_not_guest_execution(self):
        ok,_=self.run_case(g=b"Switch 2 program: using the 12 GiB memory layout\n")
        self.assertFalse(ok)

    def test_guest_svc_without_native_classification_fails(self):
        ok,_=self.run_case(g=b"Debug.Emulated <Info> OutputDebugString: "+MESSAGE.encode())
        self.assertFalse(ok)

    def test_empty_bad_image_log_does_not_pass(self):
        ok,s=self.run_case(b=b"",brc=137)
        self.assertFalse(ok)
        self.assertIn("NX2_NATIVE_INVALID_CLEAN_REJECTION=0",s)

    def test_crashed_bad_image_is_not_loader_diagnostic(self):
        ok,_=self.run_case(b=b"Segmentation fault",brc=139)
        self.assertFalse(ok)

    def test_invalid_success_exit_is_not_rejection(self):
        ok,_=self.run_case(brc=0)
        self.assertFalse(ok)

    def test_invalid_timeout_is_not_rejection(self):
        ok,_=self.run_case(brc=124)
        self.assertFalse(ok)

    def test_nul_noise_does_not_hide_valid_guest_line(self):
        ok,s=self.run_case(g=b"noise\x00\n"+GOOD)
        self.assertTrue(ok)
        self.assertIn("[NUL]",s)

if __name__=="__main__":
    unittest.main()
