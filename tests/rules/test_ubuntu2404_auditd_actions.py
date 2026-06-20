from ks_gen.rules.ubuntu2404.auditd_actions import RULE


def test_post_targets_etc_audit_auditd_conf(ubuntu_cfg_factory):
    # /etc/audit/auditd.conf is the canonical auditd config path on
    # both Ubuntu and RHEL — same upstream auditd package layout.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/audit/auditd.conf" in out


def test_applies_always_returns_true(ubuntu_cfg_factory):
    # No parent enable flag on AuditdActionsCfg — matches alma9.
    # Opting out means reverting field defaults (no-op against stock auditd.conf).
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_post_reasserts_disk_full_action_default_suspend(ubuntu_cfg_factory):
    # Default disk_full_action is SUSPEND (remote-safe; HALT would
    # kill a cloud server on a log-volume spike).
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "disk_full_action = SUSPEND" in out


def test_post_reasserts_disk_error_action_default_suspend(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "disk_error_action = SUSPEND" in out


def test_post_reasserts_max_log_file_action_default_rotate(ubuntu_cfg_factory):
    # Default max_log_file_action is ROTATE (keeps recent logs,
    # avoids unbounded growth).
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "max_log_file_action = ROTATE" in out
