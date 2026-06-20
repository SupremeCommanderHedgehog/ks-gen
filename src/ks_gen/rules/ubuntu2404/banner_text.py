from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import banner_text as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_TARGET = {
    "issue": "/etc/issue",
    "issue_net": "/etc/issue.net",
    "motd": "/etc/ssh/sshd-banner",
}

# ssg-ubuntu2404-ds.xml splits the banner checks into CIS and non-CIS variants.
# Our civilian banner moots all of them. `sshd_enable_warning_banner_net` is
# intentionally NOT in this list — ssh_config_apply's sshd drop-in enables
# the Banner directive, so that check is satisfied, not mooted.
_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED = [
    f"{_PREFIX}banner_etc_issue_cis",
    f"{_PREFIX}banner_etc_issue_net",
    f"{_PREFIX}banner_etc_issue_net_cis",
    f"{_PREFIX}banner_etc_motd_cis",
    f"{_PREFIX}dconf_gnome_banner_enabled",
    f"{_PREFIX}dconf_gnome_login_banner_text",
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
        text = cfg.banner.text.rstrip("\n") + "\n"
        lines = ["# Civilian-equivalent login banner"]
        for target in cfg.banner.apply_to:
            if target == "gdm":
                # Ubuntu Server has no GDM; tailoring for the matching oscap rule is deferred.
                continue
            path = _TARGET[target]
            lines.append(f"cat > {path} <<'__KS_GEN_EOF__'")
            lines.append(text.rstrip("\n"))
            lines.append("__KS_GEN_EOF__")
            lines.append(f"chmod 644 {path}")
        return "\n".join(lines) + "\n"

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
