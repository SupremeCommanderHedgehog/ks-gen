"""Shared identity for the unattended_updates rule.

Imported by every distro implementation (alma8, alma9, alma10) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "unattended_updates"
SUMMARY = (
    "Configure dnf-automatic for nightly security + monthly full updates, "
    "with reboot inside a maintenance window."
)
DEPENDS_ON: list[str] = []
