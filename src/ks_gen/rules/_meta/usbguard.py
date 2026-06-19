"""Shared identity for the usbguard rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "usbguard"
SUMMARY = "Enable or disable USBGuard install + service per overrides."
DEPENDS_ON: list[str] = []
EXCEPTION_SUMMARY = "USBGuard not installed/enabled."
EXCEPTION_REASON = (
    "Cloud/headless VMs have no USB; USBGuard is overhead with no benefit. "
    "Enable explicitly on bare-metal hosts."
)
