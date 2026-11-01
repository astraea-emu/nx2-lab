#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Earlier MIT-licensed material retains that permission; see LICENSES/MIT.txt.
"""Reconcile 29 native GPU cases in an exact, ephemeral Eden GPL checkout.

Only the upstream test file is written. Two DMA-contract cases remain verbatim
inside explicit disabled blocks and are named in the manifest. This tool does
not build or run Catch2 and never reports a test pass.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess

EDEN_COMMIT = "e2f285ab1ecd3a2475c2ccad66f23b06b94ead5c"
TEST_PATH = "src/tests/core/native_gpu_characteristics.cpp"
CMAKE_PATH = "src/tests/CMakeLists.txt"
CATCH2_FILTER = "[nx2-native-gpu-restored]"
ORIGINAL_BLOBS = {
    TEST_PATH: "b54bd36ee35d433263f0bed967ca111391c03ea2",
    CMAKE_PATH: "ff1168471c5eb45aa54b78892b5f65e03391688f",
    "src/video_core/macro_turing.h": "600db481198f1834ef0f83c3670727c427adebc2",
    "src/video_core/macro.h": "b1b1a6095532c3c641170df70f0da128f693de39",
    "src/video_core/macro.cpp": "48fa89a01e71c6348126bab13da67a6d8b36c989",
    "src/video_core/native_qmd.h": "3a985919e5684fcb076db5d6f702c84a4e3ff01f",
    "src/core/hle/service/nvdrv/devices/native_gpu_characteristics.h":
        "4c8c16b1c5ebe2e46e861b9ad769b7bbad6380cd",
    "src/core/hle/service/nvdrv/devices/gpu_address_space_layout.h":
        "8be7ab173cbde493b40b0781b9c0f63c20396f9d",
    "src/core/hle/service/nvdrv/devices/native_gpu_kind.h":
        "e0a36a139951171bdaca244fc82cb6465c5fd588",
    "src/core/hle/service/nvdrv/devices/native_gpu_context.h":
        "c6d11880d57c54c394ea5ad5c75d55114fed9e3d",
    "src/core/hle/service/nvdrv/devices/native_sparse_remap.h":
        "6fb10b069d0f1760b8d05eb14a99a3ac37db0d33",
    "src/video_core/native_root_table.h": "89cb4ae0ef141c7e04045bc35b8836770e90ca0e",
    "src/video_core/dirty_flags.cpp": "e6856aaca33a2b8b4e7df882615b5d737944d248",
    "src/video_core/engines/maxwell_3d.h": "84c2a84fe3cd2fcd4a9d3ab1a4b7594681c45c48",
    "src/core/hle/kernel/k_memory_block.h": "2abca31d8737d7cb7276e170b7e2d8418549b588",
    "src/tests/core/graphics_supervisor.cpp": "7172fba165e6bd06c245a7cf733222b31d5a8f71",
    "src/tests/video_core/native_semaphore.cpp": "98b3e35279daf61228967ff9342e166336a4345b",
    "src/tests/video_core/native_shader.cpp": "998cd438192008368e48862ef550ae075e70955f",
}
EXISTING_SOURCE_SPECS = {
    "src/tests/core/graphics_supervisor.cpp": ("[graphics-supervisor]", 22),
    "src/tests/video_core/native_semaphore.cpp": ("[native-gpu]", 7),
    "src/tests/video_core/native_shader.cpp": ("[native-gpu]", 4),
}
COMBINED_FILTER = "[native-gpu],[graphics-supervisor]"

LOOPS = "Native MME loops consume the exact parameter count, including zero iterations"
CARRY = "Native MME pairs ALU carry with two incrementing outputs"
DUAL_ALU = "Native MME dual ALUs sample registers before either writeback"
BACK_EDGE = "Native MME taken back edges suppress fallthrough termination"
DATA_RAM = "Shared MME programs preserve independent persistent data RAM"
COMPATIBLE_CASES = frozenset((LOOPS, CARRY, DUAL_ALU, BACK_EDGE, DATA_RAM))
UNRESOLVED_CASES = {
    "Native MME FIFO barrier reads the captured memory comparison program":
        "DMA memory reads moved to MacroEngine's caller; the old interpreter "
        "memory-failure callback and decoded-execution contract are absent.",
    "Native MME rejects oversized FIFO DMA and unknown extended operations":
        "The old 1025-word rejection conflicts with the caller's 4096-word clamp; "
        "the unknown-operation assertion is retained here but remains unexecuted.",
}

# Original test-only encoding adapter. Bit positions are data from the pinned
# decoder; no upstream implementation or test body is embedded in this tool.
# The original data-RAM case supplies Decoded field values, which are encoded
# and then decoded/executed by the real interpreter's existing raw-code API.
MME_ENCODER = r"""
// NX2 test compatibility helper; original MIT-authored transformation.
// No runtime implementation changes. Uploaded words are high-to-low.
namespace {
template <std::size_t Count>
std::array<u32, Count * 3> Nx2EncodeMmeProgram(
    const std::array<Tegra::TuringMacroInterpreter::Decoded, Count>& instructions) {
    std::array<u32, Count * 3> encoded{};
    for (std::size_t index = 0; index < Count; ++index) {
        std::array<u32, 3> bits{};
        const auto put = [&](u32 first, u32 width, u32 value) {
            for (u32 bit = 0; bit < width; ++bit) {
                const u32 position = first + bit;
                bits[position / 32] |= ((value >> bit) & 1U) << (position % 32);
            }
        };
        const auto& fields = instructions[index];
        put(0, 1, fields.end);
        put(1, 4, fields.pred_mode);
        put(5, 5, fields.pred_reg);
        for (u32 lane = 0; lane < 2; ++lane) {
            put(10 + 36 * lane, 5, fields.op[lane]);
            put(15 + 36 * lane, 5, fields.dst[lane]);
            put(20 + 36 * lane, 5, fields.src_a[lane]);
            put(25 + 36 * lane, 5, fields.src_b[lane]);
            put(30 + 36 * lane, 16, fields.imm[lane]);
            put(82 + 7 * lane, 3, fields.out_method[lane]);
            put(85 + 7 * lane, 4, fields.out_emit[lane]);
        }
        for (std::size_t word = 0; word < 3; ++word) {
            encoded[index * 3 + word] = bits[2 - word];
        }
    }
    return encoded;
}
} // namespace

