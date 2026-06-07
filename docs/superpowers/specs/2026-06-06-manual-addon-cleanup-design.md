# Design: MANUAL.md cleanup — align with `%post`-driven oscap architecture

**Date:** 2026-06-06
**Status:** Active. Pre-existing documentation debt that should land before tagging v0.2.0.
**Companion plan:** `docs/superpowers/plans/2026-06-06-manual-addon-cleanup-implementation.md` (to be written next)

## Problem

The v0.1.0 architecture pivot dropped `%addon org_fedora_oscap` and the
`oscap-anaconda-addon` package in favor of running `oscap xccdf eval
--remediate` directly from a `%post` block. The CHANGELOG, the new
§5.4 paragraph from PR #3, and the actual generated kickstart all
reflect that. But MANUAL.md's earlier sections still describe the
addon-driven architecture as if it were current:

- §1 "What ks-gen is" says STIG is applied "via the
  `oscap-anaconda-addon`".
- §3.1's bundle-contents table claims `tailoring.xml` is "referenced
  by `%addon org_fedora_oscap`".
- §3.2 says "Everything else is owned by `oscap` remediation via the
  `%addon org_fedora_oscap` block".
- §3.3's execution-timeline diagram shows
  `%packages -> %addon org_fedora_oscap [...] -> %post -> reboot`.
- §4.10's `packages.required` example includes `oscap-anaconda-addon`
  as a default — **contradicts `src/ks_gen/config.py:148-160`**, which
  does NOT include it.
- §10 troubleshooting references a lint error string `missing: %addon
  does not reference tailoring.xml` that does not exist in the current
  `src/ks_gen/lint.py`.
- §10 troubleshooting claims "The `%addon org_fedora_oscap` block
  runs *before* `%post`" — the *correct* current ordering is "the
  oscap remediation `%post` block runs before the rule-overrides
  `%post` block".

