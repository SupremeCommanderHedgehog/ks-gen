from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import dod_root_ca as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

# Dropped via #127 PR B SSG-drift sweep: the
# install_DoD_intermediate_certificates rule no longer exists in current
# ssg-almalinux9-ds.xml (0.1.80). The closest hits today
# (install_smartcard_packages, only_allow_dod_certs) check different
# things. emit_tailoring returns []; exception_entry still records the
# operator opt-out for the audit trail (mirror ubuntu2404's shape from
# #127 PR A).


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return not cfg.overrides.dod_root_ca.install

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=meta.EXCEPTION_SUMMARY,
            stig_rules_disabled=[],
            reason=meta.EXCEPTION_REASON,
        )


RULE: Rule = cast(Rule, _Rule())
