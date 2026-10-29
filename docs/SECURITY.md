# Security, clean-room and responsible device research

Scope: controlled research on hardware and software you are authorized to
examine. This repository contains no payloads, unauthorized access tooling,
firmware, decryption keys, content dumps, or arbitrary device-modification
scripts. Public CI must not contact a console.

The original ns2jb is a complex, timing-sensitive proof-of-concept requiring
specific firmware and software. A reported filesystem-service execution path
is not a persistent custom firmware or kernel exploit. Do not treat a third-
party fork as authenticated simply because it builds. Check source revision,
license, reproducibility and potential host/console effects first.

`mac2jb` publishes a USB-host workflow which may require reducing macOS
System Integrity Protection and/or installing an unsigned extension. **Do not
change SIP/security settings or run it on a primary personal Mac as an
unreviewed convenience step.** Use a dedicated disposable research setup,
review all code and vendor drivers first, and obtain explicit authorization.

For any future approved hardware observation: document exact firmware,
minimal source build, device model, effective permissions, risk/abort plan,
expected effects, clean baseline, reproducibility and data minimization.
No account tokens, console identifiers, firmware dumps, game bytes or keys
should be collected into public reports. Never test third-party devices,
accounts or networks without consent. Coordinate responsibly with upstream
maintainers when discovering a new flaw.

Jurisdiction matters. In Canada, Copyright Act section 41.12 includes a
purpose-specific interoperability exception; it does not grant blanket
permission to distribute decryption tools or copyrighted software. Nintendo's
console terms contain separate restrictions. Seek qualified legal advice for
shipping security circumvention software or commercial game support.
