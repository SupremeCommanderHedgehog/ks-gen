import pytest

from ks_gen.config import (
    AuditdActionsCfg,
    AuditdMaxFileAction,
    AuditdSystemAction,
    Overrides,
)
from ks_gen.registry import load_rules

_V = "xccdf_org.ssgproject.content_value_var_auditd_"
_R = "xccdf_org.ssgproject.content_rule_auditd_data_"


def _rule(distro: str):
    return next(r for r in load_rules(distro) if r.id == "auditd_actions")


def _with(cfg, disk_full, disk_error, max_log):
    return cfg.model_copy(
        update={
            "overrides": Overrides(
                auditd=AuditdActionsCfg(
                    disk_full_action=disk_full,
                    disk_error_action=disk_error,
                    max_log_file_action=max_log,
                )
            )
        }
    )


# What each distro's stig profile asks for (#68): alma9's `_stig` checks accept
# rotate|single for max_log_file_action; alma8 refines it to syslog.
_STRICT_MAX_LOG = {"alma8": AuditdMaxFileAction.SYSLOG, "alma9": AuditdMaxFileAction.ROTATE}


def _strict(cfg, distro):
    return _with(cfg, AuditdSystemAction.HALT, AuditdSystemAction.HALT, _STRICT_MAX_LOG[distro])


def _ops(distro, cfg, action):
    return {o.rule_id: o.value for o in _rule(distro).emit_tailoring(cfg) if o.action == action}


@pytest.mark.parametrize("distro", ["alma8", "alma9", "alma10"])
def test_post_reasserts_auditd_conf_on_every_distro(minimal_cfg, distro):
    out = _rule(distro).emit_post(minimal_cfg)
    assert "/etc/audit/auditd.conf" in out
    assert "disk_full_action = SUSPEND" in out
    assert "max_log_file_action = ROTATE" in out


# ---- #68: set_value only where a stig-selected rule reads the Value ----


def test_alma9_sets_all_three_values_its_stig_rules_remediate_from(minimal_cfg):
    assert _ops("alma9", _strict(minimal_cfg, "alma9"), "set_value") == {
        f"{_V}disk_full_action": "HALT",
        f"{_V}disk_error_action": "HALT",
        f"{_V}max_log_file_action": "ROTATE",
    }


def test_alma9_drops_the_set_value_of_a_rule_it_disables(minimal_cfg):
    """A deselected reader runs neither check nor fix, so its set_value is inert."""
    assert _ops("alma9", minimal_cfg, "set_value") == {f"{_V}max_log_file_action": "ROTATE"}


def test_alma8_sets_only_the_disk_values(minimal_cfg):
    """No stig-selected alma8 rule reads var_auditd_max_log_file_action."""
    assert set(_ops("alma8", minimal_cfg, "set_value")) == {
        f"{_V}disk_full_action",
        f"{_V}disk_error_action",
    }


def test_alma10_emits_no_tailoring(minimal_cfg):
    """AL10's stig profile selects none of the governing rules."""
    assert _rule("alma10").emit_tailoring(minimal_cfg) == []


# ---- alma9's `_stig` checks hardcode the accepted values ----


def test_alma9_default_disables_and_names_the_failing_disk_rules(minimal_cfg):
    disabled = set(_ops("alma9", minimal_cfg, "disable"))
    assert disabled == {f"{_R}disk_full_action_stig", f"{_R}disk_error_action_stig"}
    entry = _rule("alma9").exception_entry(minimal_cfg)
    assert entry is not None
    assert set(entry.stig_rules_disabled) == disabled


def test_alma9_keep_logs_fails_the_max_log_stig_check(minimal_cfg):
    """keep_logs is not in rotate|single, so 'HALT/HALT/keep_logs' is not strict here."""
    cfg = _with(
        minimal_cfg,
        AuditdSystemAction.HALT,
        AuditdSystemAction.HALT,
        AuditdMaxFileAction.KEEP_LOGS,
    )
    entry = _rule("alma9").exception_entry(cfg)
    assert entry is not None
    assert entry.stig_rules_disabled == [f"{_R}retention_max_log_file_action_stig"]
    assert f"{_V}max_log_file_action" not in _ops("alma9", cfg, "set_value")


def test_alma8_never_disables_because_its_checks_read_the_values(minimal_cfg):
    assert _ops("alma8", minimal_cfg, "disable") == {}
    entry = _rule("alma8").exception_entry(minimal_cfg)
    assert entry is not None, "SUSPEND is outside alma8's refined syslog|single|halt"
    assert entry.stig_rules_disabled == []


# ---- exception entry: only for a real deviation ----


@pytest.mark.parametrize("distro", ["alma8", "alma9"])
def test_no_exception_when_choices_are_stig_acceptable(minimal_cfg, distro):
    cfg = _strict(minimal_cfg, distro)
    assert _rule(distro).exception_entry(cfg) is None
    assert _ops(distro, cfg, "disable") == {}


def test_alma10_has_no_stig_requirement_to_deviate_from(minimal_cfg):
    assert _rule("alma10").exception_entry(minimal_cfg) is None


def test_alma8_documents_a_max_log_choice_no_rule_checks(minimal_cfg):
    """Refined to syslog but read by no selected rule: documented, not tailored."""
    cfg = _with(
        minimal_cfg, AuditdSystemAction.HALT, AuditdSystemAction.HALT, AuditdMaxFileAction.ROTATE
    )
    entry = _rule("alma8").exception_entry(cfg)
    assert entry is not None
    assert entry.stig_rules_disabled == []
    assert "max_log_file_action in syslog" in entry.reason


def test_exception_reason_names_what_the_distro_asks_for(minimal_cfg):
    entry = _rule("alma9").exception_entry(minimal_cfg)
    assert entry is not None
    assert "disk_full_action in halt|single|syslog" in entry.reason
    assert "max_log_file_action in rotate|single" in entry.reason
