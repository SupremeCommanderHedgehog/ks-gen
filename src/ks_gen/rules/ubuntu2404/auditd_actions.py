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
        # All three var_auditd_* IDs exist verbatim on ubuntu2404 (variables
        # are typically SSG-shared across distros).
        a = cfg.overrides.auditd
        return [
            TailoringOp(
                rule_id="xccdf_org.ssgproject.content_value_var_auditd_disk_full_action",
                action="set_value",
                value=a.disk_full_action.value,
            ),
            TailoringOp(
                rule_id="xccdf_org.ssgproject.content_value_var_auditd_disk_error_action",
                action="set_value",
                value=a.disk_error_action.value,
            ),
            TailoringOp(
                rule_id="xccdf_org.ssgproject.content_value_var_auditd_max_log_file_action",
                action="set_value",
                value=a.max_log_file_action.value,
            ),
        ]

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # Ubuntu Server doesn't ship auditd by default (unlike RHEL).
        return ["auditd"]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Mirror alma9: STIG-strict HALT/HALT/keep_logs → no exception.
        a = cfg.overrides.auditd
        strict = (
            a.disk_full_action.value == "HALT"
            and a.disk_error_action.value == "HALT"
            and a.max_log_file_action.value == "keep_logs"
        )
        if strict:
            return None
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=(
                f"disk_full={a.disk_full_action.value}, "
                f"disk_error={a.disk_error_action.value}, "
                f"max_log_file={a.max_log_file_action.value}"
            ),
            stig_rules_disabled=[],
            reason=(
                "STIG defaults (HALT / keep_logs) can kill a remote server on a log-volume "
                "spike. SUSPEND/ROTATE keeps audit semantics while keeping the box reachable."
            ),
        )


RULE: Rule = cast(Rule, _Rule())
