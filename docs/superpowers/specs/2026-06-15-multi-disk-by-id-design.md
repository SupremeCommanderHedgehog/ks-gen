# Multi-disk + by-id targeting — design

**Date:** 2026-06-15
**Status:** drafted; pending user review
**Type:** ks-gen feature (v0.13)

## Goal

Two related schema additions that let `ks-gen gen` produce kickstarts
for hosts with stable disk identifiers and more than one disk:

1. **Relax `disk.target`** so it accepts persistent identifiers like
   `disk/by-id/ata-TEAML5Lite3D240G_AB20181209A0100005`, not just bare
   kernel names like `sda`. Anaconda already accepts the by-id form in
   `ignoredisk --only-use=`, `clearpart --drives=`, `bootloader
   --boot-drive=`, and `part --ondisk=` — the only thing standing in
   the way is ks-gen's schema regex.
2. **Add `disk.data_disks`** — a list of secondary physical disks that
   get either freshly partitioned and mounted, or have an existing
   filesystem mounted in place from `%post`.

The proximate driver is the `cougar` workstation host: a 256 GB Teamgroup
SSD for the system + a 1 TB WDC HDD for `/data`, both addressed by the
`/dev/disk/by-id/ata-*` symlinks that survive SATA-port reshuffles.
Without these changes the cougar config cannot be expressed in YAML
and the existing one-disk hosts (`mgmt1`, `unifi`) remain at risk of
anaconda picking the wrong disk on enumeration changes.

## Background

