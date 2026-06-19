"""Shared identity for the banner_text rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "banner_text"
SUMMARY = "Write civilian-equivalent login banner; suppress DoD-text oscap rules."
DEPENDS_ON: list[str] = []
EXCEPTION_SUMMARY = "Substitutes private-system banner for DISA-mandated DoD text."
EXCEPTION_REASON = (
    "Server is not a U.S. Government Information System; literal DoD banner "
    "would make false legal claims. Civilian text satisfies the rule intent "
    "(warn unauthorized users; consent to monitoring)."
)
