# Phase 3.6 — `unattended_updates` port to ubuntu2404 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the `unattended_updates` rule to ubuntu2404 so the generated autoinstall configures Ubuntu's stock unattended-upgrades plumbing for nightly security updates, layers a custom timer for monthly `apt-get dist-upgrade`, and adds a reboot-window timer that consults `/var/run/reboot-required`.

**Architecture:** One new rule module + one new test file. `emit_post` composes three independent blocks each gated on its own `enable` flag: nightly security via drop-ins on `apt-daily.timer` + `apt-daily-upgrade.timer` plus `/etc/apt/apt.conf.d/{20auto-upgrades,52ks-gen-unattended}`; monthly full via custom `ks-gen-apt-full-upgrade.{service,timer}` running `apt-get dist-upgrade`; reboot via custom `ks-gen-reboot-if-needed.{service,timer}` keying off `/var/run/reboot-required`. emit_post-only + defer-tailoring/exception pattern matches phases 3.1–3.5.

**Tech Stack:** Python 3.11+, pydantic v2, jinja2, syrupy snapshots, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-6-unattended-updates-design.md`

**Branch:** `phase-3.6-unattended-updates` (already created off main at `35c1470`; spec already committed at `c93034c`).

---

## Reference patterns

- **alma9 sibling:** `src/ks_gen/rules/alma9/unattended_updates.py` — semantic source for the three-block decomposition (nightly / monthly / reboot) and the `_emit_*_block(on_calendar)` helper signature.
- **Closest ubuntu2404 sibling:** `src/ks_gen/rules/ubuntu2404/faillock_safety.py` (phase 3.5) — multi-block `_emit_X` decomposition + heredoc style + first ubuntu2404 rule with conditional `applies()`.
- **Test sibling:** `tests/rules/test_ubuntu2404_faillock_safety.py` — module-level `from ... import RULE` at top, local `from ks_gen.config import ...` inside per-test override functions.

The `UnattendedUpdatesCfg` schema is in `src/ks_gen/config.py:629-647` with three sub-models in the same file:

```python
# src/ks_gen/config.py:614-633
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
```

**Validator gotcha** (`_reboot_window_needs_an_update_timer`, lines 635-647): if `enable and reboot_window.enable and not (nightly_security.enable or monthly_full.enable)`, pydantic raises. When constructing a test cfg with both update timers disabled, also disable `reboot_window` (or set parent `enable=False`).

Override pattern in tests:

```python
from ks_gen.config import (
    UnattendedUpdatesCfg, NightlySecurityCfg, MonthlyFullCfg,
    RebootWindowCfg, Overrides,
)

cfg = ubuntu_cfg_factory().model_copy(
    update={"overrides": Overrides(
        unattended_updates=UnattendedUpdatesCfg(
            nightly_security=NightlySecurityCfg(enable=False),
        )
    )}
)
```

---

## Task 1: Rule skeleton + first failing test

Create the rule file with all three component emitters in one TDD shot. The `_*_block` helpers are small enough that incrementally building them out wouldn't add review value. Add one failing path test (on the nightly `20auto-upgrades` path) to drive the wiring.

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/unattended_updates.py`
- Create: `tests/rules/test_ubuntu2404_unattended_updates.py`

- [ ] **Step 1: Write the failing test**

Create `tests/rules/test_ubuntu2404_unattended_updates.py`:

```python
from ks_gen.rules.ubuntu2404.unattended_updates import RULE


def test_nightly_writes_20auto_upgrades_path_and_content(ubuntu_cfg_factory):
    # /etc/apt/apt.conf.d/20auto-upgrades is the canonical Debian/Ubuntu
    # file that flips periodic apt-daily logic from "off" to "on" — both
    # keys must be "1" to actually enable unattended-upgrades.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/apt/apt.conf.d/20auto-upgrades" in out
    assert 'APT::Periodic::Update-Package-Lists "1";' in out
    assert 'APT::Periodic::Unattended-Upgrade "1";' in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rules/test_ubuntu2404_unattended_updates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.unattended_updates'`

