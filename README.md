# NX2 Lab

Independent conformance tools and source-authored workloads for Switch 2
emulation research. The MIT lab contains a small AArch64 correctness oracle
and reproducible tests of separately built emulator runtimes.

**Current result:** 62 native unit cases pass in a pinned Eden source build;
original synthetic ExeFS guests also complete checked service-manager IPC and
natural exit on Linux. **Next:** native display service lifecycle checked by the guest.
Production-engine selection remains **HOLD**. No hardware ABI
parity, guest-produced frame or commercial-game support is established.
See [measured status](docs/STATUS.md) and [the active plan](docs/PLAN.md).

## Build and run

Requires CMake 3.25+ and a C++23 compiler. Install Python 3 to include the
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
`run-owned` accepts the small project-authored **NX2OWNED** test format.
These commands exercise the local CPU/memory oracle; external emulator
experiments have separate source-pinned workflows.

## Find your way

| Need | Start here |
| --- | --- |
| Verified results, limits and research records | [Status](docs/STATUS.md) |
| Next workload and acceptance criteria | [Plan](docs/PLAN.md) |
| Build, test and contribute | [Contributing](CONTRIBUTING.md) |
| How architecture decisions change | [Adaptive strategy](docs/ADAPTIVE_STRATEGY.md) |
| Authorized device research and evidence handling | [Security](docs/SECURITY.md) · [Research intake](docs/RESEARCH_INTAKE.md) |

| Location | Contents |
| --- | --- |
| [`include/nx2/`](include/nx2/) and [`src/`](src/) | Bounded CPU, memory, owned-image and service-stop oracle |
| [`tests/`](tests/), [`fixtures/`](fixtures/), [`evidence/`](evidence/) | Original tests, tiny inputs and byte-hashed manifests |
| [`tools/reference/`](tools/reference/) | External-runtime probes, generators, assessors and source-checked overlays |
| [`.github/workflows/`](.github/workflows/) | Core CI and separately scoped runtime experiments |
| [`docs/research/`](docs/research/) | Dated experiments, failures and exact provenance |

## Scope and license

Original NX2 code and documentation are [MIT-licensed](LICENSE), unless marked
otherwise. External GPL implementations stay in separate research builds;
reusing or distributing them requires their own license review. Console
firmware, keys, games and identifying device data do not belong in this repo.

Guest execution uses the ordinary CI runner account, without a console.
Build dependencies are installed separately in disposable CI environments.
NX2 is independent of Astraea's PS5 work and is unaffiliated with Nintendo,
NVIDIA or the external emulator projects.
