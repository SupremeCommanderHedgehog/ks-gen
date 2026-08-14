# SSG datastream versions pinned for audit-story analysis

The per-distro rule-ID lists under this directory were extracted from these
specific downstream `scap-security-guide` / `ssg-debderived` package versions.
**These were the versions installed on a freshly-built ks-gen host as of
2026-08-14** — i.e., what `oscap` saw at install time on that date.

> **These lists are a snapshot**, so treat the date above as the age of
> everything in this directory. Drift from them used to go unnoticed
> entirely — that was #90: AlmaLinux 8 moved from SSG 0.1.74 to 0.1.81, its
> `stig` profile switched to the `FIPS:STIG` sub-policy and dropped most of
> the FIPS-only rules it used to select, and ks-gen kept applying plain
> `FIPS` — so `configure_crypto_policy` failed on every AL8 STIG host until a
> real install turned it up. `.github/workflows/ssg-drift.yml` now re-extracts
> from the live repos weekly and opens an `ssg-drift` issue when these files
> stop matching shipping content; re-extract per the recipe below when it
> does.

| Distro | Package | Version | Source URL |
|---|---|---|---|
| AlmaLinux 8.10 | `scap-security-guide` | `0.1.81-1.el8_10.alma.1` | https://repo.almalinux.org/almalinux/8/AppStream/x86_64/os/Packages/scap-security-guide-0.1.81-1.el8_10.alma.1.noarch.rpm |
| AlmaLinux 9 (latest) | `scap-security-guide` | `0.1.81-1.el9_8.alma.1` | https://repo.almalinux.org/almalinux/9/AppStream/x86_64/os/Packages/scap-security-guide-0.1.81-1.el9_8.alma.1.noarch.rpm |
| AlmaLinux 10 (latest) | `scap-security-guide` | `0.1.81-1.el10_2.alma.1` | https://repo.almalinux.org/almalinux/10/AppStream/x86_64/os/Packages/scap-security-guide-0.1.81-1.el10_2.alma.1.noarch.rpm |
| Ubuntu 24.04 (noble) | `ssg-debderived` | `0.1.80-1` | http://archive.ubuntu.com/ubuntu/pool/universe/s/scap-security-guide/ssg-debderived_0.1.80-1_all.deb |

## Re-extraction recipe (reproducibility for SSG version bumps)

Tools needed: `curl`, `rpm2cpio`, `cpio`, `dpkg-deb`, `gzip`. On Ubuntu WSL:
`sudo apt install rpm2cpio cpio` (the rest are preinstalled).

`scripts/audit_story/fetch_shipping_datastreams.sh` downloads whatever each
distro ships *right now* — it resolves the highest `scap-security-guide` RPM in
each AlmaLinux AppStream repo and the highest `ssg-debderived` deb in noble's
universe pool, so it does not need updating when a version moves. `ssg-drift.yml`
runs this same script; keeping one copy is the point.

```bash
WORK=/tmp/ssg-extract

# Downloads the 4 datastreams and prints "<label> package: <exact filename>"
# for each (also written to $WORK/shipping-versions.txt).
scripts/audit_story/fetch_shipping_datastreams.sh "$WORK"

# Run the extractor (from the ks-gen repo root)
python3 scripts/audit_story/extract_ssg_rule_ids.py \
  --datastream alma8="$WORK/ssg-almalinux8-ds.xml" \
  --datastream alma9="$WORK/ssg-almalinux9-ds.xml" \
  --datastream alma10="$WORK/ssg-almalinux10-ds.xml" \
  --datastream ubuntu2404="$WORK/ssg-ubuntu2404-ds.xml" \
  --out-dir docs/audit-story/
```

Then update the version table above from the printed `package:` lines.

Re-running on a bump rewrites `*-rule-ids.txt`, `*-stig-selected.txt`, and
`cross-distro-rule-id-diff.md` in-place — `git diff` shows what SSG changed.

