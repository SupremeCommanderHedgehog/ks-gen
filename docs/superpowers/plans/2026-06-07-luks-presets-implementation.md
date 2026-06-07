# LUKS presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `disk.luks:` block to `host.yaml` that enables PV-level LUKS encryption with either passphrase or tang/clevis network-bound unlock, closing the `DiskLvDef.encrypted` reservation from #8.

**Architecture:** Four new Pydantic models (`LuksPreset`, `TangServer`, `Tang`, `DiskLuks`) mounted onto `Disk`. Two helper functions in `src/ks_gen/disk_luks.py` (`resolve_passphrase`, `kickstart_passphrase_quoted`) registered as Jinja globals. A reusable Jinja macro `_luks_flags.j2` injects `--encrypted --luks-version=luks2 --passphrase=...` onto the `part pv.01` line in both LVM-using partials (`partitioning_stig_server.j2` and `partitioning_layout.j2`). A new `luks_tang_bind.j2` partial emits a `%post` block that installs clevis and binds tang. Cross-field validators reject the `disk.preset=minimal + LUKS` combo and other invalid permutations at config-load.

**Tech Stack:** Python 3.11+ • Pydantic v2 • Jinja2 • pytest • syrupy

**Spec:** `docs/superpowers/specs/2026-06-07-luks-presets-design.md` (commit `2233c33` on this branch)

**Branch:** `feat/luks-presets` (already created; spec commit is the only commit)

---

## File map

**Create:**
- `src/ks_gen/disk_luks.py` — `resolve_passphrase`, `kickstart_passphrase_quoted`; consumes `DiskLuks`
- `src/ks_gen/templates/partials/_luks_flags.j2` — `luks_pv_flags(cfg)` macro
- `src/ks_gen/templates/partials/luks_tang_bind.j2` — `%post` block for clevis tang binding
- `tests/test_disk_luks.py` — helper unit tests
- `tests/golden/luks-partial-inline.host.yaml` + `tests/golden/test_luks_partial_inline.py`
- `tests/golden/luks-partial-sidecar.host.yaml` + `tests/golden/test_luks_partial_sidecar.py` + `tests/golden/luks-partial-sidecar.key`
- `tests/golden/luks-tang.host.yaml` + `tests/golden/test_luks_tang.py`

**Modify:**
- `src/ks_gen/config.py` — add `LuksPreset`, `TangServer`, `Tang`, `DiskLuks` models; mount `luks` on `Disk`; add HostConfig-level `_minimal_preset_rejects_luks` validator; update `DiskLvDef._encryption_deferred` rejection message
- `src/ks_gen/skeleton.py` — register `resolve_passphrase` and `kickstart_passphrase_quoted` as Jinja globals
- `src/ks_gen/templates/ks.cfg.j2` — add `{% include 'partials/luks_tang_bind.j2' %}` selector after `%packages`
- `src/ks_gen/templates/partials/partitioning_stig_server.j2` — add `luks_pv_flags(cfg)` import + invocation on `part pv.01`
- `src/ks_gen/templates/partials/partitioning_layout.j2` — same
- `tests/test_config_schema.py` — schema validation tests
- `MANUAL.md` — add `#### disk.luks` H4 subsection under §4.4

**Pre-commit chain (runs automatically on every `git commit`):** ruff check + ruff format --check + mypy + yaml/toml/json checkers. If a commit fails the chain, fix the issue and create a new commit — do not `--amend` or `--no-verify`.

**Commit signing (per global CLAUDE.md):** every commit MUST be signed:
```bash
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "..."
```

---

## Task 1: Add LuksPreset, TangServer, and Tang models

**Files:**
- Modify: `src/ks_gen/config.py` (insert after the existing `_STIG_REQUIRED_LV_MOUNTPOINTS` constant area, before the `Disk` class or anywhere appropriate at module scope)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_luks_preset_values():
    from ks_gen.config import LuksPreset
    assert LuksPreset.NONE.value == "none"
    assert LuksPreset.PARTIAL.value == "partial"
    assert LuksPreset.TANG.value == "tang"


def test_tang_server_valid():
    from ks_gen.config import TangServer
    s = TangServer(
        url="https://tang1.example.com",
        thumbprint="xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU",
    )
    assert s.url == "https://tang1.example.com"


def test_tang_server_rejects_non_http_url():
    from ks_gen.config import TangServer
    with pytest.raises(ValidationError):
        TangServer(
            url="ftp://tang1.example.com",
            thumbprint="xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU",
        )


def test_tang_server_thumbprint_too_short_rejected():
    from ks_gen.config import TangServer
    with pytest.raises(ValidationError):
        TangServer(url="https://tang1.example.com", thumbprint="short")


def test_tang_server_thumbprint_invalid_chars_rejected():
    from ks_gen.config import TangServer
    with pytest.raises(ValidationError):
        TangServer(
            url="https://tang1.example.com",
            thumbprint="invalid!@#chars in thumbprint here xx",
        )


def _tang_server_dict(n: int = 1) -> list[dict]:
    """Helper: returns n valid tang server dicts."""
    return [
        {
            "url": f"https://tang{i}.example.com",
            "thumbprint": "xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJ" + chr(ord("A") + i),
        }
        for i in range(n)
    ]


def test_tang_default_threshold_is_one():
    from ks_gen.config import Tang
    t = Tang.model_validate({"servers": _tang_server_dict(2)})
    assert t.threshold == 1


def test_tang_rejects_empty_servers():
    from ks_gen.config import Tang
    with pytest.raises(ValidationError):
        Tang.model_validate({"servers": []})


def test_tang_threshold_exceeds_servers_rejected():
    from ks_gen.config import Tang
    with pytest.raises(
        ValidationError,
        match=r"threshold \(2\) exceeds servers count \(1\)",
    ):
        Tang.model_validate({"servers": _tang_server_dict(1), "threshold": 2})


def test_tang_threshold_equal_servers_ok():
    from ks_gen.config import Tang
    t = Tang.model_validate({"servers": _tang_server_dict(2), "threshold": 2})
    assert t.threshold == 2
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k "luks_preset or tang_server or tang_default or tang_rejects or tang_threshold" -v`
Expected: 9 failures with ImportError on the new models.

- [ ] **Step 3: Implement the three models**

In `src/ks_gen/config.py`, insert near other StrEnums (find `class CryptoPolicy(StrEnum):` or similar; add nearby):

```python
class LuksPreset(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    TANG = "tang"
```

Then insert (anywhere at module scope, but near the other disk-related models is best):

```python
class TangServer(StrictModel):
    url: str = Field(..., pattern=r"^https?://[^\s/]+(/.*)?$")
    thumbprint: str = Field(..., pattern=r"^[A-Za-z0-9_-]{32,}$")


class Tang(StrictModel):
    servers: list[TangServer] = Field(..., min_length=1)
    threshold: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _threshold_within_servers(self) -> Tang:
        if self.threshold > len(self.servers):
            raise ValueError(
                f"disk.luks.tang.threshold ({self.threshold}) exceeds "
                f"servers count ({len(self.servers)}); threshold must be "
                f"<= servers count"
            )
        return self
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_config_schema.py -k "luks_preset or tang_server or tang_default or tang_rejects or tang_threshold" -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): add LuksPreset, TangServer, and Tang models

