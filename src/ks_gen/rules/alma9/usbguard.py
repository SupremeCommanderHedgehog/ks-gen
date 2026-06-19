from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_USBGUARD_RULES = [
    f"{_PREFIX}package_usbguard_installed",
    f"{_PREFIX}service_usbguard_enabled",
    f"{_PREFIX}configure_usbguard_auditbackend",
]


@dataclass(frozen=True)
class _Rule:
    id: str = "usbguard"
    summary: str = "Enable or disable USBGuard install + service per overrides."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_USBGUARD_RULES))

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        if cfg.overrides.usbguard.enable:
            return [TailoringOp(rule_id=r, action="select") for r in _USBGUARD_RULES]
        return [TailoringOp(rule_id=r, action="disable") for r in _USBGUARD_RULES]

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        if cfg.overrides.usbguard.enable:
            return None
        return ExceptionEntry(
            rule_id="usbguard",
            summary="USBGuard not installed/enabled.",
            stig_rules_disabled=list(_USBGUARD_RULES),
            reason=(
                "Cloud/headless VMs have no USB; USBGuard is overhead with no benefit. "
                "Enable explicitly on bare-metal hosts."
            ),
        )


RULE: Rule = cast(Rule, _Rule())
