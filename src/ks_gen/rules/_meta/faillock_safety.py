"""Shared identity for the faillock_safety rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.

Note: exception_entry summary is runtime-computed from cfg (it embeds
unlock_time and even_deny_root values). The reason string is static and
is extracted here as EXCEPTION_REASON.
"""

from __future__ import annotations

ID = "faillock_safety"
SUMMARY = "Set faillock unlock_time and disable even_deny_root for remote safety."
DEPENDS_ON: list[str] = []
EXCEPTION_REASON = "Prevents permanent lockout of the sole remote admin on a missed-key event."
