from ks_gen.config import (
    MonthlyFullCfg,
    NightlySecurityCfg,
    Overrides,
    RebootWindowCfg,
    UnattendedUpdatesCfg,
)
from ks_gen.rules.alma9.unattended_updates import RULE


def test_rule_metadata():
    assert RULE.id == "unattended_updates"
    assert RULE.depends_on == []
    assert RULE.stig_rules_affected == []
    assert "dnf-automatic" in RULE.summary or "unattended" in RULE.summary.lower()


def test_applies_when_enabled(minimal_cfg):
    assert RULE.applies(minimal_cfg) is True


def test_does_not_apply_when_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={"overrides": Overrides(unattended_updates=UnattendedUpdatesCfg(enable=False))}
    )
    assert RULE.applies(cfg) is False


def test_emit_tailoring_is_empty(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []


def test_exception_entry_is_none(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is None


def test_nightly_security_emits_dnf_automatic_conf(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "cat > /etc/dnf/automatic.conf" in out
    assert "upgrade_type = security" in out
    assert "apply_updates = yes" in out
    assert "reboot = never" in out


def test_nightly_security_emits_timer_dropin(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/systemd/system/dnf-automatic.timer.d/ks-gen.conf" in out
    # critical: empty OnCalendar= to reset list before adding the override
    assert "OnCalendar=\nOnCalendar=*-*-* 02:00:00" in out
    assert "systemctl enable dnf-automatic.timer" in out


def test_nightly_security_honors_custom_on_calendar(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    nightly_security=NightlySecurityCfg(on_calendar="Mon..Fri 23:30")
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "OnCalendar=Mon..Fri 23:30" in out


def test_nightly_security_omitted_when_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    nightly_security=NightlySecurityCfg(enable=False),
                    reboot_window=RebootWindowCfg(enable=False),
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "/etc/dnf/automatic.conf" not in out
    assert "dnf-automatic.timer.d" not in out


def test_monthly_full_emits_separate_config_and_timer(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "cat > /etc/dnf/automatic-full.conf" in out
    assert "upgrade_type = default" in out
    assert "ks-gen-dnf-automatic-full.service" in out
    assert "ks-gen-dnf-automatic-full.timer" in out
    assert "OnCalendar=Sun *-*-1..7 02:30:00" in out
    assert "Persistent=true" in out
    assert "systemctl enable ks-gen-dnf-automatic-full.timer" in out


def test_monthly_full_honors_custom_on_calendar(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    monthly_full=MonthlyFullCfg(on_calendar="*-*-15 04:00:00")
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "OnCalendar=*-*-15 04:00:00" in out


def test_monthly_full_omitted_when_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(monthly_full=MonthlyFullCfg(enable=False))
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "/etc/dnf/automatic-full.conf" not in out
    assert "ks-gen-dnf-automatic-full" not in out


def test_reboot_window_emits_script_service_and_timer(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/usr/local/sbin/ks-gen-reboot-if-needed" in out
    assert "needs-restarting -r" in out
    assert "systemctl reboot" in out
    assert "ks-gen-reboot-if-needed.service" in out
    assert "ks-gen-reboot-if-needed.timer" in out
    assert "OnCalendar=Sun *-*-* 03:00:00" in out
    assert "systemctl enable ks-gen-reboot-if-needed.timer" in out
    assert "$(date -Is)" in out


def test_reboot_window_honors_custom_on_calendar(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    reboot_window=RebootWindowCfg(on_calendar="*-*-* 06:00:00")
                )
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "OnCalendar=*-*-* 06:00:00" in out


def test_reboot_window_omitted_when_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(reboot_window=RebootWindowCfg(enable=False))
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "ks-gen-reboot-if-needed" not in out


def test_reboot_script_fails_loud_on_missing_needs_restarting(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    # The script must log at error level and exit non-zero rather than reboot.
    assert "needs-restarting missing" in out
    assert "exit 1" in out


def test_emit_packages_includes_dnf_automatic_and_dnf_utils_by_default(minimal_cfg):
    # All three sub-flags default to enabled, so both packages are required.
    assert RULE.emit_packages(minimal_cfg) == ["dnf-automatic", "dnf-utils"]


def test_emit_packages_drops_dnf_utils_when_reboot_window_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(reboot_window=RebootWindowCfg(enable=False))
            )
        }
    )
    assert RULE.emit_packages(cfg) == ["dnf-automatic"]


def test_emit_packages_empty_when_all_sub_blocks_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    nightly_security=NightlySecurityCfg(enable=False),
                    monthly_full=MonthlyFullCfg(enable=False),
                    reboot_window=RebootWindowCfg(enable=False),
                )
            )
        }
    )
    assert RULE.emit_packages(cfg) == []
