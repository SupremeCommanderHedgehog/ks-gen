"""alma8 package_purge — re-exports the alma9 implementation.

`dnf -y remove` is the same command on RHEL 8 and 9. The default
excluded list (telnet-server, rsh-server, tftp-server, vsftpd,
ypserv) targets package names that are RHEL-family canonical and
exist (or don't, harmlessly) in both AL8 and AL9 archives.
"""

from __future__ import annotations

from ks_gen.rules.alma9.package_purge import RULE

__all__ = ["RULE"]