- [ ] **Step 3: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/unattended_updates.py`:

```python
"""ubuntu2404 unattended_updates rule.

Configures Ubuntu's stock unattended-upgrades plumbing for nightly
security updates, layers a custom ks-gen-apt-full-upgrade timer for
monthly dist-upgrade, and adds a reboot-window timer that consults
/var/run/reboot-required (Ubuntu's canonical needs-reboot signal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import unattended_updates as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.unattended_updates.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml unattended-updates rule survey lands in the audit-story PR.
        return []

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

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        u = cfg.overrides.unattended_updates
        if u.nightly_security.enable or u.monthly_full.enable:
            return ["unattended-upgrades"]
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


def _nightly_security_block(on_calendar: str) -> str:
    return f"""\
# unattended_updates: nightly security via stock unattended-upgrades timers
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'__KS_GEN_EOF__'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
__KS_GEN_EOF__
chmod 644 /etc/apt/apt.conf.d/20auto-upgrades

cat > /etc/apt/apt.conf.d/52ks-gen-unattended <<'__KS_GEN_EOF__'
Unattended-Upgrade::MailReport "never";
Unattended-Upgrade::Automatic-Reboot "false";
__KS_GEN_EOF__
chmod 644 /etc/apt/apt.conf.d/52ks-gen-unattended

mkdir -p /etc/systemd/system/apt-daily.timer.d
cat > /etc/systemd/system/apt-daily.timer.d/ks-gen.conf <<'__KS_GEN_EOF__'
[Timer]
OnCalendar=
OnCalendar={on_calendar}
RandomizedDelaySec=0
__KS_GEN_EOF__

mkdir -p /etc/systemd/system/apt-daily-upgrade.timer.d
cat > /etc/systemd/system/apt-daily-upgrade.timer.d/ks-gen.conf <<'__KS_GEN_EOF__'
[Timer]
OnCalendar=
OnCalendar={on_calendar}
RandomizedDelaySec=0
__KS_GEN_EOF__

systemctl daemon-reload
systemctl enable apt-daily.timer apt-daily-upgrade.timer
"""


def _monthly_full_block(on_calendar: str) -> str:
    return f"""\
# unattended_updates: monthly full update via custom ks-gen timer
cat > /usr/local/sbin/ks-gen-apt-full-upgrade <<'__KS_GEN_EOF__'
#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y \\
  -o Dpkg::Options::='--force-confdef' \\
  -o Dpkg::Options::='--force-confold' \\
  dist-upgrade
__KS_GEN_EOF__
chmod 755 /usr/local/sbin/ks-gen-apt-full-upgrade

cat > /etc/systemd/system/ks-gen-apt-full-upgrade.service <<'__KS_GEN_EOF__'
[Unit]
Description=ks-gen monthly full apt dist-upgrade run
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ks-gen-apt-full-upgrade
__KS_GEN_EOF__

cat > /etc/systemd/system/ks-gen-apt-full-upgrade.timer <<'__KS_GEN_EOF__'
[Unit]
Description=ks-gen monthly full apt dist-upgrade schedule
[Timer]
OnCalendar={on_calendar}
Persistent=true
[Install]
WantedBy=timers.target
__KS_GEN_EOF__

systemctl daemon-reload
systemctl enable ks-gen-apt-full-upgrade.timer
"""


def _reboot_window_block(on_calendar: str) -> str:
    return f"""\
# unattended_updates: reboot inside maintenance window if /var/run/reboot-required exists
cat > /usr/local/sbin/ks-gen-reboot-if-needed <<'__KS_GEN_EOF__'
#!/bin/bash
set -euo pipefail
if [ -f /var/run/reboot-required ]; then
  logger -t ks-gen "reboot needed (/var/run/reboot-required present), rebooting at $(date -Is)"
  systemctl reboot
else
  logger -t ks-gen "no reboot needed at $(date -Is)"
fi
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


RULE: Rule = cast(Rule, _Rule())
```

No edit to `src/ks_gen/rules/ubuntu2404/__init__.py` — registry uses `pkgutil.iter_modules` auto-discovery.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/rules/test_ubuntu2404_unattended_updates.py -v`
Expected: PASS — `test_nightly_writes_20auto_upgrades_path_and_content` is green.

