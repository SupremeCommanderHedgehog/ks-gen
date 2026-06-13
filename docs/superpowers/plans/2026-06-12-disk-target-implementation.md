# disk.target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `disk.target` to confine every disk-touching kickstart
directive (`ignoredisk`, `clearpart --drives`, `bootloader --boot-drive`,
`part --ondisk`) to a single named disk, hard-renaming the existing
`disk.layout.ondisk` field in the process.

**Architecture:** Pydantic `Disk` model gains a `target: str | None`
field with the same regex as the old `DiskLayout.ondisk` field, which is
removed. A shared Jinja macro `_ondisk.j2` emits the `--ondisk=<target>`
suffix consistently across all three partition partials. The top-level
`ks.cfg.j2` template emits `ignoredisk --only-use=`, propagates
`--drives=` into `clearpart`, and propagates `--boot-drive=` into
`bootloader`, all conditional on `cfg.disk.target`.

**Tech Stack:** Python 3.14, pydantic 2 (`StrictModel`, `frozen=True`),
Jinja2 (`trim_blocks=True`), pytest + syrupy snapshots, ruff + mypy.

---

## File Structure

**Modify:**
- `src/ks_gen/config.py` — add `Disk.target` (~line 254), remove
  `DiskLayout.ondisk` (line 121).
- `src/ks_gen/templates/ks.cfg.j2` — emit `ignoredisk` line, add
  `--drives=` to `clearpart`, add `--boot-drive=` to `bootloader`.
- `src/ks_gen/templates/partials/partitioning_layout.j2` — switch `OND`
  source from `cfg.disk.layout.ondisk` to the shared macro.
- `src/ks_gen/templates/partials/partitioning_minimal.j2` — apply
  shared macro to every `part` line.
- `src/ks_gen/templates/partials/partitioning_stig_server.j2` — apply
  shared macro to every `part` line.
- `tests/test_config_schema.py` — rename the three `ondisk` tests at
  lines 519, 525, 532 to exercise `Disk.target` instead, plus add the
  removal regression test.
- `tests/golden/layout-custom-sizes.host.yaml` — move `ondisk: sda` out
  of `disk.layout` and up to `disk.target: sda`.
- `tests/golden/test_layout_custom_sizes.py` — rename
  `test_layout_custom_sizes_ondisk_emitted_on_all_three_partitions` to
  reflect the new field, no other changes.
- `tests/golden/__snapshots__/test_layout_custom_sizes.ambr` —
  regenerate after the ks.cfg.j2 changes land.
- `MANUAL.md:329-335` — update the `disk:` example to use the new
  field name.

**Create:**
- `src/ks_gen/templates/partials/_ondisk.j2` — shared macro
  `ondisk_flag(cfg)` returning `' --ondisk=<target>'` when set, else
  empty string. Mirrors the structure of `_luks_flags.j2`.
- `tests/golden/minimal-targeted-disk.host.yaml` — fixture pinning
  `preset=minimal` + `target=sda` so the preset-partial fan-out has
  regression coverage.
- `tests/golden/test_minimal_targeted_disk.py` — snapshot test plus
  three explicit assertions on `ignoredisk`, `clearpart --drives=sda`,
  `bootloader --boot-drive=sda`.

**Out of scope (deferred):**
- `src/ks_gen/wizard/_disk.py` — no wizard surface in this PR.

---

### Task 0: Verify baseline before changes

**Files:** none — this task just confirms the working tree is on a
green baseline before any code changes.

- [ ] **Step 1: Confirm clean working tree on `main`**

Run: `git status`
Expected: `nothing to commit, working tree clean`. The `0d67511` design
spec commit should already be in `git log`.

- [ ] **Step 2: Run the CI parity check**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four pass. This locks in that nothing in the current
working tree is broken before the schema changes start.

- [ ] **Step 3: Create a feature branch**

Run: `git checkout -b feat/disk-target`
Expected: `Switched to a new branch 'feat/disk-target'`. All subsequent
commits land here.

---

### Task 1: Add `Disk.target` field and remove `DiskLayout.ondisk`

