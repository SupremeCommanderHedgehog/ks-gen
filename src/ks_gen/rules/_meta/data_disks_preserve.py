"""Shared identity for the data_disks_preserve rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "data_disks_preserve"
SUMMARY = "Mount preserved data disks via fstab from %post."
DEPENDS_ON: list[str] = []