Field-level validation (URL regex, thumbprint base64url alphabet,
servers min_length=1) plus the threshold <= server count cross-field
check on Tang. DiskLuks lands in the next task.

Refs: #7"
```

---

## Task 2: Add DiskLuks model with all internal validators

**Files:**
- Modify: `src/ks_gen/config.py` (insert near `Tang` class)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_disk_luks_default_is_none():
    from ks_gen.config import DiskLuks, LuksPreset
    d = DiskLuks()
    assert d.preset == LuksPreset.NONE
    assert d.passphrase is None
    assert d.passphrase_file is None
    assert d.tang is None


def test_disk_luks_none_with_passphrase_rejected():
    from ks_gen.config import DiskLuks
    with pytest.raises(ValidationError, match=r"preset='none' rejects"):
        DiskLuks.model_validate({"preset": "none", "passphrase": "x"})


def test_disk_luks_none_with_passphrase_file_rejected():
    from ks_gen.config import DiskLuks
    with pytest.raises(ValidationError, match=r"preset='none' rejects"):
        DiskLuks.model_validate({"preset": "none", "passphrase_file": "/k"})


def test_disk_luks_none_with_tang_rejected():
    from ks_gen.config import DiskLuks
    with pytest.raises(ValidationError, match=r"preset='none' rejects"):
        DiskLuks.model_validate(
            {"preset": "none", "tang": {"servers": _tang_server_dict(1)}}
        )


def test_disk_luks_partial_without_passphrase_rejected():
    from ks_gen.config import DiskLuks
    with pytest.raises(
        ValidationError, match=r"requires passphrase or passphrase_file"
    ):
        DiskLuks.model_validate({"preset": "partial"})


def test_disk_luks_partial_with_passphrase_ok():
    from ks_gen.config import DiskLuks, LuksPreset
    d = DiskLuks.model_validate({"preset": "partial", "passphrase": "hunter2"})
    assert d.preset == LuksPreset.PARTIAL
    assert d.passphrase == "hunter2"


def test_disk_luks_partial_with_passphrase_file_ok():
    from ks_gen.config import DiskLuks
    d = DiskLuks.model_validate(
        {"preset": "partial", "passphrase_file": "/etc/ks-gen/luks.key"}
    )
    assert d.passphrase_file == "/etc/ks-gen/luks.key"


def test_disk_luks_passphrase_and_file_both_set_rejected():
    from ks_gen.config import DiskLuks
    with pytest.raises(ValidationError, match=r"mutually exclusive"):
        DiskLuks.model_validate(
            {
                "preset": "partial",
                "passphrase": "x",
                "passphrase_file": "/k",
            }
        )


def test_disk_luks_partial_with_tang_block_rejected():
    from ks_gen.config import DiskLuks
    with pytest.raises(ValidationError, match=r"rejects tang block"):
        DiskLuks.model_validate(
            {
                "preset": "partial",
                "passphrase": "x",
                "tang": {"servers": _tang_server_dict(1)},
            }
        )


def test_disk_luks_tang_without_tang_block_rejected():
    from ks_gen.config import DiskLuks
    with pytest.raises(
        ValidationError, match=r"preset='tang' requires disk\.luks\.tang"
    ):
        DiskLuks.model_validate({"preset": "tang", "passphrase": "x"})


def test_disk_luks_tang_with_passphrase_ok():
    from ks_gen.config import DiskLuks, LuksPreset
    d = DiskLuks.model_validate(
        {
            "preset": "tang",
            "passphrase": "fallback",
            "tang": {"servers": _tang_server_dict(2)},
        }
    )
    assert d.preset == LuksPreset.TANG
    assert d.tang is not None
    assert len(d.tang.servers) == 2
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k "disk_luks" -v`
Expected: 11 failures with ImportError on `DiskLuks`.

- [ ] **Step 3: Implement DiskLuks**

In `src/ks_gen/config.py`, insert after the `Tang` class:

```python
class DiskLuks(StrictModel):
    preset: LuksPreset = LuksPreset.NONE
    passphrase: str | None = None
    passphrase_file: str | None = None
    tang: Tang | None = None

    @model_validator(mode="after")
    def _validate_luks(self) -> DiskLuks:
        other_fields_set = (
            self.passphrase is not None
            or self.passphrase_file is not None
            or self.tang is not None
        )

        if self.preset == LuksPreset.NONE:
            if other_fields_set:
                raise ValueError(
                    "disk.luks.preset='none' rejects passphrase, "
                    "passphrase_file, and tang fields; set preset to "
                    "'partial' or 'tang'"
                )
            return self

        # preset != none from here on
        if self.passphrase is not None and self.passphrase_file is not None:
            raise ValueError(
                "disk.luks: passphrase and passphrase_file are mutually "
                "exclusive; specify one"
            )
        if self.passphrase is None and self.passphrase_file is None:
            raise ValueError(
                f"disk.luks.preset='{self.preset.value}' "
                f"requires passphrase or passphrase_file"
            )

        if self.preset == LuksPreset.TANG and self.tang is None:
            raise ValueError(
                "disk.luks.preset='tang' requires disk.luks.tang block "
                "with at least one server"
            )
        if self.preset != LuksPreset.TANG and self.tang is not None:
            raise ValueError(
                f"disk.luks.preset='{self.preset.value}' rejects tang "
                f"block; tang is only valid with preset='tang'"
            )

        return self
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_config_schema.py -k "disk_luks" -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): add DiskLuks model with internal validators

Five cross-field rules: preset=none rejects other fields; preset!=none
requires exactly one of passphrase/passphrase_file (mutex); preset=tang
requires tang block; preset!=tang rejects tang block.

Refs: #7"
```

---

## Task 3: Mount DiskLuks on Disk + HostConfig validator + DiskLvDef message update

**Files:**
- Modify: `src/ks_gen/config.py` (three changes: `Disk` model, `HostConfig` validator, `DiskLvDef._encryption_deferred` message)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_disk_default_has_luks_none():
    from ks_gen.config import Disk, LuksPreset
    d = Disk()
    assert d.luks.preset == LuksPreset.NONE


def test_disk_minimal_plus_luks_partial_rejected():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "disk": {
            "preset": "minimal",
            "luks": {"preset": "partial", "passphrase": "x"},
        },
    }
    with pytest.raises(
        ValidationError, match=r"disk\.preset='minimal' has no LVM PV"
    ):
        HostConfig.model_validate(payload)


def test_disk_minimal_plus_luks_tang_rejected():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "disk": {
            "preset": "minimal",
            "luks": {
                "preset": "tang",
                "passphrase": "fallback",
                "tang": {"servers": _tang_server_dict(1)},
            },
        },
    }
    with pytest.raises(
        ValidationError, match=r"disk\.preset='minimal' has no LVM PV"
    ):
        HostConfig.model_validate(payload)


