# Phase 3.6 — `unattended_updates` port to ubuntu2404

**Parent:** #81 ubuntu STIG autoinstall.
**Previous phases on this workstream:** 3.0 admin_user_and_keys +
ssh_keep_open (#94), 3.1 banner_text (#101), 3.2 ssh_config_apply
(#102), 3.3 time_servers (#104), 3.4 crypto_policy (#106), 3.5
faillock_safety (#108).

## Goal

Port the `unattended_updates` rule to ubuntu2404 so the generated
autoinstall produces a **functional** automatic-patching policy on
Ubuntu Server. That requires three coordinated, independently-gated
blocks: nightly security upgrades via the stock `unattended-upgrades`
plumbing (apt-daily + apt-daily-upgrade timers), monthly full
upgrades via a custom `ks-gen-apt-full-upgrade` timer running
`apt-get dist-upgrade`, and a reboot-window timer that consults
`/var/run/reboot-required`.

## Non-goals

- **ssg-ubuntu2404-ds.xml tailoring + exception text.** Deferred to
  the coordinated audit-story PR per the established phase-3.x
  pattern. The RHEL XCCDF rule IDs in the alma9 rule do not carry
  over verbatim to the Ubuntu datastream and need to be re-surveyed
  there.
- **Schema changes.** `UnattendedUpdatesCfg`, `NightlySecurityCfg`,
  `MonthlyFullCfg`, `RebootWindowCfg` are already distro-agnostic in
  `src/ks_gen/config.py:614-647` — no edits. The
  `_reboot_window_needs_an_update_timer` model validator already
  enforces "no reboot-only configs."
- **Replacing the stock `apt-daily.timer` / `apt-daily-upgrade.timer`
  with custom timers.** We drop-in over them — keeps Ubuntu's
  canonical mechanism, future apt upgrades to those units flow
  through.
- **Touching `/etc/apt/apt.conf.d/50unattended-upgrades`.** That's
  Debian/Ubuntu's stock policy file; layering policy in
  `/etc/apt/apt.conf.d/52ks-gen-unattended` avoids a conffile prompt
  on future `unattended-upgrades` package upgrades.

## Architecture

One new rule module + one new test file. Shared
`src/ks_gen/rules/_meta/unattended_updates.py` (ID, SUMMARY,
DEPENDS_ON) is untouched.

`emit_post` composes up to three independent blocks in sequence, each
gated on its own `enable` flag (mirrors alma9's structure exactly):

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

Splitting by responsibility means a future change to the apt-daily
drop-in pattern doesn't risk corrupting the full-upgrade timer or the
reboot script.

The rule plugs into the existing ubuntu2404 bundle pipeline:
- `emit_post` contributes a `# rule:unattended_updates` band to
  `late-commands`.
- `emit_packages` returns `["unattended-upgrades"]` when
  `nightly_security.enable or monthly_full.enable`. The package
  ships `unattended-upgrades(8)` and the stock
  `50unattended-upgrades` policy file. The reboot-window block needs
  no extra packages — `/var/run/reboot-required` is written by base
  `apt` postinst hooks.
- `applies(cfg)` gates on `cfg.overrides.unattended_updates.enable`
  (parent toggle).

No changes to `writer.py`, `skeleton.py`, the user-data template, or
the config schema.

## Files touched

- **Create:** `src/ks_gen/rules/ubuntu2404/unattended_updates.py`
- **Create:** `tests/rules/test_ubuntu2404_unattended_updates.py`
- **Modify:** `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`
  (snapshot regen)

## `emit_post` behavior

### Block 1: Nightly security (`_nightly_security_block`)

Mirror of alma9's `dnf-automatic.timer` drop-in pattern, adapted to
Ubuntu's split fetch/apply timer pair:

```bash
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
```

Design notes:
- `20auto-upgrades` is the canonical Debian/Ubuntu file that flips
  the periodic apt-daily logic from "off" to "on." `0` would
  silently disable us.
- `52ks-gen-unattended` layers two policies on top of the stock
  `50unattended-upgrades` file: mail off (no SMTP fanout from late
  installs), auto-reboot off (only our reboot_window block reboots).
  Numeric prefix `52` sorts after `50` so our values win without
  overwriting Ubuntu's stock allowed-origins list.
- The `OnCalendar=` clear-then-set pattern is the documented way to
  override systemd timer's `OnCalendar` (multiple `OnCalendar=` lines
  union; resetting then setting one is the canonical override).
- `RandomizedDelaySec=0` neutralizes the default ~12h spread — the
  operator picked a precise time, we deliver it precisely.
- Both timers fire at the same `on_calendar`. `apt-daily-upgrade.service`'s
  stock `After=apt-daily.service` makes apply wait for fetch.

### Block 2: Monthly full (`_monthly_full_block`)

Mirror of alma9's custom `ks-gen-dnf-automatic-full.timer` pattern,
driving `apt-get dist-upgrade`:

```bash
# unattended_updates: monthly full update via custom ks-gen timer
cat > /usr/local/sbin/ks-gen-apt-full-upgrade <<'__KS_GEN_EOF__'
#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y \
  -o Dpkg::Options::='--force-confdef' \
  -o Dpkg::Options::='--force-confold' \
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
```

Design notes:
- `set -euo pipefail` plus `DEBIAN_FRONTEND=noninteractive` matches
  the alma9 reboot-script preamble. Catches partial failures, blocks
  dpkg conf prompts.
- `apt-get update` first because we have our own schedule —
  `apt-daily.timer` may not have refreshed since last fire.
- `dist-upgrade` (not `upgrade`) parallels dnf-automatic's
  `upgrade_type = default` semantics: pick up kernel/glibc/etc.
  transitions that change the dep graph. STIG patching mandate is
  full coverage.
- `Dpkg::Options::='--force-confdef'` + `'--force-confold'`: on a
  conf file conflict, take the existing on-disk file (the admin's
  edits), don't prompt. The pair must both be set; the alternative
  is the unit hanging forever waiting on stdin.
- `Persistent=true`: if the machine was off when the timer would
  have fired, run it at next boot. Default for monthly runs is
  `Sun *-*-1..7 02:30:00` (first Sunday of every month).

### Block 3: Reboot window (`_reboot_window_block`)

Mirror of alma9's `ks-gen-reboot-if-needed.timer` pattern, but
checking `/var/run/reboot-required` (Ubuntu's canonical signal):

```bash
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
```

Design notes:
- `/var/run/reboot-required` is written by base `apt` postinst hooks
  (kernel, glibc, libssl, etc.). It is the standard Ubuntu signal —
  every Ubuntu admin runbook, every monitoring agent, every
  motd-news script checks this file.
- No package addition needed; the file's creation is a hook owned by
  packages that are already installed.
- `logger -t ks-gen` writes a journal entry with a stable tag, so
  the operator can `journalctl -t ks-gen` to audit reboot decisions.

## Rule scaffolding

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

## Tests (22)

All use the `ubuntu_cfg_factory` fixture. Module-level imports of
`RULE`; local imports of `UnattendedUpdatesCfg, NightlySecurityCfg,
MonthlyFullCfg, RebootWindowCfg, Overrides` inside per-test override
functions (matches phase 3.3/3.4/3.5 pattern).

### `applies` semantics
1. `test_applies_when_enabled` — default cfg → True
2. `test_applies_short_circuits_when_disabled` — parent
   `enable=False` → False (rule excluded from late-commands)

### Block presence/absence gating
3. `test_post_includes_nightly_block_by_default`
4. `test_post_includes_monthly_block_by_default`
5. `test_post_includes_reboot_block_by_default`
6. `test_post_omits_nightly_block_when_disabled`
7. `test_post_omits_monthly_block_when_disabled`
8. `test_post_omits_reboot_block_when_disabled`

### Nightly block shape
9. `test_nightly_writes_20auto_upgrades_path_and_content`
10. `test_nightly_writes_52ks_gen_unattended_with_mail_and_reboot_off`
11. `test_nightly_drops_in_apt_daily_timer_with_oncalendar`
12. `test_nightly_drops_in_apt_daily_upgrade_timer_with_oncalendar`
13. `test_nightly_enables_both_timers`
14. `test_nightly_reflects_on_calendar_override` — cfg
    `nightly_security.on_calendar="*-*-* 04:00:00"`

### Monthly block shape
15. `test_monthly_writes_ks_gen_apt_full_upgrade_script`
16. `test_monthly_script_uses_dist_upgrade_with_dpkg_confdef_and_confold`
17. `test_monthly_timer_oncalendar_reflects_cfg` — cfg
    `monthly_full.on_calendar="Sun *-*-1..7 05:00:00"`
18. `test_monthly_enables_full_upgrade_timer`

### Reboot block shape
19. `test_reboot_script_tests_var_run_reboot_required`
20. `test_reboot_timer_oncalendar_reflects_cfg` — cfg
    `reboot_window.on_calendar="Sun *-*-* 06:00:00"`

### Packages + Protocol contract
21. `test_emit_packages_returns_unattended_upgrades_when_either_timer_enabled`
    — three sub-asserts: both on → `["unattended-upgrades"]`, only
    nightly → `["unattended-upgrades"]`, only monthly →
    `["unattended-upgrades"]`. And one more: both off →
    `[]` (reboot-only is rejected by the `_reboot_window_needs_an_update_timer`
    model validator, so we can't reach that path).
22. `test_id_and_summary_come_from_shared_meta` (+ inline asserts
    `emit_tailoring == []`, `exception_entry() is None`,
    `depends_on == []`)

## Snapshot regen

After tests pass, run `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`.

Expected diff (and ONLY these changes):

1. New `# rule:unattended_updates ──────────...` band in
   `late-commands` containing the three blocks (nightly drop-ins +
   monthly custom timer + reboot script + timer).
2. "Applied rules: N" header bumps from 7 to 8.
3. The Applied-rules list gains `- unattended_updates — Configure
   dnf-automatic for nightly security + monthly full updates, with
   reboot inside a maintenance window.` at its sorted position (the
   list is sorted by the writer's existing key — observe the actual
   ordering in the regen diff; it will be one line, not multiple).

   Note: the `meta.SUMMARY` text still says "dnf-automatic" — that's
   a known distro-leakage in the shared meta. Resolving it is out of
   scope for this phase; leave as-is for now (consistent with
   alma9's English).
4. `unattended-upgrades` added to autoinstall packages list (the
   `autoinstall.packages:` block in the snapshot YAML).

No alma9 snapshots affected.

### Merge-order assumption

The 7 → 8 count assumes this branch sits on main at `35c1470`
(post-v0.19.0, includes phases 3.0/3.1/3.2/3.3/3.4/3.5 = 7 ubuntu
rules). If unrelated work landed first, regenerate the snapshot and
confirm the diff is "+1 your rule, nothing else."

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| `unattended-upgrades` package install hits a conffile prompt during initial install | The package is part of `ubuntu-minimal` and ships with stock 50unattended-upgrades; we never overwrite that file (we layer 52ks-gen-unattended). No prompt. |
| `apt-daily.timer` drop-in syntax wrong → unit fails to start | systemd's `OnCalendar=` (empty) is the documented reset directive; pattern is identical to alma9's dnf-automatic.timer drop-in (proven in prod since v0.x). |
| `apt-get dist-upgrade` removes packages without operator review | `dist-upgrade` is intentional — STIG patching mandate is full coverage including kernel/glibc transitions. `dnf-automatic`'s `upgrade_type = default` has the same semantics. Operator can disable via `monthly_full.enable: false`. |
| `Dpkg::Options::=--force-confdef/--force-confold` masks security-relevant conffile changes | The pair preserves admin's edits, which is the correct default for headless automation. Operator who needs fresh conffiles can run `apt-get` manually. Without both, the timer hangs on first conffile conflict. |
| `/var/run/reboot-required` missed by libraries that don't write it | Acknowledged. ssh, sudo, libc6, kernel — the high-impact packages — all write it. Edge-case libs that don't write it lose nothing vs alma9's `needs-restarting -r` (which has its own gaps). |
| Stock `apt-daily-upgrade.service` has hardened `ProtectSystem=strict` and won't touch our drop-in directory | Drop-ins land in `/etc/systemd/system/<unit>.d/` which is part of systemd's standard config search path, not blocked by `ProtectSystem`. Verified by systemd man page. |
| `apt-daily.timer` chain runs before network is up after reboot | Stock unit already has `Wants=network-online.target` via the `apt-daily.service`. Our drop-in inherits. |

## CI parity check before push

Per `CLAUDE.md`:

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

If `ruff format --check` fails, fix with `ruff format src tests`.

## Out of scope (deferred)

- ssg-ubuntu2404-ds.xml unattended-updates rule IDs + `TailoringOp`
  entries.
- `exception_entry` English text.
- Renaming `meta.SUMMARY` to remove "dnf-automatic" (cross-distro
  meta cleanup — separate refactor PR).
- Removing the `ks-gen-apt-full-upgrade.timer` /
  `ks-gen-reboot-if-needed.timer` units on rule `enable=False` after
  a previous install enabled them. (Operator concern, not a
  kickstart-time concern.)