- [ ] **Step 5: Commit**

```bash
git add tests/rules/test_ubuntu2404_unattended_updates.py src/ks_gen/rules/ubuntu2404/unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add unattended_updates rule skeleton (#81 phase 3.6)

Three-block port mirroring alma9: nightly security drop-ins on
apt-daily.timer + apt-daily-upgrade.timer plus 20auto-upgrades enable
and 52ks-gen-unattended policy overlay; monthly full via custom
ks-gen-apt-full-upgrade timer running apt-get dist-upgrade with
--force-confdef/--force-confold; reboot window via custom
ks-gen-reboot-if-needed timer keying off /var/run/reboot-required.

emit_tailoring + exception_entry deferred to audit-story PR.
emit_packages returns [unattended-upgrades] when either of the two
update timers is enabled.

First test pins the 20auto-upgrades canonical apt-daily enable file."
```

NO `Co-Authored-By` trailer in the commit message.

---

## Task 2: `applies` semantics tests

Two tests for the `applies` short-circuit: default cfg → True, parent `enable=False` → False.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_unattended_updates.py`

- [ ] **Step 1: Append two applies tests**

```python
def test_applies_when_enabled(ubuntu_cfg_factory):
    # Default cfg.overrides.unattended_updates.enable is True.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_disabled(ubuntu_cfg_factory):
    # When the operator sets the parent enable=False, the rule is
    # excluded from late-commands entirely.
    from ks_gen.config import Overrides, UnattendedUpdatesCfg

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(enable=False),
        )}
    )
    assert RULE.applies(cfg) is False
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_unattended_updates.py -v`
Expected: 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert unattended_updates applies honors parent enable flag"
```

---

## Task 3: Block presence/absence gating tests

Six tests proving each of the three blocks is gated on its own `enable` flag. Each block has both a "present by default" test and an "omitted when disabled" test.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_unattended_updates.py`

- [ ] **Step 1: Append six gating tests**

```python
def test_post_includes_nightly_block_by_default(ubuntu_cfg_factory):
    # The "nightly security via stock unattended-upgrades timers" header
    # is a stable marker for the nightly block.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "nightly security via stock unattended-upgrades timers" in out


