"""ubuntu2404 dod_root_ca rule.

Scaffolding-only port mirroring alma9. applies = not install — the
rule "fires" when the operator is NOT installing the DoD CA bundle
(default, civilian use). emit_post is empty (alma9 never
implemented the install-the-bundle branch). The meaningful work
(emit_tailoring disable of the SSG install_DoD_intermediate_certificates
rule + exception_entry) is deferred to the audit-story PR per the
phase 3.x pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import dod_root_ca as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return not cfg.overrides.dod_root_ca.install

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # ssg-ubuntu2404-ds.xml has no `install_DoD_intermediate_certificates`
        # equivalent. The closest hits (`only_allow_dod_certs`,
        # `install_smartcard_packages`) check different things. Nothing to
        # disable; the exception_entry below still records the operator's
        # opt-out for the audit trail.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=meta.EXCEPTION_SUMMARY,
            stig_rules_disabled=[],  # no Ubuntu DoD-CA SSG rule exists to record
            reason=meta.EXCEPTION_REASON,
        )


RULE: Rule = cast(Rule, _Rule())