The `disk.target` field landed in v0.10 (spec:
`2026-06-12-disk-target-design.md`, issue #59) with a deliberately
narrow regex: `^[a-zA-Z][a-zA-Z0-9]*$`. That accepts `sda`, `vda`,
`nvme0n1`, but rejects every form that contains a `-`, `_`, `.`, or
`/` — i.e. every persistent identifier under `/dev/disk/by-id/`. The
spec called multi-disk targeting a non-goal and deferred per-disk
overrides to a follow-up.

Six months later, the cougar host is the follow-up: a real workstation
build with two disks, where SATA-port enumeration is unstable enough
that referencing the system disk as `sda` is a coin flip. Real-world
multi-disk hosts also exist on the server side — anything with a
separate data drive (database state, container images on a JBOD,
scratch volumes) hits the same constraint.

## Goals

- New `disk.target` regex accepts by-id and by-path forms as well as the
  existing short names. Backwards-compatible: every previously-valid
  value still loads.
- New `Disk.data_disks: list[DataDisk]` field. Each entry declares one
  secondary physical disk, its mount, its filesystem, and whether to
  format-on-install (`wipe=True`) or preserve-and-mount-existing
  (`wipe=False`).
- Both wipe modes ship in v0.13. The cougar use case explicitly needs
  preserve mode (keep the Ubuntu /data partition intact during the
  AlmaLinux install).
- Wizard (`ks-gen wizard`) prompts for data disks alongside the system
  target.
- Cross-validation prevents the foot-guns: target collisions, mount
  collisions with system mounts, `data_disks` without a system target,
  preserve mode without a partition identifier.

## Non-goals

- Multi-disk LVM (one VG striped across two PVs). The cougar use case
  pairs a one-disk LVM system with independent flat data disks — that
  shape covers every host on the roadmap.
- LUKS on data disks. v0.13 data disks are plain xfs/ext4; LUKS stays
  scoped to the system PV via `disk.luks`. Per-disk LUKS is a future
  spec when a real use case lands.
- Multiple partitions on a single data disk. v0.13 treats each
  `data_disks` entry as "the whole disk is one filesystem." Sub-disk
  partitioning belongs in a `disk.layout`-style nested schema, not
  here.
- Auto-discovery of by-id paths (e.g. "use the largest non-system
  disk"). Operators name disks explicitly. `lsblk -o NAME,SERIAL,ID-LINK`
  is the right discovery tool, not ks-gen.

## Schema

**New module-level constant** in `src/ks_gen/config.py`:

```python
# accepts: "sda", "nvme0n1", "disk/by-id/ata-FOO", "disk/by-path/..."
# rejects: leading "/", empty, leading digit, whitespace
DISK_TARGET_REGEX = r"^[a-zA-Z][a-zA-Z0-9._/-]*$"
```

**Modified `Disk.target`** — pattern uses the constant, same default
(`None`):

```python
class Disk(StrictModel):
    ...
    target: str | None = Field(default=None, pattern=DISK_TARGET_REGEX)
    data_disks: list[DataDisk] = Field(default_factory=list)
```

**New `DataDisk` model:**

```python
class DataDisk(StrictModel):
    target: str = Field(..., pattern=DISK_TARGET_REGEX)
    mount: str = Field(..., min_length=1, pattern=r"^/[a-zA-Z0-9_/-]+$")
    fstype: Literal["xfs", "ext4"] = "xfs"
    fsoptions: str | None = "nodev,nosuid"   # STIG-aligned default
    wipe: bool = True
    partition: int | None = Field(default=None, ge=1)
    partition_uuid: str | None = None
    partition_label: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _default_partition_when_preserve(cls, data: dict[str, object]) -> dict[str, object]:
        """When wipe=False and no identifier is given, default partition=1.

        Must run before construction because StrictModel is frozen.
        """
        if not isinstance(data, dict):
            return data
        if data.get("wipe", True) is False:
            ids = (data.get("partition"), data.get("partition_uuid"), data.get("partition_label"))
            if all(x is None for x in ids):
                data["partition"] = 1
        return data

    @model_validator(mode="after")
    def _validate_identifier(self) -> DataDisk:
        ids = [self.partition, self.partition_uuid, self.partition_label]
        n_set = sum(x is not None for x in ids)
        if self.wipe:
            if n_set > 0:
                raise ValueError(
                    "data_disks: partition / partition_uuid / partition_label "
                    "are only valid when wipe=False"
                )
            return self
        # wipe=False
        if n_set > 1:
            raise ValueError(
                "data_disks: specify at most one of partition / partition_uuid / partition_label"
            )
        # n_set == 1 guaranteed by the before-validator default
        return self
```

**New `HostConfig` cross-validators:**

```python
@model_validator(mode="after")
def _validate_data_disks_require_target(self) -> HostConfig:
    if self.disk.data_disks and self.disk.target is None:
        raise ValueError(
            "disk.data_disks is non-empty but disk.target is unset; "
            "without a system target, anaconda's clearpart --all would "
            "clobber the data disks"
        )
    return self

@model_validator(mode="after")
def _validate_data_disks_targets_distinct(self) -> HostConfig:
    seen: set[str] = {self.disk.target} if self.disk.target else set()
    for i, d in enumerate(self.disk.data_disks):
        if d.target in seen:
            raise ValueError(
                f"disk.data_disks[{i}].target {d.target!r} collides "
                f"with disk.target or another data disk"
            )
        seen.add(d.target)
    return self

@model_validator(mode="after")
def _validate_data_disks_mounts_distinct(self) -> HostConfig:
    reserved = {"/", "/boot", "/boot/efi"}
    if self.disk.layout is not None:
        reserved.update(lv.mount for lv in self.disk.layout.lvs if lv.mount)
    elif self.disk.preset == DiskPreset.STIG_SERVER:
        # preset path: stig_server creates the STIG-required mountpoints
        reserved.update(_STIG_REQUIRED_LV_MOUNTPOINTS)
    # disk.preset == MINIMAL only creates "/", already in reserved; and
    # the _minimal_preset_rejects_data_disks validator rules it out anyway.
    if self.containers.enabled:
        reserved.add("/srv/containers")
    seen: set[str] = set()
    for i, d in enumerate(self.disk.data_disks):
        if d.mount in reserved or d.mount in seen:
            raise ValueError(
                f"disk.data_disks[{i}].mount {d.mount!r} collides with a "
                f"reserved or already-assigned mount point"
            )
        seen.add(d.mount)
    return self

@model_validator(mode="after")
def _minimal_preset_rejects_data_disks(self) -> HostConfig:
    if self.disk.preset == DiskPreset.MINIMAL and self.disk.data_disks:
        raise ValueError(
            "disk.preset='minimal' is incompatible with disk.data_disks; "
            "use disk.preset='stig_server' or disk.layout"
        )
    return self
```

**Breaking-change calculus.** The relaxed regex is a strict superset
of the old one — every previously-valid `disk.target` value still
loads. `data_disks` is purely additive (default empty list). No
existing host.yaml fails to load under v0.13. Conventional commit:
`feat(disk): accept by-id in disk.target; add disk.data_disks`. No `!`;
release-please bumps minor (0.12.2 → 0.13.0). No migration notes
required.

## Template fan-out

### `ks.cfg.j2` — wipe=True path threads through three existing lines

A local list captures the system target plus every wipe=True data
disk; this list drives both `ignoredisk` and `clearpart`.

```jinja
{%- set _used = ([cfg.disk.target] + [d.target for d in cfg.disk.data_disks if d.wipe]) | reject('none') | list -%}

{% if cfg.disk.target -%}
ignoredisk --only-use={{ _used | join(',') }}
{% endif -%}
```

`clearpart` follows the same shape:

```jinja
{% if cfg.disk.wipe -%}
zerombr
{% if cfg.disk.target -%}
clearpart --all --initlabel --drives={{ _used | join(',') }}
{% else -%}
clearpart --all --initlabel
{% endif -%}
{% endif -%}
```

`bootloader --boot-drive=` is unchanged — always the single system
target.

### `ks.cfg.j2` — new `part` lines for wipe=True data disks

After the partitioning partial include and before the containers
logvol, emit one whole-disk `part` line per wipe=True entry:

```jinja
{% for d in cfg.disk.data_disks if d.wipe -%}
part {{ d.mount }} --fstype={{ d.fstype }} --grow --size=1 --ondisk={{ d.target }}{% if d.fsoptions %} --fsoptions="{{ d.fsoptions }}"{% endif %}
{% endfor -%}
```

Anaconda creates a single whole-disk partition, formats it, mounts it
during install, and the resulting `/etc/fstab` entry is generated for
free.

### New rule `src/ks_gen/rules/data_disks_preserve.py` — wipe=False path

Preserve-mode disks are deliberately **omitted** from
`ignoredisk --only-use=` so anaconda ignores them entirely; the rule
mounts them from `%post`.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import DataDisk, HostConfig


def _fstab_spec(d: DataDisk) -> str:
    if d.partition is not None:
        return f"/dev/disk/by-id/{d.target}-part{d.partition}"
    if d.partition_uuid is not None:
        return f"UUID={d.partition_uuid}"
    if d.partition_label is not None:
        return f"LABEL={d.partition_label}"
    raise AssertionError("DataDisk validator guarantees one identifier when wipe=False")


@dataclass(frozen=True)
class _Rule:
    id: str = "data_disks_preserve"
    summary: str = "Mount preserved data disks via fstab from %post."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return any(not d.wipe for d in cfg.disk.data_disks)

    def emit_post(self, cfg: HostConfig) -> str:
        lines: list[str] = []
        preserved = [d for d in cfg.disk.data_disks if not d.wipe]
        for d in preserved:
            spec = _fstab_spec(d)
            opts = d.fsoptions or "defaults"
            lines.append(f"mkdir -p {d.mount}")
            lines.append(f'echo "{spec} {d.mount} {d.fstype} {opts} 0 2" >> /etc/fstab')
        lines.append("mount -a")
        mounts = " ".join(d.mount for d in preserved)
        lines.append(f"restorecon -R {mounts}")
        return "\n".join(lines)

    def emit_packages(self, cfg: HostConfig) -> list[str]: return []
    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]: return []
    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None: return None


RULE: Rule = cast(Rule, _Rule())
```

The rule's `applies` returns true only when at least one preserve-mode
disk exists, so the rule's `%post` block is omitted entirely from the
generated kickstart for wipe-only and zero-data-disk hosts.

## Wizard

`ks-gen wizard` (under `src/ks_gen/wizard/`) gains a `data_disks`
section after the system-target prompt. Sketch of the prompt flow:

```
System disk target (by-id or short name) [skip]: disk/by-id/ata-TEAM...
Add a data disk? [y/N]: y
  Data disk target (by-id or short name): disk/by-id/ata-WDC_...
  Mount point: /data
  Filesystem [xfs]:
  fsoptions [nodev,nosuid]:
  Wipe disk on install? [Y/n]: n
    Identify existing partition by:
      1) partition number (default: 1)
      2) UUID
      3) LABEL
    Choice [1]: 2
    Partition UUID: 0f2a-1c3b-...
