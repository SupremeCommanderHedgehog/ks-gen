from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import faillock_safety as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_"
_VAR_UNLOCK = f"{_PREFIX}value_var_accounts_passwords_pam_faillock_unlock_time"
_VAR_DENY = f"{_PREFIX}value_var_accounts_passwords_pam_faillock_deny"
# Renamed via #127 PR B SSG-drift sweep: the upstream SSG rule dropped
# the "even_" prefix in `_even_deny_root` → `_deny_root` between the SSG
# version this code was originally written against and current
# ssg-almalinux9-ds.xml (0.1.80). The cfg.overrides.faillock.even_deny_root
# field name is unchanged — that's the operator-facing knob.
_RULE_DENY_ROOT = f"{_PREFIX}rule_accounts_passwords_pam_faillock_deny_root"


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: [_RULE_DENY_ROOT])

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.faillock.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        f = cfg.overrides.faillock
        ops: list[TailoringOp] = [
            TailoringOp(rule_id=_VAR_UNLOCK, action="set_value", value=str(f.unlock_time)),
            TailoringOp(rule_id=_VAR_DENY, action="set_value", value=str(f.deny)),
        ]
        if not f.even_deny_root:
            ops.append(TailoringOp(rule_id=_RULE_DENY_ROOT, action="disable"))
        return ops

    def emit_post(self, cfg: HostConfig) -> str:
        f = cfg.overrides.faillock
        even = "yes" if f.even_deny_root else "no"
        conf = "/etc/security/faillock.conf"
        return "\n".join(
            [
                "# Re-assert faillock.conf in case oscap over-tightened",
                f"sed -i -E 's/^[# ]*unlock_time *=.*/unlock_time = {f.unlock_time}/' {conf}",
                f"grep -q '^unlock_time' {conf} || echo 'unlock_time = {f.unlock_time}' >> {conf}",
                f"sed -i -E 's/^[# ]*deny *=.*/deny = {f.deny}/' {conf}",
                f"grep -q '^deny' {conf} || echo 'deny = {f.deny}' >> {conf}",
                f"sed -i -E 's/^[# ]*even_deny_root.*/# even_deny_root removed by ks-gen: {even}/' {conf}",  # noqa: E501
                "",
            ]
        )

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        f = cfg.overrides.faillock
        if f.even_deny_root and f.unlock_time == 0:
            return None
        disabled = [_RULE_DENY_ROOT] if not f.even_deny_root else []
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=f"unlock_time={f.unlock_time}, even_deny_root={f.even_deny_root}",
            stig_rules_disabled=disabled,
            reason=meta.EXCEPTION_REASON,
        )


RULE: Rule = cast(Rule, _Rule())
