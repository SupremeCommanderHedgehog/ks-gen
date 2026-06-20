"""alma8 usbguard — re-exports the alma9 implementation.

usbguard ships in EPEL for both RHEL 8 and 9. The rule itself is
scaffolding-only in both distros today (applies=True, emit_post=
empty); the meaningful tailoring / exception work is deferred to
the audit-story PR.
"""

from __future__ import annotations

from ks_gen.rules.alma9.usbguard import RULE

__all__ = ["RULE"]
