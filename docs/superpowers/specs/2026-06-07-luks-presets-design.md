# LUKS presets — design

**Issue:** [#7 — LUKS presets: add 'partial' and 'tang' to disk encryption options](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)

**Status:** approved 2026-06-07

**Goal:** Add a `disk.luks:` block to `host.yaml` that enables PV-level LUKS
encryption with either passphrase or tang/clevis network-bound unlock.
Closes the encryption gap reserved when `DiskLvDef.encrypted: bool` was
introduced in #8.

## Background

Current encryption coverage is "all or nothing" via crypto policy. Real
STIG deployments often need partial disk encryption (data partitions
encrypted, `/boot` plain) with either passphrase unlock or network-bound
unlock via tang/clevis. The `encrypted: bool` field on `DiskLvDef` was
reserved during the disk.layout work (#8) and currently rejected at
config-load with a "use luks.preset block (#7); not yet implemented"
message — this design closes that gap.

## Goals

- New `disk.luks:` block, additive on top of `disk.preset` / `disk.layout`.
- Three presets: `none` (default), `partial` (PV-level LUKS + passphrase),
  `tang` (PV-level LUKS + clevis network-bound unlock with passphrase
  fallback).
- Passphrase supplied via inline `passphrase:` (operator-friendly) OR
  `passphrase_file:` (sidecar path read at bundle build time).
  Mutually exclusive; at least one required when `preset != none`.
- Tang servers require thumbprint pinning; threshold-of-N Shamir Secret
  Sharing across multiple servers.
- Backwards-compatible: existing `host.yaml` files keep working with no
  `disk.luks` block (defaults to `preset=none`).
- Cross-field validators catch invalid combos at config-load (e.g.,
  `disk.preset=minimal` + LUKS, tang threshold > server count).

## Non-goals (deferred)

- `full` preset (encrypting `/boot` requires exotic key sources — USB
  stick, TPM2, network key file — that the v0.5 scope doesn't justify).
- Per-LV LUKS. The `DiskLvDef.encrypted: bool` field stays in the schema
  but the rejection message is updated to "per-LV encryption is not
  supported; use `disk.luks.preset` for PV-level LUKS". Operators wanting
  selective encryption have a clear escape hatch (custom_post).
- Clevis backends other than tang (TPM2, YubiKey). Tang is the
  network-unlock use case the issue targets.
- Re-keying after install. Operators rotate via `cryptsetup luksAddKey`
  post-install, documented in MANUAL.md.
- Tang server reachability probing at `ks-gen gen` time. Air-gap-hostile
  and reachable-now ≠ reachable-at-boot.
- Passphrase strength enforcement. Anaconda doesn't require a minimum;
  ks-gen follows that policy. A future `ks-gen lint` warning is possible
  if demand emerges.
- Lint warning for inline passphrases. Documented as a possible
  follow-up; not in scope here.

## Architecture

### Surface

The new `disk.luks` block is orthogonal to the existing `disk.preset` /
`disk.layout` choice:

| `disk.preset/layout` | + `disk.luks: partial`/`tang` | Result |
|---|---|---|
| `stig_server` | ✅ | LUKS on `pv.01` from existing partial |
| `layout` (any LV config) | ✅ | LUKS on `pv.01` from layout partial |
| `minimal` | ❌ rejected | minimal has no LVM PV — cross-field validator rejects this combo |

PV-level LUKS means one LUKS container on `pv.01`, one unlock event at
boot. All LVs inherit encryption automatically. `/boot` and `/boot/efi`
stay plain (required to bootstrap unlock).

### Schema

Four new Pydantic models. All `StrictModel` (`extra=forbid`, `frozen`).

```python
class LuksPreset(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    TANG = "tang"


class TangServer(StrictModel):
    url: str = Field(..., pattern=r"^https?://[^\s/]+(/.*)?$")
    thumbprint: str = Field(
        ..., pattern=r"^[A-Za-z0-9_-]{32,}$"
    )


class Tang(StrictModel):
    servers: list[TangServer] = Field(..., min_length=1)
    threshold: int = Field(default=1, ge=1)


class DiskLuks(StrictModel):
    preset: LuksPreset = LuksPreset.NONE
    passphrase: str | None = None
    passphrase_file: str | None = None
    tang: Tang | None = None
```

Mounted onto `Disk`:

```python
class Disk(StrictModel):
    preset: DiskPreset | None = None
    layout: DiskLayout | None = None
    luks: DiskLuks = Field(default_factory=DiskLuks)   # new
    wipe: bool = True
    bootloader_password: str | None = None
```

`luks` has `default_factory=DiskLuks()` so existing host.yamls (with no
`disk.luks` block) keep working — `Disk().luks.preset == NONE`.

**Thumbprint regex** `^[A-Za-z0-9_-]{32,}$`: base64url alphabet (no
padding), at least 32 chars. SHA-256 thumbprints are 43–44 chars
base64url; the loose lower bound catches obviously-wrong values without
locking the format to a specific tang version.

**Passphrase representation**: Anaconda's `--passphrase=` takes a
literal string. Renderer wraps in double quotes and escapes `\` and `"`.

## Validation

All enforced at config-load with specific error messages.

**On `DiskLuks`** (model_validator on `DiskLuks`):

1. **Passphrase mutex.** Exactly one of `passphrase` / `passphrase_file`
   when `preset != none`. Both set → error. Neither set → error
   mentioning "passphrase or passphrase_file".
2. **`preset == none` rejects other LUKS fields.** If `preset == none`
   AND any of `passphrase` / `passphrase_file` / `tang` is set → error:
   `"disk.luks.preset='none' rejects passphrase, passphrase_file, and
   tang fields; set preset to 'partial' or 'tang'"`. Catches operator
   typos.
3. **`preset == tang` requires `tang` block.** Missing → error:
   `"disk.luks.preset='tang' requires disk.luks.tang block with at least
   one server"`.
4. **`preset != tang` rejects `tang` block.** Setting `tang` when preset
   is `partial` or `none` → error. Prevents dead config.
5. **`passphrase_file` shape.** Non-empty string. File existence checked
   at `build_bundle` time (not config-load), so the config validator
   stays pure.

**On `Tang`** (model_validator on `Tang`):

6. **`threshold ≤ len(servers)`.** If `threshold > server count` → error:
   `"disk.luks.tang.threshold (<N>) exceeds servers count (<M>);
   threshold must be ≤ servers count"`. Catches a config the operator
   can't actually unlock.

**On `HostConfig`** (model_validator on `HostConfig`):

7. **`minimal` preset + LUKS rejected.** If
   `cfg.disk.preset == DiskPreset.MINIMAL` AND
   `cfg.disk.luks.preset != LuksPreset.NONE` → error:
   `"disk.preset='minimal' has no LVM PV; disk.luks requires
   disk.preset='stig_server' or disk.layout"`.

**On `DiskLvDef`** (existing field validator):

8. **Update `encrypted=true` rejection message** to:
   `"per-LV encryption is not supported; use disk.luks.preset for
   PV-level LUKS"`. The field stays; the prior `#7 not yet implemented`
   reservation is closed by this work.

**Deliberately NOT validated** (handled downstream):

- Tang server reachability. Not probed at `ks-gen gen` time.
- Passphrase strength. Operator policy.
- Thumbprint correctness vs. server URL. Verified out-of-band via
  `clevis-encrypt-tang -y`.

## Renderer

### Helper module

New `src/ks_gen/disk_luks.py`:

```python
from pathlib import Path
from ks_gen.config import DiskLuks, LuksPreset


def resolve_passphrase(luks: DiskLuks) -> str | None:
    """Return the literal LUKS passphrase, or None if preset == NONE.

    Raises FileNotFoundError if passphrase_file is set but missing.
    Raises ValueError if the file is empty after whitespace strip.
    """
    if luks.preset == LuksPreset.NONE:
        return None
    if luks.passphrase is not None:
        return luks.passphrase
    p = Path(luks.passphrase_file)
    content = p.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(
            f"disk.luks.passphrase_file '{p}' is empty after whitespace strip"
        )
    return content


def kickstart_passphrase_quoted(passphrase: str) -> str:
    """Escape and double-quote for kickstart's --passphrase= flag.

    Backslash and double-quote are the only chars needing escape.
    """
    return '"' + passphrase.replace("\\", "\\\\").replace('"', '\\"') + '"'
```

Both functions are registered as Jinja globals in `skeleton.py` alongside
the existing `disk_layout` helpers.

### Macro for the `--encrypted` flags

New `src/ks_gen/templates/partials/_luks_flags.j2`:

```jinja2
{%- macro luks_pv_flags(cfg) -%}
{%- if cfg.disk.luks.preset.value != 'none' -%}
 --encrypted --luks-version=luks2 --passphrase={{ kickstart_passphrase_quoted(resolve_passphrase(cfg.disk.luks)) }}
{%- endif -%}
{%- endmacro -%}
```

The leading space inside `{%- if %}` is intentional: the macro output
appends after the existing `--size=1` (or `{{ OND }}`) on the `part pv.01`
line. When `preset == none`, the macro outputs nothing.

### Partial updates

**`partitioning_stig_server.j2`** — line 3 changes from
`part pv.01 --grow --size=1` to:

```jinja2
{% from 'partials/_luks_flags.j2' import luks_pv_flags -%}
... (unchanged through line 2) ...
part pv.01 --grow --size=1{{ luks_pv_flags(cfg) }}
```

**`partitioning_layout.j2`** — `part pv.01` line becomes:

```jinja2
part pv.01 --grow --size=1{{ OND }}{{ luks_pv_flags(cfg) }}
```

with the `{% from 'partials/_luks_flags.j2' import luks_pv_flags -%}`
import added near the top of the partial.

**`partitioning_minimal.j2`** — no change. The cross-field validator
rejects `minimal + LUKS` so the macro is never invoked from this partial.

### Tang `%post` block

When `disk.luks.preset == tang`, an additional `%post` block is emitted
in `ks.cfg.j2`, inserted AFTER `%packages` and BEFORE the existing
`%post --nochroot` (the oscap fetch block).

New partial `src/ks_gen/templates/partials/luks_tang_bind.j2`:

```jinja2
%post --erroronfail --log=/root/ks-post-clevis.log
set -euo pipefail

# Install clevis + tang bindings. Run after the rootfs is in place so
# the new system has the packages it needs to unlock at next boot.
dnf -y install clevis clevis-luks clevis-systemd

# Identify the LUKS device backing pv.01.
luks_dev=$(blkid -t TYPE=crypto_LUKS -o device | head -n1)
test -n "$luks_dev"  # fail loudly if no LUKS device found

# Bind each tang server. SSS threshold {{ cfg.disk.luks.tang.threshold }} of {{ cfg.disk.luks.tang.servers | length }}.
clevis luks bind -d "$luks_dev" -y sss '{
  "t": {{ cfg.disk.luks.tang.threshold }},
  "pins": {
    "tang": [
      {% for s in cfg.disk.luks.tang.servers -%}
      {"url": "{{ s.url }}", "thp": "{{ s.thumbprint }}"}{{ "," if not loop.last else "" }}
      {% endfor %}
    ]
  }
}'

systemctl enable clevis-luks-askpass.path
%end
```

Selector update in `ks.cfg.j2`:

```jinja2
{% if cfg.disk.luks.preset.value == 'tang' -%}
{% include 'partials/luks_tang_bind.j2' %}
{% endif -%}
```

The `-y sss` clause with `t: <threshold>` is clevis's Shamir Secret
Sharing pin syntax matching the threshold-of-N semantics in `Tang`.

### Package strategy

Tang binding requires `clevis`, `clevis-luks`, `clevis-systemd`. These
are installed via `dnf -y install` in the tang `%post` block, NOT added
to `Packages.required`. Rationale:

- Keeps the `packages` schema field purely operator-controlled.
- Avoids making the rendered host.yaml dependent on luks settings.
- `dnf` runs in the freshly-installed chroot which has network.

The chosen tradeoff: very slightly slower install (extra dnf transaction
at %post time) for cleaner separation of concerns.

## Tests

### A. Schema validation (extends `tests/test_config_schema.py`)

| Test | Purpose |
|---|---|
| `test_disk_luks_default_is_none` | `DiskLuks()` → preset=NONE, other fields default |
| `test_disk_luks_none_with_passphrase_rejected` | dead-config check |
| `test_disk_luks_none_with_passphrase_file_rejected` | dead-config check |
| `test_disk_luks_none_with_tang_rejected` | dead-config check |
| `test_disk_luks_partial_without_passphrase_rejected` | error mentions "passphrase or passphrase_file" |
| `test_disk_luks_partial_with_passphrase_ok` | inline accepted |
| `test_disk_luks_partial_with_passphrase_file_ok` | file path accepted |
| `test_disk_luks_passphrase_and_file_both_set_rejected` | mutex |
| `test_disk_luks_partial_with_tang_block_rejected` | dead-config check |
| `test_disk_luks_tang_without_servers_rejected` | min_length=1 |
| `test_disk_luks_tang_threshold_exceeds_servers_rejected` | cross-field |
| `test_disk_luks_tang_thumbprint_too_short_rejected` | regex |
| `test_disk_luks_tang_thumbprint_invalid_chars_rejected` | regex |
| `test_disk_luks_tang_with_passphrase_ok` | tang + passphrase fallback |
| `test_disk_minimal_plus_luks_rejected` | parametrized over `partial`/`tang` |
| `test_disk_stig_server_plus_luks_partial_ok` | supported combo |
| `test_disk_layout_plus_luks_partial_ok` | layout + luks works |
| `test_disk_lv_def_encrypted_true_rejected_with_pv_level_message` | updated message |

### B. Helper unit tests (new `tests/test_disk_luks.py`)

| Test | Purpose |
|---|---|
| `test_resolve_passphrase_none_preset_returns_none` | |
| `test_resolve_passphrase_inline` | |
| `test_resolve_passphrase_from_file` | tmp_path / "key" → returns content |
| `test_resolve_passphrase_from_file_strips_whitespace` | |
| `test_resolve_passphrase_from_missing_file_raises` | FileNotFoundError |
| `test_resolve_passphrase_from_empty_file_raises` | ValueError |
| `test_kickstart_passphrase_quoted_simple` | `hunter2` → `"hunter2"` |
| `test_kickstart_passphrase_quoted_escapes_backslash` | |
| `test_kickstart_passphrase_quoted_escapes_double_quote` | |
| `test_kickstart_passphrase_quoted_handles_unicode` | passes through |

### C. Golden snapshots (new in `tests/golden/`)

1. **`luks-partial-inline.host.yaml` + `test_luks_partial_inline.py`** —
   `disk.preset: stig_server` + `disk.luks: { preset: partial, passphrase: hunter2 }`.
   Snapshots full `ks.cfg`. Targeted assertions:
   - `part pv.01 --grow --size=1 --encrypted --luks-version=luks2 --passphrase="hunter2"` (whitespace-normalized)
   - No `clevis luks bind` line anywhere
   - `/boot` and `/boot/efi` DO NOT have `--encrypted`

2. **`luks-tang.host.yaml` + `test_luks_tang.py`** — `disk.layout` minimal
   + `disk.luks: { preset: tang, passphrase: fallback, tang: { servers: [...x2], threshold: 1 } }`.
   Snapshots full `ks.cfg`. Targeted assertions:
   - `part pv.01 ... --encrypted --luks-version=luks2 --passphrase="fallback"` present
   - `%post` block contains `clevis luks bind -d "$luks_dev" -y sss`
   - SSS JSON contains both tang URLs and thumbprints
   - `systemctl enable clevis-luks-askpass.path` present

3. **`luks-partial-sidecar.host.yaml` + `test_luks_partial_sidecar.py` +
   `luks-partial-sidecar.key` fixture** — exercises the file-read path
   end-to-end. Sidecar key file committed alongside the host.yaml; content
   is the known test secret `sidecartest`. Renderer reads the file, embeds
   in ks.cfg.

### D. Acceptance criteria (issue #7)

- ✅ "Cross-field validator rejects `tang` without at least one server
  entry" → schema test A.
- 🔶 "`partial` preset installs cleanly in Hyper-V, boots, `lsblk` shows
  expected encrypted/plain split" → cannot automate in CI. Manual
  verification step in `MINIMAL-TEST.md`-style checklist.
- 🔶 "`tang` preset installs cleanly against a test tang server, reboots
  without operator prompt, `clevis luks list` shows the binding" →
  manual. Requires a tang server fixture which is out of CI scope.

Golden tests pin rendered kickstart correctness; manual checklist
confirms runtime behavior on real hardware.

### E. Lint coverage

`ks-gen lint` already understands `part` directives. The
`--encrypted --luks-version=luks2 --passphrase="..."` form parses the
same way (additional flags tolerated). No lint changes required.

## Migration

Existing v0.4 `host.yaml` files keep working unchanged:

- No `disk.luks` block → defaults to `preset=none`. No LUKS, no change
  to rendered ks.cfg.
- `disk.layout.lvs[].encrypted: true` is still rejected, but the message
  now points at `disk.luks.preset` for the PV-level path instead of
  "not yet implemented".

The change is purely additive.

## Documentation

MANUAL.md gets a new `#### \`disk.luks\`` H4 subsection under §4.4
`disk`, modeled on the `disk.layout` subsection added in #8. Contents:

- The three presets, what each renders
- Passphrase source (inline vs sidecar) with the security note that
  inline passphrases land in VCS if `host.yaml` is committed
- Tang server config with thumbprint capture instructions
  (`clevis-encrypt-tang -y` one-liner)
- The `minimal + LUKS` constraint
- Post-install passphrase rotation pointer
  (`cryptsetup luksAddKey`/`luksRemoveKey`)
