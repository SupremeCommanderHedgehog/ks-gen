# audit-story phase 1 — SSG datastream introspection

**Parent:** #127 (cross-distro audit-story PR).

## Goal

Produce the per-distro lists of SSG `xccdf:Rule` IDs available in the three
datastreams we target — `ssg-almalinux8-ds.xml`, `ssg-almalinux9-ds.xml`,
`ssg-ubuntu2404-ds.xml` — plus a cross-distro diff showing which IDs are
shared and which are distro-only. This is the **data** that drives every
subsequent phase of #127:

- Phase 2 (per-rule mapping) needs to know which SSG IDs each of our 14
  ubuntu2404 rules + 15 alma8 rules should reference in `emit_tailoring`.
- Phase 3 (implementation strategy) decisions — `cfg.distro` branching vs
  re-export-replacement vs separate implementation — depend on whether the
  SSG IDs a given rule needs are shared across distros or distro-only.
- The alma9 sweep needs to confirm the IDs the existing alma9 rules already
  reference still exist in the current `ssg-almalinux9-ds.xml`.

## Pinned SSG versions (downstream packages, what oscap actually sees at install time)

| Distro | Package | Version | Source |
|---|---|---|---|
| AlmaLinux 8 | `scap-security-guide` | 0.1.74-3.el8_10.alma.1 | `repo.almalinux.org/almalinux/8/AppStream/x86_64/os/Packages/` |
| AlmaLinux 9 | `scap-security-guide` | 0.1.80-1.el9_7.alma.2 | `repo.almalinux.org/almalinux/9/AppStream/x86_64/os/Packages/` |
| Ubuntu 24.04 | `ssg-debderived` | 0.1.79-1 | `archive.ubuntu.com/ubuntu/pool/universe/s/scap-security-guide/` |