"""

CASE_HEADER = re.compile(
    r'^TEST_CASE\("([^"]+)",\s*"\[native-gpu\]"\) \{', re.MULTILINE)
ASSERTION = re.compile(r"\bREQUIRE(?:_FALSE)?\s*\(")
ALL_CASE_HEADERS = re.compile(
    r'^TEST_CASE\("([^"]+)",\s*"([^"]+)"\) \{', re.MULTILINE)


@dataclass(frozen=True)
class Case:
    name: str
    header: str
    body: str
    line: int


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"expected one frozen replacement site: {old!r}")
    return source.replace(old, new, 1)


def split_cases(source: str) -> tuple[str, list[Case]]:
    matches = list(CASE_HEADER.finditer(source))
    if len(matches) != 31 or source.count("TEST_CASE(") != 31:
        raise ValueError("expected exactly 31 frozen native GPU case declarations")
    cases = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        cases.append(Case(match[1], match[0], source[match.end():end],
                          source.count("\n", 0, match.start()) + 1))
    if len({case.name for case in cases}) != 31:
        raise ValueError("duplicate case identities")
    return source[:matches[0].start()], cases


def adapt_case(case: Case) -> str:
    body = case.body
    if case.name == LOOPS:
        changes = (
            ("const std::array<u32, 1> zero{", "std::vector<u32> zero{"),
            ("const std::array<u32, 3> two{", "std::vector<u32> two{"),
            ("    result = interpreter.Execute(code, 0, std::span<const u32>{}, read, emit);",
             "    std::vector<u32> empty;\n"
             "    result = interpreter.Execute(code, 0, empty, read, emit);"),
        )
    elif case.name == CARRY:
        changes = (("const std::array<u32, 2> params{", "std::vector<u32> params{"),)
    elif case.name == DUAL_ALU:
        changes = (("const std::array<u32, 2> parameters{", "std::vector<u32> parameters{"),)
    elif case.name == BACK_EDGE:
        changes = (("const std::array<u32, 1> parameters{", "std::vector<u32> parameters{"),)
    elif case.name == DATA_RAM:
        changes = (
            ("std::array<Interpreter::Instruction, 2> store{};",
             "std::array<Interpreter::Decoded, 2> store{};"),
            ("std::array<Interpreter::Instruction, 3> load{};",
             "std::array<Interpreter::Decoded, 3> load{};"),
            ("    store[0].load_mask = 1;\n", ""),
            ("store[0].end_next = true;", "store[0].end = true;"),
            ("load[1].end_next = true;", "load[1].end = true;"),
            ("const std::array<u32, 1> a{", "std::vector<u32> a{"),
            ("first.ExecuteDecoded(store, 0, a, read,",
             "first.Execute(Nx2EncodeMmeProgram(store), 0, a, read,"),
            ("second.ExecuteDecoded(store, 0, b, read,",
             "second.Execute(Nx2EncodeMmeProgram(store), 0, b, read,"),
            ("                const auto result = interpreter.ExecuteDecoded(load, 0, {}, read,",
             "                std::vector<u32> empty;\n"
             "                const auto result = interpreter.Execute("
             "Nx2EncodeMmeProgram(load), 0, empty, read,"),
        )
    else:
        return body
    for old, new in changes:
        body = replace_once(body, old, new)
    if len(ASSERTION.findall(body)) != len(ASSERTION.findall(case.body)):
        raise ValueError(f"assertion count changed in {case.name}")
    return body


def transform(original: bytes) -> tuple[bytes, dict]:
    if git_blob(original) != ORIGINAL_BLOBS[TEST_PATH]:
        raise ValueError("test contents do not match the frozen source blob")
    prefix, cases = split_cases(original.decode("utf-8"))
    if not (COMPATIBLE_CASES | UNRESOLVED_CASES.keys()) <= {case.name for case in cases}:
        raise ValueError("missing declared compatibility or unresolved cases")
    parts = [prefix, MME_ENCODER]
    records = []
    for case in cases:
        if case.name in UNRESOLVED_CASES:
            disposition = "unresolved_disabled"
            body = case.body
            parts.extend((
                "#if 0 // NX2_UNRESOLVED_DMA_CONTRACT: retained, not passed\n",
                case.header, body,
                "#endif // NX2_UNRESOLVED_DMA_CONTRACT\n\n",
            ))
        else:
            disposition = "compatible" if case.name in COMPATIBLE_CASES else "unchanged"
            body = adapt_case(case)
            header = replace_once(case.header, '"[native-gpu]"',
                                  f'"[native-gpu]{CATCH2_FILTER}"')
            parts.extend((header, body))
        record = {
            "name": case.name, "original_line": case.line,
            "area": "MME" if "MME" in case.name else "other",
            "disposition": disposition,
            "original_tags": "[native-gpu]",
            "applied_tags": ("[native-gpu]" if disposition == "unresolved_disabled"
                             else "[native-gpu]" + CATCH2_FILTER),
            "expected_registered": disposition != "unresolved_disabled",
            "original_assertion_expressions": len(ASSERTION.findall(case.body)),
            "adapted_assertion_expressions": len(ASSERTION.findall(body)),
            "original_body_sha256": hashlib.sha256(case.body.encode()).hexdigest(),
            "adapted_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        }
        if disposition == "unresolved_disabled":
            record["reason"] = UNRESOLVED_CASES[case.name]
        records.append(record)
    patched = "".join(parts).encode("utf-8")
    counts = {
        "original_cases": len(cases),
        "mme_cases": sum(record["area"] == "MME" for record in records),
        "other_cases": sum(record["area"] == "other" for record in records),
        "unchanged_bodies": sum(record["disposition"] == "unchanged" for record in records),
        "compatibility_cases": sum(record["disposition"] == "compatible" for record in records),
        "unresolved_disabled": sum(record["disposition"] == "unresolved_disabled"
                                   for record in records),
        "selected_cases": patched.count(CATCH2_FILTER.encode("ascii")),
    }
    if tuple(counts.values()) != (31, 8, 23, 24, 5, 2, 29):
        raise ValueError(f"unexpected reconciliation inventory: {counts}")
    manifest = {
        "schema_version": 1,
        "frozen_commit": EDEN_COMMIT,
        "guarded_original_blobs": dict(ORIGINAL_BLOBS),
        "modified_path": TEST_PATH,
        "patched_test_blob": git_blob(patched),
        "catch2_filter": CATCH2_FILTER,
        "required_environment": {"EDEN_NATIVE_STRICT": "1"},
        "evidence": "source overlay only; linked Catch2 execution not established",
        "counts": counts,
        "cases": records,
    }
    return patched, manifest


def git_output(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args],
                                   stderr=subprocess.PIPE)


def existing_case_inventory(sources: dict[str, bytes]) -> list[dict]:
    """Derive the prior selected cases from exact source, without vendoring names."""
    records = []
    for relative, (required_tag, expected_count) in EXISTING_SOURCE_SPECS.items():
        raw = sources[relative]
        if git_blob(raw) != ORIGINAL_BLOBS[relative]:
            raise ValueError(f"existing test source mismatch: {relative}")
        source = raw.decode("utf-8")
        selected = [match for match in ALL_CASE_HEADERS.finditer(source)
                    if required_tag in re.findall(r"\[[^\[\]]+\]", match[2])]
        if len(selected) != expected_count:
            raise ValueError(f"existing case inventory mismatch: {relative}")
        records.extend({
            "name": match[1], "source_path": relative, "tags": match[2],
            "original_line": source.count("\n", 0, match.start()) + 1,
        } for match in selected)
    if len({case["name"] for case in records}) != 33:
        raise ValueError("existing case names must be unique")
    return records


def checked_file(root: Path, relative: str) -> Path:
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError(f"guarded source is not a regular in-checkout path: {relative}")
    if not path.is_file():
        raise ValueError(f"missing guarded source: {relative}")
    return path


def reconcile(root: Path, *, verify_applied: bool = False) -> dict:
    root = root.resolve(strict=True)
    top = Path(git_output(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if top != root:
        raise ValueError("pass the exact Eden checkout root")
    commit = git_output(root, "rev-parse", "HEAD").decode().strip()
    if commit != EDEN_COMMIT:
        raise ValueError(f"wrong Eden revision: expected {EDEN_COMMIT}, found {commit}")
    original = git_output(root, "show", f"{EDEN_COMMIT}:{TEST_PATH}")
    patched, manifest = transform(original)
    for relative, expected in ORIGINAL_BLOBS.items():
        if verify_applied and relative == TEST_PATH:
            expected = manifest["patched_test_blob"]
        actual = git_blob(checked_file(root, relative).read_bytes())
        if actual != expected:
            raise ValueError(f"frozen source mismatch: {relative}: expected {expected}, found {actual}")
    cmake = (root / CMAKE_PATH).read_text()
    if cmake.count("    core/native_gpu_characteristics.cpp\n") != 1:
        raise ValueError("original native GPU test CMake entry must remain enabled")
    manifest["existing_cases"] = existing_case_inventory({
        relative: (root / relative).read_bytes() for relative in EXISTING_SOURCE_SPECS
    })
    if ({case["name"] for case in manifest["cases"]} &
            {case["name"] for case in manifest["existing_cases"]}):
        raise ValueError("restored and existing case names overlap")
    manifest["combined_filter"] = COMBINED_FILTER
    manifest["counts"].update(existing_cases=33, combined_selected_cases=62)
    if not verify_applied:
        (root / TEST_PATH).write_bytes(patched)
    manifest["overlay_state"] = "verified_applied" if verify_applied else "applied"
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eden_checkout", type=Path)
    parser.add_argument("--verify-applied", action="store_true",
                        help="check the exact applied result without modifying source")
    parser.add_argument("--manifest", type=Path,
                        help="write case inventory and source identities as JSON")
    args = parser.parse_args()
    try:
        manifest = reconcile(args.eden_checkout, verify_applied=args.verify_applied)
        if args.manifest:
            args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"NX2_NATIVE_GPU_OVERLAY_REFUSED: {error}\n")
    print(f"NX2_NATIVE_GPU_OVERLAY_STATE={manifest['overlay_state']}")
    print(f"NX2_NATIVE_GPU_OVERLAY_TEST_BLOB={manifest['patched_test_blob']}")
    print("NX2_NATIVE_GPU_CANDIDATES=29")
    print("NX2_NATIVE_GPU_UNCHANGED_BODIES=24")
    print("NX2_NATIVE_GPU_COMPATIBILITY_CASES=5")
    print("NX2_NATIVE_GPU_UNRESOLVED_CASES=2")
    print("NX2_NATIVE_GPU_COMBINED_EXPECTED_CASES=62")
    for name in UNRESOLVED_CASES:
        print(f"NX2_NATIVE_GPU_UNRESOLVED={name}")
    print("NX2_NATIVE_GPU_LINKED_CATCH2_EXECUTION_NOT_ESTABLISHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
