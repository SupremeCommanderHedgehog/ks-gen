from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    s = cfg.ssh
    pwd = "yes" if s.password_authentication else "no"
    pam = "yes" if s.use_pam else "no"
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
__KS_GEN_EOF__
chmod 600 /etc/ssh/sshd_config.d/00-ks-gen.conf
sshd -t
"""


@dataclass(frozen=True)
class _Rule:
    id: str = "ssh_config_apply"
    summary: str = "Write sshd drop-in config for Port/PermitRootLogin/PasswordAuthentication."
    depends_on: list[str] = field(default_factory=lambda: ["admin_user_and_keys", "ssh_keep_open"])
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
