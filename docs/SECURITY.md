# Research boundaries

NX2 has made no physical-console observations. Public CI must not contact a
console. Research is limited to software, devices, accounts and networks we
are authorized to examine.

## Authorization and execution

Obtain explicit, informed approval before any risk-bearing device or host
change. Establish the exact target, firmware, source revision, permitted scope,
expected effects, clean baseline, recovery route and abort conditions first.
Prefer small, non-destructive observations. Console updates and automatic
exploit execution are outside the default workflow.

Do not disable SIP or other host protections, install unsigned drivers, or
run unreviewed device tools on a primary personal machine as a convenience
step. Use a dedicated disposable research setup and review code, dependencies
and possible host/console effects before execution.

External runtime experiments use pinned public source in separate disposable
builds, without personal credentials or console access. Check provenance and
dependency licenses before reuse or redistribution. Keep external implementation
source in its separate build. Input preflight and process timeouts do not
establish safe handling of arbitrary inputs or host containment.

## Evidence

Distinguish reproduced host behavior, attributed upstream reports, authorized
local device observations and unverified hypotheses. Record the exact source
and date, observed effects, negative results and limits. For device evidence,
identify firmware, execution context, effective privileges and duration; leave
unknown fields unknown. Keep confidential raw observations outside public Git.

Host execution, screenshots and source-model tests do not establish hardware
ABI fidelity. System-module access does not establish kernel control or
persistence. A graphics demonstration does not establish native executable
loading. Report only the behavior actually checked.

## Data and disclosure

Never publish Nintendo firmware or game bytes, keys, proprietary SDK/code, device
certificates or identifiers, account/session tokens, credentials, identifying
USB captures, or unredacted host logs. Collect only what the approved experiment
needs; publish redacted findings and reproducible project-authored fixtures.

Coordinate new vulnerability findings privately with the affected maintainers
through their disclosure process. Keep private vulnerability details out of
public issues, pull requests and reports while coordinated disclosure is pending.
