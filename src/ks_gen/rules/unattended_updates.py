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
        u = cfg.overrides.unattended_updates
        parts: list[str] = []
        if u.nightly_security.enable:
            parts.append(_nightly_security_block(u.nightly_security.on_calendar))
        return "\n".join(parts)

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


RULE: Rule = cast(Rule, _Rule())
