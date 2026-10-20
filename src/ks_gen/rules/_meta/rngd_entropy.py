"""Shared identity for the rngd_entropy rule.

Imported by every distro implementation (alma8, alma9, alma10) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "rngd_entropy"
SUMMARY = "Install + enable rngd so SSH_USE_STRONG_RNG cannot starve sshd at boot."
DEPENDS_ON: list[str] = []