`*-stig-selected.txt` is the subset of each distro's rules that the `stig`
profile actually selects (`<select selected="true">`). It exists because
existence is too weak a guard: a rule can be in the datastream and still never
run, and disabling one of those is inert (#61).

`*-fips-candidates.txt` is the subset of the stig-selected rules whose OVAL
check or shell remediation mentions FIPS, each line carrying the markers that
matched (`check:fips`, `fix:fips-mode-setup`, …). It is a "classify me" queue,
deliberately over-inclusive: a candidate is a rule someone must judge, not a
rule that must be disabled — `aide_use_fips_hashes` is on the list and passes
fine off FIPS. See `tests/test_fips_dependent_rules.py` (#67).

## Headline numbers (snapshot of 2026-08-14)

- AlmaLinux 8: **1699** rules
- AlmaLinux 9: **1532** rules
- AlmaLinux 10: **1061** rules (added 2026-08-11 for #58; the EL10 content is
  younger than EL9's, and its `stig` profile selects **508** of them)
- Ubuntu 24.04: **642** rules
- Shared across all 4: **427** rules (universal STIG floor)
- AL9 ∩ AL10: **992** rules (65% of AL9) — the alma10 re-export gambit holds
  for 13 of 15 rules; the 2 that diverge are documented in their rule modules
- AL8 ∩ AL9: **1468** rules (86% of AL8, 96% of AL9) — confirms the alma8
  re-export gambit from #121 phase 2: the alma9 `emit_tailoring` output
  is mostly directly valid on alma8

Full distro-only sets and pairwise breakdowns: `cross-distro-rule-id-diff.md`.

The extractor rewrites that file from whatever `--datastream` set it is given,
so always re-run it with **all four** at once — a partial run silently drops
the distros you left out.

Three mechanical guards run off these lists:

- `tests/test_rule_ids_exist_in_datastream.py` asserts every SSG rule ID
  referenced by a rule **exists** in its distro's list, so a stale pin or an
  upstream rename fails the suite instead of turning into a silent no-op on a
  live host.
- `tests/test_rule_ids_selected_by_stig.py` asserts every referenced ID is
  **selected by the `stig` profile**. This is the stronger property: #61 was a
  case where the IDs existed but were never selected, so the exception looked
  real in `exceptions.md` while the checks that actually fire stayed enabled.
- `tests/test_fips_dependent_rules.py` asserts the **converse**: every
  FIPS-dependent stig-selected rule is either disabled on a MODERN/FUTURE host
  or explicitly classified as passing anyway, with a reason. #67 was the gap —
  rules that cannot pass off FIPS stayed enabled, and one of them
  (`enable_dracut_fips_module`, then stig-selected on AL8) remediated a
  non-FIPS host into FIPS. AL8 stopped selecting it in 0.1.81.

## stig-selected counts (snapshot of 2026-08-14)

- AlmaLinux 8: **392** of 1699 — down from 411 under 0.1.74, and the profile
  now refines `var_system_crypto_policy` to `FIPS:STIG` (#90)
- AlmaLinux 9: **488** of 1532
- AlmaLinux 10: **508** of 1061
- Ubuntu 24.04: **230** of 642

## Why pin downstream versions, not upstream

`oscap xccdf eval` at install time loads
`/usr/share/xml/scap/ssg/content/ssg-<distro>-ds.xml` from the
**installed `scap-security-guide` RPM / `ssg-debderived` deb** on the target
host — whichever version that distro shipped. ks-gen's `emit_tailoring`
references rule IDs that need to exist in **that** datastream, not in the
latest upstream release. So we pin against what's actually deployable today.

When a downstream bumps SSG, re-extract per the recipe above. If the diff
moves rule IDs that ks-gen rules reference, update the rules and bump the
versions in this file. `ssg-drift.yml` notices the bump for you, weekly, and
files an `ssg-drift` issue naming the changed files — a fetch failure fails
that job with a different message and never opens an issue, so a drift issue
always means real content movement.
