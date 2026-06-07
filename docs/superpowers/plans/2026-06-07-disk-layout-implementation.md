# disk.layout Block Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `disk.layout:` block to `host.yaml` that lets operators size and customize LVM partitioning without dropping to raw kickstart directives, while preserving STIG-correct defaults.

**Architecture:** Three new Pydantic models on `HostConfig.disk` (`DiskLvDef`, `DiskBootPart`, `DiskEfiPart`, `DiskLayout`); a new Jinja partial `partitioning_layout.j2`; a helper module `src/ks_gen/disk_layout.py` exposing three render-time functions (`effective_size_mb`, `effective_fsoptions`, `size_to_mb`) registered as Jinja globals. The existing `Disk.preset` field becomes optional and mutually exclusive with the new `layout` field; both omitted falls back to `preset=STIG_SERVER` for v0.3 backwards compat.

**Tech Stack:** Python 3.11+ • Pydantic v2 • Jinja2 • pytest • syrupy

**Spec:** `docs/superpowers/specs/2026-06-07-disk-layout-block-design.md` (commit `dd69aec` on this branch)

**Branch:** `feat/disk-layout-block` (already created; spec commit is the only commit)

---

## File map

**Create:**
- `src/ks_gen/disk_layout.py` — render-time helpers; consumes `DiskLvDef`
- `src/ks_gen/templates/partials/partitioning_layout.j2` — new partial
- `tests/test_disk_layout_helpers.py` — unit tests for the three helpers
- `tests/golden/layout-stig-baseline.host.yaml` — fixture
- `tests/golden/test_layout_stig_baseline.py` — snapshot + equivalence test
- `tests/golden/layout-custom-sizes.host.yaml` — fixture
- `tests/golden/test_layout_custom_sizes.py` — snapshot test

**Modify:**
- `src/ks_gen/config.py` — add `DiskLvDef`, `DiskBootPart`, `DiskEfiPart`, `DiskLayout`; update `Disk` model + `_custom_not_yet_implemented` validator; add module-level `_DEFAULT_LV_SIZES`, `_DEFAULT_FSOPTIONS`, `_STIG_REQUIRED_MOUNTPOINTS` constants
- `src/ks_gen/skeleton.py` — register three Jinja globals on the environment
- `src/ks_gen/templates/ks.cfg.j2` — update partial selector at line 26
- `tests/test_config_schema.py` — add schema validation tests

**Pre-commit chain (runs automatically on every `git commit`):** ruff check + ruff format --check + mypy + yaml/toml/json checkers. If a commit fails the chain, fix the issue and create a new commit — do not `--amend` or `--no-verify`.

**Commit signing (per global CLAUDE.md):** every commit MUST be signed. Use:
```bash
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "..."
```

---

## Task 1: Add DiskLvDef schema with field-level validation

**Files:**
- Modify: `src/ks_gen/config.py` (insert after `DiskPreset` enum around line 54)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_disk_lv_def_minimal_valid():
    from ks_gen.config import DiskLvDef
    lv = DiskLvDef(name="root", mount="/", size="15G")
    assert lv.name == "root"
    assert lv.mount == "/"
    assert lv.size == "15G"
    assert lv.fstype == "xfs"
    assert lv.fsoptions is None
    assert lv.encrypted is False


def test_disk_lv_def_name_rejects_special_chars():
    from ks_gen.config import DiskLvDef
    with pytest.raises(ValidationError):
        DiskLvDef(name="root/path", mount="/", size="15G")


def test_disk_lv_def_size_rejects_bare_number():
    from ks_gen.config import DiskLvDef
    with pytest.raises(ValidationError):
        DiskLvDef(name="root", mount="/", size="15")


def test_disk_lv_def_size_rejects_unknown_unit():
    from ks_gen.config import DiskLvDef
    with pytest.raises(ValidationError):
        DiskLvDef(name="root", mount="/", size="15K")


def test_disk_lv_def_size_accepts_recommended():
    from ks_gen.config import DiskLvDef
    lv = DiskLvDef(name="swap", size="recommended", fstype="swap")
    assert lv.size == "recommended"


def test_disk_lv_def_size_accepts_omitted():
    from ks_gen.config import DiskLvDef
    lv = DiskLvDef(name="root", mount="/")
    assert lv.size is None


def test_disk_lv_def_encrypted_true_rejected():
    from ks_gen.config import DiskLvDef
    with pytest.raises(ValidationError, match=r"luks\.preset.*#7"):
        DiskLvDef(name="root", mount="/", size="15G", encrypted=True)
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k disk_lv_def -v`
Expected: 7 failures with ImportError on `DiskLvDef`.

- [ ] **Step 3: Implement DiskLvDef**

In `src/ks_gen/config.py`, insert after the `DiskPreset` enum (around line 54, before the `class Disk` line):

```python
class DiskLvDef(StrictModel):
    name: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    mount: str | None = None
    size: str | None = Field(
        default=None, pattern=r"^\d+(M|G|T)$|^recommended$"
    )
    fstype: Literal["xfs", "ext4", "swap"] = "xfs"
    fsoptions: str | None = None
    encrypted: bool = False

    @field_validator("encrypted")
    @classmethod
    def _encryption_deferred(cls, v: bool) -> bool:
        if v:
            raise ValueError(
                "disk.layout.lvs[].encrypted=true requires the luks.preset "
                "block (issue #7); not yet implemented."
            )
        return v
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_config_schema.py -k disk_lv_def -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): add DiskLvDef model

Field-level constraints only; cross-field validators land with DiskLayout
in subsequent tasks. The encrypted=true field is reserved for issue #7
(LUKS presets) and rejected with a pointer to that issue.

Refs: #8"
```

---

## Task 2: Helper `size_to_mb`

**Files:**
- Create: `src/ks_gen/disk_layout.py`
- Test: `tests/test_disk_layout_helpers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_disk_layout_helpers.py`:

```python
import pytest

from ks_gen.disk_layout import size_to_mb


def test_size_to_mb_megabytes():
    assert size_to_mb("500M") == 500


def test_size_to_mb_gigabytes():
    assert size_to_mb("15G") == 15360


def test_size_to_mb_one_gigabyte():
    assert size_to_mb("1G") == 1024
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_disk_layout_helpers.py -v`
Expected: 3 failures with ImportError on `ks_gen.disk_layout`.

- [ ] **Step 3: Create disk_layout module with `size_to_mb`**

Create `src/ks_gen/disk_layout.py`:

```python
from __future__ import annotations


def size_to_mb(size_str: str) -> int:
    """Convert size string like '15G' or '500M' to MB integer.

    Used for /boot and /boot/efi where 'recommended' isn't valid.
    """
    n, unit = int(size_str[:-1]), size_str[-1]
    return n * {"M": 1, "G": 1024}[unit]
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_disk_layout_helpers.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/disk_layout.py tests/test_disk_layout_helpers.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(disk_layout): size_to_mb helper

