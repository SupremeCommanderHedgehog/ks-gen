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


def test_post_reflects_disk_full_action_override(ubuntu_cfg_factory):
    from ks_gen.config import AuditdActionsCfg, AuditdSystemAction, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                auditd=AuditdActionsCfg(disk_full_action=AuditdSystemAction.HALT),
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "disk_full_action = HALT" in out
    # The default value must NOT appear in the disk_full assignment.
    assert "disk_full_action = SUSPEND" not in out


def test_post_reflects_disk_error_action_override(ubuntu_cfg_factory):
    from ks_gen.config import AuditdActionsCfg, AuditdSystemAction, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                auditd=AuditdActionsCfg(disk_error_action=AuditdSystemAction.SYSLOG),
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "disk_error_action = SYSLOG" in out
    assert "disk_error_action = SUSPEND" not in out


def test_post_reflects_max_log_file_action_keep_logs_lowercase(ubuntu_cfg_factory):
    # AuditdMaxFileAction.KEEP_LOGS has string value "keep_logs"
    # (lowercase) — auditd.conf's documented token. The enum's
    # string value lands verbatim in the sed-replace.
    from ks_gen.config import AuditdActionsCfg, AuditdMaxFileAction, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                auditd=AuditdActionsCfg(max_log_file_action=AuditdMaxFileAction.KEEP_LOGS),
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "max_log_file_action = keep_logs" in out
    assert "max_log_file_action = ROTATE" not in out


def test_post_uses_defensive_sed_prefix_for_all_three_directives(ubuntu_cfg_factory):
    # The ^[# ]* prefix handles three states defensively: line
    # uncommented, line commented (e.g., "# disk_full_action = ..."),
    # and line entirely absent (the grep-fallback covers this last
    # case — see the next test).
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "^[# ]*disk_full_action" in out
    assert "^[# ]*disk_error_action" in out
    assert "^[# ]*max_log_file_action" in out


def test_post_appends_with_grep_fallback_for_all_three_directives(ubuntu_cfg_factory):
    # When the line is entirely absent (e.g., Debian downstream
    # rebuild dropped a default), the grep || echo fallback appends
    # the line so the directive is always set.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert (
        "grep -q '^disk_full_action' /etc/audit/auditd.conf || echo 'disk_full_action = SUSPEND'"
    ) in out
    assert (
        "grep -q '^disk_error_action' /etc/audit/auditd.conf || echo 'disk_error_action = SUSPEND'"
    ) in out
    assert (
        "grep -q '^max_log_file_action' /etc/audit/auditd.conf"
        " || echo 'max_log_file_action = ROTATE'"
    ) in out


def test_emit_packages_returns_auditd(ubuntu_cfg_factory):
    # Ubuntu Server's seed doesn't include auditd. Without this pull,
    # /etc/audit/auditd.conf doesn't exist and the sed-replace fails.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == ["auditd"]


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred: ssg-ubuntu2404-ds.xml var_auditd_* variable IDs land
    # in the audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred: runtime-computed English (mirroring alma9's
    # HALT/HALT/keep_logs strict check) lands in the audit-story PR.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import auditd_actions as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []
