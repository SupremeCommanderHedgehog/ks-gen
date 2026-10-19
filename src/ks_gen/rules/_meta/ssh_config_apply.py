"""Shared identity for the ssh_config_apply rule.

Imported by every distro implementation (alma8, alma9, alma10) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "ssh_config_apply"
SUMMARY = "Write sshd drop-in config for Port/PermitRootLogin/PasswordAuthentication."
# crypto_policy must precede this rule: its %post generates the SSH host keys,
# and `sshd -t` below exits non-zero when none exist, aborting the install
# (#72). That ordering used to hold only by alphabetical rule discovery.
DEPENDS_ON: list[str] = ["admin_user_and_keys", "ssh_keep_open", "crypto_policy"]
