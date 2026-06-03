# Unattended Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `unattended_updates` rule plugin that configures `dnf-automatic` for nightly security updates and monthly full updates, plus a maintenance-window reboot timer, all configurable via `overrides.unattended_updates` in `host.yaml`.

**Architecture:** New pydantic config block (`UnattendedUpdatesCfg` and three nested models) lives in `src/ks_gen/config.py`. A new rule module `src/ks_gen/rules/unattended_updates.py` is auto-discovered by the existing `registry.load_rules()` and emits a `%post` bash fragment that (a) rewrites `/etc/dnf/automatic.conf` + drops in a `OnCalendar` override for the stock `dnf-automatic.timer`, (b) writes a separate config + custom systemd unit/timer pair for monthly full updates, (c) writes a `needs-restarting`-based reboot script + custom systemd unit/timer pair. Each of the three sub-blocks is independently togglable.

**Tech Stack:** Python 3.11+, pydantic 2.x, Jinja2 (`src/ks_gen/templates/ks.cfg.j2`), pytest + syrupy snapshots, ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-06-02-unattended-updates-design.md`

---

## File Map

**Modified:**

- `src/ks_gen/config.py` — Add `NightlySecurityCfg`, `MonthlyFullCfg`, `RebootWindowCfg`, `UnattendedUpdatesCfg`; wire into `Overrides`; extend `Packages.required` defaults with `dnf-automatic` and `dnf-utils`.
- `tests/test_config_schema.py` — Add coverage for the new defaults, the cross-field validator, and the two new package defaults.
- `tests/golden/__snapshots__/test_minimal_dhcp.ambr` — Regenerated (new defaults pull in the rule's `%post` fragment).
- `tests/golden/__snapshots__/test_stig_strict.ambr` — Regenerated.
- `tests/golden/__snapshots__/test_modern_crypto.ambr` — Regenerated.
- `tests/golden/__snapshots__/test_bare_metal_usbguard.ambr` — Regenerated.
- `MANUAL.md` — New `unattended_updates` block in §4.11, new "Unattended updates" row in §6 rule reference table.
- `MINIMAL-TEST.md` — Add post-install timer verification step.
- `CHANGELOG.md` — `[Unreleased]` (or `[0.2.0]`) section with the addition.

**Created:**

- `src/ks_gen/rules/unattended_updates.py` — The rule plugin.
- `tests/rules/test_unattended_updates.py` — Unit tests for the rule.
- `tests/golden/unattended-disabled.host.yaml` — Scenario fixture.
- `tests/golden/test_unattended_disabled.py` — Snapshot test driver.
- `tests/golden/__snapshots__/test_unattended_disabled.ambr` — Generated snapshot.

---

## Task 1: Add `unattended_updates` config models

**Files:**
- Modify: `src/ks_gen/config.py`
- Test: `tests/test_config_schema.py`

- [ ] **Step 1.1: Write failing tests for default-shaped models**

Add to `tests/test_config_schema.py` (append to the imports at the top and add the test functions at the end of the file):

```python
# Add to imports
from ks_gen.config import (
    MonthlyFullCfg,
    NightlySecurityCfg,
    RebootWindowCfg,
    UnattendedUpdatesCfg,
)

# Add at end of file
def test_unattended_updates_defaults_are_enabled():
    u = UnattendedUpdatesCfg()
    assert u.enable is True
    assert u.nightly_security.enable is True
    assert u.nightly_security.on_calendar == "*-*-* 02:00:00"
    assert u.monthly_full.enable is True
    assert u.monthly_full.on_calendar == "Sun *-*-1..7 02:30:00"
    assert u.reboot_window.enable is True
    assert u.reboot_window.on_calendar == "Sun *-*-* 03:00:00"


def test_unattended_updates_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        UnattendedUpdatesCfg.model_validate({"enable": True, "garbage": 1})


def test_unattended_updates_on_calendar_must_be_nonempty():
    with pytest.raises(ValidationError):
        NightlySecurityCfg(on_calendar="")
```

- [ ] **Step 1.2: Run failing tests**

```bash
pytest tests/test_config_schema.py::test_unattended_updates_defaults_are_enabled -v
```

Expected: FAIL with `ImportError` on `UnattendedUpdatesCfg` (or similar).

- [ ] **Step 1.3: Add the four pydantic models**

Insert into `src/ks_gen/config.py` immediately after the existing `DodRootCaCfg` class (before `class Overrides`):

```python
class NightlySecurityCfg(StrictModel):
    enable: bool = True
    on_calendar: str = Field(default="*-*-* 02:00:00", min_length=1)


class MonthlyFullCfg(StrictModel):
    enable: bool = True
    on_calendar: str = Field(default="Sun *-*-1..7 02:30:00", min_length=1)


