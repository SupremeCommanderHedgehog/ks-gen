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
# Under STIG the deviation is not a choice: kernel FIPS mode disables the
# AES-SIV AEADs NTS needs for NTP packets (#125), so time.nts is rejected.
NTS_EXCEPTION_REASON_FIPS = (
    "NTS is unavailable in FIPS mode: NTS authenticates NTP packets with AES-SIV, "
    "which the FIPS crypto policy disables (NTS key exchange succeeds, then no "
    "packet can be protected). The STIG's FIPS requirement therefore rules out "
    "chrony_set_nts; time is synchronised over plain NTP."
)
