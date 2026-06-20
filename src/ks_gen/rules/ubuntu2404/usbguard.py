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
        # Deferred: ssg-ubuntu2404-ds.xml usbguard rule IDs land in
        # the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # Deferred with emit_tailoring: when usbguard.enable is wired,
        # this will return ["usbguard"].
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
