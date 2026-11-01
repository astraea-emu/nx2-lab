# Contributing

Tie each change to a measured failure or an acceptance criterion in the
[active plan](docs/PLAN.md). [Status](docs/STATUS.md) owns current results;
[Evidence](docs/SOURCES.md) links the complete historical records.

## Local checks

Requires Git, Python 3.9+, CMake 3.25+, a C++23 compiler and GNU AArch64
binutils (`as`, `ld`, `objcopy`; Debian/Ubuntu: `binutils-aarch64-linux-gnu`).
From the repository root, run:

```sh
python3 tools/ci/check.py
```

This checks local Markdown file targets, builds the core, runs CTest and
Python/ELF regressions, and assembles the original SM, VI2 and image guests. It does
not fetch or execute an external engine. Missing assembler tools fail the check.
Use `NX2_AARCH64_PREFIX` for a tool prefix other than `aarch64-linux-gnu-`.

`--build-dir PATH` selects a build directory; `--python-only` omits the core
build and CTest. The portable [core quick start](README.md#build-and-run)
works without a cross-assembler on Linux, Windows and macOS.

Source-backed tests require `NX2_EDEN_SOURCE` pointing to the pinned Eden
checkout; they explicitly skip locally without it. The relevant external
workflows supply that source and require the runtime checks.

## Original image trial (Linux)

The local runner and [runtime workflow](.github/workflows/p0-eden-native-exefs-runtime.yml)
use the same pinned Eden source, recorded repairs and build recipe.
The full engine requires Linux, CMake 3.31+, Clang and the listed development
packages. CI qualifies Ubuntu 26.04 with Lavapipe; other environments remain
unqualified. Install prerequisites once, from the repository root:

```sh
python3 tools/reference/eden_ns2/build_native_engine.py --print-packages
sudo apt-get update
sudo apt-get install $(python3 tools/reference/eden_ns2/build_native_engine.py --print-packages)
```

Then run:

```sh
python3 tools/reference/eden_ns2/run_native_frame.py --both
```

The first invocation fetches and builds the engine under `build/native-engine/`,
then assembles and runs two original guest colour variants. Repeat the same
command to validate and reuse the engine, run its incremental build and create
fresh Vulkan captures. Both variants must match their independent pixel
references and fail each other's reference. Exit 0 and
`NX2_ORIGINAL_FRAME_PASS` mean the complete trial passed.

Each invocation saves images, raw logs, source/build hashes and measured times
in a new directory under `build/native-frame/`. Use `--engine-dir` and `--output`
to select other locations. Changed engine inputs or an interrupted build require
a fresh engine directory; existing files are never reset or cleaned. The recipe
records system package versions but does not provide a hermetic toolchain.

`--eden-revision` selects either exact revision recorded in [Status](docs/STATUS.md).
Use a separate `--engine-dir` for each revision; an existing engine cannot be
reused across revisions. CI compares separate builds and compiler caches on
separate runners, and records when a cache was seeded from baseline objects.

To exercise original guest GPU commands and shaders through the same engine:

```sh
python3 tools/reference/eden_ns2/run_native_frame.py --gpu-triangle --both
```

This runs magenta and green triangles plus a clear-only control. It requires
strict native execution, exact runtime shader bytes, independently calculated
pixels, saved capture before cleanup and natural exit for all three guests.
The clear-only image must fail both triangle references. Exit 0 and
`NX2_ORIGINAL_GPU_TRIANGLE_PASS` identify the complete result. Each fresh output
directory retains the original input hashes, shader snapshots, captures and logs.
Current qualification and remaining limits are in [Status](docs/STATUS.md).

To run four frames with two reused image buffers and an edited vertex sequence:

```sh
python3 tools/reference/eden_ns2/run_native_frame.py --gpu-animation --both
```

Both variants keep the same original shaders. The guest changes vertices and
alternates buffers; all four completed images must match independent references.
The checker requires each saved capture before the next memory update, checked
GPU fences and display release, complete cleanup and natural exit. A fixed
capture allowance is not proof of completion. Exit 0 and
`NX2_ORIGINAL_GPU_ANIMATION_PASS` identify a complete passing trial. Each output
retains four separate captures, callback records, stdout and the engine log.

## External-runtime changes

A reference probe, fixture, assessor or overlay change needs its relevant
[workflow](.github/workflows/) as well as local checks. Record the tested
revision, actual runtime output, limitations and a negative control. A passing
generator or mock does not establish guest execution or hardware behavior.

Keep external implementation and test bodies in separate source builds.
Overlays must verify input revisions/blobs and replacement sites, report the
applied diff, preserve original assertions and declare omitted coverage.
Review provenance and dependency licenses before reusing external code.

## Before merging

Explain the problem, resulting behavior, verification and remaining limits.
Use positive and negative controls for behavior changes. Keep documentation
links valid, preserve historical failures and source pins, and require passing
checks for the final PR head. Add a document only when the existing six cannot
serve a distinct reader need; record routine investigation in the relevant issue.

Evidence manifests hash exact bytes: preserve the repository's LF and binary
fixture rules and verify affected manifests. Follow the
[research scope](docs/SECURITY.md) for inputs, data and disclosure.

## Licensing contributions

Submit original contributions under [GPL-3.0-only](LICENSE). Contributors retain
their copyright; contributing does not assign it to the maintainer. Preserve
third-party copyright and license notices, and review external material before
adding it.
