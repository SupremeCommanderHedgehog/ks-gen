"""Shared identity for the container_host rule.

Imported by every distro implementation (alma8, alma9, alma10) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "container_host"
SUMMARY = "Install rootless-container helper, storage.conf, and per-user setup on /srv/containers."
# skel_init_files tightens /etc/skel before this rule's %post creates a home
# from it (#131).
DEPENDS_ON: list[str] = ["skel_init_files"]
