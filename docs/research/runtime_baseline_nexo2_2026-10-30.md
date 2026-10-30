# Issue #21 — frozen NeXo 2 runtime control (2026-10-30)

**Decision: HOLD, not selected as the production emulator.** This experiment independently tests a real external NRO loader and userland CPU/HLE path. The format and guest program are **Switch 1-style homebrew**, not a native Switch 2 executable. No game execution, GPU capability, or Switch 2 ABI has been shown.

## Exact provenance

- External project: NeXoNetwork/NeXo2-emu (GPL-3.0), source commit `7fa73a5062e64370163a248d1a0b555272012c0f`.
- Original upstream homebrew test: `tests/generated/hello.nro` at Git blob `bb0ee2a52acd303e7c800443163aa91900eabb58`, 24,636 bytes. Its source is `tests/programs/nro_hello/main.c`.
- NX2-owned external test: `tools/reference/nexo2/nro_qualification.cpp` (MIT). The exact third-party source is cloned in isolated GitHub-hosted Linux CI; it is not copied or distributed as part of the NX2 MIT repository.
- The upstream NRO invokes actual (emulated) homebrew-facing services: output-debug-string, heap allocation, memory query and system-info query; its original code computes a heap sum and Fibonacci value.

## Gate acceptance

The opt-in PR workflow `.github/workflows/p0-nexo-runtime-qualification.yml` pins the full upstream SHA and original test image Git blob. It disables app UI, JIT and TLS; it compiles the Vulkan backend with the upstream-pinned Vulkan-Headers and volk gitlinks (no GPU execution), then compiles the genuine candidate core and the NX2-owned independent tests.

1. **Positive:** unchanged external guest NRO loads, returns a valid source-defined guest entry, executes through CPU/HLE, exits, and produces the expected data counter 42, heap sum 499500, Fibonacci(50) 12586269025 and 2 MiB heap size.
2. **Negative:** an undersized NRO, corrupted NRO0 magic and truncated original file must each be rejected by the candidate loader.
3. **Unsupported boundary:** an NX2-authored synthetic SVC #0x2e must halt with the candidate's original unsupported-service diagnosis. This instruction is **not** part of the unchanged NRO and is not evidence of any Switch 2 guest's first fault.
4. **Independent corroboration:** original upstream Nro_* tests run against the same pinned checkout, including the author's malformed-input and execution routes.

Only a green **exact-PR-head** external workflow proves this narrow milestone. A clone, source review, or passing existing upstream badge alone does not qualify. Failure is a useful engineering result and must be preserved; do not replace it with mocks.

## Observed negative build case — October 30

- [Initial external CI run](https://github.com/astraea-emu/nx2-lab/actions/runs/41092044244) successfully fetched the exact NeXo source, validated the NRO blob, and configured under Ubuntu 24.04 / GCC 13.
- **Build FAILED** in the upstream `src/video_core/gpu.cpp` with Vulkan disabled: `std::unique_ptr` destructors for incomplete `NeXo2::GPU::Vulkan::Device` and `VulkanRasterizer`. This is an upstream feature-flag build limitation, not evidence that the NRO cannot run.
- The second attempt uses only the exact upstream-pinned Vulkan-Headers and volk gitlinks and compiles Vulkan; it still does **not** run GPU execution, import game data, enable JIT or adopt NeXo as the product engine. Preserve the failure as a comparison datum, even if the corrected lane succeeds.

## Explicit remaining gaps

This control does not qualify a production engine, modern Switch 2 Horizon features, Ampere/SM86/NVN2 graphics, Apple Silicon, user-executable UI, native Switch 2 process formats, or lawful commercial game compatibility. Host security and complete GPL dependency provenance remain separate gates. The NeXo interpreter-only runtime is a comparison control, not the final baseline.

**Next after this acceptance:** inspect and reproduce an Eden-derived runtime's source-owned CPU/loader/GPU path under frozen revision and negative controls. Compare first observed unsupported behavior, build feasibility and dependencies before accepting any engine in issue #21.