Refs: #8"
```

---

## Task 3: Helper `effective_size_mb` + LV size defaults

**Files:**
- Modify: `src/ks_gen/config.py` (add `_DEFAULT_LV_SIZES` after `DiskLvDef`)
- Modify: `src/ks_gen/disk_layout.py`
- Modify: `tests/test_disk_layout_helpers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_disk_layout_helpers.py`:

```python
from ks_gen.config import DiskLvDef
from ks_gen.disk_layout import effective_size_mb


def test_effective_size_mb_explicit():
    lv = DiskLvDef(name="data", mount="/data", size="20G")
    assert effective_size_mb(lv) == 20480


def test_effective_size_mb_default_for_var():
    lv = DiskLvDef(name="var", mount="/var")
    assert effective_size_mb(lv) == 10240


def test_effective_size_mb_default_for_root():
    lv = DiskLvDef(name="root", mount="/")
    assert effective_size_mb(lv) == 15360


def test_effective_size_mb_recommended_for_swap():
    lv = DiskLvDef(name="swap", fstype="swap")
    assert effective_size_mb(lv) == "recommended"


def test_effective_size_mb_explicit_recommended():
    lv = DiskLvDef(name="swap", size="recommended", fstype="swap")
    assert effective_size_mb(lv) == "recommended"
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_disk_layout_helpers.py -v`
Expected: 5 new failures with ImportError on `effective_size_mb`.

- [ ] **Step 3: Add `_DEFAULT_LV_SIZES` to config.py**

In `src/ks_gen/config.py`, insert after the `DiskLvDef` class:

```python
_DEFAULT_LV_SIZES: dict[str | None, str] = {
    "/":              "15G",
    "/home":          "5G",
    "/tmp":           "3G",
    "/var":           "10G",
    "/var/log":       "5G",
    "/var/log/audit": "3G",
    "/var/tmp":       "2G",
    None:             "recommended",  # swap LV
}
```

- [ ] **Step 4: Add `effective_size_mb` to disk_layout.py**

In `src/ks_gen/disk_layout.py`, add at the top after the existing import:

```python
from ks_gen.config import DiskLvDef, _DEFAULT_LV_SIZES
```

Then add the function:

```python
def effective_size_mb(lv: DiskLvDef) -> int | str:
    """Returns MB integer, or the string 'recommended' for swap-style sizing.

    Falls back to _DEFAULT_LV_SIZES when lv.size is None.
    """
    s = lv.size if lv.size is not None else _DEFAULT_LV_SIZES[lv.mount]
    if s == "recommended":
        return "recommended"
    n, unit = int(s[:-1]), s[-1]
    return n * {"M": 1, "G": 1024, "T": 1024 * 1024}[unit]
```

- [ ] **Step 5: Verify tests pass**

Run: `pytest tests/test_disk_layout_helpers.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/config.py src/ks_gen/disk_layout.py tests/test_disk_layout_helpers.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(disk_layout): effective_size_mb helper + LV size defaults

Defaults table mirrors partitioning_stig_server.j2 exactly. swap LV
(mount=None) defaults to 'recommended' which renders to kickstart's
--recommended flag.

Refs: #8"
```

---

## Task 4: Helper `effective_fsoptions` + fsoptions defaults

**Files:**
- Modify: `src/ks_gen/config.py` (add `_DEFAULT_FSOPTIONS`)
- Modify: `src/ks_gen/disk_layout.py`
- Modify: `tests/test_disk_layout_helpers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_disk_layout_helpers.py`:

```python
from ks_gen.disk_layout import effective_fsoptions


def test_effective_fsoptions_explicit_passthrough():
    lv = DiskLvDef(name="var", mount="/var", fsoptions="nodev,custom")
    assert effective_fsoptions(lv) == "nodev,custom"


def test_effective_fsoptions_default_for_var_log_audit():
    lv = DiskLvDef(name="varlogaudit", mount="/var/log/audit")
    assert effective_fsoptions(lv) == "nodev,nosuid,noexec"


def test_effective_fsoptions_default_for_home_is_baseline_only():
    # STIG baseline: /home gets nodev,nosuid but NOT noexec.
    lv = DiskLvDef(name="home", mount="/home")
    assert effective_fsoptions(lv) == "nodev,nosuid"
    assert "noexec" not in effective_fsoptions(lv)


def test_effective_fsoptions_none_for_root():
    lv = DiskLvDef(name="root", mount="/")
    assert effective_fsoptions(lv) is None


def test_effective_fsoptions_none_for_swap():
    lv = DiskLvDef(name="swap", fstype="swap")
    assert effective_fsoptions(lv) is None
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_disk_layout_helpers.py -v`
Expected: 5 new failures with ImportError on `effective_fsoptions`.

- [ ] **Step 3: Add `_DEFAULT_FSOPTIONS` to config.py**

In `src/ks_gen/config.py`, insert after `_DEFAULT_LV_SIZES`:

```python
_DEFAULT_FSOPTIONS: dict[str, str] = {
    "/home":          "nodev,nosuid",
    "/tmp":           "nodev,nosuid,noexec",
    "/var":           "nodev",
    "/var/log":       "nodev,nosuid,noexec",
    "/var/log/audit": "nodev,nosuid,noexec",
    "/var/tmp":       "nodev,nosuid,noexec",
}
```

- [ ] **Step 4: Add `effective_fsoptions` to disk_layout.py**

In `src/ks_gen/disk_layout.py`, update the import line:

```python
from ks_gen.config import DiskLvDef, _DEFAULT_FSOPTIONS, _DEFAULT_LV_SIZES
```

Then add the function:

```python
def effective_fsoptions(lv: DiskLvDef) -> str | None:
    """Returns explicit fsoptions if set; otherwise the STIG-baseline
    default for the mountpoint; otherwise None (for / and swap).
    """
    if lv.fsoptions is not None:
        return lv.fsoptions
    if lv.mount is None:
        return None
    return _DEFAULT_FSOPTIONS.get(lv.mount)
```

- [ ] **Step 5: Verify tests pass**

Run: `pytest tests/test_disk_layout_helpers.py -v`
Expected: 13 passed (5 + 3 + 5).

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/config.py src/ks_gen/disk_layout.py tests/test_disk_layout_helpers.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(disk_layout): effective_fsoptions helper + STIG defaults

/home defaults to nodev,nosuid (STIG baseline) — does NOT include
noexec, since STIG only requires nodev+nosuid on /home and noexec would
break legitimate user execution from ~/.local/bin etc.

Refs: #8"
```

---

## Task 5: DiskBootPart and DiskEfiPart schemas

**Files:**
- Modify: `src/ks_gen/config.py` (insert after `_DEFAULT_FSOPTIONS`)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_disk_boot_part_defaults():
    from ks_gen.config import DiskBootPart
    b = DiskBootPart()
    assert b.size == "1G"
    assert b.fstype == "xfs"
    assert b.fsoptions == "nodev,nosuid"


