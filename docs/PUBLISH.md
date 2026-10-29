# NX2 Lab — GitHub publication and history

**Live repository:** https://github.com/astraea-emu/nx2-lab

The complete **36-file tracked source tree** was published through the
connected GitHub Git-object API on 2026-10-29, with tree SHA
`0323c4d08a2d755e597c18eaa02a7f09f59be28a`.
This exactly matches the source tree at the original locally tested
commit `c133acb6dd534ec55374edec01484fe8dd0eec05`.

GitHub's `main` was initialized using a new publication commit
(`ab4baa5d2e66659c2f6e9a1456d2ba0d1bfb966c`).
Its **commit history** therefore differs from the original seven-commit
local development history. That original history is preserved separately
in `nx2-lab-20261029-v2.bundle`, supplied with the handoff.
No force-push or history rewrite is necessary for future development.

## Normal contributor workflow

```sh
git clone https://github.com/astraea-emu/nx2-lab.git
cd nx2-lab
cmake -S . -B build -DBUILD_TESTING=ON
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```

Create a feature branch, test it locally, and open a pull request.
GitHub Actions runs Linux, Windows, macOS and Linux sanitizers.
Use the PR's **exact final head** and successful checks before merging.

## Evidence-byte portability

The source-owned evidence manifests hash exact bytes. The repository's
`.gitattributes` forces LF line endings for text files on every checkout
and preserves `*.nx2o` binary fixtures unchanged. This prevents Windows
`core.autocrlf` transformations from invalidating reproducible hashes.

Never publish proprietary Nintendo firmware, games, encryption keys, personal
console captures or privileged host secrets. The NX2OWNED file format is
project-authored, not a Nintendo executable format.
