"""alma8 ssh_keep_open — re-exports the alma9 implementation.

firewalld is the default firewall on both RHEL 8 and 9, and
`firewall-offline-cmd --add-port` (which writes the permanent config
with no daemon, as %post's chroot requires) behaves the same on both.
SELinux semanage port-rule semantics are unchanged.
"""

from __future__ import annotations

from ks_gen.rules.alma9.ssh_keep_open import RULE

__all__ = ["RULE"]
