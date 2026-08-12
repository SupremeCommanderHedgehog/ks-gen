# SSG datastream versions pinned for audit-story analysis

The per-distro rule-ID lists under this directory were extracted from these
specific downstream `scap-security-guide` / `ssg-debderived` package versions.
**These are the versions that will be installed on a freshly-built ks-gen
host as of 2026-06-20** — i.e., what `oscap` will actually see at install
time. Upstream SSG (`ComplianceAsCode/content`) was on `v0.1.81` on
2026-06-20; each downstream lags by 1-7 patch releases.

| Distro | Package | Version | Source URL |
|---|---|---|---|
| AlmaLinux 8.10 | `scap-security-guide` | `0.1.74-3.el8_10.alma.1` | https://repo.almalinux.org/almalinux/8/AppStream/x86_64/os/Packages/scap-security-guide-0.1.74-3.el8_10.alma.1.noarch.rpm |
| AlmaLinux 9 (latest) | `scap-security-guide` | `0.1.80-1.el9_7.alma.2` | https://repo.almalinux.org/almalinux/9/AppStream/x86_64/os/Packages/scap-security-guide-0.1.80-1.el9_7.alma.2.noarch.rpm |
| AlmaLinux 10 (latest) | `scap-security-guide` | `0.1.81-1.el10_2.alma.1` | https://repo.almalinux.org/almalinux/10/AppStream/x86_64/os/Packages/scap-security-guide-0.1.81-1.el10_2.alma.1.noarch.rpm |
| Ubuntu 24.04 (noble) | `ssg-debderived` | `0.1.79-1` | http://archive.ubuntu.com/ubuntu/pool/universe/s/scap-security-guide/ssg-debderived_0.1.79-1_all.deb |

## Re-extraction recipe (reproducibility for SSG version bumps)

Tools needed: `rpm2cpio`, `cpio`, `dpkg-deb`. On Ubuntu WSL:
`sudo apt install rpm2cpio cpio` (`dpkg-deb` is preinstalled).

```bash
WORK=/tmp/ssg-extract
mkdir -p "$WORK" && cd "$WORK"

curl -sLo al8.rpm \
  https://repo.almalinux.org/almalinux/8/AppStream/x86_64/os/Packages/scap-security-guide-0.1.74-3.el8_10.alma.1.noarch.rpm
curl -sLo al9.rpm \
  https://repo.almalinux.org/almalinux/9/AppStream/x86_64/os/Packages/scap-security-guide-0.1.80-1.el9_7.alma.2.noarch.rpm
curl -sLo ssg.deb \
  http://archive.ubuntu.com/ubuntu/pool/universe/s/scap-security-guide/ssg-debderived_0.1.79-1_all.deb

# Extract the datastream files
rpm2cpio al8.rpm | cpio -id --quiet './usr/share/xml/scap/ssg/content/ssg-almalinux8-ds.xml'
mkdir al9-ex && (cd al9-ex && rpm2cpio ../al9.rpm | cpio -id --quiet \
  './usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml')
mkdir ubuntu-ex && dpkg-deb -x ssg.deb ubuntu-ex/

# Run the extractor (from the ks-gen repo root)
python3 scripts/audit_story/extract_ssg_rule_ids.py \
  --datastream alma8="$WORK/usr/share/xml/scap/ssg/content/ssg-almalinux8-ds.xml" \
  --datastream alma9="$WORK/al9-ex/usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml" \
  --datastream ubuntu2404="$WORK/ubuntu-ex/usr/share/xml/scap/ssg/content/ssg-ubuntu2404-ds.xml" \
  --out-dir docs/audit-story/
```

Re-running on a bump rewrites `*-rule-ids.txt` and `cross-distro-rule-id-diff.md`
in-place — `git diff` shows what SSG changed.

## Headline numbers (current pin, 2026-06-20)

- AlmaLinux 8: **1630** rules
- AlmaLinux 9: **1530** rules
- AlmaLinux 10: **1061** rules (added 2026-08-11 for #58; the EL10 content is
  younger than EL9's, and its `stig` profile selects **508** of them)
- Ubuntu 24.04: **639** rules
- Shared across all 4: **409** rules (universal STIG floor)
- AL9 ∩ AL10: **991** rules (65% of AL10) — the alma10 re-export gambit holds
  for 12 of 15 rules; the 3 that diverge are documented in their rule modules
- AL8 ∩ AL9: **1435** rules (88% of AL8, 94% of AL9) — confirms the alma8
  re-export gambit from #121 phase 2: the alma9 `emit_tailoring` output
  is mostly directly valid on alma8

Full distro-only sets and pairwise breakdowns: `cross-distro-rule-id-diff.md`.

The extractor rewrites that file from whatever `--datastream` set it is given,
so always re-run it with **all four** at once — a partial run silently drops
the distros you left out.

`tests/test_rule_ids_exist_in_datastream.py` asserts that every SSG rule ID
referenced by a rule exists in its distro's list here, so a stale pin or an
upstream rename fails the suite instead of turning into a silent no-op on a
live host.

## Why pin downstream versions, not upstream

`oscap xccdf eval` at install time loads
`/usr/share/xml/scap/ssg/content/ssg-<distro>-ds.xml` from the
**installed `scap-security-guide` RPM / `ssg-debderived` deb** on the target
host — whichever version that distro shipped. ks-gen's `emit_tailoring`
references rule IDs that need to exist in **that** datastream, not in the
latest upstream release. So we pin against what's actually deployable today.

When a downstream bumps SSG, re-extract per the recipe above. If the diff
moves rule IDs that ks-gen rules reference, update the rules and bump the
pin in this file.