class RebootWindowCfg(StrictModel):
    enable: bool = True
    on_calendar: str = Field(default="Sun *-*-* 03:00:00", min_length=1)


class UnattendedUpdatesCfg(StrictModel):
    enable: bool = True
    nightly_security: NightlySecurityCfg = Field(default_factory=NightlySecurityCfg)
    monthly_full: MonthlyFullCfg = Field(default_factory=MonthlyFullCfg)
    reboot_window: RebootWindowCfg = Field(default_factory=RebootWindowCfg)

    @model_validator(mode="after")
    def _reboot_window_needs_an_update_timer(self) -> UnattendedUpdatesCfg:
        if self.reboot_window.enable and not (
            self.nightly_security.enable or self.monthly_full.enable
        ):
            raise ValueError(
                "overrides.unattended_updates.reboot_window requires at least one "
                "update timer enabled (nightly_security or monthly_full) — "
                "otherwise the host will reboot weekly against a never-updated system."
            )
        return self
```

- [ ] **Step 1.4: Run tests to confirm pass**

```bash
pytest tests/test_config_schema.py::test_unattended_updates_defaults_are_enabled tests/test_config_schema.py::test_unattended_updates_rejects_unknown_fields tests/test_config_schema.py::test_unattended_updates_on_calendar_must_be_nonempty -v
```

Expected: 3 PASSED.

- [ ] **Step 1.5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): add UnattendedUpdatesCfg model"
```

---

## Task 2: Wire `unattended_updates` into `Overrides` and add cross-field validator test

**Files:**
- Modify: `src/ks_gen/config.py`
- Test: `tests/test_config_schema.py`

- [ ] **Step 2.1: Write failing test for `Overrides.unattended_updates` field**

Add to `tests/test_config_schema.py`:

```python
def test_overrides_has_unattended_updates_default():
    o = Overrides()
    assert o.unattended_updates.enable is True
    assert o.unattended_updates.nightly_security.enable is True


def test_reboot_window_without_updates_rejected():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "overrides": {
            "unattended_updates": {
                "nightly_security": {"enable": False},
                "monthly_full": {"enable": False},
                "reboot_window": {"enable": True},
            }
        },
    }
    with pytest.raises(ValidationError, match="reboot_window requires"):
        HostConfig.model_validate(payload)


def test_reboot_window_with_only_monthly_allowed():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "overrides": {
            "unattended_updates": {
                "nightly_security": {"enable": False},
                "monthly_full": {"enable": True},
                "reboot_window": {"enable": True},
            }
        },
    }
    cfg = HostConfig.model_validate(payload)
    assert cfg.overrides.unattended_updates.reboot_window.enable is True
```

- [ ] **Step 2.2: Run failing tests**

```bash
pytest tests/test_config_schema.py::test_overrides_has_unattended_updates_default tests/test_config_schema.py::test_reboot_window_without_updates_rejected -v
```

Expected: FAIL — `Overrides` has no `unattended_updates` attr.

- [ ] **Step 2.3: Wire into `Overrides`**

In `src/ks_gen/config.py`, modify the `Overrides` class. Find:

```python
class Overrides(StrictModel):
    fips_mode: bool = False
    faillock: FaillockCfg = Field(default_factory=FaillockCfg)
    auditd: AuditdActionsCfg = Field(default_factory=AuditdActionsCfg)
    ssh_keep_open: SshKeepOpenCfg = Field(default_factory=SshKeepOpenCfg)
    usbguard: UsbguardCfg = Field(default_factory=UsbguardCfg)
    kernel_module_blacklist: KernelModuleBlacklistCfg = Field(
        default_factory=KernelModuleBlacklistCfg
    )
    package_purge: PackagePurgeCfg = Field(default_factory=PackagePurgeCfg)
    dod_root_ca: DodRootCaCfg = Field(default_factory=DodRootCaCfg)
```

Add one line at the end:

```python
class Overrides(StrictModel):
    fips_mode: bool = False
    faillock: FaillockCfg = Field(default_factory=FaillockCfg)
    auditd: AuditdActionsCfg = Field(default_factory=AuditdActionsCfg)
    ssh_keep_open: SshKeepOpenCfg = Field(default_factory=SshKeepOpenCfg)
    usbguard: UsbguardCfg = Field(default_factory=UsbguardCfg)
    kernel_module_blacklist: KernelModuleBlacklistCfg = Field(
        default_factory=KernelModuleBlacklistCfg
    )
    package_purge: PackagePurgeCfg = Field(default_factory=PackagePurgeCfg)
    dod_root_ca: DodRootCaCfg = Field(default_factory=DodRootCaCfg)
    unattended_updates: UnattendedUpdatesCfg = Field(default_factory=UnattendedUpdatesCfg)
```

