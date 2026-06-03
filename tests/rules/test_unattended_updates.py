from ks_gen.config import (
    NightlySecurityCfg,
    Overrides,
    RebootWindowCfg,
    UnattendedUpdatesCfg,
)
from ks_gen.rules.unattended_updates import RULE


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
