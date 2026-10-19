"""Shared identity for the package_purge rule.

Imported by every distro implementation (alma8, alma9, alma10) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "package_purge"
SUMMARY = "Remove disallowed packages after install (catches transitive pulls)."
DEPENDS_ON: list[str] = []
