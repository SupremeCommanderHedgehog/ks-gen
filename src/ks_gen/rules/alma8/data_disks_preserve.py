"""alma8 data_disks_preserve — re-exports the alma9 implementation.

/etc/fstab, mkdir -p, mount -a, and restorecon -R are universal on
RHEL-family. UUID/LABEL/by-id resolution is kernel-level and identical
on AL8 and AL9.
"""

from __future__ import annotations

from ks_gen.rules.alma9.data_disks_preserve import RULE

__all__ = ["RULE"]
