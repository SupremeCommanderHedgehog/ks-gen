"""Shared identity for the dod_root_ca rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "dod_root_ca"
SUMMARY = "Skip DoD root CA bundle installation."
DEPENDS_ON: list[str] = []
EXCEPTION_SUMMARY = "DoD root/intermediate CA bundle not installed."
EXCEPTION_REASON = "Server is not a DoD asset; bundle is not applicable."