def test_disk_stig_server_plus_luks_partial_ok():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "disk": {
            "preset": "stig_server",
            "luks": {"preset": "partial", "passphrase": "hunter2"},
        },
    }
    cfg = HostConfig.model_validate(payload)
    assert cfg.disk.luks.preset.value == "partial"


def test_disk_layout_plus_luks_partial_ok():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "disk": {
            "layout": {"lvs": _stig_layout_lvs()},
            "luks": {"preset": "partial", "passphrase": "hunter2"},
        },
    }
    cfg = HostConfig.model_validate(payload)
    assert cfg.disk.luks.preset.value == "partial"
    assert cfg.disk.layout is not None


def test_disk_lv_def_encrypted_true_rejected_with_pv_level_message():
    from ks_gen.config import DiskLvDef
    with pytest.raises(
        ValidationError,
        match=r"per-LV encryption is not supported; use disk\.luks\.preset",
    ):
        DiskLvDef(name="root", mount="/", size="15G", encrypted=True)
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_config_schema.py -k "disk_default_has_luks or disk_minimal_plus_luks or disk_stig_server_plus_luks or disk_layout_plus_luks or disk_lv_def_encrypted_true_rejected_with_pv_level" -v`
Expected: 6 failures (the validator and Disk.luks field don't exist yet; the DiskLvDef message check fails because the current message references #7).

- [ ] **Step 3: Mount `luks` on Disk**

In `src/ks_gen/config.py`, find the `Disk` class. Add a `luks` field (the model_validators stay; just add the new field):

```python
class Disk(StrictModel):
    preset: DiskPreset | None = None
    layout: DiskLayout | None = None
    luks: DiskLuks = Field(default_factory=DiskLuks)
    wipe: bool = True
    bootloader_password: str | None = None

    # ... existing model_validator and field_validator unchanged
```

- [ ] **Step 4: Update DiskLvDef's encrypted rejection message**

In `src/ks_gen/config.py`, find the `_encryption_deferred` field validator on `DiskLvDef`. Replace the error message:

```python
    @field_validator("encrypted")
    @classmethod
    def _encryption_deferred(cls, v: bool) -> bool:
        if v:
            raise ValueError(
                "per-LV encryption is not supported; use "
                "disk.luks.preset for PV-level LUKS"
            )
        return v
```

- [ ] **Step 5: Add HostConfig validator for minimal + LUKS**

In `src/ks_gen/config.py`, find the `HostConfig` class. Append a new `model_validator` next to the existing `_crypto_fips_mutex` and `_admin_credential_mutex`:

```python
    @model_validator(mode="after")
    def _minimal_preset_rejects_luks(self) -> HostConfig:
        if (
            self.disk.preset == DiskPreset.MINIMAL
            and self.disk.luks.preset != LuksPreset.NONE
        ):
            raise ValueError(
                "disk.preset='minimal' has no LVM PV; disk.luks "
                "requires disk.preset='stig_server' or disk.layout"
            )
        return self
```

- [ ] **Step 6: Verify all schema tests pass**

Run: `pytest tests/test_config_schema.py -v`
Expected: all passed (new tests + all existing tests).

Run regression on related files: `pytest tests/test_config_schema.py tests/test_loader.py tests/test_writer.py tests/golden/ -v`
Expected: all passed — the existing 5 golden snapshots use no `disk.luks` block so they get the default `preset=none` (no rendered change).

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): mount DiskLuks on Disk + minimal+LUKS HostConfig validator

Three changes:
- Disk gains an Optional luks field (default_factory=DiskLuks) so existing
  host.yamls without a disk.luks block stay valid.
- HostConfig._minimal_preset_rejects_luks rejects disk.preset='minimal' +
  disk.luks.preset!='none' since minimal has no LVM PV to encrypt.
- DiskLvDef._encryption_deferred message updated from \"#7 not yet
  implemented\" to \"use disk.luks.preset for PV-level LUKS\" — the
  reservation from #8 is closed by this work.

Refs: #7"
```

---

## Task 4: Add `resolve_passphrase` helper

**Files:**
- Create: `src/ks_gen/disk_luks.py`
- Test: `tests/test_disk_luks.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_disk_luks.py`:

```python
from pathlib import Path

import pytest

from ks_gen.config import DiskLuks
from ks_gen.disk_luks import resolve_passphrase


def test_resolve_passphrase_none_preset_returns_none():
    luks = DiskLuks()  # preset=NONE, no passphrase
    assert resolve_passphrase(luks) is None


def test_resolve_passphrase_inline():
    luks = DiskLuks.model_validate({"preset": "partial", "passphrase": "hunter2"})
    assert resolve_passphrase(luks) == "hunter2"


def test_resolve_passphrase_from_file(tmp_path: Path):
    keyfile = tmp_path / "key"
    keyfile.write_text("hunter2\n", encoding="utf-8")
    luks = DiskLuks.model_validate(
        {"preset": "partial", "passphrase_file": str(keyfile)}
    )
    assert resolve_passphrase(luks) == "hunter2"


def test_resolve_passphrase_from_file_strips_whitespace(tmp_path: Path):
    keyfile = tmp_path / "key"
    keyfile.write_text("  hunter2  \n\n", encoding="utf-8")
    luks = DiskLuks.model_validate(
        {"preset": "partial", "passphrase_file": str(keyfile)}
    )
    assert resolve_passphrase(luks) == "hunter2"


def test_resolve_passphrase_from_missing_file_raises(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    luks = DiskLuks.model_validate(
        {"preset": "partial", "passphrase_file": str(missing)}
    )
    with pytest.raises(FileNotFoundError):
        resolve_passphrase(luks)


def test_resolve_passphrase_from_empty_file_raises(tmp_path: Path):
    keyfile = tmp_path / "empty"
    keyfile.write_text("   \n\n  ", encoding="utf-8")
    luks = DiskLuks.model_validate(
        {"preset": "partial", "passphrase_file": str(keyfile)}
    )
    with pytest.raises(ValueError, match=r"empty after whitespace strip"):
        resolve_passphrase(luks)
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_disk_luks.py -k "resolve_passphrase" -v`
Expected: 6 failures with ImportError on `ks_gen.disk_luks`.

- [ ] **Step 3: Create disk_luks module with resolve_passphrase**

Create `src/ks_gen/disk_luks.py`:

```python
from __future__ import annotations

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
    # Validator guarantees passphrase_file is set if passphrase isn't.
    assert luks.passphrase_file is not None
    p = Path(luks.passphrase_file)
    content = p.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(
            f"disk.luks.passphrase_file '{p}' is empty after whitespace strip"
        )
    return content
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_disk_luks.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/disk_luks.py tests/test_disk_luks.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(disk_luks): resolve_passphrase helper

Reads the passphrase from inline or sidecar file. Strips whitespace,
rejects empty content, lets FileNotFoundError surface to the caller.
None for preset=none.

Refs: #7"
```

---

## Task 5: Add `kickstart_passphrase_quoted` helper

