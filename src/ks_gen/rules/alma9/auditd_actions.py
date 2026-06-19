from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_value_"
_VAR_DISK_FULL = f"{_PREFIX}var_auditd_disk_full_action"
_VAR_DISK_ERROR = f"{_PREFIX}var_auditd_disk_error_action"
_VAR_MAX_LOG = f"{_PREFIX}var_auditd_max_log_file_action"


@dataclass(frozen=True)
class _Rule:
    id: str = "auditd_actions"
    summary: str = "auditd disk_full/disk_error/max_log_file actions (SUSPEND/ROTATE default)."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        a = cfg.overrides.auditd
        return [
            TailoringOp(rule_id=_VAR_DISK_FULL, action="set_value", value=a.disk_full_action.value),
            TailoringOp(
                rule_id=_VAR_DISK_ERROR, action="set_value", value=a.disk_error_action.value
            ),
            TailoringOp(
                rule_id=_VAR_MAX_LOG, action="set_value", value=a.max_log_file_action.value
            ),
        ]

    def emit_post(self, cfg: HostConfig) -> str:
        a = cfg.overrides.auditd
        conf = "/etc/audit/auditd.conf"
        return "\n".join(
            [
                "# Re-assert auditd actions",
                f"sed -i -E 's|^disk_full_action.*|disk_full_action = {a.disk_full_action.value}|' {conf}",  # noqa: E501
                f"sed -i -E 's|^disk_error_action.*|disk_error_action = {a.disk_error_action.value}|' {conf}",  # noqa: E501
                f"sed -i -E 's|^max_log_file_action.*|max_log_file_action = {a.max_log_file_action.value}|' {conf}",  # noqa: E501
                "",
            ]
        )

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        a = cfg.overrides.auditd
        strict = (
            a.disk_full_action.value == "HALT"
            and a.disk_error_action.value == "HALT"
            and a.max_log_file_action.value == "keep_logs"
        )
        if strict:
            return None
        return ExceptionEntry(
            rule_id="auditd_actions",
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
