"""Shared identity for the crypto_policy rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.

Note: exception_entry summary and reason are runtime-computed from cfg
(they embed cfg.crypto.policy.value), so no EXCEPTION_SUMMARY /
EXCEPTION_REASON constants are defined here.
"""

from __future__ import annotations

ID = "crypto_policy"
SUMMARY = "Apply system crypto-policy; optionally generate Ed25519 host keys."
DEPENDS_ON: list[str] = []