**Files:**
- Modify: `src/ks_gen/config.py:121` (remove `ondisk` from `DiskLayout`)
- Modify: `src/ks_gen/config.py:254-259` (add `target` to `Disk`)
- Modify: `tests/test_config_schema.py:519` (`test_disk_layout_minimal_valid`)
- Modify: `tests/test_config_schema.py:525-536` (the two `ondisk` tests)

- [ ] **Step 1: Write the failing schema tests**

Open `tests/test_config_schema.py`. Find `test_disk_layout_minimal_valid`
at line 514 and remove the `assert layout.ondisk is None` line (line
519). Replace the two `ondisk` tests at lines 525-536 with new tests on
`Disk.target`. The final state of that block should be:

```python
def test_disk_layout_minimal_valid():
    from ks_gen.config import DiskLayout

    layout = DiskLayout.model_validate({"lvs": _stig_layout_lvs()})
    assert layout.vg_name == "vg_root"
    assert len(layout.lvs) == 8
    assert layout.boot.size == "1G"
    assert layout.efi.size == "1G"


def test_disk_target_accepts_plain_basename():
    d = Disk.model_validate({"target": "sda"})
    assert d.target == "sda"


def test_disk_target_accepts_nvme():
    d = Disk.model_validate({"target": "nvme0n1"})
    assert d.target == "nvme0n1"


def test_disk_target_defaults_to_none():
    d = Disk.model_validate({})
    assert d.target is None


def test_disk_target_with_dev_prefix_rejected():
    with pytest.raises(ValidationError):
        Disk.model_validate({"target": "/dev/sda"})


def test_disk_target_with_leading_digit_rejected():
    with pytest.raises(ValidationError):
        Disk.model_validate({"target": "1sda"})


def test_disk_target_empty_rejected():
    with pytest.raises(ValidationError):
        Disk.model_validate({"target": ""})


def test_disk_layout_ondisk_field_removed():
    """Regression-lock the rename: the old field name now hard-fails."""
    from ks_gen.config import DiskLayout

    with pytest.raises(ValidationError):
        DiskLayout.model_validate({"ondisk": "sda", "lvs": _stig_layout_lvs()})
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `pytest tests/test_config_schema.py -k "disk_target or disk_layout_minimal_valid or ondisk_field_removed" -v`
Expected: most tests fail with `AttributeError: 'Disk' object has no
attribute 'target'` or `Disk` extra-field errors. The minimal_valid test
still passes since we just removed an assertion.

- [ ] **Step 3: Modify `src/ks_gen/config.py` — remove `DiskLayout.ondisk`**

Open `src/ks_gen/config.py`. At line 120-121 inside `class DiskLayout`,
delete the entire `ondisk` field line:

```python
class DiskLayout(StrictModel):
    ondisk: str | None = Field(default=None, pattern=r"^[a-zA-Z][a-zA-Z0-9]*$")  # DELETE THIS LINE
    boot: DiskBootPart = Field(default_factory=DiskBootPart)
```

After the edit, the class body starts directly with `boot:`.

- [ ] **Step 4: Modify `src/ks_gen/config.py` — add `Disk.target`**

In the `class Disk(StrictModel):` block at line 254-259, append the
`target` field after `bootloader_password`:

```python
class Disk(StrictModel):
    preset: DiskPreset | None = None
    layout: DiskLayout | None = None
    luks: DiskLuks = Field(default_factory=DiskLuks)
    wipe: bool = True
    bootloader_password: str | None = None
    target: str | None = Field(default=None, pattern=r"^[a-zA-Z][a-zA-Z0-9]*$")
```

- [ ] **Step 5: Run all schema tests to verify they pass**

Run: `pytest tests/test_config_schema.py -v`
Expected: all green. If any test fails with an unrelated message, stop
and investigate before continuing.

- [ ] **Step 6: Verify the full test suite still parses (some goldens will fail; that is expected)**

Run: `pytest -q --co tests/`
Expected: collection succeeds. Tests will FAIL when run because
`layout-custom-sizes.host.yaml` still contains `disk.layout.ondisk`; that
is fixed in Task 2. Do not run the full suite yet.

- [ ] **Step 7: Commit**

```powershell
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(config)!: rename disk.layout.ondisk to disk.target

