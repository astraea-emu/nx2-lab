# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic log controls; these tests do not claim emulator or guest execution."""
import contextlib
import io
import unittest
from unittest.mock import patch

import assess_native_vi2
from assess_native_vi2 import assess


CLASSIFIED = (b"[   0.022450] Core <Info> core/core.cpp:321:Load: "
              b"Switch 2 program: using the 12 GiB memory layout\n")
PREFIX = (b"[   0.753159] Debug.Emulated <Info> "
          b"core/hle/kernel/svc/svc_debug_string.cpp:25:OutputDebugString: ")
BEGIN = PREFIX + b"NX2_VI2_BEGIN\n"
COMPLETE = PREFIX + b"NX2_VI2_COMPLETE\n"
EXIT = (b"[   0.753189] Kernel.SVC <Info> "
        b"core/hle/kernel/svc/svc_process.cpp:17:ExitProcess: Process 81 exiting\n")
MANAGER = (b"[   0.753161] Service.VI <Warning> "
           b"core/hle/service/vi/application_display_service.cpp:81:"
           b"GetManagerDisplayService: (STUBBED) called\n")
EMPTY_PATH = (b"[   0.000182] Common.Filesystem <Error> "
              b"common/fs/path_util.cpp:308:SetEdenPath: "
              b"Filesystem object at new_path= is not a directory\n")
MISSING_TITLE = (b"[   0.256642] Core <Error> core/core.cpp:355:Load: "
                 b"Failed to read title for ROM!\n")
NETWORK = (b"[   0.274937] Service <Error> "
           b"core/hle/service/sockets/bsd.cpp:1164:BSD_USA: Network isn't initialized\n")


def observed_fields():
    """Spell out wire observations independently of the assessor's field table."""
    fields = [("connect_rc", 0), ("sm_handle", 0x103FE)]
    for name, word1, descriptor, extra in (
        ("sm_init", 0xA, 0, ()),
        ("get_applet", 0x8000000A, 0x20, (("applet_handle", 0x183FD),)),
        ("open_proxy", 0x8000000A, 0x20, (("proxy_handle", 0x203FC),)),
        ("get_window", 0x8000000A, 0x20, (("window_handle", 0x283FB),)),
        ("get_aruid", 0xE, 0, (("aruid_lo", 0x51), ("aruid_hi", 0))),
        ("get_self", 0x8000000A, 0x20, (("self_handle", 0x303FA),)),
        ("get_gsv", 0x8000000A, 2, (("gsv_handle", 0x383F9),)),
    ):
        fields.extend((name + "_" + suffix, value) for suffix, value in (
            ("transport", 0), ("header0", 0), ("header1", word1),
            ("descriptor", descriptor), ("magic", 0x4F434653), ("result", 0)))
        fields.extend(extra)
    for name, word0, word1, result in (
        ("bootstrap", 0x14, 1, 0), ("bind", 0x1B, 1, 0), ("ready", 0x75, 1, 0),
        ("display_init", 0x13D, 1, 0), ("open_vi2", 0x141, 0x80000001, 0),
        ("register", 0xD9, 1, 0), ("duplicate", 0xD9, 1, 0xFA01),
        ("unregister", 0xDA, 1, 0), ("missing", 0xDA, 1, 0xF201),
        ("short", 0x25, 1, 0xCA01), ("first", 0x25, 1, 0),
        ("clear", 0x25, 1, 0), ("display_finalize", 0x13F, 1, 0),
    ):
        fields.extend(((name + "_transport", 0), (name + "_header0", word0),
                       (name + "_header1", word1)))
        if name == "open_vi2":
            fields.extend((("open_vi2_descriptor", 0x20), ("vi2_handle", 0x403F8)))
        fields.append((name + "_result", result))
        if name in ("short", "first", "clear"):
            fields.append((name + "_guard_before", 0xA5A5A5A5))
            contents = ([0xA5A5A5A5] * 32 if name == "short" else
                        [4] + [0] * 31 if name == "first" else [0] * 32)
            fields.extend((f"{name}_word{index:02d}", value)
                          for index, value in enumerate(contents))
            fields.append((name + "_guard_after", 0xA5A5A5A5))
    fields.extend(("close_" + name, 0) for name in
                  ("vi2", "gsv", "self", "window", "proxy", "applet", "sm"))
    return fields + [("fail_step", 0)]


FIELDS = observed_fields()


def record(name, value):
    return PREFIX + f"NX2_VI2 {name}={value:08x}\n".encode()


RECORDS = b"".join(record(name, value) for name, value in FIELDS)
GOOD = CLASSIFIED + BEGIN + MANAGER + RECORDS + COMPLETE + EXIT


