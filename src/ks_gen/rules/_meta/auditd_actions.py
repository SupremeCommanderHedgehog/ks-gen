"""Shared identity for the auditd_actions rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.

Note: exception_entry summary and reason are runtime-computed from cfg
(they embed the configured action values), so no EXCEPTION_SUMMARY /
EXCEPTION_REASON constants are defined here.
"""

from __future__ import annotations

ID = "auditd_actions"
SUMMARY = "auditd disk_full/disk_error/max_log_file actions (SUSPEND/ROTATE default)."
DEPENDS_ON: list[str] = []
