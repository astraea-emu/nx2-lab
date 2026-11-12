# NX2 engineering guide

Read [Plan](docs/PLAN.md), [Status](docs/STATUS.md),
[Contributing](CONTRIBUTING.md) and [Security](docs/SECURITY.md) before
substantial work. They are the source of truth; this file is a short guide.

## Objective

Build a leading Switch 2 emulator by measured software compatibility,
correctness, stability, performance and platform reach. The active delivery
milestone is [#50](https://github.com/astraea-emu/nx2-lab/issues/50).
This repository is the **regression lab**, not the distributable emulator.
A maintained full-engine fork belongs in a separate repository with its
upstream history and licence notices intact.

## Execution

1. Check the live GitHub head, relevant PRs and latest exact-head CI before
   editing. Preserve completed work rather than repeating an audit.
2. Choose the smallest change that fixes a reproduced problem or directly
   enables the active milestone. Prefer existing code and tests.
3. Preserve strict negative controls and acceptance criteria. A screenshot,
   clean build or one passing retry is not proof of compatibility or stability.
4. Run focused checks first, then full CI on the final head. Use costly external
   builds only when the source change could affect the result.
5. Record the observed behavior, exact revision, positive and negative tests,
   unresolved failures and next decision. Use `passed`, `failed` and
   `not tested` precisely.

## Standards

- Keep code and documentation concise, specific and readable. No redundant
  wrappers, status documents, repeated caveats or promotional prose.
- Prefer a coherent small PR; avoid speculative refactors or cleanup without
  a verified benefit. Do not delete historical evidence or tests casually.
- Preserve licences, authorship, source pins, tests and earlier failures.
  Do not vendor copyrighted games, firmware, keys or private logs.
- Keep draft experiments draft until validated. Do not merge, force-push,
  rewrite history or publish software without the necessary approval.
- Use issues for routine findings. Update the plan only when the direction
  changes; update status only when evidence changes.
