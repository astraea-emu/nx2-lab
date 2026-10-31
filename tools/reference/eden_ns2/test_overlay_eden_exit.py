"""Source-only safety tests for isolated GPL-side exit callback experiment."""
import unittest
from overlay_eden_exit import patch_sources


def fixtures():
    svc = ("void ExitProcess(Core::System& system) {\n"
           "    ASSERT_MSG(current_process->GetState() == KProcess::State::Running,\n"
           "               \"Process has already exited\");\n"
           "    system.Exit();\n"
           "}\n")
    front = ("#include <cstdio>\n"
             "struct SdlState {\n    Core::System system{};\n};\n"
             "    state->system.RegisterExitCallback([] {});\n"
             "    return state->emu_window->IsOpen() ? SDL_APP_CONTINUE : SDL_APP_SUCCESS;\n"
             "    void(state->system.Pause());\n"
             "    state->system.ShutdownMainProcess();\n")
    return svc, front


class OverlayExitTest(unittest.TestCase):
    def test_exact_noop_callback_becomes_atomic_guest_exit_request(self):
        svc, front = patch_sources(*fixtures())
        self.assertIn("current_process->Exit(system.Kernel());", svc)
        self.assertIn("guest_exit_requested.store(true, std::memory_order_release)", front)
        self.assertIn("guest_exit_requested.load(std::memory_order_acquire)", front)

    def test_unloaded_image_does_not_run_full_guest_shutdown(self):
        _, front = patch_sources(*fixtures())
        self.assertIn("if (state->system.IsPoweredOn()) {", front)
        self.assertIn("state->system.ShutdownMainProcess();", front)

    def test_modifies_only_svc_and_frontend_text(self):
        svc, front = patch_sources(*fixtures())
        self.assertEqual(svc.count("current_process->Exit(system.Kernel());"), 1)
        self.assertEqual(front.count("guest_exit_requested"), 3)
        self.assertEqual(front.count("IsPoweredOn()"), 1)

    def test_drift_in_svc_is_refused(self):
        svc, front = fixtures()
        with self.assertRaises(ValueError):
            patch_sources(svc.replace("    system.Exit();", "    no_op();"), front)

    def test_drift_in_frontend_is_refused(self):
        svc, front = fixtures()
        with self.assertRaises(ValueError):
            patch_sources(svc, front.replace("RegisterExitCallback([] {})", "RegisterExitCallback(foo)"))

    def test_double_application_fails_closed(self):
        svc, front = patch_sources(*fixtures())
        with self.assertRaises(ValueError):
            patch_sources(svc, front)


if __name__ == "__main__":
    unittest.main()