- [ ] **Step 2.4: Run tests to confirm pass**

```bash
pytest tests/test_config_schema.py -v -k "unattended or reboot_window"
```

Expected: all unattended-related tests PASS.

- [ ] **Step 2.5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): wire unattended_updates into Overrides with cross-field validator"
```

---

## Task 3: Add `dnf-automatic` and `dnf-utils` to `Packages.required` defaults

**Files:**
- Modify: `src/ks_gen/config.py`
- Test: `tests/test_config_schema.py`

- [ ] **Step 3.1: Write failing test**

Add to `tests/test_config_schema.py`:

```python
def test_packages_include_dnf_automatic_tooling():
    p = Packages()
    assert "dnf-automatic" in p.required
    assert "dnf-utils" in p.required
```

- [ ] **Step 3.2: Run failing test**

```bash
pytest tests/test_config_schema.py::test_packages_include_dnf_automatic_tooling -v
```

Expected: FAIL — `dnf-automatic` not in defaults.

- [ ] **Step 3.3: Extend `Packages.required` defaults**

In `src/ks_gen/config.py`, find:

```python
class Packages(StrictModel):
    base_groups: list[str] = Field(default_factory=lambda: ["@^minimal-environment", "@standard"])
    required: list[str] = Field(
        default_factory=lambda: [
            "scap-security-guide",
            "openscap-scanner",
            "aide",
            "audit",
            "rsyslog",
            "chrony",
            "firewalld",
            "sudo",
            "policycoreutils-python-utils",
        ]
    )
```

Append two entries:

```python
class Packages(StrictModel):
    base_groups: list[str] = Field(default_factory=lambda: ["@^minimal-environment", "@standard"])
    required: list[str] = Field(
        default_factory=lambda: [
            "scap-security-guide",
            "openscap-scanner",
            "aide",
            "audit",
            "rsyslog",
            "chrony",
            "firewalld",
            "sudo",
            "policycoreutils-python-utils",
            "dnf-automatic",
            "dnf-utils",
        ]
    )
```

- [ ] **Step 3.4: Run test to confirm pass**

```bash
pytest tests/test_config_schema.py::test_packages_include_dnf_automatic_tooling -v
```

Expected: PASS.

- [ ] **Step 3.5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(config): add dnf-automatic and dnf-utils to required packages"
```

---

## Task 4: Create `unattended_updates` rule module — scaffold + non-emitting methods

**Files:**
- Create: `src/ks_gen/rules/unattended_updates.py`
- Create: `tests/rules/test_unattended_updates.py`

- [ ] **Step 4.1: Write failing tests for the contract**

Create `tests/rules/test_unattended_updates.py`:

```python
from ks_gen.config import Overrides, UnattendedUpdatesCfg
from ks_gen.rules.unattended_updates import RULE


def test_rule_metadata():
    assert RULE.id == "unattended_updates"
    assert RULE.depends_on == []
    assert RULE.stig_rules_affected == []
    assert "dnf-automatic" in RULE.summary or "unattended" in RULE.summary.lower()


def test_applies_when_enabled(minimal_cfg):
    assert RULE.applies(minimal_cfg) is True


def test_does_not_apply_when_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={"overrides": Overrides(unattended_updates=UnattendedUpdatesCfg(enable=False))}
    )
    assert RULE.applies(cfg) is False


def test_emit_tailoring_is_empty(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []


def test_exception_entry_is_none(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is None
```

- [ ] **Step 4.2: Run failing tests**

```bash
pytest tests/rules/test_unattended_updates.py -v
```

Expected: FAIL — `ModuleNotFoundError: ks_gen.rules.unattended_updates`.

- [ ] **Step 4.3: Create the rule module (scaffold only — `emit_post` returns empty)**

Create `src/ks_gen/rules/unattended_updates.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = "unattended_updates"
    summary: str = (
        "Configure dnf-automatic for nightly security + monthly full updates, "
        "with reboot inside a maintenance window."
    )
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.unattended_updates.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
```

- [ ] **Step 4.4: Run tests to confirm pass**

```bash
pytest tests/rules/test_unattended_updates.py -v
```

Expected: 5 PASSED.

- [ ] **Step 4.5: Commit**

```bash
git add src/ks_gen/rules/unattended_updates.py tests/rules/test_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules): scaffold unattended_updates rule"
```

---

## Task 5: Implement `emit_post` — nightly security branch

**Files:**
- Modify: `src/ks_gen/rules/unattended_updates.py`
- Modify: `tests/rules/test_unattended_updates.py`

- [ ] **Step 5.1: Write failing tests for nightly security emission**

Append to `tests/rules/test_unattended_updates.py`:

