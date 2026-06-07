# disk.layout block — design

**Issue:** [#8 — disk.layout: block — replace reserved 'disk.preset: custom' token with structured layout](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)

**Status:** approved 2026-06-07

**Goal:** Replace the reserved `disk.preset: custom` token with a structured
`disk.layout:` block that lets operators size and customize LVs without
dropping to raw kickstart `part`/`logvol` directives, while preserving the
STIG-correct partitioning that `disk.preset: stig_server` produces today.

## Background

`DiskPreset.CUSTOM` was reserved at v0.1 design time with the intent that
v0.2 would land a structured layout block. The validator currently rejects
`preset: custom` with a "reserved for v0.2" message
(`src/ks_gen/config.py:67`). v0.4 closes that gap.

The existing `partitioning_stig_server.j2` partial encodes a complete
STIG-compliant LVM layout (separate `/var`, `/var/log`, `/var/log/audit`,
`/var/tmp`, `/home`, `/tmp` with STIG-baseline fsoptions per mountpoint,
PV grows to fill disk, LVs are fixed-size). The new `layout` block is a
data-driven generalization of that partial: same STIG defaults, with
operator-supplied overrides for sizes, names, and an optional `ondisk:`
hint.

## Goals

- `disk.layout:` block, mutually exclusive with `disk.preset:`, accepted at
  config-load.
- STIG-baseline defaults match `partitioning_stig_server.j2` — a minimal
  `layout` listing the required mountpoints with no sizes or fsoptions
  renders kickstart directives equivalent to `disk.preset: stig_server`
  (same partition lines, same options, same order; internal whitespace
  may differ since the existing partial has hand-aligned columns).
- STIG-required mountpoints enforced at config-load. Missing
  `/var/log/audit` (or any other required mountpoint) hard-fails with a
  specific error.
- Forward-compatible with issue #7 (LUKS presets): `encrypted: bool` field
  reserved on each LV; rejected at load until #7 lands.
- Backwards-compatible: existing `host.yaml` files with `disk.preset:`
  (or no `disk:` block at all) keep working unchanged.

## Non-goals (deferred)

- `scheme: plain` (flat partitions, no LVM). The `minimal` preset still
  serves this use case; a `layout` variant can be added in a follow-up
  issue if operator demand emerges.
- Multi-PV, multi-VG. Single PV / single VG covers single-disk STIG
  hosts, which is the realistic deployment target. Multi-disk operators
  can use `custom_post:`.
- Explicit device names (`/dev/sda3` etc.). Operator portability across
  disk enumeration variants (cloud `vda`, Hyper-V `sda`, bare-metal
  `nvme0n1`) is preserved by letting anaconda bind logical PVs to disks,
  with at most an optional `ondisk: sda`-style hint.
- LUKS / at-rest encryption. Issue #7 owns the LUKS preset surface.
  `DiskLvDef.encrypted` is reserved here; #7 will add the password-source
  and luks-formatter wiring on top.
- `size: max` grow-LV semantics. The existing preset has the PV grow
  to fill the disk; LVs are fixed-size, leaving free VG space for future
  `lvextend`. No `size: max` LV sentinel is needed.
- LV size sum vs. disk capacity validation. Disk size isn't known at
  config-load; anaconda catches over-allocation at install.

## Architecture

### Surface

The `Disk` model on `HostConfig` gains an optional `layout` sibling to
`preset`. Both omitted → `preset` defaults to `STIG_SERVER` (matches v0.3
behavior). One set → that one is used. Both set → ValidationError.

`DiskPreset.CUSTOM` stays as an enum value for one release with an
updated rejection message pointing at `disk.layout`. Removing the value
outright would yield a less-helpful "invalid enum" error for anyone
migrating from a v0.1-era YAML.

```python
class Disk(StrictModel):
    preset: DiskPreset | None = None
    layout: DiskLayout | None = None
    wipe: bool = True
    bootloader_password: str | None = None

    @model_validator(mode="after")
    def _preset_xor_layout(self) -> Disk:
        # Both omitted -> default to STIG_SERVER (v0.3 backwards-compat)
        # Both set     -> error
        # One set      -> use it
        ...
```

### Schema

Three new Pydantic models. All `StrictModel` (`extra=forbid`, `frozen`).

```python
class DiskLvDef(StrictModel):
    name: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    mount: str | None = None              # None = swap LV
    size: str | None = Field(
        default=None, pattern=r"^\d+(M|G|T)$|^recommended$"
    )
    fstype: Literal["xfs", "ext4", "swap"] = "xfs"
    fsoptions: str | None = None          # None => STIG-safe defaults per mountpoint
    encrypted: bool = False                # rejected at load until #7 lands

    @field_validator("encrypted")
    @classmethod
    def _encryption_deferred(cls, v: bool) -> bool:
        if v:
            raise ValueError(
                "disk.layout.lvs[].encrypted=true requires the luks.preset "
                "block (issue #7); not yet implemented."
            )
        return v


class DiskBootPart(StrictModel):
    size: str = Field(default="1G", pattern=r"^\d+(M|G)$")
    fstype: Literal["xfs", "ext4"] = "xfs"
    fsoptions: str | None = "nodev,nosuid"  # STIG default


class DiskEfiPart(StrictModel):
    size: str = Field(default="1G", pattern=r"^\d+(M|G)$")
    # fstype is always "efi" for the EFI System Partition; not configurable.


class DiskLayout(StrictModel):
    ondisk: str | None = Field(default=None, pattern=r"^[a-zA-Z][a-zA-Z0-9]*$")
    boot: DiskBootPart = Field(default_factory=DiskBootPart)
    efi: DiskEfiPart = Field(default_factory=DiskEfiPart)
    vg_name: str = "vg_root"
    lvs: list[DiskLvDef] = Field(..., min_length=1)
```

Size representation: strings with units (`"20G"`, `"100G"`, `"600M"`) or
the literal `"recommended"` (swap-only). Renderer converts to kickstart's
raw-MB integers via the `effective_size_mb` helper. Bare numbers and other
units are rejected by the regex.

### Defaults

LVs with `size:` omitted resolve via this table (matches
`partitioning_stig_server.j2`):

| Mountpoint | Default size |
|---|---|
| `/` | 15G |
| `/home` | 5G |
| `/tmp` | 3G |
| `/var` | 10G |
| `/var/log` | 5G |
| `/var/log/audit` | 3G |
| `/var/tmp` | 2G |
| swap (mount=null) | `recommended` |

LVs with `fsoptions:` omitted resolve via:

| Mountpoint | Default fsoptions |
|---|---|
| `/` | (none) |
| `/home` | `nodev,nosuid` |
| `/tmp`, `/var/tmp` | `nodev,nosuid,noexec` |
| `/var` | `nodev` |
| `/var/log`, `/var/log/audit` | `nodev,nosuid,noexec` |
| swap (mount=null) | (none) |

`/boot` defaults: 1G, xfs, `nodev,nosuid`. `/boot/efi` defaults: 1G, efi.

**`/home` does not default to `noexec`** — the DISA RHEL 9 STIG (which
AlmaLinux 9 inherits via SSG) requires `nodev` and `nosuid` on `/home` but
does not require `noexec`. Users legitimately execute binaries from
`$HOME` (`~/.local/bin`, language version managers like nvm/pyenv,
source-compiled tools). The current `stig_server` preset reflects this
correctly; the layout block preserves the same baseline. Operators
wanting stricter behavior set `fsoptions: "nodev,nosuid,noexec"`
explicitly on the home LV.

## Validation

All enforced at config-load with specific error messages.

**On `Disk`:**

1. `preset` and `layout` mutually exclusive. Both set → error.
2. Both omitted → `preset` defaults to `STIG_SERVER`.
3. `preset: custom` still rejected, message updated to point at
   `disk.layout`.

**On `DiskLayout`:**

4. STIG required mountpoints present. The set of LV `mount:` values plus
   the implicit `/boot` and `/boot/efi` from the boot/efi structs must
   include `{/, /home, /tmp, /var, /var/log, /var/log/audit, /var/tmp,
   /boot, /boot/efi}`. Missing any → error naming that mountpoint, e.g.:
   `"disk.layout missing STIG-required mountpoint: /var/log/audit"`.
5. Exactly one swap LV. Zero → error. More than one → error.
6. LV `name` uniqueness. Duplicate → error.
7. LV `mount` uniqueness (excluding swap, which has `mount=None`).
   Duplicate → error.
8. LVs may omit `size:` only if `mount` is in the defaults table (or
   `mount` is null/swap, defaulting to `recommended`). LV with omitted
   `size:` AND a mount not in the table → error:
   `"disk.layout.lvs[<name>].size: required for custom mountpoint
   <mount>; no default available"`.
9. Swap LV must have `mount: null` (or omitted) AND `fstype: swap`.
   Cross-check rejects e.g. an LV with `mount: /var, fstype: swap`.
10. `encrypted: true` rejected at the field level (already shown above)
    until #7 lands.
11. `ondisk:` is a plain basename (`sda`, `nvme0n1`, `vda`) — no `/dev/`
    prefix, no partition suffix. Enforced by regex on the field.

**Deliberately NOT validated** (handled downstream by anaconda at install):

- LV size sum ≤ VG capacity (disk size unknown at config-load).
- Mount option syntax — `fsoptions:` strings pass through verbatim.
- LV name length (LVM allows 128 chars; only regex pattern enforced).

## Renderer

Selector update in `src/ks_gen/templates/ks.cfg.j2` at line 26:

```jinja2
{% if cfg.disk.layout -%}
{% include 'partials/partitioning_layout.j2' %}
{% else -%}
{% include 'partials/partitioning_' ~ cfg.disk.preset.value ~ '.j2' %}
{% endif %}
```

New partial `src/ks_gen/templates/partials/partitioning_layout.j2`:

```jinja2
{# Layout-driven partitioning. PV grows to fill remaining disk; LVs are
   fixed-size, leaving free VG space for operator extension. ondisk
   (when set) applies to /boot/efi, /boot, and the PV so the whole
   install lands on the named disk in multi-disk hosts. #}
{% set OND = (' --ondisk=' ~ cfg.disk.layout.ondisk) if cfg.disk.layout.ondisk else '' -%}
part /boot/efi --fstype=efi --size={{ size_to_mb(cfg.disk.layout.efi.size) }} --asprimary{{ OND }}
part /boot --fstype={{ cfg.disk.layout.boot.fstype }} --size={{ size_to_mb(cfg.disk.layout.boot.size) }}{% if cfg.disk.layout.boot.fsoptions %} --fsoptions="{{ cfg.disk.layout.boot.fsoptions }}"{% endif %} --asprimary{{ OND }}
part pv.01 --grow --size=1{{ OND }}
volgroup {{ cfg.disk.layout.vg_name }} pv.01
{% for lv in cfg.disk.layout.lvs -%}
logvol {{ lv.mount or 'swap' }} --vgname={{ cfg.disk.layout.vg_name }} --name={{ lv.name }} --fstype={{ lv.fstype }} {% set sz = effective_size_mb(lv) %}{% if sz == 'recommended' %}--recommended{% else %}--size={{ sz }}{% endif %}{% set fso = effective_fsoptions(lv) %}{% if fso %} --fsoptions="{{ fso }}"{% endif %}
{% endfor %}
```

New helper module `src/ks_gen/disk_layout.py`:

```python
_DEFAULT_LV_SIZES: dict[str | None, str] = {
    "/":              "15G",
    "/home":          "5G",
    "/tmp":           "3G",
    "/var":           "10G",
    "/var/log":       "5G",
    "/var/log/audit": "3G",
    "/var/tmp":       "2G",
    None:             "recommended",
}

_DEFAULT_FSOPTIONS: dict[str, str] = {
    "/home":          "nodev,nosuid",
    "/tmp":           "nodev,nosuid,noexec",
    "/var":           "nodev",
    "/var/log":       "nodev,nosuid,noexec",
    "/var/log/audit": "nodev,nosuid,noexec",
    "/var/tmp":       "nodev,nosuid,noexec",
}

def effective_size_mb(lv: DiskLvDef) -> int | str:
    """Returns MB int, or the string 'recommended' for swap-style sizing."""
    s = lv.size if lv.size is not None else _DEFAULT_LV_SIZES[lv.mount]
    if s == "recommended":
        return "recommended"
    n, unit = int(s[:-1]), s[-1]
    return n * {"M": 1, "G": 1024, "T": 1024 * 1024}[unit]

def effective_fsoptions(lv: DiskLvDef) -> str | None:
    if lv.fsoptions is not None:
        return lv.fsoptions
    return _DEFAULT_FSOPTIONS.get(lv.mount or "")

def size_to_mb(size_str: str) -> int:
    """For /boot and /boot/efi where 'recommended' isn't valid."""
    n, unit = int(size_str[:-1]), size_str[-1]
    return n * {"M": 1, "G": 1024}[unit]
```

`src/ks_gen/skeleton.py` change: register these three helpers as Jinja
globals on the environment so the partial can call them.

**Output guarantee:** a minimal `layout` block that lists exactly the
STIG-required mountpoints (no explicit sizes/fsoptions, no `ondisk`, LV
names matching the existing partial: `root`, `home`, `tmp`, `var`,
`varlog`, `varlogaudit`, `vartmp`, `swap`) renders the same kickstart
directives as today's `partitioning_stig_server.j2` — same partition
lines, same flags, same order. Internal whitespace may differ (the
existing partial has hand-aligned columns; the Jinja output uses
single-space separators). Golden test C.1 below normalizes whitespace
within each line before comparing.

## Tests

### A. Schema validation (extends `tests/test_config_schema.py`)

| Test | Purpose |
|---|---|
| `test_disk_layout_minimal_valid` | STIG-required mountpoints, no sizes/fsoptions → parses |
| `test_disk_preset_xor_layout_both_set_rejected` | Both set → ValidationError |
| `test_disk_neither_defaults_to_stig_server` | Empty `disk:` → preset == STIG_SERVER (v0.3 backwards-compat) |
| `test_disk_layout_missing_required_mountpoint` | Parametrized over `/`, `/home`, `/tmp`, `/var`, `/var/log`, `/var/log/audit`, `/var/tmp` |
| `test_disk_layout_no_swap_rejected` | |
| `test_disk_layout_multiple_swap_rejected` | |
| `test_disk_layout_duplicate_lv_name_rejected` | |
| `test_disk_layout_duplicate_mount_rejected` | |
| `test_disk_layout_custom_mount_without_size_rejected` | `/srv` with no size → error |
| `test_disk_layout_stig_mount_without_size_ok` | `/var` with no size → uses default 10G |
| `test_disk_layout_encrypted_true_rejected` | `encrypted: true` → "#7" error |
| `test_disk_layout_ondisk_with_dev_prefix_rejected` | `ondisk: /dev/sda` → error |
| `test_disk_preset_custom_rejected_with_layout_message` | `preset: custom` → updated message |

### B. Renderer helpers (new `tests/test_disk_layout_helpers.py`)

| Test | Purpose |
|---|---|
| `test_effective_size_mb_explicit` | `size="20G"` → 20480 |
| `test_effective_size_mb_default` | `size=None, mount="/var"` → 10240 |
| `test_effective_size_mb_recommended` | swap LV → `"recommended"` |
| `test_effective_fsoptions_explicit` | `fsoptions="nodev"` → `"nodev"` |
| `test_effective_fsoptions_default` | `mount="/var/log/audit"` → `"nodev,nosuid,noexec"` |
| `test_effective_fsoptions_none_for_root` | `mount="/"` → None |
| `test_size_to_mb_m_unit` | `"500M"` → 500 |
| `test_size_to_mb_g_unit` | `"15G"` → 15360 |

### C. Golden snapshots (new in `tests/golden/`)

1. **`layout-stig-baseline.host.yaml` + `test_layout_stig_baseline.py`** —
   the spec-level guarantee test. Layout lists exactly the STIG-required
   mountpoints with LV names matching the existing partial (`root`,
   `home`, `tmp`, `var`, `varlog`, `varlogaudit`, `vartmp`, `swap`), no
   sizes/fsoptions specified. The test renders two bundles from
   otherwise-identical host.yamls (one with `disk.layout:`, one with
   `disk.preset: stig_server`), extracts the partitioning region from
   each `ks.cfg`, normalizes whitespace within each line (collapses
   runs of spaces), and asserts the normalized lines are equal in
   content and order. Also snapshots the layout-rendered partitioning
   region via syrupy.
2. **`layout-custom-sizes.host.yaml` + `test_layout_custom_sizes.py`** —
   `/var: 20G`, `/var/log: 10G`, plus a custom `/srv: 50G xfs` mountpoint,
   `ondisk: sda`. Snapshot the full `ks.cfg`.

### D. Acceptance criteria (issue #8)

- ✅ "`disk.preset` and `disk.layout` are mutually exclusive at config
  load" → schema test A.
- ✅ "Layout missing `/var/log/audit` fails config-load with a specific
  error" → parametrized schema test A.
- 🔶 "Custom layout with all STIG-required mountpoints renders and
  installs cleanly in Hyper-V" → cannot be automated in CI. The
  equivalent-to-stig_server golden (C.1) provides automated coverage by
  transitivity since the `stig_server` preset has already been Hyper-V
  verified during v0.1. Manual Hyper-V verification of one custom
  layout listed in `MINIMAL-TEST.md`-style manual checklist.

Lint coverage: `ks-gen lint` already understands `part`/`volgroup`/`logvol`
directives; no changes needed.

## Migration

Existing v0.1–v0.3 `host.yaml` files keep working unchanged:

- No `disk:` block → `Disk()` defaults still resolve to `preset=STIG_SERVER`.
- `disk.preset: stig_server` (or `minimal`) → unchanged.
- `disk.preset: custom` → still rejected, message now points at the new
  `disk.layout` block instead of "v0.2 reserved."

No schema break. The change is purely additive.
