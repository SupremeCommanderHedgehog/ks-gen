"""alma10 banner_text — re-exports the alma9 implementation.

This was a real divergence when alma9 still disabled `banner_etc_issue_net`
(absent from ssg-almalinux10-ds.xml). #61 dropped that ID from alma9 because
neither the AL8 nor the AL9 stig profile selects it, so the divergence is gone.

Both distros now disable the same three rules: `banner_etc_issue`,
`dconf_gnome_banner_enabled`, and `dconf_gnome_login_banner_text`.
"""

from __future__ import annotations

from ks_gen.rules.alma9.banner_text import RULE

__all__ = ["RULE"]
