# NX2 Lab

Original ARM64 workloads, CPU/memory checks and reproducible external-emulator
tests for Nintendo Switch 2 research. `nx2lab` is a small test executable,
**not a game-capable Switch 2 emulator**.

## Direction

Our goal is a full NX2 emulator with leading game compatibility, correctness,
stability, performance and platform support. Rather than rebuild an entire
emulator here, we will qualify a maintained GPL engine, develop a separate
full-runtime fork and use this lab to detect regressions and measure improvements.

[Current plan](docs/PLAN.md) · [Runtime milestone](https://github.com/astraea-emu/nx2-lab/issues/50) · [Measured status](docs/STATUS.md)

## Verified baseline

On Linux, original ARM64 guests execute checked IPC and native GPU shaders
through a pinned external Eden build. Two triangle colours and a clear-only
control pass independent pixel checks. These are original test workloads,
not game compatibility results. See [Status](docs/STATUS.md) for the dated
evidence and [draft experiments](https://github.com/astraea-emu/nx2-lab/pulls)
for unmerged modern-engine work.

## Build and run

Requires CMake 3.25+ and a C++23 compiler. Install Python 3.9+ to include the
evidence checks in CTest.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON
cmake --build build --config Debug --parallel 2
ctest --test-dir build -C Debug --output-on-failure
./build/nx2lab demo
./build/nx2lab run-owned fixtures/owned-aarch64-demo.nx2o
```

With a Windows multi-configuration generator, use `build/Debug/nx2lab.exe`.
The demo executes two original AArch64 instructions and reports `x0=43`.
`run-owned` accepts the project's small NX2OWNED fixture format. These commands
exercise the local oracle. The [original image trial](CONTRIBUTING.md#original-image-trial-linux)
prepares a pinned external engine and checks fresh captures with one command;
[Status](docs/STATUS.md) records its evidence and limits.

## Project guide

| Document | Purpose |
| --- | --- |
| [Status](docs/STATUS.md) | Measured results and current limits |
| [Plan](docs/PLAN.md) | One active milestone and its acceptance criteria |
| [Contributing](CONTRIBUTING.md) | Setup, checks and change requirements |
| [Security](docs/SECURITY.md) | Authorized research and evidence handling |
| [Evidence](docs/SOURCES.md) | Exact historical records and source revisions |

The core lives in `include/nx2/` and `src/`; original inputs and checks live in
`fixtures/`, `tests/` and `evidence/`. `tools/reference/` contains external-runtime
probes, with their workflows in `.github/workflows/`.

## License

Copyright (c) 2026 nx2-lab contributors.

NX2 Lab is licensed under the [GNU GPL, version 3 only](LICENSE)
(`GPL-3.0-only`). Forks, improvements and redistribution are welcome under
those terms, including paid redistribution.

External components retain their own licenses. NX2 is unaffiliated with
Nintendo, NVIDIA or the external emulator projects.
