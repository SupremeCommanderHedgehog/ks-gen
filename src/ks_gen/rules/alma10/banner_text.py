"""alma10 banner_text — re-exports the alma9 implementation.

This was a real divergence when alma9 still disabled `banner_etc_issue_net`
(absent from ssg-almalinux10-ds.xml). #61 dropped that ID from alma9 because
neither the AL8 nor the AL9 stig profile selects it, so both distros now
disable the same two rules and the divergence is gone.
"""

from __future__ import annotations

from ks_gen.rules.alma9.banner_text import RULE

__all__ = ["RULE"]
