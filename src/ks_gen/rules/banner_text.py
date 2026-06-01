from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED = [
    f"{_PREFIX}banner_etc_issue",
    f"{_PREFIX}banner_etc_issue_net",
    f"{_PREFIX}dconf_gnome_banner_enabled",
]

_TARGET = {
    "issue": "/etc/issue",
    "issue_net": "/etc/issue.net",
    "motd": "/etc/motd",
}


@dataclass(frozen=True)
class _Rule:
    id: str = "banner_text"
    summary: str = "Write civilian-equivalent login banner; suppress DoD-text oscap rules."
    depends_on: list[str] = field(default_factory=list)
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
                continue  # GDM banner only meaningful with GUI; oscap rule above disabled
            path = _TARGET[target]
            lines.append(f"cat > {path} <<'__KS_GEN_EOF__'")
            lines.append(text.rstrip("\n"))
            lines.append("__KS_GEN_EOF__")
            lines.append(f"chmod 644 {path}")
        return "\n".join(lines) + "\n"

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id="banner_text",
            summary="Substitutes private-system banner for DISA-mandated DoD text.",
            stig_rules_disabled=list(_TAILORED),
            reason=(
                "Server is not a U.S. Government Information System; literal DoD banner "
                "would make false legal claims. Civilian text satisfies the rule intent "
                "(warn unauthorized users; consent to monitoring)."
            ),
        )


RULE: Rule = cast(Rule, _Rule())
