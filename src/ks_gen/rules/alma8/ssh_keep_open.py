"""alma8 ssh_keep_open — re-exports the alma9 implementation.

firewalld is the default firewall on both RHEL 8 and 9. The
`firewall-cmd --add-port` / `--permanent` flow is identical.
SELinux semanage port-rule semantics are unchanged.
"""

from __future__ import annotations

from ks_gen.rules.alma9.ssh_keep_open import RULE

__all__ = ["RULE"]
