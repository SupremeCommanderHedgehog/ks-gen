"""Shared identity for the skel_init_files rule.

Imported by every distro implementation (alma8, alma9, alma10) so the
rule's auditor-facing English does not drift between distros. Only the
STIG rule ID differs.
"""

from __future__ import annotations

ID = "skel_init_files"
SUMMARY = "Tighten /etc/skel's init files to 0740 so every new user's home is STIG-compliant."
DEPENDS_ON: list[str] = []
