# disk.target — design

**Issue:** [#59 — Add disk.target to confine install to a specific disk in multi-disk hosts](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/59)

**Status:** approved 2026-06-12

**Goal:** Add a single `disk.target` field that confines every disk-touching
kickstart directive (`ignoredisk`, `clearpart`, `bootloader`, partition
placement) to a named disk, so installs onto multi-disk hosts cannot wipe
sibling drives.

## Background

`ks-gen gen` today has no reliable way to bound an install to a single
disk on a multi-disk host:

- `clearpart --all --initlabel` in `templates/ks.cfg.j2:23` wipes **every**
  attached disk when `disk.wipe` is true. There is no `--drives=`.
- `bootloader --location=mbr` (`templates/ks.cfg.j2:16-18`) has no
  `--boot-drive=`, so anaconda picks the boot disk by enumeration order.
- The two preset partition partials emit bare `part` lines with no
  `--ondisk=`:
  - `templates/partials/partitioning_minimal.j2`
  - `templates/partials/partitioning_stig_server.j2`
- `cfg.disk.layout.ondisk` exists and is propagated in
  `partitioning_layout.j2`, but it only covers the layout path and only
  stamps `--ondisk=` on the three layout parts. It does not bound
  `clearpart` or `bootloader`. So even the layout path can clobber other
  disks.
- There is no `ignoredisk --only-use=` anywhere in the generated
  kickstart.

Practical impact: installing onto a server with a target SSD plus
pre-existing data drives risks wiping the data drives. Today's workaround
("detach the other disks before booting the ISO") is not viable for
bare-metal or cloud-image workflows.

## Goals

- New `disk.target: str | None = None` field on the top-level `Disk`
  model. When set, every disk-touching directive in the generated
  kickstart names that disk explicitly.
- One field, one meaning: `disk.target` is the only way to confine the
  install. `disk.layout.ondisk` is removed.
- Default behavior unchanged: `disk.target = None` produces the same
  kickstart as today.
- Works with all three partitioning paths: `minimal`, `stig_server`,
  and `layout`.
- Works orthogonally to LUKS — `target` and `disk.luks` are independent.
- NVMe naming (`nvme0n1`) accepted.

## Non-goals (deferred)

- Multi-disk targeting (e.g., `targets: [sda, sdb]`). Single disk only.
- Wizard prompt for target disk. Defer to a follow-up issue.
- Auto-detect of "smallest disk" / "first SSD" / similar heuristics.
  Operators name the disk explicitly.
- A separate `disk.target` per-LV override (the issue's "Open question
  #1, option (c)" path). Single source of truth is simpler.

## Schema

Add `Disk.target` and remove `DiskLayout.ondisk`:

```python
class Disk(StrictModel):
    preset: DiskPreset | None = None
    layout: DiskLayout | None = None
    luks: DiskLuks = Field(default_factory=DiskLuks)
    wipe: bool = True
    bootloader_password: str | None = None
    target: str | None = Field(
        default=None,
        pattern=r"^[a-zA-Z][a-zA-Z0-9]*$",
    )
```

```python
class DiskLayout(StrictModel):
    # ondisk: REMOVED — moved up to Disk.target
    boot: DiskBootPart = Field(default_factory=DiskBootPart)
    efi: DiskEfiPart = Field(default_factory=DiskEfiPart)
    vg_name: str = "vg_root"
    lvs: list[DiskLvDef] = Field(..., min_length=1)
```

**Breaking change.** Existing host.yaml files that set
`disk.layout.ondisk:` will fail config-load with pydantic's standard
"extra field not permitted" error from `StrictModel`. That is the desired
behavior — silent semantic widening (now bounds clearpart/bootloader too)
would be worse than failing loud. The error message will be the default
pydantic one; we accept that for now since pre-1.0 and the rename is
documented in the issue and release notes.

Validation regex matches the prior `DiskLayout.ondisk` regex exactly, so
every previously-valid value remains valid as a `disk.target` value.

## Template fan-out

When `cfg.disk.target` is set, the generated kickstart gains:

**In `ks.cfg.j2` (top-level skeleton).**

- New `ignoredisk --only-use=<target>` line, emitted before `rootpw`,
  conditional on `cfg.disk.target`.
- `clearpart --all --initlabel --drives=<target>` (only when
  `cfg.disk.wipe` is also true).
- `bootloader --location=mbr --boot-drive=<target> --append=... [--password=...]`.

**In the three partition partials.**

Every `part` line gains `--ondisk=<target>` when `cfg.disk.target` is
set. For the layout partial this collapses to the prior `OND` mechanism;
just the source of truth changes from `cfg.disk.layout.ondisk` to
`cfg.disk.target`.

Centralize the suffix as a Jinja macro to avoid drift across the three
partials. Adding the macro to a shared partial (e.g.,
`partials/_ondisk.j2`) and importing it where needed keeps each `part`
line short.

## Validation

- Regex `^[a-zA-Z][a-zA-Z0-9]*$` rejects `sda1` (digit-after-letter is
  fine), `/dev/sda` (slash), empty string, leading digit. Accepts `sda`,
  `vda`, `nvme0n1`, `hda`.
- No cross-field validation. `target` is orthogonal to `preset`,
  `layout`, `wipe`, `bootloader_password`, and `luks`.
- `disk.wipe=False, disk.target=sda` is legal and produces an
  `ignoredisk --only-use=sda` + bounded `bootloader --boot-drive=sda`
  but no `clearpart`. This is the "preserve existing partitions on the
  target disk" path; anaconda's behavior in that scenario is outside
  this spec's scope.

## Tests

**Unit tests in `tests/test_config.py`:**

- `disk.target = "sda"` loads.
- `disk.target = "nvme0n1"` loads.
- `disk.target = "sda1"` loads (current regex allows trailing digits;
  not what an operator wants, but matches existing `ondisk` regex).
- `disk.target = "/dev/sda"` rejected.
- `disk.target = ""` rejected.
- `disk.target = "1sda"` rejected (leading digit).
- `disk.layout.ondisk = "sda"` rejected with pydantic extra-field error
  (regression-locks the removal).

**Golden snapshots in `tests/golden/`:**

For each `(target ∈ {None, "sda"}) × (preset ∈ {minimal, stig_server,
layout})` combination, snapshot the generated `ks.cfg`. Six new
snapshots, regenerated with `pytest tests/golden/ --snapshot-update`.

The diff between `target=None` and `target=sda` snapshots should be
minimal and predictable: one new `ignoredisk` line, `--drives=sda`
appended to `clearpart`, `--boot-drive=sda` appended to `bootloader`,
and `--ondisk=sda` on each `part`. Anything else in the diff is a bug.

## Install-regression harness

Per `CLAUDE.md`'s "When to recommend running it" guidance, this diff
touches:

- `src/ks_gen/templates/ks.cfg.j2` (clearpart, bootloader, ignoredisk)
- `src/ks_gen/templates/partials/partitioning_*.j2` (ondisk on parts)
- `src/ks_gen/config.py` (defaults reachable from the install)

All three are in the "DO recommend" list. Surface the install-regression
recommendation to the user before merge, with the suggestion to bring up
a second virtual disk in the QEMU VM and confirm only `target` is
touched. Do not run the harness from a normal session.

## Rollout

- One PR. The breaking schema rename is small enough that splitting it
  from the template fan-out would force an awkward intermediate state
  where `disk.layout.ondisk` is gone but nothing replaces it.
- Conventional commit: `feat(disk)!: add disk.target; remove
  disk.layout.ondisk` (with `!` to mark the breaking change for
  release-please).
- Release notes mention the rename explicitly so operators upgrading
  from v0.10.x know to move the field.
