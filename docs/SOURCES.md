# Evidence

These records are frozen at
[`23f536a21a6ca029a01da8c70e48d4d40628452c`](https://github.com/astraea-emu/nx2-lab/commit/23f536a21a6ca029a01da8c70e48d4d40628452c).
They preserve source pins, input hashes, procedures, failures and measured
limits. Historical next steps and coverage statements are superseded by
[current status](STATUS.md) and [the active plan](PLAN.md).

| Experiment | Frozen records |
| --- | --- |
| CPU, memory and external ELF controls | [CPU reference baseline](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/cpu_reference_baseline_2026-10-31.md) |
| Custom HBX ABI and original guest | [Host/QEMU intake](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/hblauncher_host_abi_2026-10-29.md) · [Original entry and write accounting](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/hblauncher_original_guest_2026-10-29.md) |
| Eden original-header contracts | [Source qualification](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/runtime_baseline_eden_ns2_2026-10-30.md) |
| Integrated build and native GPU tests | [Earlier build failures and reduced suite](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/eden_ns2_full_build_gate_2026-10-30.md) · [Reconciliation, linked result and DMA exclusions](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/eden_native_gpu_test_reconciliation_2026-10-31.md) |
| NRO execution and input checks | [Original/adapted lifecycle and AES assertion](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/eden_nro_guest_probe_2026-10-30.md) · [Conservative preflight and unresolved loader bounds](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/eden_nro_input_preflight_2026-10-30.md) |
| NPDM object reuse | [Original C++ failure and isolated reset](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/eden_ns2_npdm_reload_2026-10-30.md) |
| Synthetic native ExeFS | [Original fixture and priority correction](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/eden_native_exefs_fixture_2026-10-30.md) · [Runtime lifecycle and checker correction](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/eden_native_exefs_runtime_2026-10-31.md) |
| Guest-checked service-manager IPC | [Observed replies, controls and interface limits](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/research/eden_native_ipc_runtime_2026-10-31.md) |

Earlier context: [strategy](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/STRATEGY_2026-10-29.md),
[architecture audit](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/COMPETITIVE_ARCHITECTURE_AUDIT_2026-10-30.md),
[competitive snapshot](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/COMPETITIVE_RESEARCH_2026-10-29.md),
and [research-lead matrix](https://github.com/astraea-emu/nx2-lab/blob/23f536a21a6ca029a01da8c70e48d4d40628452c/docs/COMPATIBILITY_EVIDENCE_MATRIX.md).
The [complete documentation snapshot](https://github.com/astraea-emu/nx2-lab/tree/23f536a21a6ca029a01da8c70e48d4d40628452c/docs)
also retains the former process, intake and publication records.

Git preserves these reports, not the lifetime of linked Actions artifacts.
Artifact downloads have separate retention; a recorded digest does not make
the raw archive permanently available. The records identify the pinned
workflows and source needed for reproduction.