```python
from ks_gen.config import NightlySecurityCfg


def test_nightly_security_emits_dnf_automatic_conf(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "cat > /etc/dnf/automatic.conf" in out
    assert "upgrade_type = security" in out
    assert "apply_updates = yes" in out
    assert "reboot = never" in out


def test_nightly_security_emits_timer_dropin(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/systemd/system/dnf-automatic.timer.d/ks-gen.conf" in out
    # critical: empty OnCalendar= to reset list before adding the override
    assert "OnCalendar=\nOnCalendar=*-*-* 02:00:00" in out
    assert "systemctl enable dnf-automatic.timer" in out


def test_nightly_security_honors_custom_on_calendar(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    nightly_security=NightlySecurityCfg(on_calendar="Mon..Fri 23:30")
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "OnCalendar=Mon..Fri 23:30" in out


def test_nightly_security_omitted_when_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    nightly_security=NightlySecurityCfg(enable=False),
                    reboot_window=RebootWindowCfg(enable=False),
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "/etc/dnf/automatic.conf" not in out
    assert "dnf-automatic.timer.d" not in out
```

You also need to import `RebootWindowCfg` at the top of the test file; update the imports block:

```python
from ks_gen.config import (
    NightlySecurityCfg,
    Overrides,
    RebootWindowCfg,
    UnattendedUpdatesCfg,
)
```

- [ ] **Step 5.2: Run failing tests**

```bash
pytest tests/rules/test_unattended_updates.py -v -k "nightly"
```

Expected: FAIL — `emit_post` returns empty string.

- [ ] **Step 5.3: Implement nightly security branch**

In `src/ks_gen/rules/unattended_updates.py`, replace the placeholder `emit_post` and add a helper. Replace the entire `_Rule` class body's `emit_post` with:

```python
    def emit_post(self, cfg: HostConfig) -> str:
        u = cfg.overrides.unattended_updates
        parts: list[str] = []
        if u.nightly_security.enable:
            parts.append(_nightly_security_block(u.nightly_security.on_calendar))
        return "\n".join(parts)
```

Then add this module-level function below the `_Rule` class (above `RULE = ...`):

```python
def _nightly_security_block(on_calendar: str) -> str:
    return f"""\
# unattended_updates: nightly security via stock dnf-automatic.timer
cat > /etc/dnf/automatic.conf <<'__KS_GEN_EOF__'
[commands]
upgrade_type = security
apply_updates = yes
reboot = never
network_online_timeout = 60
[emitters]
emit_via = motd
[base]
debuglevel = 1
__KS_GEN_EOF__
chmod 644 /etc/dnf/automatic.conf

mkdir -p /etc/systemd/system/dnf-automatic.timer.d
cat > /etc/systemd/system/dnf-automatic.timer.d/ks-gen.conf <<'__KS_GEN_EOF__'
[Timer]
OnCalendar=
OnCalendar={on_calendar}
RandomizedDelaySec=0
__KS_GEN_EOF__

systemctl daemon-reload
systemctl enable dnf-automatic.timer
"""
```

- [ ] **Step 5.4: Run tests to confirm pass**

```bash
pytest tests/rules/test_unattended_updates.py -v -k "nightly"
```

Expected: 4 PASSED.

- [ ] **Step 5.5: Commit**

```bash
git add src/ks_gen/rules/unattended_updates.py tests/rules/test_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules): emit nightly security dnf-automatic config + timer override"
```

---

## Task 6: Implement `emit_post` — monthly full branch

**Files:**
- Modify: `src/ks_gen/rules/unattended_updates.py`
- Modify: `tests/rules/test_unattended_updates.py`

- [ ] **Step 6.1: Write failing tests for monthly full emission**

Append to `tests/rules/test_unattended_updates.py`:

```python
from ks_gen.config import MonthlyFullCfg


def test_monthly_full_emits_separate_config_and_timer(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "cat > /etc/dnf/automatic-full.conf" in out
    assert "upgrade_type = default" in out
    assert "ks-gen-dnf-automatic-full.service" in out
    assert "ks-gen-dnf-automatic-full.timer" in out
    assert "OnCalendar=Sun *-*-1..7 02:30:00" in out
    assert "Persistent=true" in out
    assert "systemctl enable ks-gen-dnf-automatic-full.timer" in out


def test_monthly_full_honors_custom_on_calendar(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    monthly_full=MonthlyFullCfg(on_calendar="*-*-15 04:00:00")
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "OnCalendar=*-*-15 04:00:00" in out


def test_monthly_full_omitted_when_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    monthly_full=MonthlyFullCfg(enable=False)
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "/etc/dnf/automatic-full.conf" not in out
    assert "ks-gen-dnf-automatic-full" not in out
```

Update the imports at top of the test file to include `MonthlyFullCfg`:

