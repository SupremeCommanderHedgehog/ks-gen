from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import ssh_config_apply as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    s = cfg.ssh
    pwd = "yes" if s.password_authentication else "no"
    pam = "yes" if s.use_pam else "no"
    # phase 3.1's banner_text writes /etc/ssh/sshd-banner only when "motd"
    # is in apply_to. Gate the Banner directive on the same condition so
    # sshd never points at a missing file.
    banner_line = "Banner /etc/ssh/sshd-banner\n" if "motd" in cfg.banner.apply_to else ""
    return f"""\
# Drop-in SSH server config (active on first boot)
install -d -m 755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/00-ks-gen.conf <<'__KS_GEN_EOF__'
Port {s.port}
PermitRootLogin {s.permit_root_login}
PasswordAuthentication {pwd}
ClientAliveInterval {s.client_alive_interval}
ClientAliveCountMax {s.client_alive_count_max}
MaxAuthTries {s.max_auth_tries}
UsePAM {pam}
{banner_line}__KS_GEN_EOF__
chmod 600 /etc/ssh/sshd_config.d/00-ks-gen.conf
sshd -t
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
        # Deferred: ssg-ubuntu2404-ds.xml sshd-rule survey lands in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
