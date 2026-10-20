"""alma10 skel_init_files — the alma9 implementation, AL10's rule ID.

AL10's stig profile selects file_permission_user_init_files instead of the
_root variant AL8/AL9 select (same var_user_initialization_files_regex and
0740 threshold), so only stig_rules_affected differs.
"""

from __future__ import annotations

from typing import cast

from ks_gen.rules._types import Rule
from ks_gen.rules.alma9.skel_init_files import SkelInitFiles
from ks_gen.ssg_ids import RULE_PREFIX

RULE: Rule = cast(
    Rule, SkelInitFiles(stig_rules_affected=[f"{RULE_PREFIX}file_permission_user_init_files"])
)
