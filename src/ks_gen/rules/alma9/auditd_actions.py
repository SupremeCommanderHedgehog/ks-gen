"""auditd disk_full / disk_error / max_log_file actions.

The three actions are always written into /etc/audit/auditd.conf by
`emit_post`. What differs per distro is which stig-selected SSG rule (if any)
governs each setting, and how — so each distro declares that as data (#68):

- A rule whose *check or fix* reads the XCCDF Value gets a `set_value`, so the
  scan and oscap's remediation both follow the operator's choice. A Value no
  enabled stig-selected rule reads gets no `set_value`: it would be inert
  tailoring — including when the only reader is disabled below.
- A rule whose *check* hardcodes the accepted values (alma9's `_stig`
  variants) fails for any other choice, so it is disabled and named in the
  exception entry — never left to fail unexplained (#61, #65).
- The exception entry exists exactly when a choice falls outside what the
  distro's STIG content asks for. A distro whose stig profile governs none of
  the three (alma10) has nothing to deviate from.

Module-level so the alma8 and alma10 siblings can import rather than
duplicate; only their `Setting` tables differ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, cast

from ks_gen.rules._meta import auditd_actions as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_VALUE = "xccdf_org.ssgproject.content_value_"
_RULE = "xccdf_org.ssgproject.content_rule_"

SettingName = Literal["disk_full_action", "disk_error_action", "max_log_file_action"]


@dataclass(frozen=True)
class Setting:
    """How one auditd.conf setting is governed by a distro's stig profile.

    `rule` is the stig-selected rule that reads the Value, or None when no
    selected rule does. `accepts` is what that distro's STIG content requires
    (casefolded), or None when it requires nothing. `check_reads_value` says
    whether the rule's check compares against the Value (so a `set_value`
    makes any choice verify) or against hardcoded `accepts` (so other choices
    fail and must be disabled).
    """

    name: SettingName
    rule: str | None = None
    accepts: frozenset[str] | None = None
    check_reads_value: bool = False

    @property
    def value_id(self) -> str:
        return f"{_VALUE}var_auditd_{self.name}"

    def chosen(self, cfg: HostConfig) -> str:
        return str(getattr(cfg.overrides.auditd, self.name).value)

    def deviates(self, cfg: HostConfig) -> bool:
        return self.accepts is not None and self.chosen(cfg).casefold() not in self.accepts

    def fails_check(self, cfg: HostConfig) -> bool:
        return self.rule is not None and not self.check_reads_value and self.deviates(cfg)


_SYSTEM_ACTIONS = frozenset({"syslog", "single", "halt"})


@dataclass(frozen=True)
class AuditdActions:
    settings: tuple[Setting, ...]
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))

    def _asks(self) -> str:
        return "; ".join(
            f"{s.name} in {'|'.join(sorted(s.accepts))}"
            for s in self.settings
            if s.accepts is not None
        )

    @property
    def stig_rules_affected(self) -> list[str]:
        return [s.rule for s in self.settings if s.rule is not None]

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def _disabled(self, cfg: HostConfig) -> list[str]:
        return [s.rule for s in self.settings if s.rule is not None and s.fails_check(cfg)]

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        ops = [
            TailoringOp(rule_id=s.value_id, action="set_value", value=s.chosen(cfg))
            for s in self.settings
            if s.rule is not None and not s.fails_check(cfg)
        ]
        ops += [TailoringOp(rule_id=rid, action="disable") for rid in self._disabled(cfg)]
        return ops

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
        if not any(s.deviates(cfg) for s in self.settings):
            return None
        a = cfg.overrides.auditd
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=(
                f"disk_full={a.disk_full_action.value}, "
                f"disk_error={a.disk_error_action.value}, "
                f"max_log_file={a.max_log_file_action.value}"
            ),
            stig_rules_disabled=self._disabled(cfg),
            reason=(
                "The chosen actions fall outside what this distro's stig profile asks for "
                f"({self._asks()}). ks-gen defaults to SUSPEND/ROTATE because HALT can take "
                "a remote server down on a log-volume spike, while SUSPEND keeps audit "
                "semantics and the box reachable."
            ),
        )


# ssg-almalinux9 0.1.82 selects the `_stig` variants. Their fixes read the
# Values (so set_value steers oscap's remediation) but their checks hardcode
# SYSLOG|SINGLE|HALT and rotate|single, so other choices must be disabled.
SETTINGS: tuple[Setting, ...] = (
    Setting("disk_full_action", f"{_RULE}auditd_data_disk_full_action_stig", _SYSTEM_ACTIONS),
    Setting("disk_error_action", f"{_RULE}auditd_data_disk_error_action_stig", _SYSTEM_ACTIONS),
    Setting(
        "max_log_file_action",
        f"{_RULE}auditd_data_retention_max_log_file_action_stig",
        frozenset({"rotate", "single"}),
    ),
)

RULE: Rule = cast(Rule, AuditdActions(SETTINGS))