**Files:**
- Modify: `src/ks_gen/disk_luks.py`
- Modify: `tests/test_disk_luks.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_disk_luks.py`:

```python
from ks_gen.disk_luks import kickstart_passphrase_quoted


def test_kickstart_passphrase_quoted_simple():
    assert kickstart_passphrase_quoted("hunter2") == '"hunter2"'


def test_kickstart_passphrase_quoted_escapes_backslash():
    assert kickstart_passphrase_quoted("a\\b") == '"a\\\\b"'


def test_kickstart_passphrase_quoted_escapes_double_quote():
    assert kickstart_passphrase_quoted('he"llo') == '"he\\"llo"'


def test_kickstart_passphrase_quoted_handles_unicode():
    # Anaconda accepts UTF-8 in --passphrase=
    assert kickstart_passphrase_quoted("pássphráse") == '"pássphráse"'


def test_kickstart_passphrase_quoted_escapes_both():
    # The order matters: escape backslash FIRST, then double-quote.
    # Otherwise the backslash from escaping " would itself get escaped.
    assert kickstart_passphrase_quoted('a"\\b') == '"a\\"\\\\b"'
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_disk_luks.py -k "kickstart_passphrase" -v`
Expected: 5 failures with ImportError on `kickstart_passphrase_quoted`.

- [ ] **Step 3: Add `kickstart_passphrase_quoted` to disk_luks.py**

Append to `src/ks_gen/disk_luks.py`:

```python
def kickstart_passphrase_quoted(passphrase: str) -> str:
    """Escape and double-quote for kickstart's --passphrase= flag.

    Backslash and double-quote are the only chars needing escape.
    Order matters: escape backslash first, then double-quote.
    """
    escaped = passphrase.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_disk_luks.py -v`
Expected: 11 passed (6 from Task 4 + 5 new).

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/disk_luks.py tests/test_disk_luks.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(disk_luks): kickstart_passphrase_quoted helper

Wraps the passphrase in double quotes, escaping backslashes (first)
and double quotes (second). Order matters — escaping backslashes after
double quotes would double-escape the backslash from quote escaping.

Refs: #7"
```

---

## Task 6: Register `resolve_passphrase` and `kickstart_passphrase_quoted` as Jinja globals

**Files:**
- Modify: `src/ks_gen/skeleton.py`
- Test: `tests/test_skeleton.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_skeleton.py`:

```python
def test_skeleton_jinja_env_exposes_disk_luks_helpers():
    from ks_gen.skeleton import _env
    env = _env()
    assert "resolve_passphrase" in env.globals
    assert "kickstart_passphrase_quoted" in env.globals
```

- [ ] **Step 2: Verify test fails**

Run: `pytest tests/test_skeleton.py::test_skeleton_jinja_env_exposes_disk_luks_helpers -v`
Expected: failure.

- [ ] **Step 3: Update skeleton.py**

In `src/ks_gen/skeleton.py`, find `_env()`. It already registers the `disk_layout` helpers. Add the two new disk_luks helpers in the same pattern:

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
    from ks_gen.disk_luks import (
        kickstart_passphrase_quoted,
        resolve_passphrase,
    )
    env.globals["effective_size_mb"] = effective_size_mb
    env.globals["effective_fsoptions"] = effective_fsoptions
    env.globals["size_to_mb"] = size_to_mb
    env.globals["resolve_passphrase"] = resolve_passphrase
    env.globals["kickstart_passphrase_quoted"] = kickstart_passphrase_quoted
    return env
```

- [ ] **Step 4: Verify test passes**

Run: `pytest tests/test_skeleton.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/skeleton.py tests/test_skeleton.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(skeleton): register disk_luks helpers as Jinja globals

Refs: #7"
```

---

## Task 7: Create the `_luks_flags.j2` macro

**Files:**
- Create: `src/ks_gen/templates/partials/_luks_flags.j2`
- Test: `tests/test_skeleton.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_skeleton.py`:

```python
def test_skeleton_luks_macro_none_emits_empty():
    from ks_gen.config import AdminUser, HostConfig, System, User
    from ks_gen.skeleton import _env

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 A a@b"],
                sudo="nopasswd_yes",
            )
        ),
    )
    env = _env()
    tmpl = env.from_string(
        "{% from 'partials/_luks_flags.j2' import luks_pv_flags %}"
        "BEFORE{{ luks_pv_flags(cfg) }}AFTER"
    )
    assert tmpl.render(cfg=cfg) == "BEFOREAFTER"


def test_skeleton_luks_macro_partial_emits_flags():
    from ks_gen.config import AdminUser, Disk, DiskLuks, HostConfig, System, User
    from ks_gen.skeleton import _env

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 A a@b"],
                sudo="nopasswd_yes",
            )
        ),
        disk=Disk(
            luks=DiskLuks.model_validate(
                {"preset": "partial", "passphrase": "hunter2"}
            )
        ),
    )
    env = _env()
    tmpl = env.from_string(
        "{% from 'partials/_luks_flags.j2' import luks_pv_flags %}"
        "BEFORE{{ luks_pv_flags(cfg) }}AFTER"
    )
    assert (
        tmpl.render(cfg=cfg)
        == 'BEFORE --encrypted --luks-version=luks2 --passphrase="hunter2"AFTER'
    )
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_skeleton.py -k "luks_macro" -v`
Expected: 2 failures with `TemplateNotFound: partials/_luks_flags.j2`.

- [ ] **Step 3: Create the macro partial**

Create `src/ks_gen/templates/partials/_luks_flags.j2`:

```jinja2
{#- Reusable macro: emits ' --encrypted --luks-version=luks2 --passphrase=...'
    when LUKS is enabled, or empty string when preset=none. The leading
    space inside the if-body is intentional so the macro appends cleanly
    after --size=1 (or --ondisk=sda from the layout partial). -#}
{%- macro luks_pv_flags(cfg) -%}
{%- if cfg.disk.luks.preset.value != 'none' -%}
 --encrypted --luks-version=luks2 --passphrase={{ kickstart_passphrase_quoted(resolve_passphrase(cfg.disk.luks)) }}
{%- endif -%}
{%- endmacro -%}
```

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_skeleton.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/templates/partials/_luks_flags.j2 tests/test_skeleton.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(templates): _luks_flags.j2 macro

Shared macro for both partitioning_stig_server.j2 and partitioning_layout.j2.
Emits the --encrypted --luks-version=luks2 --passphrase=... triplet when
disk.luks.preset != none, empty string otherwise. Leading space inside
the if-body lets callers concatenate without conditional logic.

