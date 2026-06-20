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
        # Deferred: ssg-ubuntu2404-ds.xml unattended-updates rule survey lands
        # in the audit-story PR.
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
