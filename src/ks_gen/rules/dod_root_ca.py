from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_RULE_ID = "xccdf_org.ssgproject.content_rule_install_DoD_intermediate_certificates"


@dataclass(frozen=True)
class _Rule:
    id: str = "dod_root_ca"
    summary: str = "Skip DoD root CA bundle installation."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=lambda: [_RULE_ID])

    def applies(self, cfg: HostConfig) -> bool:
        return not cfg.overrides.dod_root_ca.install

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return [TailoringOp(rule_id=_RULE_ID, action="disable")]

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id="dod_root_ca",
            summary="DoD root/intermediate CA bundle not installed.",
            stig_rules_disabled=[_RULE_ID],
            reason="Server is not a DoD asset; bundle is not applicable.",
        )


RULE: Rule = cast(Rule, _Rule())