```python
from ks_gen.config import (
    MonthlyFullCfg,
    NightlySecurityCfg,
    Overrides,
    RebootWindowCfg,
    UnattendedUpdatesCfg,
)
```

- [ ] **Step 6.2: Run failing tests**

```bash
pytest tests/rules/test_unattended_updates.py -v -k "monthly"
```

Expected: FAIL — monthly block not emitted.

- [ ] **Step 6.3: Implement monthly full branch**

In `src/ks_gen/rules/unattended_updates.py`, update `_Rule.emit_post` to add the monthly branch:

```python
    def emit_post(self, cfg: HostConfig) -> str:
        u = cfg.overrides.unattended_updates
        parts: list[str] = []
        if u.nightly_security.enable:
            parts.append(_nightly_security_block(u.nightly_security.on_calendar))
        if u.monthly_full.enable:
            parts.append(_monthly_full_block(u.monthly_full.on_calendar))
        return "\n".join(parts)
```

Add `_monthly_full_block` as a module-level function below `_nightly_security_block`:

```python
def _monthly_full_block(on_calendar: str) -> str:
    return f"""\
# unattended_updates: monthly full update via custom dnf-automatic timer
cat > /etc/dnf/automatic-full.conf <<'__KS_GEN_EOF__'
[commands]
upgrade_type = default
apply_updates = yes
reboot = never
network_online_timeout = 60
[emitters]
emit_via = motd
[base]
debuglevel = 1
__KS_GEN_EOF__
chmod 644 /etc/dnf/automatic-full.conf

cat > /etc/systemd/system/ks-gen-dnf-automatic-full.service <<'__KS_GEN_EOF__'
[Unit]
Description=ks-gen monthly full dnf-automatic run
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/dnf-automatic /etc/dnf/automatic-full.conf
__KS_GEN_EOF__

cat > /etc/systemd/system/ks-gen-dnf-automatic-full.timer <<'__KS_GEN_EOF__'
[Unit]
Description=ks-gen monthly full dnf-automatic schedule
[Timer]
OnCalendar={on_calendar}
Persistent=true
[Install]
WantedBy=timers.target
__KS_GEN_EOF__

systemctl daemon-reload
systemctl enable ks-gen-dnf-automatic-full.timer
"""
```

- [ ] **Step 6.4: Run tests to confirm pass**

```bash
pytest tests/rules/test_unattended_updates.py -v -k "monthly"
```

Expected: 3 PASSED.

- [ ] **Step 6.5: Commit**

```bash
git add src/ks_gen/rules/unattended_updates.py tests/rules/test_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules): emit monthly full dnf-automatic timer pair"
```

---

## Task 7: Implement `emit_post` — reboot window branch

**Files:**
- Modify: `src/ks_gen/rules/unattended_updates.py`
- Modify: `tests/rules/test_unattended_updates.py`

- [ ] **Step 7.1: Write failing tests for reboot window emission**

Append to `tests/rules/test_unattended_updates.py`:

```python
def test_reboot_window_emits_script_service_and_timer(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/usr/local/sbin/ks-gen-reboot-if-needed" in out
    assert "needs-restarting -r" in out
    assert "systemctl reboot" in out
    assert "ks-gen-reboot-if-needed.service" in out
    assert "ks-gen-reboot-if-needed.timer" in out
    assert "OnCalendar=Sun *-*-* 03:00:00" in out
    assert "systemctl enable ks-gen-reboot-if-needed.timer" in out


def test_reboot_window_honors_custom_on_calendar(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    reboot_window=RebootWindowCfg(on_calendar="*-*-* 06:00:00")
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "OnCalendar=*-*-* 06:00:00" in out


def test_reboot_window_omitted_when_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    reboot_window=RebootWindowCfg(enable=False)
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "ks-gen-reboot-if-needed" not in out


def test_reboot_script_fails_loud_on_missing_needs_restarting(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    # The script must log at error level and exit non-zero rather than reboot.
    assert "needs-restarting missing" in out
    assert "exit 1" in out
```

- [ ] **Step 7.2: Run failing tests**

```bash
pytest tests/rules/test_unattended_updates.py -v -k "reboot"
```

Expected: FAIL — reboot block not emitted.

- [ ] **Step 7.3: Implement reboot window branch**

In `src/ks_gen/rules/unattended_updates.py`, update `_Rule.emit_post` to add the reboot branch:

```python
    def emit_post(self, cfg: HostConfig) -> str:
        u = cfg.overrides.unattended_updates
        parts: list[str] = []
        if u.nightly_security.enable:
            parts.append(_nightly_security_block(u.nightly_security.on_calendar))
        if u.monthly_full.enable:
            parts.append(_monthly_full_block(u.monthly_full.on_calendar))
        if u.reboot_window.enable:
            parts.append(_reboot_window_block(u.reboot_window.on_calendar))
        return "\n".join(parts)
```

