"""alma8 auditd_actions — the alma9 implementation with alma8's governing rules.

ssg-almalinux8 0.1.82 selects the plain `auditd_data_disk_{full,error}_action`
rules, whose checks compare against the Value itself: the set_value makes any
operator choice verify, so nothing is ever disabled. The profile still refines
both Values to syslog|single|halt, so other choices are documented as an
exception. No stig-selected rule reads var_auditd_max_log_file_action, so it
gets no set_value (#68), but the profile refines it to syslog, so any other
choice is documented too.
"""

from __future__ import annotations

from typing import cast

from ks_gen.rules._types import Rule
from ks_gen.rules.alma9.auditd_actions import _RULE, _SYSTEM_ACTIONS, AuditdActions, Setting

SETTINGS: tuple[Setting, ...] = (
    Setting(
        "disk_full_action",
        f"{_RULE}auditd_data_disk_full_action",
        _SYSTEM_ACTIONS,
        check_reads_value=True,
    ),
    Setting(
        "disk_error_action",
        f"{_RULE}auditd_data_disk_error_action",
        _SYSTEM_ACTIONS,
        check_reads_value=True,
    ),
    # No selected rule reads it, but the profile still refines it to syslog:
    # documented as a deviation, never set_value'd (#68).
    Setting("max_log_file_action", accepts=frozenset({"syslog"})),
)

RULE: Rule = cast(Rule, AuditdActions(SETTINGS))
