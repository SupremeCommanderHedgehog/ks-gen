"""alma8 banner_text — re-exports the alma9 implementation.

/etc/issue, /etc/issue.net, /etc/motd, and the sshd banner directive
are universal across RHEL-family installs. SSG rule IDs for the
DoD-text banner checks differ between ssg-almalinux8 and -9 — handled
in the audit-story PR.
"""

from __future__ import annotations

from ks_gen.rules.alma9.banner_text import RULE

__all__ = ["RULE"]