def changed(name, value, log=GOOD):
    original = dict(FIELDS)[name]
    return log.replace(record(name, original), record(name, value), 1)


class NativeVi2AssessmentTests(unittest.TestCase):
    def run_case(self, log=GOOD, status=0):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = assess(log, status)
        return result, output.getvalue()

    def test_complete_lifecycle_requires_observed_results_memory_handles_and_exit(self):
        ok, output = self.run_case()
        self.assertTrue(ok)
        for item in ("FIELD_COUNT=215", "KNOWN_MANAGER_STUB_COUNT=1",
                     "ARUID_MATCHES_EXIT_PROCESS=1", "OBSERVED_DUPLICATE_RESULT=0000fa01",
                     "OBSERVED_MISSING_RESULT=0000f201", "OBSERVED_SHORT_RESULT=0000ca01",
                     "OBSERVED_FIRST_WORD00=00000004", "CLIENT_LIFECYCLE_PASS"):
            self.assertIn("NX2_NATIVE_VI2_" + item, output)

    def test_each_field_must_exist_once_including_every_buffer_word_and_close(self):
        for name, value in FIELDS:
            line = record(name, value)
            with self.subTest(name=name, defect="missing"):
                self.assertFalse(self.run_case(GOOD.replace(line, b"", 1))[0])
            with self.subTest(name=name, defect="duplicate"):
                self.assertFalse(self.run_case(GOOD.replace(line, line * 2, 1))[0])

    def test_each_fixed_wire_value_and_memory_word_is_checked(self):
        for name, value in FIELDS:
            if name.endswith("_handle") or name.startswith("aruid_"):
                continue
            with self.subTest(name=name):
                self.assertFalse(self.run_case(changed(name, value ^ 1))[0])

    def test_unobserved_sentinel_never_counts_as_a_result_or_handle(self):
        for name, _ in FIELDS:
            with self.subTest(name=name):
                self.assertFalse(self.run_case(changed(name, 0xFFFFFFFF))[0])

    def test_cmif_copy_handle_and_tipc_move_handle_cannot_be_confused(self):
        for name, value in (("get_gsv_descriptor", 0x20), ("get_self_descriptor", 2),
                            ("open_vi2_descriptor", 2), ("open_vi2_header1", 1),
                            ("get_gsv_header1", 0xA), ("get_aruid_header1", 0xA),
                            ("bootstrap_result", 0x4F434653), ("first_header1", 0xA)):
            with self.subTest(name=name):
                self.assertFalse(self.run_case(changed(name, value))[0])

    def test_negative_operations_must_return_their_distinct_typed_results(self):
        for name in ("duplicate_result", "missing_result", "short_result"):
            for value in (0, 1, 0xF601):
                with self.subTest(name=name, value=value):
                    self.assertFalse(self.run_case(changed(name, value))[0])

    def test_short_buffer_cannot_consume_notification_or_modify_any_byte(self):
        for name, value in (("short_word31", 0x00A5A5A5), ("short_guard_after", 0),
                            ("first_word00", 0), ("first_word00", 8),
                            ("first_word31", 4), ("clear_word00", 4)):
            with self.subTest(name=name, value=value):
                self.assertFalse(self.run_case(changed(name, value))[0])

    def test_all_seven_handles_must_have_real_table_encoding_and_be_distinct(self):
        handles = [name for name, _ in FIELDS if name.endswith("_handle")]
        self.assertEqual(len(handles), 7)
        for name in handles:
            for value in (0, 1, 0x80000400, 0x00008400, 0x40008001,
                          0xFFFF8000, 0xFFFF8001, 0xFFFFFFFF):
                with self.subTest(name=name, value=value):
                    self.assertFalse(self.run_case(changed(name, value))[0])
            other = next(key for key in handles if key != name)
            with self.subTest(name=name, defect="duplicate"):
                self.assertFalse(self.run_case(changed(name, dict(FIELDS)[other]))[0])

    def test_aruid_must_match_process_id_in_actual_exit_record(self):
        for name, value in (("aruid_lo", 0), ("aruid_lo", 0x52), ("aruid_hi", 1)):
            with self.subTest(name=name):
                self.assertFalse(self.run_case(changed(name, value))[0])
        self.assertFalse(self.run_case(GOOD.replace(b"Process 81 exiting", b"Process 82 exiting"))[0])
        self.assertTrue(self.run_case(changed("aruid_lo", 0x52).replace(
            b"Process 81 exiting", b"Process 82 exiting"))[0])

    def test_field_order_is_part_of_the_guest_contract(self):
        for first, second in ((FIELDS[0], FIELDS[1]), (FIELDS[-2], FIELDS[-1])):
            a, b = record(*first), record(*second)
            self.assertFalse(self.run_case(GOOD.replace(a + b, b + a))[0])
        self.assertFalse(self.run_case(GOOD.replace(
            record("register_result", 0), record("unregister_result", 0), 1))[0])

    def test_classification_begin_completion_and_exit_are_unique_and_ordered(self):
        for event in (CLASSIFIED, BEGIN, COMPLETE, EXIT):
            with self.subTest(event=event, defect="missing"):
                self.assertFalse(self.run_case(GOOD.replace(event, b"", 1))[0])
            with self.subTest(event=event, defect="duplicate"):
                self.assertFalse(self.run_case(GOOD.replace(event, event * 2, 1))[0])
        for log in (BEGIN + CLASSIFIED + MANAGER + RECORDS + COMPLETE + EXIT,
                    CLASSIFIED + MANAGER + BEGIN + RECORDS + COMPLETE + EXIT,
                    CLASSIFIED + BEGIN + MANAGER + COMPLETE + RECORDS + EXIT,
                    CLASSIFIED + BEGIN + MANAGER + RECORDS + EXIT + COMPLETE):
            with self.subTest(log=log[:100]):
                self.assertFalse(self.run_case(log)[0])

    def test_source_tags_cannot_be_supplied_by_host_prefixed_or_plain_echoes(self):
        for before, after in ((PREFIX, b"Fixture echo: " + PREFIX),
                              (PREFIX, b"Fixture echo: "),
                              (b"svc_debug_string.cpp", b"fixture_echo.cpp"),
                              (CLASSIFIED, b"Fixture echo: " + CLASSIFIED),
                              (EXIT, b"Fixture echo: " + EXIT),
                              (BEGIN, b"NX2_VI2_BEGIN\n"),
                              (COMPLETE, b"NX2_VI2_COMPLETE\n")):
            with self.subTest(after=after[:100]):
                self.assertFalse(self.run_case(GOOD.replace(before, after))[0])
        self.assertFalse(self.run_case(GOOD + b"NX2_VI2 connect_rc=00000000\n")[0])

    def test_malformed_unknown_or_interior_control_bytes_are_not_repaired(self):
        for replacement in (b"connect_rc=0", b"connect_rc=000000000",
                            b"connect_rc=0x00000000", b"connect_rc=0000000A",
                            b"connect_rc=0000\0\x1b[0m0000", b"connect_rc=0000\x1b[0m0000",
                            b"connect_rc=0000\xff0000", b"connect_rc=00000000 trailing",
                            b"unknown_field=00000000", b"CONNECT_RC=00000000"):
            with self.subTest(replacement=replacement):
                self.assertFalse(self.run_case(GOOD.replace(b"connect_rc=00000000", replacement))[0])

    def test_failure_marker_or_nonzero_process_status_cannot_pass(self):
        for status in (-11, -9, 1, 2, 124, 125, 126, 127, 134, 137, 139, 143):
            with self.subTest(status=status):
                self.assertFalse(self.run_case(status=status)[0])
        for line in (PREFIX + b"NX2_VI2_FAILURE\n", b"NX2_VI2_FAILURE\n"):
            self.assertFalse(self.run_case(GOOD + line)[0])

    def test_manager_diagnostic_is_required_exactly_once_during_guest_execution(self):
        for replacement in (b"", MANAGER * 2, b"Host echo: " + MANAGER,
                            MANAGER.replace(b":81:", b":82:"),
                            MANAGER.replace(b"application_display_service.cpp", b"other.cpp"),
                            MANAGER.replace(b"GetManagerDisplayService", b"GetSystemDisplayService"),
                            MANAGER.replace(b"<Warning>", b"<Info>"),
                            MANAGER.replace(b"(STUBBED) called", b"(STUBBED) called anyway")):
            with self.subTest(replacement=replacement):
                self.assertFalse(self.run_case(GOOD.replace(MANAGER, replacement))[0])
        for log in (MANAGER + GOOD.replace(MANAGER, b""),
                    GOOD.replace(MANAGER, b"").replace(COMPLETE, MANAGER + COMPLETE),
                    GOOD.replace(MANAGER, b"") + MANAGER):
            self.assertFalse(self.run_case(log)[0])

    def test_no_other_stub_fallback_or_unimplemented_path_is_accepted(self):
        for diagnostic in (
            b"Service <Warning> Using auto stub fallback!",
            b"Debug <Critical> Unknown / unimplemented OpenApplicationProxy",
            b"Service.AM <Warning> core/hle/service/stub.cpp:14:Call: (STUBBED) called",
            b"Service.VI <Warning> runtime fallback selected",
            b"Service.VI <Info> Not implemented",
        ):
            with self.subTest(diagnostic=diagnostic):
                self.assertFalse(self.run_case(GOOD + diagnostic + b"\n")[0])

    def test_known_pre_guest_errors_are_explicitly_counted_and_limited(self):
        log = EMPTY_PATH * 5 + CLASSIFIED + MISSING_TITLE + NETWORK * 3 + GOOD[len(CLASSIFIED):]
        ok, output = self.run_case(log)
        self.assertTrue(ok)
        for field in ("EMPTY_PATH_ERRORS=5", "MISSING_TITLE_ERRORS=1", "NETWORK_UNINITIALIZED_ERRORS=3"):
            self.assertIn("NX2_NATIVE_VI2_ALLOWED_STARTUP_" + field, output)
        for diagnostic, count in ((EMPTY_PATH, 6), (MISSING_TITLE, 2), (NETWORK, 4)):
            with self.subTest(diagnostic=diagnostic):
                self.assertFalse(self.run_case(diagnostic * count + GOOD)[0])

    def test_allowed_startup_messages_require_exact_source_and_pre_begin_phase(self):
        for diagnostic in (EMPTY_PATH, MISSING_TITLE, NETWORK):
            for changed_diagnostic in (
                b"Host echo: " + diagnostic,
                diagnostic.replace(b" <Error>", b" <Critical>"),
                diagnostic.replace(b".cpp:", b".cpp:9"),
                diagnostic.replace(b"core/", b"other/", 1) if b"core/" in diagnostic else
                diagnostic.replace(b"common/fs/", b"other/", 1),
                diagnostic.replace(b"\n", b" extra\n"),
            ):
                with self.subTest(diagnostic=changed_diagnostic):
                    self.assertFalse(self.run_case(changed_diagnostic + GOOD)[0])
            for log in (GOOD.replace(BEGIN, BEGIN + diagnostic), GOOD + diagnostic):
                with self.subTest(diagnostic=diagnostic, defect="late"):
                    self.assertFalse(self.run_case(log)[0])

    def test_genuine_am_vi_sm_and_shutdown_errors_are_never_exempted(self):
        for diagnostic in (
            b"Service.AM <Error> core/hle/service/am/service/graphics_supervisor.cpp:1:Initialize: failed",
            b"Service.VI <Error> core/hle/service/vi/application_display_service.cpp:81:GetManagerDisplayService: (STUBBED) called",
            b"Service.SM <Error> core/hle/service/sm/sm.cpp:1:GetService: Invalid service name!",
            b"Common.Filesystem <Error> common/fs/file.cpp:286:Open: Failed to open the file at path=/tmp/play_time/playtime.bin, ec_message=No such file or directory",
            b"Frontend <Error> frontend_common/play_time_manager.cpp:146:Save: Failed to update play time database!",
            b"Core <Critical> core/core.cpp:355:Load: Failed to read title for ROM!",
        ):
            with self.subTest(diagnostic=diagnostic):
                self.assertFalse(self.run_case(diagnostic + b"\n" + GOOD)[0])
                self.assertFalse(self.run_case(GOOD + diagnostic + b"\n")[0])

    def test_fault_assertion_sanitizer_or_timeout_is_fatal_even_with_complete_log(self):
        for diagnostic in (b"assert (priority)", b"ExceptionRaised(exception=UndefinedInstruction)",
                           b"Cannot execute instruction at unmapped address 0x0", b"Segmentation fault",
                           b"Aborted", b"AddressSanitizer: heap-buffer-overflow",
                           b"UndefinedBehaviorSanitizer", b"runtime error: misaligned access",
                           b"Operation timed out", b"timeout: command killed"):
            with self.subTest(diagnostic=diagnostic):
                self.assertFalse(self.run_case(GOOD + diagnostic + b"\n")[0])

    def test_boundary_nuls_colors_and_crlf_preserve_source_records(self):
        colored = b"".join(b"\0\x1b[0;37m" + line + b"\0\x1b[0m\r\n"
                           for line in GOOD.splitlines())
        ok, output = self.run_case(colored)
        self.assertTrue(ok)
        self.assertIn("NX2_NATIVE_VI2_LOG_NUL_COUNT=440", output)
        self.assertNotIn("\x1b", output)
        # An interior NUL must not hide an actual error severity from the scan.
        self.assertFalse(self.run_case(GOOD + b"Core <Er\0ror> failed\n")[0])

    def test_oversized_input_is_refused_before_parsing(self):
        with patch.object(assess_native_vi2, "MAX_LOG_SIZE", 16):
            ok, output = self.run_case()
        self.assertFalse(ok)
        self.assertIn("NX2_NATIVE_VI2_LOG_LIMIT_EXCEEDED", output)


if __name__ == "__main__":
    unittest.main()
