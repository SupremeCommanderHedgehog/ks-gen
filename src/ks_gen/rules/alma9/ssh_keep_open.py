from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    port = cfg.ssh.port
    parts: list[str] = []
    if cfg.overrides.ssh_keep_open.ensure_selinux_port and port != 22:
        parts.append(
            f"semanage port -a -t ssh_port_t -p tcp {port} 2>/dev/null || "
            f"semanage port -m -t ssh_port_t -p tcp {port}"
        )
    if cfg.overrides.ssh_keep_open.ensure_firewalld_port:
        parts.append(f"firewall-offline-cmd --add-port={port}/tcp")
    if not parts:
        return "# ssh_keep_open: nothing to do\n"
    return (
        "# Pre-open SSH port in firewalld + SELinux (before sshd starts on first boot)\n"
        + "\n".join(parts)
        + "\n"
    )


@dataclass(frozen=True)
class _Rule:
    id: str = "ssh_keep_open"
    summary: str = "Ensure ssh.port reachable in firewalld + SELinux before sshd starts."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        o = cfg.overrides.ssh_keep_open
        return o.ensure_firewalld_port or o.ensure_selinux_port

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