Add another data disk? [y/N]: n
```

Loops until the operator declines another disk. Each disk's answers
feed a `DataDisk` model; the same pydantic validators that protect the
YAML path catch wizard mistakes (target collisions, wipe=True paired
with a partition identifier, mount collisions, etc.). The new prompts
live in `src/ks_gen/wizard/_disk.py` (which already owns the
`disk.target` / `disk.layout` flow), reusing the `_prompts.py`
helpers.

## Validation

**Unit tests in `tests/test_config.py`:**

- `disk.target = "disk/by-id/ata-FOO"` loads.
- `disk.target = "nvme0n1"` still loads.
- `disk.target = "/dev/sda"` still rejected (leading `/`).
- `disk.target = "1sda"` still rejected (leading digit).
- DataDisk: `wipe=True` + any `partition*` field → rejected.
- DataDisk: `wipe=False` with both `partition_uuid` and `partition_label`
  set → rejected.
- DataDisk: `wipe=False` with no identifier → `partition` defaults to 1.
- DataDisk: `mount = "data"` (no leading `/`) → rejected by the mount
  pattern.
- HostConfig: `data_disks` non-empty + `disk.target=None` → rejected.
- HostConfig: two `data_disks` with the same `target` → rejected.
- HostConfig: `data_disks[0].target == disk.target` → rejected.
- HostConfig: `data_disks[0].mount = "/home"` → rejected (collides with
  the stig_server `/home` LV).
- HostConfig: `data_disks[0].mount = "/srv/containers"` with
  `containers.enabled=true` → rejected.
- HostConfig: `data_disks[0].mount = data_disks[1].mount` → rejected.
- HostConfig: `disk.preset='minimal'` + non-empty `data_disks` →
  rejected.

**Golden snapshots in `tests/golden/`:**

Six new snapshots covering the matrix of data-disk modes. Each is the
generated `ks.cfg` for a parametrized config:

1. **baseline** — no data_disks (the existing snapshot; regen confirms no
   accidental drift in the existing render).
2. **one wipe=True data disk** — adds one entry to `ignoredisk`, one
   entry to `clearpart --drives`, one new `part` line.
3. **one wipe=False with `partition=1`** — disk is *absent* from
   `ignoredisk`; a new `%post` block from `data_disks_preserve` writes
   `/dev/disk/by-id/...-part1` into fstab.
4. **one wipe=False with `partition_uuid`** — same shape; `UUID=...` in
   fstab.
5. **one wipe=False with `partition_label`** — same shape; `LABEL=...`
   in fstab.
6. **mixed: one wipe=True + one wipe=False** — proves the two paths
   coexist (kickstart `part` line for the first, `%post` fstab block
   for the second).

Regenerate after the schema + template + rule are in place:
`pytest tests/golden/ --snapshot-update`. The diffs against the baseline
should match the prediction exactly; anything else is a bug.

## Install-regression harness

Per CLAUDE.md's "When to recommend running it" guidance, this diff
touches every category in the "DO recommend" list:

- `src/ks_gen/templates/ks.cfg.j2` (ignoredisk, clearpart, part lines)
- `src/ks_gen/config.py` (defaults reachable from the install)
- A new file under `src/ks_gen/rules/` that writes `%post` shell

Surface the recommendation pre-merge with a two-disk variant of the
existing harness. Concrete steps for whoever runs it:

1. Add a second virtual disk to the QEMU VM (`-drive
   file=data.qcow2,if=none,id=data` + `-device
   ata-hd,drive=data,bus=ide.0`). Stable size — 1 GiB is plenty.
2. **Wipe=True scenario.** Author a host.yaml with one `data_disks`
   entry (`wipe: true`, `mount: /data`, target = whichever by-id path
   anaconda exposes for the second virtual disk). Install. SSH in and
   confirm `/data` is mounted, owned root:root, on the expected
   `/dev/disk/by-id/...-part1`.
3. **Wipe=False scenario.** Before the install, pre-format the second
   virtual disk via the live ISO shell: `mkfs.xfs -L preserve_test
   /dev/disk/by-id/...`. Author a host.yaml with the data disk in
   preserve mode (`wipe: false`, `partition_label: preserve_test`).
   Install. SSH in and confirm `/data` is mounted from the
   pre-existing fs (the label survives; running `xfs_info /data` shows
   the pre-install UUID).

Wall-clock for both runs together on TCG: ~60-90 min. Do not run from
a normal session — surface the recommendation, let the operator
decide.

## Rollout

- One PR. The schema relaxation + `data_disks` block + template
  fan-out + new rule + wizard prompts + tests are tightly enough
  coupled that splitting them creates an awkward intermediate state.
- Conventional commit: `feat(disk): accept by-id in disk.target; add
  disk.data_disks`. No `!` — strictly additive.
- release-please bumps minor: **0.12.2 → 0.13.0**.
- Release notes mention the new capability and the install-regression
  recommendation.

## Deliverables

1. `src/ks_gen/config.py` — `DISK_TARGET_REGEX`, modified `Disk`,
   new `DataDisk`, new `HostConfig` cross-validators.
2. `src/ks_gen/templates/ks.cfg.j2` — the three threading points
   above + the new `part` block.
3. `src/ks_gen/rules/data_disks_preserve.py` — new rule for
   wipe=False.
4. `src/ks_gen/wizard/_disk.py` — new prompt loop for `data_disks`.
5. `tests/test_config.py` — the validation tests above.
6. `tests/golden/__snapshots__/` — six new snapshots.
7. Release notes for v0.13 highlighting the change and the
   install-regression recommendation.

## What is NOT in this design

- The `cougar` host config itself. It depends on this work shipping but
  is its own follow-up brainstorm/spec/plan cycle.
- Per-LV LUKS on data disks.
- Multi-partition data disks (e.g. `/data` + `/scratch` on the same
  physical disk).
- Auto-discovery of available by-id paths via the wizard.
