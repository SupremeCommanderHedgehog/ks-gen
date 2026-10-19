"""alma10 auditd_actions — the alma9 implementation with no governing rules.

ssg-almalinux10 0.1.82's stig profile selects none of the auditd action rules
and refines none of their Values, so every set_value would be inert tailoring
and there is no STIG requirement to deviate from (#68). `emit_post` still
writes the operator's choices into /etc/audit/auditd.conf.
"""

from __future__ import annotations

from typing import cast

from ks_gen.rules._types import Rule
from ks_gen.rules.alma9.auditd_actions import AuditdActions, Setting

SETTINGS: tuple[Setting, ...] = (
    Setting("disk_full_action"),
    Setting("disk_error_action"),
    Setting("max_log_file_action"),
)

RULE: Rule = cast(Rule, AuditdActions(SETTINGS))
