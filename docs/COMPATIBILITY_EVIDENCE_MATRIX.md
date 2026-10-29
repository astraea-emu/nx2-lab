# Switch 2 research evidence matrix — provisional v0 (2026-10-29)

**Purpose:** inventory falsifiable, *public-source* hypotheses and select the
smallest meaningful conformance workloads. This is **not** a platform spec,
hardware trace, security finding or proof of software compatibility.

**Evidence levels:** 0 rumor; 1 third-party documentary/source claim;
2 independently audited source at exact revision; 3 reproduced **host-only**
experiment; 4 authorized physical device observation; 5 emulator/device parity.
No row below has an NX2-collected level-4/5 Switch 2 observation.

**Firmware applicability:** Wiki statements may refer to multiple firmware
versions. Unless dated exact target evidence is available, write "not frozen".
HBLauncher, SmileBASIC and console session reports must never be silently
generalized across versions.

| ID | Research assertion from public source | Current provenance / evidence | Firmware | Critical unknown | Proposed independently repeatable first check |
| --- | --- | --- | --- | --- | --- |
| C-01 | Switch 1 backward compatibility uses `nnCompatTrampoline`, `nnCompatThin`, and `nnCompat` loaded alongside the title | Switchbrew compatibility-mode wiki (level 1) | not frozen | Exact mapping order, identity and loader effects | Source-owned module-list fixture; confirm ordering only with authorized device measurements |
| C-02 | Compatibility binaries use pointer authentication (PAC) | Switchbrew compatibility-mode wiki (level 1) | not frozen | Which entries and keys, and version/ABI differences | Isolated ARM PAC feature-census fixture; prohibit guessed signing behavior |
| C-03 | Compatibility process capabilities include SVC `0x54`, `0x80` beyond original NPDM specification | Switchbrew compatibility-mode wiki (level 1) | not frozen | Whether acceptance is per title/revision and actual failure return | Declarative process-capability contract and denied-SVC negative on a simulator |
| C-04 | Back-compat core mask reports may hide cores via `nn::os::GetThreadAvailableCoreMask` | Switchbrew compatibility-mode wiki (level 1) | not frozen | Observed vs effective mask and process topology | Two explicit source-owned logical/effective mask cases with diverging expected results |
| C-05 | `nn::os::GetSystemTickFrequency` differs: reported `31,250,000` instead of `19,200,000` | Switchbrew compatibility-mode wiki (level 1) | not frozen | Exact context, conversion precision, error behavior | Versioned frequency-to-ticks corpus with overflow, rounding and monotonicity negatives |
| C-06 | `nn::os::ConvertToTick` uses a compatibility-adjusted conversion | Switchbrew compatibility-mode wiki (level 1) | not frozen | Rounding/overflow and clamping semantics | Two independent integer model implementations and boundary/overflow cases |
| C-07 | Selected graphics `gl*`, `egl*`, `vk*` APIs may be translated in compatibility mode | Switchbrew compatibility-mode wiki (level 1; some descriptions explicitly speculative) | not frozen | Actual command/resource semantics and driver version | Small source-authored one-frame shader/draw test; no hardware claim without reference output |
| C-08 | Compatibility hooks may alter VI/display-facing interfaces | Switchbrew compatibility-mode wiki (level 1) | not frozen | Whether `vi:u` routing changed; API/provider semantics | Abstract display request/response schema with explicit unsupported status |
| C-09 | Specific applet and socket calls add waits or synchronization in some compatibility paths | Switchbrew compatibility-mode wiki (level 1) | not frozen | Predicate, duration, synchronization and false positives | Timed event-state mock with two bounded ordering negatives |
| C-10 | Compatibility data may serialize certain savedata operations | Switchbrew compatibility-mode wiki (level 1) | not frozen | Scope of locking, ordering and failure modes | Source-owned concurrent state-machine/property test; no Nintendo save data |
| C-11 | HBLauncher publishes a *custom* HBX ABI v3 native AArch64 SDK and a host/QEMU test route; separately reports a SmileBASIC session on-device route | HBLauncher MIT source at `18b4748ba98eeac7df17beb5d3418985eb74897c`, `sdk/abi.json` Git blob `c143bba98182d22240bfbc692ebc2dbaa3059c9d` (source level 2, host testing distinct from device claim level 1) | On-device route firmware applicability not independently reproduced | HBX context/trampoline rules versus actual Horizon interfaces; host/device parity unproven | Reproduce unmodified `tests/abi/build.sh` under QEMU; independently check ABI layout and malformed-input negatives; then freeze stage-1 `Hello CPU` guest source |
| C-12 | ns2jb author reports tethered `fs` / userland code execution, not persistent kernel CFW | Original pepsipu October 2026 report (level 1; **not** reproduced on hardware by NX2) | author reports 23.0.1 | Replication conditions, privilege differences and firmware scope | Research citation/provenance inventory only; no exploit reproduction in public CI |

## First candidate tests

**Candidate A: compatibility clock semantics (C-05 and C-06).** Freeze
two publicly described clock-rate models and a no-console, author-created
integer boundary test. Use results to discover ambiguous rounding and
overflow contracts, not to claim a physical device matches either model.

**Candidate B: visible core affinity (C-03/C-04).** Model logical vs raw
core masks with deliberately incompatible expected outputs. Obtain actual
authorized observations later, and promote only the measured subset.

**Candidate C: HBLauncher hello-CPU program (C-11).** Review exact MIT
source revision, independently build it off-device and compare a bounded
CPU/entry trace with its published host-side test; avoid assuming standard
Switch NRO, Horizon SVC or verified on-console execution from a mock backend.

## Falsification conditions

- A wiki claim is not an observed hardware fact; document contradictions,
  build revisions, hardware context and uncertainty instead of choosing the
  result the emulator already returns.
- A Switch 1 NRO passing under a PC interpreter is **not** Switch 2 commercial
  support.
- A generic Linux ARM64 SVC #0 test is **not** a Horizon service probe.
- Third-party GUI demos, release names, and screenshots do not replace exact
  source-to-executable or hardware readback evidence.
- Security vulnerabilities and exploit chains are separate: this matrix
  contains only public research leads, not unknown vulnerabilities.

## Sources (snapshot / provenance)

1. Switchbrew, "Switch 2: Compatibility Mode", public page last inspected
   October 29, 2026; revision reference `oldid=15275`:
   https://switchbrew.org/wiki/Switch_2:_Compatibility_Mode
2. HBLauncher original public MIT repo; source and README snapshot inspected
   2026-10-29: https://github.com/ravensclawx/HBLauncher
3. Original ns2jb researcher, `pepsipu` (October 18/22 context):
   https://pepsipu.com/blog/2026-10-switch2-jailbreak-ns2jb/
4. Dynarmic E1 and source-owned generic Linux AArch64 ELF E2 remain separate
   proofs in this repository; neither provides NX2 Switch 2 hardware evidence.

## Next update acceptance

Every row must eventually gain exact source hash/revision, source license,
explicit test program ID, expected state/effects, negative controls, actual
measured run count, evidence level, and owner. Promote a row to level 4
**only** with a consented hardware observation and provenance preserved
outside public proprietary artifacts.
