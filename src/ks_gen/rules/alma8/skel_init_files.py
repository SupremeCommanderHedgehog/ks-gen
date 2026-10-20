"""alma8 skel_init_files — re-exports the alma9 implementation.

AL8's stig profile selects the same file_permission_user_init_files_root
rule as AL9's.
"""

from __future__ import annotations

from ks_gen.rules.alma9.skel_init_files import RULE

__all__ = ["RULE"]