def test_disk_boot_part_rejects_T_unit():
    from ks_gen.config import DiskBootPart
    with pytest.raises(ValidationError):
        DiskBootPart(size="2T")


def test_disk_boot_part_accepts_M_and_G_units():
    from ks_gen.config import DiskBootPart
    assert DiskBootPart(size="500M").size == "500M"
    assert DiskBootPart(size="2G").size == "2G"


def test_disk_efi_part_defaults():
    from ks_gen.config import DiskEfiPart
    e = DiskEfiPart()
    assert e.size == "1G"


def test_disk_efi_part_rejects_T_unit():
    from ks_gen.config import DiskEfiPart
    with pytest.raises(ValidationError):
        DiskEfiPart(size="2T")
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k "disk_boot_part or disk_efi_part" -v`
Expected: 5 failures with ImportError.

- [ ] **Step 3: Implement DiskBootPart and DiskEfiPart**

In `src/ks_gen/config.py`, insert after `_DEFAULT_FSOPTIONS`:

```python
class DiskBootPart(StrictModel):
    size: str = Field(default="1G", pattern=r"^\d+(M|G)$")
    fstype: Literal["xfs", "ext4"] = "xfs"
    fsoptions: str | None = "nodev,nosuid"


class DiskEfiPart(StrictModel):
    size: str = Field(default="1G", pattern=r"^\d+(M|G)$")
    # fstype is always "efi" for the EFI System Partition; not configurable.
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_config_schema.py -k "disk_boot_part or disk_efi_part" -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): add DiskBootPart and DiskEfiPart models

Refs: #8"
```

---

## Task 6: DiskLayout basic schema (no cross-field validators yet)

**Files:**
- Modify: `src/ks_gen/config.py` (insert after `DiskEfiPart`)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_config_schema.py`:

```python
def _stig_layout_lvs():
    """Helper: returns the minimal STIG LV list (used by several layout tests)."""
    return [
        {"name": "root", "mount": "/"},
        {"name": "home", "mount": "/home"},
        {"name": "tmp", "mount": "/tmp"},
        {"name": "var", "mount": "/var"},
        {"name": "varlog", "mount": "/var/log"},
        {"name": "varlogaudit", "mount": "/var/log/audit"},
        {"name": "vartmp", "mount": "/var/tmp"},
        {"name": "swap", "fstype": "swap"},
    ]


def test_disk_layout_minimal_valid():
    from ks_gen.config import DiskLayout
    layout = DiskLayout.model_validate({"lvs": _stig_layout_lvs()})
    assert layout.vg_name == "vg_root"
    assert layout.ondisk is None
    assert len(layout.lvs) == 8
    assert layout.boot.size == "1G"
    assert layout.efi.size == "1G"


def test_disk_layout_ondisk_with_dev_prefix_rejected():
    from ks_gen.config import DiskLayout
    with pytest.raises(ValidationError):
        DiskLayout.model_validate({"ondisk": "/dev/sda", "lvs": _stig_layout_lvs()})


def test_disk_layout_ondisk_accepts_plain_basename():
    from ks_gen.config import DiskLayout
    layout = DiskLayout.model_validate({"ondisk": "nvme0n1", "lvs": _stig_layout_lvs()})
    assert layout.ondisk == "nvme0n1"


def test_disk_layout_empty_lvs_rejected():
    from ks_gen.config import DiskLayout
    with pytest.raises(ValidationError):
        DiskLayout.model_validate({"lvs": []})
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k disk_layout -v`
Expected: 4 failures with ImportError on `DiskLayout`.

- [ ] **Step 3: Implement DiskLayout (no cross-field validators yet)**

In `src/ks_gen/config.py`, insert after `DiskEfiPart`:

```python
class DiskLayout(StrictModel):
    ondisk: str | None = Field(default=None, pattern=r"^[a-zA-Z][a-zA-Z0-9]*$")
    boot: DiskBootPart = Field(default_factory=DiskBootPart)
    efi: DiskEfiPart = Field(default_factory=DiskEfiPart)
    vg_name: str = "vg_root"
    lvs: list[DiskLvDef] = Field(..., min_length=1)
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_config_schema.py -k disk_layout -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): add DiskLayout basic schema

Field-level validation only; cross-field validators (required
mountpoints, swap cardinality, uniqueness) land in subsequent tasks.

Refs: #8"
```

---

## Task 7: DiskLayout cross-field validators — required mountpoints + swap cardinality

**Files:**
- Modify: `src/ks_gen/config.py` (add module constant + model_validator to `DiskLayout`)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
REQUIRED_MOUNTS_FOR_PARAMETRIZE = [
    "/",
    "/home",
    "/tmp",
    "/var",
    "/var/log",
    "/var/log/audit",
    "/var/tmp",
]