Add `_reboot_window_block` as a module-level function below `_monthly_full_block`:

```python
def _reboot_window_block(on_calendar: str) -> str:
    return f"""\
# unattended_updates: reboot inside maintenance window if needs-restarting -r says so
cat > /usr/local/sbin/ks-gen-reboot-if-needed <<'__KS_GEN_EOF__'
#!/bin/bash
set -euo pipefail
if ! command -v needs-restarting >/dev/null 2>&1; then
  logger -t ks-gen -p user.err "needs-restarting missing; cannot evaluate reboot"
  exit 1
fi
if needs-restarting -r >/dev/null 2>&1; then
  logger -t ks-gen "no reboot needed at $(date -Is)"
  exit 0
fi
logger -t ks-gen "reboot needed, rebooting at $(date -Is)"
systemctl reboot
__KS_GEN_EOF__
chmod 755 /usr/local/sbin/ks-gen-reboot-if-needed

cat > /etc/systemd/system/ks-gen-reboot-if-needed.service <<'__KS_GEN_EOF__'
[Unit]
Description=ks-gen reboot if pending kernel/glibc/etc.
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ks-gen-reboot-if-needed
__KS_GEN_EOF__

cat > /etc/systemd/system/ks-gen-reboot-if-needed.timer <<'__KS_GEN_EOF__'
[Unit]
Description=ks-gen reboot-if-needed schedule
[Timer]
OnCalendar={on_calendar}
Persistent=true
[Install]
WantedBy=timers.target
__KS_GEN_EOF__

systemctl daemon-reload
systemctl enable ks-gen-reboot-if-needed.timer
"""
```

Note: The `$(date -Is)` inside the heredoc must be inside a *single-quoted* heredoc delimiter (`'__KS_GEN_EOF__'`) so the kickstart's outer shell does not expand it — only the installed `/usr/local/sbin/ks-gen-reboot-if-needed` script should evaluate it at runtime. The single quotes on the delimiter are already in place.

- [ ] **Step 7.4: Run tests to confirm pass**

```bash
pytest tests/rules/test_unattended_updates.py -v
```

Expected: ALL tests in the file PASS.

- [ ] **Step 7.5: Run the full rule test suite to confirm no other rule regressed**

```bash
pytest tests/rules/ -v
```

Expected: all PASS.

- [ ] **Step 7.6: Commit**

```bash
git add src/ks_gen/rules/unattended_updates.py tests/rules/test_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules): emit reboot-if-needed script + maintenance-window timer"
```

---

## Task 8: Regenerate existing golden snapshots

The new defaults pull in the rule's `%post` fragment and the two new packages, so all four existing snapshots will diff. Regenerate them.

**Files:**
- Regenerate: `tests/golden/__snapshots__/test_minimal_dhcp.ambr`
- Regenerate: `tests/golden/__snapshots__/test_stig_strict.ambr`
- Regenerate: `tests/golden/__snapshots__/test_modern_crypto.ambr`
- Regenerate: `tests/golden/__snapshots__/test_bare_metal_usbguard.ambr`

- [ ] **Step 8.1: Run golden tests; observe them fail**

```bash
pytest tests/golden/ -v
```

Expected: 4 FAILED with snapshot diff (each contains the new `unattended_updates` `%post` block and the two new packages).

- [ ] **Step 8.2: Regenerate snapshots**

```bash
pytest tests/golden/ --snapshot-update
```

Expected: 4 snapshots regenerated.

- [ ] **Step 8.3: Inspect the diff before committing**

```bash
git diff tests/golden/__snapshots__/
```

Sanity-check the diff:
- New `# ===== unattended_updates =====` block appears in each `ks.cfg` snapshot.
- The block contains `cat > /etc/dnf/automatic.conf`, the timer drop-in, the monthly service+timer, and the reboot script+timer.
- `dnf-automatic` and `dnf-utils` appear in the `%packages` section.
- `host.yaml` snapshot reflects the new `overrides.unattended_updates` block.
- `exceptions.md` snapshot is unchanged (the rule does not register an exception).

- [ ] **Step 8.4: Re-run golden tests to confirm they pass on the new snapshots**

```bash
pytest tests/golden/ -v
```

Expected: 4 PASSED.

- [ ] **Step 8.5: Commit**

```bash
git add tests/golden/__snapshots__/
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regenerate snapshots for unattended_updates rule"
```

---

## Task 9: Add `unattended-disabled` golden scenario

**Files:**
- Create: `tests/golden/unattended-disabled.host.yaml`
- Create: `tests/golden/test_unattended_disabled.py`
- Create: `tests/golden/__snapshots__/test_unattended_disabled.ambr` (auto-generated)

