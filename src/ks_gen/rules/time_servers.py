from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = "time_servers"
    summary: str = "Write chrony.conf with operator-chosen NTP servers (non-DoD by default)."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        servers = "\n".join(f"server {s} iburst" for s in cfg.time.servers)
        thresh = cfg.time.chrony_makestep_threshold
        return f"""\
# Chrony configuration (servers from host.yaml; STIG-compliant base)
cat > /etc/chrony.conf <<'__KS_GEN_EOF__'
{servers}
driftfile /var/lib/chrony/drift
makestep {thresh} 3
rtcsync
logdir /var/log/chrony
__KS_GEN_EOF__
chmod 644 /etc/chrony.conf
"""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
