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
        pkgs: list[str] = []
        if u.nightly_security.enable or u.monthly_full.enable:
            pkgs.append("dnf-automatic")
        if u.reboot_window.enable:
            pkgs.append("dnf-utils")
        return pkgs

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


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


RULE: Rule = cast(Rule, _Rule())