Refs: #7"
```

---

## Task 8: Integrate `luks_pv_flags` macro into `partitioning_stig_server.j2`

**Files:**
- Modify: `src/ks_gen/templates/partials/partitioning_stig_server.j2`
- Test: existing golden tests should still pass; add a quick render check to confirm the macro fires.

- [ ] **Step 1: Update `partitioning_stig_server.j2`**

The current file's first 4 lines (per `src/ks_gen/templates/partials/partitioning_stig_server.j2`):

```
part /boot/efi --fstype=efi --size=1024 --asprimary
part /boot --fstype=xfs --size=1024 --fsoptions="nodev,nosuid" --asprimary
part pv.01 --grow --size=1
volgroup vg_root pv.01
```

Replace with:

```jinja2
{% from 'partials/_luks_flags.j2' import luks_pv_flags -%}
part /boot/efi --fstype=efi --size=1024 --asprimary
part /boot --fstype=xfs --size=1024 --fsoptions="nodev,nosuid" --asprimary
part pv.01 --grow --size=1{{ luks_pv_flags(cfg) }}
volgroup vg_root pv.01
```

(The `{% from ... %}` at the top is a Jinja statement with `-%}` whitespace control so it doesn't introduce a blank line. The `{{ luks_pv_flags(cfg) }}` invocation is appended to the existing `part pv.01` line.)

- [ ] **Step 2: Verify existing golden tests still pass**

Run: `pytest tests/golden/ -v`
Expected: all 7 existing golden tests pass (no `disk.luks` block in any fixture → macro emits empty string → byte-identical output).

- [ ] **Step 3: Commit**

```bash
git add src/ks_gen/templates/partials/partitioning_stig_server.j2
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(templates): wire luks_pv_flags into partitioning_stig_server.j2

Appends macro call to the part pv.01 line. When disk.luks.preset=none
(the default for all existing fixtures), the macro emits empty string
and the rendered output is byte-identical.

Refs: #7"
```

---

## Task 9: Integrate `luks_pv_flags` macro into `partitioning_layout.j2`

**Files:**
- Modify: `src/ks_gen/templates/partials/partitioning_layout.j2`

- [ ] **Step 1: Update `partitioning_layout.j2`**

Current state (the `part pv.01` line currently reads `part pv.01 --grow --size=1{{ OND }}`). Add the `{% from %}` import at the top of the file (right after any existing leading Jinja comment but before the OND set) and append the macro call to the pv.01 line:

Current beginning of file (read it first to confirm structure):
```
{# Layout-driven partitioning. ... #}
{# Trailing {{ "" }} on the logvol line is load-bearing: ... #}
{% set OND = (' --ondisk=' ~ cfg.disk.layout.ondisk) if cfg.disk.layout.ondisk else '' -%}
part /boot/efi ...
part /boot ...
part pv.01 --grow --size=1{{ OND }}
volgroup ...
```

Updated (add `{% from %}` immediately before the `{% set OND %}` line, and append `{{ luks_pv_flags(cfg) }}` to the `part pv.01` line):

```jinja2
{# Layout-driven partitioning. ... existing comment ... #}
{# Trailing {{ "" }} on the logvol line is load-bearing: ... existing comment ... #}
{% from 'partials/_luks_flags.j2' import luks_pv_flags -%}
{% set OND = (' --ondisk=' ~ cfg.disk.layout.ondisk) if cfg.disk.layout.ondisk else '' -%}
part /boot/efi ...
part /boot ...
part pv.01 --grow --size=1{{ OND }}{{ luks_pv_flags(cfg) }}
volgroup ...
```

- [ ] **Step 2: Verify existing golden tests still pass**

Run: `pytest tests/golden/ -v`
Expected: all 7 existing golden tests pass (the two layout-based goldens use no `disk.luks` → macro emits empty string → unchanged output).

- [ ] **Step 3: Commit**

```bash
git add src/ks_gen/templates/partials/partitioning_layout.j2
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(templates): wire luks_pv_flags into partitioning_layout.j2

Refs: #7"
```

---

## Task 10: Create `luks_tang_bind.j2` partial + selector in `ks.cfg.j2`

**Files:**
- Create: `src/ks_gen/templates/partials/luks_tang_bind.j2`
- Modify: `src/ks_gen/templates/ks.cfg.j2`
- Test: `tests/test_skeleton.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_skeleton.py`:

```python
def test_skeleton_tang_block_emitted_when_preset_tang():
    from ks_gen.config import AdminUser, Disk, DiskLuks, HostConfig, System, User
    from ks_gen.skeleton import render_skeleton

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 A a@b"],
                sudo="nopasswd_yes",
            )
        ),
        disk=Disk(
            luks=DiskLuks.model_validate(
                {
                    "preset": "tang",
                    "passphrase": "fallback",
                    "tang": {
                        "servers": [
                            {
                                "url": "https://tang1.example.com",
                                "thumbprint": "xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU",
                            },
                            {
                                "url": "https://tang2.example.com",
                                "thumbprint": "yL4IGHn-BWPbKWmA9pBp8vNdsKChiGDexr9XY9hrYKV",
                            },
                        ],
                        "threshold": 1,
                    },
                }
            )
        ),
    )
    out = render_skeleton(cfg, post_blocks=[])
    assert "dnf -y install clevis clevis-luks clevis-systemd" in out
    assert 'clevis luks bind -d "$luks_dev" -y sss' in out
    assert '"url": "https://tang1.example.com"' in out
    assert '"url": "https://tang2.example.com"' in out
    assert '"thp": "xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU"' in out
    assert '"t": 1' in out
    assert "systemctl enable clevis-luks-askpass.path" in out


def test_skeleton_tang_block_not_emitted_for_partial():
    from ks_gen.config import AdminUser, Disk, DiskLuks, HostConfig, System, User
    from ks_gen.skeleton import render_skeleton

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 A a@b"],
                sudo="nopasswd_yes",
            )
        ),
        disk=Disk(
            luks=DiskLuks.model_validate(
                {"preset": "partial", "passphrase": "x"}
            )
        ),
    )
    out = render_skeleton(cfg, post_blocks=[])
    assert "clevis luks bind" not in out
    assert "clevis-luks-askpass" not in out