@pytest.mark.parametrize("missing_mount", REQUIRED_MOUNTS_FOR_PARAMETRIZE)
def test_disk_layout_missing_required_mountpoint(missing_mount):
    from ks_gen.config import DiskLayout
    lvs = [lv for lv in _stig_layout_lvs() if lv.get("mount") != missing_mount]
    with pytest.raises(
        ValidationError,
        match=rf"disk\.layout missing STIG-required mountpoint: {re.escape(missing_mount)}",
    ):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_no_swap_rejected():
    from ks_gen.config import DiskLayout
    lvs = [lv for lv in _stig_layout_lvs() if lv["name"] != "swap"]
    with pytest.raises(ValidationError, match=r"exactly one swap"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_multiple_swap_rejected():
    from ks_gen.config import DiskLayout
    lvs = _stig_layout_lvs() + [{"name": "swap2", "fstype": "swap"}]
    with pytest.raises(ValidationError, match=r"exactly one swap"):
        DiskLayout.model_validate({"lvs": lvs})
```

Also add `import re` at the top of `tests/test_config_schema.py` if not already present.

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k "disk_layout_missing or disk_layout_no_swap or disk_layout_multiple_swap" -v`
Expected: 9 failures (7 parametrized + 2 swap) — validator doesn't exist yet, so the configs validate cleanly when they shouldn't.

- [ ] **Step 3: Add module constant and model_validator to DiskLayout**

In `src/ks_gen/config.py`, insert after `_DEFAULT_FSOPTIONS`:

```python
_STIG_REQUIRED_LV_MOUNTPOINTS: frozenset[str] = frozenset({
    "/",
    "/home",
    "/tmp",
    "/var",
    "/var/log",
    "/var/log/audit",
    "/var/tmp",
})
```

Then add this `model_validator` to `DiskLayout` (after the existing field declarations):

```python
    @model_validator(mode="after")
    def _validate_layout(self) -> DiskLayout:
        lv_mounts = {lv.mount for lv in self.lvs if lv.mount is not None}

        missing = _STIG_REQUIRED_LV_MOUNTPOINTS - lv_mounts
        if missing:
            mount = sorted(missing)[0]
            raise ValueError(
                f"disk.layout missing STIG-required mountpoint: {mount}"
            )

        swap_lvs = [lv for lv in self.lvs if lv.fstype == "swap"]
        if len(swap_lvs) != 1:
            raise ValueError(
                f"disk.layout requires exactly one swap LV "
                f"(fstype=swap, mount unset); found {len(swap_lvs)}"
            )

        return self
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_config_schema.py -k "disk_layout_missing or disk_layout_no_swap or disk_layout_multiple_swap" -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): DiskLayout validates required mountpoints + swap cardinality

Closes the issue #8 acceptance criterion: layout missing /var/log/audit
(or any other STIG-required mountpoint) hard-fails at config-load with
a specific error.

Refs: #8"
```

---

## Task 8: DiskLayout cross-field validators — name and mount uniqueness

**Files:**
- Modify: `src/ks_gen/config.py` (extend `_validate_layout`)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_disk_layout_duplicate_lv_name_rejected():
    from ks_gen.config import DiskLayout
    lvs = _stig_layout_lvs()
    lvs.append({"name": "root", "mount": "/extra"})  # duplicate name
    with pytest.raises(ValidationError, match=r"duplicate LV name"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_duplicate_lv_mount_rejected():
    from ks_gen.config import DiskLayout
    lvs = _stig_layout_lvs()
    lvs.append({"name": "extra", "mount": "/var"})  # duplicate mount
    with pytest.raises(ValidationError, match=r"duplicate LV mount"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_multiple_swap_lvs_without_mounts_still_caught_by_swap_cardinality():
    # Sanity check: two swap LVs both with mount=None aren't caught by the
    # mount-uniqueness check (mount=None is excluded) but ARE caught by
    # the swap cardinality check.
    from ks_gen.config import DiskLayout
    lvs = _stig_layout_lvs() + [{"name": "swap2", "fstype": "swap"}]
    with pytest.raises(ValidationError, match=r"exactly one swap"):
        DiskLayout.model_validate({"lvs": lvs})
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k "duplicate_lv_name or duplicate_lv_mount" -v`
Expected: 2 failures (cardinality test was already passing in Task 7).

- [ ] **Step 3: Extend `_validate_layout`**

In `src/ks_gen/config.py`, extend the `_validate_layout` method body (insert before `return self`):

```python
        names = [lv.name for lv in self.lvs]
        if len(names) != len(set(names)):
            seen: set[str] = set()
            for n in names:
                if n in seen:
                    raise ValueError(f"disk.layout duplicate LV name: {n}")
                seen.add(n)

        mounts = [lv.mount for lv in self.lvs if lv.mount is not None]
        if len(mounts) != len(set(mounts)):
            seen_m: set[str] = set()
            for m in mounts:
                if m in seen_m:
                    raise ValueError(f"disk.layout duplicate LV mount: {m}")
                seen_m.add(m)
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_config_schema.py -k "duplicate_lv_name or duplicate_lv_mount or multiple_swap_lvs_without_mounts" -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): DiskLayout rejects duplicate LV names and mounts

Refs: #8"
```

---

## Task 9: DiskLayout cross-field validators — custom-mount-needs-size + swap consistency

**Files:**
- Modify: `src/ks_gen/config.py` (extend `_validate_layout`)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_disk_layout_custom_mount_without_size_rejected():
    from ks_gen.config import DiskLayout
    lvs = _stig_layout_lvs()
    lvs.append({"name": "srv", "mount": "/srv"})  # custom mount, no size
    with pytest.raises(
        ValidationError,
        match=r"disk\.layout\.lvs\[srv\]\.size: required for custom mountpoint /srv",
    ):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_custom_mount_with_size_ok():
    from ks_gen.config import DiskLayout
    lvs = _stig_layout_lvs()
    lvs.append({"name": "srv", "mount": "/srv", "size": "50G"})
    layout = DiskLayout.model_validate({"lvs": lvs})
    assert layout.lvs[-1].name == "srv"


def test_disk_layout_stig_mount_without_size_ok():
    # /var is in the defaults table -> size may be omitted
    from ks_gen.config import DiskLayout
    layout = DiskLayout.model_validate({"lvs": _stig_layout_lvs()})
    var = next(lv for lv in layout.lvs if lv.mount == "/var")
    assert var.size is None  # validator passes; renderer fills 10G


def test_disk_layout_swap_with_mount_rejected():
    from ks_gen.config import DiskLayout
    lvs = _stig_layout_lvs()
    # Add a "swap" with a mount path — nonsense, must be rejected.
    lvs.append({"name": "weird", "mount": "/foo", "fstype": "swap"})
    with pytest.raises(ValidationError, match=r"swap LV.*mount.*null"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_non_swap_without_mount_rejected():
    from ks_gen.config import DiskLayout
    lvs = _stig_layout_lvs()
    lvs.append({"name": "weird", "fstype": "xfs"})  # no mount, no swap
    with pytest.raises(ValidationError, match=r"non-swap LV.*mount"):
        DiskLayout.model_validate({"lvs": lvs})
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k "custom_mount_without_size or custom_mount_with_size or stig_mount_without_size or swap_with_mount or non_swap_without_mount" -v`
Expected: 3 failures (the 2 OK-tests already pass from prior tasks; the 3 rejection-tests fail).

- [ ] **Step 3: Extend `_validate_layout`**

In `src/ks_gen/config.py`, extend `_validate_layout` body (still before `return self`):

```python
        for lv in self.lvs:
            # Swap consistency
            if lv.fstype == "swap" and lv.mount is not None:
                raise ValueError(
                    f"disk.layout.lvs[{lv.name}]: swap LV mount must be null "
                    f"(got {lv.mount!r})"
                )
            if lv.fstype != "swap" and lv.mount is None:
                raise ValueError(
                    f"disk.layout.lvs[{lv.name}]: non-swap LV requires a "
                    f"mount path"
                )

            # Size required for custom mountpoints
            if lv.size is None and lv.mount not in _DEFAULT_LV_SIZES:
                raise ValueError(
                    f"disk.layout.lvs[{lv.name}].size: required for custom "
                    f"mountpoint {lv.mount}; no default available"
                )
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_config_schema.py -k "custom_mount or stig_mount_without_size or swap_with_mount or non_swap_without_mount" -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): DiskLayout validates swap consistency and custom-mount sizes

Refs: #8"
```

---

## Task 10: Update Disk model for preset/layout mutex + backwards compat

**Files:**
- Modify: `src/ks_gen/config.py` (replace the existing `Disk` class)
- Modify: `tests/test_config_schema.py` (update `test_disk_preset_default`)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_disk_neither_defaults_to_stig_server():
    # v0.3 backwards compat: empty `disk:` block -> preset=STIG_SERVER
    from ks_gen.config import Disk, DiskPreset
    d = Disk()
    assert d.preset == DiskPreset.STIG_SERVER
    assert d.layout is None


def test_disk_preset_explicit_works():
    from ks_gen.config import Disk, DiskPreset
    d = Disk(preset=DiskPreset.MINIMAL)
    assert d.preset == DiskPreset.MINIMAL
    assert d.layout is None


def test_disk_layout_only_leaves_preset_none():
    from ks_gen.config import Disk
    payload = {"layout": {"lvs": _stig_layout_lvs()}}
    d = Disk.model_validate(payload)
    assert d.preset is None
    assert d.layout is not None


def test_disk_preset_and_layout_both_set_rejected():
    from ks_gen.config import Disk
    payload = {
        "preset": "stig_server",
        "layout": {"lvs": _stig_layout_lvs()},
    }
    with pytest.raises(ValidationError, match=r"mutually exclusive"):
        Disk.model_validate(payload)
```

Update the existing `test_disk_preset_default` to reflect the new shape (it currently asserts `d.preset == DiskPreset.STIG_SERVER` which still holds, but explicitly note `d.layout is None`):

```python
def test_disk_preset_default():
    d = Disk()
    assert d.preset == DiskPreset.STIG_SERVER
    assert d.layout is None
    assert d.wipe is True
    assert d.bootloader_password is None
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k "disk_neither or disk_preset_explicit or disk_layout_only or disk_preset_and_layout_both or disk_preset_default" -v`
Expected: 4 of 5 fail (the existing `test_disk_preset_default` still passes since the model is unchanged at this point).

- [ ] **Step 3: Replace the Disk class**

In `src/ks_gen/config.py`, REPLACE the existing `Disk` class entirely with:

```python
class Disk(StrictModel):
    preset: DiskPreset | None = None
    layout: DiskLayout | None = None
    wipe: bool = True
    bootloader_password: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _preset_xor_layout(cls, data: dict[str, object]) -> dict[str, object]:
        if not isinstance(data, dict):
            return data
        preset = data.get("preset")
        layout = data.get("layout")
        if preset is not None and layout is not None:
            raise ValueError(
                "disk.preset and disk.layout are mutually exclusive; "
                "specify one"
            )
        # v0.3 backwards-compat: both omitted -> default to STIG_SERVER
        if preset is None and layout is None:
            data["preset"] = DiskPreset.STIG_SERVER
        return data

    @field_validator("preset")
    @classmethod
    def _custom_not_yet_implemented(
        cls, v: DiskPreset | None
    ) -> DiskPreset | None:
        if v == DiskPreset.CUSTOM:
            raise ValueError(
                "disk.preset='custom' was reserved in v0.1-v0.3; use the "
                "disk.layout block instead."
            )
        return v
```

- [ ] **Step 4: Verify all schema tests pass**

Run: `pytest tests/test_config_schema.py -v`
Expected: all passed (including the 4 new tests and the updated `test_disk_preset_default`).

Run full schema regression: `pytest tests/test_config_schema.py tests/test_loader.py tests/test_writer.py -v`
Expected: all passed. This catches any place where old code expected `preset` to be non-None.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): Disk.preset becomes Optional, mutually exclusive with layout

mode='before' validator fills preset=STIG_SERVER when both are omitted
(preserves v0.3 behavior for host.yamls without an explicit disk block).
Updates the disk.preset='custom' rejection message to point at the new
disk.layout block.

Refs: #8"
```

---

## Task 11: Verify `disk.preset: custom` rejection message points at layout

**Files:**
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_config_schema.py`:

```python
def test_disk_preset_custom_rejected_with_layout_message():
    from ks_gen.config import Disk
    with pytest.raises(ValidationError, match=r"disk\.layout block"):
        Disk.model_validate({"preset": "custom"})
```

- [ ] **Step 2: Verify test passes**

Run: `pytest tests/test_config_schema.py -k disk_preset_custom_rejected_with_layout -v`
Expected: passed (Task 10 already changed the message; this is the regression guard).

- [ ] **Step 3: Commit**

```bash
git add tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(config): regression guard for disk.preset=custom message

Asserts the rejection message references the new disk.layout block, so
a future docstring rewrite can't silently drop the migration pointer.

Refs: #8"
```

---

## Task 12: Register Jinja globals in skeleton.py

**Files:**
- Modify: `src/ks_gen/skeleton.py`
- Test: `tests/test_skeleton.py` (existing) — add a regression test

- [ ] **Step 1: Write failing test**

Append to `tests/test_skeleton.py`:

```python
def test_skeleton_jinja_env_exposes_disk_layout_helpers():
    from ks_gen.skeleton import _env
    env = _env()
    assert "effective_size_mb" in env.globals
    assert "effective_fsoptions" in env.globals
    assert "size_to_mb" in env.globals
```

- [ ] **Step 2: Verify test fails**

Run: `pytest tests/test_skeleton.py::test_skeleton_jinja_env_exposes_disk_layout_helpers -v`
Expected: fail with `assert 'effective_size_mb' in env.globals` failing.

- [ ] **Step 3: Update skeleton.py**

In `src/ks_gen/skeleton.py`, modify `_env()` to register the three helpers:

```python
def _env() -> Environment:
    templates_path = files("ks_gen") / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_path)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    # Import locally to avoid module-load-time circular import risk.
    from ks_gen.disk_layout import (
        effective_fsoptions,
        effective_size_mb,
        size_to_mb,
    )
    env.globals["effective_size_mb"] = effective_size_mb
    env.globals["effective_fsoptions"] = effective_fsoptions
    env.globals["size_to_mb"] = size_to_mb
    return env
```

- [ ] **Step 4: Verify test passes**

Run: `pytest tests/test_skeleton.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/skeleton.py tests/test_skeleton.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(skeleton): register disk_layout helpers as Jinja globals

Refs: #8"
```

---

## Task 13: Create partitioning_layout.j2 partial + update selector

**Files:**
- Create: `src/ks_gen/templates/partials/partitioning_layout.j2`
- Modify: `src/ks_gen/templates/ks.cfg.j2` (line 26)
- Test: `tests/test_skeleton.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_skeleton.py`:

```python
def test_skeleton_renders_layout_partial_when_layout_set():
    from ks_gen.config import (
        AdminUser,
        DiskLayout,
        DiskLvDef,
        HostConfig,
        System,
        User,
        Disk,
    )
    from ks_gen.skeleton import render_skeleton

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(admin=AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"], sudo="nopasswd_yes")),
        disk=Disk(layout=DiskLayout(lvs=[
            DiskLvDef(name="root", mount="/"),
            DiskLvDef(name="home", mount="/home"),
            DiskLvDef(name="tmp", mount="/tmp"),
            DiskLvDef(name="var", mount="/var"),
            DiskLvDef(name="varlog", mount="/var/log"),
            DiskLvDef(name="varlogaudit", mount="/var/log/audit"),
            DiskLvDef(name="vartmp", mount="/var/tmp"),
            DiskLvDef(name="swap", fstype="swap"),
        ])),
    )
    out = render_skeleton(cfg, post_blocks=[])
    assert "part /boot/efi --fstype=efi" in out
    assert "volgroup vg_root pv.01" in out
    assert "logvol / --vgname=vg_root --name=root --fstype=xfs --size=15360" in out
    assert "logvol swap --vgname=vg_root --name=swap --fstype=swap --recommended" in out
    assert 'logvol /var/log/audit --vgname=vg_root --name=varlogaudit --fstype=xfs --size=3072 --fsoptions="nodev,nosuid,noexec"' in out


def test_skeleton_still_renders_preset_partial_when_preset_set():
    from ks_gen.config import AdminUser, HostConfig, System, User
    from ks_gen.skeleton import render_skeleton

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(admin=AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"], sudo="nopasswd_yes")),
    )
    out = render_skeleton(cfg, post_blocks=[])
    # The existing stig_server partial has aligned-column whitespace:
    assert "logvol /var/log/audit --vgname=vg_root --name=varlogaudit" in out
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_skeleton.py -k "skeleton_renders" -v`
Expected: failures — `TemplateNotFound: partials/partitioning_layout.j2`.

- [ ] **Step 3: Create the partial**

Create `src/ks_gen/templates/partials/partitioning_layout.j2`:

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

- [ ] **Step 4: Update the selector in ks.cfg.j2**

In `src/ks_gen/templates/ks.cfg.j2`, REPLACE line 26 (currently:
`{% include 'partials/partitioning_' ~ cfg.disk.preset.value ~ '.j2' %}`)
with:

```jinja2
{% if cfg.disk.layout -%}
{% include 'partials/partitioning_layout.j2' %}
{% else -%}
{% include 'partials/partitioning_' ~ cfg.disk.preset.value ~ '.j2' %}
{% endif %}
```

- [ ] **Step 5: Verify tests pass**

Run: `pytest tests/test_skeleton.py -v`
Expected: all passed.

Run full test suite: `pytest -q`
Expected: all passed. This catches any existing snapshot that broke due to the selector change (none should — the `else` branch preserves prior behavior).

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/templates/partials/partitioning_layout.j2 src/ks_gen/templates/ks.cfg.j2 tests/test_skeleton.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(templates): partitioning_layout.j2 partial + selector

The ks.cfg.j2 selector branches: layout-set -> partitioning_layout;
otherwise -> existing partitioning_<preset>.j2. --ondisk= (when set)
applies to /boot/efi, /boot, and the PV so all install partitions land
on the named disk in multi-disk scenarios.

Refs: #8"
```

---

## Task 14: Golden test — layout-stig-baseline (equivalence vs. preset)

**Files:**
- Create: `tests/golden/layout-stig-baseline.host.yaml`
- Create: `tests/golden/test_layout_stig_baseline.py`

- [ ] **Step 1: Create the fixture**

Create `tests/golden/layout-stig-baseline.host.yaml`:

```yaml
system:
  hostname: layout01.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYlayout ops@bastion"
    sudo: nopasswd_yes
disk:
  layout:
    lvs:
      - {name: root, mount: /}
      - {name: home, mount: /home}
      - {name: tmp, mount: /tmp}
      - {name: var, mount: /var}
      - {name: varlog, mount: /var/log}
      - {name: varlogaudit, mount: /var/log/audit}
      - {name: vartmp, mount: /var/tmp}
      - {name: swap, fstype: swap}
```

- [ ] **Step 2: Create a sibling fixture for the equivalence comparison**

Create `tests/golden/layout-stig-baseline-preset.host.yaml`:

```yaml
system:
  hostname: layout01.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYlayout ops@bastion"
    sudo: nopasswd_yes
disk:
  preset: stig_server
```

(Same host.yaml minus the layout block, with explicit `preset: stig_server`. Used by the test to render the "reference" output.)

- [ ] **Step 3: Create the test**

Create `tests/golden/test_layout_stig_baseline.py`:

```python
import re
from pathlib import Path

from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle


def _normalize(text: str) -> str:
    text = re.sub(r"Generated by ks-gen v\S+ on \S+", "Generated by ks-gen vSNAP on SNAP", text)
    text = re.sub(r"Generated: \S+", "Generated: SNAP", text)
    text = re.sub(r'<xccdf:version time="[^"]+"', '<xccdf:version time="SNAP"', text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _partitioning_lines(ks_cfg: str) -> list[str]:
    """Extract part/volgroup/logvol lines and collapse internal whitespace."""
    lines = []
    for raw in ks_cfg.splitlines():
        stripped = raw.strip()
        if stripped.startswith(("part ", "volgroup ", "logvol ")):
            # Collapse runs of whitespace to a single space.
            lines.append(re.sub(r"\s+", " ", stripped))
    return lines


def test_layout_stig_baseline_equivalent_to_preset(snapshot):
    layout_yaml = Path(__file__).parent / "layout-stig-baseline.host.yaml"
    preset_yaml = Path(__file__).parent / "layout-stig-baseline-preset.host.yaml"
    layout_bundle = build_bundle(load_host_config(layout_yaml, sets=[]))
    preset_bundle = build_bundle(load_host_config(preset_yaml, sets=[]))

    layout_part = _partitioning_lines(layout_bundle.ks_cfg)
    preset_part = _partitioning_lines(preset_bundle.ks_cfg)

    assert layout_part == preset_part, (
        "Layout-rendered partitioning must match preset-rendered "
        "partitioning after whitespace normalization. Diff:\n"
        f"  layout: {layout_part}\n  preset: {preset_part}"
    )


def test_layout_stig_baseline_snapshot(snapshot):
    layout_yaml = Path(__file__).parent / "layout-stig-baseline.host.yaml"
    bundle = build_bundle(load_host_config(layout_yaml, sets=[]))
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")
```

- [ ] **Step 4: Run tests; equivalence should pass, snapshot should generate**

Run: `pytest tests/golden/test_layout_stig_baseline.py -v --snapshot-update`
Expected: 2 passed; new snapshot file generated at `tests/golden/__snapshots__/test_layout_stig_baseline.ambr`.

- [ ] **Step 5: Inspect the snapshot**

Run: `git diff tests/golden/__snapshots__/test_layout_stig_baseline.ambr`

Manually verify:
- partitioning section emits `part /boot/efi`, `part /boot`, `part pv.01`, `volgroup vg_root`, and 8 logvol lines
- LV sizes match: root=15360, home=5120, tmp=3072, var=10240, varlog=5120, varlogaudit=3072, vartmp=2048, swap=--recommended
- fsoptions match the spec defaults table

- [ ] **Step 6: Re-run without --snapshot-update to confirm stability**

Run: `pytest tests/golden/test_layout_stig_baseline.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add tests/golden/layout-stig-baseline.host.yaml tests/golden/layout-stig-baseline-preset.host.yaml tests/golden/test_layout_stig_baseline.py tests/golden/__snapshots__/test_layout_stig_baseline.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): layout-stig-baseline equivalence + snapshot

Asserts the minimal layout block (STIG mountpoints with default sizes
and fsoptions) renders equivalent kickstart directives to disk.preset:
stig_server, after whitespace normalization within each line. This is
the spec-level guarantee that issue #8 acceptance criterion 2 hinges on.

Refs: #8"
```

---

## Task 15: Golden test — layout-custom-sizes

**Files:**
- Create: `tests/golden/layout-custom-sizes.host.yaml`
- Create: `tests/golden/test_layout_custom_sizes.py`

- [ ] **Step 1: Create the fixture**

Create `tests/golden/layout-custom-sizes.host.yaml`:

```yaml
system:
  hostname: layout02.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYlayoutcustom ops@bastion"
    sudo: nopasswd_yes
disk:
  layout:
    ondisk: sda
    lvs:
      - {name: root, mount: /}
      - {name: home, mount: /home}
      - {name: tmp, mount: /tmp}
      - {name: var, mount: /var, size: 20G}
      - {name: varlog, mount: /var/log, size: 10G}
      - {name: varlogaudit, mount: /var/log/audit}
      - {name: vartmp, mount: /var/tmp}
      - {name: srv, mount: /srv, size: 50G, fsoptions: "nodev,nosuid"}
      - {name: swap, fstype: swap}
```

- [ ] **Step 2: Create the test**

Create `tests/golden/test_layout_custom_sizes.py`:

```python
import re
from pathlib import Path

from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle


def _normalize(text: str) -> str:
    text = re.sub(r"Generated by ks-gen v\S+ on \S+", "Generated by ks-gen vSNAP on SNAP", text)
    text = re.sub(r"Generated: \S+", "Generated: SNAP", text)
    text = re.sub(r'<xccdf:version time="[^"]+"', '<xccdf:version time="SNAP"', text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def test_layout_custom_sizes(snapshot):
    yaml_path = Path(__file__).parent / "layout-custom-sizes.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")


def test_layout_custom_sizes_ondisk_emitted_on_all_three_partitions(snapshot):
    yaml_path = Path(__file__).parent / "layout-custom-sizes.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    ks = bundle.ks_cfg
    # All three install-partitioning lines must carry --ondisk=sda.
    assert "part /boot/efi" in ks and "--ondisk=sda" in [
        line for line in ks.splitlines() if "part /boot/efi" in line
    ][0]
    assert "part /boot " in ks and "--ondisk=sda" in [
        line for line in ks.splitlines() if line.startswith("part /boot ")
    ][0]
    assert "part pv.01" in ks and "--ondisk=sda" in [
        line for line in ks.splitlines() if "part pv.01" in line
    ][0]


def test_layout_custom_sizes_explicit_sizes_used(snapshot):
    yaml_path = Path(__file__).parent / "layout-custom-sizes.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    ks = bundle.ks_cfg
    # /var was set to 20G -> 20480, /var/log to 10G -> 10240, /srv 50G -> 51200
    assert "logvol /var --vgname=vg_root --name=var --fstype=xfs --size=20480" in ks
    assert "logvol /var/log --vgname=vg_root --name=varlog --fstype=xfs --size=10240" in ks
    assert 'logvol /srv --vgname=vg_root --name=srv --fstype=xfs --size=51200 --fsoptions="nodev,nosuid"' in ks
```

- [ ] **Step 3: Run tests; snapshot should generate**

Run: `pytest tests/golden/test_layout_custom_sizes.py -v --snapshot-update`
Expected: 3 passed; new snapshot at `tests/golden/__snapshots__/test_layout_custom_sizes.ambr`.

- [ ] **Step 4: Inspect snapshot**

Run: `git diff tests/golden/__snapshots__/test_layout_custom_sizes.ambr`

Manually verify the ks.cfg snapshot is sensible: ondisk on all three partitions, correct custom sizes, /srv as an extra LV with custom fsoptions.

- [ ] **Step 5: Re-run without --snapshot-update**

Run: `pytest tests/golden/test_layout_custom_sizes.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/golden/layout-custom-sizes.host.yaml tests/golden/test_layout_custom_sizes.py tests/golden/__snapshots__/test_layout_custom_sizes.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): layout-custom-sizes scenario

Exercises operator-customized layout: explicit sizes on /var and
/var/log, a custom /srv mountpoint with explicit size and fsoptions,
and ondisk: sda. The ondisk assertion verifies --ondisk= lands on
/boot/efi, /boot, and pv.01 — the multi-disk-safety guarantee from the
spec.

Refs: #8"
```

---

## Task 16: Documentation — MANUAL.md disk.layout section

**Files:**
- Modify: `MANUAL.md`

- [ ] **Step 1: Locate the existing disk section**

Run: `grep -n -i "disk" MANUAL.md | head -20`

Find the section that documents `disk.preset` (likely under a "Configuration" or "host.yaml schema" heading).

- [ ] **Step 2: Add a `disk.layout` subsection**

After the existing `disk.preset` documentation, append the following Markdown:

```markdown
### `disk.layout` (alternative to `disk.preset`)

For operators who need to customize partition sizes or add extra
mountpoints, `disk.layout` accepts a structured LVM definition. It is
mutually exclusive with `disk.preset`.

```yaml
disk:
  layout:
    ondisk: sda           # optional, hints anaconda to use this disk
    lvs:
      - {name: root, mount: /}
      - {name: home, mount: /home}
      - {name: tmp, mount: /tmp}
      - {name: var, mount: /var, size: 20G}     # override default 10G
      - {name: varlog, mount: /var/log}
      - {name: varlogaudit, mount: /var/log/audit}
      - {name: vartmp, mount: /var/tmp}
      - {name: srv, mount: /srv, size: 50G}     # custom mountpoint
      - {name: swap, fstype: swap}
```

LVs that mount a STIG-required path can omit `size:` and inherit the
default from this table:

| Mountpoint | Default size | Default fsoptions |
|---|---|---|
| `/` | 15G | (none) |
| `/home` | 5G | `nodev,nosuid` |
| `/tmp` | 3G | `nodev,nosuid,noexec` |
| `/var` | 10G | `nodev` |
| `/var/log` | 5G | `nodev,nosuid,noexec` |
| `/var/log/audit` | 3G | `nodev,nosuid,noexec` |
| `/var/tmp` | 2G | `nodev,nosuid,noexec` |
| swap | `--recommended` | (none) |

LVs that mount a non-STIG path (`/srv`, `/data`, etc.) must specify
`size:` explicitly. `fsoptions:` can be set explicitly on any LV to
override the default.

The PV grows to fill the disk; LVs are fixed-size, leaving free VG
space for future `lvextend`. The `/boot` and `/boot/efi` partitions
default to 1G xfs/efi respectively and can be overridden with a top-level
`boot:` or `efi:` block.

STIG-required mountpoints (`/`, `/home`, `/tmp`, `/var`, `/var/log`,
`/var/log/audit`, `/var/tmp`) are enforced at config-load — a layout
missing any of them fails with a specific error.

Encryption is not yet supported via the layout block (issue #7 will
add LUKS presets).
```

- [ ] **Step 3: Smoke-test the doc rendering**

No automated test for MANUAL.md. Open the file in a viewer (or `cat MANUAL.md | less`) and verify the new section reads cleanly and the table renders.

- [ ] **Step 4: Commit**

```bash
git add MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs(manual): document disk.layout block

Closes the docs side of issue #8.

Refs: #8"
```

---

## Task 17: Full regression + branch push + PR

- [ ] **Step 1: Run full local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```
Expected: all four steps pass; all tests green (including all existing snapshots — none should have regressed since the new code only adds the `if cfg.disk.layout` branch).

- [ ] **Step 2: Verify nothing else regressed**

Run: `pytest -q`
Expected: 263+ existing tests + new tests all green.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin feat/disk-layout-block
```

- [ ] **Step 4: Open the PR**

```bash
gh pr create -R SupremeCommanderHedgehog/ks-gen --title "feat(disk): add disk.layout block (closes #8)" --body "$(cat <<'EOF'
## Summary

Closes #8. Replaces the reserved `disk.preset: custom` token with a structured `disk.layout:` block. Operators can size and customize LVM partitioning without dropping to raw kickstart directives; STIG-baseline defaults match `disk.preset: stig_server` exactly.

## Scope

- LVM only (single PV / single VG)
- Mutually exclusive with `disk.preset`; both omitted → backwards-compat `preset=STIG_SERVER`
- STIG-required mountpoints enforced at config-load
- `encrypted: bool` field on LVs reserved for #7 (LUKS presets), rejected at load until that ships

## Out of scope (deferred)

- `scheme: plain` (use `disk.preset: minimal` for now)
- Multi-PV, multi-VG, explicit device names
- LUKS / at-rest encryption (#7)

## Test plan

- [ ] CI ruff job green
- [ ] CI test matrix (3.11 / 3.12 / 3.13) green
- [ ] `tests/golden/test_layout_stig_baseline.py::test_layout_stig_baseline_equivalent_to_preset` confirms the layout-block output matches the existing stig_server preset
- [ ] `tests/golden/test_layout_custom_sizes.py` snapshot reviewed
- [ ] After merge: manual Hyper-V install of the layout-custom-sizes scenario (deferred to next manual verification cycle)

Spec: \`docs/superpowers/specs/2026-06-07-disk-layout-block-design.md\`
Plan: \`docs/superpowers/plans/2026-06-07-disk-layout-implementation.md\`
EOF
)"
```

- [ ] **Step 5: Wait for CI green**

Run: `gh pr checks <PR#> -R SupremeCommanderHedgehog/ks-gen --watch --interval 15`
Expected: ruff, test (3.11), test (3.12), test (3.13) all pass.

- [ ] **Step 6: Signed `--no-ff` merge**

After CI green:
```bash
git checkout main
git pull --ff-only origin main
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 merge --no-ff -S feat/disk-layout-block -m "Merge branch 'feat/disk-layout-block'

Adds the disk.layout block (issue #8). Single PV/VG LVM scheme;
STIG-required mountpoints enforced at config-load; defaults match the
existing stig_server preset.

PR: https://github.com/SupremeCommanderHedgehog/ks-gen/pull/<PR#>
Closes: #8"
git push origin main
```

- [ ] **Step 7: Verify cleanup**

```bash
gh pr view <PR#> -R SupremeCommanderHedgehog/ks-gen --json state,mergedAt --jq .
gh issue view 8 -R SupremeCommanderHedgehog/ks-gen --json state --jq .
git branch -d feat/disk-layout-block
git push origin --delete feat/disk-layout-block  # may already be auto-deleted
```

Expected: PR `MERGED`, issue `CLOSED`, local branch deleted, remote branch deleted (or already absent).

- [ ] **Step 8: Confirm release-please reaction**

Run: `gh pr list -R SupremeCommanderHedgehog/ks-gen`

This commit is a `feat:` — release-please will open a release PR for **v0.4.0** (minor bump). Unlike the prior `chore`/`docs`/`ci` accumulation, this one is genuinely user-facing and should ship. Decide at merge time whether to merge the release PR immediately or accumulate one more `feat:` first.

---

## Self-review notes (writing-plans skill)

Run before handing the plan to the executor:

**Spec coverage check:**

| Spec section | Plan task(s) |
|---|---|
| Architecture — Surface (Disk.preset XOR Disk.layout) | Task 10 |
| Architecture — Schema (DiskLvDef) | Task 1 |
| Architecture — Schema (DiskBootPart, DiskEfiPart) | Task 5 |
| Architecture — Schema (DiskLayout) | Task 6 |
| Architecture — Defaults (size table) | Task 3 |
| Architecture — Defaults (fsoptions table) | Task 4 |
| Architecture — `/home` baseline rationale | Task 4 (assertion in test_effective_fsoptions_default_for_home_is_baseline_only) |
| Validation — preset/layout mutex | Task 10 |
| Validation — preset: custom rejected | Task 10 (message) + Task 11 (regression guard) |
| Validation — required mountpoints | Task 7 |
| Validation — swap cardinality | Task 7 |
| Validation — LV name uniqueness | Task 8 |
| Validation — LV mount uniqueness | Task 8 |
| Validation — custom mount needs size | Task 9 |
| Validation — swap consistency (mount/fstype) | Task 9 |
| Validation — encrypted=true deferred | Task 1 (field validator) |
| Validation — ondisk no /dev/ prefix | Task 6 (regex on Field) |
| Renderer — partitioning_layout.j2 partial | Task 13 |
| Renderer — ks.cfg.j2 selector update | Task 13 |
| Renderer — Jinja globals registration | Task 12 |
| Renderer — ondisk on all three partitions | Task 13 (partial), Task 15 (test assertion) |
| Helper — effective_size_mb | Task 3 |
| Helper — effective_fsoptions | Task 4 |
| Helper — size_to_mb | Task 2 |
| Tests A — schema validation | Tasks 1, 5–11 |
| Tests B — helper unit tests | Tasks 2–4 |
| Tests C — golden layout-stig-baseline | Task 14 |
| Tests C — golden layout-custom-sizes | Task 15 |
| Acceptance — preset/layout mutex | Task 10 |
| Acceptance — missing /var/log/audit specific error | Task 7 (parametrized) |
| Acceptance — Hyper-V install (manual) | Documented in PR description (Task 17 step 4) |
| Migration | Backwards compat covered by Task 10 |

No gaps.
