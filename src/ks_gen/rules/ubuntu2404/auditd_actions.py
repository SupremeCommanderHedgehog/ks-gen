"""ubuntu2404 auditd_actions rule.

Installs the auditd package and defensively re-asserts
disk_full_action, disk_error_action, and max_log_file_action in
/etc/audit/auditd.conf to the operator's cfg.overrides.auditd
values. Ubuntu Server does not ship auditd by default (unlike
RHEL), so emit_packages pulls it in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import auditd_actions as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    a = cfg.overrides.auditd
    conf = "/etc/audit/auditd.conf"
    df = a.disk_full_action.value
    de = a.disk_error_action.value
    mf = a.max_log_file_action.value
    return (
        "# Re-assert auditd actions (defensive sed + append-if-missing)\n"
        f"sed -i -E 's|^[# ]*disk_full_action.*|disk_full_action = {df}|' {conf}\n"
        f"grep -q '^disk_full_action' {conf} || echo 'disk_full_action = {df}' >> {conf}\n"
        f"sed -i -E 's|^[# ]*disk_error_action.*|disk_error_action = {de}|' {conf}\n"
        f"grep -q '^disk_error_action' {conf} || echo 'disk_error_action = {de}' >> {conf}\n"
        f"sed -i -E 's|^[# ]*max_log_file_action.*|max_log_file_action = {mf}|' {conf}\n"
        f"grep -q '^max_log_file_action' {conf} || echo 'max_log_file_action = {mf}' >> {conf}\n"
    )


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml var_auditd_* variable IDs
        # land in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # Ubuntu Server doesn't ship auditd by default (unlike RHEL).
        return ["auditd"]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