```

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_skeleton.py -k "tang_block" -v`
Expected: 2 failures (the first because the partial doesn't exist; the second passes because no tang content is emitted yet — still helpful as a regression guard).

- [ ] **Step 3: Create the tang partial**

Create `src/ks_gen/templates/partials/luks_tang_bind.j2`:

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

- [ ] **Step 4: Update `ks.cfg.j2` selector**

In `src/ks_gen/templates/ks.cfg.j2`, find the `%packages` block. After its `%end`, insert the tang selector before the existing `%post --nochroot` block. The current order (approx):

```
%packages
...
%end

%post --nochroot --erroronfail --log=/mnt/sysimage/root/ks-post-oscap-fetch.log
```

Insert between them:

```jinja2
%end

{% if cfg.disk.luks.preset.value == 'tang' -%}
{% include 'partials/luks_tang_bind.j2' %}
{% endif -%}

%post --nochroot --erroronfail --log=/mnt/sysimage/root/ks-post-oscap-fetch.log
```

- [ ] **Step 5: Verify tests pass**

Run: `pytest tests/test_skeleton.py -k "tang_block" -v`
Expected: 2 passed.

Run all skeleton + golden tests:
Run: `pytest tests/test_skeleton.py tests/golden/ -v`
Expected: all pass (existing goldens unchanged since they use preset=none, which skips the include).

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/templates/partials/luks_tang_bind.j2 src/ks_gen/templates/ks.cfg.j2 tests/test_skeleton.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(templates): luks_tang_bind.j2 partial + ks.cfg.j2 selector

Emits a %post block (between %packages and the existing oscap %post)
that installs clevis-luks, binds the LUKS device to each configured
tang server using Shamir Secret Sharing (threshold-of-N), and enables
clevis-luks-askpass.path so the system unlocks via tang at next boot.

Refs: #7"
```

---

## Task 11: Golden test — luks-partial-inline

**Files:**
- Create: `tests/golden/luks-partial-inline.host.yaml`
- Create: `tests/golden/test_luks_partial_inline.py`

- [ ] **Step 1: Create the fixture**

Create `tests/golden/luks-partial-inline.host.yaml`:

```yaml
system:
  hostname: luks01.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYluks ops@bastion"
    sudo: nopasswd_yes
disk:
  preset: stig_server
  luks:
    preset: partial
    passphrase: hunter2
```

- [ ] **Step 2: Create the test**

Create `tests/golden/test_luks_partial_inline.py`:

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


def test_luks_partial_inline_snapshot(snapshot):
    yaml_path = Path(__file__).parent / "luks-partial-inline.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")


def test_luks_partial_inline_pv_encrypted():
    yaml_path = Path(__file__).parent / "luks-partial-inline.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    ks = bundle.ks_cfg
    pv_lines = [
        re.sub(r"\s+", " ", line.strip())
        for line in ks.splitlines()
        if line.strip().startswith("part pv.01")
    ]
    assert len(pv_lines) == 1
    assert (
        pv_lines[0]
        == 'part pv.01 --grow --size=1 --encrypted --luks-version=luks2 --passphrase="hunter2"'
    )


def test_luks_partial_inline_boot_not_encrypted():
    yaml_path = Path(__file__).parent / "luks-partial-inline.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    ks = bundle.ks_cfg
    boot_lines = [
        line
        for line in ks.splitlines()
        if line.startswith("part /boot/efi") or line.startswith("part /boot ")
    ]
    assert len(boot_lines) == 2
    for line in boot_lines:
        assert "--encrypted" not in line


def test_luks_partial_inline_no_tang_post_block():
    yaml_path = Path(__file__).parent / "luks-partial-inline.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    ks = bundle.ks_cfg
    assert "clevis luks bind" not in ks
    assert "clevis-luks-askpass" not in ks
```

- [ ] **Step 3: Generate the snapshot**

Run: `pytest tests/golden/test_luks_partial_inline.py -v --snapshot-update`
Expected: 4 passed; snapshot generated at `tests/golden/__snapshots__/test_luks_partial_inline.ambr`.

- [ ] **Step 4: Spot-check the snapshot**

Look at `tests/golden/__snapshots__/test_luks_partial_inline.ambr`. Verify:
- `part pv.01 --grow --size=1 --encrypted --luks-version=luks2 --passphrase="hunter2"`
- `/boot/efi` and `/boot` lines have no `--encrypted`
- No `%post --erroronfail --log=/root/ks-post-clevis.log` block

If anything looks wrong, STOP and report BLOCKED.

- [ ] **Step 5: Re-run without --snapshot-update**

Run: `pytest tests/golden/test_luks_partial_inline.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/golden/luks-partial-inline.host.yaml tests/golden/test_luks_partial_inline.py tests/golden/__snapshots__/test_luks_partial_inline.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): luks-partial-inline scenario

Exercises disk.preset=stig_server + disk.luks.preset=partial with
inline passphrase. Snapshot + targeted assertions confirm:
- part pv.01 carries --encrypted --luks-version=luks2 --passphrase=
- /boot and /boot/efi stay plain
- no tang %post block emitted

Refs: #7"
```

---

## Task 12: Golden test — luks-partial-sidecar (with sidecar key file)

**Files:**
- Create: `tests/golden/luks-partial-sidecar.key`
- Create: `tests/golden/luks-partial-sidecar.host.yaml`
- Create: `tests/golden/test_luks_partial_sidecar.py`

- [ ] **Step 1: Create the sidecar key fixture**

Create `tests/golden/luks-partial-sidecar.key` with this exact content (single line, terminating newline):

```
sidecartest
```

(This is a deliberate test fixture — the value `sidecartest` is obviously a placeholder, not a real credential. Acceptable for VCS commit.)

- [ ] **Step 2: Create the host.yaml fixture**

Create `tests/golden/luks-partial-sidecar.host.yaml`:

```yaml
system:
  hostname: luks02.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYluks2 ops@bastion"
    sudo: nopasswd_yes
disk:
  preset: stig_server
  luks:
    preset: partial
    passphrase_file: tests/golden/luks-partial-sidecar.key
```

(The path is RELATIVE to the project root, which is where `pytest` runs. The renderer reads via `Path(...).read_text()` which resolves relative paths against `os.getcwd()`.)

- [ ] **Step 3: Create the test**

Create `tests/golden/test_luks_partial_sidecar.py`:

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


# The yaml fixture's passphrase_file uses a path relative to the project
# root (tests/golden/luks-partial-sidecar.key). Pin cwd to the project
# root so resolution is deterministic regardless of where pytest is run.
_REPO_ROOT = Path(__file__).parent.parent.parent


def test_luks_partial_sidecar_renders_passphrase_from_file(monkeypatch):
    monkeypatch.chdir(_REPO_ROOT)
    yaml_path = Path(__file__).parent / "luks-partial-sidecar.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    ks = bundle.ks_cfg
    pv_lines = [
        re.sub(r"\s+", " ", line.strip())
        for line in ks.splitlines()
        if line.strip().startswith("part pv.01")
    ]
    assert len(pv_lines) == 1
    assert (
        pv_lines[0]
        == 'part pv.01 --grow --size=1 --encrypted --luks-version=luks2 --passphrase="sidecartest"'
    )


def test_luks_partial_sidecar_snapshot(monkeypatch, snapshot):
    monkeypatch.chdir(_REPO_ROOT)
    yaml_path = Path(__file__).parent / "luks-partial-sidecar.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")
```

- [ ] **Step 4: Generate the snapshot**

Run: `pytest tests/golden/test_luks_partial_sidecar.py -v --snapshot-update`
Expected: 2 passed; snapshot generated.

- [ ] **Step 5: Spot-check the snapshot**

Look at `tests/golden/__snapshots__/test_luks_partial_sidecar.ambr`. Verify the `part pv.01` line has `--passphrase="sidecartest"` (the value from the sidecar key file, not from the yaml).

- [ ] **Step 6: Re-run without --snapshot-update**

Run: `pytest tests/golden/test_luks_partial_sidecar.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add tests/golden/luks-partial-sidecar.key tests/golden/luks-partial-sidecar.host.yaml tests/golden/test_luks_partial_sidecar.py tests/golden/__snapshots__/test_luks_partial_sidecar.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): luks-partial-sidecar scenario