Hard rename — pre-1.0 schema break. Existing host.yaml files with
disk.layout.ondisk now fail config-load. Follow-up commits wire
disk.target into ignoredisk, clearpart --drives, bootloader --boot-drive,
and the preset partition partials.

Refs #59"
```

---

### Task 2: Shared `_ondisk.j2` macro and layout-partial source switch

**Files:**
- Create: `src/ks_gen/templates/partials/_ondisk.j2`
- Modify: `src/ks_gen/templates/partials/partitioning_layout.j2:6` (drop
  the local `OND` set, import the macro, use it on each `part` line)
- Modify: `tests/golden/layout-custom-sizes.host.yaml:10-11` (move
  `ondisk: sda` up out of `disk.layout`)
- Modify: `tests/golden/test_layout_custom_sizes.py:23` (rename test)

- [ ] **Step 1: Move `ondisk: sda` to the new field in the fixture**

Edit `tests/golden/layout-custom-sizes.host.yaml`. The current top of
the `disk:` block is:

```yaml
disk:
  layout:
    ondisk: sda
    lvs:
      - {name: root, mount: /}
```

Replace with:

```yaml
disk:
  target: sda
  layout:
    lvs:
      - {name: root, mount: /}
```

- [ ] **Step 2: Rename the explicit-ondisk test**

In `tests/golden/test_layout_custom_sizes.py`, rename
`test_layout_custom_sizes_ondisk_emitted_on_all_three_partitions` to
`test_layout_custom_sizes_target_emitted_on_all_three_partitions`. The
body is unchanged — it still greps for `--ondisk=sda`, which is exactly
what the new behavior must emit.

- [ ] **Step 3: Run the renamed test to verify it fails**

Run: `pytest tests/golden/test_layout_custom_sizes.py::test_layout_custom_sizes_target_emitted_on_all_three_partitions -v`
Expected: FAIL. Either the fixture fails to load (DiskLayout no longer
accepts `ondisk`) — actually the fixture is fixed, so it loads. The
layout partial still reads `cfg.disk.layout.ondisk`, which is now always
None, so no `--ondisk=` is emitted. The test fails on the assertion
`"--ondisk=sda" in efi_line`.

- [ ] **Step 4: Create `src/ks_gen/templates/partials/_ondisk.j2`**

Create the file with this exact content:

```jinja
{#- Reusable macro: emits ' --ondisk=<target>' when cfg.disk.target is
    set, otherwise empty string. Leading space inside the if-body is
    intentional so the macro appends cleanly after the preceding flag. -#}
{%- macro ondisk_flag(cfg) -%}
{%- if cfg.disk.target %} --ondisk={{ cfg.disk.target }}
{%- endif -%}
{%- endmacro -%}
```

- [ ] **Step 5: Switch `partitioning_layout.j2` to the macro**

Open `src/ks_gen/templates/partials/partitioning_layout.j2`. Today's
file:

```jinja
{# Layout-driven partitioning. PV grows to fill remaining disk; LVs are
   fixed-size, leaving free VG space for operator extension. ondisk
   (when set) applies to /boot/efi, /boot, and the PV so the whole
   install lands on the named disk in multi-disk hosts. #}
{% from 'partials/_luks_flags.j2' import luks_pv_flags -%}
{% set OND = (' --ondisk=' ~ cfg.disk.layout.ondisk) if cfg.disk.layout.ondisk else '' -%}
part /boot/efi --fstype=efi --size={{ size_to_mb(cfg.disk.layout.efi.size) }} --asprimary{{ OND }}
part /boot --fstype={{ cfg.disk.layout.boot.fstype }} --size={{ size_to_mb(cfg.disk.layout.boot.size) }}{% if cfg.disk.layout.boot.fsoptions %} --fsoptions="{{ cfg.disk.layout.boot.fsoptions }}"{% endif %} --asprimary{{ OND }}
part pv.01 --grow --size=1{{ OND }}{{ luks_pv_flags(cfg) }}
volgroup {{ cfg.disk.layout.vg_name }} pv.01
```

Replace the header comment and the `OND` set with the macro import,
then call the macro at each `part` line. The final file:

```jinja
{# Layout-driven partitioning. PV grows to fill remaining disk; LVs are
   fixed-size, leaving free VG space for operator extension.
   disk.target (when set) is appended via ondisk_flag so the whole
   install lands on the named disk in multi-disk hosts. #}
{% from 'partials/_luks_flags.j2' import luks_pv_flags -%}
{% from 'partials/_ondisk.j2' import ondisk_flag -%}
part /boot/efi --fstype=efi --size={{ size_to_mb(cfg.disk.layout.efi.size) }} --asprimary{{ ondisk_flag(cfg) }}
part /boot --fstype={{ cfg.disk.layout.boot.fstype }} --size={{ size_to_mb(cfg.disk.layout.boot.size) }}{% if cfg.disk.layout.boot.fsoptions %} --fsoptions="{{ cfg.disk.layout.boot.fsoptions }}"{% endif %} --asprimary{{ ondisk_flag(cfg) }}
part pv.01 --grow --size=1{{ ondisk_flag(cfg) }}{{ luks_pv_flags(cfg) }}
volgroup {{ cfg.disk.layout.vg_name }} pv.01
{# Trailing {{ "" }} on the logvol line is load-bearing: the Jinja env
   uses trim_blocks=True which strips the newline after any {% block %}
   tag. The logvol line ends with {% endif %}, so without the empty
   expression tag the line's terminating newline gets eaten and all 8
   logvols fuse into one. The expression tag breaks the
   block-tag-at-EOL pattern, preserving the newline. #}
{% for lv in cfg.disk.layout.lvs -%}
logvol {{ lv.mount or 'swap' }} --vgname={{ cfg.disk.layout.vg_name }} --name={{ lv.name }} --fstype={{ lv.fstype }} {% set sz = effective_size_mb(lv) %}{% if sz == 'recommended' %}--recommended{% else %}--size={{ sz }}{% endif %}{% set fso = effective_fsoptions(lv) %}{% if fso %} --fsoptions="{{ fso }}"{% endif %}{{ "" }}
{% endfor %}
```

Diff is small: the comment changes from "ondisk" to "disk.target",
the `OND` line is replaced with the `ondisk_flag` macro import, and
each `{{ OND }}` becomes `{{ ondisk_flag(cfg) }}`.

- [ ] **Step 6: Run the renamed test to verify it passes**

Run: `pytest tests/golden/test_layout_custom_sizes.py::test_layout_custom_sizes_target_emitted_on_all_three_partitions -v`
Expected: PASS — the layout partial now sources `--ondisk=` from
`cfg.disk.target`.

- [ ] **Step 7: Run the existing snapshot test (no snapshot regen yet)**

Run: `pytest tests/golden/test_layout_custom_sizes.py -v`
Expected: `test_layout_custom_sizes` and
`test_layout_custom_sizes_explicit_sizes_used` still PASS. The output
is byte-identical to the prior snapshot — same `--ondisk=sda` on the
same three part lines.

- [ ] **Step 8: Commit**

```powershell
git add src/ks_gen/templates/partials/_ondisk.j2 `
        src/ks_gen/templates/partials/partitioning_layout.j2 `
        tests/golden/layout-custom-sizes.host.yaml `
        tests/golden/test_layout_custom_sizes.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "refactor(templates): centralize --ondisk via _ondisk.j2 macro

Replaces the inline OND set in partitioning_layout.j2 with a shared
ondisk_flag(cfg) macro that reads from cfg.disk.target. Output is
byte-identical for the layout-custom-sizes golden.

Refs #59"
```

---

### Task 3: Apply `_ondisk.j2` to the preset partials

**Files:**
- Modify: `src/ks_gen/templates/partials/partitioning_minimal.j2`
- Modify: `src/ks_gen/templates/partials/partitioning_stig_server.j2`
- Create: `tests/golden/minimal-targeted-disk.host.yaml`
- Create: `tests/golden/test_minimal_targeted_disk.py`

- [ ] **Step 1: Create the targeted-minimal fixture**

Create `tests/golden/minimal-targeted-disk.host.yaml`:

```yaml
system:
  hostname: targetedmin.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYminimal ops@bastion"
    sudo: nopasswd_yes
disk:
  target: sda
  preset: minimal
```

- [ ] **Step 2: Write the failing assertion test**

Create `tests/golden/test_minimal_targeted_disk.py`:

```python
from pathlib import Path

from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle


def test_minimal_targeted_disk_part_lines_carry_ondisk():
    yaml_path = Path(__file__).parent / "minimal-targeted-disk.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    lines = bundle.ks_cfg.splitlines()
    part_lines = [line for line in lines if line.startswith("part ")]
    assert len(part_lines) == 4, f"expected 4 part lines, got {part_lines}"
    for line in part_lines:
        assert "--ondisk=sda" in line, f"missing --ondisk=sda on: {line}"


def test_stig_server_targeted_emits_ondisk_on_pv():
    yaml = (
        "system:\n  hostname: stigsrv.example.com\n"
        "user:\n  admin:\n    name: opsadmin\n"
        "    authorized_keys:\n"
        '      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEY ops@bastion"\n'
        "    sudo: nopasswd_yes\n"
        "disk:\n  target: vda\n  preset: stig_server\n"
    )
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".host.yaml", delete=False) as fh:
        fh.write(yaml)
        path = Path(fh.name)
    try:
        bundle = build_bundle(load_host_config(path, sets=[]))
    finally:
        path.unlink()
    lines = bundle.ks_cfg.splitlines()
    pv_line = next(line for line in lines if line.startswith("part pv.01 "))
    assert "--ondisk=vda" in pv_line
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `pytest tests/golden/test_minimal_targeted_disk.py -v`
Expected: FAIL on the assertion `"--ondisk=sda" in line` (or
`"--ondisk=vda"` for stig_server). The preset partials emit no
`--ondisk=` today.

- [ ] **Step 4: Update `partitioning_minimal.j2` to use the macro**

Open `src/ks_gen/templates/partials/partitioning_minimal.j2`. Today's
file is four bare `part` lines. Replace with:

```jinja
{% from 'partials/_ondisk.j2' import ondisk_flag -%}
part /boot/efi --fstype=efi --size=1024 --asprimary{{ ondisk_flag(cfg) }}
part /boot --fstype=xfs --size=1024 --fsoptions="nodev,nosuid" --asprimary{{ ondisk_flag(cfg) }}
part / --fstype=xfs --grow --size=8192{{ ondisk_flag(cfg) }}
part swap --recommended{{ ondisk_flag(cfg) }}
```

- [ ] **Step 5: Update `partitioning_stig_server.j2` to use the macro**

Open `src/ks_gen/templates/partials/partitioning_stig_server.j2`. The
file imports `luks_pv_flags` and emits three `part` lines plus
`volgroup` plus `logvol` lines. Add the `_ondisk.j2` import and the
macro call on every `part` line. The final state:

```jinja
{% from 'partials/_luks_flags.j2' import luks_pv_flags -%}
{% from 'partials/_ondisk.j2' import ondisk_flag -%}
part /boot/efi --fstype=efi --size=1024 --asprimary{{ ondisk_flag(cfg) }}
part /boot --fstype=xfs --size=1024 --fsoptions="nodev,nosuid" --asprimary{{ ondisk_flag(cfg) }}
part pv.01 --grow --size=1{{ ondisk_flag(cfg) }}{{ luks_pv_flags(cfg) }}
volgroup vg_root pv.01
logvol /             --vgname=vg_root --name=root     --fstype=xfs --size=15360
logvol /home         --vgname=vg_root --name=home     --fstype=xfs --size=5120  --fsoptions="nodev,nosuid"
logvol /tmp          --vgname=vg_root --name=tmp      --fstype=xfs --size=3072  --fsoptions="nodev,nosuid,noexec"
logvol /var          --vgname=vg_root --name=var      --fstype=xfs --size=10240 --fsoptions="nodev"
logvol /var/log      --vgname=vg_root --name=varlog   --fstype=xfs --size=5120  --fsoptions="nodev,nosuid,noexec"
logvol /var/log/audit --vgname=vg_root --name=varlogaudit --fstype=xfs --size=3072 --fsoptions="nodev,nosuid,noexec"
logvol /var/tmp      --vgname=vg_root --name=vartmp   --fstype=xfs --size=2048  --fsoptions="nodev,nosuid,noexec"
logvol swap          --vgname=vg_root --name=swap     --fstype=swap --recommended
```

Diff against the existing file: two added lines (the `_ondisk.j2`
import, and the macro call on each `part` line). `logvol` lines are
unchanged because `--ondisk=` doesn't apply to logical volumes — the PV
already binds them to the target disk.

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `pytest tests/golden/test_minimal_targeted_disk.py -v`
Expected: PASS.

- [ ] **Step 7: Run the existing snapshot tests to confirm no regressions for target-unset goldens**

Run: `pytest tests/golden/ -v`
Expected: every existing snapshot test PASSES because the `ondisk_flag`
macro emits empty string when `cfg.disk.target` is None — output is
byte-identical for every golden that doesn't set `target`.
`test_layout_custom_sizes` is the only golden that sets `target` and its
snapshot will start drifting in Task 4, not yet.

- [ ] **Step 8: Commit**

```powershell
git add src/ks_gen/templates/partials/partitioning_minimal.j2 `
        src/ks_gen/templates/partials/partitioning_stig_server.j2 `
        tests/golden/minimal-targeted-disk.host.yaml `
        tests/golden/test_minimal_targeted_disk.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(templates): emit --ondisk on preset partial part lines

partitioning_minimal.j2 and partitioning_stig_server.j2 now use the
shared ondisk_flag macro so disk.target propagates to every part line
in the preset paths, not just the layout path.

Refs #59"
```

---

### Task 4: Emit `ignoredisk`, `clearpart --drives`, `bootloader --boot-drive`

**Files:**
- Modify: `src/ks_gen/templates/ks.cfg.j2:14-23`
- Modify: `tests/golden/__snapshots__/test_layout_custom_sizes.ambr`
  (regenerated by syrupy)

- [ ] **Step 1: Extend the targeted-minimal test with the three new assertions**

Open `tests/golden/test_minimal_targeted_disk.py` and append:

```python
def test_minimal_targeted_disk_emits_ignoredisk():
    yaml_path = Path(__file__).parent / "minimal-targeted-disk.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    assert "ignoredisk --only-use=sda" in bundle.ks_cfg


def test_minimal_targeted_disk_clearpart_carries_drives():
    yaml_path = Path(__file__).parent / "minimal-targeted-disk.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    assert "clearpart --all --initlabel --drives=sda" in bundle.ks_cfg


def test_minimal_targeted_disk_bootloader_carries_boot_drive():
    yaml_path = Path(__file__).parent / "minimal-targeted-disk.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    bootloader_line = next(
        line for line in bundle.ks_cfg.splitlines() if line.startswith("bootloader ")
    )
    assert "--boot-drive=sda" in bootloader_line
```

- [ ] **Step 2: Run the three new tests to verify they fail**

Run: `pytest tests/golden/test_minimal_targeted_disk.py -v`
Expected: the three new tests FAIL; the older two still PASS.

- [ ] **Step 3: Update `ks.cfg.j2` to emit the three new directives**

Open `src/ks_gen/templates/ks.cfg.j2`. Today's lines 14-24:

```jinja
rootpw --lock
{% if cfg.disk.bootloader_password -%}
bootloader --location=mbr --append="audit=1 audit_backlog_limit=8192{% if cfg.overrides.fips_mode %} fips=1{% endif %}" --password="{{ cfg.disk.bootloader_password }}"
{% else -%}
bootloader --location=mbr --append="audit=1 audit_backlog_limit=8192{% if cfg.overrides.fips_mode %} fips=1{% endif %}"
{% endif %}

{% if cfg.disk.wipe -%}
zerombr
clearpart --all --initlabel
{% endif -%}
```

Replace with the targeted variants. The `--boot-drive=` flag, when
present, goes between `--location=mbr` and `--append=`; the `--drives=`
flag goes on the end of `clearpart`. `ignoredisk` is inserted between
`rootpw` and `bootloader`:

```jinja
rootpw --lock
{% if cfg.disk.target -%}
ignoredisk --only-use={{ cfg.disk.target }}
{% endif -%}
{% set BOOT_DRIVE = (' --boot-drive=' ~ cfg.disk.target) if cfg.disk.target else '' -%}
{% if cfg.disk.bootloader_password -%}
bootloader --location=mbr{{ BOOT_DRIVE }} --append="audit=1 audit_backlog_limit=8192{% if cfg.overrides.fips_mode %} fips=1{% endif %}" --password="{{ cfg.disk.bootloader_password }}"
{% else -%}
bootloader --location=mbr{{ BOOT_DRIVE }} --append="audit=1 audit_backlog_limit=8192{% if cfg.overrides.fips_mode %} fips=1{% endif %}"
{% endif %}

{% if cfg.disk.wipe -%}
zerombr
clearpart --all --initlabel{% if cfg.disk.target %} --drives={{ cfg.disk.target }}{% endif %}
{% endif -%}
```

Three changes:
1. `{% if cfg.disk.target %}ignoredisk --only-use=...{% endif %}` block
   inserted after `rootpw --lock`.
2. New `BOOT_DRIVE` set var used in both `bootloader` branches.
3. `clearpart` line gains an inline `{% if %}` for `--drives=`.

- [ ] **Step 4: Run the three new tests to verify they pass**

Run: `pytest tests/golden/test_minimal_targeted_disk.py -v`
Expected: all five tests PASS.

- [ ] **Step 5: Regenerate the layout-custom-sizes snapshot**

The `layout-custom-sizes` golden has `target: sda` so its snapshot must
change in exactly three ways: a new `ignoredisk` line, `--drives=sda`
on `clearpart`, `--boot-drive=sda` on `bootloader`. Regenerate:

Run: `pytest tests/golden/test_layout_custom_sizes.py --snapshot-update -v`
Expected: snapshot updates. Then immediately:

Run: `git diff tests/golden/__snapshots__/test_layout_custom_sizes.ambr`
Expected output (paraphrased): three+/- pairs. The `bootloader` line
gains ` --boot-drive=sda` after `--location=mbr`. A new `ignoredisk
--only-use=sda` line appears between `rootpw --lock` and `bootloader`.
`clearpart --all --initlabel` becomes `clearpart --all --initlabel
--drives=sda`. Nothing else should change. **If anything else in the
diff is different — `part` lines, `%post` blocks, ordering, anything —
stop and investigate.**

- [ ] **Step 6: Run the full golden suite**

Run: `pytest tests/golden/ -v`
Expected: every test PASSES, including all the target-unset goldens
(`stig-strict`, `minimal-dhcp`, `luks-*`, etc.). Those snapshots are
byte-identical because none of them set `disk.target`, and every new
template branch is guarded by `{% if cfg.disk.target %}`.

- [ ] **Step 7: Run the full unit test suite**

Run: `pytest -q`
Expected: every test PASSES.

- [ ] **Step 8: Commit**

```powershell
git add src/ks_gen/templates/ks.cfg.j2 `
        tests/golden/test_minimal_targeted_disk.py `
        tests/golden/__snapshots__/test_layout_custom_sizes.ambr
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(templates): wire disk.target into ignoredisk/clearpart/bootloader

When cfg.disk.target is set:
- emit ignoredisk --only-use=<target> before bootloader
- append --drives=<target> to clearpart
- append --boot-drive=<target> to bootloader

Output is unchanged when disk.target is None — every new branch is
guarded.

Closes #59"
```

---

### Task 5: Update `MANUAL.md` example

**Files:**
- Modify: `MANUAL.md:329-335`

- [ ] **Step 1: Find the current example**

Open `MANUAL.md`. The relevant block at line 329-335 today shows:

```yaml
disk:
  layout:
    ondisk: sda           # optional, hints anaconda to use this disk
    lvs:
      - {name: root, mount: /}
      - {name: home, mount: /home}
```

- [ ] **Step 2: Rewrite the example**

Replace with:

```yaml
disk:
  target: sda             # optional; confines install (ignoredisk +
                          # clearpart --drives + bootloader --boot-drive +
                          # part --ondisk) to this disk in multi-disk hosts
  layout:
    lvs:
      - {name: root, mount: /}
      - {name: home, mount: /home}
```

- [ ] **Step 3: Skim the rest of `MANUAL.md` for other `ondisk` references**

Run: `git grep -n ondisk -- MANUAL.md`
Expected: no remaining matches.

- [ ] **Step 4: Commit**

```powershell
git add MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "docs(manual): use disk.target in multi-disk install example

Refs #59"
```

---

### Task 6: Final CI parity check

**Files:** none — verification only.

- [ ] **Step 1: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four PASS. If `ruff format --check` fails, fix with `ruff
format src tests`, then run the chain again, and commit the formatting
change as a `style:` commit (signed, same author overrides as above).

- [ ] **Step 2: Confirm no lingering `ondisk` references**

Run: `git grep -n -E "(disk\.layout\.ondisk|DiskLayout\.ondisk|layout\.ondisk)" -- src/ tests/`
Expected: no matches. The only remaining `ondisk` references in the
tree should be `--ondisk=` strings in templates/snapshots/test
assertions, plus historical mentions in the `docs/superpowers/specs/`
and `docs/superpowers/plans/` files (which document v0.4-era history and
are not changed by this PR).

- [ ] **Step 3: Confirm the diff is what we expect**

Run: `git log --oneline main..HEAD`
Expected: five commits (Tasks 1, 2, 3, 4, 5), each signed.

Run: `git diff --stat main..HEAD`
Expected: roughly these files changed —
`src/ks_gen/config.py`, `src/ks_gen/templates/ks.cfg.j2`,
`src/ks_gen/templates/partials/_ondisk.j2`,
`src/ks_gen/templates/partials/partitioning_layout.j2`,
`src/ks_gen/templates/partials/partitioning_minimal.j2`,
`src/ks_gen/templates/partials/partitioning_stig_server.j2`,
`tests/test_config_schema.py`, `tests/golden/layout-custom-sizes.host.yaml`,
`tests/golden/test_layout_custom_sizes.py`,
`tests/golden/__snapshots__/test_layout_custom_sizes.ambr`,
`tests/golden/minimal-targeted-disk.host.yaml`,
`tests/golden/test_minimal_targeted_disk.py`, `MANUAL.md`.

---

### Task 7: Push branch and surface install-regression recommendation

**Files:** none.

- [ ] **Step 1: Push the branch**

Run: `git push -u origin feat/disk-target`
Expected: branch created on origin. If push fails with `GH007: Your push
would publish a private email address`, stop and surface the message
from the user's global CLAUDE.md (don't fall back to the noreply form
silently). The user resolves it themselves.

- [ ] **Step 2: Open a PR via `gh pr create`**

Use a HEREDOC for the body so the bullet list renders correctly:

```powershell
gh pr create --title "feat(disk): add disk.target to confine install to a single disk (closes #59)" --body @'
## Summary

Adds `disk.target` to `Disk` and removes `DiskLayout.ondisk`. When
`disk.target` is set, the generated kickstart confines every
disk-touching directive to that disk: a new `ignoredisk --only-use=`
line, `clearpart --all --initlabel --drives=`, `bootloader
--location=mbr --boot-drive=`, and `--ondisk=` on every preset `part`
line via a new shared Jinja macro `partials/_ondisk.j2`.

**Breaking change.** Pre-1.0 schema rename. Existing host.yaml files
that use `disk.layout.ondisk:` will fail config-load with the standard
pydantic extra-field error. Move the value up to `disk.target:`.

Closes #59.

## Test plan

- [x] `ruff check && ruff format --check && mypy && pytest -q` green
- [x] Existing target-unset goldens byte-identical
- [x] New `minimal-targeted-disk` golden exercises preset + target
- [x] `test_disk_layout_ondisk_field_removed` regression-locks the rename
- [ ] **Recommended: install-regression harness.** This diff changes the
  preset partials, clearpart, and bootloader — per `CLAUDE.md`'s "When
  to recommend running it" guidance, the local install-regression
  harness in `.scratch/install-regression/` is appropriate. Bring up a
  second virtual disk in the QEMU VM and confirm only `target` is
  touched.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
'@
```

- [ ] **Step 3: Surface the install-regression recommendation in the
  end-of-turn message**

Tell the user: "Per CLAUDE.md, this diff touches preset partials,
clearpart, and bootloader — the install-regression harness in
`.scratch/install-regression/` is the appropriate next check. Bring up a
second virtual disk in the QEMU VM and confirm only the target disk is
touched. Should I describe the steps, or do you want to drive it
yourself?"

Do not run the harness from this session.
