"""Exit overlay tests; compiled fragments use controlled process/SDL dependencies."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import overlay_eden_exit as overlay
from overlay_eden_exit import patch_applet_sources, patch_sources


def fixtures():
    svc = ("void ExitProcess(Core::System& system) {\n"
           "    ASSERT_MSG(current_process->GetState() == KProcess::State::Running,\n"
           "               \"Process has already exited\");\n"
           "    system.Exit();\n"
           "}\n")
    front = ("#include <cstdio>\n"
             "struct SdlState {\n    Core::System system{};\n    Window* emu_window{};\n};\n"
             "void Initialize(SdlState* state) {\n"
             "    state->system.RegisterExitCallback([] {});\n"
             "}\nSDL_AppResult Iterate(SdlState* state) {\n"
             "    return state->emu_window->IsOpen() ? SDL_APP_CONTINUE : SDL_APP_SUCCESS;\n"
             "}\nvoid Shutdown(SdlState* state) {\n"
             "    void(state->system.Pause());\n"
             "    state->system.ShutdownMainProcess();\n}\n")
    return svc, front


def applet_fixtures():
    header = "    void TrackAppletProcess(Applet& applet);\n"
    observer = ("EventObserver::~EventObserver() {\n"
                "    // Free remaining owned sessions.\n"
                "    auto it = m_process_holder_list.begin();\n"
                "    while (it != m_process_holder_list.end()) {\n"
                "        // Get the holder.\n"
                "        auto* const holder = std::addressof(*it);\n\n"
                "        // Remove from the list.\n"
                "        it = m_process_holder_list.erase(it);\n\n"
                "        // Free the holder.\n"
                "        delete holder;\n"
                "    }\n"
                "}\n"
                "void EventObserver::RequestUpdate() {\n}\n"
                "void EventObserver::DestroyAppletProcessHolderLocked(ProcessHolder* holder) {\n}\n")
    window = ("        const auto& [aruid, applet] = *it;\n"
              "        // A winding applet has had its own process killed but is kept alive as a transparent slot\n")
    return header, observer, window


class OverlayExitTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "linux", "compiled exit regression requires Linux")
    def test_generated_exit_waits_for_callback_and_guards_unloaded_shutdown(self):
        compiler = shutil.which("g++") or shutil.which("c++")
        self.assertIsNotNone(compiler, "Linux verification requires a C++ compiler")
        svc, front = patch_sources(*fixtures())
        dependencies = r'''
#include <cassert>
#include <functional>
#define ASSERT_MSG(condition, message) assert(condition)
struct KProcess {
    enum class State { Running };
    unsigned exits{};
    State GetState() const { return State::Running; }
    void Exit(int&) { ++exits; }
} process;
KProcess* current_process = &process;
namespace Core {
struct System {
    int kernel{};
    bool powered{};
    unsigned notifications{}, pauses{}, shutdowns{};
    std::function<void()> callback;
    int& Kernel() { return kernel; }
    void RegisterExitCallback(std::function<void()> cb) { callback = cb; }
    void Exit() { ++notifications; callback(); }
    bool IsPoweredOn() const { return powered; }
    void Pause() { ++pauses; }
    void ShutdownMainProcess() { ++shutdowns; }
};
}
struct Window { bool open{true}; bool IsOpen() const { return open; } } window;
enum SDL_AppResult { SDL_APP_CONTINUE, SDL_APP_SUCCESS };
'''
        checks = r'''
int main() {
    SdlState state;
    state.emu_window = &window;
    Initialize(&state);
    if (Iterate(&state) != SDL_APP_CONTINUE) return 1;
    ExitProcess(state.system);
    if (process.exits != 1 || state.system.notifications != 0 ||
        Iterate(&state) != SDL_APP_CONTINUE) return 2;
    state.system.Exit();  // Model the later completion callback from AM.
    if (Iterate(&state) != SDL_APP_SUCCESS) return 3;
    Shutdown(&state);
    if (state.system.pauses != 0 || state.system.shutdowns != 0) return 4;
    state.system.powered = true;
    Shutdown(&state);
    if (state.system.pauses != 1 || state.system.shutdowns != 1) return 5;
    SdlState closed;
    closed.emu_window = &window;
    Initialize(&closed);
    window.open = false;
    if (Iterate(&closed) != SDL_APP_SUCCESS) return 6;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, executable = Path(directory) / "exit.cpp", Path(directory) / "exit"
            source.write_text(dependencies + svc + front + checks)
            subprocess.run([compiler, "-std=c++20", str(source), "-o", str(executable)],
                           check=True, capture_output=True, timeout=30)
            result = subprocess.run([str(executable)], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

    def test_modifies_only_svc_and_frontend_text(self):
        original_svc, original_front = fixtures()
        svc, front = patch_sources(original_svc, original_front)
        self.assertEqual(svc, original_svc.replace("    system.Exit();\n",
                                                 "    current_process->Exit(system.Kernel());\n"))
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


    def test_applet_overlay_rejects_drift_in_each_modified_site(self):
        edits = ((0, "TrackAppletProcess"), (1, "// Free remaining owned sessions."),
                 (1, "void EventObserver::RequestUpdate()"),
                 (1, "void EventObserver::DestroyAppletProcessHolderLocked"),
                 (2, "const auto& [aruid, applet]"), (2, "// A winding applet"))
        for index, marker in edits:
            with self.subTest(marker=marker):
                source = list(applet_fixtures())
                source[index] = source[index].replace(marker, "changed")
                with self.assertRaisesRegex(ValueError, "frozen AM source"):
                    patch_applet_sources(*source)

    def test_applet_overlay_rejects_ambiguous_and_already_repaired_sources(self):
        original = applet_fixtures()
        for index in range(len(original)):
            with self.subTest(index=index):
                ambiguous = list(original)
                ambiguous[index] *= 2
                with self.assertRaisesRegex(ValueError, "frozen AM source"):
                    patch_applet_sources(*ambiguous)
        with self.assertRaisesRegex(ValueError, "frozen AM source"):
            patch_applet_sources(*patch_applet_sources(*original))

    def test_standalone_overlay_checks_all_am_inputs_before_writing_any_source(self):
        original = dict(zip(overlay.ORIGINAL_BLOBS, fixtures()))
        original.update(zip(overlay.APPLET_BLOBS, applet_fixtures()))
        for failure in ("blob", "replacement"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name, text in original.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text)
                last = root / next(reversed(overlay.APPLET_BLOBS))
                last.write_text(last.read_text().replace("// A winding applet", "// Changed input"))
                before = {name: (root / name).read_bytes() for name in original}
                blobs = {name: subprocess.check_output(["git", "hash-object", str(root / name)],
                                                       text=True).strip() for name in original}
                applet_blobs = {name: blobs[name] for name in overlay.APPLET_BLOBS}
                if failure == "blob":
                    applet_blobs[last.relative_to(root).as_posix()] = "0" * 40
                with patch.dict(overlay.ORIGINAL_BLOBS, {name: blobs[name] for name in overlay.ORIGINAL_BLOBS}), \
                     patch.dict(overlay.APPLET_BLOBS, applet_blobs):
                    with self.assertRaisesRegex(ValueError, "frozen (GPL|AM) source"):
                        overlay.apply(root)
                self.assertEqual({name: (root / name).read_bytes() for name in original}, before)


if __name__ == "__main__":
    unittest.main()
