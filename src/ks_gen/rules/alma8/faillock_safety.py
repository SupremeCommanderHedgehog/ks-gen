"""alma8 faillock_safety — re-exports the alma9 implementation.

/etc/security/faillock.conf is the same on RHEL 8 and 9 (introduced
in RHEL 8). pam_faillock is the standard PAM module on both. The
deny / unlock_time / even_deny_root knobs all have the same shape.
"""

from __future__ import annotations

from ks_gen.rules.alma9.faillock_safety import RULE

__all__ = ["RULE"]
