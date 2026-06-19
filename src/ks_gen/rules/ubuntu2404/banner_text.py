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


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml banner-rule survey lands in the audit-story PR.
        return []

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
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
