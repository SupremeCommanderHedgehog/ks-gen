"""Shared identity for the admin_user_and_keys rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "admin_user_and_keys"
SUMMARY = "Create wheel admin, drop authorized_keys, sudoers fragment."
DEPENDS_ON: list[str] = []
