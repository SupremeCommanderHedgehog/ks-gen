"""Shared identity for the kernel_module_blacklist rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "kernel_module_blacklist"
SUMMARY = "Write modprobe blacklist for unused/disallowed kernel modules."
DEPENDS_ON: list[str] = []
