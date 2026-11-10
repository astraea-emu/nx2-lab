#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Offline guardrails for the isolated modern guest exit experiment."""
import unittest
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from engine_source_preflight import PATHS, oid
import engine_source_preflight as source_module
import modern_exit_overlay as overlay

from engine_source_preflight import CANDIDATES
from modern_exit_overlay import (OverlayError, patch_sources, patch_metadata_magic,
                                 verify_applied, apply, META_PATH)


SVC = """// SPDX-License-Identifier: GPL-3.0-or-later
void ExitProcess(Core::System& system) {
    auto* current_process = GetCurrentProcessPointer(system.Kernel());
    ASSERT_MSG(current_process->GetState() == KProcess::State::Running,
               "Process has already exited");
    system.Exit();
}
"""
FRONTEND = """// SPDX-License-Identifier: GPL-3.0-or-later
#include <atomic>
struct SdlState {
    Core::System system{};
    bool network_initialized{};
};
void Load() {
    state->system.RegisterExitCallback([] {});
}
SDL_AppResult SDL_AppIterate() {
    return state->emu_window && state->emu_window->IsOpen() ? SDL_APP_CONTINUE : SDL_APP_SUCCESS;
}
void SDL_AppQuit() {
    if (state->system.IsPoweredOn()) {
        state->system.ShutdownMainProcess();
    }
}
"""

META_SOURCE = """// SPDX-License-Identifier: GPL-3.0-or-later
Loader::ResultStatus ProgramMetadata::Load(VirtualFile file) {
    if (sizeof(Header) != file->ReadObject(&npdm_header)) {
        return Loader::ResultStatus::ErrorBadNPDMHeader;
    }
    if (sizeof(AcidHeader) != file->ReadObject(&acid_header, npdm_header.acid_offset)) {
        return Loader::ResultStatus::ErrorBadACIDHeader;
    }
}
"""


class OverlayTests(unittest.TestCase):
    def test_both_exact_reviewed_candidate_pins_exist(self):
        self.assertEqual(CANDIDATES["eglantine"][1],
                         "78743f30c251f66bd77e6eea6c28d8632d642d6f")
        self.assertEqual(CANDIDATES["lichii"][1],
                         "7afad5494e650edfc169624be54e606f54b079ec")
        self.assertEqual(CANDIDATES["eglantine"][2][0],
                         CANDIDATES["lichii"][2][0])

    def test_guest_exit_is_signaled_without_changing_other_shutdown_guard(self):
        svc, cli = patch_sources(SVC, FRONTEND)
        self.assertIn("    current_process->Exit(system.Kernel());\n", svc)
        self.assertEqual(svc.count("    system.Exit();\n"), 1)
        self.assertIn("std::atomic_bool guest_exit_requested{false}", cli)
        self.assertIn("std::memory_order_release", cli)
        self.assertIn("std::memory_order_acquire", cli)
        self.assertIn("if (state->guest_exit_requested.load(", cli)
        self.assertIn("if (state->system.IsPoweredOn())", cli)
        self.assertEqual(cli.count("ShutdownMainProcess()"), 1)
        self.assertTrue(cli.startswith("// SPDX-License-Identifier: GPL-3.0-or-later"))
        self.assertTrue(svc.startswith("// SPDX-License-Identifier: GPL-3.0-or-later"))

    def test_npdm_signature_guard_precedes_acid_offset_parsing(self):
        checked = patch_metadata_magic(META_SOURCE)
        self.assertIn('std::memcmp(npdm_header.magic.data(), "META", 4)', checked)
        self.assertLess(checked.index("npdm_header.magic.data()"),
                        checked.index("npdm_header.acid_offset"))
        self.assertEqual(checked.count("ErrorBadNPDMHeader;"), 2)
        self.assertTrue(checked.startswith("// SPDX-License-Identifier: GPL-3.0-or-later"))

    def test_npdm_guard_rejects_missing_duplicate_or_prior_patch(self):
        checked = patch_metadata_magic(META_SOURCE)
        for value in (checked, META_SOURCE.replace(
                "    if (sizeof(Header)", "    if (sizeof(DifferentHeader)"),
                META_SOURCE.replace("    if (sizeof(AcidHeader)", 
                                    "    if (sizeof(Header) != file->ReadObject(&npdm_header)) {\n"
                                    "        return Loader::ResultStatus::ErrorBadNPDMHeader;\n"
                                    "    }\n    if (sizeof(AcidHeader)")):
            with self.subTest(case=value[:60]):
                with self.assertRaises(OverlayError):
                    patch_metadata_magic(value)

    def test_refuses_double_application(self):
        patched = patch_sources(SVC, FRONTEND)
        with self.assertRaises(OverlayError):
            patch_sources(*patched)

    def test_refuses_missing_or_duplicate_guest_exit(self):
        for svc in (SVC.replace("    system.Exit();\n", ""),
                    SVC.replace("    system.Exit();\n", "    system.Exit();\n    system.Exit();\n")):
            with self.subTest(svc=svc):
                with self.assertRaises(OverlayError):
                    patch_sources(svc, FRONTEND)

    def test_refuses_changed_frontend_callbacks_or_iteration(self):
        changes = ("RegisterExitCallback([] {});", "state->emu_window && state->emu_window->IsOpen()",
                   "if (state->system.IsPoweredOn())", "#include <atomic>")
        for value in changes:
            with self.subTest(value=value):
                with self.assertRaises(OverlayError):
                    patch_sources(SVC, FRONTEND.replace(value, "DIFFERENT_SOURCE"))

    def test_refuses_missing_process_state_guard(self):
        with self.assertRaises(OverlayError):
            patch_sources(SVC.replace("KProcess::State::Running", "KProcess::State::Exited"),
                          FRONTEND)


class AppliedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Source Test")
        self.git("remote", "add", "origin", "https://github.com/fixture/source.git")
        original = {}
        for file in PATHS:
            data = SVC.encode() if file.endswith("svc_process.cpp") else (
                FRONTEND.encode() if file.endswith("yuzu.cpp") else
                b"// SPDX-License-Identifier: GPL-3.0-or-later\n")
            output = self.root / file
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
            original[file] = oid(data)
        licenses = {}
        for file in source_module.LICENSES:
            output = self.root / file
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"GNU GENERAL PUBLIC LICENSE\nVersion 3\n")
            licenses[file] = oid(output.read_bytes())
        meta_file = self.root / META_PATH
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        meta_file.write_text(META_SOURCE)
        self.local_meta_blob = oid(META_SOURCE.encode())
        (self.root / "src/yuzu_cmd/CMakeLists.txt").write_text(
            "add_executable(yuzu-cmd test.cpp)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "original GPL test fixture")
        revision = self.git("rev-parse", "HEAD")
        self.local_spec = ("fixture/source", revision, tuple(original[file] for file in PATHS))
        with patch.dict(CANDIDATES, {"eglantine": self.local_spec}):
            with patch.dict(source_module.LICENSES, licenses, clear=True):
                with patch.object(overlay, "META_BLOB", self.local_meta_blob):
                    apply(self.root, "eglantine")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], text=True).strip()

    def test_exact_three_file_patch_is_independently_verified(self):
        with patch.dict(CANDIDATES, {"eglantine": self.local_spec}):
            with patch.object(overlay, "META_BLOB", self.local_meta_blob):
                receipt = verify_applied(self.root, "eglantine")
        self.assertTrue(receipt["exactly_three_modified_source_files"])
        self.assertTrue(receipt["reviewed_npdm_signature_guard_applied"])
        self.assertTrue(receipt["source_identity_verified"])
        self.assertFalse(receipt["emulator_runtime_qualified"])

    def test_extra_modified_source_rejected(self):
        (self.root / PATHS[2]).write_text("unexpected\n")
        with patch.dict(CANDIDATES, {"eglantine": self.local_spec}):
            with patch.object(overlay, "META_BLOB", self.local_meta_blob):
                with self.assertRaisesRegex(OverlayError, "three approved files"):
                    verify_applied(self.root, "eglantine")

    def test_tampered_adapter_bytes_rejected(self):
        p = self.root / "src/yuzu_cmd/yuzu.cpp"
        p.write_text(p.read_text() + "// unexpected\n")
        with patch.dict(CANDIDATES, {"eglantine": self.local_spec}):
            with patch.object(overlay, "META_BLOB", self.local_meta_blob):
                with self.assertRaisesRegex(OverlayError, "overlay bytes"):
                    verify_applied(self.root, "eglantine")

    def test_mutated_npdm_guard_bytes_rejected(self):
        path = self.root / META_PATH
        path.write_text(path.read_text().replace('"META", 4', '"METX", 4'))
        with patch.dict(CANDIDATES, {"eglantine": self.local_spec}):
            with patch.object(overlay, "META_BLOB", self.local_meta_blob):
                with self.assertRaisesRegex(OverlayError, "overlay bytes"):
                    verify_applied(self.root, "eglantine")

    def test_wrong_npdm_source_blob_rejected(self):
        with patch.dict(CANDIDATES, {"eglantine": self.local_spec}):
            with patch.object(overlay, "META_BLOB", "0" * 40):
                with self.assertRaisesRegex(OverlayError, "reviewed Git blob"):
                    verify_applied(self.root, "eglantine")


if __name__ == "__main__":
    unittest.main()
