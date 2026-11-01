"""Offline engine admission tests: real Git trees, explicitly mocked build tools."""
# SPDX-License-Identifier: GPL-3.0-only
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build_native_engine as engine
from test_overlay_eden_exit import fixtures


def console_source():
    return ("Unchanged Windows branch\n#else // ^^^ Windows vvv POSIX\n" +
            engine.CONSOLE_WRITES + "\n#endif\n};\nUnchanged file backend\n")


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "engine"
        self.source = self.directory / "eden"
        self.source.mkdir(parents=True)
        svc, frontend = fixtures()
        self.original = dict(zip(engine.overlay_eden_exit.ORIGINAL_BLOBS, (svc, frontend)))
        self.original.update({engine.CAST:
            "for (s32 layer = 0; layer < info.resources.layers; ++layer) {\n" +
            engine.CAST_BEFORE + "\n}\n", engine.LOADER: "enum ResultStatus { Success, ErrorBadNPDMHeader = 4 };\n",
            engine.LOGGING: console_source(),
            "README": "Original source\n", ".gitignore": ".cache/\nsrc/common/scm_rev.cpp\nexternals/generated/\n",
            "tool.sh": "#!/bin/sh\nexit 0\n"})
        for name, text in self.original.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        (self.source / "tool.sh").chmod(0o755)
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=NX2 test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "original synthetic fixture")
        revision = self.git("rev-parse", "HEAD").strip()
        blobs = {name: self.git("hash-object", name).strip() for name in engine.SOURCE_BLOBS}
        self.tools = {name: {"path": "/tools/" + name, "sha256": "a" * 64,
                             "version": "cmake version 3.31.0" if name == "cmake" else "test tool 1"}
                      for name in ("git", "cmake", "ninja", "clang", "clang++", "ccache")}
        self.patches = [patch.object(engine, "BASELINE_SHA", revision),
                        patch.object(engine, "EDEN_SHA", revision),
                        patch.object(engine, "SOURCE_BLOBS", blobs),
                        patch.object(engine, "toolchain", return_value=self.tools),
                        patch.object(engine, "system_packages", return_value={"available": False}),
                        patch.object(engine, "resources", return_value={"jobs": 2}),
                        patch.object(engine.sys, "platform", "linux"),
                        patch.object(engine, "run", side_effect=self.command)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.commands = []
        self.environments = []
        self.build = self.directory / "eden-build"
        self.receipt = self.directory / "native-engine.json"

    def git(self, *arguments):
        return subprocess.check_output(["git", "-C", str(self.source), *arguments], text=True)

    def command(self, argv, env):
        self.commands.append(argv)
        self.environments.append(env)
        if argv[0] != "/tools/cmake":
            return
        if "-S" in argv:
            self.build.mkdir(parents=True, exist_ok=True)
            options = dict(arg[2:].split("=", 1) for arg in argv if arg.startswith("-D"))
            options.update(CMAKE_GENERATOR="Ninja", CMAKE_HOME_DIRECTORY=str(self.source))
            (self.build / "CMakeCache.txt").write_text("".join(f"{key}:STRING={value}\n"
                                                             for key, value in options.items()))
            (self.build / "CMakeFiles").mkdir(exist_ok=True)
            (self.build / "build.ninja").write_text("# synthetic build graph\n")
            (self.build / "CMakeFiles/rules.ninja").write_text("# synthetic rules\n")
            for name in (".cache/cpm/example/header.h", "src/common/scm_rev.cpp",
                         "externals/generated/header.h"):
                path = self.source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Generated original input\n")
        elif "--build" in argv:
            binary = self.build / "bin/eden-cli"
            binary.parent.mkdir(exist_ok=True)
            if not binary.exists():
                binary.write_text("#!/bin/sh\nexit 0\n")
                binary.chmod(0o755)

    def build_engine(self, *, eden_revision=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.build_engine(self.directory, self.directory / "ccache",
                                       eden_revision=eden_revision)

    @contextlib.contextmanager
    def candidate_source(self):
        (self.source / engine.CAST).write_text(
            self.original[engine.CAST].replace(engine.CAST_BEFORE, engine.CAST_AFTER))
        (self.source / engine.LOADER).write_text(self.original[engine.LOADER] + "// candidate loader\n")
        self.git("add", engine.CAST, engine.LOADER)
        self.git("-c", "user.name=NX2 test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "synthetic candidate with upstream cast repair")
        revision = self.git("rev-parse", "HEAD").strip()
        blobs = {name: self.git("hash-object", name).strip() for name in engine.SOURCE_BLOBS}
        with patch.object(engine, "CANDIDATE_SHA", revision), \
             patch.object(engine, "CANDIDATE_BLOBS", blobs):
            yield revision

    def test_original_source_is_patched_once_and_reused_with_an_incremental_build(self):
        source, binary, first = self.build_engine()
        self.assertEqual(source, self.source)
        self.assertEqual(binary, self.build / "bin/eden-cli")
        self.assertFalse(first["reused"])
        modified = first["modified_source_sha256"]
        self.assertEqual(len(modified), 4)
        mtimes = {name: (source / name).stat().st_mtime_ns for name in modified}
        _, _, second = self.build_engine()
        self.assertTrue(second["reused"])
        self.assertEqual(second["configure_seconds"], 0)
        self.assertEqual(second["eden_cli_sha256"], first["eden_cli_sha256"])
        self.assertEqual({name: (source / name).stat().st_mtime_ns for name in modified}, mtimes)
        self.assertEqual(sum("--build" in command for command in self.commands), 2)
        self.assertEqual(sum("-S" in command for command in self.commands), 1)
        self.assertEqual(json.loads(self.receipt.read_text()), second)
        self.assertFalse((self.directory / ".building").exists())
        self.assertTrue(any("--max-size=1200M" in command for command in self.commands))

    def test_wrong_revision_is_refused_without_source_rewrite(self):
        with self.assertRaisesRegex(ValueError, "pinned revision"):
            self.build_engine(eden_revision=engine.CANDIDATE_SHA)
        self.assertEqual((self.source / engine.CAST).read_text(), self.original[engine.CAST])
        self.assertEqual(self.commands, [])

    def test_candidate_keeps_upstream_cast_and_reuses_only_its_own_receipt(self):
        with self.candidate_source() as revision:
            cast = self.source / engine.CAST
            original_cast, cast_mtime = cast.read_bytes(), cast.stat().st_mtime_ns
            _, _, first = self.build_engine(eden_revision=revision)
            self.assertEqual(first["eden_revision"], revision)
            self.assertEqual(first["identity"]["eden_revision"], revision)
            self.assertEqual(set(first["modified_source_sha256"]),
                             {*engine.overlay_eden_exit.ORIGINAL_BLOBS, engine.LOGGING})
            self.assertNotIn(engine.CAST, first["source_diff"])
            self.assertEqual(cast.read_bytes(), original_cast)
            self.assertEqual(cast.stat().st_mtime_ns, cast_mtime)
            with patch.object(engine, "EDEN_SHA", revision):
                _, _, second = self.build_engine()
            self.assertTrue(second["reused"])
            self.assertEqual(second["eden_cli_sha256"], first["eden_cli_sha256"])
            saved, commands = self.receipt.read_bytes(), len(self.commands)
            with self.assertRaisesRegex(ValueError, "another pinned revision"):
                self.build_engine()
            self.assertEqual(self.receipt.read_bytes(), saved)
            self.assertEqual(len(self.commands), commands)

    def test_baseline_receipt_cannot_be_reused_for_the_candidate(self):
        self.build_engine()
        saved, commands = self.receipt.read_bytes(), len(self.commands)
        with self.assertRaisesRegex(ValueError, "another pinned revision"):
            self.build_engine(eden_revision=engine.CANDIDATE_SHA)
        self.assertEqual(self.receipt.read_bytes(), saved)
        self.assertEqual(len(self.commands), commands)

    def test_candidate_loader_and_cast_cannot_use_baseline_blobs(self):
        with self.candidate_source() as revision:
            for name in (engine.LOADER, engine.CAST):
                with self.subTest(name=name), \
                     patch.dict(engine.CANDIDATE_BLOBS, {name: engine.SOURCE_BLOBS[name]}):
                    with self.assertRaisesRegex(ValueError, "blob changed"):
                        self.build_engine(eden_revision=revision)
        self.assertEqual(self.commands, [])

    def test_unreviewed_revision_is_refused_before_build(self):
        with self.assertRaisesRegex(ValueError, "unsupported Eden revision"):
            self.build_engine(eden_revision="f" * 40)
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.commands, [])

    def test_wrong_loader_blob_is_refused(self):
        with patch.dict(engine.SOURCE_BLOBS, {engine.LOADER: "0" * 40}):
            with self.assertRaisesRegex(ValueError, "blob changed"):
                self.build_engine()

    def test_wrong_logging_blob_is_refused_before_repair(self):
        with patch.dict(engine.SOURCE_BLOBS, {engine.LOGGING: "0" * 40}):
            with self.assertRaisesRegex(ValueError, "blob changed"):
                self.build_engine()
        self.assertEqual((self.source / engine.LOGGING).read_text(), console_source())

    def test_non_overlay_edit_is_found_even_when_git_assumes_unchanged(self):
        self.git("update-index", "--assume-unchanged", "README")
        (self.source / "README").write_text(self.original["README"].replace("Original", "Modified"))
        self.assertEqual(self.git("diff", "--name-only"), "")
        with self.assertRaisesRegex(ValueError, "changed source: README"):
            self.build_engine()
        self.assertEqual((self.source / engine.CAST).read_text(), self.original[engine.CAST])

    def test_foreign_patch_is_not_overwritten(self):
        path = self.source / engine.CAST
        path.write_text(path.read_text() + "unexpected edit\n")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "source"):
            self.build_engine()
        self.assertEqual(path.read_bytes(), before)

    def test_nonignored_untracked_file_is_refused(self):
        (self.source / "extra.cmake").write_text("unknown input\n")
        with self.assertRaisesRegex(ValueError, "untracked"):
            self.build_engine()

    def test_staged_extra_source_is_not_hidden_from_admission(self):
        (self.source / "extra.cmake").write_text("unknown staged input\n")
        self.git("add", "extra.cmake")
        with self.assertRaisesRegex(ValueError, "index path inventory"):
            self.build_engine()

    def test_git_replacement_objects_cannot_redefine_the_pinned_tree(self):
        original = engine.EDEN_SHA
        changed = self.original["README"].replace("Original", "Modified")
        (self.source / "README").write_text(changed)
        self.git("add", "README")
        self.git("-c", "user.name=NX2 test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "replacement tree")
        replacement = self.git("rev-parse", "HEAD").strip()
        self.git("replace", original, replacement)
        self.git("update-ref", "HEAD", original)
        self.assertEqual(self.git("show", f"{original}:README"), changed)
        with self.assertRaisesRegex(ValueError, "changed source: README"):
            self.build_engine()

    def test_source_symlink_or_mode_change_is_refused(self):
        path = self.source / "README"
        external = self.directory / "outside"
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.build_engine()
        path.unlink()
        path.write_bytes(external.read_bytes())
        (self.source / "tool.sh").chmod(0o644)
        with self.assertRaisesRegex(ValueError, "mode"):
            self.build_engine()

    def test_nested_source_directory_is_not_a_checkout_root(self):
        with self.assertRaisesRegex(ValueError, "repository root"):
            engine.check_source(self.source / "src")

    def test_receipt_schema_and_recipe_changes_are_refused(self):
        self.build_engine()
        saved = self.receipt.read_text()
        for mutation in ([], {"schema": True}, {"schema": 1, "identity": {}},
                         {**json.loads(saved), "identity": {"helper_sha256": "changed"}}):
            with self.subTest(mutation=mutation):
                self.receipt.write_text(json.dumps(mutation))
                with self.assertRaises(ValueError):
                    self.build_engine()
        self.receipt.write_text(saved)

    def test_binary_and_generated_build_configuration_changes_are_refused(self):
        _, binary, _ = self.build_engine()
        for path in (binary, *(self.build / name for name in engine.BUILD_FILES)):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"changed\n")
                with self.assertRaisesRegex(ValueError, "binary or configuration changed"):
                    self.build_engine()
                path.write_bytes(original)

    def test_compiler_identity_change_is_refused(self):
        self.build_engine()
        self.tools["clang"]["sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "build identity changed"):
            self.build_engine()

    def test_missing_receipt_does_not_admit_an_existing_binary(self):
        self.build_engine()
        self.receipt.unlink()
        with self.assertRaisesRegex(ValueError, "no successful receipt"):
            self.build_engine()

    def test_failed_incremental_build_invalidates_previous_success(self):
        self.build_engine()
        def fail(argv, env):
            if "--build" in argv:
                raise subprocess.CalledProcessError(7, argv)
            self.command(argv, env)
        with patch.object(engine, "run", side_effect=fail):
            with self.assertRaises(subprocess.CalledProcessError):
                self.build_engine()
        self.assertFalse(self.receipt.exists())
        self.assertTrue((self.directory / ".building").exists())
        with self.assertRaisesRegex(ValueError, "interrupted"):
            self.build_engine()

    def test_successful_incremental_command_cannot_publish_a_different_engine(self):
        self.build_engine()
        def change_binary(argv, env):
            self.command(argv, env)
            if "--build" in argv:
                (self.build / "bin/eden-cli").write_text("#!/bin/sh\nexit 1\n")
        with patch.object(engine, "run", side_effect=change_binary):
            with self.assertRaisesRegex(ValueError, "incremental build changed the engine binary"):
                self.build_engine()
        self.assertFalse(self.receipt.exists())
        self.assertTrue((self.directory / ".building").exists())

    def test_failed_configuration_is_not_published(self):
        def wrong_configuration(argv, env):
            self.command(argv, env)
            if "-S" in argv:
                path = self.build / "CMakeCache.txt"
                path.write_text(path.read_text().replace("ENABLE_OPENGL:STRING=OFF", "ENABLE_OPENGL:STRING=ON"))
        with patch.object(engine, "run", side_effect=wrong_configuration):
            with self.assertRaisesRegex(ValueError, "CMake configuration"):
                self.build_engine()
        self.assertFalse(self.receipt.exists())
        self.assertFalse(any("--build" in command for command in self.commands))

    def test_source_change_during_build_is_not_published(self):
        def edit_source(argv, env):
            self.command(argv, env)
            if "--build" in argv:
                (self.source / "README").write_text(self.original["README"].replace("Original", "Modified"))
        with patch.object(engine, "run", side_effect=edit_source):
            with self.assertRaisesRegex(ValueError, "changed source"):
                self.build_engine()
        self.assertFalse(self.receipt.exists())

    def test_symlink_binary_cannot_be_used_as_an_engine_escape_hatch(self):
        _, binary, _ = self.build_engine()
        external = self.directory / "outside-cli"
        external.write_bytes(binary.read_bytes())
        external.chmod(0o755)
        binary.unlink()
        binary.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.build_engine()

    def test_source_size_is_checked_before_reading_replacement_bytes(self):
        path = self.source / "README"
        with path.open("wb") as stream:
            stream.truncate(64 * 1024**2)
        original_read = engine.bounded_read
        def bounded_read(candidate, limit):
            if candidate == path:
                raise AssertionError("must refuse size before reading this file")
            return original_read(candidate, limit)
        with patch.object(engine, "bounded_read", side_effect=bounded_read):
            with self.assertRaisesRegex(ValueError, "source file size"):
                self.build_engine()

    def test_corrupt_git_object_bytes_are_refused(self):
        original_git = engine.git
        def corrupt(root, *args):
            raw = original_git(root, *args)
            return raw + b"changed" if args[0] == "show" else raw
        with patch.object(engine, "git", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "Git object bytes"):
                self.build_engine()

    def test_oversized_receipt_and_inconsistent_summary_are_refused(self):
        self.build_engine()
        original = self.receipt.read_text()
        with self.receipt.open("wb") as stream:
            stream.truncate(1024**2 + 1)
        with self.assertRaisesRegex(ValueError, "oversized engine file"):
            self.build_engine()
        record = json.loads(original)
        record["eden_cli_sha256"] = "b" * 64
        self.receipt.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "inconsistent engine receipt"):
            self.build_engine()

    def test_fixed_recipe_does_not_inherit_compile_or_include_overrides(self):
        overrides = {name: "/unreviewed" for name in engine.BUILD_OVERRIDES}
        overrides.update(CCACHE_SLOPPINESS="file_stat_matches", CPM_SOURCE_CACHE="/unreviewed",
                         GIT_DIR="/unreviewed")
        with patch.dict(os.environ, overrides):
            self.build_engine()
        for env in self.environments:
            self.assertFalse(set(overrides) & set(env))
            self.assertEqual(env["CCACHE_DIR"], str(self.directory / "ccache"))

    def test_fresh_directory_fetches_exact_commit_from_a_real_local_git_origin(self):
        origin = self.directory / "origin"
        self.source.rename(origin)
        def actual_git(argv, env):
            if argv[0] == "/tools/git":
                subprocess.run(["git", *argv[1:]], env=env, capture_output=True, check=True)
                self.commands.append(argv)
            else:
                self.command(argv, env)
        with patch.object(engine, "EDEN_REPO", str(origin)), \
             patch.object(engine, "run", side_effect=actual_git):
            self.build_engine()
        fetches = [command for command in self.commands if "fetch" in command]
        self.assertEqual(len(fetches), 1)
        self.assertEqual(fetches[0][-1], engine.EDEN_SHA)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), engine.EDEN_SHA)
        self.assertEqual(len(engine.check_source(self.source)), 4)

    def test_exact_prepared_source_without_a_receipt_is_not_repatched(self):
        engine.prepare_source(self.source)
        modified = engine.check_source(self.source)
        mtimes = {name: (self.source / name).stat().st_mtime_ns for name in modified}
        self.build_engine()
        self.assertEqual({name: (self.source / name).stat().st_mtime_ns for name in modified}, mtimes)

    def test_ignored_dependency_or_generated_source_edits_refuse_reuse(self):
        _, _, report = self.build_engine()
        self.assertEqual(report["ignored_source_inputs"]["files"], 3)
        for name in (".cache/cpm/example/header.h", "src/common/scm_rev.cpp",
                     "externals/generated/header.h"):
            with self.subTest(name=name):
                path = self.source / name
                original = path.read_bytes()
                path.write_bytes(original.replace(b"original", b"modified"))
                with self.assertRaisesRegex(ValueError, "ignored dependency or generated source changed"):
                    self.build_engine()
                path.write_bytes(original)

    def test_first_build_refuses_preexisting_ignored_inputs(self):
        path = self.source / ".cache/cpm/example/header.h"
        path.parent.mkdir(parents=True)
        path.write_text("Unverified previous dependency\n")
        with self.assertRaisesRegex(ValueError, "unverified preexisting ignored"):
            self.build_engine()
        self.assertEqual(self.commands, [])