End-to-end exercise of disk.luks.passphrase_file. The .key sidecar
contains 'sidecartest' (an obvious test placeholder). Renderer reads
the file and embeds the value in the kickstart's --passphrase=.

Refs: #7"
```

---

## Task 13: Golden test — luks-tang (with disk.layout)

**Files:**
- Create: `tests/golden/luks-tang.host.yaml`
- Create: `tests/golden/test_luks_tang.py`

- [ ] **Step 1: Create the fixture**

Create `tests/golden/luks-tang.host.yaml`:

```yaml
system:
  hostname: luks03.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYluks3 ops@bastion"
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
  luks:
    preset: tang
    passphrase: fallback
    tang:
      servers:
        - url: https://tang1.example.com
          thumbprint: xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU
        - url: https://tang2.example.com
          thumbprint: yL4IGHn-BWPbKWmA9pBp8vNdsKChiGDexr9XY9hrYKV
      threshold: 1
```

- [ ] **Step 2: Create the test**

Create `tests/golden/test_luks_tang.py`:

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


def test_luks_tang_snapshot(snapshot):
    yaml_path = Path(__file__).parent / "luks-tang.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")


def test_luks_tang_pv_encrypted_with_fallback_passphrase():
    yaml_path = Path(__file__).parent / "luks-tang.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    ks = bundle.ks_cfg
    pv_lines = [
        re.sub(r"\s+", " ", line.strip())
        for line in ks.splitlines()
        if line.strip().startswith("part pv.01")
    ]
    assert len(pv_lines) == 1
    assert "--encrypted --luks-version=luks2" in pv_lines[0]
    assert '--passphrase="fallback"' in pv_lines[0]


def test_luks_tang_post_block_present():
    yaml_path = Path(__file__).parent / "luks-tang.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    ks = bundle.ks_cfg
    assert "dnf -y install clevis clevis-luks clevis-systemd" in ks
    assert 'clevis luks bind -d "$luks_dev" -y sss' in ks
    assert "systemctl enable clevis-luks-askpass.path" in ks


def test_luks_tang_post_block_has_both_servers_and_thumbprints():
    yaml_path = Path(__file__).parent / "luks-tang.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    ks = bundle.ks_cfg
    assert '"url": "https://tang1.example.com"' in ks
    assert '"url": "https://tang2.example.com"' in ks
    assert '"thp": "xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU"' in ks
    assert '"thp": "yL4IGHn-BWPbKWmA9pBp8vNdsKChiGDexr9XY9hrYKV"' in ks
    assert '"t": 1' in ks
```

- [ ] **Step 3: Generate the snapshot**

Run: `pytest tests/golden/test_luks_tang.py -v --snapshot-update`
Expected: 4 passed; snapshot generated.

- [ ] **Step 4: Spot-check the snapshot**

Look at `tests/golden/__snapshots__/test_luks_tang.ambr`. Verify:
- `part pv.01` line has `--encrypted --luks-version=luks2 --passphrase="fallback"`
- `%post --erroronfail --log=/root/ks-post-clevis.log` block present
- `clevis luks bind ... sss` line contains both tang URLs in correct JSON shape
- No misplaced or extra commas in the JSON

If the JSON looks malformed (e.g., trailing comma after last server), STOP and report BLOCKED.

- [ ] **Step 5: Re-run without --snapshot-update**

Run: `pytest tests/golden/test_luks_tang.py -v`
Expected: 4 passed.

- [ ] **Step 6: Run full suite**

Run: `pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add tests/golden/luks-tang.host.yaml tests/golden/test_luks_tang.py tests/golden/__snapshots__/test_luks_tang.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): luks-tang scenario

End-to-end exercise of disk.luks.preset=tang with two tang servers and
threshold-of-1 SSS. Tests confirm:
- part pv.01 carries --encrypted + --passphrase=\"fallback\"
- %post clevis bind block emitted with both servers + thumbprints
- clevis-luks-askpass.path enabled

Refs: #7"
```

---

## Task 14: MANUAL.md `#### disk.luks` subsection

**Files:**
- Modify: `MANUAL.md`

- [ ] **Step 1: Locate the existing `#### disk.layout` subsection**

Run: `grep -n "#### \`disk.layout\`" MANUAL.md`

Find the line number where `#### \`disk.layout\` (alternative to \`disk.preset\`)` is. The new `#### disk.luks` subsection should be inserted immediately AFTER that subsection ends and BEFORE the next `### 4.5 user.admin` heading.

- [ ] **Step 2: Insert the new subsection**

Append (between the end of the `disk.layout` subsection and the start of `### 4.5 user.admin`) the following Markdown:

````markdown
#### `disk.luks` (PV-level LUKS encryption)

Enables LUKS2 encryption on the LVM physical volume, with optional
clevis/tang network-bound unlock.

```yaml
disk:
  preset: stig_server     # or `disk.layout: ...`
  luks:
    preset: partial       # or "tang" or "none" (default)
    passphrase: hunter2   # OR passphrase_file (mutually exclusive)
    # tang only when preset == tang:
    # tang:
    #   servers:
    #     - url: https://tang1.example.com
    #       thumbprint: <sha256-base64url>
    #     - url: https://tang2.example.com
    #       thumbprint: <sha256-base64url>
    #   threshold: 1       # SSS threshold; default 1
```

| Preset | Behavior |
|---|---|
| `none` (default) | No LUKS. |
| `partial` | LUKS2 on the LVM PV (`pv.01`). All LVs inherit. `/boot` and `/boot/efi` stay plain. Passphrase unlock. |
| `tang` | Same coverage as `partial`. Adds a `%post` block that installs `clevis-luks`, binds to each tang server (Shamir Secret Sharing across servers with threshold-of-N), and enables `clevis-luks-askpass.path`. The `passphrase` field stays as a fallback if all tang servers are unreachable. |

**Passphrase source.** Provide exactly one of `passphrase:` (inline,
operator-friendly but lands in VCS if `host.yaml` is committed) or
`passphrase_file:` (relative-to-cwd path read at `ks-gen gen` time;
keep the file out of VCS).

**Tang thumbprint capture.** Tang servers advertise their signing key
via HTTPS. Capture the thumbprint with the same tool that does the
binding:

```bash
clevis-encrypt-tang '{"url": "https://tang1.example.com"}' < /dev/null 2>&1 \
  | grep -oP 'Trust the .*? Tang server.*? \(\K[^)]+'
```

Pin that thumbprint in `host.yaml` to prevent first-boot
trust-on-first-use weakness.

**Constraints.**

- `disk.preset: minimal` has no LVM PV — `disk.luks` is rejected at
  config-load. Use `disk.preset: stig_server` or `disk.layout` instead.
- Per-LV encryption via `disk.layout.lvs[].encrypted: true` is rejected
  at config-load with a pointer to `disk.luks.preset` (the supported
  PV-level path).
- LUKS2 + argon2id is FIPS-compatible on AlmaLinux 9.2+; no special
  configuration needed.

**Post-install rotation.** To rotate the passphrase later:

```bash
cryptsetup luksAddKey   /dev/<pv-device> [/path/to/new-key]
cryptsetup luksRemoveKey /dev/<pv-device> [/path/to/old-key]
```

For tang re-binding after a tang server rotates its key, re-run
`clevis luks bind` with the new thumbprint and remove the old slot
with `clevis luks unbind`.
````

- [ ] **Step 3: Smoke-test the doc rendering**

Read 20 lines around the insertion point with `head`/`cat`/your editor to confirm:

- Headings: `### 4.4 disk` (existing) → `#### \`disk.layout\`` (existing) → `#### \`disk.luks\`` (new) → `### 4.5 user.admin` (existing).
- Tables render: three columns / two columns where applicable.

- [ ] **Step 4: Commit**

```bash
git add MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs(manual): document disk.luks block

H4 under §4.4 disk, modeled on the disk.layout subsection (same pattern
as the H4 nesting fix from #8). Covers the three presets, passphrase
sources, tang thumbprint capture, constraints, and post-install
rotation pointer.

Closes the docs side of issue #7.

Refs: #7"
```

---

## Task 15: Push branch, open PR, watch CI, signed --no-ff merge

- [ ] **Step 1: Final local CI parity check**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```
Expected: all four steps pass; full test suite green (323 prior + new tests across schema, helper, skeleton, and 3 goldens).

- [ ] **Step 2: Push the branch**

```bash
git push -u origin feat/luks-presets
```

- [ ] **Step 3: Open the PR**

```bash
gh pr create -R SupremeCommanderHedgehog/ks-gen --title "feat(disk): add LUKS presets (closes #7)" --body "$(cat <<'EOF'
## Summary

Closes #7. Adds a \`disk.luks:\` block to \`host.yaml\` enabling PV-level LUKS encryption with either passphrase or tang/clevis network-bound unlock. Closes the \`DiskLvDef.encrypted\` reservation from #8 — that field's rejection message now points operators at \`disk.luks.preset\` for PV-level encryption.

## Scope

- Three presets: \`none\` (default), \`partial\` (PV-level LUKS + passphrase), \`tang\` (PV-level LUKS + clevis network-bound unlock with passphrase fallback)
- Passphrase supplied inline (\`passphrase:\`) or via sidecar file (\`passphrase_file:\`); mutex enforced
- Tang servers require thumbprint pinning; threshold-of-N Shamir Secret Sharing across servers
- Backwards compatible: existing host.yamls without \`disk.luks\` default to \`preset=none\` (no rendered change)
- Cross-field validator rejects \`disk.preset=minimal + LUKS\` (no LVM PV to encrypt)

## Out of scope (deferred)

- \`full\` preset (encrypting /boot requires exotic key sources)
- Per-LV LUKS (different operational model)
- Clevis TPM2 / YubiKey backends
- Tang server reachability probing at \`ks-gen gen\` time

## Test plan

- [ ] CI ruff job green
- [ ] CI test matrix (3.11 / 3.12 / 3.13) green
- [ ] Existing 5 golden snapshots still pass (no \`disk.luks\` block → preset=none → no rendered change)
- [ ] 3 new golden tests: luks-partial-inline, luks-partial-sidecar, luks-tang
- [ ] After merge: manual Hyper-V install of luks-partial-inline + \`lsblk\` showing crypto_LUKS on pv.01 (deferred to next manual verification cycle)
- [ ] After merge: manual install of luks-tang against a test tang server + reboot without prompt (deferred)

Spec: \`docs/superpowers/specs/2026-06-07-luks-presets-design.md\`
Plan: \`docs/superpowers/plans/2026-06-07-luks-presets-implementation.md\`
EOF
)"
```

- [ ] **Step 4: Wait for CI green**

Run: `gh pr checks <PR#> -R SupremeCommanderHedgehog/ks-gen --watch --interval 15`
Expected: ruff, test (3.11), test (3.12), test (3.13) all pass.

- [ ] **Step 5: Signed `--no-ff` merge**

```bash
git checkout main
git pull --ff-only origin main
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 merge --no-ff -S feat/luks-presets -m "Merge branch 'feat/luks-presets'

Adds the disk.luks block (issue #7). PV-level LUKS with passphrase or
tang/clevis network-bound unlock. Closes the per-LV encrypted-field
reservation from #8.

PR: https://github.com/SupremeCommanderHedgehog/ks-gen/pull/<PR#>
Closes: #7"
git push origin main
```

- [ ] **Step 6: Verify cleanup**

```bash
gh pr view <PR#> -R SupremeCommanderHedgehog/ks-gen --json state,mergedAt --jq .
gh issue view 7 -R SupremeCommanderHedgehog/ks-gen --json state --jq .
git branch -d feat/luks-presets
git push origin --delete feat/luks-presets  # may already be auto-deleted
```

Expected: PR `MERGED`, issue `CLOSED`, local branch deleted.

- [ ] **Step 7: Handle the release-please PR**

This is a `feat:` commit since v0.4.0, so release-please will open a PR for **v0.5.0**. Decide at merge time:

- v0.5.0 is genuinely user-facing (LUKS is a real new feature). Recommend merging the release PR to ship v0.5.0.

---

## Self-review notes (writing-plans skill)

**Spec coverage check:**

| Spec section | Plan task(s) |
|---|---|
| Architecture — Surface (preset table, integration with preset/layout) | Task 3 (HostConfig validator) |
| Schema — `LuksPreset` enum | Task 1 |
| Schema — `TangServer` + `Tang` | Task 1 |
| Schema — `DiskLuks` + internal validators | Task 2 |
| Schema — `Disk.luks` field + default | Task 3 |
| Validation — Passphrase mutex | Task 2 |
| Validation — preset=none rejects other fields | Task 2 |
| Validation — preset=tang requires tang block | Task 2 |
| Validation — preset!=tang rejects tang block | Task 2 |
| Validation — threshold ≤ servers | Task 1 |
| Validation — thumbprint regex | Task 1 |
| Validation — minimal + LUKS rejected | Task 3 |
| Validation — DiskLvDef.encrypted message update | Task 3 |
| Renderer — resolve_passphrase | Task 4 |
| Renderer — kickstart_passphrase_quoted | Task 5 |
| Renderer — Jinja globals registration | Task 6 |
| Renderer — _luks_flags.j2 macro | Task 7 |
| Renderer — partitioning_stig_server.j2 integration | Task 8 |
| Renderer — partitioning_layout.j2 integration | Task 9 |
| Renderer — luks_tang_bind.j2 + ks.cfg.j2 selector | Task 10 |
| Tests — schema validation (A) | Tasks 1–3 |
| Tests — helper unit (B) | Tasks 4–5 |
| Tests — golden luks-partial-inline (C.1) | Task 11 |
| Tests — golden luks-partial-sidecar (C.2 sidecar) | Task 12 |
| Tests — golden luks-tang (C.2 tang) | Task 13 |
| Tests — Hyper-V install (manual D) | Documented in PR body (Task 15) |
| Documentation — MANUAL.md | Task 14 |

No gaps.