An operator who reads §3 will get a contradictory picture against
§5.4 (added by PR #3) and against the generated `ks.cfg`. The
package-list discrepancy is the worst of these — anyone who copies
the manual's example into their `host.yaml` will install an unused
package that doesn't even exist on AlmaLinux 9 anyway.

Final-branch code review of PR #3 (commit `ffb1e4e`) surfaced this
debt. Reviewer flagged 6 lines; subsequent verification found
9 sites total plus a related log-file note (10 sites).

## Goals

- Every MANUAL.md sentence that describes the install-time oscap
  architecture matches the current `%post`-driven implementation.
- The `packages.required` example matches `config.py`'s actual
  defaults.
- The §10 troubleshooting entries for oscap-related lint errors
  reference real, current lint error keys.
- The §10 log-file pointer mentions all three `/root/` logs the
  current install writes (`ks-post-oscap-fetch.log`,
  `ks-post-oscap.log`, `ks-post.log`).

## Non-goals

- Removing the glossary entry for `oscap-anaconda-addon` (§11) or
  the references-section link to its GitHub (§12). The addon is a
  real upstream project an operator may encounter in Red Hat docs
  or third-party tutorials; the glossary stub helps them place it
  in the SCAP ecosystem even though ks-gen does not use it.
- Broader §3 modernization beyond the enumerated sites. No new
  architecture diagrams, no expanded "how Anaconda runs `%post`"
  explainer.
- Touching MANUAL.md §5.4 — PR #3 already updated that section.
  This branch must branch from `main` (not from the PR #3 branch)
  to keep the two changes independent on the merge queue.

## Design

### Edit sites and replacement text

> **Note on site numbering.** This spec uses sites 1-7 + 10,
> matching the brainstorming catalog. The gap (8, 9) is the
> glossary entry and references-section link in §11/§12 of
> MANUAL.md — both intentionally excluded per Non-goals.

**Site 1 — MANUAL.md:31 (§1).**

Old:

```
`scap-security-guide` profile (via the `oscap-anaconda-addon`), driven by a per-host `tailoring.xml`.
```

New:

```
`scap-security-guide` profile (`oscap xccdf eval --remediate` invoked from `%post` at install time), driven by a per-host `tailoring.xml`.
```

**Site 2 — MANUAL.md:131 (§3.1 bundle-contents table).** The `tailoring.xml` table row.

Old (the row's "What it is" + "Who reads it" cells):

```
| `tailoring.xml` | An XCCDF 1.2 tailoring document referenced by `%addon org_fedora_oscap`. | `oscap` during Anaconda's remediation phase. |
```

New:

```
| `tailoring.xml` | An XCCDF 1.2 tailoring document staged into the target rootfs by a `%post --nochroot` block at install time, then passed to `oscap --tailoring-file`. | `oscap` during the install-time `%post` remediation phase. |
```

**Site 3 — MANUAL.md:145-146 (§3.2).**

Old:

```
in v0.1. Everything else is owned by `oscap` remediation via the
`%addon org_fedora_oscap` block.
```

New:

```
in v0.1. Everything else is owned by `oscap` remediation via a
`%post` block that runs `oscap xccdf eval --remediate` directly.
```

**Site 4 — MANUAL.md:160 (§3.3 execution timeline diagram).**
Replace the single-line `%packages -> %addon org_fedora_oscap
[reads tailoring.xml, remediates] -> %post -> reboot` with a
four-line vertical form:

```
%packages
  -> %post --nochroot [stages tailoring.xml]
  -> %post [oscap reads tailoring.xml, remediates]
  -> %post [ks-gen rule overrides]
  -> reboot
```

Vertical form because three `%post` blocks make the linear form
unwieldy.

**Site 5 — MANUAL.md:387 (§4.10 packages.required example).**
DELETE the `oscap-anaconda-addon` line. Verified against
`src/ks_gen/config.py:148-160` — the actual `Packages.required`
default does not include it.

**Site 6 — MANUAL.md:968-969 (§10 troubleshooting bullet).** The
existing bullet references a lint error key that no longer exists
in `src/ks_gen/lint.py`.

Old (one bullet, DELETE):

```
- **`missing: %addon does not reference tailoring.xml`** — The addon
  block was edited. Regenerate.
```

New (four bullets, REPLACE with the actual current oscap-related
lint error keys; format mirrors the surrounding bullets — bold
backtick-wrapped error key, em-dash, brief explanation, period,
"Regenerate."):

```
- **`missing: %post --nochroot oscap fetch block`** — The leading
  `%post --nochroot` block that stages `tailoring.xml` is missing
  or its `--log=` path was hand-edited. Regenerate.
- **`ordering: oscap fetch block must precede oscap eval block`** —
  Something reordered the `%post` blocks; the fetch must run before
  the chrooted oscap eval. Regenerate.
- **`missing: hd:LABEL= branch in oscap fetch case`** — The
  `hd:LABEL=*)` arm of the fetch `case` statement was removed.
  ISO-delivered installs (`inst.ks=hd:LABEL=…`) will hard-fail
  without it. Regenerate.
- **`missing: hd: cp from /run/install/repo in oscap fetch case`** —
  The `hd:LABEL=` arm is present but the `cp /run/install/repo/...`
  line that does the actual staging was edited. Regenerate.
```

The adjacent `ksvalidator: ...` bullet (just below) stays unchanged.

**Site 7 — MANUAL.md:988-990 (§10 crypto-policy timing claim).**

Old:

```
The `%addon org_fedora_oscap` block runs *before* `%post`, so any
`crypto_policy` rule output in `%post` is too late to influence
oscap's view.
```

New:

```
The oscap remediation `%post` block runs *before* the `ks-gen`
rule-overrides `%post` block, so any `crypto_policy` rule output
in the overrides block is too late to influence oscap's view.
```

Same architectural concern (override-channel output is too late
for oscap), correct actor labels.

**Site 10 — MANUAL.md:979 (§10 log-file pointer).**

Old:

```
Check `/root/ks-post.log` (if you got far enough into `%post`) and
`/tmp/anaconda.log` on the install media or via VNC.
```

New:

```
Check `/root/ks-post-oscap-fetch.log`, `/root/ks-post-oscap.log`,
and `/root/ks-post.log` (in that order — they correspond to the
fetch / eval / overrides `%post` blocks), and `/tmp/anaconda.log`
on the install media or via VNC.
```

### Branching strategy

Branch `impl/v0.2.0-manual-cleanup` off `main` (commit `18ebddc`,
the spec+plan commits from the PR #3 brainstorming session). This
keeps the cleanup independent of PR #3 on the merge queue — either
order can land first. There are no overlapping line edits between
PR #3 and this branch (PR #3 added a paragraph in §5.4 plus the
log-count fix in §5.4; this branch touches §1, §3, §4.10, §10).

### Commit hygiene

One signed commit per the project convention. Commit subject:
`docs(manual): align with current %post-driven oscap architecture`.
Body enumerates the 7 sites + the log-file pointer with the
rationale (final-branch reviewer of PR #3 surfaced these).

Sign with the user's GPG key `BE707B220C995478`. No `--amend`, no
`--no-verify`.

### Testing

No tests to write — this is pure documentation. Local CI parity
chain (`ruff check src tests && ruff format --check src tests &&
mypy && pytest -q`) runs before the push as a sanity check that
nothing accidental leaked in.

## After this lands

The only remaining v0.1.x gap before tagging v0.2.0 is the OVAL
`--fetch-remote-resources` flag on install-time oscap. That work
is queued for a separate session.

The glossary entry for `oscap-anaconda-addon` (§11) and the
references-section link (§12) intentionally remain as historical
context — see Non-goals.
