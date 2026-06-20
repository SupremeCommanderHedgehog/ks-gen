"""alma8 ssh_config_apply — re-exports the alma9 implementation.

/etc/ssh/sshd_config.d/ drop-in support shipped in OpenSSH 8.2+
(RHEL 8.2+ via openssh 8.0 base + RHEL backport). All four SSH
directives the rule manages — Port, PermitRootLogin,
PasswordAuthentication, KbdInteractiveAuthentication — have the
same syntax on both releases.
"""

from __future__ import annotations

from ks_gen.rules.alma9.ssh_config_apply import RULE

__all__ = ["RULE"]
