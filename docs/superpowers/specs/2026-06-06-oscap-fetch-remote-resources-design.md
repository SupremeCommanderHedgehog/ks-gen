# Design: `--fetch-remote-resources` on install-time oscap eval

**Date:** 2026-06-06
**Status:** Active. The last remaining v0.1-era gap, targeted at v0.2.1.
**Companion plan:** `docs/superpowers/plans/2026-06-06-oscap-fetch-remote-resources-implementation.md` (to be written next)

## Problem

The chrooted oscap remediation invocation in
`src/ks_gen/templates/ks.cfg.j2:76-81` runs:

```
oscap xccdf eval --remediate \
  --profile xccdf_org.ssgproject.content_profile_{{ cfg.meta.profile }} \
  --tailoring-file /root/tailoring.xml \
  --results-arf /root/oscap-remediation-results.xml \
  --report /root/oscap-remediation-report.html \
  /usr/share/xml/scap/ssg/content/{{ cfg.meta.scap_content }} || true
```

It does **not** pass `--fetch-remote-resources`. Any STIG rule whose
OVAL definition references a remote resource — in particular the
AlmaLinux OVAL CVE feed at
`https://security.almalinux.org/oval/org.almalinux.alsa-9.xml.bz2`,
referenced by ALSA-tied content controls — is silently skipped at
evaluation time. Structural STIG rules (file permissions, sshd
options, kernel parameters, etc.) still run, so the installer
produces what looks like a remediated system. The CVE-feed-tied
rules just never fire.

This is the last v0.1-era gap. v0.2.0 closed the other (PR #3,
`hd:LABEL=` transport).

## Goals

- The install-time oscap evaluation reaches and applies remote OVAL
  resources on online installs (HTTP transport).
- The flag's presence is a load-bearing invariant, guarded by `lint.py`
  so a future refactor cannot drop it silently.
- The change is a single-line template edit plus tests and docs —
  nothing else moves.

## Non-goals

- New configuration surface. No YAML key, no `--set` switch, no
  per-host opt-out for `--fetch-remote-resources`. If an operator
  later needs fine control, that becomes its own design.
- Retry / timeout / proxy tuning around the fetch. oscap's default
  behavior is what install-time gets.
- Refactoring the oscap %post block layout. The `--nochroot` fetch
  / chrooted eval split from PR #3 stays exactly as is.
- Changing how air-gapped (`hd:LABEL=`) installs reach OVAL.

## Air-gap behavior (and why we accept the noisy log)

The `hd:LABEL=` transport added in PR #3 was specifically built for
operators delivering kickstart media to systems with no install-time
network access. `--fetch-remote-resources` actively contacts
`security.almalinux.org` during `oscap eval`. On an air-gapped install
this fetch will fail.

The eval invocation is wrapped in `|| true`, so a fetch failure does
not abort the install — the eval still runs, OVAL-dependent rules
skip (same end state as today), and the install completes. The
visible cost is one or more failed-fetch log lines in
`/root/ks-post-oscap.log` and the same coverage gap operators have
today.

We accept this because:

- Online installs are the dominant path; they gain real CVE-tied
  coverage that v0.1 silently dropped.
- The air-gap end state is unchanged — those rules were already
  skipping. The only delta is a log line.
- Conditionally inserting the flag based on transport would require
  threading state across the `--nochroot` fetch block and the
  chrooted eval block (e.g., a marker file in `/mnt/sysimage/root/`),
  plus new lint invariants for the conditional. That complexity is
  not justified for a behavior change visible only in install logs.

MANUAL.md §10 troubleshooting will document the expected fetch
failure on `hd:LABEL=` installs so the log line is not mistaken for
a bug.

## Why between `--profile` and `--tailoring-file`

Argument order is cosmetic for oscap, but the template reads
left-to-right as "evaluate this profile with these remote resources,
using this tailoring, against this content." That matches the
man-page ordering convention and keeps the diff to a single inserted
line at a stable position. No other rationale.

## Lint invariant

Add one check to `_internal_checks` in `src/ks_gen/lint.py`: the
chrooted oscap %post block must contain `--fetch-remote-resources`.
Same pattern as the three invariants PR #3 added for the fetch /
eval split — load-bearing template state is guarded by lint, so a
future refactor that drops the flag fails CI loudly.

One RED-phase negative test in `tests/test_lint.py` (template with
the flag stripped should fail this check, all others should still
pass).

## Tests

- **Golden snapshots** (`tests/golden/__snapshots__/`): regenerate
  with `pytest tests/golden/ --snapshot-update`. The diff must be
  exactly one inserted line per rendered ks.cfg — nothing else.
  Inspect before committing.
- **`tests/test_skeleton.py`** oscap-block assertions: tighten to
  assert `--fetch-remote-resources` is present in the chrooted eval
  block. PR #3 already tightened this file; the new assertion slots
  into the same place.
- **`tests/test_lint.py`**: one new negative test for the new lint
  invariant.

## Docs

- **CHANGELOG.md** — one bullet under `### Added` of the existing
  `## [Unreleased]` heading. (The file currently uses `[Unreleased]`
  as the working area and gets promoted to a numbered heading at
  tag time. v0.2.0 content is still sitting under `[Unreleased]` as
  of 2026-06-06; promoting it to `[v0.2.0]` is intentionally out of
  scope for this work.)
- **MANUAL.md §3.3** (oscap %post timeline): mention that the
  evaluation now fetches the AlmaLinux OVAL feed at install time.
- **MANUAL.md §10** (troubleshooting): one short subsection
  explaining that `hd:LABEL=` (air-gapped) installs will see an
  expected failed-fetch log line for `security.almalinux.org`, that
  the install proceeds normally, and that CVE-tied OVAL rules will
  skip in that case. Same coverage gap as v0.1; visible now where
  it was invisible before.

## Out of scope (for completeness)

- A `--no-fetch-remote-resources` override or YAML opt-out — punted
  to a follow-up design if real operator demand emerges.
- Pre-staging the OVAL feed onto the kickstart media so air-gapped
  installs get CVE coverage too — possible future v0.3 work,
  intentionally not bundled here.

## Version target

v0.2.1 (patch). Single template line + lint check + tests + docs.
No config or behavior changes for the operator-facing CLI. Signed
tag at the merge commit, same release flow as v0.1.0 and v0.2.0.