class ConsoleWriteTests(unittest.TestCase):
    def test_only_the_frozen_posix_write_sequence_changes(self):
        original = console_source()
        repaired = engine.patch_console_logging(original)
        self.assertEqual(repaired.replace(engine.CONSOLE_LOCKED_WRITES, engine.CONSOLE_WRITES),
                         original)
        self.assertTrue(repaired.startswith("Unchanged Windows branch\n"))
        self.assertTrue(repaired.endswith("Unchanged file backend\n"))
        self.assertEqual(repaired.count("::flockfile(stdout);"), 1)
        self.assertEqual(repaired.count("::funlockfile(stdout);"), 1)
        for changed in (original.replace("entry.message_len", "unreviewed_length"),
                        original.replace("vvv POSIX", "vvv OTHER"),
                        original.replace(engine.CONSOLE_WRITES, engine.CONSOLE_WRITES * 2)):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "write site"):
                engine.patch_console_logging(changed)

    @unittest.skipUnless(sys.platform == "linux", "POSIX stdout regression requires Linux")
    def test_actual_write_fragment_serializes_forced_interleaving_and_preserves_bytes(self):
        # These are the exact three calls guarded in the frozen source. Linker
        # wrapping pauses A immediately after its first real fwrite; B probes
        # the real FILE lock. No sleeps or probabilistic scheduling are used.
        compiler = shutil.which("g++") or shutil.which("c++")
        self.assertIsNotNone(compiler, "Linux verification requires a C++ compiler")
        harness = r'''
#include <algorithm>
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <thread>

static std::mutex gate;
static std::condition_variable changed;
static bool prefix_written = false;
static bool resume_writer = false;
static thread_local char writer = 0;
static thread_local unsigned calls = 0;

extern "C" size_t __real_fwrite(const void*, size_t, size_t, FILE*);
extern "C" size_t __wrap_fwrite(const void* data, size_t size, size_t count, FILE* stream) {
    const size_t written = __real_fwrite(data, size, count, stream);
    if (writer == 'A' && calls++ == 0) {
        std::unique_lock<std::mutex> lock(gate);
        prefix_written = true;
        changed.notify_all();
        changed.wait(lock, [] { return resume_writer; });
    }
    return written;
}

static void emit(char label) {
    writer = label;
    char buffer[256] = {label, ':', ' '};
    struct { size_t size; } result{3};
    const char message[] = {'x', '\0', 'y'};
    struct { const char* message; size_t message_len; } entry{message, sizeof(message)};
    /* GUARDED_WRITES */
}

static void release_writer() {
    {
        std::lock_guard<std::mutex> lock(gate);
        resume_writer = true;
    }
    changed.notify_all();
}

int main() {
    std::thread first([] { emit('A'); });
    std::thread second([] {
        {
            std::unique_lock<std::mutex> lock(gate);
            changed.wait(lock, [] { return prefix_written; });
        }
        if (::ftrylockfile(stdout) == 0) {
            // The original sequence has already released its implicit lock.
            emit('B');
            ::funlockfile(stdout);
            release_writer();
        } else {
            // The repaired sequence owns stdout until its complete record.
            release_writer();
            emit('B');
        }
    });
    first.join();
    second.join();
}
'''
        repaired = engine.patch_console_logging(console_source())
        repaired_fragment = repaired.partition("#else // ^^^ Windows vvv POSIX\n")[2].partition(
            "#endif\n};")[0]
        outputs = {}
        with tempfile.TemporaryDirectory() as temporary:
            for name, fragment in (("original", engine.CONSOLE_WRITES),
                                   ("repaired", repaired_fragment)):
                source = Path(temporary) / (name + ".cpp")
                executable = Path(temporary) / name
                source.write_text(harness.replace("/* GUARDED_WRITES */", fragment))
                subprocess.run([compiler, "-std=c++17", "-pthread", "-O0", "-fno-builtin-fwrite",
                                "-Wl,--wrap=fwrite", str(source), "-o", str(executable)],
                               check=True, capture_output=True, timeout=30)
                result = subprocess.run([str(executable)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, b"")
                outputs[name] = result.stdout
        suffix = b"x\0y\x1b[0m\n\0"  # Preserve message length and the existing suffix NUL.
        self.assertEqual(outputs["original"], b"A: " + b"B: " + suffix + suffix)
        self.assertEqual(outputs["repaired"], b"A: " + suffix + b"B: " + suffix)
        self.assertNotEqual(outputs["original"], outputs["repaired"])


class PrerequisiteTests(unittest.TestCase):
    def test_old_cmake_is_rejected_before_build(self):
        with patch.object(engine.shutil, "which", side_effect=lambda name: "/tools/" + name), \
             patch.object(engine, "digest", return_value="a" * 64), \
             patch.object(engine.subprocess, "check_output", return_value="cmake version 3.30.0\n"):
            with self.assertRaisesRegex(ValueError, "3.31"):
                engine.toolchain()

    def test_resource_limits_match_the_reviewed_build_recipe(self):
        cases = ((4, 14, 12, 4), (4, 13, 12, 2), (4, 14, 11, 2), (3, 16, 14, 2), (1, 16, 14, 1))
        for cpus, total, available, expected in cases:
            with self.subTest(cpus=cpus, total=total, available=available), \
                 patch.object(engine.os, "sched_getaffinity", return_value=set(range(cpus)), create=True), \
                 patch.object(Path, "read_text", return_value=f"MemTotal: {total * 1024**2} kB\nMemAvailable: {available * 1024**2} kB\n"):
                self.assertEqual(engine.resources()["jobs"], expected)

    def test_print_packages_is_only_the_shared_install_list(self):
        output = io.StringIO()
        with patch.object(engine.sys, "argv", ["build_native_engine.py", "--print-packages"]), \
             patch.object(engine, "build_engine", side_effect=AssertionError("must not build")), \
             contextlib.redirect_stdout(output):
            self.assertEqual(engine.main(), 0)
        self.assertEqual(output.getvalue().splitlines(), [" ".join(engine.APT_PACKAGES)])
        self.assertEqual(len(engine.APT_PACKAGES), len(set(engine.APT_PACKAGES)))


if __name__ == "__main__":
    unittest.main()
