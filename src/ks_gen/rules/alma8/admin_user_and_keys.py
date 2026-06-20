"""alma8 admin_user_and_keys — re-exports the alma9 implementation.

The alma9 rule is portable to alma8 verbatim: same useradd/usermod
flow, same /etc/sudoers.d/ drop-in shape, same SELinux semantics
(SELinux ships on both RHEL 8 and RHEL 9). The rule's SSG mapping
in `emit_tailoring` is deferred to the audit-story PR, so any
alma8-vs-alma9 SSG rule ID drift will surface there rather than
in this file.

When (if) alma8 ever needs to actually diverge from alma9 for
this rule, replace this re-export with a real implementation.
"""

from __future__ import annotations

from ks_gen.rules.alma9.admin_user_and_keys import RULE

__all__ = ["RULE"]
