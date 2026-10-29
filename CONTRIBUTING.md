# Contributing

Keep changes focused on one reproducible dependency. Include both a passing
fixture and a negative case. Report exact inputs, build/platform, expected and
actual behavior, source provenance and remaining limitations. Do not commit
copyrighted console code/data, credentials, private captures or claimed Sony/
Nintendo ABI semantics copied from another emulator without verification.

Run `cmake -S . -B build && cmake --build build && ctest --test-dir build
--output-on-failure`. Optional evidence checking uses Python 3.9+.

Cross-project reuse must undergo licensing and provenance review. MIT here
applies to **our original files**, not external repos, commercial games or
Nintendo APIs. External claims are leads to verify, not truths to copy.