- [ ] **Step 9.1: Create the scenario fixture**

Create `tests/golden/unattended-disabled.host.yaml`:

```yaml
system:
  hostname: airgap01.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYunattendeddisabled test@laptop"
    sudo: nopasswd_yes
overrides:
  unattended_updates:
    enable: false
```

- [ ] **Step 9.2: Create the snapshot test driver**

Create `tests/golden/test_unattended_disabled.py`:

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


def test_unattended_disabled(snapshot):
    yaml_path = Path(__file__).parent / "unattended-disabled.host.yaml"
    cfg = load_host_config(yaml_path, sets=[])
    bundle = build_bundle(cfg)
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")
    assert _normalize(bundle.tailoring_xml) == snapshot(name="tailoring.xml")
    assert _normalize(bundle.exceptions_md) == snapshot(name="exceptions.md")
```

- [ ] **Step 9.3: Generate the snapshot**

```bash
pytest tests/golden/test_unattended_disabled.py --snapshot-update -v
```

Expected: new snapshot file written; test passes.

- [ ] **Step 9.4: Inspect the generated snapshot**

```bash
cat tests/golden/__snapshots__/test_unattended_disabled.ambr
```

Sanity-check:
- `ks.cfg` snapshot does NOT contain `# ===== unattended_updates =====` block (rule no-ops when `enable=false`).
- `dnf-automatic` and `dnf-utils` still appear in `%packages` (those are package-list defaults, independent of the rule's `applies()`).
- `exceptions.md` does not gain a new section.

- [ ] **Step 9.5: Re-run to confirm idempotent**

```bash
pytest tests/golden/test_unattended_disabled.py -v
```

Expected: PASS without `--snapshot-update`.

- [ ] **Step 9.6: Commit**

```bash
git add tests/golden/unattended-disabled.host.yaml tests/golden/test_unattended_disabled.py tests/golden/__snapshots__/test_unattended_disabled.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): unattended-disabled scenario snapshot"
```

---

## Task 10: Run full test suite

- [ ] **Step 10.1: Run the entire suite**

```bash
pytest -v
```

Expected: all PASS, no warnings. If any test outside the touched files fails, investigate — it likely means an assumption about `Overrides` defaults or `Packages.required` was hard-coded elsewhere.

- [ ] **Step 10.2: Run ruff and mypy**

```bash
ruff check src tests
mypy
```

Expected: both clean. If ruff complains about line length on the long heredoc strings, prefer to wrap the docstring or split the f-string rather than disable the rule.

- [ ] **Step 10.3: (No commit — verification step only.)**

---

## Task 11: Update MANUAL.md

**Files:**
- Modify: `MANUAL.md`

- [ ] **Step 11.1: Add the `unattended_updates` block to §4.11**

In `MANUAL.md`, find §4.11's YAML example (around line 413, the `overrides:` block). After the `dod_root_ca:` block, append:

```yaml
  unattended_updates:
    enable: true                              # master switch; false leaves STIG defaults
    nightly_security:
      enable: true
      on_calendar: "*-*-* 02:00:00"           # systemd OnCalendar; nightly 02:00 host-local
    monthly_full:
      enable: true
      on_calendar: "Sun *-*-1..7 02:30:00"    # first Sunday each month, 02:30 host-local
    reboot_window:
      enable: true
      on_calendar: "Sun *-*-* 03:00:00"       # weekly Sunday 03:00 host-local
```

Then immediately below the closing ` ``` ` of that YAML block (before "See §6 for what each rule does..."), insert this prose paragraph:

```markdown
**Fleet operators:** the maintenance-window defaults are *not* staggered.
A datacenter where every host runs the same `host.yaml` will see every
host reboot at Sunday 03:00 in unison. Set `reboot_window.on_calendar`
to different values per host (or per rack) to avoid a synchronous
fleet-wide reboot.

The rule preserves the STIG `timer_dnf-automatic_enabled` control — it
overrides the stock timer's `OnCalendar` via a systemd drop-in rather
than disabling and replacing the unit.
```

- [ ] **Step 11.2: Add the `unattended_updates` row to §6 rule reference table**

Find the rule reference table in §6 (around line 640, the row for `dod_root_ca`). After the `usbguard` row, add:

```markdown
| `unattended_updates` | Configures `dnf-automatic` for nightly security + monthly full updates and drops a `needs-restarting`-driven reboot timer that fires only inside `overrides.unattended_updates.reboot_window`. Stock `dnf-automatic.timer` is kept enabled with operator-supplied `OnCalendar` via drop-in. |
```

- [ ] **Step 11.3: Commit**

```bash
git add MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs(manual): document unattended_updates override block"
```

---

## Task 12: Update MINIMAL-TEST.md

**Files:**
- Modify: `MINIMAL-TEST.md`

- [ ] **Step 12.1: Locate the post-install verification section**

Read `MINIMAL-TEST.md` and find the section where the operator verifies first-boot state via SSH. (It typically lists `systemctl is-active sshd`, `oscap` log checks, etc.)

- [ ] **Step 12.2: Add timer verification step**

Append a new verification step in that section:

````markdown
**Verify unattended-update timers are scheduled:**

```bash
systemctl list-timers --all | grep -E 'dnf-automatic|reboot-if-needed'
```

Expected: three timer entries with future `NEXT` columns —
`dnf-automatic.timer`, `ks-gen-dnf-automatic-full.timer`, and
`ks-gen-reboot-if-needed.timer`. If `dnf-automatic.timer`'s schedule
shows `06:00` (the SSG default) rather than the YAML-configured
nightly `02:00`, the drop-in at
`/etc/systemd/system/dnf-automatic.timer.d/ks-gen.conf` wasn't picked
up — re-check the `%post` log at `/root/ks-post.log`.
````

- [ ] **Step 12.3: Commit**

```bash
git add MINIMAL-TEST.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs(test): verify three unattended-update timers post-install"
```

---

## Task 13: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 13.1: Add a `[Unreleased]` section at the top**

The current `CHANGELOG.md` opens with `## [0.1.0] — 2026-06-01`. Insert a new section above it:

```markdown
## [Unreleased]

### Added
- `unattended_updates` rule + `overrides.unattended_updates` config block.
  Configures `dnf-automatic` for nightly security updates and monthly full
  updates, plus a `needs-restarting`-driven reboot timer scoped to an
  operator-defined maintenance window. Defaults: nightly 02:00, monthly
  full first Sunday 02:30, reboot Sundays 03:00 — all host-local time and
  overridable per host. `dnf-automatic` and `dnf-utils` added to required
  package defaults.

```

(Keep the existing `## [0.1.0] — 2026-06-01` section unchanged below.)

- [ ] **Step 13.2: Commit**

```bash
git add CHANGELOG.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs(changelog): unattended_updates rule + config block"
```

---

## Task 14: Final verification

- [ ] **Step 14.1: Full test suite + linters**

```bash
pytest -v && ruff check src tests && mypy
```

Expected: all green.

- [ ] **Step 14.2: Smoke-render a default config and eyeball the `%post` block**

```bash
python -m ks_gen gen --config tests/golden/minimal-dhcp.host.yaml --out /tmp/ks-gen-smoke
cat /tmp/ks-gen-smoke/ks.cfg
```

Expected: the rendered `ks.cfg` contains a `# ===== unattended_updates =====` section with all three sub-blocks visible, plus `dnf-automatic` and `dnf-utils` in `%packages`. No Jinja syntax errors, no `__KS_GEN_EOF__` markers left dangling.

- [ ] **Step 14.3: Smoke-render the `unattended-disabled` scenario**

```bash
python -m ks_gen gen --config tests/golden/unattended-disabled.host.yaml --out /tmp/ks-gen-smoke-off
grep -c "unattended_updates" /tmp/ks-gen-smoke-off/ks.cfg
```

Expected: `0` (the rule no-ops, leaving no marker in the kickstart).

- [ ] **Step 14.4: Confirm rule appears in `ks-gen rules` output**

```bash
python -m ks_gen rules
```

Expected: `unattended_updates` listed alongside the other 12 rules, with its `summary` text.

- [ ] **Step 14.5: (No commit — verification only.)**

---

## Task 15: Open the pull request

- [ ] **Step 15.1: Push the branch**

The user has not specified a branch name; if working on a feature branch named `impl/v0.2.0-unattended-updates`, push it. Otherwise, ask the user before pushing.

```bash
git push -u origin HEAD
```

- [ ] **Step 15.2: Open the PR with the title and body below**

```bash
gh pr create --title "feat: unattended updates + maintenance-window reboots" --body "$(cat <<'EOF'
## Summary
- New `unattended_updates` rule + `overrides.unattended_updates` config block — nightly security updates, monthly full updates, reboots inside a maintenance window.
- Preserves the STIG `timer_dnf-automatic_enabled` control via a systemd drop-in; does not replace the stock unit.
- Adds `dnf-automatic` and `dnf-utils` to `Packages.required` defaults.

## Spec
- `docs/superpowers/specs/2026-06-02-unattended-updates-design.md`

## Test plan
- [ ] `pytest -v` green
- [ ] `ruff check src tests` clean
- [ ] `mypy` clean
- [ ] Hyper-V install (per `MINIMAL-TEST.md`) shows three timers in `systemctl list-timers`
- [ ] `dnf-automatic.timer` next-fire shows the YAML-configured time, not SSG default `06:00`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Return the PR URL.