(Upstream SSG is on v0.1.81 as of 2026-06-20; each downstream lags by 1-7
patch releases. The downstream version is what matters because that's
what's installed on the target host at kickstart time.)

## Files touched

- **Create:** `scripts/audit_story/extract_ssg_rule_ids.py` — small CLI
  that takes three pre-extracted `ssg-*-ds.xml` paths (and the distro
  label per file), parses `xccdf:Rule id="..."` elements, and emits
  one rule ID per line per distro plus a markdown diff. ~80 LOC.
- **Create:** `docs/audit-story/SSG-VERSIONS.md` — pins the three
  downstream versions checked, plus the dpkg/rpm extraction recipe
  for reproducibility.
- **Create:** `docs/audit-story/alma8-rule-ids.txt`
  `docs/audit-story/alma9-rule-ids.txt`
  `docs/audit-story/ubuntu2404-rule-ids.txt` — one full rule ID per line,
  sorted, with the full `xccdf_org.ssgproject.content_rule_*` prefix
  preserved.
- **Create:** `docs/audit-story/cross-distro-rule-id-diff.md` —
  human-readable summary: total per distro, all-three intersection,
  pairwise intersections, distro-only sets (with full ID lists).

## Non-goals

- **Building SSG from source.** The upstream tarball
  (`scap-security-guide-0.1.81.tar.bz2` on GitHub releases) is source-only;
  building takes CMake + Python + ~5 min per build. The downstream packages
  are pre-built and what operators actually run, so pin those.
- **Per-rule mapping** (which of our rules each SSG ID belongs to) —
  phase 2 of #127.
- **Implementation of `emit_tailoring` for any rule** — phase 3 of #127.
- **CLI integration into `ks-gen`.** This is a one-off introspection
  tool, not an operator-facing feature. Lives under `scripts/`, not
  `src/ks_gen/`.
- **Automated SSG version-bump detection.** Re-running this tool on a
  bump is manual; updating the pin in `SSG-VERSIONS.md` documents what
  was checked against.

## Architecture — `extract_ssg_rule_ids.py`

Pure stdlib (no new deps). Approximate shape:

```python
#!/usr/bin/env python3
"""Extract xccdf:Rule IDs from one or more SSG datastreams.

Usage:
    python3 scripts/audit_story/extract_ssg_rule_ids.py \\
        --datastream alma8=/tmp/extract/ssg-almalinux8-ds.xml \\
        --datastream alma9=/tmp/extract/ssg-almalinux9-ds.xml \\
        --datastream ubuntu2404=/tmp/extract/ssg-ubuntu2404-ds.xml \\
        --out-dir docs/audit-story/

For each --datastream, writes <distro>-rule-ids.txt (one ID per line, sorted)
under --out-dir. Also writes cross-distro-rule-id-diff.md with set ops over
the three lists.
"""

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"xccdf": "http://checklists.nist.gov/xccdf/1.2"}


def extract_rule_ids(datastream_path: Path) -> set[str]:
    tree = ET.parse(datastream_path)
    return {
        elem.attrib["id"]
        for elem in tree.iter("{http://checklists.nist.gov/xccdf/1.2}Rule")
        if "id" in elem.attrib
    }


def write_diff(per_distro: dict[str, set[str]], out: Path) -> None:
    distros = sorted(per_distro)
    all_three = set.intersection(*per_distro.values()) if len(per_distro) >= 2 else set()
    # ... per-pair intersections + distro-only sets, written as markdown
```

`xml.etree.ElementTree` handles the SSG namespace fine; the XCCDF 1.2
namespace is `http://checklists.nist.gov/xccdf/1.2` and `xccdf:Rule`
elements have an `id` attribute that's the full
`xccdf_org.ssgproject.content_rule_*` form.

## Extraction recipe (reproducibility for SSG version bumps)

Documented in `docs/audit-story/SSG-VERSIONS.md`:

```bash
WORK=/tmp/ssg-extract
mkdir -p $WORK && cd $WORK

curl -sLo al8.rpm  https://repo.almalinux.org/almalinux/8/AppStream/x86_64/os/Packages/scap-security-guide-0.1.74-3.el8_10.alma.1.noarch.rpm
curl -sLo al9.rpm  https://repo.almalinux.org/almalinux/9/AppStream/x86_64/os/Packages/scap-security-guide-0.1.80-1.el9_7.alma.2.noarch.rpm
curl -sLo ssg.deb  http://archive.ubuntu.com/ubuntu/pool/universe/s/scap-security-guide/ssg-debderived_0.1.79-1_all.deb

# Extract just the ds.xml files
rpm2cpio al8.rpm | cpio -id './usr/share/xml/scap/ssg/content/ssg-almalinux8-ds.xml'
rpm2cpio al9.rpm | cpio -id './usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml'
dpkg-deb -x ssg.deb ssg-deb-extracted/

# Run the extractor
python3 /mnt/c/Users/yizshachuck/source/ks-gen/scripts/audit_story/extract_ssg_rule_ids.py \
  --datastream alma8=./usr/share/xml/scap/ssg/content/ssg-almalinux8-ds.xml \
  --datastream alma9=./usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml \
  --datastream ubuntu2404=./ssg-deb-extracted/usr/share/xml/scap/ssg/content/ssg-ubuntu2404-ds.xml \
  --out-dir /mnt/c/Users/yizshachuck/source/ks-gen/docs/audit-story/
```

(Tools needed: `rpm2cpio`, `cpio`, `dpkg-deb` — all in apt. The Ubuntu
WSL host already has `dpkg-deb`; install the rest with
`sudo apt install rpm2cpio cpio`.)

## Tests

- `tests/audit_story/test_extract_ssg_rule_ids.py`:
  - `test_extract_rule_ids_from_known_xml` — synthesize a minimal XCCDF
    XML with 3 Rule elements, assert extractor returns 3 IDs.
  - `test_extract_handles_missing_id_attribute` — `<Rule>` without
    `id=` is skipped.
  - `test_namespace_only_xccdf12` — `<Benchmark><Rule>` outside the
    xccdf 1.2 namespace is ignored.

(No test that exercises the real datastreams — they're large XML blobs
not committed to the repo. The pinned-and-committed rule-id lists ARE
the regression check: changing a list means the SSG version bumped.)

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Downstream SSG version drift between distros makes per-rule mapping unstable | Pin the three versions in `SSG-VERSIONS.md`; bump only when there's a reason. The mapping done in phase 2 references the pinned versions. |
| `<Rule>` IDs aren't the full set of "what a tailoring op can reference" — `<set-value>` ops target `<Value>` elements, not `<Rule>` | Out of scope for phase 1. Phase 2 mapping will deal with set-value targets separately. |
| Some downstream RPMs may strip or rewrite rule IDs (relabeling, profile-specific filters) | The extraction takes IDs from the raw datastream XML, not from a profile selection — so this captures the full `<Rule>` superset regardless of profile filtering. |
| The committed rule-id lists are large text files (each datastream has ~600-800 rules) | Acceptable: they're plain text, sorted, line-per-id; diffs on version bump are reviewable. |
| Tool fragility if SSG ever changes XML namespace or schema | Acceptable for an internal tool. If it breaks on bump, fix it then. |

## CI parity check before push

```bash
ruff check src tests scripts \
  && ruff format --check src tests scripts \
  && mypy \
  && pytest -q
```

(Need to add `scripts/` to ruff's `src` paths in `pyproject.toml` if not
already there — verify before commit.)

## Out of scope (phase 1 only)

- Per-rule mapping of ks-gen rules → SSG rule IDs (phase 2).
- Branching strategy in `emit_tailoring` implementations (phase 3).
- `exception_entry` English-text sweep (phase 4).
- Per-rule unit tests + golden snapshots for tailoring.xml (phase 5).
- Any change to existing rule files under `src/ks_gen/rules/`.
- Automated SSG version-bump detection / CI workflow.