def test_post_includes_monthly_block_by_default(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "monthly full update via custom ks-gen timer" in out


def test_post_includes_reboot_block_by_default(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "reboot inside maintenance window if /var/run/reboot-required exists" in out


def test_post_omits_nightly_block_when_disabled(ubuntu_cfg_factory):
    from ks_gen.config import (
        MonthlyFullCfg,
        NightlySecurityCfg,
        Overrides,
        RebootWindowCfg,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(
                nightly_security=NightlySecurityCfg(enable=False),
                monthly_full=MonthlyFullCfg(),
                reboot_window=RebootWindowCfg(),
            ),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "nightly security via stock unattended-upgrades timers" not in out
    # Monthly + reboot still present.
    assert "monthly full update via custom ks-gen timer" in out
    assert "reboot inside maintenance window" in out


def test_post_omits_monthly_block_when_disabled(ubuntu_cfg_factory):
    from ks_gen.config import (
        MonthlyFullCfg,
        NightlySecurityCfg,
        Overrides,
        RebootWindowCfg,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(
                nightly_security=NightlySecurityCfg(),
                monthly_full=MonthlyFullCfg(enable=False),
                reboot_window=RebootWindowCfg(),
            ),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "monthly full update via custom ks-gen timer" not in out
    # Nightly + reboot still present.
    assert "nightly security via stock unattended-upgrades timers" in out
    assert "reboot inside maintenance window" in out


def test_post_omits_reboot_block_when_disabled(ubuntu_cfg_factory):
    from ks_gen.config import (
        MonthlyFullCfg,
        NightlySecurityCfg,
        Overrides,
        RebootWindowCfg,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(
                nightly_security=NightlySecurityCfg(),
                monthly_full=MonthlyFullCfg(),
                reboot_window=RebootWindowCfg(enable=False),
            ),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "reboot inside maintenance window" not in out
    # Nightly + monthly still present.
    assert "nightly security via stock unattended-upgrades timers" in out
    assert "monthly full update via custom ks-gen timer" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_unattended_updates.py -v`
Expected: 9 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert unattended_updates block gating per sub-enable flag"
```

---

## Task 4: Nightly block shape tests

Five tests for the nightly block: 52ks-gen-unattended policy file, drop-in on apt-daily.timer, drop-in on apt-daily-upgrade.timer, both timers enabled, and on_calendar substitution. (The seed test in Task 1 covered the 20auto-upgrades file.)

**Files:**
- Modify: `tests/rules/test_ubuntu2404_unattended_updates.py`

- [ ] **Step 1: Append five nightly-shape tests**

```python
def test_nightly_writes_52ks_gen_unattended_with_mail_and_reboot_off(ubuntu_cfg_factory):
    # 52ks-gen-unattended is layered over the stock 50unattended-upgrades
    # to enforce mail-off (no SMTP fanout) and reboot-off (only our
    # reboot_window block reboots). Numeric prefix 52 sorts after 50 so
    # our values win without overwriting Ubuntu's stock allowed-origins
    # list.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/apt/apt.conf.d/52ks-gen-unattended" in out
    assert 'Unattended-Upgrade::MailReport "never";' in out
    assert 'Unattended-Upgrade::Automatic-Reboot "false";' in out


def test_nightly_drops_in_apt_daily_timer_with_oncalendar(ubuntu_cfg_factory):
    # Drop-in pattern: clear OnCalendar= then set it to our value, plus
    # RandomizedDelaySec=0 to neutralize the default ~12h spread.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/systemd/system/apt-daily.timer.d/ks-gen.conf" in out
    # Default nightly_security.on_calendar = "*-*-* 02:00:00".
    assert "OnCalendar=\nOnCalendar=*-*-* 02:00:00" in out
    assert "RandomizedDelaySec=0" in out


def test_nightly_drops_in_apt_daily_upgrade_timer_with_oncalendar(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/systemd/system/apt-daily-upgrade.timer.d/ks-gen.conf" in out


def test_nightly_enables_both_timers(ubuntu_cfg_factory):
    # daemon-reload + enable both timers — apply waits for fetch via
    # the stock After=apt-daily.service on apt-daily-upgrade.service.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "systemctl daemon-reload" in out
    assert "systemctl enable apt-daily.timer apt-daily-upgrade.timer" in out


def test_nightly_reflects_on_calendar_override(ubuntu_cfg_factory):
    from ks_gen.config import (
        NightlySecurityCfg,
        Overrides,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(
                nightly_security=NightlySecurityCfg(on_calendar="*-*-* 04:00:00"),
            ),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "OnCalendar=\nOnCalendar=*-*-* 04:00:00" in out
    # The default time must NOT appear anywhere.
    assert "OnCalendar=*-*-* 02:00:00" not in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_unattended_updates.py -v`
Expected: 14 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert unattended_updates nightly block shape"
```

---

## Task 5: Monthly block shape tests

Four tests for the monthly block: the wrapper script, dist-upgrade with both Dpkg confdef/confold flags, on_calendar substitution on the timer, and the enable line.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_unattended_updates.py`

- [ ] **Step 1: Append four monthly-shape tests**

```python
def test_monthly_writes_ks_gen_apt_full_upgrade_script(ubuntu_cfg_factory):
    # Wrapper script at /usr/local/sbin executed by the timer's service.
    # chmod 755 makes it executable.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/usr/local/sbin/ks-gen-apt-full-upgrade" in out
    assert "chmod 755 /usr/local/sbin/ks-gen-apt-full-upgrade" in out
    # Shebang + strict bash + non-interactive frontend so dpkg never prompts.
    assert "#!/bin/bash" in out
    assert "set -euo pipefail" in out
    assert "export DEBIAN_FRONTEND=noninteractive" in out


def test_monthly_script_uses_dist_upgrade_with_dpkg_confdef_and_confold(ubuntu_cfg_factory):
    # dist-upgrade (not plain upgrade) for STIG full-coverage parity
    # with alma9's dnf-automatic upgrade_type=default. The pair of
    # Dpkg::Options preserves admin's edits on conffile conflicts so
    # the unit never blocks on stdin.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "apt-get update" in out
    assert "dist-upgrade" in out
    assert "Dpkg::Options::='--force-confdef'" in out
    assert "Dpkg::Options::='--force-confold'" in out


def test_monthly_timer_oncalendar_reflects_cfg(ubuntu_cfg_factory):
    from ks_gen.config import (
        MonthlyFullCfg,
        Overrides,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(
                monthly_full=MonthlyFullCfg(on_calendar="Sun *-*-1..7 05:00:00"),
            ),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "/etc/systemd/system/ks-gen-apt-full-upgrade.timer" in out
    assert "OnCalendar=Sun *-*-1..7 05:00:00" in out
    # Default monthly OnCalendar must NOT appear.
    assert "OnCalendar=Sun *-*-1..7 02:30:00" not in out


def test_monthly_enables_full_upgrade_timer(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "systemctl enable ks-gen-apt-full-upgrade.timer" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_unattended_updates.py -v`
Expected: 18 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert unattended_updates monthly block shape"
```

---

## Task 6: Reboot block shape tests

Two tests for the reboot block: the script checks `/var/run/reboot-required`, and the timer's OnCalendar reflects cfg.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_unattended_updates.py`

- [ ] **Step 1: Append two reboot-shape tests**

```python
def test_reboot_script_tests_var_run_reboot_required(ubuntu_cfg_factory):
    # /var/run/reboot-required is the standard Ubuntu signal written by
    # base apt postinst hooks for kernel/glibc/libssl etc. The script
    # tests for it and uses systemctl reboot if present.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/usr/local/sbin/ks-gen-reboot-if-needed" in out
    assert "chmod 755 /usr/local/sbin/ks-gen-reboot-if-needed" in out
    assert "[ -f /var/run/reboot-required ]" in out
    assert "systemctl reboot" in out
    # logger writes journal lines tagged "ks-gen" — auditable.
    assert "logger -t ks-gen" in out


def test_reboot_timer_oncalendar_reflects_cfg(ubuntu_cfg_factory):
    from ks_gen.config import (
        Overrides,
        RebootWindowCfg,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(
                reboot_window=RebootWindowCfg(on_calendar="Sun *-*-* 06:00:00"),
            ),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "/etc/systemd/system/ks-gen-reboot-if-needed.timer" in out
    assert "OnCalendar=Sun *-*-* 06:00:00" in out
    assert "OnCalendar=Sun *-*-* 03:00:00" not in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_unattended_updates.py -v`
Expected: 20 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert unattended_updates reboot block shape"
```

---

## Task 7: Packages + Protocol contract tests

Two tests: `emit_packages` returns `["unattended-upgrades"]` when either update timer is enabled (and `[]` when both are off), and a final contract test guarding `id`, `summary`, `depends_on`, `emit_tailoring`, `exception_entry`.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_unattended_updates.py`

- [ ] **Step 1: Append two contract tests**

```python
def test_emit_packages_returns_unattended_upgrades_when_either_timer_enabled(
    ubuntu_cfg_factory,
):
    from ks_gen.config import (
        MonthlyFullCfg,
        NightlySecurityCfg,
        Overrides,
        RebootWindowCfg,
        UnattendedUpdatesCfg,
    )

    # Default: both timers on -> package required.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == ["unattended-upgrades"]

    # Only nightly -> package still required.
    cfg_nightly_only = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(
                nightly_security=NightlySecurityCfg(),
                monthly_full=MonthlyFullCfg(enable=False),
                reboot_window=RebootWindowCfg(),
            ),
        )}
    )
    assert RULE.emit_packages(cfg_nightly_only) == ["unattended-upgrades"]

    # Only monthly -> package still required.
    cfg_monthly_only = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(
                nightly_security=NightlySecurityCfg(enable=False),
                monthly_full=MonthlyFullCfg(),
                reboot_window=RebootWindowCfg(),
            ),
        )}
    )
    assert RULE.emit_packages(cfg_monthly_only) == ["unattended-upgrades"]

    # Both update timers off + reboot off (validator forbids reboot-only)
    # -> no package required.
    cfg_all_off = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            unattended_updates=UnattendedUpdatesCfg(
                nightly_security=NightlySecurityCfg(enable=False),
                monthly_full=MonthlyFullCfg(enable=False),
                reboot_window=RebootWindowCfg(enable=False),
            ),
        )}
    )
    assert RULE.emit_packages(cfg_all_off) == []


def test_id_and_summary_and_contract_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import unattended_updates as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []
    # Deferred until ssg-ubuntu2404-ds.xml rule survey lands.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None
```

- [ ] **Step 2: Run all tests in the file**

Run: `pytest tests/rules/test_ubuntu2404_unattended_updates.py -v`
Expected: 22 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_unattended_updates.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert protocol contract for unattended_updates"
```

---

## Task 8: Regenerate the ubuntu_minimal golden snapshot

**Files:**
- Modify: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

- [ ] **Step 1: Run the golden test to confirm it fails**

Run: `pytest tests/golden/ -v -k ubuntu_minimal`
Expected: FAIL — syrupy reports the snapshot diff for the new
unattended_updates band.

(Note: the snapshot may already be modified in the working tree if an
earlier `pytest -q` run via pre-commit hooks regen'd it during prior
tasks. In that case Step 1 still works — just verify the diff against
expectations in Step 3.)

- [ ] **Step 2: Regenerate the snapshot if not already updated**

If the snapshot test failed in Step 1:
Run: `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`

If `git status` already shows the snapshot file as modified, skip the
update command — the existing changes are what we want to inspect.

- [ ] **Step 3: Inspect the diff**

Run: `git diff tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

Expected diff (and ONLY these changes):

1. `- Applied rules: 7` → `+ Applied rules: 8` in the Summary section.
2. `+ - `unattended_updates` — Configure dnf-automatic for nightly
   security + monthly full updates, with reboot inside a maintenance
   window.` inserted at its sorted position in the Applied-rules list.
   (The writer's existing sort key determines the exact location;
   observe the diff and accept what came out — should be a single
   one-line insertion. The `meta.SUMMARY` text still says
   "dnf-automatic" — that's distro-leakage in the shared meta and is
   out of scope to fix here.)
3. A new `# rule:unattended_updates ──────────...` band inside
   `late-commands` containing the three blocks: the nightly drop-ins
   (20auto-upgrades + 52ks-gen-unattended + apt-daily.timer.d +
   apt-daily-upgrade.timer.d), the monthly custom timer
   (ks-gen-apt-full-upgrade script + service + timer), and the reboot
   script + service + timer.
4. `+ - unattended-upgrades` added to the `autoinstall.packages:` list
   (alphabetical insertion). The block reflects `emit_packages`
   returning `["unattended-upgrades"]` for default cfg.

If any alma9 snapshot diffs, STOP — investigate before proceeding.

**Merge-order assumption.** The 7 → 8 count assumes this branch sits
on main at `35c1470` (post-v0.19.0, phases 3.0/3.1/3.2/3.3/3.4/3.5
merged = 7 ubuntu rules). If unrelated work landed first that added
another rule, regenerate and confirm "+1 your rule, nothing else."

- [ ] **Step 4: Commit the snapshot**

```bash
git add tests/golden/__snapshots__/test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regen ubuntu_minimal snapshot for unattended_updates rule"
```

---

## Task 9: CI parity + push + PR

- [ ] **Step 1: ruff check**

Run: `ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 2: ruff format --check**

Run: `ruff format --check src tests`
Expected: `N files already formatted`

If reformat needed:

```bash
ruff format src tests
ruff format --check src tests
git add -u
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "style: ruff format src tests"
```

- [ ] **Step 3: mypy**

Run: `mypy`
Expected: `Success: no issues found in N source files`

- [ ] **Step 4: pytest**

Run: `pytest -q`
Expected: ~841 tests pass (819 from end of phase 3.5 + 22 new
unattended_updates tests). Exact baseline count may differ if other
work has landed since v0.19.0 — what matters is "+22 tests, all green."

- [ ] **Step 5: Verify signed-clean**

Run: `git log --show-signature -10 --oneline`
Expected: every commit on this branch since `c93034c` (spec) is signed
with key `BE707B220C995478`.

- [ ] **Step 6: Push**

Run: `git push -u origin phase-3.6-unattended-updates`
Expected: push succeeds; GitHub returns the PR URL.

If push fails with `GH007`, STOP and surface to user.

- [ ] **Step 7: Open the PR**

```bash
gh pr create --title "feat(rules/ubuntu2404): unattended_updates port (#81 phase 3.6)" --body "$(cat <<'EOF'
## Summary

- Ports the `unattended_updates` rule to ubuntu2404 (issue #81 phase 3.6).
- Three independent blocks each gated on its own `enable` flag in `cfg.overrides.unattended_updates.{nightly_security,monthly_full,reboot_window}`:
  - **Nightly security** uses Ubuntu's stock plumbing: writes `/etc/apt/apt.conf.d/20auto-upgrades` (the canonical enable file) and `/etc/apt/apt.conf.d/52ks-gen-unattended` (mail-off + auto-reboot-off policy overlay), then drops in on both `apt-daily.timer` and `apt-daily-upgrade.timer` with the operator's `OnCalendar` and `RandomizedDelaySec=0`. Apply waits for fetch via the stock `After=apt-daily.service` dependency.
  - **Monthly full** installs `/usr/local/sbin/ks-gen-apt-full-upgrade` (runs `apt-get update` then `apt-get -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold dist-upgrade`) plus a custom `ks-gen-apt-full-upgrade.{service,timer}` pair. `dist-upgrade` mirrors dnf-automatic's `upgrade_type=default` STIG full-coverage intent; the Dpkg flag pair prevents conffile prompts from hanging the unit.
  - **Reboot window** installs `/usr/local/sbin/ks-gen-reboot-if-needed` that consults `/var/run/reboot-required` (Ubuntu's canonical needs-reboot signal, written by base apt postinst hooks for kernel/glibc/libssl/etc.) and runs `systemctl reboot` if present. Custom `ks-gen-reboot-if-needed.{service,timer}` schedules it.
- `emit_packages` returns `["unattended-upgrades"]` whenever either of the two update timers is enabled.
- `emit_tailoring` + `exception_entry` deferred to the audit-story PR (consistent with phases 3.1–3.5).

Spec: `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-6-unattended-updates-design.md`
Plan: `docs/superpowers/plans/2026-06-19-ubuntu-stig-autoinstall-phase-3-6-unattended-updates.md`

## Test plan

- [x] 22 new unit tests in `tests/rules/test_ubuntu2404_unattended_updates.py` cover: `applies` parent-enable short-circuit, per-block gating (each of the three blocks present-by-default + omitted-when-disabled), nightly block shape (20auto-upgrades content / 52ks-gen-unattended policy / both timer drop-ins / OnCalendar substitution / enable lines), monthly block shape (wrapper script content / dist-upgrade with Dpkg confdef+confold pair / timer OnCalendar substitution / enable line), reboot block shape (/var/run/reboot-required test + systemctl reboot + logger), `emit_packages` matrix (both on, only nightly, only monthly, all off), and the Rule Protocol contract (id, summary, depends_on, emit_tailoring, exception_entry).
- [x] `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` regenerated — diff adds the `# rule:unattended_updates` band (3 blocks), bumps Applied-rules header 7 → 8, and inserts `unattended-upgrades` into `autoinstall.packages:`. No alma9 snapshot changes.
- [x] Full CI chain run locally: `ruff check && ruff format --check && mypy && pytest -q` — all four green.
- [x] Each commit on this branch is GPG-signed with `BE707B220C995478`.
EOF
)"
```

- [ ] **Step 8: Wait for GitHub CI**

Run: `gh pr checks <pr-number>`
Expected: 5/5 checks pass.

Or poll:
```bash
until gh pr checks <pr-number> --json bucket --jq 'all(.[]; .bucket != "pending")' | grep -q true; do sleep 30; done
gh pr checks <pr-number>
```

If any check fails, STOP and report.
