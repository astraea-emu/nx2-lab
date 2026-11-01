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

Source-backed overlay tests require `NX2_EDEN_SOURCE` pointing to the pinned
Eden checkout; they explicitly skip locally without it. The GPU workflow
supplies that source and requires the runtime checks.

## Original image trial (Linux)

Use the exact Eden revision and three build/lifecycle repairs in the
[runtime workflow](.github/workflows/p0-eden-native-exefs-runtime.yml).
That workflow records the complete engine build. The local runner requires
its already-built `eden-cli`, source checkout, GNU AArch64 binutils, `xvfb`,
`xauth`, `mesa-vulkan-drivers` and `vulkan-tools`.

```sh
python3 tools/reference/eden_ns2/run_native_frame.py \
  --eden-cli /path/to/eden-build/bin/eden-cli \
  --eden-source /path/to/eden \
  --both
```

This assembles and runs two original guest colour variants, reuses the engine
binary, and checks fresh Vulkan captures against independent pixel references.
It creates a new directory under `build/native-frame/` with images, raw logs,
hashes and timings. Both variants must pass; each must fail the other's pixel
reference. Exit code 0 and `NX2_ORIGINAL_FRAME_PASS` mean the trial passed.
The runner does not build or install Eden; a single-command engine setup is
still the [next step](docs/PLAN.md).

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
