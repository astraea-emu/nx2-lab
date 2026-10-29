# Public references — reviewed 2026-10-29

Source category, provenance, and confidence matter. This is not a list of
things the new codebase has implemented.

## Primary references

- pepsipu, original ns2jb: https://gitlab.com/pepsipu/ns2jb
  - Demonstrated tethered filesystem-sysmodule research on firmware 23.0.1.
  - No public production custom firmware/kernel access claim.
  - No permission or compatible license to copy its code established.
- pepsipu, detailed research write-up:
  https://pepsipu.com/blog/2026-10-switch2-jailbreak-ns2jb/
- Nintendo official Switch 2 hardware specification:
  https://www.nintendo.com/en-ca/gaming-systems/switch-2/tech-specs/
- Community SoC research (provisional model-specific details):
  https://switchbrew.org/wiki/Switch_2%3A_Tegra_T239
- Nintendo current Switch 2 system releases:
  https://www.nintendo.com/en-gb/Support/Nintendo-Switch-2/System-Update-Information-for-Nintendo-Switch-2-2843738.html
- oboromi main repository: https://github.com/0xNikilite/oboromi
- Pound main repository: https://github.com/pound-emu/pound
- Ballistic ARM64 recompilation research: https://github.com/pound-emu/ballistic
- mac2jb (Mac research; READ SECURITY.md before any use):
  https://github.com/cpypwn/mac2jb
- Source-owned homebrew infrastructure (Switch 1—not automatically Switch 2):
  https://github.com/switchbrew/libnx

## Confidence categories

- **Verified here:** source-owned code compiled, tested and independently
  reproducible on the host.
- **Primary reported:** upstream publishes a dated result; not reproduced by us.
- **Comparative:** third-party emulators or news; do not promote to hardware truth.
- **Unknown:** behavior requiring independent lawful observation.

The reported Switch 2 CPU/GPU architecture (T239, A78C, NVIDIA Ampere) helps
choose research directions but is NOT an authenticated ABI/ISA test corpus.
