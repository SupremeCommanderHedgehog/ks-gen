"""alma10 banner_text — diverges from alma9.

ssg-almalinux10-ds.xml (0.1.81) has no `banner_etc_issue_net` rule at all.
The surviving near-equivalent, `banner_etc_issue_net_cis`, is not selected
by the stig profile, so disabling it would be inert — we drop the ID
rather than swap it.

`banner_etc_issue` and `dconf_gnome_banner_enabled` both still exist and
are stig-selected on AL10, so the rest of the mapping is unchanged.

emit_post is byte-identical to alma9 — writing /etc/issue et al is the
same on both releases, so we reuse the alma9 rule's implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import banner_text as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp
from ks_gen.rules.alma9.banner_text import RULE as _ALMA9_RULE

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED = [
    f"{_PREFIX}banner_etc_issue",
    # alma9 also disables banner_etc_issue_net here — absent from AL10 SSG.
    f"{_PREFIX}dconf_gnome_banner_enabled",
]


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED))

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return [TailoringOp(rule_id=r, action="disable") for r in _TAILORED]

    def emit_post(self, cfg: HostConfig) -> str:
        return _ALMA9_RULE.emit_post(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=meta.EXCEPTION_SUMMARY,
            stig_rules_disabled=list(_TAILORED),
            reason=meta.EXCEPTION_REASON,
        )


RULE: Rule = cast(Rule, _Rule())
