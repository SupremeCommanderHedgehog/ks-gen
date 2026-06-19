"""Shared identity for the ssh_keep_open rule."""

from __future__ import annotations

ID = "ssh_keep_open"
SUMMARY = "Ensure ssh.port reachable in firewalld + SELinux before sshd starts."
DEPENDS_ON: list[str] = []
