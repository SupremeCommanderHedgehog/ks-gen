from ks_gen.config import (
    AuditdActionsCfg,
    AuditdMaxFileAction,
    AuditdSystemAction,
    Overrides,
)
from ks_gen.rules.auditd_actions import RULE


def test_tailoring_uses_default_actions(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    values = {o.rule_id: o.value for o in ops if o.action == "set_value"}
    assert any("disk_full_action" in k for k in values)
    assert "SUSPEND" in values.get(
        "xccdf_org.ssgproject.content_value_var_auditd_disk_full_action", ""
    )


def test_post_reasserts_auditd_conf(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/audit/auditd.conf" in out
    assert "disk_full_action = SUSPEND" in out
    assert "max_log_file_action = ROTATE" in out


def test_exception_when_actions_not_stig_default(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is not None


def test_no_exception_when_strict_halt(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                auditd=AuditdActionsCfg(
                    disk_full_action=AuditdSystemAction.HALT,
                    disk_error_action=AuditdSystemAction.HALT,
                    max_log_file_action=AuditdMaxFileAction.KEEP_LOGS,
                )
            )
        }
    )
    assert RULE.exception_entry(cfg) is None
