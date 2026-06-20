"""ubuntu2404 usbguard rule.

Scaffolding-only port: applies unconditionally so the rule lands in
the Applied-rules count + listing. emit_post is empty (mirrors
alma9 — the meaningful work is in emit_tailoring + exception_entry,
both deferred to the audit-story PR per the phase 3.x pattern).

When the audit-story PR wires up the deferred methods, this rule
will gain ssg-ubuntu2404-ds.xml tailoring ops (select if
overrides.usbguard.enable, disable otherwise) and a paired
exception_entry. At that point, a coordinated edit will likely
also add the `usbguard` package install + service enable in
emit_post — currently neither alma9 nor ubuntu2404 implements that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import usbguard as meta
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
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # ssg-ubuntu2404-ds.xml (0.1.79-1) ships no usbguard rules — phase 1
        # audit confirmed `grep usbguard` returns empty against the Ubuntu
        # rule-IDs list. Nothing to select / disable here; the exception_entry
        # below still records the operator's opt-out for the audit trail.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # Deferred with emit_tailoring: when usbguard.enable is wired,
        # this will return ["usbguard"].
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        if cfg.overrides.usbguard.enable:
            return None
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=meta.EXCEPTION_SUMMARY,
            stig_rules_disabled=[],  # no Ubuntu usbguard SSG rules exist to record
            reason=meta.EXCEPTION_REASON,
        )


RULE: Rule = cast(Rule, _Rule())
