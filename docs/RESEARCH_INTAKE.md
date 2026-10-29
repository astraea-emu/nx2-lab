# Switch 2 research intake — independent evidence before claims

**Status: protocol only. No Switch 2 console was accessed by NX2 Lab.**

Purpose: make public and consented local hardware observations useful to
security researchers and emulator developers without laundering rumors,
proprietary bytes, identifying data, or unverified exploit-success claims.

## Classification

Record each claim as exactly one of:

- `source_owned_host`: behavior reproduced in our independent host code;
- `public_upstream_report`: explicitly attributed upstream report, not ours;
- `authorized_local_observation`: measured with permission on a specific
  privately controlled console, with confidential raw logs kept outside Git;
- `unverified_hypothesis`: potentially useful, not executable truth.

Separate *execution context* from *firmware* and from *outcome*:

- context: web/SmileBASIC process, graphics task, system module, kernel,
  persistent boot, or unknown;
- firmware: exact version when confirmed, or unknown;
- duration: one session, survives app exit, survives reboot, or unknown;
- outcome: observed instruction/report, visual-only evidence, reproducible
  bounded service effect, or an unconfirmed claim.

One observation in a system module does **not** imply kernel privileges,
complete address-space control, independent homebrew, or persistent custom
firmware. A GPU-drawn demo does **not** imply an emulator supports Switch 2
native executable loading.

## Minimal public issue/report shape

| Field | Meaning |
| --- | --- |
| Source URL + immutable revision | Primary, authorized public evidence |
| Report date | When observed/published, not when reposted |
| Console/host configuration | Only generic hardware and firmware version |
| Execution context | Which process, service or privileges are actually evidenced |
| Procedure class | Read-only, generated homebrew probe, or risk-bearing system modification |
| Observed facts | Precise positive result and negative/failed cases |
| Confidence / limitations | Unknown fields stated explicitly |
| Safety/consent | Authorized ownership and rollback/abort plan, when relevant |
| Emulator dependency | Which independent CPU/IPC/GPU behavior this could establish |

## Never publish

Unique console identifiers, account/session IDs, USB captures with personal
metadata, keys, Nintendo firmware/game binaries, raw proprietary code, device
certificates, private vulnerability details awaiting coordinated disclosure,
or unredacted host logs. Keep reproducible *owned* fixtures under `fixtures/`.

## Initial primary report register

- `ns2jb` original by pepsipu: https://gitlab.com/pepsipu/ns2jb — public
  report of firmware-specific, tethered system-module execution; **no local
  independent run here**, no claim of persistence or full kernel ownership.
- `mac2jb`: https://github.com/cpypwn/mac2jb — third-party host workflow;
  its published versions and security assumptions must be individually
  reviewed before any hardware step. **Do not disable host protections by
  default**; this is an external research tool, not a NX2 Lab dependency.
- `HBLauncher`: https://github.com/ravensclawx/HBLauncher — independently
  maintained SmileBASIC homebrew workflow. Treat guest environment and
  graphics demos as unverified until exact revisions/outputs are examined.

First safe research task: classify source and capability claims in public
reports, identify contradictory firmware/version statements, and propose
small, source-owned, non-destructive tests that would discriminate between
hypotheses. No automatic exploit execution or console updates are part of
this repository's default workflow.
