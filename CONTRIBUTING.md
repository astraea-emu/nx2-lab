# Contributing

Start with [current status](docs/STATUS.md) and [the active plan](docs/PLAN.md).
Keep each change tied to one measured failure or acceptance criterion.

## Run the local checks

The complete local check requires Git, Python 3.9+, CMake 3.25+, a C++23 compiler
and GNU AArch64 binutils (`as`, `ld`, `objcopy`). On Debian/Ubuntu, the
cross-assembler package is `binutils-aarch64-linux-gnu`.

From the repository root:

```sh
python3 tools/ci/check.py
```

This checks local Markdown file links, configures a Debug build, runs CTest,
runs first-party Python and ELF mutation checks, and assembles the original IPC fixture.
It uses local source and fixtures; it does not fetch or execute an external
emulator. Missing assembler tools fail the check instead of skipping cases.
The default tool prefix is `aarch64-linux-gnu-`; use `NX2_AARCH64_PREFIX` when
your GNU toolchain has a different prefix.

Overlay tests that inspect upstream source run when `NX2_EDEN_SOURCE` points
to the pinned Eden checkout; otherwise they are explicitly skipped locally.
The GPU workflow supplies that source and requires the linked runtime tests.

Use `--build-dir PATH` for a separate build directory. `--python-only` runs
the Python and assembly checks without repeating the core build/CTest.
For the portable core-only build on Linux, Windows or macOS, follow the
[README commands](README.md#build-and-run); no cross-assembler is needed.

## External-runtime changes

The workflows in [`.github/workflows/`](.github/workflows/) define separately
pinned experiments. A change to a reference probe, fixture, assessor or overlay
needs its relevant runtime workflow as well as the local checks. Record the
exact tested revision and original runtime output. A passing generator or
mock is not evidence that the guest ran in the external engine.

Keep external implementation and test bodies in their separate source builds.
Source overlays must verify the expected input revision/blob and replacement
sites, and report the applied diff. Preserve original assertions and make any
omitted coverage explicit.

## Make the change reviewable

Explain the observed problem, the behavior changed, the evidence and tests,
and the remaining limitation. Include a positive and negative control for a
behavior change. Documentation changes should keep links valid and distinguish
current status from dated observations; preserve historical failures and pins.
Use successful checks for the PR's final tested head before merging.

Original NX2 files are MIT-licensed. Review provenance and dependency licenses
before cross-project reuse. Do not commit console firmware, keys, games,
credentials or identifying captures. See [the research scope](docs/SECURITY.md).

Evidence manifests hash exact bytes. Preserve the repository's LF text and
binary-fixture rules when editing inputs; verify affected manifests after a
change. Source-backed format experiments do not by themselves establish a
Nintendo hardware ABI.
