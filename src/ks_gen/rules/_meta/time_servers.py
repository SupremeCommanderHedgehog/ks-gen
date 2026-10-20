"""Shared identity for the time_servers rule.

Imported by every distro implementation (alma8, alma9, alma10) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "time_servers"
SUMMARY = "Write a STIG-hardened chrony.conf with operator-chosen NTP servers (non-DoD by default)."
DEPENDS_ON: list[str] = []
NTS_EXCEPTION_SUMMARY = "chrony time sources are not authenticated with NTS."
NTS_EXCEPTION_REASON = (
    "time.nts is off: the configured time servers are used over plain NTP, so "
    "chrony_set_nts cannot pass. Set time.nts: true with NTS-capable servers to "
    "comply."
)
