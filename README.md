# NX2 Lab

A research lab for Switch 2 emulation: original guest workloads, repeatable
external-runtime tests and a small AArch64 CPU/memory correctness oracle.

Original ARM64 guests complete checked IPC and display a CPU-drawn image
through a pinned Eden build on Linux. Both original and edited images match
every expected captured pixel and exit naturally. This establishes one
presentation path; NX2 has no developer SDK or verified game compatibility.

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
