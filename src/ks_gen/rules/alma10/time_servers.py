"""alma10 time_servers — the alma9 implementation plus chrony_set_nts.

AL10's stig profile (SSG 0.1.82 and the 0.1.78 media floor) also selects
chrony_set_nts, whose check wants `nts` on every server/pool/peer line. With
time.nts on, the shared %post emits it; with it off (the default, since
pool.ntp.org offers no NTS) the rule is tailored out and declared as an
exception, not left failing unexplained (#125). AL8/AL9 select no NTS rule.
"""

from __future__ import annotations

from typing import cast

from ks_gen.rules._types import Rule
from ks_gen.rules.alma9.time_servers import CHRONY_RULES, TimeServers
from ks_gen.ssg_ids import RULE_PREFIX

_NTS_RULE = f"{RULE_PREFIX}chrony_set_nts"

RULE: Rule = cast(
    Rule, TimeServers(stig_rules_affected=[*CHRONY_RULES, _NTS_RULE], nts_rule=_NTS_RULE)
)
