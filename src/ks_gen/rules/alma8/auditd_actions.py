"""alma8 auditd_actions — re-exports the alma9 implementation.

`/etc/audit/auditd.conf` and the disk_full_action / disk_error_action /
max_log_file_action field names are identical on RHEL 8 and RHEL 9.
auditd ships in the base install on both. SSG rule IDs differ between
ssg-almalinux8 and ssg-almalinux9 datastreams — that drift surfaces
in the audit-story PR, not here.
"""

from __future__ import annotations

from ks_gen.rules.alma9.auditd_actions import RULE

__all__ = ["RULE"]
