"""ubuntu2404 chrony NTP configuration.

Writes /etc/chrony/chrony.conf with operator-chosen servers from
cfg.time.servers. Adds the chrony package to autoinstall.packages so
it's present in the chroot before this late-command runs. Service
activation and systemd-timesyncd masking are owned by chrony's apt
postinst (Conflicts=systemd-timesyncd.service) — same config-only
stance as the alma9 rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import time_servers as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    servers = "\n".join(f"server {s} iburst" for s in cfg.time.servers)
    thresh = cfg.time.chrony_makestep_threshold
    return f"""\
# Chrony configuration (servers from host.yaml; STIG-compliant base)
install -d -m 755 /etc/chrony
cat > /etc/chrony/chrony.conf <<'__KS_GEN_EOF__'
{servers}
driftfile /var/lib/chrony/chrony.drift
makestep {thresh} 3
rtcsync
logdir /var/log/chrony
__KS_GEN_EOF__
chmod 644 /etc/chrony/chrony.conf
"""


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml time/NTP rule survey lands in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return ["chrony"]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
